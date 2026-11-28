"""Finalize the tract-to-piece crosswalk for every county in groups.json (docs/specs/county-pieces.md).

build_groups.py assigns land tracts to pieces (nested, or by largest 2020 block-population share where a division line
cuts a tract). Here water-only tracts join the piece of the nearest tract (`internal_point`), and a contiguity repair
moves populated parts cut off from their piece to the piece they border most (`contiguity`). Piece IDs are stable:
piece_registry.csv ties each ID and region name to an anchor tract, and a piece takes the ID of the anchor it holds; a new
piece gets the next unused number, and an ID whose anchor no longer marks its own piece is retired (never reused).
pins.csv (tract_geoid, piece_id, note) moves single tracts by hand after the grouping. The mechanical label (top three
component units or places) is kept as piece_components. Also holds the shared loaders used by the other build scripts.

usage: python3 build_crosswalk.py --cache DIR
Writes crosswalk_tract_piece.csv, split_tracts.csv and pieces_summary.csv next to this script.
"""
import argparse, collections, csv, hashlib, json, os, time, urllib.error, urllib.parse, urllib.request

from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree
from shapely.validation import make_valid

TG = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2020/MapServer/"
HERE = os.path.dirname(os.path.abspath(__file__))
VERSION = open(os.path.join(HERE, "VERSION")).read().strip()  # geography version (release.py)
CACHE = None


def _open(url):
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 5:
                raise
            time.sleep(5 * 2 ** attempt)


# Frozen inputs (freeze_inputs.py, spec rule 6). Query answers from local-government hosts are snapshotted in
# inputs/snapshot/ and read first; every other input (Census, LEHD) is pinned by SHA-256 in inputs/manifest.csv and
# checked when read. PIECES_REFRESH=1 ignores the snapshot and the pins (to fetch newer sources on purpose).
INPUTS = os.path.join(HERE, "inputs")
REFRESH = os.environ.get("PIECES_REFRESH") == "1"
_PINS, _LOGGED = None, set()


def fix_hash_seed():
    """Re-run the script with PYTHONHASHSEED=0: sets of names iterate in hash order, and a fixed seed makes builds repeat exactly."""
    import sys
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.environ["PYTHONHASHSEED"] = "0"
        os.execv(sys.executable, [sys.executable] + sys.argv)


def pins():
    global _PINS
    if _PINS is None:
        p = os.path.join(INPUTS, "manifest.csv")
        _PINS = {r["input_id"]: r["sha256"] for r in csv.DictReader(open(p))} if os.path.exists(p) else {}
    return _PINS


def canon(d):
    """SHA-256 of a JSON answer in canonical form (sorted keys), so re-serialization does not change it."""
    return hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _use(kind, input_id, source, sha):
    """Log an input to CACHE/used_inputs.tsv (read by freeze_inputs.py) and check it against its pin."""
    pin = pins().get(input_id)
    if pin and pin != sha and not REFRESH:
        raise SystemExit(f"input {input_id} ({source}) differs from its pinned SHA-256; set PIECES_REFRESH=1 to accept a newer source")
    if input_id not in _LOGGED and CACHE:
        _LOGGED.add(input_id)
        with open(os.path.join(CACHE, "used_inputs.tsv"), "a") as fh:
            fh.write(f"{kind}\t{input_id}\t{source}\t{sha}\n")


def cached(key, fn, source=None):
    import gzip
    k = hashlib.md5(key.encode()).hexdigest()
    snap = os.path.join(INPUTS, "snapshot", k + ".json.gz")
    if os.path.exists(snap) and not REFRESH:
        d = json.load(gzip.open(snap, "rt")); _use("query", k, source or key, canon(d)); return d
    p = os.path.join(CACHE, k + ".json")
    d = json.load(open(p)) if os.path.exists(p) else None
    if not d:
        d = fn()
        if d:  # never cache an empty answer (TIGERweb sometimes returns nothing under load)
            json.dump(d, open(p, "w"))
    if d:
        _use("query", k, source or key, canon(d))
    return d


