"""Atlas indicator tables (docs/specs/atlas-indicators.md): one table per level (atlas units, districts, subregions,
metro areas), built from additive components so that every level is computed the same way.

Components, per atlas unit:
  population   2020 census and Vintage 2025 estimate (regions/units), land area (2020 Gazetteer, tracts)
  ACS          2020-2024 five-year estimates summed from 2020 tracts (every unit is a set of whole tracts); income and
               home-value brackets for estimated medians
  QCEW 2024    establishments, employment, wages: total, government (federal + state + local), private, and the 11
               private supersectors (regions/data/qcew_2024_units.csv)
  BEA 2024     GDP (current, real), personal income and transfers, earnings by place of work (regions/data/bea_units.csv)
Indicators (indicator_catalogue.csv) are components or ratios of two summed components; medians are estimated from the
summed brackets by linear interpolation within the median's bracket (the Census Bureau's method for derived medians).
A level's value is missing when any member's component is missing (a QCEW or BEA cell withheld at the county, ACS
without an estimate, or BEA in Puerto Rico, which it does not cover). BEA's combined areas (Virginia's independent cities
with a neighbouring county, Maui with Kalawao) have no unit values; a level holding every member of one takes the
combined area's figure. Government jobs are QCEW total minus private (both always published), so a withheld federal,
state or local cell does not blank them. Mean commute time uses only tracts with an aggregate travel time.

Writes next to this script:
  indicator_catalogue.csv           indicator_id, label, unit, kind, numerator, denominator, scale, source, year
  components_units.csv              unit_id and every component (for re-aggregating to any union of units)
  indicators_units.csv, indicators_districts.csv, indicators_subregions.csv, indicators_metros.csv
usage: python3 build_indicators.py --cache DIR
"""
import argparse, collections, csv, io, os, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, "..")
sys.path[:0] = [os.path.join(R, "pieces"), os.path.join(R, "keys"), os.path.join(R, "data")]
import build_crosswalk as bx  # noqa: E402
import build_keys as bk  # noqa: E402
import apply_bea as ab  # noqa: E402

GAZ = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2020_Gazetteer/2020_Gaz_tracts_national.zip"
INC_EDGES = [0, 10e3, 15e3, 20e3, 25e3, 30e3, 35e3, 40e3, 45e3, 50e3, 60e3, 75e3, 100e3, 125e3, 150e3, 200e3, None]  # B19001_002-017
VAL_EDGES = [0, 10e3, 15e3, 20e3, 25e3, 30e3, 35e3, 40e3, 50e3, 60e3, 70e3, 80e3, 90e3, 100e3, 125e3, 150e3, 175e3, 200e3,
             250e3, 300e3, 400e3, 500e3, 750e3, 1e6, 1.5e6, 2e6, None]  # B25075_002-027

