"""Allocation keys for county-only data (docs/specs/allocation-keys.md): each split county's figures are shared among
its pieces in proportion to a key. Only counties with more than one piece need keys.

Keys (each summed from tracts to pieces, then expressed as a share of the county):
  workplace (LODES 8 WAC, 2024; Michigan 2021)
    jobs_total, jobs_<naics>                 all jobs, by NAICS sector (CNS01-CNS20)
    jobs_private_<naics>                     private jobs (JT02)
    jobs_state_local[_<naics>]               state and local government = all - private - federal (JT00 - JT02 - JT04);
                                             splits local government and government by sector
  government, ACS-calibrated (gov_keys; validated in validate_keys.py)
    jobs_federal                             federal civilian jobs: shared among the county's places of 10,000+ ACS
                                             workers (wholly in the county) and its rest by ACS workplace counts (B08528
                                             federal workers less B23025 armed forces, at residence), then within each by
                                             LODES federal jobs (JT04)
    jobs_state                               state government jobs: the same with ACS state workers (B08528_E007), then
                                             within each area by LODES state and local jobs (LODES has no state/local split)
    wages_<naics>, wages_private_<naics>     jobs x the piece's pay index (decision 1)
  establishments (ZIP Code Business Patterns 2023, ZIP -> tract by population share of the 2020 ZCTA-tract overlap)
    est_total, est_<naics>                   private establishments by sector (CBP has no public administration)
  residence (ACS 5-year 2020-2024, tract)
    res_* household income components, people 65+, Medicaid coverage, unemployed, armed forces, veterans,
    self-employed workers, population; housing_services (12 x gross rent + RENT_TO_VALUE x owner home value)
  combined
    gdp_real_estate = housing share x housing_services + (1 - housing share) x wages_53 (decision 2); housing share
    from BEA GDP by industry (TVA105, 2024: Housing / Real estate and rental and leasing)
Pay index (decision 1): LODES earnings bands (CE01 <= $1,250/month, CE02 $1,251-3,333, CE03 > $3,333). The mean of the
open top band is set per county so that the county's band-weighted mean equals its QCEW 2024 average monthly pay; a
piece's index is its band-weighted mean over the county's.

Writes next to this script:
  keys.csv           key_id, county_fips, piece_id, value, share
  keys_catalog.csv   key_id, basis, description, source, year
  measure_keys.csv   BEA and QCEW measures -> key_id (which key splits which figure)
  sector_groups.csv  NAICS sector -> publishing group (decision 5: about 10 groups for pieces)
  pay_index.csv      county_fips, piece_id, qcew_avg_monthly_pay, top_band_mean, piece_mean, pay_index
usage: python3 build_keys.py --cache DIR
"""
import argparse, collections, csv, gzip, io, os, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pieces"))
import build_crosswalk as bx  # noqa: E402

LODES = "https://lehd.ces.census.gov/data/lodes/LODES8/{st}/wac/{st}_wac_S000_{jt}_{yr}.csv.gz"
ACS = "https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-{t}.dat"
ACS_SHELLS = "https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/documentation/ACS20245YR_Table_Shells.txt"
ZBP = "https://www2.census.gov/programs-surveys/cbp/datasets/2023/zbp23detail.zip"
ZCTA_TRACT = "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_tract20_natl.txt"
QCEW = "https://data.bls.gov/cew/data/api/2024/a/area/{fips}.csv"
ST = {"01": "al", "02": "ak", "04": "az", "05": "ar", "06": "ca", "08": "co", "09": "ct", "10": "de", "11": "dc", "12": "fl", "13": "ga",
      "15": "hi", "16": "id", "17": "il", "18": "in", "19": "ia", "20": "ks", "21": "ky", "22": "la", "23": "me", "24": "md", "25": "ma",
      "26": "mi", "27": "mn", "28": "ms", "29": "mo", "30": "mt", "31": "ne", "32": "nv", "33": "nh", "34": "nj", "35": "nm", "36": "ny",
      "37": "nc", "38": "nd", "39": "oh", "40": "ok", "41": "or", "42": "pa", "44": "ri", "45": "sc", "46": "sd", "47": "tn", "48": "tx",
      "49": "ut", "50": "vt", "51": "va", "53": "wa", "54": "wv", "55": "wi", "56": "wy"}
LODES_YEAR = {"mi": "2021"}
CNS = ["11", "21", "22", "23", "31-33", "42", "44-45", "48-49", "51", "52", "53", "54", "55", "56", "61", "62", "71", "72", "81", "92"]
ZBP_SECTOR = {"11": "11", "21": "21", "22": "22", "23": "23", "31": "31-33", "42": "42", "44": "44-45", "48": "48-49", "51": "51",
              "52": "52", "53": "53", "54": "54", "55": "55", "56": "56", "61": "61", "62": "62", "71": "71", "72": "72", "81": "81"}
