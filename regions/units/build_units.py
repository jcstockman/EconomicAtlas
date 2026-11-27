"""All-US atlas units (docs/specs/atlas-units.md): every 2020 census tract in the 50 states and DC mapped to one unit.

A unit is a county piece (regions/pieces, a frozen release) in the counties with 1.0M+ residents, and a whole county
everywhere else. Counties are the county-equivalents of the Census Vintage 2025 estimates, so Connecticut uses its nine
planning regions (2022): each 2020 tract goes to the planning region holding its internal point (tracts nest in towns,
towns in regions). Everything else keeps the tract's own 2020 county.

Inputs (through the pieces loaders: logged, hash-pinned or snapshotted; see regions/pieces/freeze_inputs.py):
  TIGERweb Census 2020 tracts (GEOID, POP100, internal point), all states
  TIGERweb ACS 2024 counties, Connecticut planning regions
  co-est2025-alldata.csv (Vintage 2025), cb_2024_us_county_500k.zip (county shapes), pieces release <PIECES>
Writes next to this script:
  crosswalk_tract_unit.csv  tract_geoid, county_fips_2020, county_fips, unit_id, unit_type
  atlas_units.csv           unit_id, unit_type (piece | county), county_fips, county, state_fips, state, unit_name,
                            pop2020, pop2025_est, tracts, pieces_release
  atlas_units.geojson       pieces from the release's pieces.geojson, counties from the 2024 cartographic file
pop2020 is the 2020 census count (tracts). pop2025_est is the county's Vintage 2025 estimate; a piece takes its 2020 share
of its county, rounded per piece exactly as in regions/pieces (so a split county's pieces can sum to within one resident
per piece of its estimate).

usage: python3 build_units.py --cache DIR [--pieces 1.0.1]
"""
import argparse, collections, csv, io, json, os, sys, time, zipfile

from shapely.geometry import Point, mapping, shape
from shapely.strtree import STRtree
from shapely.validation import make_valid

HERE = os.path.dirname(os.path.abspath(__file__))
PIECES = os.path.join(HERE, "..", "pieces")
sys.path.insert(0, PIECES)
import build_crosswalk as bx  # noqa: E402
import build_geojson as bgj  # noqa: E402