# ACS components: name -> (table, [variables summed])
ACS_COMP = {
    "acs_pop": ("B01001", ["001"]),
    "acs_under18": ("B01001", [f"{i:03d}" for i in list(range(3, 7)) + list(range(27, 31))]),
    "acs_65plus": ("B01001", [f"{i:03d}" for i in list(range(20, 26)) + list(range(44, 50))]),
    "acs_hisp_base": ("B03002", ["001"]), "acs_hispanic": ("B03002", ["012"]), "acs_nh_white": ("B03002", ["003"]),
    "acs_nh_black": ("B03002", ["004"]), "acs_nh_asian": ("B03002", ["006"]),
    "acs_nativity_base": ("B05002", ["001"]), "acs_foreign_born": ("B05002", ["013"]),
    "acs_households": ("B11001", ["001"]),
    "acs_pov_base": ("B17001", ["001"]), "acs_poverty": ("B17001", ["002"]),
    "acs_pop25": ("B15003", ["001"]), "acs_bachelors_plus": ("B15003", ["022", "023", "024", "025"]),
    "acs_pop16": ("B23025", ["001"]), "acs_labor_force": ("B23025", ["002"]), "acs_civ_lf": ("B23025", ["003"]),
    "acs_employed": ("B23025", ["004"]), "acs_unemployed": ("B23025", ["005"]),
    "acs_occ_units": ("B25003", ["001"]), "acs_owner_occ": ("B25003", ["002"]),
    "acs_renters_computed": ("B25070", [f"{i:03d}" for i in range(2, 11)]), "acs_rent_burdened": ("B25070", ["007", "008", "009", "010"]),
    "acs_hh_vehicles_base": ("B08201", ["001"]), "acs_hh_no_vehicle": ("B08201", ["002"]),
    "acs_workers": ("B08301", ["001"]), "acs_work_home": ("B08301", ["021"]), "acs_travel_minutes": ("B08013", ["001"]),
    "acs_ins_base": ("B27010", ["001"]), "acs_uninsured": ("B27010", ["017", "033", "050", "066"]),
}
ACS_COMP.update({f"acs_inc_b{i:02d}": ("B19001", [f"{i + 2:03d}"]) for i in range(16)})
ACS_COMP.update({f"acs_val_b{i:02d}": ("B25075", [f"{i + 2:03d}"]) for i in range(26)})

SUPERSECTORS = {"1011": "Natural resources and mining", "1012": "Construction", "1013": "Manufacturing",
                "1021": "Trade, transportation and utilities", "1022": "Information", "1023": "Financial activities",
                "1024": "Professional and business services", "1025": "Education and health services",
                "1026": "Leisure and hospitality", "1027": "Other services", "1029": "Unclassified"}
BEA_COMP = {"bea_gdp": ("CAGDP2", "1"), "bea_gdp_real": ("CAGDP9", "1"), "bea_personal_income": ("CAINC4", "10"),
            "bea_population": ("CAINC4", "20"), "bea_transfers": ("CAINC4", "47"), "bea_earnings_pow": ("CAINC4", "35")}