BAF = "https://www2.census.gov/geo/docs/maps-data/data/baf2020/BlockAssign_ST{ss}_{ST}.zip"
GOV_MIN_WORKERS = 10_000    # places with at least this many ACS workers (all classes) are calibration areas
BAND_MID = (625.0, 2292.0)  # midpoints of the two closed LODES earnings bands, $/month
RENT_TO_VALUE = 0.05        # annual imputed rent per dollar of owner-occupied home value (assumption; see spec)
BEA_VA = "https://apps.bea.gov/industry/Release/XLS/GDPxInd/ValueAdded.xlsx"  # GDP by industry, table TVA105
HOUSING_YEAR = "2024"


def housing_share():
    """Housing's share of real estate and rental and leasing value added (BEA TVA105, HOUSING_YEAR): the line county GDP
    reports as one sector (CAGDP2 line 56)."""
    import openpyxl
    rows = list(openpyxl.load_workbook(bx.fetch(BEA_VA), read_only=True, data_only=True)["TVA105-A"].iter_rows(values_only=True))
    head = [r for r in rows if r and r[0] == "Line"][0]; col = list(head).index(HOUSING_YEAR)
    val = {r[1].strip(): r[col] for r in rows if r and isinstance(r[1], str)}
    return val["Housing"] / val["Real estate and rental and leasing"]
# ACS variables (checked against the table shells at run time): key -> list of (variable, expected label start)
ACS_VARS = {
    "res_wage_income": [("B19062_001", "Aggregate wage or salary income")],
    "res_selfemp_income": [("B19063_001", "Aggregate self-employment income")],
    "res_dir_income": [("B19064_001", "Aggregate interest, dividends, or net rental income")],
    "res_social_security_income": [("B19065_001", "Aggregate Social Security income")],
    "res_ssi_pa_income": [("B19066_001", "Aggregate Supplemental Security Income"), ("B19067_001", "Aggregate public assistance income")],
    "res_pop65": [(f"B01001_{i:03d}", v) for i, v in zip(list(range(20, 26)) + list(range(44, 50)),
                  ["65 and 66", "67 to 69", "70 to 74", "75 to 79", "80 to 84", "85 years"] * 2)],
    "res_medicaid": [(f"C27007_{i:03d}", "With Medicaid") for i in (4, 7, 10, 14, 17, 20)],
    "res_unemployed": [("B23025_005", "Unemployed")],
    "res_armed_forces": [("B23025_006", "Armed Forces")],
    "res_veterans": [("B21001_002", "Veteran")],
    "res_selfemployed_workers": [("B24080_010", "Self-employed in own not incorporated"), ("B24080_020", "Self-employed in own not incorporated")],
    "res_population": [("B01003_001", "Total")],
    "res_gross_rent": [("B25065_001", "Aggregate gross rent")],
    "res_home_value": [("B25079_001", "Aggregate value")],
}
# Aggregates are withheld for many tracts (the row is missing or carries an annotation code). A missing aggregate is
# imputed as the tract's base count x the ratio of aggregate to base over the reported tracts of the same piece.
IMPUTE_BASE = {"B19062_001": "B11001_001", "B19063_001": "B11001_001", "B19064_001": "B11001_001", "B19065_001": "B11001_001",
               "B19066_001": "B19056_002", "B19067_001": "B19057_002", "B25079_001": "B25003_002", "B25065_001": "B25003_003"}
BASE_LABELS = {"B11001_001": "Total", "B25003_002": "Owner occupied", "B25003_003": "Renter occupied",
               "B19056_002": "With Supplemental Security Income", "B19057_002": "With public assistance income", "B25077_001": "Median value"}
# home value: where the aggregate is withheld but the median is published, median x owner units, scaled per piece by
# (aggregate / median x owners) over tracts that report both; only then the owner-unit ratio


def acs_table(table, tracts):
    """Estimates for the given tracts from one ACS 5-year table-based summary file: {tract: {var: value}}."""
    out = {}
    with open(bx.fetch(ACS.format(t=table.lower()), f"acsdt5y2024-{table.lower()}.dat"), encoding="latin-1") as fh:
        head = fh.readline().rstrip("\n").split("|")
        for line in fh:
            if not line.startswith("1400000US"):
                continue
            f = line.rstrip("\n").split("|"); g = bx.tract_2020(f[0][9:])  # Connecticut: 2022 codes -> 2020
            if g in tracts:
                out[g] = {h.replace("_E", "_"): float(v) if v not in ("", "null") and not v.startswith("*") and float(v) >= 0 else None
                          for h, v in zip(head[1:], f[1:]) if "_E" in h}  # None: no estimate (negative annotation codes)
    return out


