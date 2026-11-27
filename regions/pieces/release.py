"""Freeze a numbered geography release (docs/specs/county-pieces.md, Versions).

Runs check_pieces.py (a release needs every check to pass), then writes releases/<version>/:
  crosswalk_tract_piece.csv, crosswalk_tract_subarea.csv, piece_registry.csv   the release's tract assignments and IDs
  release.json   version, date, git commit, build parameters, counts, SHA-256 of every output and of inputs/manifest.csv
  changes.csv    against the previous release: every tract whose piece or subarea changed, with 2020 residents
                 (with a piece-level summary in release.json: IDs added and retired, residents moved)
The version must match the VERSION file, which the build stamps on new registry entries. Bump VERSION before the next
build that is meant to change boundaries.

usage: python3 release.py --cache DIR --version 1.0
"""
import argparse, collections, csv, datetime, hashlib, json, os, shutil, subprocess, sys

import build_groups as bg

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUTS = ["groups.json", "crosswalk_tract_piece.csv", "split_tracts.csv", "pieces_summary.csv", "pieces.geojson",
           "tract_demographics.csv", "piece_demographics.csv", "crosswalk_tract_subarea.csv", "subareas_summary.csv",
           "subareas.geojson", "piece_registry.csv", "pins.csv", "inputs/manifest.csv"]
FROZEN = ["crosswalk_tract_piece.csv", "crosswalk_tract_subarea.csv", "piece_registry.csv"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def vkey(v):
    return tuple(int(x) for x in v.split("."))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True); ap.add_argument("--version", required=True)
    a = ap.parse_args()
    if open(os.path.join(HERE, "VERSION")).read().strip() != a.version:
        raise SystemExit(f"--version {a.version} does not match the VERSION file")
    rel = os.path.join(HERE, "releases"); out = os.path.join(rel, a.version)
    if os.path.exists(out):
        raise SystemExit(f"release {a.version} exists; releases are never overwritten")
    chk = subprocess.run([sys.executable, os.path.join(HERE, "check_pieces.py"), "--cache", a.cache], capture_output=True, text=True)
    print(chk.stdout)
    if chk.returncode:
        raise SystemExit("checks failed; no release written")
    prev = sorted((d for d in os.listdir(rel) if d[0].isdigit()), key=vkey) if os.path.isdir(rel) else []
    prev = prev[-1] if prev else None
    os.makedirs(out)
    for f in FROZEN:
        shutil.copy(os.path.join(HERE, f), os.path.join(out, f))
    rd = lambda p: {r["tract_geoid"]: r for r in csv.DictReader(open(p))}
    summary = {}
    if prev:
        po, pn = rd(os.path.join(rel, prev, "crosswalk_tract_piece.csv")), rd(os.path.join(HERE, "crosswalk_tract_piece.csv"))
        so, sn = rd(os.path.join(rel, prev, "crosswalk_tract_subarea.csv")), rd(os.path.join(HERE, "crosswalk_tract_subarea.csv"))
        pop = {r["tract_geoid"]: int(r["total"]) for r in csv.DictReader(open(os.path.join(HERE, "tract_demographics.csv")))}
        rows = []
        for g in sorted(set(po) | set(pn)):
            a0, a1 = po.get(g, {}).get("piece_id", ""), pn.get(g, {}).get("piece_id", "")
            b0, b1 = so.get(g, {}).get("subarea_id", ""), sn.get(g, {}).get("subarea_id", "")
            if a0 != a1 or b0 != b1:
                rows.append({"tract_geoid": g, "piece_from": a0, "piece_to": a1, "subarea_from": b0, "subarea_to": b1, "pop2020": pop.get(g, 0)})
        with open(os.path.join(out, "changes.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, ["tract_geoid", "piece_from", "piece_to", "subarea_from", "subarea_to", "pop2020"]); w.writeheader(); w.writerows(rows)
        ids0, ids1 = {r["piece_id"] for r in po.values()}, {r["piece_id"] for r in pn.values()}
        moved = collections.Counter()
        for r in rows:
            if r["piece_from"] != r["piece_to"]:
                moved[(r["piece_from"], r["piece_to"])] += r["pop2020"]
        summary = {"previous": prev, "tracts_changed_piece": sum(1 for r in rows if r["piece_from"] != r["piece_to"]),
                   "tracts_changed_subarea": sum(1 for r in rows if r["subarea_from"] != r["subarea_to"]),
                   "residents_moved_2020": sum(moved.values()), "pieces_added": sorted(ids1 - ids0), "pieces_retired": sorted(ids0 - ids1),
                   "largest_moves": [{"from": k[0], "to": k[1], "pop2020": v} for k, v in moved.most_common(10)]}
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = ""
    xw = list(csv.DictReader(open(os.path.join(HERE, "crosswalk_tract_piece.csv"))))
    info = {"version": a.version, "released": datetime.date.today().isoformat(), "git_commit_of_build_code": commit,
            "parameters": {"TARGET": bg.TARGET, "LO": bg.LO, "HI": bg.HI, "MIN_COUNTY": bg.MIN_COUNTY, "MU": bg.MU,
                           "PUMA_WEIGHT": bg.PUMA_WEIGHT, "NECK": bg.NECK, "CORE_DENSITY": bg.CORE_DENSITY, "CORE_JOBS": bg.CORE_JOBS,
                           "WHOLE": sorted(bg.WHOLE), "SPLIT": bg.SPLIT},
            "counts": {"counties": len({r["county_fips"] for r in xw}), "tracts": len(xw),
                       "pieces": len({r["piece_id"] for r in xw}),
                       "subareas": len({r["subarea_id"] for r in csv.DictReader(open(os.path.join(HERE, "crosswalk_tract_subarea.csv")))})},
            "checks": chk.stdout.strip().splitlines(),
            "sha256": {f: sha(os.path.join(HERE, f)) for f in OUTPUTS if os.path.exists(os.path.join(HERE, f))},
            "changes": summary}
    json.dump(info, open(os.path.join(out, "release.json"), "w"), indent=1)
    print(f"release {a.version} written to {out}" + (f"; {summary['tracts_changed_piece']} tracts changed piece since {prev}" if prev else " (first release)"))


if __name__ == "__main__":
    main()