def fetch(url, name=None):
    """A bulk file (zip, csv.gz): downloaded once into CACHE, logged, and checked against its pinned SHA-256."""
    name = name or url.rsplit("/", 1)[1]
    p = os.path.join(CACHE, name)
    if not os.path.exists(p):
        urllib.request.urlretrieve(url, p)
    if (name not in _LOGGED) or pins().get(name):
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for b in iter(lambda: fh.read(1 << 20), b""):
                h.update(b)
        _use("file", name, url, h.hexdigest())
    return p


def arcgis(url, where="1=1", fields="*", geometry=True):
    def run():
        feats, off = [], 0
        while True:
            q = {"where": where, "outFields": fields, "outSR": 4326, "f": "geojson" if geometry else "json",
                 "returnGeometry": str(geometry).lower(), "resultOffset": off, "resultRecordCount": 1000}
            d = _open(url + "/query?" + urllib.parse.urlencode(q))
            fs = d.get("features", [])
            feats += fs if geometry else [{"properties": f["attributes"]} for f in fs]
            if len(fs) < 1000:
                return feats
            off += len(fs)
    return cached(url + where + fields + str(geometry), run, f"{url} where {where}")


def socrata(url):
    return cached(url, lambda: _open(url), url)["features"]


def poly(feats, key):
    return [(key(f["properties"]), make_valid(shape(f["geometry"]))) for f in feats if f.get("geometry")]


CT_REGIONS = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2024/MapServer/82"
_CTY = {}


def cty(g):
    """Current county of a 2020 tract (or block) GEOID: its 2020 county, except in Connecticut, where the Vintage 2025
    county-equivalents are the nine planning regions (2022): the region holding the tract's internal point (as in
    regions/units)."""
    if g[:2] != "09":
        return g[:5]
    _ct_load()
    return _CTY[g[:11]]


def _ct_load():
    if not _CTY:
        regions = poly(arcgis(CT_REGIONS, "STATE='09'", "GEOID,NAME"), lambda p: p["GEOID"])
        for f in arcgis(TG + "6", "STATE='09'", "GEOID,POP100,INTPTLAT,INTPTLON", geometry=False):
            p = f["properties"]; pt = Point(float(p["INTPTLON"]), float(p["INTPTLAT"]))
            hit = [r for r, geo in regions if geo.contains(pt)]
            _CTY[p["GEOID"]] = hit[0] if hit else min(regions, key=lambda r: r[1].distance(pt))[0]


_CT20 = {}


def tract_2020(g):
    """2020 tract GEOID for a tract code from data released since 2022 (ACS), where Connecticut tracts carry their planning
    region as county code with the tract number unchanged."""
    if g[:2] != "09" or int(g[2:5]) < 100:
        return g
    if not _CT20:
        _ct_load()
        _CT20.update({r + t[5:]: t for t, r in _CTY.items()})
    return _CT20.get(g, g)


def county_codes(fips):
    """2020 county codes whose tracts make up a current county (several for a Connecticut planning region)."""
    if fips[:2] != "09" or int(fips[2:]) < 100:
        return [fips]
    _ct_load()
    return sorted({g[:5] for g, r in _CTY.items() if r == fips})


def ccd(fips, name=lambda v: v.replace(" CCD", ""), field="NAME"):
    if fips in county_codes(fips):
        return poly(arcgis(TG + "20", f"STATE='{fips[:2]}' AND COUNTY='{fips[2:]}'"), lambda p: name(p[field]))
    # a Connecticut planning region: the towns (CCDs) of its 2020 counties lying in the region
    region = unary_union([g for r, g in poly(arcgis(CT_REGIONS, "STATE='09'", "GEOID,NAME"), lambda p: p["GEOID"]) if r == fips])
    return [(n, g) for c in county_codes(fips) for n, g in ccd(c, name, field) if region.contains(g.representative_point())]