def lodes_keys(area_of):
    """LODES WAC sums by area: jobs (all, private, federal, state and local) by sector, and earnings bands."""
    keys = collections.defaultdict(collections.Counter)
    bands = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
    for s2 in sorted({g[:2] for g in area_of}):
        st = ST[s2]; yr = LODES_YEAR.get(st, "2024")
        for jt in ("JT00", "JT02", "JT04"):
            with gzip.open(bx.fetch(LODES.format(st=st, jt=jt, yr=yr)), "rt") as fh:
                r = csv.reader(fh); h = next(r); ix = {k: i for i, k in enumerate(h)}
                for row in r:
                    p = area_of.get(row[0][:11])
                    if not p:
                        continue
                    tot = int(row[ix["C000"]]); pre = {"JT00": "jobs_", "JT02": "jobs_private_", "JT04": "jobs_federal_"}[jt]
                    keys[pre + "total"][p] += tot
                    for i, s in enumerate(CNS, 1):
                        keys[f"{pre}{s}"][p] += int(row[ix[f"CNS{i:02d}"]])
                    if jt == "JT00":
                        for k in range(3):
                            bands[p][k] += int(row[ix[f"CE0{k + 1}"]])
    for p in list(keys["jobs_total"]):
        keys["jobs_federal"][p] = keys["jobs_federal_total"][p]  # LODES federal; build_keys replaces it with gov_keys
        keys["jobs_state_local"][p] = max(0, keys["jobs_total"][p] - keys["jobs_private_total"][p] - keys["jobs_federal"][p])
        for s in CNS:
            keys[f"jobs_state_local_{s}"][p] = max(0, keys[f"jobs_{s}"][p] - keys[f"jobs_private_{s}"][p] - keys[f"jobs_federal_{s}"][p])
    for s in CNS + ["total"]:
        keys.pop(f"jobs_federal_{s}", None)
    return keys, bands


def acs_geo(t, prefixes=("1600000US", "0500000US")):
    """ACS 5-year estimates of table t for places and counties: {geoid: {variable: value}} (missing or annotated -> 0)."""
    out = {}
    with open(bx.fetch(ACS.format(t=t), f"acsdt5y2024-{t}.dat"), encoding="latin-1") as fh:
        head = fh.readline().rstrip("\n").split("|")
        for line in fh:
            if line.startswith(prefixes):
                f = line.rstrip("\n").split("|")
                out[f[0][9:]] = {h: float(v) if v not in ("", "null") and not v.startswith("*") and float(v) >= 0 else 0.0
                                 for h, v in zip(head[1:], f[1:]) if "_E" in h}
    return out


def gov_keys(groups, unit_of_block, min_workers=GOV_MIN_WORKERS):
    """ACS-calibrated government keys. groups: {group: set of counties} (a split county, or a test metro);
    unit_of_block(block) -> unit (piece or county) or None. Within each group, federal civilian and state government
    jobs are shared among areas (places of min_workers+ ACS workers lying wholly in the group, and the rest of the group)
    by ACS workplace counts, then within each area among units by LODES (federal: JT04; state: JT00 - JT02 - JT04; an area
    with none of those jobs in LODES: all jobs). Values are in LODES jobs: federal sums to the group's LODES federal
    jobs, state to its LODES state and local jobs x the ACS state share of state and local. A group without ACS counts
    keeps the LODES keys. Returns {"jobs_federal": {unit: v}, "jobs_state": {unit: v}}."""
    b28, b25 = acs_geo("b08528"), acs_geo("b23025")

    def acs(g):
        c = b28.get(g)
        if c is None:
            return None
        return {"all": sum(c[f"B08528_E{k:03d}"] for k in (2, 5, 6, 7, 8)), "sl": c["B08528_E006"] + c["B08528_E007"],
                "fed": max(0.0, c["B08528_E008"] - b25.get(g, {}).get("B23025_E006", 0.0)), "state": c["B08528_E007"]}
    group_of = {c: g for g, cs in groups.items() for c in cs}
    L = collections.defaultdict(collections.Counter)  # (group, calibration place or None, unit) -> all, fed, sl
    for ss in sorted({c[:2] for c in group_of}):
        st = ST[ss]; up = st.upper()
        place_of, pc = {}, collections.defaultdict(set)
        with zipfile.ZipFile(bx.fetch(BAF.format(ss=ss, ST=up))).open(f"BlockAssign_ST{ss}_{up}_INCPLACE_CDP.txt") as fh:
            r = csv.reader(io.TextIOWrapper(fh, encoding="latin-1"), delimiter="|"); next(r)
            for b, p in r:
                if p:
                    place_of[b] = ss + p; pc[ss + p].add(bx.cty(b))
        gs = {p: {group_of.get(c) for c in cs} for p, cs in pc.items()}
        ok = {p for p, g in gs.items() if len(g) == 1 and None not in g and (acs(p) or {}).get("all", 0) >= min_workers}
        yr = LODES_YEAR.get(st, "2024")
        for jt in ("JT00", "JT02", "JT04"):
            with gzip.open(bx.fetch(LODES.format(st=st, jt=jt, yr=yr)), "rt") as fh:
                r = csv.reader(fh); h = next(r); ci = h.index("C000")
                for row in r:
                    b = row[0]; g = group_of.get(bx.cty(b))
                    u = unit_of_block(b) if g is not None else None
                    if u is None:
                        continue
                    p = place_of.get(b); k = (g, p if p in ok else None, u); n = int(row[ci])
                    if jt == "JT00":
                        L[k]["all"] += n; L[k]["sl"] += n
                    elif jt == "JT02":
                        L[k]["sl"] -= n
                    else:
                        L[k]["fed"] += n; L[k]["sl"] -= n
    out = {"jobs_federal": collections.Counter(), "jobs_state": collections.Counter()}
    by_group = collections.defaultdict(dict)
    for k, v in L.items():
        by_group[k[0]][k] = {x: max(0, y) for x, y in v.items()}
    for g, cells in by_group.items():
        LT = collections.Counter()
        for v in cells.values():
            LT.update(v)
        gt = collections.Counter()
        for c in groups[g]:
            gt.update(acs(c) or {})
        places = sorted({k[1] for k in cells if k[1]})
        A = {p: acs(p) for p in places}
        A[None] = {x: max(0.0, gt[x] - sum(A[p][x] for p in places)) for x in ("fed", "state")}
        for kid, cl, lk in (("jobs_federal", "fed", "fed"), ("jobs_state", "state", "sl")):
            total = LT[lk] * (gt["state"] / gt["sl"] if cl == "state" and gt["sl"] else 1)
            atot = sum(a[cl] for a in A.values())
            if not atot:  # no ACS counts: LODES as is
                for k, v in cells.items():
                    out[kid][k[2]] += v[lk] * (total / LT[lk] if LT[lk] else 0)
                continue
            for p, a in A.items():
                sub = collections.Counter()
                for k, v in cells.items():
                    if k[1] == p:
                        sub[k[2]] += v[lk]
                if not sum(sub.values()):
                    for k, v in cells.items():
                        if k[1] == p:
                            sub[k[2]] += v["all"]
                s = sum(sub.values())
                for u, x in sub.items():
                    out[kid][u] += total * a[cl] / atot * x / s if s else 0
    return out