# indicators: id, label, unit, kind, numerator, denominator, scale, source, year
CATALOGUE = [
    ("pop2020", "Population, 2020 census", "persons", "count", "pop2020", "", 1, "Census 2020 (PL 94-171, tracts)", "2020"),
    ("pop2025", "Population, 2025 estimate", "persons", "count", "pop2025", "", 1, "Census Vintage 2025 estimates", "2025"),
    ("pop_change_2020_25", "Population change, 2020 to 2025", "%", "change", "pop2025", "pop2020", 100, "Census 2020, Vintage 2025", "2020-2025"),
    ("density_2025", "Residents per square mile of land, 2025", "per sq mi", "ratio", "pop2025", "land_sqmi", 1, "Vintage 2025; 2020 Gazetteer", "2025"),
    ("share_under18", "Residents under 18", "%", "rate", "acs_under18", "acs_pop", 100, "ACS 2020-2024 B01001", "2020-2024"),
    ("share_65plus", "Residents 65 and over", "%", "rate", "acs_65plus", "acs_pop", 100, "ACS 2020-2024 B01001", "2020-2024"),
    ("share_hispanic", "Hispanic or Latino", "%", "rate", "acs_hispanic", "acs_hisp_base", 100, "ACS 2020-2024 B03002", "2020-2024"),
    ("share_nh_white", "White alone, not Hispanic", "%", "rate", "acs_nh_white", "acs_hisp_base", 100, "ACS 2020-2024 B03002", "2020-2024"),
    ("share_nh_black", "Black alone, not Hispanic", "%", "rate", "acs_nh_black", "acs_hisp_base", 100, "ACS 2020-2024 B03002", "2020-2024"),
    ("share_nh_asian", "Asian alone, not Hispanic", "%", "rate", "acs_nh_asian", "acs_hisp_base", 100, "ACS 2020-2024 B03002", "2020-2024"),
    ("share_foreign_born", "Foreign-born residents", "%", "rate", "acs_foreign_born", "acs_nativity_base", 100, "ACS 2020-2024 B05002", "2020-2024"),
    ("households", "Households", "households", "count", "acs_households", "", 1, "ACS 2020-2024 B11001", "2020-2024"),
    ("median_hh_income", "Median household income (estimated from brackets)", "$ (2024)", "median", "acs_inc_b*", "", 1, "ACS 2020-2024 B19001", "2020-2024"),
    ("poverty_rate", "Residents below the poverty line", "%", "rate", "acs_poverty", "acs_pov_base", 100, "ACS 2020-2024 B17001", "2020-2024"),
    ("share_bachelors", "Bachelor's degree or higher, 25 and over", "%", "rate", "acs_bachelors_plus", "acs_pop25", 100, "ACS 2020-2024 B15003", "2020-2024"),
    ("lf_participation", "Labour force participation, 16 and over", "%", "rate", "acs_labor_force", "acs_pop16", 100, "ACS 2020-2024 B23025", "2020-2024"),
    ("unemployment_rate", "Unemployment rate (civilian labour force)", "%", "rate", "acs_unemployed", "acs_civ_lf", 100, "ACS 2020-2024 B23025", "2020-2024"),
    ("share_uninsured", "Residents without health insurance", "%", "rate", "acs_uninsured", "acs_ins_base", 100, "ACS 2020-2024 B27010", "2020-2024"),
    ("share_owner_occupied", "Owner-occupied homes", "%", "rate", "acs_owner_occ", "acs_occ_units", 100, "ACS 2020-2024 B25003", "2020-2024"),
    ("median_home_value", "Median owner-occupied home value (estimated from brackets)", "$ (2024)", "median", "acs_val_b*", "", 1, "ACS 2020-2024 B25075", "2020-2024"),
    ("share_rent_burdened", "Renters paying 30%+ of income on rent", "%", "rate", "acs_rent_burdened", "acs_renters_computed", 100, "ACS 2020-2024 B25070", "2020-2024"),
    ("share_no_vehicle", "Households without a vehicle", "%", "rate", "acs_hh_no_vehicle", "acs_hh_vehicles_base", 100, "ACS 2020-2024 B08201", "2020-2024"),
    ("share_work_home", "Workers working from home", "%", "rate", "acs_work_home", "acs_workers", 100, "ACS 2020-2024 B08301", "2020-2024"),
    ("mean_commute_min", "Mean travel time to work (those not working from home)", "minutes", "ratio", "acs_travel_minutes", "acs_commuters", 1, "ACS 2020-2024 B08013, B08301", "2020-2024"),
    ("qcew_estabs", "Establishments", "establishments", "count", "qcew_estabs", "", 1, "BLS QCEW 2024 annual", "2024"),
    ("qcew_jobs", "Jobs (annual average employment)", "jobs", "count", "qcew_jobs", "", 1, "BLS QCEW 2024 annual", "2024"),
    ("qcew_avg_weekly_wage", "Average weekly wage", "$", "ratio", "qcew_wages", "qcew_job_weeks", 1, "BLS QCEW 2024 annual", "2024"),
    ("jobs_per_employed_resident", "Jobs per employed resident", "ratio", "ratio", "qcew_jobs", "acs_employed", 1, "QCEW 2024; ACS 2020-2024 B23025", "2024 / 2020-2024"),
    ("share_jobs_government", "Jobs in government (federal, state, local)", "%", "rate", "qcew_jobs_gov", "qcew_jobs", 100, "BLS QCEW 2024 annual", "2024"),
] + [(f"share_jobs_{c}", f"Private jobs: {n}", "%", "rate", f"qcew_jobs_{c}", "qcew_jobs", 100, "BLS QCEW 2024 annual", "2024")
     for c, n in SUPERSECTORS.items()] + [
    ("gdp", "GDP (current dollars)", "$ thousands", "count", "bea_gdp", "", 1, "BEA CAGDP2 2024", "2024"),
    ("gdp_real", "Real GDP (chained 2017 dollars)", "$ thousands", "count", "bea_gdp_real", "", 1, "BEA CAGDP9 2024", "2024"),
    ("gdp_per_job", "GDP per QCEW job", "$", "ratio", "bea_gdp", "qcew_jobs", 1000, "BEA CAGDP2 2024; QCEW 2024", "2024"),
    ("personal_income", "Personal income", "$ thousands", "count", "bea_personal_income", "", 1, "BEA CAINC4 2024", "2024"),
    ("pc_personal_income", "Per capita personal income", "$", "ratio", "bea_personal_income", "bea_population", 1000, "BEA CAINC4 2024", "2024"),
    ("share_income_transfers", "Personal income from transfer receipts", "%", "rate", "bea_transfers", "bea_personal_income", 100, "BEA CAINC4 2024", "2024"),
]


