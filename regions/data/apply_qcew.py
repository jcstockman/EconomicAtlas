"""QCEW 2024 annual averages for every atlas unit (docs/specs/allocation-keys.md).

County units take BLS's published figures. In the split counties each county figure is shared among its pieces by
its allocation key (regions/keys/keys.csv, measure_keys.csv):
  ownership totals   federal: jobs_federal; state, local: jobs_state_local; private: sum of its sectors
  private sectors    employment jobs_private_<s>, wages wages_private_<s>, establishments est_<s> (fallback: the total key)
  withheld cells     where BLS withholds a county cell, the county's residual (parent total minus the published cells)
                     is shared by the keys of the withheld cells; no piece value is published for a withheld cell
Published table (decision 5): totals, ownership and the 11 private supersectors for all units. Sector detail for pieces
is written to a separate internal file.

Writes next to this script:
  qcew_2024_units.csv         unit_id, unit_type, county_fips, own_code, industry_code, level, estabs, emplvl,
                              total_wages, avg_weekly_wage, method (published | allocated | withheld)
  qcew_2024_pieces_detail.csv internal: piece values by private NAICS sector, including shares of withheld residuals
usage: python3 apply_qcew.py --cache DIR
"""
import argparse, collections, csv, io, os, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pieces"))
import build_crosswalk as bx  # noqa: E402

SINGLEFILE = "https://data.bls.gov/cew/data/files/2024/csv/2024_annual_singlefile.zip"
SUPERSECTORS = {"1011": ["11", "21"], "1012": ["23"], "1013": ["31-33"], "1021": ["22", "42", "44-45", "48-49"], "1022": ["51"],
                "1023": ["52", "53"], "1024": ["54", "55", "56"], "1025": ["61", "62"], "1026": ["71", "72"], "1027": ["81"],
                "1028": ["92"], "1029": ["99"]}
MEASURES = ("estabs", "emplvl", "total_wages")
COL = {"estabs": "annual_avg_estabs", "emplvl": "annual_avg_emplvl", "total_wages": "total_annual_wages"}


def load_qcew(counties):
    """{(area, own, industry): {measure: value or None if withheld}} for county totals, ownership, supersector, sector."""
    z = zipfile.ZipFile(bx.fetch(SINGLEFILE))
    out = {}
    with z.open(z.namelist()[0]) as fh:
        for r in csv.DictReader(io.TextIOWrapper(fh)):
            if r["area_fips"] in counties and r["agglvl_code"] in ("70", "71", "73", "74"):
                withheld = r["disclosure_code"] == "N"
                out[(r["area_fips"], r["own_code"], r["industry_code"])] = {m: None if withheld else float(r[COL[m]]) for m in MEASURES}
    return out


