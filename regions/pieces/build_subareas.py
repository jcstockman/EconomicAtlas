"""Piece subareas: a tier nested inside county pieces, built from 2020 PUMAs (docs/specs/county-pieces.md, Subareas).

Each piece is cut along 2020 Public Use Microdata Area lines: a subarea is the part of one PUMA inside one piece
(each connected part separately). Parts holding fewer than MIN_PART 2020 residents join the neighbouring subarea in the
same piece with the longest shared boundary (islands: the nearest part of the same piece). A subarea is an exact PUMA when it holds the whole PUMA (>= 99% of its 2020
residents), so ACS 1-year PUMA estimates and PUMS apply to it directly; otherwise it is a PUMA part.

Reads crosswalk_tract_piece.csv and pieces_summary.csv. Writes next to this script:
  crosswalk_tract_subarea.csv  tract_geoid, piece_id, subarea_id, puma_geoid, assign (puma | absorbed | internal_point)
  Subarea IDs are stable: <piece_id>-<PUMA5CE> of the subarea's PUMA (plus a letter where one PUMA leaves several parts).
  subareas_summary.csv         subarea_id, piece_id, county_fips, name, puma_geoid, kind (puma | puma_part), puma_share,
                               pop2020, pop2025_est, jobs_lodes, absorbed_tracts
  subareas.geojson             same fields plus neighbors, work_inside and lodes_year
usage: python3 build_subareas.py --cache DIR
"""
import argparse, collections, csv, gzip, json, os, re

from shapely.geometry import mapping
from shapely.ops import unary_union
from shapely.strtree import STRtree
from shapely.validation import make_valid

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_crosswalk as bx  # noqa: E402
import build_geojson as bgj  # noqa: E402
import build_groups as bg  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MIN_PART = 30_000  # 2020 residents; smaller PUMA parts join a neighbouring subarea in the same piece


def puma_names():
    feats = bx.arcgis(bx.TG + "86", "1=1", "GEOID,BASENAME,POP100", geometry=False)
    return {f["properties"]["GEOID"]: (f["properties"]["BASENAME"], f["properties"]["POP100"]) for f in feats}


def short(name):
    """'Clark County (Central)--Spring Valley (West)' -> 'Spring Valley (West)'; keeps names without a county prefix."""
    m = re.match(r"NYC-\w+ Community Districts? ([\d &]+)--(.+)", name)
    if m:  # 'NYC-Manhattan Community District 9--Morningside Heights & Hamilton Heights' -> '... (CD 9)'
        return f"{m.group(2)} (CD {m.group(1).strip()})"
    parts = name.split("--", 1)
    return parts[1] if len(parts) == 2 and re.search(r"Count(y|ies)|Borough|Parish", parts[0]) else name


