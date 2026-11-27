"""Workplace check of the LODES job locations behind the allocation keys (docs/specs/allocation-keys.md, Workplace check).

CTPP 2017-2021 (workers by workplace tract) is not reachable from the build environment, so this check uses the ACS's own
workplace-geography tables (2020-2024 five-year), which count workers where they work for counties and places:
  B08528 class of worker (private, local, state and federal government) and B08526 industry (13 groups).
Within each county split into pieces, every place of 10,000+ ACS workers lying wholly in the county, plus the rest of
the county, gets its share of the county's jobs in LODES 8 (WAC 2024, Michigan 2021; blocks assigned to places with the
Census 2020 block assignment files) and its share of the county's workers in the ACS. For each class or industry the
check reports the share placed in the wrong area, sum |LODES share - ACS share| / 2, against the same figure for all
jobs (the baseline: ACS sampling error, jobs vs workers, place boundaries 2020 vs 2024). A class far above the baseline
means LODES puts those jobs at another address than the one workers report (a central office, a headquarters).
LODES has no state/local split: state and local government are compared together (JT00 - JT02 - JT04).

Writes next to this script: workplace_check.csv (county x class: areas, jobs, misplaced share, baseline) and
workplace_check_areas.csv (county x area x class: LODES and ACS counts and shares).
usage: python3 check_workplace.py --cache DIR
"""
import argparse, collections, csv, gzip, io, os, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pieces")); sys.path.insert(0, HERE)
import build_crosswalk as bx  # noqa: E402
import build_keys as bk  # noqa: E402

ACS = "https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-{t}.dat"
BAF = "https://www2.census.gov/geo/docs/maps-data/data/baf2020/BlockAssign_ST{ss}_{ST}.zip"
MIN_WORKERS = 10_000
# LODES sector columns (CNS01-CNS20) grouped to the ACS industry groups of B08526 (002-014)
IND = {"Agriculture and mining": (["CNS01", "CNS02"], 2), "Construction": (["CNS04"], 3), "Manufacturing": (["CNS05"], 4),
       "Wholesale trade": (["CNS06"], 5), "Retail trade": (["CNS07"], 6), "Transportation, warehousing, utilities": (["CNS08", "CNS03"], 7),
       "Information": (["CNS09"], 8), "Finance, insurance, real estate": (["CNS10", "CNS11"], 9),
       "Professional, management, administrative": (["CNS12", "CNS13", "CNS14"], 10), "Education and health care": (["CNS15", "CNS16"], 11),
       "Arts, accommodation and food": (["CNS17", "CNS18"], 12), "Other services": (["CNS19"], 13), "Public administration": (["CNS20"], 14)}


