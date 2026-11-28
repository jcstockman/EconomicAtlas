"""Light shapes of every atlas unit for the atlas map's United States view (docs/specs/atlas-indicators.md, The atlas map).

Reads regions/units/atlas_units.geojson (8.6 MB) and the metros crosswalk, and writes next to this script:
  us_units.geojson    every unit with id (unit_id), name, state (postal code), county (county FIPS), piece (1 for a county
                      piece) and cbsa (the covered metro area or region, if any)
  us_states.geojson   the borders between states (lines), for the map's state lines
Plain GeoJSON, so the map needs no TopoJSON library. Shapes are simplified with mapshaper (topology-aware Visvalingam, so
neighbours keep shared borders and no gaps open; every unit keeps a shape), with coordinates rounded to 0.001 degrees.
mapshaper is a Node tool: pass its path with --mapshaper (npm install mapshaper@0.6.102).
usage: python3 build_us_shapes.py --mapshaper PATH [--keep 0.08]
"""
import argparse, csv, json, os, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, "..")
POSTAL = {"01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
          "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
          "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
          "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
          "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
          "56": "WY", "72": "PR"}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--mapshaper", required=True); ap.add_argument("--keep", default="0.08")
    a = ap.parse_args()
    cbsa = {r["unit_id"]: r["cbsa"] for r in csv.DictReader(open(os.path.join(R, "metros", "crosswalk_unit_metro.csv")))}
    gj = json.load(open(os.path.join(R, "units", "atlas_units.geojson")))
    feats = []
    for f in gj["features"]:
        p = f["properties"]; k = p["unit_id"]
        feats.append({"type": "Feature", "geometry": f["geometry"],
                      "properties": {"id": k, "name": p["unit_name"], "state": POSTAL[p["state_fips"]], "county": p["county_fips"],
                                     "piece": 1 if p["unit_type"] == "piece" else 0, "cbsa": cbsa.get(k, "")}})
    out, outs = os.path.join(HERE, "us_units.geojson"), os.path.join(HERE, "us_states.geojson")
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "units.json")
        json.dump({"type": "FeatureCollection", "features": feats}, open(src, "w"))
        subprocess.run([a.mapshaper, "-i", src, "snap", "name=units", "-simplify", a.keep, "keep-shapes", "planar",
                        "-o", out, "format=geojson", "precision=0.001",
                        "-innerlines", "where=A.state != B.state", "+", "name=states",
                        "-o", outs, "target=states", "format=geojson", "precision=0.001"], check=True)
    n = len(json.load(open(out))["features"])
    print(f"us_units.geojson: {n:,} units, {os.path.getsize(out) / 1e6:.2f} MB; us_states.geojson {os.path.getsize(outs) / 1e6:.2f} MB (keep {a.keep})")
    if n != len(feats):
        raise SystemExit(f"{len(feats) - n} units lost")


if __name__ == "__main__":
    main()