def pay_index(bands, county_of_area, pay):
    """Pay index per area: band-weighted mean pay over its county's, with the open top band's mean set so that the
    county's band-weighted mean equals its QCEW average monthly pay (pay: county -> $/month)."""
    index, rows = {}, []
    for c in sorted(set(county_of_area.values())):
        ps = [p for p in bands if county_of_area[p] == c]
        N = [sum(bands[p][k] for p in ps) for k in range(3)]
        m3 = (pay[c] * sum(N) - BAND_MID[0] * N[0] - BAND_MID[1] * N[1]) / N[2]
        mean = lambda b: (BAND_MID[0] * b[0] + BAND_MID[1] * b[1] + m3 * b[2]) / sum(b)
        cm = mean(N)
        for p in sorted(ps):
            index[p] = mean(bands[p]) / cm
            rows.append([c, p, round(pay[c], 1), round(m3, 1), round(mean(bands[p]), 1), round(index[p], 4)])
    return index, rows


def wage_keys(keys, index):
    """Wage-weighted jobs: jobs x pay index, all and private, by sector."""
    out = collections.defaultdict(collections.Counter)
    for s in ["total"] + CNS:
        for p, v in keys["jobs_total" if s == "total" else f"jobs_{s}"].items():
            out[f"wages_{s}"][p] = v * index[p]
            out[f"wages_private_{s}"][p] = keys["jobs_private_total" if s == "total" else f"jobs_private_{s}"][p] * index[p]
    return out


_TPOP = None


def tract_pop():
    """2020 population of every tract in the 50 states and DC (TIGERweb, cached by the units build)."""
    global _TPOP
    if _TPOP is None:
        _TPOP = {}
        for st in sorted({v for v in [f"{i:02d}" for i in range(1, 57)]} - {"03", "07", "14", "43", "52"}):
            for f in bx.arcgis(bx.TG + "6", f"STATE='{st}'", "GEOID,POP100,INTPTLAT,INTPTLON", geometry=False):
                _TPOP[f["properties"]["GEOID"]] = f["properties"]["POP100"]
    return _TPOP


