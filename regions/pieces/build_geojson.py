"""Dissolve 2020 tracts into county pieces: regions/pieces/pieces.geojson.

Reads crosswalk_tract_piece.csv and pieces_summary.csv (build_crosswalk.py). Per piece:
  piece_id, county_fips, county, name (region name), components (top three component units), method, source_id, neighbors (adjacent piece_ids), pop2020, pop2025 (estimate),
  jobs_lodes (jobs located in the piece, LODES WAC S000 JT00),
  work_inside (share of resident workers with a job in the same piece, LODES OD main: in-state jobs only),
  lodes_year (2024; Michigan 2021),
  hispanic_share, nh_white_share, nh_black_share, nh_asian_share, nh_other_share (2020 PL 94-171 P2, piece_demographics.csv).
Geometry: union of the piece's tracts from the Census 2020 cartographic boundary file (cb_2020_us_tract_500k, clipped to
the shoreline), simplified by SIMPLIFY degrees, coordinates rounded to 5 decimals. Offshore areas are cut: water-only
tracts have no land polygon, and island parts of tracts are left out of the geometry when they hold no 2020 residents, or
fewer than 1,000 and lie more than 20 km from other land (San Clemente Island). Figures are not changed.
Needs pyshp.

usage: python3 build_geojson.py --cache DIR
"""
import argparse, collections, csv, gzip, json, os, urllib.request

from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from shapely.validation import make_valid

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_crosswalk as bx  # noqa: E402


def land_tracts(cache, counties):
    bx.CACHE = cache
    return bx.land_tracts(counties)

HERE = os.path.dirname(os.path.abspath(__file__))
SIMPLIFY = 0.0002  # about 20 m
ST = {"06": "ca", "48": "tx", "17": "il", "12": "fl", "36": "ny", "53": "wa", "42": "pa", "25": "ma", "26": "mi", "04": "az", "32": "nv",
      "39": "oh", "27": "mn", "37": "nc", "49": "ut", "51": "va", "13": "ga", "24": "md"}
YEAR = {"mi": "2021"}
LODES = "https://lehd.ces.census.gov/data/lodes/LODES8/{st}/{kind}/{st}_{kind}_{part}JT00_{yr}.csv.gz"


def lodes(cache, st, kind):
    yr = YEAR.get(st, "2024"); part = "main_" if kind == "od" else "S000_"
    name = f"{st}_{kind}_{part}JT00_{yr}.csv.gz"; p = os.path.join(cache, name)
    bx.CACHE = cache; p = bx.fetch(LODES.format(st=st, kind=kind, part=part, yr=yr), name)
    return p, yr


def rnd(o):
    if isinstance(o, float):
        return round(o, 5)
    if isinstance(o, (list, tuple)):
        return [rnd(x) for x in o]
    return o


FAR_ISLAND_KM, FAR_ISLAND_MAX = 20, 1000


def uninhabited_islands_removed(g, geo, cut):
    """Drop island parts of tract g (touching no other tract) that hold no 2020 residents, or that lie more than
    FAR_ISLAND_KM from any other tract and hold fewer than FAR_ISLAND_MAX residents (for example San Clemente Island).
    Only the drawing changes; the piece's figures keep everyone."""
    x = geo[g]
    parts = list(x.geoms) if x.geom_type == "MultiPolygon" else [x]
    near = x.buffer(0.01).envelope
    others = [y for h, y in geo.items() if h != g and y.envelope.intersects(near)]
    lone = [p for p in parts if not any(p.buffer(0.0005).intersects(y) for y in others)]
    if not lone:
        return x
    from shapely.geometry import Point
    allother = [y for h, y in geo.items() if h != g]
    def residents(p):
        return sum(int(b["properties"]["POP100"]) for b in bx.blocks(g) if b["properties"]["POP100"]
                   and p.buffer(0.0005).contains(Point(float(b["properties"]["INTPTLON"]), float(b["properties"]["INTPTLAT"]))))
    def far(p):
        return min(p.distance(y) for y in allother) * 111 > FAR_ISLAND_KM if allother else False
    keep = [p for p in parts if p not in lone or (residents(p) > 0 and not (residents(p) < FAR_ISLAND_MAX and far(p)))]
    if len(keep) < len(parts):
        cut.append(f"{g} ({len(parts) - len(keep)} of {len(parts)} parts)")
    return unary_union(keep) if keep else None