AG = "https://services.arcgis.com/"
NYC_MERGE = {"BK55": "BK06", "BK56": "BK18", "QN80": "QN03", "QN81": "QN04", "QN82": "QN06", "QN83": "QN10", "QN84": "QN14", "MN64": "MN07", "BX08": "MN12"}


def tracts(fips):
    return [t for c in county_codes(fips) for t in arcgis(TG + "6", f"STATE='{c[:2]}' AND COUNTY='{c[2:]}'", "GEOID,POP100,INTPTLAT,INTPTLON")
            if cty(t["properties"]["GEOID"]) == fips]


def blocks(geoid):
    return arcgis(TG + "10", f"STATE='{geoid[:2]}' AND COUNTY='{geoid[2:5]}' AND TRACT='{geoid[5:]}'", "GEOID,POP100,INTPTLAT,INTPTLON", geometry=False)


CB = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_tract_500k.zip"
_LAND = {}


def land_tracts(counties):
    """Tract land polygons from the 2020 cartographic boundary file (clipped to the shoreline). Needs pyshp."""
    import io, zipfile
    import shapefile
    key = tuple(sorted(counties))
    if key in _LAND:
        return _LAND[key]
    codes = {c for x in counties for c in county_codes(x)}
    p = fetch(CB)
    z = zipfile.ZipFile(p)
    r = shapefile.Reader(shp=io.BytesIO(z.read("cb_2020_us_tract_500k.shp")), dbf=io.BytesIO(z.read("cb_2020_us_tract_500k.dbf")))
    i = [f[0] for f in r.fields[1:]].index("GEOID")
    out = {}
    for sr in r.iterShapeRecords():
        g = sr.record[i]
        if g[:5] in codes and cty(g) in counties and sr.shape.points:
            out[g] = make_valid(shape(sr.shape.__geo_interface__))
    _LAND[key] = out
    return out


def repair(fips, piece_of, scale=1.0, lo=450_000, hi=1_100_000):
    """Contiguity repair (rule 1 check), on land polygons: each piece keeps its most populous part; another populated
    part that touches a different piece on land moves to the piece it borders most. A part touching no other piece on
    land is an island and stays (allowed where the county spans water). Water-only tracts take no part. Returns moves, islands."""
    tr = {t["properties"]["GEOID"]: t for t in tracts(fips)}
    geo = land_tracts({fips})
    pop = {g: t["properties"]["POP100"] for g, t in tr.items()}
    moves, islands = [], []
    size = collections.Counter()
    for g, q in piece_of.items():
        size[q] += pop.get(g, 0) * scale
    for _ in range(5):
        changed = False
        for pc in sorted(set(piece_of.values())):
            mine = [g for g, q in piece_of.items() if q == pc and g in geo]
            u = unary_union([geo[g].buffer(0.0005) for g in mine])
            if u.geom_type == "Polygon":
                continue
            members = [(part, [g for g in mine if part.intersects(geo[g].representative_point())]) for part in u.geoms]
            members.sort(key=lambda m: -sum(pop[g] for g in m[1]))
            for part, tr_in in members[1:]:
                if not tr_in or sum(pop[g] for g in tr_in) == 0:
                    continue
                touch = collections.Counter()
                for g, q in piece_of.items():
                    if q != pc and g in geo and part.intersects(geo[g]):
                        touch[q] += part.intersection(geo[g].buffer(0.0005)).area
                if not touch:
                    islands.append((pc, tr_in, sum(pop[g] for g in tr_in))); continue
                moved = sum(pop[g] for g in tr_in) * scale
                ok = [q for q, _ in touch.most_common() if size[q] + moved <= hi and size[pc] - moved >= lo]
                if not ok:  # reconnect instead: move bridge tracts (touching both this part and the piece's main body)
                    main = members[0][0]
                    bridge = [h for h, q in piece_of.items() if q != pc and h in geo and part.intersects(geo[h]) and main.intersects(geo[h])]
                    done = False
                    for cand in ([[h] for h in bridge] + [bridge]):
                        if not cand:
                            continue
                        donors = collections.Counter()
                        for h in cand:
                            donors[piece_of[h]] += pop[h] * scale
                        if size[pc] + sum(donors.values()) > hi or any(size[q] - v < lo for q, v in donors.items()):
                            continue
                        trial = dict(piece_of); trial.update({h: pc for h in cand})
                        def conn(q):
                            gs = [g for g, x in trial.items() if x == q and g in geo]
                            u2 = unary_union([geo[g].buffer(0.0005) for g in gs])
                            return u2.geom_type == "Polygon" or sum(1 for x in u2.geoms if any(pop[g] for g in gs if x.intersects(geo[g].representative_point()))) <= 1
                        if conn(pc) and all(conn(q) for q in donors):
                            for h in cand:
                                piece_of[h] = pc
                            for q, v in donors.items():
                                size[q] -= v
                            size[pc] += sum(donors.values())
                            moves.append(("bridge", pc, cand, sum(pop[h] for h in cand))); changed = done = True
                            break
                    if not done:
                        print(f"  contiguity NOT repaired (size limits): piece {pc}, {len(tr_in)} tracts ({sum(pop[g] for g in tr_in):,} people)")
                    continue
                tgt = ok[0]
                for g in tr_in:
                    piece_of[g] = tgt
                size[tgt] += moved; size[pc] -= moved
                moves.append((pc, tgt, tr_in, sum(pop[g] for g in tr_in))); changed = True
        if not changed:
            break
    return moves, islands