def median_from(counts, edges):
    """Median of a bracketed distribution, by linear interpolation in the median bracket (open top: its lower edge)."""
    tot = sum(counts)
    if not tot:
        return None
    half, cum = tot / 2, 0.0
    for i, n in enumerate(counts):
        if cum + n >= half and n:
            lo, hi = edges[i], edges[i + 1]
            return lo if hi is None else lo + (half - cum) / n * (hi - lo)
        cum += n
    return None


def num(x):
    return None if x in ("", None) else float(x)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True)
    a = ap.parse_args(); bx.CACHE = a.cache; bx.fix_hash_seed()
    U = os.path.join(R, "units")
    units = {u["unit_id"]: u for u in csv.DictReader(open(os.path.join(U, "atlas_units.csv")))}
    unit_of = {r["tract_geoid"]: r["unit_id"] for r in csv.DictReader(open(os.path.join(U, "crosswalk_tract_unit.csv")))}
    tracts = set(unit_of)
    comp = {k: collections.defaultdict(lambda: None) for k in units}
    for k, u in units.items():
        comp[k]["pop2020"] = float(u["pop2020"]); comp[k]["pop2025"] = float(u["pop2025_est"])

    # land area: 2020 Gazetteer tracts (square miles)
    z = zipfile.ZipFile(bx.fetch(GAZ))
    land = collections.Counter()
    with z.open(z.namelist()[0]) as fh:
        r = csv.reader(io.TextIOWrapper(fh, encoding="latin-1"), delimiter="\t"); h = [c.strip() for c in next(r)]
        gi, li = h.index("GEOID"), h.index("ALAND_SQMI")
        for row in r:
            if row[gi] in unit_of:
                land[unit_of[row[gi]]] += float(row[li])
    for k in units:
        comp[k]["land_sqmi"] = land[k]

    # ACS: sum tracts to units; a unit's component is missing only if no tract has an estimate
    missing_tracts = collections.Counter()
    by_table = collections.defaultdict(list)
    for name, (t, vs) in ACS_COMP.items():
        by_table[t].append((name, vs))
    per_tract = {}
    for t, items in sorted(by_table.items()):
        data = bk.acs_table(t, tracts)
        if t in ("B08301", "B08013"):
            per_tract[t] = data
        for name, vs in items:
            s = collections.Counter(); seen = set()
            for g, d in data.items():
                vals = [d.get(f"{t}_{v}") for v in vs]
                if all(x is not None for x in vals):
                    s[unit_of[g]] += sum(vals); seen.add(unit_of[g])
                else:
                    missing_tracts[name] += 1
            for k in units:
                comp[k][name] = s[k] if k in seen else None  # tracts without an estimate (mostly empty tracts) count as 0
        print(f"ACS {t}: {len(data):,} tracts", flush=True)
    # commuters (workers not working from home) only in tracts with an aggregate travel time, to match its numerator
    commuters, seen = collections.Counter(), set()
    for g, d in per_tract["B08013"].items():
        w = per_tract["B08301"].get(g, {})
        if d.get("B08013_001") is not None and w.get("B08301_001") is not None and w.get("B08301_021") is not None:
            commuters[unit_of[g]] += w["B08301_001"] - w["B08301_021"]; seen.add(unit_of[g])
    for k in units:
        comp[k]["acs_commuters"] = commuters[k] if k in seen else None

    # QCEW 2024: total, government, supersectors
    for r in csv.DictReader(open(os.path.join(R, "data", "qcew_2024_units.csv"))):
        k = r["unit_id"]; c = comp[k]; e = num(r["emplvl"])
        if r["level"] == "total":
            c["qcew_estabs"] = num(r["estabs"]); c["qcew_jobs"] = e; c["qcew_wages"] = num(r["total_wages"])
            c["qcew_job_weeks"] = None if e is None else e * 52
        elif r["level"] == "ownership" and r["own_code"] == "5":
            c["_private"] = e
        elif r["level"] == "supersector" and r["own_code"] == "5":
            c[f"qcew_jobs_{r['industry_code']}"] = e
    for k in units:
        c = comp[k]; pv = c.pop("_private", None)
        c["qcew_jobs_gov"] = None if c["qcew_jobs"] is None or pv is None else c["qcew_jobs"] - pv  # total - private
        if c["qcew_jobs"] is not None:
            for s in SUPERSECTORS:
                if f"qcew_jobs_{s}" not in c:
                    c[f"qcew_jobs_{s}"] = 0.0  # no row: no private jobs in that supersector
    # BEA 2024 (combined areas: kept apart, used where a level holds all their members)
    combos = collections.defaultdict(set)
    for r in csv.DictReader(open(os.path.join(R, "data", "bea_units.csv"))):
        if r["method"].startswith("bea_combined_area"):
            combos[r["method"].split()[1]].add(r["unit_id"])
        for name, (t, l) in BEA_COMP.items():
            if r["table"] == t and r["line"] == l and r["method"] in ("published", "allocated"):
                comp[r["unit_id"]][name] = num(r["value"])
    combo_val = collections.defaultdict(dict)
    for t in sorted({t for t, _ in BEA_COMP.values()}):
        data, _, _ = ab.load(t, set(combos))
        for name, (t2, l) in BEA_COMP.items():
            if t2 == t:
                for cb in combos:
                    combo_val[cb][name] = data.get(cb, {}).get(l)
    combo_of = {m: cb for cb, ms in combos.items() for m in ms}

    names = ["pop2020", "pop2025", "land_sqmi"] + list(ACS_COMP) + ["acs_commuters", "qcew_estabs", "qcew_jobs", "qcew_wages",
             "qcew_job_weeks", "qcew_jobs_gov"] + [f"qcew_jobs_{s}" for s in SUPERSECTORS] + list(BEA_COMP)
    with open(os.path.join(HERE, "components_units.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["unit_id"] + names)
        for k in sorted(units):
            w.writerow([k] + ["" if comp[k][n] is None else round(comp[k][n], 3) for n in names])

    def summed(members):
        out = {}
        ms = set(members)
        for n in names:
            if n in BEA_COMP:
                vs, used = [], set()
                for m in members:
                    cb = combo_of.get(m)
                    if cb is None:
                        vs.append(comp[m][n])
                    elif cb not in used:
                        used.add(cb); vs.append(combo_val[cb].get(n) if combos[cb] <= ms else None)
            else:
                vs = [comp[m][n] for m in members]
            out[n] = None if any(v is None for v in vs) else sum(vs)
        return out

    def indicators(c):
        row = {}
        for iid, _, unit, kind, nu, de, sc, *_ in CATALOGUE:
            if kind == "median":
                pre = nu.rstrip("*"); bins = sorted(n for n in names if n.startswith(pre))
                vals = [c[b] for b in bins]
                v = None if any(x is None for x in vals) else median_from(vals, INC_EDGES if "inc" in pre else VAL_EDGES)
                row[iid] = "" if v is None else round(v)
            elif kind == "count":
                row[iid] = "" if c[nu] is None else round(c[nu])
            else:
                n_, d_ = c[nu], c[de]
                if n_ is None or not d_:
                    row[iid] = ""
                else:
                    v = (n_ / d_ - 1) * sc if kind == "change" else n_ / d_ * sc
                    row[iid] = round(v) if unit.startswith("$") or unit == "per sq mi" else round(v, 1 if unit == "minutes" else 2)
        return row

    # levels
    M = os.path.join(R, "metros")
    xw = list(csv.DictReader(open(os.path.join(M, "crosswalk_unit_metro.csv"))))
    D = {r["district_id"]: r for r in csv.DictReader(open(os.path.join(M, "districts.csv")))}
    S = {r["subregion_id"]: r for r in csv.DictReader(open(os.path.join(M, "subregions.csv")))}
    dmem, smem, cmem, ctitle = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list), {}
    for r in xw:
        dmem[r["district_id"]].append(r["unit_id"]); cmem[r["cbsa"]].append(r["unit_id"])
        if r["subregion_id"]:
            smem[r["subregion_id"]].append(r["unit_id"])
    for d in D.values():
        ctitle[d["cbsa"]] = d["cbsa_title"]
    iids = [c[0] for c in CATALOGUE]
    levels = {
        "units": [({"unit_id": k, "unit_type": u["unit_type"], "name": u["unit_name"], "county_fips": u["county_fips"], "state": u["state"]},
                   [k]) for k, u in sorted(units.items())],
        "districts": [({"district_id": k, "name": d["name"], "cbsa": d["cbsa"], "subregion_id": d["subregion_id"],
                        "district_view": d["district_view"], "units": d["units"], "work_inside": d["work_inside"]}, dmem[k]) for k, d in sorted(D.items())],
        "subregions": [({"subregion_id": k, "name": s["name"], "cbsa": s["cbsa"], "units": s["units"], "districts": s["districts"],
                         "work_inside": s["work_inside"]}, smem[k]) for k, s in sorted(S.items())],
        "metros": [({"cbsa": c, "name": ctitle[c], "units": len(ms)}, ms) for c, ms in sorted(cmem.items())],
    }
    blanks = {}
    for lvl, rows in levels.items():
        out = []
        for head, ms in rows:
            out.append({**head, **indicators(summed(ms))})
        with open(os.path.join(HERE, f"indicators_{lvl}.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, list(out[0])); w.writeheader(); w.writerows(out)
        blanks[lvl] = {i: sum(r[i] == "" for r in out) for i in iids}
        print(f"{lvl}: {len(out):,} rows", flush=True)
    with open(os.path.join(HERE, "indicator_catalogue.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["indicator_id", "label", "unit", "kind", "numerator", "denominator", "scale", "source", "year"])
        w.writerows(CATALOGUE)

    # checks: levels add up (counts), every unit in one district per covered area, totals
    tot = lambda lvl, i: sum(float(r[i]) for r in csv.DictReader(open(os.path.join(HERE, f"indicators_{lvl}.csv"))) if r[i] != "")
    us_pop = tot("units", "pop2025")
    cov = sum(comp[k]["pop2025"] for ms in cmem.values() for k in ms)
    bad = []
    for lvl in ("districts", "metros"):
        if abs(tot(lvl, "pop2025") - cov) > 1:
            bad.append(f"{lvl} pop2025 {tot(lvl, 'pop2025'):,.0f} vs covered units {cov:,.0f}")
    print(f"units pop2025 {us_pop:,.0f}; covered by districts {cov:,.0f}; checks failed: {bad}")
    print("blank values by level (indicators with any):", {lvl: {i: n for i, n in b.items() if n} for lvl, b in blanks.items()})
    print("ACS tracts without an estimate, by component (largest):", missing_tracts.most_common(6))
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
