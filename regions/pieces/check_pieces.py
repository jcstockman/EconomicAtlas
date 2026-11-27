"""Checks before freezing (docs/specs/county-pieces.md): validate the built outputs against the rules.

Fails (exit 1) on any of:
  coverage      every 2020 tract of each county in exactly one piece and one subarea, none extra
  registry      piece IDs active in piece_registry.csv, each anchor tract inside its own piece, names unique per county,
                names at most NAME_MAX characters, pins applied
  totals        each county's pieces sum to its 2020 census count and its Vintage 2025 estimate
  size          pieces of split counties within 0.45-1.1M (2025); whole counties within 1.0-1.25M and listed in WHOLE
  contiguity    each piece one populated land body, apart from islands touching no other piece
  necks         no piece whose main body splits when shrunk by NECK (rule 13)
  job centres   every job core and named district (rule 12) in one piece; APART anchor sets in different pieces
  subareas      nested in their piece, at least MIN_PART residents, exact-PUMA flags consistent
  files         pieces.geojson and subareas.geojson match the summaries
usage: python3 check_pieces.py --cache DIR
"""
import argparse, collections, csv, json, os, sys

from shapely.geometry import Point
from shapely.ops import unary_union

import build_crosswalk as bx
import build_groups as bg
import build_subareas as bs

