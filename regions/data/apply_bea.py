"""BEA county data for every atlas unit (docs/specs/allocation-keys.md).

Tables (latest year BEA publishes for counties):
  CAGDP2 (GDP, current $) and CAGDP9 (real GDP, chained 2017 $), 2024
  CAINC5N (earnings by industry, place of work), 2024
  CAINC4 (personal income and its components, place of residence), 2024
  CAINC35 (transfer receipts by type), 2022
  CAEMP25N (employment by industry, including proprietors), 2022
County units take BEA's published figures. In the split counties each line is shared among the pieces by its key
(regions/keys): industries by wage-weighted private jobs (real estate by gdp_real_estate), government by federal,
military and state/local keys (GDP's single government line is first split by the county's CAINC5N government
earnings), residence components by ACS keys, 2024 transfers by the county's 2022 CAINC35 mix. A withheld line ((D))
gets the residual of its parent, split at the county by comparable proxies, then by its own key; no piece value is
published for a line BEA withholds at the county. Every published county line's piece values are scaled to it.
BEA areas that combine counties (Virginia independent cities, Maui + Kalawao) are kept as one figure; their county units
are marked bea_combined_area. Fairfax County, a split county, is combined by BEA with Fairfax City and Falls Church
(51919): that area is shared among the two Fairfax pieces and the two cities (workplace keys from LODES; residence keys
from population x the Fairfax average).
BEA's regional accounts do not cover Puerto Rico: its 78 municipio units get no BEA rows.

Writes next to this script:
  bea_units.csv          unit_id, unit_type, county_fips, table, line, description, year, value, method
                         (totals, components and 11 industry groups for every unit)
  bea_pieces_detail.csv  internal: piece values for every allocated line, including industry detail
usage: python3 apply_bea.py --cache DIR
"""
import argparse, collections, csv, io, os, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pieces"))
sys.path.insert(0, os.path.join(HERE, "..", "keys"))
import build_crosswalk as bx  # noqa: E402
import build_keys as bk  # noqa: E402

ZIPS = {"CAGDP2": ("CAGDP2__ALL_AREAS_2001_2024.csv", "2024"), "CAGDP9": ("CAGDP9__ALL_AREAS_2001_2024.csv", "2024"),
        "CAINC5N": ("CAINC5N__ALL_AREAS_2001_2024.csv", "2024"), "CAINC4": ("CAINC4__ALL_AREAS_1969_2024.csv", "2024"),
        "CAINC35": ("CAINC35__ALL_AREAS_1969_2022.csv", "2022"), "CAEMP25N": ("CAEMP25N__ALL_AREAS_2001_2022.csv", "2022")}
URL = "https://apps.bea.gov/regional/zip/{t}.zip"
GDP_SECTORS = {"3": "11", "6": "21", "10": "22", "11": "23", "12": "31-33", "34": "42", "35": "44-45", "36": "48-49", "45": "51",
               "51": "52", "56": "53", "60": "54", "64": "55", "65": "56", "69": "61", "70": "62", "76": "71", "79": "72", "82": "81"}
EARN_SECTORS = {"100": "11", "200": "21", "300": "22", "400": "23", "500": "31-33", "600": "42", "700": "44-45", "800": "48-49",
                "900": "51", "1000": "52", "1100": "53", "1200": "54", "1300": "55", "1400": "56", "1500": "61", "1600": "62",
                "1700": "71", "1800": "72", "1900": "81"}
NO_BEA = {"72"}  # BEA's regional accounts do not cover Puerto Rico: its municipios get no BEA rows
GOV_EARN = {"2001": "jobs_federal", "2002": "res_armed_forces", "2011": "jobs_state", "2012": "jobs_state_local"}
TRANSFER_LEAVES = {"2110": "res_social_security_income", "2120": "res_pop65", "2210": "res_pop65", "2220": "res_medicaid",
                   "2230": "res_veterans", "2310": "res_ssi_pa_income", "2320": "res_ssi_pa_income", "2330": "res_ssi_pa_income",
                   "2340": "res_ssi_pa_income", "2400": "res_unemployed", "2500": "res_veterans", "2600": "res_population",
                   "2700": "res_population", "3000": "res_population", "4000": "res_population"}
