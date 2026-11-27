"""Checks on the built subregions and districts (docs/specs/subregions-districts.md); exits non-zero on any failure.

  coverage    every atlas unit in a CBSA of 1.0M+ (OMB 2023, Vintage 2025) is in the crosswalk exactly once, no other unit is
  nesting     each district lies in one CBSA and (in CBSAs of 2.5M+) one subregion; subregions only in CBSAs of 2.5M+
  sizes       subregions 0.6-3.5M; districts in the district view 0.35-1.5M
  view        district view = subregion over 1.5M (CBSAs of 2.5M+), or two or more districts (CBSAs of 1.0-2.5M)
  contiguity  every district and subregion is contiguous (adjacency as in the build)
  totals      populations add up: units -> districts -> subregions -> CBSA
  registry    every ID in use is active in metro_registry.csv and every active ID is in use
  files       GeoJSON features match the summary tables
  names       every area has a curated name (metro_names.csv), unique within its CBSA except a subregion that is a single
              district, which shares that district's name

usage: python3 check_metros.py --cache DIR
"""
import argparse, collections, csv, json, os, sys

import networkx as nx
from shapely.geometry import shape

import build_metros as bm

HERE = bm.HERE


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True)
    a = ap.parse_args(); bm.bx.CACHE = a.cache
    U = os.path.join(HERE, "..", "units")
    units = {u["unit_id"]: u for u in csv.DictReader(open(os.path.join(U, "atlas_units.csv")))}
    upop = {k: int(u["pop2025_est"]) for k, u in units.items()}
    rd = lambda f: list(csv.DictReader(open(os.path.join(HERE, f))))
    xw, D, S, reg = rd("crosswalk_unit_metro.csv"), rd("districts.csv"), rd("subregions.csv"), rd("metro_registry.csv")
    cbsa_of = {d["FIPS State Code"] + d["FIPS County Code"]: d["CBSA Code"] for d in bm.delineation()}
    cunits = collections.defaultdict(set)
    for k, u in units.items():
        if u["county_fips"] in cbsa_of:
            cunits[cbsa_of[u["county_fips"]]].add(k)
    cpop = {c: sum(upop[k] for k in ks) for c, ks in cunits.items()}
    covered = {c for c in cunits if cpop[c] >= bm.COVER}; big = {c for c in covered if cpop[c] >= bm.BIG}
    fails = collections.defaultdict(list)

    ids = [r["unit_id"] for r in xw]
    want = set().union(*(cunits[c] for c in covered))
    if len(ids) != len(set(ids)) or set(ids) != want:
        fails["coverage"].append(f"{len(ids)} rows, {len(set(ids))} units; missing {sorted(want - set(ids))[:5]}, extra {sorted(set(ids) - want)[:5]}")
    for r in xw:
        if r["cbsa"] != cbsa_of.get(r["county_fips"]):
            fails["coverage"].append(f"{r['unit_id']} cbsa {r['cbsa']}")

    dmem, smem = collections.defaultdict(set), collections.defaultdict(set)
    d_s, d_c, s_c = collections.defaultdict(set), collections.defaultdict(set), collections.defaultdict(set)
    for r in xw:
        dmem[r["district_id"]].add(r["unit_id"]); d_c[r["district_id"]].add(r["cbsa"]); d_s[r["district_id"]].add(r["subregion_id"])
        if r["subregion_id"]:
            smem[r["subregion_id"]].add(r["unit_id"]); s_c[r["subregion_id"]].add(r["cbsa"])
        if (r["cbsa"] in big) != bool(r["subregion_id"]):
            fails["nesting"].append(f"{r['unit_id']}: subregion '{r['subregion_id']}' in CBSA {r['cbsa']}")
    for d in dmem:
        if len(d_c[d]) > 1 or len(d_s[d]) > 1:
            fails["nesting"].append(f"{d} spans {sorted(d_c[d])} / {sorted(d_s[d])}")
    for s in smem:
        if len(s_c[s]) > 1:
            fails["nesting"].append(f"{s} spans {sorted(s_c[s])}")

    spop = {r["subregion_id"]: int(r["pop2025"]) for r in S}
    ndist = collections.Counter(r["cbsa"] for r in D)
    for r in S:
        if not bm.S_LO <= spop[r["subregion_id"]] <= bm.S_HI:
            fails["sizes"].append(f"{r['subregion_id']} {spop[r['subregion_id']]:,}")
        if (r["district_view"] == "True") != (spop[r["subregion_id"]] > bm.VIEW_MIN):
            fails["view"].append(r["subregion_id"])
    for r in D:
        view = r["district_view"] == "True"
        if view and not bm.D_LO <= int(r["pop2025"]) <= bm.D_HI:
            fails["sizes"].append(f"{r['district_id']} {int(r['pop2025']):,}")
        expect = (spop[r["subregion_id"]] > bm.VIEW_MIN) if r["subregion_id"] else ndist[r["cbsa"]] >= 2
        if view != expect:
            fails["view"].append(r["district_id"])

    geo = {f["properties"]["unit_id"]: shape(f["geometry"]) for f in json.load(open(os.path.join(U, "atlas_units.geojson")))["features"]
           if f["properties"]["unit_id"] in want}
    adj, _ = bm.adjacency(geo, {c: cunits[c] for c in covered}, upop, sorted(covered))
    for name, mem in (("district", dmem), ("subregion", smem)):
        for g, ks in mem.items():
            G = nx.Graph(); G.add_nodes_from(ks); G.add_edges_from((k, m) for k in ks for m in adj[k] if m in ks)
            if not nx.is_connected(G):
                fails["contiguity"].append(f"{name} {g}")

    for r in D:
        if int(r["pop2025"]) != sum(upop[k] for k in dmem[r["district_id"]]):
            fails["totals"].append(r["district_id"])
    for r in S:
        if spop[r["subregion_id"]] != sum(int(x["pop2025"]) for x in D if x["subregion_id"] == r["subregion_id"]):
            fails["totals"].append(r["subregion_id"])
    for c in big:
        if sum(spop[s] for s in smem if c in s_c[s]) != cpop[c]:
            fails["totals"].append(f"CBSA {c}")

    active = {r["id"] for r in reg if r["status"] == "active"}
    used = set(dmem) | set(smem)
    if used != active or {r["district_id"] for r in D} != set(dmem) or {r["subregion_id"] for r in S} != set(smem):
        fails["registry"].append(f"in use not active {sorted(used - active)[:5]}; active not in use {sorted(active - used)[:5]}")

    for f, rows, key in (("districts.geojson", D, "district_id"), ("subregions.geojson", S, "subregion_id")):
        got = sorted(x["properties"][key] for x in json.load(open(os.path.join(HERE, f)))["features"])
        if got != sorted(r[key] for r in rows):
            fails["files"].append(f)

    seen = collections.defaultdict(list)
    for r in S:
        seen[(r["cbsa"], r["name"])].append(("s", r["subregion_id"], frozenset(smem[r["subregion_id"]])))
    for r in D:
        seen[(r["cbsa"], r["name"])].append(("d", r["district_id"], frozenset(dmem[r["district_id"]])))
        if r["name_source"] != "curated" or not r["name"].strip():
            fails["names"].append(f"{r['district_id']} has no curated name")
    for r in S:
        if r["name_source"] != "curated" or not r["name"].strip():
            fails["names"].append(f"{r['subregion_id']} has no curated name")
    for (c, n), xs in seen.items():
        if len(xs) > 1 and not (len(xs) == 2 and {x[0] for x in xs} == {"s", "d"} and xs[0][2] == xs[1][2]):
            fails["names"].append(f"'{n}' used by {[x[1] for x in xs]}")

    names = ["coverage", "nesting", "sizes", "view", "contiguity", "totals", "registry", "files", "names"]
    for n in names:
        print(f"{'FAIL' if fails[n] else 'ok  '} {n}" + (f": {len(fails[n])} - {fails[n][:3]}" if fails[n] else ""))
    print(f"CBSAs {len(covered)} ({len(big)} of 2.5M+), units {len(ids)}, districts {len(D)} "
          f"({sum(r['district_view'] == 'True' for r in D)} in the view), subregions {len(S)}")
    sys.exit(1 if any(fails.values()) else 0)


if __name__ == "__main__":
    main()