def main():
    global CACHE
    fix_hash_seed()
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True)
    a = ap.parse_args(); CACHE = a.cache; os.makedirs(CACHE, exist_ok=True)
    groups = json.load(open(os.path.join(HERE, "groups.json")))  # build_groups.py
    registry = list(csv.DictReader(open(os.path.join(HERE, "piece_registry.csv"))))
    pins = list(csv.DictReader(open(os.path.join(HERE, "pins.csv")))) if os.path.exists(os.path.join(HERE, "pins.csv")) else []
    out, split_rows, summary = [], [], []
    for c in groups:
        fips, name = c["fips"], c["county"]
        tr = {t["properties"]["GEOID"]: t["properties"] for t in tracts(fips)}
        pop = {g: p["POP100"] for g, p in tr.items()}
        piece_of = {g: v[0] for g, v in c["assign"].items()}
        how = {g: v[1] for g, v in c["assign"].items()}; share = {g: v[2] for g, v in c["assign"].items()}
        pt = {g: (float(p["INTPTLON"]), float(p["INTPTLAT"])) for g, p in tr.items()}
        for g in tr:  # water-only tracts: piece of the nearest assigned tract
            if g not in piece_of:
                near = min(piece_of, key=lambda h: (pt[h][0] - pt[g][0]) ** 2 + (pt[h][1] - pt[g][1]) ** 2)
                piece_of[g] = piece_of[near]; how[g] = "internal_point"; share[g] = 1.0
        p25 = sum(p["pop2025_est"] for p in c["pieces"]); scale0 = p25 / sum(pop.values())
        moves, islands = repair(fips, piece_of, scale0)
        for m in moves:
            for g in m[2]:
                how[g] = "contiguity"
            print(f"  contiguity: {len(m[2])} tracts ({m[3]:,} people) piece {m[0]} -> {m[1]}")
        for isl in islands:
            print(f"  island kept: piece {isl[0]} {len(isl[1])} tracts ({isl[2]:,} people)")
        # stable piece IDs (piece_registry.csv): a piece takes the ID and name of the registry anchor tract it holds
        reg = [r for r in registry if r["county_fips"] == fips and r["status"] == "active"]
        pid, pname = {}, {}
        for r in sorted(reg, key=lambda r: r["piece_id"]):
            i = piece_of.get(r["anchor_tract"])
            if i is None or i in pid:
                r["status"] = "retired"; r["note"] = f"retired in {VERSION}: anchor tract no longer marks its own piece"
                print(f"  REGISTRY: {r['piece_id']} retired ({r['piece_name']})"); continue
            pid[i] = r["piece_id"]; pname[i] = r["piece_name"]
        used = [int(r["piece_id"][-2:]) for r in registry if r["county_fips"] == fips]
        for i in sorted(set(piece_of.values()) - set(pid), key=lambda i: -sum(pop[g] for g, j in piece_of.items() if j == i)):
            n = max(used, default=0) + 1; used.append(n); pid[i] = f"{fips}-{n:02d}"; pname[i] = c["pieces"][i]["name"]
            anchor = max((g for g, j in piece_of.items() if j == i), key=lambda g: pop[g])
            registry.append({"piece_id": pid[i], "county_fips": fips, "anchor_tract": anchor, "piece_name": pname[i],
                             "status": "active", "since_version": VERSION, "note": "new piece: name it"})
            print(f"  REGISTRY: new piece {pid[i]} (anchor {anchor}); give it a region name")
        # manual pins (pins.csv): tract -> piece_id, applied after grouping and contiguity repair
        byid = {v: i for i, v in pid.items()}
        for r in pins:
            if cty(r["tract_geoid"]) == fips:
                if r["piece_id"] not in byid:
                    raise SystemExit(f"pins.csv: {r['tract_geoid']} -> unknown piece {r['piece_id']}")
                piece_of[r["tract_geoid"]] = byid[r["piece_id"]]; how[r["tract_geoid"]] = "pinned"; share[r["tract_geoid"]] = 1.0
        tot = collections.Counter()
        for g, i in piece_of.items():
            tot[i] += pop[g]
        scale = sum(p["pop2025_est"] for p in c["pieces"]) / max(1, sum(p["pop2020"] for p in c["pieces"]))
        p25 = None
        if os.path.exists(os.path.join(HERE, "tract_pop2025.csv")):  # sub-county 2025 estimates (release 1.4 on)
            import build_tract_estimates as te
            p25 = te.piece_pop2025({g: pid[i] for g, i in piece_of.items()})
        order = sorted(tot, key=lambda i: pid[i])
        comp = {i: c["pieces"][i]["name"] for i in order}
        src = c["source_id"] if c["method"] in ("official", "whole") else "lodes_2024_louvain"
        for g in tr:
            i = piece_of[g]
            out.append({"tract_geoid": g, "county_fips": fips, "piece_id": pid[i], "piece_name": pname[i],
                        "method": c["method"], "source_id": src, "assign": how[g], "pop2020_share": share[g]})
        for g, i, n in c["splits"]:
            split_rows.append({"tract_geoid": g, "county_fips": fips, "piece_id": pid[i], "piece_name": pname[i], "pop2020": n})
        for i in order:
            summary.append((pid[i], fips, name, pname[i], comp[i], c["method"], tot[i], p25[pid[i]] if p25 else round(tot[i] * scale)))
        print(fips, name, len(tr), "tracts", dict(collections.Counter(how.values())), "pieces", len(order), flush=True)
    cols = ["tract_geoid", "county_fips", "piece_id", "piece_name", "method", "source_id", "assign", "pop2020_share"]
    with open(os.path.join(HERE, "crosswalk_tract_piece.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, cols); w.writeheader(); [w.writerow(r) for r in sorted(out, key=lambda r: r["tract_geoid"])]
    with open(os.path.join(HERE, "split_tracts.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, ["tract_geoid", "county_fips", "piece_id", "piece_name", "pop2020"]); w.writeheader()
        w.writerows(sorted(split_rows, key=lambda r: (r["tract_geoid"], r["piece_id"])))
    with open(os.path.join(HERE, "piece_registry.csv"), "w", newline="") as fh:  # new and retired IDs are recorded
        w = csv.DictWriter(fh, list(registry[0])); w.writeheader(); w.writerows(sorted(registry, key=lambda r: r["piece_id"]))
    with open(os.path.join(HERE, "pieces_summary.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["piece_id", "county_fips", "county", "piece_name", "piece_components", "method", "pop2020", "pop2025_est"]); w.writerows(sorted(summary))


if __name__ == "__main__":
    main()