CT_REGIONS = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2024/MapServer/82"
COUNTY_SHAPES = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_county_500k.zip"
EST = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/counties/totals/co-est2025-alldata.csv"
SIMPLIFY = 0.002  # degrees (~200 m) for county shapes; pieces keep their own simplification


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True); ap.add_argument("--pieces")
    a = ap.parse_args(); bx.CACHE = a.cache; bx.fix_hash_seed()
    rel_dir = os.path.join(PIECES, "releases")
    release = a.pieces or sorted(os.listdir(rel_dir), key=lambda v: tuple(int(x) for x in v.split(".")))[-1]
    rel = os.path.join(rel_dir, release)

    counties = {}
    for r in csv.DictReader(open(bx.fetch(EST), encoding="latin-1")):
        if r["SUMLEV"] == "050":
            counties[r["STATE"] + r["COUNTY"]] = {"county": r["CTYNAME"], "state": r["STNAME"], "pop2025": int(r["POPESTIMATE2025"])}
    states = sorted({c[:2] for c in counties})

    # tracts, all states
    tracts = {}
    for st in states:
        for attempt in range(4):  # TIGERweb sometimes answers empty under load (never cached); retry, then stop
            fs = bx.arcgis(bx.TG + "6", f"STATE='{st}'", "GEOID,POP100,INTPTLAT,INTPTLON", geometry=False)
            if fs:
                break
            time.sleep(20)
        else:
            raise SystemExit(f"no tracts returned for state {st}")
        for f in fs:
            p = f["properties"]
            tracts[p["GEOID"]] = {"pop": p["POP100"], "pt": Point(float(p["INTPTLON"]), float(p["INTPTLAT"]))}
    # current county of each tract (Connecticut: planning region by internal point)
    regions = bx.poly(bx.arcgis(CT_REGIONS, "STATE='09'", "GEOID,NAME"), lambda p: p["GEOID"])
    rtree = STRtree([g for _, g in regions])
    county_of = {}
    for g, t in tracts.items():
        if g[:2] == "09":
            hit = [regions[i][0] for i in rtree.query(t["pt"]) if regions[i][1].contains(t["pt"])]
            county_of[g] = hit[0] if hit else min(regions, key=lambda r: r[1].distance(t["pt"]))[0]
        else:
            county_of[g] = g[:5]
    unknown = {c for c in county_of.values() if c not in counties}
    empty = {c for c in counties if c not in set(county_of.values())}
    if unknown or empty:
        raise SystemExit(f"county mismatch: tracts in counties not in Vintage 2025 {sorted(unknown)[:10]}; counties without tracts {sorted(empty)[:10]}")

    # pieces (frozen release)
    pxw = list(csv.DictReader(open(os.path.join(rel, "crosswalk_tract_piece.csv"))))
    piece_of = {r["tract_geoid"]: r["piece_id"] for r in pxw}
    pname = {r["piece_id"]: r["piece_name"] for r in csv.DictReader(open(os.path.join(rel, "piece_registry.csv"))) if r["status"] == "active"}
    missing = set(piece_of) - set(tracts)
    if missing:
        raise SystemExit(f"{len(missing)} piece tracts not among 2020 tracts")
    piece_counties = {r["county_fips"] for r in pxw}  # current counties (a Connecticut planning region, not the 2020 county)

    unit_of = {g: (piece_of[g] if county_of[g] in piece_counties else county_of[g]) for g in tracts}
    for g in tracts:
        if county_of[g] in piece_counties and g not in piece_of:
            raise SystemExit(f"tract {g} in a piece county but not in the pieces crosswalk")

    # unit table
    cpop = collections.Counter(); upop = collections.Counter(); ntr = collections.Counter()
    for g, t in tracts.items():
        cpop[county_of[g]] += t["pop"]; upop[unit_of[g]] += t["pop"]; ntr[unit_of[g]] += 1
    units = []
    for u in sorted(upop):
        c = u[:5]; is_piece = "-" in u
        share = upop[u] / cpop[c] if cpop[c] else 1.0
        units.append({"unit_id": u, "unit_type": "piece" if is_piece else "county", "county_fips": c,
                      "county": counties[c]["county"], "state_fips": c[:2], "state": counties[c]["state"],
                      "unit_name": pname[u] if is_piece else counties[c]["county"], "pop2020": upop[u],
                      "pop2025_est": round(counties[c]["pop2025"] * share), "tracts": ntr[u], "pieces_release": release})
    with open(os.path.join(HERE, "crosswalk_tract_unit.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["tract_geoid", "county_fips_2020", "county_fips", "unit_id", "unit_type"])
        for g in sorted(tracts):
            w.writerow([g, g[:5], county_of[g], unit_of[g], "piece" if "-" in unit_of[g] else "county"])
    with open(os.path.join(HERE, "atlas_units.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, list(units[0])); w.writeheader(); w.writerows(units)

    # geometry: release pieces + 2024 cartographic counties
    import shapefile
    z = zipfile.ZipFile(bx.fetch(COUNTY_SHAPES))
    r = shapefile.Reader(shp=io.BytesIO(z.read("cb_2024_us_county_500k.shp")), dbf=io.BytesIO(z.read("cb_2024_us_county_500k.dbf")))
    gi = [f[0] for f in r.fields[1:]].index("GEOID")
    shp = {}
    for sr in r.iterShapeRecords():
        g = sr.record[gi]
        if g in counties and g not in piece_counties and sr.shape.points:
            shp[g] = make_valid(shape(sr.shape.__geo_interface__)).simplify(SIMPLIFY, preserve_topology=True)
    pieces_geo = {f["properties"]["piece_id"]: f["geometry"] for f in json.load(open(os.path.join(PIECES, "pieces.geojson")))["features"]}
    feats = []
    for u in units:
        geom = pieces_geo.get(u["unit_id"]) if u["unit_type"] == "piece" else (bgj.rnd(mapping(shp[u["unit_id"]])) if u["unit_id"] in shp else None)
        if geom is None:
            raise SystemExit(f"no shape for unit {u['unit_id']}")
        feats.append({"type": "Feature", "properties": u, "geometry": geom})
    json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(HERE, "atlas_units.geojson"), "w"), separators=(",", ":"))

    n = collections.Counter(u["unit_type"] for u in units)
    print(f"tracts {len(tracts):,}  units {len(units):,} {dict(n)}  counties {len(counties):,} ({len(piece_counties)} split into pieces)  "
          f"pop2020 {sum(upop.values()):,}  pop2025 {sum(u['pop2025_est'] for u in units):,}  pieces release {release}  "
          f"geojson MB {os.path.getsize(os.path.join(HERE, 'atlas_units.geojson')) / 1e6:.1f}")


if __name__ == "__main__":
    main()