TRANSFER_PARENTS = {"2100": ["2110", "2120"], "2200": ["2210", "2220", "2230"], "2300": ["2310", "2320", "2330", "2340"],
                    "2000": ["2100", "2200", "2300", "2400", "2500", "2600", "2700"], "1000": ["2000", "3000", "4000"]}


def num(v):
    v = v.strip()
    try:
        return float(v)
    except ValueError:
        return None  # (D) withheld, (NA), (NM), (L) and similar


def load(table, areas):
    name, year = ZIPS[table]
    z = zipfile.ZipFile(bx.fetch(URL.format(t=table)))
    out, desc = collections.defaultdict(dict), {}
    with z.open(name) as fh:
        r = csv.reader(io.TextIOWrapper(fh, encoding="latin-1")); h = next(r); col = h.index(year)
        for row in r:
            if len(row) <= col:
                continue
            f = row[0].strip().strip('"').strip()
            if f in areas:
                out[f][row[4].strip()] = num(row[col]); desc[row[4].strip()] = (row[6].strip(), row[7].strip())
    return out, desc, year


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True)
    a = ap.parse_args(); bx.CACHE = a.cache; bx.fix_hash_seed()
    units = list(csv.DictReader(open(os.path.join(HERE, "..", "units", "atlas_units.csv"))))
    no_bea = sorted({u["county_fips"] for u in units if u["state_fips"] in NO_BEA})
    units = [u for u in units if u["state_fips"] not in NO_BEA]
    cty = {u["county_fips"] for u in units}
    pieces_of = collections.defaultdict(list)
    upop = {u["unit_id"]: int(u["pop2020"]) for u in units}
    upop25 = {u["unit_id"]: int(u["pop2025_est"]) for u in units}  # BEA population shared like the 2025 estimate
    for u in units:
        if u["unit_type"] == "piece":
            pieces_of[u["county_fips"]].append(u["unit_id"])
    split = {c for c, ps in pieces_of.items() if len(ps) > 1}
    K = collections.defaultdict(dict)
    for r in csv.DictReader(open(os.path.join(HERE, "..", "keys", "keys.csv"))):
        K[r["key_id"]][r["piece_id"]] = float(r["value"])

    # BEA areas: counties, plus combinations (Virginia, Hawaii) that hold unit counties
    allareas = set()
    z = zipfile.ZipFile(bx.fetch(URL.format(t="CAINC4")))
    with z.open(ZIPS["CAINC4"][0]) as fh:
        r = csv.reader(io.TextIOWrapper(fh, encoding="latin-1")); next(r)
        names = {}
        for row in r:
            if len(row) > 5 and row[4].strip() == "10":
                f = row[0].strip().strip('"').strip(); names[f] = row[1]
    combo_members = {"15901": ["15005", "15009"]}
    va = {u["county_fips"]: u["county"] for u in units if u["county_fips"].startswith("51")}
    for f, n in names.items():
        if f.startswith("51") and f[2:] >= "900" and ("+" in n or "," in n):
            toks = [t.strip().replace(", VA*", "").replace(" VA*", "").replace("*", "") for t in n.replace(", VA*", "").replace("+", ",").split(",")]
            mem = []
            for i, t in enumerate(toks):  # BEA names the county first, then its independent cities
                t = t.strip()
                cands = [c for c, nm in va.items() if nm.lower() in (t.lower() + " county", t.lower() + " city", t.lower().replace(" city", "") + " city")]
                want = "County" if i == 0 and not t.endswith("City") else "city"
                cands = [c for c in cands if va[c].endswith(want)] or cands
                if cands:
                    mem.append(cands[0])
            combo_members[f] = mem
    in_combo = {m: f for f, ms in combo_members.items() for m in ms}
    missing = sorted(c for c in cty if c not in names and c not in in_combo)
    areas = (cty & set(names)) | set(combo_members)
    states = {a[:2] + "000" for a in areas}  # state rows: fallback transfer mix where a county has no CAINC35 (Connecticut regions)

    data, desc, year = {}, {}, {}
    for t in ZIPS:
        data[t], desc[t], year[t] = load(t, areas | (states if t == "CAINC35" else set()))

    # Fairfax combination (51919): extend keys to Fairfax City (51600) and Falls Church (51610)
    ext = {}
    fx_area = in_combo.get("51059")
    if fx_area:
        others = [m for m in combo_members[fx_area] if m != "51059"]
        tp = bk.tract_pop()
        area_of = {g: g[:5] for g in tp if g[:5] in others}
        lk, bands = bk.lodes_keys(area_of)
        pi = {r["piece_id"]: r for r in csv.DictReader(open(os.path.join(HERE, "..", "keys", "pay_index.csv")))}
        m3 = float(pi[pieces_of["51059"][0]]["top_band_mean"]); W = float(pi[pieces_of["51059"][0]]["qcew_avg_monthly_pay"])
        fx_bands = bk.lodes_keys({g: "fx" for g in tp if g[:5] == "51059"})[1]["fx"]
        mean = lambda b: (bk.BAND_MID[0] * b[0] + bk.BAND_MID[1] * b[1] + m3 * b[2]) / sum(b)
        index = {c: mean(bands[c]) / mean(fx_bands) for c in others}
        fx_pop = sum(upop[p] for p in pieces_of["51059"])
        for c in others:
            cp = sum(tp[g] for g in area_of if g[:5] == c)
            for key, d in K.items():
                fx_tot = sum(d.get(p, 0) for p in pieces_of["51059"])
                if key == "jobs_state":  # cities: LODES state and local x Fairfax County's ACS state share
                    fx_sl = sum(K["jobs_state_local"].get(p, 0) for p in pieces_of["51059"])
                    v = lk["jobs_state_local"].get(c, 0) * (fx_tot / fx_sl if fx_sl else 0)
                elif key.startswith(("jobs_", "est_")):
                    v = lk.get(key, {}).get(c, 0)
                elif key.startswith("wages_private_"):
                    v = lk.get(key.replace("wages_", "jobs_"), {}).get(c, 0) * index[c]
                elif key.startswith("wages_"):
                    v = lk.get(key.replace("wages_", "jobs_"), {}).get(c, 0) * index[c]
                else:
                    v = fx_tot * cp / fx_pop  # residence keys: population x the Fairfax average
                ext.setdefault(key, {})[c] = v
        hs = bk.housing_share()
        allm = pieces_of["51059"] + others
        h = {m: (K["housing_services"].get(m) if m in K["housing_services"] else ext["housing_services"][m]) for m in allm}
        w53 = {m: (K["wages_53"].get(m) if m in K["wages_53"] else ext["wages_53"][m]) for m in allm}
        th, tw = sum(h.values()), sum(w53.values())
        for m in allm:
            ext.setdefault("gdp_real_estate", {})[m] = hs * h[m] / th + (1 - hs) * w53[m] / tw

    def members(area):
        """The units a BEA area is shared among (pieces, or pieces plus cities for the Fairfax combination)."""
        if area in split:
            return pieces_of[area]
        if area == fx_area:
            return pieces_of["51059"] + [m for m in combo_members[area] if m != "51059"]
        return None

    def key(name, area):
        ms = members(area)
        vals = {m: (ext.get(name, {}).get(m) if m in ext.get(name, {}) and area == fx_area and not m.startswith("51059-") else K.get(name, {}).get(m, 0.0)) for m in ms}
        if area == fx_area and name == "gdp_real_estate":
            vals = {m: ext["gdp_real_estate"][m] for m in ms}
        return vals

    def share(d):
        t = sum(d.values())
        return {m: v / t for m, v in d.items()} if t else None

    def tree(area, vals, parent, children, keyname, proxyname, fallback):
        """Share a parent line and its child lines among members. Published children by their key; withheld children
        get the parent's residual, split at county level by proxy totals, then by their key."""
        out = {}
        pv = vals.get(parent)
        known = {c: vals[c] for c in children if vals.get(c) is not None}
        wh = [c for c in children if c in vals and vals.get(c) is None]
        for c, v in known.items():
            sh = share(key(keyname(c), area)) or share(key(fallback, area))
            out[c] = {m: v * s for m, s in sh.items()}
        if pv is not None and wh:
            rest = max(0.0, pv - sum(known.values()))
            px = {c: sum(key(proxyname(c), area).values()) for c in wh}
            tp_ = sum(px.values())
            for c in wh:
                cv = rest * (px[c] / tp_ if tp_ else 1 / len(wh))
                sh = share(key(keyname(c), area)) or share(key(fallback, area))
                out[c] = {m: cv * s for m, s in sh.items()}
        return out, set(wh)

    rows, detail = [], []
    pub_lines = {
        "CAGDP2": ["1", "2", "83"], "CAGDP9": ["1", "2", "83"],
        "CAINC5N": ["35", "50", "60", "70", "81", "90", "2000", "2001", "2002", "2010"],
        "CAINC4": ["10", "20", "30", "35", "36", "42", "45", "46", "47", "50", "60", "70"],
        "CAINC35": ["1000", "2000", "2100", "2110", "2200", "2210", "2220", "2300", "2400", "2500", "3000", "4000"],
        "CAEMP25N": ["10", "20", "40", "70", "90", "2000", "2001", "2002", "2010"]}
    groups = collections.defaultdict(list)
    for r in csv.DictReader(open(os.path.join(HERE, "..", "keys", "sector_groups.csv"))):
        groups[r["group"]].append(r["naics_sector"])
    sector_maps = {"CAGDP2": GDP_SECTORS, "CAGDP9": GDP_SECTORS, "CAINC5N": EARN_SECTORS, "CAEMP25N": EARN_SECTORS}

    def emit(unit, utype, c, t, line, value, method):
        d = desc[t].get(line, (line, ""))
        rows.append({"unit_id": unit, "unit_type": utype, "county_fips": c, "table": t, "line": line, "description": d[0],
                     "unit": d[1], "year": year[t], "value": "" if value is None else round(value, 1), "method": method})

    def group_lines(t, vals):
        """Industry-group values from sector lines (None if any sector line is withheld)."""
        out = {}
        sm = sector_maps.get(t)
        if not sm:
            return out
        inv = {s: l for l, s in sm.items()}
        for g, secs in groups.items():
            ls = [inv[s] for s in secs if s in inv and inv[s] in vals]
            if not ls:
                continue
            out["group:" + g] = None if any(vals[l] is None for l in ls) else sum(vals[l] for l in ls)
        return out

    # county units and combined areas: published
    for u in units:
        c = u["county_fips"]
        if c in split or (fx_area and c in combo_members.get(fx_area, [])):
            continue
        area = c if c in names else in_combo.get(c)
        for t in ZIPS:
            v = data[t].get(area, {})
            gl = group_lines(t, v)
            for line in pub_lines[t] + sorted(gl):
                if area != c:
                    emit(u["unit_id"], u["unit_type"], c, t, line, None, f"bea_combined_area {area}"); continue
                val = gl.get(line) if line.startswith("group:") else v.get(line)
                emit(u["unit_id"], u["unit_type"], c, t, line, val, "published" if val is not None else "withheld")

    # split counties (and the Fairfax combination): allocate
    notes_mix = []
    alloc_areas = sorted(split - ({"51059"} if fx_area else set())) + ([fx_area] if fx_area else [])
    for area in alloc_areas:
        ms = members(area)
        res = collections.defaultdict(dict)  # (table, line) -> member -> value
        withheld = collections.defaultdict(set)
        for t in ("CAGDP2", "CAGDP9"):
            v = data[t][area]
            secs = list(GDP_SECTORS)
            kn = lambda l: "gdp_real_estate" if GDP_SECTORS[l] == "53" else f"wages_private_{GDP_SECTORS[l]}"
            px = lambda l: f"wages_private_{GDP_SECTORS[l]}"
            out, wh = tree(area, v, "2", secs, kn, px, "wages_private_total")
            withheld[t] |= wh
            for l, d in out.items():
                res[(t, l)] = d
            # government: split by the county's CAINC5N government earnings mix
            ge = data["CAINC5N"][area]
            if ge.get("2011") is not None and ge.get("2012") is not None:
                parts = {"2001": ge.get("2001"), "2002": ge.get("2002"), "2011": ge["2011"], "2012": ge["2012"]}
            else:
                parts = {"2001": ge.get("2001"), "2002": ge.get("2002"), "2010": ge.get("2010")}
            kmap = {"2001": "jobs_federal", "2002": "res_armed_forces", "2010": "jobs_state_local", "2011": "jobs_state", "2012": "jobs_state_local"}
            tot = sum(x for x in parts.values() if x)
            gv = v.get("83") or 0
            res[(t, "83")] = collections.Counter()
            for l, x in parts.items():
                if not x or not tot:
                    continue
                sh = share(key(kmap[l], area)) or share(key("jobs_total", area))
                for m, s in sh.items():
                    res[(t, "83")][m] += gv * x / tot * s
            for m in ms:
                res[(t, "2")][m] = sum(res[(t, l)].get(m, 0) for l in secs if (t, l) in res)
                res[(t, "1")][m] = res[(t, "2")][m] + res[(t, "83")].get(m, 0)
        # earnings by industry
        t = "CAINC5N"; v = data[t][area]
        out, wh = tree(area, v, "90", list(EARN_SECTORS), lambda l: f"wages_private_{EARN_SECTORS[l]}", lambda l: f"wages_private_{EARN_SECTORS[l]}", "wages_private_total")
        withheld[t] |= wh; res.update({(t, l): d for l, d in out.items()})
        out, wh = tree(area, v, "2000", list(GOV_EARN), lambda l: GOV_EARN[l], lambda l: GOV_EARN[l], "jobs_total")
        withheld[t] |= wh; res.update({(t, l): d for l, d in out.items()})
        for l, kn in (("81", "wages_11"), ("50", "wages_total"), ("60", "wages_total"), ("70", "res_selfemp_income")):
            if v.get(l) is not None:
                sh = share(key(kn, area)) or share(key("wages_total", area))
                res[(t, l)] = {m: v[l] * s for m, s in sh.items()}
        for m in ms:
            res[(t, "90")][m] = sum(res[(t, l)].get(m, 0) for l in EARN_SECTORS if (t, l) in res)
            res[(t, "2010")][m] = res[(t, "2011")].get(m, 0) + res[(t, "2012")].get(m, 0) if (t, "2011") in res else 0
            res[(t, "2000")][m] = sum(res[(t, l)].get(m, 0) for l in GOV_EARN if (t, l) in res)
            res[(t, "35")][m] = res[(t, "81")].get(m, 0) + res[(t, "90")][m] + res[(t, "2000")][m]
        if (t, "2010") in res and not any(res[(t, "2010")].values()) and v.get("2010") is not None:
            sh = share(key("jobs_state_local", area)); res[(t, "2010")] = {m: v["2010"] * s for m, s in sh.items()}
        # transfers by type (2022)
        t = "CAINC35"; v = data[t].get(area, {})
        for l, kn in TRANSFER_LEAVES.items():
            if v.get(l) is not None:
                sh = share(key(kn, area)) or share(key("res_population", area))
                res[(t, l)] = {m: v[l] * s for m, s in sh.items()}
        for p, chs in TRANSFER_PARENTS.items():
            known = [c for c in chs if (t, c) in res]
            whs = [c for c in chs if (t, c) not in res and c in v]
            if v.get(p) is not None and whs:
                rest = max(0.0, v[p] - sum(v[c] or 0 for c in known))
                sh = share(key("res_population", area))
                for c in whs:
                    res[(t, c)] = {m: rest / len(whs) * s for m, s in sh.items()}; withheld[t].add(c)
            res[(t, p)] = {m: sum(res[(t, c)].get(m, 0) for c in chs if (t, c) in res) for m in ms}
        # personal income components (2024); transfers by the county's 2022 transfer mix
        t = "CAINC4"; v = data[t][area]
        mix = {l: data["CAINC35"].get(area, {}).get(l) for l in TRANSFER_LEAVES}
        tm = sum(x for x in mix.values() if x)
        if not tm:  # no county transfer table (CAINC35 2022 still has Connecticut's old counties): the state's mix
            mix = {l: data["CAINC35"].get(area[:2] + "000", {}).get(l) for l in TRANSFER_LEAVES}
            tm = sum(x for x in mix.values() if x)
            notes_mix.append(area)
        comp = collections.Counter()
        for l, x in mix.items():
            if x:
                for m, s in (share(key(TRANSFER_LEAVES[l], area)) or {}).items():
                    comp[m] += x / tm * s
        for l, kn in (("45", "res_wage_selfemp_income"), ("46", "res_dir_income"), ("36", "wages_total"), ("50", "wages_total"), ("60", "wages_total"), ("70", "res_selfemp_income")):
            sh = share(key(kn, area))
            res[(t, l)] = {m: (v.get(l) or 0) * s for m, s in sh.items()}
        res[(t, "47")] = {m: (v.get("47") or 0) * comp[m] for m in ms}
        res[(t, "35")] = dict(res[("CAINC5N", "35")])
        cpop = sum(upop25[m] for m in ms)
        for m in ms:
            res[(t, "10")][m] = res[(t, "45")][m] + res[(t, "46")][m] + res[(t, "47")][m]
            res[(t, "20")][m] = (v.get("20") or 0) * upop25[m] / cpop
        # employment by industry (2022)
        t = "CAEMP25N"; v = data[t][area]
        out, wh = tree(area, v, "90", list(EARN_SECTORS), lambda l: f"jobs_private_{EARN_SECTORS[l]}", lambda l: f"jobs_private_{EARN_SECTORS[l]}", "jobs_private_total")
        withheld[t] |= wh; res.update({(t, l): d for l, d in out.items()})
        out, wh = tree(area, v, "2000", list(GOV_EARN), lambda l: GOV_EARN[l], lambda l: GOV_EARN[l], "jobs_total")
        withheld[t] |= wh; res.update({(t, l): d for l, d in out.items()})
        for l, kn in (("70", "jobs_11"), ("40", "res_selfemployed_workers")):
            if v.get(l) is not None:
                sh = share(key(kn, area)) or share(key("jobs_total", area))
                res[(t, l)] = {m: v[l] * s for m, s in sh.items()}
        for m in ms:
            res[(t, "90")][m] = sum(res[(t, l)].get(m, 0) for l in EARN_SECTORS if (t, l) in res)
            res[(t, "2010")][m] = res[(t, "2011")].get(m, 0) + res[(t, "2012")].get(m, 0) if (t, "2011") in res else 0
            res[(t, "2000")][m] = sum(res[(t, l)].get(m, 0) for l in GOV_EARN if (t, l) in res)
            res[(t, "10")][m] = res[(t, "70")].get(m, 0) + res[(t, "90")][m] + res[(t, "2000")][m]
        # scale every published county line exactly; derived lines afterwards
        for (t, l), d in res.items():
            pub = data[t][area].get(l)
            s = sum(d.values())
            if pub is not None and s > 0 and l not in ("20",):
                for m in d:
                    d[m] *= pub / s
        for m in ms:
            res[("CAINC4", "10")][m] = res[("CAINC4", "45")][m] + res[("CAINC4", "46")][m] + res[("CAINC4", "47")][m]
            res[("CAINC4", "35")][m] = res[("CAINC5N", "35")][m]
            res[("CAINC4", "42")][m] = res[("CAINC4", "45")][m] - res[("CAINC4", "35")][m] + res[("CAINC4", "36")][m]
            res[("CAINC4", "30")][m] = res[("CAINC4", "10")][m] * 1000 / res[("CAINC4", "20")][m] if res[("CAINC4", "20")][m] else None
            res[("CAEMP25N", "20")][m] = res[("CAEMP25N", "10")][m] - res[("CAEMP25N", "40")].get(m, 0)
        for m in sorted(ms):
            ut = "piece" if "-" in m else "county"
            c = m[:5]
            for t in ZIPS:
                sm = sector_maps.get(t, {})
                vals = {l: (res[(t, l)].get(m) if (t, l) in res else None) for l in set(sm) | set(pub_lines[t])}
                for l in sm:
                    if l in withheld[t]:
                        vals[l] = None
                gl = group_lines(t, vals)
                for line in pub_lines[t] + sorted(gl):
                    val = gl.get(line) if line.startswith("group:") else vals.get(line)
                    cw = (line in withheld[t]) or (not line.startswith("group:") and data[t][area].get(line) is None and line not in ("30", "42", "20"))
                    emit(m, ut, c, t, line, None if cw else val, "withheld" if cw or val is None else "allocated")
                for (tt, l), d in res.items():
                    if tt == t and m in d:
                        detail.append({"unit_id": m, "county_fips": c, "bea_area": area, "table": t, "line": l,
                                       "description": desc[t].get(l, (l, ""))[0], "year": year[t], "value": round(d[m], 1),
                                       "county_line": "withheld (residual share)" if l in withheld[t] else "published"})

    cols = ["unit_id", "unit_type", "county_fips", "table", "line", "description", "unit", "year", "value", "method"]
    with open(os.path.join(HERE, "bea_units.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, cols); w.writeheader(); w.writerows(rows)
    with open(os.path.join(HERE, "bea_pieces_detail.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, list(detail[0])); w.writeheader(); w.writerows(detail)

    # checks: pieces sum to the published county (area) figure for every published total line
    bad = []
    byk = collections.defaultdict(float); cnt = collections.Counter()
    for r in rows:
        if r["method"] == "allocated" and not r["line"].startswith("group:"):
            area = in_combo.get(r["county_fips"], r["county_fips"]) if r["county_fips"] in ("51059", "51600", "51610") else r["county_fips"]
            byk[(area, r["table"], r["line"])] += float(r["value"]); cnt[(area, r["table"], r["line"])] += 1
    for (area, t, l), s in byk.items():
        pub = data[t].get(area, {}).get(l)
        if pub is not None and l not in ("30",) and abs(s - pub) > max(2.0, 1e-6 * abs(pub)):
            bad.append((area, t, l, round(s), pub))
    n = collections.Counter(r["method"].split()[0] for r in rows)
    print(f"rows {len(rows):,} units {len({r['unit_id'] for r in rows}):,}; methods {dict(n)}; counties with no BEA area {missing}; not covered by BEA (Puerto Rico) {len(no_bea)}; "
          f"sum checks failed {len(bad)} {bad[:5]}")
    if notes_mix:
        print("transfer mix from the state's CAINC35 (no county table):", notes_mix)


if __name__ == "__main__":
    main()