def split_value(total, parts, keys):
    """Share a county total among pieces. parts: {cell: value or None}; keys: {cell: {piece: key value}}.
    Published cells are split by their own key; the residual (total - published cells) by the summed keys of the withheld
    cells. Returns ({cell: {piece: value}}, {piece: residual share}) ."""
    out, resid = {}, collections.Counter()
    known = sum(v for v in parts.values() if v is not None)
    rest = max(0.0, (total or 0) - known)
    wk = collections.Counter()
    for cell, v in parts.items():
        k = keys[cell]; tot = sum(k.values())
        if v is None:
            for p, x in k.items():
                wk[p] += x
            continue
        out[cell] = {p: v * x / tot for p, x in k.items()} if tot else None
    wt = sum(wk.values())
    for p, x in wk.items():
        resid[p] = rest * x / wt if wt else 0.0
    return out, resid


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True)
    a = ap.parse_args(); bx.CACHE = a.cache; bx.fix_hash_seed()
    units = list(csv.DictReader(open(os.path.join(HERE, "..", "units", "atlas_units.csv"))))
    counties = {u["county_fips"] for u in units}
    q = load_qcew(counties)
    pieces_of = collections.defaultdict(list)
    for u in units:
        if u["unit_type"] == "piece":
            pieces_of[u["county_fips"]].append(u["unit_id"])
    split = {c for c, ps in pieces_of.items() if len(ps) > 1}
    key = collections.defaultdict(dict)
    for r in csv.DictReader(open(os.path.join(HERE, "..", "keys", "keys.csv"))):
        key[r["key_id"]][r["piece_id"]] = float(r["value"])
    sectors = [i for (c, o, i) in q if o == "5" and len(i) <= 5 and i not in ("10",) and not i.startswith("10")]
    sectors = sorted(set(sectors))

    def k(name, c, fallback):
        d = {p: key.get(name, {}).get(p, 0.0) for p in pieces_of[c]}
        return d if sum(d.values()) > 0 else {p: key[fallback].get(p, 0.0) for p in pieces_of[c]}

    rows, detail = [], []
    def emit(unit, utype, c, own, ind, level, vals, method):
        e, w = vals.get("emplvl"), vals.get("total_wages")
        rows.append({"unit_id": unit, "unit_type": utype, "county_fips": c, "own_code": own, "industry_code": ind, "level": level,
                     **{m: ("" if vals.get(m) is None else round(vals[m], 1 if method == "allocated" else 0)) for m in MEASURES},
                     "avg_weekly_wage": round(w / e / 52) if e and w is not None else "", "method": method})

    missing = []
    for u in units:
        c = u["county_fips"]
        if c in split:
            continue
        uid, ut = u["unit_id"], u["unit_type"]
        if (c, "0", "10") not in q:
            missing.append(c); continue
        emit(uid, ut, c, "0", "10", "total", q[(c, "0", "10")], "published")
        for own in ("1", "2", "3", "5"):
            if (c, own, "10") in q:
                v = q[(c, own, "10")]
                emit(uid, ut, c, own, "10", "ownership", v, "withheld" if v["emplvl"] is None else "published")
        for ss in SUPERSECTORS:
            if (c, "5", ss) in q:
                v = q[(c, "5", ss)]
                emit(uid, ut, c, "5", ss, "supersector", v, "withheld" if v["emplvl"] is None else "published")

    for c in sorted(split):
        ps = pieces_of[c]
        alloc = {m: collections.defaultdict(collections.Counter) for m in MEASURES}  # m -> (own, ind) -> piece -> value
        for m in MEASURES:
            # private sectors (internal detail), residual over withheld sectors
            kname = {"emplvl": "jobs_private_{}", "total_wages": "wages_private_{}", "estabs": "est_{}"}[m]
            fb = {"emplvl": "jobs_private_total", "total_wages": "wages_private_total", "estabs": "est_total"}[m]
            parts = {s: q[(c, "5", s)][m] for s in sectors if (c, "5", s) in q}
            keys_s = {s: k(kname.format(s) if s != "99" else fb, c, fb) for s in parts}
            priv = q.get((c, "5", "10"), {}).get(m)
            out, resid = split_value(priv, parts, keys_s)
            for s, d in out.items():
                for p, v in (d or {}).items():
                    alloc[m][("5", s)][p] = v
            for p, v in resid.items():
                alloc[m][("5", "withheld")][p] = v
            # private supersectors (published): split with summed sector keys where the county cell is published
            for ss, secs in SUPERSECTORS.items():
                if (c, "5", ss) in q and q[(c, "5", ss)][m] is not None:
                    kk = collections.Counter()
                    for s in secs:
                        for p, v in k(kname.format(s) if s != "99" else fb, c, fb).items():
                            kk[p] += v
                    t = sum(kk.values()) or 1
                    for p in ps:
                        alloc[m][("5", ss)][p] = q[(c, "5", ss)][m] * kk[p] / t
            # ownership totals; private = county private total split as the sum of its sector allocations
            gov = {"1": "jobs_federal", "2": "jobs_state_local", "3": "jobs_state_local"}
            own_parts = {o: q[(c, o, "10")][m] for o in gov if (c, o, "10") in q}
            own_keys = {o: k(gov[o], c, "jobs_total") for o in own_parts}
            psum = collections.Counter()
            for (o, s), d in alloc[m].items():
                if o == "5" and not s.startswith("10"):
                    for p, v in d.items():
                        psum[p] += v
            tot0 = q[(c, "0", "10")][m]
            pv = priv if priv is not None else None
            gout, gres = split_value((tot0 or 0) - (pv or 0) if pv is not None else tot0, own_parts, own_keys)
            for o, d in gout.items():
                for p, v in (d or {}).items():
                    alloc[m][(o, "10")][p] = v
            for p in ps:
                alloc[m][("5", "10")][p] = psum[p]
                alloc[m][("0", "10")][p] = psum[p] + sum(alloc[m][(o, "10")][p] for o in gov) + gres.get(p, 0.0)
        # exact: scale each published county cell's piece values to the county figure (BLS cells need not add up)
        for m in MEASURES:
            for (o, i), d in alloc[m].items():
                pub = q.get((c, o, i), {}).get(m)
                t = sum(d.values())
                if pub is not None and t > 0:
                    for p in d:
                        d[p] *= pub / t
        for p in sorted(ps):
            val = lambda o, i: {m: alloc[m][(o, i)].get(p) if (o, i) in alloc[m] else None for m in MEASURES}
            emit(p, "piece", c, "0", "10", "total", val("0", "10"), "allocated")
            for own in ("1", "2", "3", "5"):
                if (c, own, "10") in q:
                    pub = q[(c, own, "10")]["emplvl"] is not None
                    emit(p, "piece", c, own, "10", "ownership", val(own, "10") if pub or own == "5" else {}, "allocated" if pub or own == "5" else "withheld")
            for ss in SUPERSECTORS:
                if (c, "5", ss) in q:
                    pub = q[(c, "5", ss)]["emplvl"] is not None
                    emit(p, "piece", c, "5", ss, "supersector", val("5", ss) if pub else {}, "allocated" if pub else "withheld")
            for s in sectors + ["withheld"]:
                if ("5", s) in alloc["emplvl"]:
                    detail.append({"piece_id": p, "county_fips": c, "naics_sector": s,
                                   **{m: round(alloc[m][("5", s)].get(p, 0.0), 1) for m in MEASURES},
                                   "county_cell": "residual of withheld sectors" if s == "withheld" else "published"})

    cols = ["unit_id", "unit_type", "county_fips", "own_code", "industry_code", "level", *MEASURES, "avg_weekly_wage", "method"]
    with open(os.path.join(HERE, "qcew_2024_units.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, cols); w.writeheader(); w.writerows(rows)
    with open(os.path.join(HERE, "qcew_2024_pieces_detail.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, list(detail[0])); w.writeheader(); w.writerows(detail)

    # checks: every split county's pieces sum to its published figures
    bad = []
    for c in split:
        for (own, ind, lvl) in [("0", "10", "total")] + [(o, "10", "ownership") for o in "1235"] + [("5", s, "supersector") for s in SUPERSECTORS]:
            if (c, own, ind) not in q:
                continue
            for m in MEASURES:
                pub = q[(c, own, ind)][m]
                vals = [r[m] for r in rows if r["county_fips"] == c and r["own_code"] == own and r["industry_code"] == ind and r["unit_type"] == "piece"]
                if pub is not None and all(v != "" for v in vals) and abs(sum(vals) - pub) > max(1.0, 1e-6 * pub):
                    bad.append((c, own, ind, m, round(sum(vals)), pub))
    print(f"units {len({r['unit_id'] for r in rows}):,} rows {len(rows):,}; split counties {len(split)}; counties without QCEW {missing}; "
          f"sum checks failed {len(bad)} {bad[:4]}")
    n = collections.Counter((r["level"], r["method"]) for r in rows if r["unit_type"] == "piece")
    print("piece rows by level and method:", dict(n))


if __name__ == "__main__":
    main()