HERE = os.path.dirname(os.path.abspath(__file__))
NAME_MAX = 45
LO, HI, WHOLE_MAX = 450_000, 1_100_000, 1_250_000


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True)
    a = ap.parse_args(); bx.CACHE = a.cache
    rd = lambda f: list(csv.DictReader(open(os.path.join(HERE, f))))
    xw, summ, reg, sub, subsum = rd("crosswalk_tract_piece.csv"), rd("pieces_summary.csv"), rd("piece_registry.csv"), \
        rd("crosswalk_tract_subarea.csv"), rd("subareas_summary.csv")
    pins = rd("pins.csv") if os.path.exists(os.path.join(HERE, "pins.csv")) else []
    groups = {c["fips"]: c for c in json.load(open(os.path.join(HERE, "groups.json")))}
    est = bg.county_list(a.cache)
    fails, notes = collections.defaultdict(list), []
    fail = lambda k, m: fails[k].append(m)

    piece_of = {}
    for r in xw:
        if r["tract_geoid"] in piece_of:
            fail("coverage", f"tract {r['tract_geoid']} listed twice")
        piece_of[r["tract_geoid"]] = r["piece_id"]
    counties = sorted({r["county_fips"] for r in xw})
    if set(counties) != set(est):
        fail("coverage", f"counties built {len(counties)} vs counties with 1.0M+ {len(est)}: {sorted(set(est) ^ set(counties))}")
    pop = {}
    for c in counties:
        tr = {t["properties"]["GEOID"]: t["properties"]["POP100"] for t in bx.tracts(c)}
        pop.update(tr)
        missing = set(tr) - {g for g in piece_of if g[:5] == c}
        extra = {g for g in piece_of if g[:5] == c} - set(tr)
        if missing or extra:
            fail("coverage", f"{c}: {len(missing)} tracts missing, {len(extra)} extra")

    # registry
    active = {r["piece_id"]: r for r in reg if r["status"] == "active"}
    pieces = {r["piece_id"]: r for r in summ}
    for p in pieces:
        if p not in active:
            fail("registry", f"piece {p} not active in piece_registry.csv")
    for p, r in active.items():
        if p not in pieces:
            fail("registry", f"active registry ID {p} has no piece")
        elif piece_of.get(r["anchor_tract"]) != p:
            fail("registry", f"{p}: anchor tract {r['anchor_tract']} lies in {piece_of.get(r['anchor_tract'])}")
        if pieces.get(p) and pieces[p]["piece_name"] != r["piece_name"]:
            fail("registry", f"{p}: summary name differs from registry")
        if len(r["piece_name"]) > NAME_MAX:
            fail("registry", f"{p}: name over {NAME_MAX} characters ({r['piece_name']})")
        if "name it" in r["note"]:
            fail("registry", f"{p}: new piece without a region name")
    byc = collections.defaultdict(list)
    for p, r in active.items():
        byc[r["county_fips"]].append(r["piece_name"])
    for c, ns in byc.items():
        dup = [n for n, k in collections.Counter(ns).items() if k > 1]
        if dup:
            fail("registry", f"{c}: duplicate names {dup}")
    for r in pins:
        if piece_of.get(r["tract_geoid"]) != r["piece_id"]:
            fail("registry", f"pin {r['tract_geoid']} -> {r['piece_id']} not applied")

    # totals and size
    for c in counties:
        ps = [r for r in summ if r["county_fips"] == c]
        p20 = sum(int(r["pop2020"]) for r in ps); p25 = sum(int(r["pop2025_est"]) for r in ps)
        t20 = sum(v for g, v in pop.items() if g[:5] == c)
        if p20 != t20:
            fail("totals", f"{c}: pieces sum to {p20:,} (2020), tracts to {t20:,}")
        if abs(p25 - est[c][1]) > len(ps):
            fail("totals", f"{c}: pieces sum to {p25:,} (2025), estimate {est[c][1]:,}")
        whole = groups[c]["method"] == "whole"
        for r in ps:
            v = int(r["pop2025_est"])
            if whole:
                if c not in bg.WHOLE or len(ps) != 1 or not (1_000_000 <= v <= WHOLE_MAX):
                    fail("size", f"{r['piece_id']}: whole county {v:,} not allowed")
            elif not (LO <= v <= HI):
                fail("size", f"{r['piece_id']}: {v:,} outside {LO:,}-{HI:,}")

    # contiguity, necks, job centres
    for c in counties:
        land = bx.land_tracts({c})
        assign = {g: (p, None, None) for g, p in piece_of.items() if g[:5] == c and g in land}
        by = collections.defaultdict(list)
        for g, (p, _, _) in assign.items():
            by[p].append(g)
        for p, gs in by.items():
            u = unary_union([land[g].buffer(0.0005) for g in gs])
            parts = [x for x in getattr(u, "geoms", [u]) if any(pop[g] for g in gs if x.intersects(land[g].representative_point()))]
            if len(parts) > 1:
                parts.sort(key=lambda x: -sum(pop[g] for g in gs if x.intersects(land[g].representative_point())))
                others = [land[g] for q, hs in by.items() if q != p for g in hs]
                for x in parts[1:]:
                    if any(x.intersects(o) for o in others):
                        fail("contiguity", f"{p}: a populated part touches another piece on land")
                        break
        for i in bg.necks(assign, land, pop):
            fail("necks", f"{i}: main body joined by a neck under ~{2 * bg.NECK * 111:.1f} km")
        for lab, nunits, n, tg in (x for x in groups[c].get("job_centres", []) if len(x) == 4):
            ps = {piece_of[g] for g in tg}
            if len(ps) > 1:
                fail("job centres", f"{c} {lab}: split across {sorted(ps)}")
        sets = []
        for lab, pts in bg.APART.get(c, []):
            tg = {g for g in land for x, y in pts if land[g].contains(Point(x, y))}
            ps = {piece_of[g] for g in tg}
            if len(ps) != 1:
                fail("job centres", f"{c} anchor set {lab} spans {sorted(ps)}")
            sets.append((lab, ps))
        allp = [p for _, ps in sets for p in ps]
        if len(allp) != len(set(allp)):
            fail("job centres", f"{c}: two anchor sets share a piece {sets}")

    # subareas
    sub_of = {r["tract_geoid"]: r for r in sub}
    if set(sub_of) != set(piece_of):
        fail("subareas", f"subarea crosswalk covers {len(sub_of)} tracts, piece crosswalk {len(piece_of)}")
    for g, r in sub_of.items():
        if r["piece_id"] != piece_of.get(g) or not r["subarea_id"].startswith(r["piece_id"] + "-"):
            fail("subareas", f"{g}: subarea {r['subarea_id']} not nested in piece {piece_of.get(g)}")
            break
    for r in subsum:
        if int(r["pop2020"]) < bs.MIN_PART:
            fail("subareas", f"{r['subarea_id']}: {int(r['pop2020']):,} residents, under {bs.MIN_PART:,}")
        if r["kind"] == "puma" and float(r["puma_share"]) < 0.99:
            fail("subareas", f"{r['subarea_id']}: flagged exact PUMA with share {r['puma_share']}")

    # files
    for fn, idk, rows in (("pieces.geojson", "piece_id", summ), ("subareas.geojson", "subarea_id", subsum)):
        feats = {f["properties"][idk]: f["properties"] for f in json.load(open(os.path.join(HERE, fn)))["features"]}
        if set(feats) != {r[idk] for r in rows}:
            fail("files", f"{fn}: features differ from the summary ({len(feats)} vs {len(rows)})")
        bad = [r[idk] for r in rows if r[idk] in feats and int(feats[r[idk]]["pop2020"]) != int(r["pop2020"])]
        if bad:
            fail("files", f"{fn}: pop2020 differs for {bad[:5]}")

    checks = ["coverage", "registry", "totals", "size", "contiguity", "necks", "job centres", "subareas", "files"]
    for k in checks:
        print(f"{'FAIL' if fails[k] else 'pass'}  {k}" + (f": {len(fails[k])} problem(s)" if fails[k] else ""))
        for m in fails[k][:10]:
            print("      ", m)
    print(f"{len(xw):,} tracts, {len(summ)} pieces, {len(subsum)} subareas, {len(counties)} counties")
    sys.exit(1 if any(fails.values()) else 0)


if __name__ == "__main__":
    main()
