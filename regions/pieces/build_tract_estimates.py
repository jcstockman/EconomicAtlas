"""Tract 2025 population estimates for the counties split into pieces (docs/specs/county-pieces.md, Sub-county
estimates; docs/specs/atlas-indicators.md).

The Census Bureau publishes 2025 estimates for counties and for cities and towns, not for tracts. The sub-county method:
  1. every 2020 block (PL 94-171) is grown by its area's April 2020 - July 2025 growth in the Vintage 2025 city and town
     estimates (sub-est2025): the place part within a county subdivision where county subdivisions are estimated (states
     with towns or townships), otherwise the incorporated place within the county, otherwise the balance of the county;
  2. block values are summed to tracts and controlled to the county's 2025 estimate (Vintage 2025), so tracts add up to it;
  3. a tract's 2020 base is the county's April 2020 estimates base times the tract's share of the county's 2020 count.
Counties of 0.92M+ (build_groups.MIN_COUNTY), i.e. every county that has pieces.
Writes tract_pop2025.csv next to this script: tract_geoid, county_fips, pop2020, est_base2020, pop2025_est (decimals kept;
users round per piece with piece_pop2025), growth_source (share of the tract's residents by source: cousub/place/county).
usage: python3 build_tract_estimates.py --cache DIR
"""
import argparse, collections, csv, io, os, zipfile

import build_crosswalk as bx

HERE = os.path.dirname(os.path.abspath(__file__))
EST = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/counties/totals/co-est2025-alldata.csv"
SUBEST = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/cities/totals/sub-est2025_{s}.csv"
OUT = os.path.join(HERE, "tract_pop2025.csv")


def load():
    """{tract: (county, 2020 count, 2020 estimates base, 2025 estimate)} from tract_pop2025.csv."""
    return {r["tract_geoid"]: (r["county_fips"], int(r["pop2020"]), float(r["est_base2020"]), float(r["pop2025_est"]))
            for r in csv.DictReader(open(OUT))}


def piece_pop2025(piece_of, est=None):
    """Piece 2025 estimates: tract estimates summed per piece and rounded by largest remainder within each county, so a
    county's pieces add up exactly to its 2025 estimate. piece_of: {tract: piece_id}."""
    est = est or load()
    raw = collections.Counter()
    for g, p in piece_of.items():
        if g in est:
            raw[p] += est[g][3]
    out = {}
    for c in sorted({p[:5] for p in raw}):
        ps = [p for p in raw if p[:5] == c]
        tot = round(sum(raw[p] for p in ps))
        alloc = {p: int(raw[p]) for p in ps}
        for p in sorted(ps, key=lambda p: -(raw[p] - alloc[p]))[:tot - sum(alloc.values())]:
            alloc[p] += 1
        out.update(alloc)
    return out


def main():
    import build_demographics as bd
    import build_groups as bg
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True)
    a = ap.parse_args(); bx.CACHE = a.cache; bx.fix_hash_seed()
    county = {}
    for r in csv.DictReader(open(bx.fetch(EST), encoding="latin-1")):
        if r["SUMLEV"] == "050" and int(r["POPESTIMATE2025"]) >= bg.MIN_COUNTY:
            county[r["STATE"] + r["COUNTY"]] = (int(r["ESTIMATESBASE2020"]), int(r["POPESTIMATE2025"]))
    rows = []
    for s2 in sorted({c[:2] for c in county}):
        name, st = bd.STATES[s2]
        g071, g157 = {}, {}
        for r in csv.DictReader(open(bx.fetch(SUBEST.format(s=int(s2))), encoding="latin-1")):
            b, e = int(r["ESTIMATESBASE2020"]), int(r["POPESTIMATE2025"])
            if b <= 0:
                continue
            if r["SUMLEV"] == "071":  # place part within a county subdivision (cousub codes are unique within a state)
                g071[(r["COUSUB"], r["PLACE"])] = e / b
            elif r["SUMLEV"] == "157":  # incorporated place within a county, or the balance of the county (99990)
                g157[(r["STATE"] + r["COUNTY"], r["PLACE"])] = e / b
        z = zipfile.ZipFile(bx.fetch(bd.PL.format(name=name, st=st)))
        geo = {}
        with z.open(f"{st}geo2020.pl") as fh:
            for line in io.TextIOWrapper(fh, encoding="latin-1"):
                f = line.split("|")
                if f[2] == "750":
                    c = bx.cty(f[9][:11])
                    if c in county:
                        geo[f[7]] = (f[9][:11], c, f[17], f[29])
        p20, grown = collections.Counter(), collections.Counter()
        src = collections.defaultdict(collections.Counter)
        with z.open(f"{st}000012020.pl") as fh:
            for line in io.TextIOWrapper(fh, encoding="latin-1"):
                f = line.split("|"); g = geo.get(f[4])
                if not g:
                    continue
                t, c, cs, pl = g; n = int(f[5])
                p20[t] += n
                if not n:
                    continue
                gr, how = g071.get((cs, pl)) or g071.get((cs, "99990")), "cousub"
                if gr is None:
                    gr, how = g157.get((c, pl)) or g157.get((c, "99990")), "place"
                if gr is None:
                    gr, how = county[c][1] / county[c][0], "county"
                grown[t] += n * gr; src[t][how] += n
        for c in sorted(x for x in county if x[:2] == s2):
            ts = [t for t in p20 if bx.cty(t) == c]
            b, e = county[c]; c20, cg = sum(p20[t] for t in ts), sum(grown[t] for t in ts)
            for t in sorted(ts):
                rows.append({"tract_geoid": t, "county_fips": c, "pop2020": p20[t], "est_base2020": round(b * p20[t] / c20, 3),
                             "pop2025_est": round(e * grown[t] / cg, 3) if cg else 0.0,
                             "growth_source": ";".join(f"{k}:{v / p20[t]:.2f}" for k, v in sorted(src[t].items())) if p20[t] else ""})
        print(f"{st}: {len(geo):,} blocks", flush=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"tract_pop2025.csv: {len(rows):,} tracts in {len(county)} counties")


if __name__ == "__main__":
    main()
