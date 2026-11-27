"""Freeze the inputs of the last build (docs/specs/county-pieces.md, rule 6).

Reads CACHE/used_inputs.tsv, written by the build scripts as they read each input, and writes inputs/manifest.csv:
  input_id, kind (query | file), frozen (snapshot | sha256), source, publisher, license, retrieved, last_edit, bytes, sha256
Query answers from local-government hosts (boundary layers that can change without notice) are copied, gzipped, to
inputs/snapshot/<input_id>.json.gz; the build reads them before any cache or network. Layers whose terms discourage
redistribution (HASH_ONLY: SanGIS) are pinned by SHA-256 only, like the Census inputs, and never copied. Census and LEHD inputs (TIGERweb
2020, cartographic boundaries, PL 94-171, Vintage 2025 estimates, LODES) are fixed releases: they are not copied, but their
SHA-256 is pinned, and the build stops if a fresh download differs (PIECES_REFRESH=1 overrides).
last_edit is read from the layer's own metadata (ArcGIS editingInfo.lastEditDate, Socrata rowsUpdatedAt).

usage: python3 freeze_inputs.py --cache DIR
"""
import argparse, csv, datetime, gzip, json, os, urllib.parse

import build_crosswalk as bx

HERE = os.path.dirname(os.path.abspath(__file__))
CENSUS = ("tigerweb.geo.census.gov", "www2.census.gov", "lehd.ces.census.gov")
# local layers whose terms discourage redistribution: pinned by SHA-256 only, never copied into the repository
HASH_ONLY = ("geo.sandag.org",)  # SanGIS end-user agreement
# publisher and license as stated (recorded in the spec's county sections)
SOURCES = [
    ("RmCCgQtiZLDCtblq", "LA County Department of Public Health", "not stated on the layer"),
    ("data.cityofchicago.org", "City of Chicago", "City of Chicago Terms of Use (not opened)"),
    ("datacatalog.cookcountyil.gov", "Cook County Department of Public Health", "not stated"),
    ("geo.sandag.org", "SANDAG / SanGIS", "SanGIS end-user agreement: as is; redistribution discouraged, not prohibited; credit SanGIS"),
    ("8Pc9XBTAsYuxx9Ny", "Miami-Dade County", "as is disclaimer"),
    ("data.cityofnewyork.us", "NYC Department of City Planning", "none stated (credit DCP)"),
    ("Ej0PsM5Aw677QF1W", "Public Health - Seattle & King County", "King County GIS terms: copying and distribution allowed; sale needs agreement"),
    ("i2dkYWmb4wHvYPda", "Metropolitan Transportation Commission", "no license text"),
    ("YBp5dUuxCMd8W1EI", "SACOG", "not stated"),
    ("fLeGjb7u4uXqeF9q", "Philadelphia City Planning Commission", "as is disclaimer with hold-harmless clause"),
    ("tigerweb.geo.census.gov", "U.S. Census Bureau (TIGERweb, 2020 Census)", "public domain (U.S. Government work)"),
    ("www2.census.gov", "U.S. Census Bureau", "public domain (U.S. Government work)"),
    ("lehd.ces.census.gov", "U.S. Census Bureau, LEHD (LODES 8)", "public domain (U.S. Government work)"),
    ("data.bls.gov", "U.S. Bureau of Labor Statistics (QCEW)", "public domain (U.S. Government work)"),
    ("apps.bea.gov", "U.S. Bureau of Economic Analysis", "public domain (U.S. Government work)"),
]


def describe(source):
    for key, pub, lic in SOURCES:
        if key in source:
            return pub, lic
    return "unknown", "not recorded"


def last_edit(source):
    """Edit date from the layer's metadata, where the host publishes one."""
    url = source.split(" ")[0]
    try:
        if "/FeatureServer/" in url or "/MapServer/" in url:
            if "tigerweb" in url:
                return "2020 Census vintage"
            ms = bx._open(url + "?f=json").get("editingInfo", {}).get("lastEditDate")
            return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime("%Y-%m-%d") if ms else ""
        u = urllib.parse.urlparse(url)
        if u.path.startswith("/resource/"):
            vid = u.path.split("/")[2].split(".")[0]
            ts = bx._open(f"{u.scheme}://{u.netloc}/api/views/{vid}.json").get("rowsUpdatedAt")
            return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d") if ts else ""
    except Exception as e:  # metadata is informative only
        return f"not read ({type(e).__name__})"
    return ""


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True)
    a = ap.parse_args(); bx.CACHE = a.cache
    used = {}
    for line in open(os.path.join(a.cache, "used_inputs.tsv")):
        kind, iid, source, sha = line.rstrip("\n").split("\t")
        used[iid] = (kind, source, sha)
    snapdir = os.path.join(HERE, "inputs", "snapshot"); os.makedirs(snapdir, exist_ok=True)
    rows, meta = [], {}
    for iid, (kind, source, sha) in sorted(used.items(), key=lambda x: (x[1][0], x[1][1])):
        url = source.split(" ")[0]; host = urllib.parse.urlparse(url).netloc
        pub, lic = describe(source)
        if kind == "file":
            p = os.path.join(a.cache, iid); frozen = "sha256"; size = os.path.getsize(p)
            retrieved = datetime.date.fromtimestamp(os.path.getmtime(p)).isoformat(); edit = ""
        else:
            snap = os.path.join(snapdir, iid + ".json.gz"); cache = os.path.join(a.cache, iid + ".json")
            src = cache if os.path.exists(cache) else snap
            retrieved = datetime.date.fromtimestamp(os.path.getmtime(src)).isoformat()
            if host in CENSUS:
                frozen = "sha256"; size = os.path.getsize(src); edit = "2020 Census vintage" if "tigerweb" in host else ""
            elif host in HASH_ONLY:
                frozen = "sha256"; size = os.path.getsize(src)
                layer = url.split("/query")[0]
                if layer not in meta:
                    meta[layer] = last_edit(source)
                edit = meta[layer]
            else:
                frozen = "snapshot"
                if not os.path.exists(snap):
                    d = json.load(open(cache))
                    with gzip.GzipFile(snap, "wb", mtime=0) as fh:  # deterministic bytes
                        fh.write(json.dumps(d, sort_keys=True, separators=(",", ":")).encode())
                size = os.path.getsize(snap)
                layer = url.split("/query")[0]
                if layer not in meta:
                    meta[layer] = last_edit(source)
                edit = meta[layer]
        rows.append({"input_id": iid, "kind": kind, "frozen": frozen, "source": source, "publisher": pub, "license": lic,
                     "retrieved": retrieved, "last_edit": edit, "bytes": size, "sha256": sha})
    # remove snapshots the build no longer reads
    keep = {r["input_id"] + ".json.gz" for r in rows if r["frozen"] == "snapshot"}
    for f in os.listdir(snapdir):
        if f not in keep:
            os.remove(os.path.join(snapdir, f))
    with open(os.path.join(HERE, "inputs", "manifest.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0])); w.writeheader(); w.writerows(rows)
    n = {}
    for r in rows:
        n[(r["kind"], r["frozen"])] = n.get((r["kind"], r["frozen"]), 0) + 1
    print("inputs", len(rows), n, "snapshot MB", round(sum(os.path.getsize(os.path.join(snapdir, f)) for f in os.listdir(snapdir)) / 1e6, 1))


if __name__ == "__main__":
    main()