def zbp_keys(area_of):
    """Private establishments by sector per area: ZIP Code Business Patterns, each ZIP spread over its ZCTA's tracts by
    population (tract population x the share of the tract's land inside the ZCTA), using every tract in the country so a
    ZIP straddling a county line is split correctly."""
    tpop = tract_pop()
    zt, tland = collections.defaultdict(list), {}
    with open(bx.fetch(ZCTA_TRACT), encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh, delimiter="|"):
            z, g = row["GEOID_ZCTA5_20"], row["GEOID_TRACT_20"]
            if z and g:
                tland[g] = float(row["AREALAND_TRACT_20"] or 0); zt[z].append((g, float(row["AREALAND_PART"] or 0)))
    weight = {}
    for z, parts in zt.items():
        w = [(g, tpop.get(g, 0) * (part / tland[g] if tland[g] else 0)) for g, part in parts]
        tot = sum(x for _, x in w)
        weight[z] = [(g, x / tot) for g, x in w if x > 0] if tot else []
    keys = collections.defaultdict(collections.Counter); unmatched = 0.0
    zz = zipfile.ZipFile(bx.fetch(ZBP))
    name = [n for n in zz.namelist() if n.endswith(".txt") or n.endswith(".csv")][0]
    with zz.open(name) as fh:
        for row in csv.DictReader(io.TextIOWrapper(fh, encoding="latin-1")):
            code = row["naics"].strip()
            s = "total" if code == "------" else ZBP_SECTOR.get(code[:2]) if code.endswith("----") else None
            if not s:
                continue
            z = row["zip"].strip().zfill(5); est = float(row["est"] or 0)
            if not weight.get(z):
                unmatched += est if s == "total" else 0; continue
            for g, w in weight[z]:
                p = area_of.get(g)
                if p:
                    keys[f"est_{s}"][p] += est * w
    return keys, unmatched


