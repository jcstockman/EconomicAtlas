"""Checks on the atlas indicator tables (docs/specs/atlas-indicators.md); exits non-zero on a failed check.

  additivity  district, subregion and metro counts equal the sums of their units (population, jobs, households)
  acs         for whole-county units, each ACS indicator from summed tracts against the ACS's own county estimate
              (same tables, county summary level); reports the median and 95th-percentile difference
  medians     estimated median household income and home value against the published county medians (B19013, B25077)
Writes check_indicators.csv (every county x indicator comparison).
usage: python3 check_indicators.py --cache DIR
"""
import argparse, collections, csv, os, statistics, sys

import build_indicators as bi

HERE = bi.HERE


def county_acs(table):
    return bi.bk.acs_geo(table.lower(), ("0500000US",))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True)
    a = ap.parse_args(); bi.bx.CACHE = a.cache; bi.bx.fix_hash_seed()
    rd = lambda f: list(csv.DictReader(open(os.path.join(HERE, f))))
    units = {r["unit_id"]: r for r in rd("indicators_units.csv")}
    fails = collections.defaultdict(list)

    # additivity
    xw = list(csv.DictReader(open(os.path.join(bi.R, "metros", "crosswalk_unit_metro.csv"))))
    for lvl, key in (("districts", "district_id"), ("subregions", "subregion_id"), ("metros", "cbsa")):
        mem = collections.defaultdict(list)
        for r in xw:
            if r[key]:
                mem[r[key]].append(r["unit_id"])
        for r in rd(f"indicators_{lvl}.csv"):
            for i in ("pop2025", "households", "qcew_jobs"):
                if r[i] == "" or any(units[m][i] == "" for m in mem[r[key]]):
                    continue
                s = sum(float(units[m][i]) for m in mem[r[key]])
                if abs(s - float(r[i])) > len(mem[r[key]]):  # rounding per unit
                    fails["additivity"].append(f"{lvl} {r[key]} {i}: {r[i]} vs {s:,.0f}")

    # ACS: tract sums against county estimates, whole-county units
    cat = {c[0]: c for c in bi.CATALOGUE}
    tables = sorted({t for t, _ in bi.ACS_COMP.values()} | {"B19013", "B25077"})
    cdata = {t: county_acs(t) for t in tables}
    rows, diffs = [], collections.defaultdict(list)
    for k, u in units.items():
        if u["unit_type"] != "county":
            continue
        c = {}
        for name, (t, vs) in bi.ACS_COMP.items():
            d = cdata[t].get(k)
            c[name] = None if d is None else sum(d.get(f"{t}_E{v}", 0) for v in vs)
        b08013, b08301 = cdata["B08013"].get(k), cdata["B08301"].get(k)
        c["acs_commuters"] = None if not b08301 else b08301["B08301_E001"] - b08301["B08301_E021"]
        for iid, _, _, kind, nu, de, sc, src, _ in bi.CATALOGUE:
            if not src.startswith("ACS") or kind == "count":
                continue
            if kind == "median":
                pub = cdata["B19013" if "inc" in nu else "B25077"].get(k, {})
                pv = pub.get("B19013_E001" if "inc" in nu else "B25077_E001")
                if not pv or u[iid] == "":
                    continue
                d = (float(u[iid]) - pv) / pv * 100
                diffs[iid].append(abs(d)); rows.append({"unit_id": k, "indicator": iid, "atlas": u[iid], "published": round(pv), "diff": round(d, 2), "diff_unit": "% of published"})
                continue
            if c.get(nu) is None or not c.get(de) or u[iid] == "":
                continue
            pv = c[nu] / c[de] * sc
            d = float(u[iid]) - pv
            diffs[iid].append(abs(d)); rows.append({"unit_id": k, "indicator": iid, "atlas": u[iid], "published": round(pv, 2), "diff": round(d, 2), "diff_unit": "points" if cat[iid][2] == "%" else cat[iid][2]})
    with open(os.path.join(HERE, "check_indicators.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"{'indicator':28} {'counties':>8} {'median |diff|':>14} {'p95 |diff|':>11}  unit")
    for iid, v in sorted(diffs.items()):
        v = sorted(v); p95 = v[int(0.95 * (len(v) - 1))]
        unit = "% of published" if cat[iid][3] == "median" else ("points" if cat[iid][2] == "%" else cat[iid][2])
        print(f"{iid:28} {len(v):8d} {statistics.median(v):14.2f} {p95:11.2f}  {unit}")
        # tract sums should reproduce county rates closely; medians from brackets within a few percent
        lim = 5.0 if cat[iid][3] == "median" else 1.0
        if p95 > lim:
            fails["acs"].append(f"{iid} p95 {p95:.2f} > {lim}")
    for n in ("additivity", "acs"):
        print(f"{'FAIL' if fails[n] else 'ok  '} {n}" + (f": {fails[n][:4]}" if fails[n] else ""))
    sys.exit(1 if any(fails.values()) else 0)


if __name__ == "__main__":
    main()
