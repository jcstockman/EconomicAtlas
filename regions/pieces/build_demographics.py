"""2020 tract demographics (PL 94-171, table P2) for the piece counties, and per-piece composition.

P2: total, Hispanic or Latino, and not Hispanic by race (White alone, Black alone, Asian alone; the rest grouped
as other, which includes AIAN, NHPI, some other race and two or more races).
Reads crosswalk_tract_piece.csv; writes tract_demographics.csv and piece_demographics.csv next to this script.

usage: python3 build_demographics.py --cache DIR
"""
import argparse, collections, csv, io, os, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_crosswalk as bx  # noqa: E402  (fetch: logged, hash-pinned downloads)

HERE = os.path.dirname(os.path.abspath(__file__))
PL = "https://www2.census.gov/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171/{name}/{st}2020.pl.zip"
STATES = {"06": ("California", "ca"), "48": ("Texas", "tx"), "17": ("Illinois", "il"), "12": ("Florida", "fl"), "36": ("New_York", "ny"),
          "53": ("Washington", "wa"), "42": ("Pennsylvania", "pa"), "25": ("Massachusetts", "ma"), "26": ("Michigan", "mi"),
          "04": ("Arizona", "az"), "32": ("Nevada", "nv"), "39": ("Ohio", "oh"), "27": ("Minnesota", "mn"), "37": ("North_Carolina", "nc"),
          "49": ("Utah", "ut"), "51": ("Virginia", "va"), "13": ("Georgia", "ga"), "24": ("Maryland", "md"),
          "09": ("Connecticut", "ct"), "18": ("Indiana", "in"), "29": ("Missouri", "mo"), "15": ("Hawaii", "hi"), "34": ("New_Jersey", "nj"), "55": ("Wisconsin", "wi")}
GROUPS = ["hispanic", "nh_white", "nh_black", "nh_asian", "nh_other"]


def tracts_for_state(cache, fips2, counties):
    name, st = STATES[fips2]
    bx.CACHE = cache; p = bx.fetch(PL.format(name=name, st=st))
    z = zipfile.ZipFile(p)
    logrec = {}
    with z.open(f"{st}geo2020.pl") as fh:
        for line in io.TextIOWrapper(fh, encoding="latin-1"):
            f = line.split("|")
            if f[2] == "140" and bx.cty(f[9][:11]) in counties:  # SUMLEV 140 = tract; GEOCODE = state+county+tract
                logrec[f[7]] = f[9]
    out = {}
    with z.open(f"{st}000012020.pl") as fh:
        for line in io.TextIOWrapper(fh, encoding="latin-1"):
            f = line.split("|")
            g = logrec.get(f[4])
            if g:
                tot, hisp, white, black, asian = int(f[76]), int(f[77]), int(f[80]), int(f[81]), int(f[83])
                out[g] = {"total": tot, "hispanic": hisp, "nh_white": white, "nh_black": black, "nh_asian": asian,
                          "nh_other": tot - hisp - white - black - asian}
    return out


def main():
    bx.fix_hash_seed()
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True)
    a = ap.parse_args(); os.makedirs(a.cache, exist_ok=True)
    xw = list(csv.DictReader(open(os.path.join(HERE, "crosswalk_tract_piece.csv"))))
    counties = {r["county_fips"] for r in xw}
    demo = {}
    for s2 in sorted({c[:2] for c in counties}):
        demo.update(tracts_for_state(a.cache, s2, {c for c in counties if c[:2] == s2}))
    missing = [r["tract_geoid"] for r in xw if r["tract_geoid"] not in demo]
    if missing:
        raise SystemExit(f"{len(missing)} crosswalk tracts not in PL files, e.g. {missing[:5]}")
    cols = ["tract_geoid", "total"] + GROUPS
    with open(os.path.join(HERE, "tract_demographics.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(cols)
        for g in sorted(demo):
            w.writerow([g] + [demo[g][k] for k in cols[1:]])
    agg = collections.defaultdict(collections.Counter)
    for r in xw:
        agg[r["piece_id"]].update(demo[r["tract_geoid"]])
    with open(os.path.join(HERE, "piece_demographics.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["piece_id", "total"] + GROUPS + [f"{k}_share" for k in GROUPS])
        for pid in sorted(agg):
            t = agg[pid]["total"]
            w.writerow([pid, t] + [agg[pid][k] for k in GROUPS] + [round(agg[pid][k] / t, 4) for k in GROUPS])
    print("tracts", len(demo), "pieces", len(agg))


if __name__ == "__main__":
    main()