def acs_keys(area_of):
    """Residence keys per area from ACS 5-year tract tables, with withheld aggregates imputed within each area (see
    IMPUTE_BASE). Returns (keys, share imputed per aggregate, share of home value from calibrated medians)."""
    tracts = set(area_of); piece_of = area_of
    keys = collections.defaultdict(collections.Counter)
    shells = {}
    for line in open(bx.fetch(ACS_SHELLS), encoding="latin-1"):
        f = line.split("|")
        if len(f) > 4:
            shells[f[3]] = f[4]
    for key, vs in list(ACS_VARS.items()) + [("base", list(BASE_LABELS.items()))]:
        for v, lab in vs:
            if not shells.get(v, "").startswith(lab):
                raise SystemExit(f"ACS {v}: expected '{lab}', shells say '{shells.get(v)}'")
    by_table = collections.defaultdict(list)
    for key, vs in ACS_VARS.items():
        for v, _ in vs:
            by_table[v.split("_")[0]].append((key, v))
    for v in BASE_LABELS:
        by_table[v.split("_")[0]].append(("base:" + v, v))
    vals = collections.defaultdict(dict)  # var -> tract -> value or None
    for t, kv in sorted(by_table.items()):
        data = acs_table(t, tracts)
        for g in tracts:
            for key, v in kv:
                vals[v][g] = data.get(g, {}).get(v)
    imputed = {}
    med = {}
    k = collections.defaultdict(lambda: [0.0, 0.0])
    for g in tracts:
        mv, ow, ag = vals["B25077_001"][g], vals["B25003_002"][g], vals["B25079_001"][g]
        if mv is not None and ow:
            med[g] = mv * ow
            if ag is not None:
                k[piece_of[g]][0] += ag; k[piece_of[g]][1] += med[g]
    by_median = 0.0
    for g in tracts:
        if vals["B25079_001"][g] is None and g in med:
            r = k[piece_of[g]]
            vals["B25079_001"][g] = med[g] * (r[0] / r[1] if r[1] else 1.0); by_median += vals["B25079_001"][g]
    for v, b in IMPUTE_BASE.items():
        rep = collections.defaultdict(lambda: [0.0, 0.0])
        for g in tracts:
            if vals[v][g] is not None and vals[b][g]:
                rep[piece_of[g]][0] += vals[v][g]; rep[piece_of[g]][1] += vals[b][g]
        n = tot = 0.0
        for g in tracts:
            if vals[v][g] is None:
                r = rep[piece_of[g]]
                vals[v][g] = (vals[b][g] or 0) * (r[0] / r[1] if r[1] else 0); n += vals[v][g]
            tot += vals[v][g]
        imputed[v] = (n + (by_median if v == "B25079_001" else 0)) / tot if tot else 0
    for t, kv in sorted(by_table.items()):
        for key, v in kv:
            if not key.startswith("base:"):
                for g in tracts:
                    keys[key][piece_of[g]] += vals[v][g] or 0.0
    for p in set(piece_of.values()):
        keys["res_wage_selfemp_income"][p] = keys["res_wage_income"][p] + keys["res_selfemp_income"][p]
        keys["housing_services"][p] = 12 * keys["res_gross_rent"][p] + RENT_TO_VALUE * keys["res_home_value"][p]
    hv = sum(vals["B25079_001"][g] or 0 for g in tracts)
    return keys, imputed, by_median / hv if hv else 0


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True)
    a = ap.parse_args(); bx.CACHE = a.cache; bx.fix_hash_seed()
    units = os.path.join(HERE, "..", "units")
    piece_of, release = {}, None
    for r in csv.DictReader(open(os.path.join(units, "crosswalk_tract_unit.csv"))):
        if r["unit_type"] == "piece":
            piece_of[r["tract_geoid"]] = r["unit_id"]
    for r in csv.DictReader(open(os.path.join(units, "atlas_units.csv"))):
        release = r["pieces_release"]
    npieces = collections.Counter(p[:5] for p in set(piece_of.values()))
    split = {c for c, n in npieces.items() if n > 1}
    piece_of = {g: p for g, p in piece_of.items() if p[:5] in split}  # the piece ID carries the current county
    tracts = set(piece_of)
    keys = collections.defaultdict(collections.Counter)  # key -> piece -> value
    catalog = []

    # workplace (LODES), pay index (QCEW-calibrated) and establishments (ZBP): shared with validate_keys.py
    lk, bands = lodes_keys(piece_of)
    for k, d in lk.items():
        keys[k].update(d)
    pay = {}
    for c in sorted(split):
        q = [r for r in csv.DictReader(io.StringIO(open(bx.fetch(QCEW.format(fips=c), f"qcew_2024_a_{c}.csv")).read()))
             if r["own_code"] == "0" and r["industry_code"] == "10"]
        pay[c] = float(q[0]["avg_annual_pay"]) / 12
    index, pay_rows = pay_index(bands, {p: p[:5] for p in bands}, pay)
    for k, d in wage_keys(keys, index).items():
        keys[k].update(d)
    for k, d in gov_keys({c: {c} for c in split}, lambda b: piece_of.get(b[:11])).items():
        keys[k] = collections.Counter(d)
    ek, unmatched = zbp_keys(piece_of)
    for k, d in ek.items():
        keys[k].update(d)
    catalog += [("jobs_total", "work", "All jobs at the workplace", "LODES 8 WAC JT00 C000", "2024 (MI 2021)")]
    catalog += [(f"jobs_{s}", "work", f"Jobs in NAICS {s}", f"LODES 8 WAC JT00 CNS{i:02d}", "2024 (MI 2021)") for i, s in enumerate(CNS, 1)]
    catalog += [("jobs_private_total", "work", "Private jobs", "LODES 8 WAC JT02 C000", "2024 (MI 2021)")]
    catalog += [(f"jobs_private_{s}", "work", f"Private jobs in NAICS {s}", f"LODES 8 WAC JT02 CNS{i:02d}", "2024 (MI 2021)") for i, s in enumerate(CNS, 1)]
    catalog += [("jobs_federal", "work", "Federal civilian jobs: places of 10,000+ ACS workers and the rest of the county by ACS workplace counts (federal workers less armed forces), then by LODES federal jobs", "ACS 2020-2024 B08528, B23025 (places, counties) + LODES 8 WAC JT04", "2020-2024 / 2024 (MI 2021)"),
                ("jobs_state", "work", "State government jobs: places of 10,000+ ACS workers and the rest of the county by ACS state workers, then by LODES state and local jobs", "ACS 2020-2024 B08528 (places, counties) + LODES 8 WAC JT00, JT02, JT04", "2020-2024 / 2024 (MI 2021)"),
                ("jobs_state_local", "work", "State and local government jobs (all - private - federal); the key for local government", "LODES 8 WAC JT00, JT02, JT04", "2024 (MI 2021)")]
    catalog += [(f"jobs_state_local_{s}", "work", f"State and local government jobs in NAICS {s}", "LODES 8 WAC JT00, JT02, JT04", "2024 (MI 2021)") for s in CNS]
    catalog += [(f"wages_{s}", "work", f"Wage-weighted jobs, {'all sectors' if s == 'total' else 'NAICS ' + s} (jobs x pay index)", "LODES 8 WAC + QCEW 2024 county average pay", "2024 (MI 2021)") for s in ["total"] + CNS]
    catalog += [(f"wages_private_{s}", "work", f"Wage-weighted private jobs, {'all sectors' if s == 'total' else 'NAICS ' + s}", "LODES 8 WAC JT02 + QCEW 2024", "2024 (MI 2021)") for s in ["total"] + CNS]
    catalog += [("est_total", "work", "Private establishments", "ZIP Code Business Patterns 2023 (ZIP -> tract)", "2023")]
    catalog += [(f"est_{s}", "work", f"Private establishments in NAICS {s}", "ZIP Code Business Patterns 2023 (ZIP -> tract)", "2023") for s in ZBP_SECTOR.values()]

    # residence: ACS 5-year 2020-2024 (shared with validate_keys.py)
    rk, imputed, by_median = acs_keys(piece_of)
    for k_, d in rk.items():
        keys[k_].update(d)
    print("share of each aggregate imputed:", {v: round(x, 3) for v, x in imputed.items()}, "home value from medians:", round(by_median, 3))
    with open(os.path.join(HERE, "acs_imputed_share.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["acs_variable", "base", "share_of_piece_county_total_imputed"])
        w.writerows([(v, IMPUTE_BASE[v], round(x, 4)) for v, x in imputed.items()])
    acs_desc = {"res_wage_income": "Aggregate household wage or salary income (B19062)", "res_selfemp_income": "Aggregate self-employment income (B19063)",
                "res_wage_selfemp_income": "Wage or salary + self-employment income (B19062 + B19063)", "res_dir_income": "Aggregate interest, dividends or net rental income (B19064)",
                "res_social_security_income": "Aggregate Social Security income (B19065)", "res_ssi_pa_income": "Aggregate SSI + public assistance income (B19066 + B19067)",
                "res_pop65": "People 65 and over (B01001)", "res_medicaid": "People with Medicaid or means-tested coverage (C27007)",
                "res_unemployed": "Unemployed people (B23025)", "res_armed_forces": "People in the Armed Forces, at residence (B23025)",
                "res_veterans": "Civilian veterans (B21001)", "res_selfemployed_workers": "Self-employed workers, not incorporated (B24080)",
                "res_population": "Population (B01003)", "res_gross_rent": "Aggregate monthly gross rent (B25065)", "res_home_value": "Aggregate owner-occupied home value (B25079)",
                "housing_services": f"Housing services: 12 x gross rent + {RENT_TO_VALUE} x home value (B25065, B25079)"}
    catalog += [(k, "residence", d, "ACS 5-year 2020-2024, tracts", "2020-2024") for k, d in acs_desc.items()]

    # combined: real estate GDP (decision 2), from shares
    def shares(key):
        out = {}
        for c in split:
            ps = [p for p in set(piece_of.values()) if p[:5] == c]
            tot = sum(keys[key][p] for p in ps)
            for p in ps:
                out[p] = keys[key][p] / tot if tot else None
        return out
    HOUSING_SHARE = housing_share()
    sh_h, sh_b = shares("housing_services"), shares("wages_53")
    for p in sh_h:
        keys["gdp_real_estate"][p] = HOUSING_SHARE * sh_h[p] + (1 - HOUSING_SHARE) * (sh_b[p] or 0)
    catalog += [("gdp_real_estate", "mixed", f"{HOUSING_SHARE:.3f} x housing_services share + {1 - HOUSING_SHARE:.3f} x wages_53 share (housing share: BEA TVA105 {HOUSING_YEAR})", "ACS + LODES + BEA", "2020-2024 / 2024")]

    # write keys with shares; a key with a zero county total has no share (the figure falls back, see measure_keys)
    rows, empty = [], []
    for key in sorted(keys):
        sh = shares(key)
        for p in sorted(sh):
            if sh[p] is None:
                empty.append((key, p[:5]))
            rows.append({"key_id": key, "county_fips": p[:5], "piece_id": p, "value": round(keys[key][p], 4),
                         "share": "" if sh[p] is None else round(sh[p], 6)})
    with open(os.path.join(HERE, "keys.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0])); w.writeheader(); w.writerows(rows)
    with open(os.path.join(HERE, "keys_catalog.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["key_id", "basis", "description", "source", "year"])
        w.writerows(sorted(set(catalog)))
    with open(os.path.join(HERE, "pay_index.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["county_fips", "piece_id", "qcew_avg_monthly_pay", "top_band_mean", "piece_mean", "pay_index"]); w.writerows(pay_rows)
    write_maps()
    # checks: shares sum to 1 per county and key; no negative values
    bad = []
    sums = collections.defaultdict(float)
    for r in rows:
        if r["share"] != "":
            sums[(r["key_id"], r["county_fips"])] += r["share"]
            if r["share"] < 0:
                bad.append(r)
    off = [(k, round(v, 6)) for k, v in sums.items() if abs(v - 1) > 1e-4]
    if bad or off:
        raise SystemExit(f"key check failed: {len(bad)} negative shares, {len(off)} county sums off 1, e.g. {off[:3]}")
    keyset = sorted({r['key_id'] for r in rows})
    print(f"keys {len(keyset)} for {len(split)} counties, {len(set(piece_of.values()))} pieces (release {release}); "
          f"zero-total keys {len(set(empty))} county-key pairs; ZBP establishments in unmatched ZIPs (US) {unmatched:,.0f}")


def write_maps():
    """Which key splits which published figure, and the publishing sector groups."""
    groups = [("11", "Natural resources and mining"), ("21", "Natural resources and mining"), ("23", "Construction"),
              ("31-33", "Manufacturing"), ("22", "Trade, transportation and utilities"), ("42", "Trade, transportation and utilities"),
              ("44-45", "Trade, transportation and utilities"), ("48-49", "Trade, transportation and utilities"), ("51", "Information"),
              ("52", "Financial activities"), ("53", "Financial activities"), ("54", "Professional and business services"),
              ("55", "Professional and business services"), ("56", "Professional and business services"),
              ("61", "Education and health services"), ("62", "Education and health services"), ("71", "Leisure and hospitality"),
              ("72", "Leisure and hospitality"), ("81", "Other services"), ("92", "Public administration")]
    with open(os.path.join(HERE, "sector_groups.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["naics_sector", "group"]); w.writerows(groups)
    m = [
        ("QCEW", "Employment, private, NAICS sector s", "jobs_private_<s>", "jobs_<s>"),
        ("QCEW", "Employment, federal government (any sector)", "jobs_federal", "jobs_total"),
        ("QCEW", "Employment, state government (any sector)", "jobs_state", "jobs_state_local"),
        ("QCEW", "Employment, local government (any sector)", "jobs_state_local", "jobs_total"),
        ("QCEW", "Employment, state or local government, NAICS sector s", "jobs_state_local_<s>", "jobs_state_local"),
        ("QCEW", "Total wages and average weekly wage, private, sector s", "wages_private_<s>", "wages_<s>"),
        ("QCEW", "Total wages, government (federal, state, local)", "jobs_federal / jobs_state / jobs_state_local (x pay index not applied)", "jobs_total"),
        ("QCEW", "Establishments, private, sector s", "est_<s>", "est_total"),
        ("QCEW", "Establishments, government (federal, state, local)", "jobs_federal / jobs_state / jobs_state_local", "jobs_total"),
        ("BEA CAEMP25N", "Employment by private industry (includes proprietors)", "jobs_private_<s>", "jobs_private_total"),
        ("BEA CAEMP25N", "Proprietors employment (nonfarm and farm)", "res_selfemployed_workers", "res_population"),
        ("BEA CAINC5N / CAINC6N", "Earnings by private industry", "wages_private_<s>", "wages_private_total"),
        ("BEA CAINC4", "Earnings by place of work, wages and salaries, supplements, contributions for social insurance", "(sum of industry earnings) / wages_total", "wages_total"),
        ("BEA CAINC5N", "Proprietors' income", "res_selfemp_income", "res_selfemployed_workers"),
        ("BEA CAINC5N", "Government earnings and employment: federal civilian / military / state / local", "jobs_federal / res_armed_forces / jobs_state / jobs_state_local", "jobs_total"),
        ("BEA CAGDP2 / CAGDP9", "GDP by industry (current, real), private sectors except real estate", "wages_private_<s>", "wages_private_total"),
        ("BEA CAGDP2 / CAGDP9", "GDP, real estate (NAICS 53 real estate part)", "gdp_real_estate", "wages_53"),
        ("BEA CAGDP2 / CAGDP9", "GDP, government (one line): split by the county's federal civilian / military / state / local earnings (CAINC5N), each by its key", "jobs_federal / res_armed_forces / jobs_state / jobs_state_local", "jobs_total"),
        ("BEA CAINC4", "Net earnings by place of residence", "res_wage_selfemp_income", "res_population"),
        ("BEA CAINC4", "Dividends, interest and rent", "res_dir_income", "res_population"),
        ("BEA CAINC35", "Social Security benefits", "res_social_security_income", "res_pop65"),
        ("BEA CAINC35", "Medicare benefits", "res_pop65", "res_population"),
        ("BEA CAINC35", "Medicaid", "res_medicaid", "res_population"),
        ("BEA CAINC35", "Income maintenance benefits (SSI, SNAP, family assistance, other)", "res_ssi_pa_income", "res_population"),
        ("BEA CAINC35", "Unemployment insurance compensation", "res_unemployed", "res_population"),
        ("BEA CAINC35", "Veterans' benefits", "res_veterans", "res_population"),
        ("BEA CAINC35", "Other retirement and disability benefits (excl. Social Security)", "res_pop65", "res_population"),
        ("BEA CAINC35", "Military medical insurance benefits", "res_veterans", "res_population"),
        ("BEA CAINC35", "EITC, SNAP, other income maintenance", "res_ssi_pa_income", "res_population"),
        ("BEA CAINC35", "Education and training, other government, nonprofit, business transfers, refundable tax credits", "res_population", ""),
        ("BEA CAINC4", "Personal current transfer receipts (latest year): county's CAINC35 mix (latest year) x each component's key", "(composite)", "res_population"),
        ("BEA CAINC1 / CAINC4", "Personal income: sum of the allocated components above", "(components)", ""),
        ("BEA CAINC1", "Population; per capita personal income = allocated income / unit population", "atlas units population", ""),
    ]
    with open(os.path.join(HERE, "measure_keys.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["dataset", "measure", "key", "fallback_key_if_county_total_is_zero"]); w.writerows(m)


if __name__ == "__main__":
    main()