def drop_specks(g, min_area=1e-6):
    """Remove polygon parts under about 0.01 km2 left by the grow-and-shrink step at narrow necks."""
    if g.geom_type != "MultiPolygon":
        return g
    keep = [p for p in g.geoms if p.area >= min_area]
    return unary_union(keep) if keep else g


def main():
    bx.fix_hash_seed()
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True)
    a = ap.parse_args(); bx.CACHE = a.cache
    xw = list(csv.DictReader(open(os.path.join(HERE, "crosswalk_tract_piece.csv"))))
    piece_of = {r["tract_geoid"]: r["piece_id"] for r in xw}
    source = {r["piece_id"]: r["source_id"] for r in xw}
    summ = {r["piece_id"]: r for r in csv.DictReader(open(os.path.join(HERE, "pieces_summary.csv")))}
    demo = {r["piece_id"]: r for r in csv.DictReader(open(os.path.join(HERE, "piece_demographics.csv")))}  # build_demographics.py
    counties = sorted({r["county_fips"] for r in xw})
    jobs = collections.Counter(); res = collections.Counter(); inside = collections.Counter(); year = {}
    for st in sorted({c[:2] for c in counties}):
        abbr = ST[st]; cs = {c for c in counties if c[:2] == st}
        p, yr = lodes(a.cache, abbr, "wac")
        with gzip.open(p, "rt") as fh:
            r = csv.reader(fh); next(r)
            for row in r:
                pc = piece_of.get(row[0][:11])
                if pc:
                    jobs[pc] += int(row[1])
        p, yr = lodes(a.cache, abbr, "od")
        with gzip.open(p, "rt") as fh:
            r = csv.reader(fh); next(r)
            for w, h, n, *_ in r:
                hp = piece_of.get(h[:11])
                if hp:
                    res[hp] += int(n)
                    if piece_of.get(w[:11]) == hp:
                        inside[hp] += int(n)
        for c in cs:
            year[c] = yr
        print("lodes", abbr, yr)
    feats = []; cut = []
    land = land_tracts(a.cache, set(counties))
    for c in counties:
        pop = {t["properties"]["GEOID"]: t["properties"]["POP100"] for t in bx.tracts(c)}
        geo = {g: x for g, x in land.items() if g[:5] == c}
        by = collections.defaultdict(list)
        for g, pc in piece_of.items():
            if g[:5] != c or g not in geo:
                continue  # water-only tract: no land polygon
            by[pc].append(uninhabited_islands_removed(g, geo, cut))
        # close hairline gaps between neighbouring cartographic tracts: grow ~50 m, the adjacency tolerance build_groups.py uses, merge, shrink back
        full = {pc: drop_specks(make_valid(unary_union([x.buffer(0.0005) for x in gs if x is not None]).buffer(-0.0005))) for pc, gs in by.items()}
        for pc in sorted(by):
            geom = make_valid(full[pc].simplify(SIMPLIFY, preserve_topology=True))
            s = summ[pc]
            nb = sorted(q for q in full if q != pc and full[q].buffer(0.001).intersects(full[pc]))
            feats.append({"type": "Feature", "properties": {
                "piece_id": pc, "county_fips": c, "county": s["county"], "name": s["piece_name"], "components": s["piece_components"], "method": s["method"],
                "source_id": source[pc], "neighbors": nb,
                "pop2020": int(s["pop2020"]), "pop2025": int(s["pop2025_est"]), "jobs_lodes": jobs[pc],
                "work_inside": round(inside[pc] / res[pc], 4) if res[pc] else None, "lodes_year": int(year[c]),
                **{k: float(demo[pc][k]) for k in ("hispanic_share", "nh_white_share", "nh_black_share", "nh_asian_share", "nh_other_share")}},
                "geometry": rnd(mapping(geom))})
        print(c, len(by), "pieces")
    json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(HERE, "pieces.geojson"), "w"), separators=(",", ":"))
    print("offshore island parts cut from geometry:", cut)
    print("pieces", len(feats), "size MB", round(os.path.getsize(os.path.join(HERE, "pieces.geojson")) / 1e6, 1))


if __name__ == "__main__":
    main()