def acs(t, prefix):
    out = {}
    with open(bx.fetch(ACS.format(t=t), f"acsdt5y2024-{t}.dat"), encoding="latin-1") as fh:
        head = fh.readline().rstrip("\n").split("|")
        for line in fh:
            if line.startswith(prefix):
                f = line.rstrip("\n").split("|")
                out[f[0][9:]] = {h: float(v) if v not in ("", "null") and not v.startswith("*") and float(v) >= 0 else 0.0
                                 for h, v in zip(head[1:], f[1:]) if "_E" in h}
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True)
    a = ap.parse_args(); bx.CACHE = a.cache; bx.fix_hash_seed()
    U = os.path.join(HERE, "..", "units")
    npieces = collections.Counter(r["county_fips"] for r in csv.DictReader(open(os.path.join(U, "atlas_units.csv"))) if r["unit_type"] == "piece")
    split = sorted(c for c, n in npieces.items() if n > 1)
    cls = {"private": None, "state and local government": None, "federal government": None}
    acs_cls = {**acs("b08528", "1600000US"), **acs("b08528", "0500000US")}
    acs_ind = {**acs("b08526", "1600000US"), **acs("b08526", "0500000US")}

    def acs_values(g):
        c, i = acs_cls.get(g), acs_ind.get(g)
        if not c or not i:
            return None
        v = {"all jobs": c["B08528_E002"] + c["B08528_E005"] + c["B08528_E006"] + c["B08528_E007"] + c["B08528_E008"],
             "private": c["B08528_E002"] + c["B08528_E005"], "state and local government": c["B08528_E006"] + c["B08528_E007"],
             "federal government": c["B08528_E008"]}
        for name, (_, k) in IND.items():
            v[name] = i[f"B08526_E{k:03d}"]
        return v

    rows_c, rows_a = [], []
    for ss in sorted({c[:2] for c in split}):
        st = bk.ST[ss]
        ST = st.upper()
        z = zipfile.ZipFile(bx.fetch(BAF.format(ss=ss, ST=ST)))
        place_of, pcounties = {}, collections.defaultdict(set)
        with z.open(f"BlockAssign_ST{ss}_{ST}_INCPLACE_CDP.txt") as fh:
            r = csv.reader(io.TextIOWrapper(fh, encoding="latin-1"), delimiter="|"); next(r)
            for b, p in r:
                if p:
                    place_of[b] = ss + p; pcounties[ss + p].add(bx.cty(b))
        yr = bk.LODES_YEAR.get(st, "2024")
        lodes = collections.defaultdict(lambda: collections.Counter())  # (county, place|None) -> class -> jobs
        for jt in ("JT00", "JT02", "JT04"):
            with gzip.open(bx.fetch(bk.LODES.format(st=st, jt=jt, yr=yr)), "rt") as fh:
                r = csv.reader(fh); h = next(r); ix = {k: i for i, k in enumerate(h)}
                for row in r:
                    b = row[0]; c = bx.cty(b)
                    if c not in split:
                        continue
                    key = (c, place_of.get(b)); n = int(row[ix["C000"]])
                    if jt == "JT00":
                        lodes[key]["all jobs"] += n
                        for nm, (cols, _) in IND.items():
                            lodes[key][nm] += sum(int(row[ix[x]]) for x in cols)
                    elif jt == "JT02":
                        lodes[key]["private"] += n
                    else:
                        lodes[key]["federal government"] += n
        for key, v in lodes.items():
            v["state and local government"] = v["all jobs"] - v["private"] - v["federal government"]
        for c in sorted(x for x in split if x[:2] == ss):
            cty = acs_values(c)
            if cty is None:
                continue
            places = sorted(p for p in pcounties if pcounties[p] == {c} and (acs_values(p) or {}).get("all jobs", 0) >= MIN_WORKERS)
            classes = ["all jobs"] + list(cls) + list(IND)
            lt = collections.Counter()
            for (cc, p), v in lodes.items():
                if cc == c:
                    lt.update(v)
            areas = {}
            for p in places:
                areas[p] = (lodes.get((c, p), collections.Counter()), acs_values(p))
            rest_l = collections.Counter(lt); rest_a = dict(cty)
            for p, (lv, av) in areas.items():
                rest_l.subtract(lv)
                for k in classes:
                    rest_a[k] = rest_a[k] - av[k]
            areas["rest of county"] = (rest_l, {k: max(0.0, v) for k, v in rest_a.items()})
            mis = {}
            for k in classes:
                L = sum(max(0, lv[k]) for lv, _ in areas.values()); A = sum(av[k] for _, av in areas.values())
                if not L or not A:
                    continue
                mis[k] = sum(abs(max(0, lv[k]) / L - av[k] / A) for lv, av in areas.values()) / 2
                for ar, (lv, av) in areas.items():
                    rows_a.append({"county_fips": c, "area": ar, "class": k, "lodes": max(0, lv[k]), "acs": round(av[k]),
                                   "lodes_share": round(max(0, lv[k]) / L, 4), "acs_share": round(av[k] / A, 4)})
            for k, m in mis.items():
                rows_c.append({"county_fips": c, "class": k, "areas": len(areas), "lodes_jobs": lt[k], "acs_workers": round(cty[k]),
                               "misplaced": round(m, 4), "baseline_all_jobs": round(mis["all jobs"], 4)})
        print(ss, "done", flush=True)
    for fn, rows in (("workplace_check.csv", rows_c), ("workplace_check_areas.csv", rows_a)):
        with open(os.path.join(HERE, fn), "w", newline="") as fh:
            w = csv.DictWriter(fh, list(rows[0])); w.writeheader(); w.writerows(rows)
    # summary: job-weighted misplaced share by class
    agg = collections.defaultdict(lambda: [0.0, 0.0])
    for r in rows_c:
        agg[r["class"]][0] += r["misplaced"] * r["lodes_jobs"]; agg[r["class"]][1] += r["lodes_jobs"]
    print(f"{'class':42} misplaced (job-weighted, {len({r['county_fips'] for r in rows_c})} counties)")
    for k, (s, w) in sorted(agg.items(), key=lambda x: x[1][0] / x[1][1]):
        print(f"  {k:40} {s / w:6.1%}")


if __name__ == "__main__":
    main()