def main():
    bx.fix_hash_seed()
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True)
    a = ap.parse_args(); bx.CACHE = a.cache
    xw = list(csv.DictReader(open(os.path.join(HERE, "crosswalk_tract_piece.csv"))))
    summ = {r["piece_id"]: r for r in csv.DictReader(open(os.path.join(HERE, "pieces_summary.csv")))}
    piece_of = {r["tract_geoid"]: r["piece_id"] for r in xw}
    counties = sorted({r["county_fips"] for r in xw})
    puma = bg.puma_of(); names = puma_names()
    pop, ipt = {}, {}
    for c in counties:
        for t in bx.tracts(c):
            q = t["properties"]; pop[q["GEOID"]] = q["POP100"]; ipt[q["GEOID"]] = (float(q["INTPTLON"]), float(q["INTPTLAT"]))
    puma_pop = collections.Counter()
    for g, p in puma.items():
        if g in pop:
            puma_pop[p] += pop[g]
    land = bx.land_tracts(set(counties))
    sub_of, how = {}, {}
    for c in counties:
        gs = [g for g in piece_of if g[:5] == c]
        lg = [g for g in gs if g in land]
        buf = {g: land[g].buffer(0.0005) for g in lg}
        tree = STRtree([buf[g] for g in lg]); adj = collections.defaultdict(dict)
        for i, g in enumerate(lg):
            for j in tree.query(buf[g], predicate="intersects"):
                h = lg[j]
                if h != g and piece_of[h] == piece_of[g]:
                    adj[g][h] = buf[g].intersection(buf[h]).area / 0.001
        # connected parts of (piece, PUMA) on land
        part = {}; parts = []
        for g in lg:
            if g in part:
                continue
            key = (piece_of[g], puma[g]); comp = {g}; stk = [g]; part[g] = len(parts)
            while stk:
                x = stk.pop()
                for y in adj[x]:
                    if y not in part and (piece_of[y], puma[y]) == key:
                        part[y] = len(parts); comp.add(y); stk.append(y)
            parts.append({"piece": key[0], "puma": key[1], "tracts": comp, "pop": sum(pop[t] for t in comp)})
        # absorb small parts into the neighbouring part (same piece) with the longest shared boundary, smallest first
        alive = set(range(len(parts))); absorbed = collections.defaultdict(set)
        while True:
            small = sorted((i for i in alive if parts[i]["pop"] < MIN_PART), key=lambda i: parts[i]["pop"])
            moved = False
            for i in small:
                border = collections.Counter()
                for t in parts[i]["tracts"]:
                    for h, w in adj[t].items():
                        j = part[h]
                        if j != i and j in alive:
                            border[j] += w
                if border:
                    j = border.most_common(1)[0][0]
                else:  # island: nearest part of the same piece across the water
                    others = [j for j in alive if j != i and parts[j]["piece"] == parts[i]["piece"]]
                    if not others:
                        continue
                    gi = unary_union([land[t] for t in parts[i]["tracts"]])
                    j = min(others, key=lambda j: min(gi.distance(land[t]) for t in parts[j]["tracts"]))
                for t in parts[i]["tracts"]:
                    part[t] = j
                absorbed[j] |= parts[i]["tracts"] | absorbed.pop(i, set())
                parts[j]["tracts"] |= parts[i]["tracts"]; parts[j]["pop"] += parts[i]["pop"]
                alive.discard(i); moved = True
                break
            if not moved:
                break
        for i in alive:
            for t in parts[i]["tracts"]:
                sub_of[t] = i; how[t] = "absorbed" if t in absorbed[i] else "puma"
        for g in gs:  # water-only tracts: subarea of the nearest land tract (internal points) in the same piece
            if g not in sub_of:
                same = [h for h in lg if piece_of[h] == piece_of[g]]
                near = min(same, key=lambda h: (ipt[h][0] - ipt[g][0]) ** 2 + (ipt[h][1] - ipt[g][1]) ** 2)
                sub_of[g] = sub_of[near]; how[g] = "internal_point"
        # stable IDs: <piece_id>-<PUMA5CE> of the part's PUMA; a letter is added when one PUMA leaves several parts in a piece
        by_key = collections.defaultdict(list)
        for i in alive:
            by_key[(parts[i]["piece"], parts[i]["puma"][2:])].append(i)
        sid = {}
        for (pc, pu), ids in by_key.items():
            ids = sorted(ids, key=lambda i: -parts[i]["pop"])
            for n, i in enumerate(ids):
                sid[i] = f"{pc}-{pu}" + ("" if len(ids) == 1 else "abcdefghij"[n])
        for g in gs:
            sub_of[g] = sid[sub_of[g]] if isinstance(sub_of[g], int) else sub_of[g]
        print(c, len(alive), "subareas", flush=True)
    # summary figures
    members = collections.defaultdict(list)
    for g, s in sub_of.items():
        members[s].append(g)
    jobs = collections.Counter(); res = collections.Counter(); inside = collections.Counter(); year = {}
    for st in sorted({c[:2] for c in counties}):
        abbr = bgj.ST[st]
        p, yr = bgj.lodes(a.cache, abbr, "wac")
        with gzip.open(p, "rt") as fh:
            r = csv.reader(fh); next(r)
            for row in r:
                s = sub_of.get(row[0][:11])
                if s:
                    jobs[s] += int(row[1])
        p, yr = bgj.lodes(a.cache, abbr, "od")
        with gzip.open(p, "rt") as fh:
            r = csv.reader(fh); next(r)
            for w, h, n, *_ in r:
                hs = sub_of.get(h[:11])
                if hs:
                    res[hs] += int(n)
                    if sub_of.get(w[:11]) == hs:
                        inside[hs] += int(n)
        for c in counties:
            if c[:2] == st:
                year[c] = yr
    rows = []
    for s, gs in sorted(members.items()):
        pc = s[:8]; c = pc[:5]
        pp = collections.Counter()
        for g in gs:
            pp[puma[g]] += pop[g]
        main_puma = pp.most_common(1)[0][0]
        share = pp[main_puma] / puma_pop[main_puma] if puma_pop[main_puma] else 0
        p20 = sum(pop[g] for g in gs); scale = int(summ[pc]["pop2025_est"]) / max(1, int(summ[pc]["pop2020"]))
        exact = share >= 0.99 and pp[main_puma] >= 0.99 * p20
        nm = short(names.get(main_puma, (main_puma, 0))[0]) + ("" if exact else " (part)")
        rows.append({"subarea_id": s, "piece_id": pc, "county_fips": c, "name": nm, "puma_geoid": main_puma,
                     "kind": "puma" if exact else "puma_part", "puma_share": round(share, 4), "pop2020": p20,
                     "pop2025_est": round(p20 * scale), "jobs_lodes": jobs[s],
                     "absorbed_tracts": sum(1 for g in gs if how[g] == "absorbed")})
    with open(os.path.join(HERE, "crosswalk_tract_subarea.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["tract_geoid", "piece_id", "subarea_id", "puma_geoid", "assign"])
        for g in sorted(sub_of):
            w.writerow([g, piece_of[g], sub_of[g], puma.get(g, ""), how[g]])
    cols = list(rows[0])
    with open(os.path.join(HERE, "subareas_summary.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, cols); w.writeheader(); w.writerows(rows)
    # geometry, dissolved as in build_geojson.py
    feats = []; cut = []
    geom = {}
    for c in counties:
        geo = {g: x for g, x in land.items() if g[:5] == c}
        by = collections.defaultdict(list)
        for g, s in sub_of.items():
            if g[:5] == c and g in geo:
                by[s].append(bgj.uninhabited_islands_removed(g, geo, cut))
        for s, xs in by.items():
            geom[s] = bgj.drop_specks(make_valid(unary_union([x.buffer(0.0005) for x in xs if x is not None]).buffer(-0.0005)))
    tree_ids = sorted(geom); tree = STRtree([geom[s] for s in tree_ids])
    for r in rows:
        s = r["subarea_id"]
        if s not in geom:
            continue
        nb = sorted(tree_ids[j] for j in tree.query(geom[s].buffer(0.001), predicate="intersects") if tree_ids[j] != s)
        feats.append({"type": "Feature", "properties": {**r, "county": summ[r["piece_id"]]["county"],
                      "piece_name": summ[r["piece_id"]]["piece_name"], "neighbors": nb,
                      "work_inside": round(inside[s] / res[s], 4) if res[s] else None, "lodes_year": int(year[r["county_fips"]])},
                      "geometry": bgj.rnd(mapping(make_valid(geom[s].simplify(bgj.SIMPLIFY, preserve_topology=True))))})
    json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(HERE, "subareas.geojson"), "w"), separators=(",", ":"))
    k = collections.Counter(r["kind"] for r in rows)
    print("subareas", len(rows), dict(k), "pop2020 range", min(r["pop2020"] for r in rows), max(r["pop2020"] for r in rows),
          "size MB", round(os.path.getsize(os.path.join(HERE, "subareas.geojson")) / 1e6, 1))


if __name__ == "__main__":
    main()
