"""Validate the allocation keys on known splits (docs/specs/allocation-keys.md, Validation).

Each test treats a multi-county metro as one "county": its QCEW 2024 total is shared among its real counties by keys
built exactly as for pieces (same sources and code: build_keys.lodes_keys, pay_index, wage_keys, zbp_keys), and the result
is compared with BLS's published county figures. Only cells published for every county of a metro are tested.

Error = share of the metro total placed in the wrong county: sum |allocated - published| / (2 x metro total).
Compared methods, per measure:
  employment, private, by sector   key jobs_private_<s>          baselines: population, all jobs
  wages, private, by sector        wages_private_<s> (pay index) vs jobs_private_<s> (no index: decision 1); baselines
  establishments, private, sector  est_<s> (ZBP)                 vs jobs_private_<s> (decision 3); baselines
  employment, federal / state / local  jobs_federal / jobs_state (ACS-calibrated, gov_keys) / jobs_state_local; also
                                       the LODES keys alone (federal JT04, state and local); baselines
Residence keys (--part residence) are tested the same way against BEA personal income by county:
  CAINC4 2024   net earnings by residence (res_wage_selfemp_income), dividends interest and rent (res_dir_income),
                transfers (the metro's 2022 CAINC35 mix x each type's key), personal income (sum of the three)
  CAINC35 2022  each transfer type with its key
  baselines     population; one key for everything: total household income (ACS B19062 + B19063 + B19064 + B19065 +
                B19066 + B19067, decision 4); per capita income error by county is reported too
Writes validation.csv (workplace) / validation_residence.csv (every test cell) and prints a summary.
usage: python3 validate_keys.py --cache DIR [--part work|residence|all]
"""
import argparse, collections, csv, os, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pieces"))
sys.path.insert(0, os.path.join(HERE, "..", "data"))
import build_crosswalk as bx  # noqa: E402
import build_keys as bk  # noqa: E402
import apply_qcew as aq  # noqa: E402
import apply_bea as ab  # noqa: E402

METROS = {
    "New York (5 boroughs)": ["36005", "36047", "36061", "36081", "36085"],
    "Bay Area core": ["06001", "06013", "06075", "06081", "06085"],
    "Dallas-Fort Worth": ["48113", "48439", "48085", "48121"],
    "Houston": ["48201", "48157", "48339"],
    "Atlanta": ["13121", "13089", "13067", "13135", "13063"],
    "Twin Cities": ["27053", "27123", "27037", "27003", "27163"],
    "Philadelphia": ["42101", "42091", "42045", "42017", "42029"],
    "Detroit": ["26163", "26125", "26099"],
    "LA basin": ["06037", "06059"],
    "South Florida": ["12086", "12011", "12099"],
    "Seattle": ["53033", "53053", "53061"],
    "Boston": ["25017", "25025", "25021", "25009"],
    "Cleveland": ["39035", "39085", "39093", "39103"],
    "Charlotte": ["37119", "37179", "37025"],
    "Salt Lake": ["49035", "49049", "49011"],
    "Phoenix-Tucson (control: distant)": ["04013", "04019"],
}


def err(alloc, truth):
    t = sum(truth.values())
    return sum(abs(alloc[c] - truth[c]) for c in truth) / (2 * t) if t else None


def split(total, key):
    s = sum(key.values())
    return {c: total * v / s for c, v in key.items()} if s else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True); ap.add_argument("--part", default="all")
    a = ap.parse_args(); bx.CACHE = a.cache; bx.fix_hash_seed()
    if a.part in ("residence", "all"):
        residence()
    if a.part == "residence":
        return
    counties = {c for cs in METROS.values() for c in cs}
    tp = bk.tract_pop()
    area_of = {g: g[:5] for g in tp if g[:5] in counties}
    lk, bands = bk.lodes_keys(area_of)
    q = aq.load_qcew(counties)
    metro_of = {c: m for m, cs in METROS.items() for c in cs}
    pay = {}
    for m, cs in METROS.items():
        w = sum(q[(c, "0", "10")]["total_wages"] for c in cs); e = sum(q[(c, "0", "10")]["emplvl"] for c in cs)
        pay[m] = w / e / 12
    index, _ = bk.pay_index(bands, metro_of, pay)
    wk = bk.wage_keys(lk, index)
    ek, _ = bk.zbp_keys(area_of)
    gk = bk.gov_keys({m: set(cs) for m, cs in METROS.items()}, lambda b: b[:5])
    lodes_gov = {"jobs_federal_lodes": lk["jobs_federal"], "jobs_state_lodes": lk["jobs_state_local"]}
    popk = collections.Counter()
    for g, c in area_of.items():
        popk[c] += tp[g]
    K = lambda name: {**lk, **wk, **ek, **gk, **lodes_gov}.get(name, {})
    rows = []
    for m, cs in METROS.items():
        base = {"population": {c: popk[c] for c in cs}, "all jobs": {c: lk["jobs_total"][c] for c in cs}}
        tests = []
        for s in bk.CNS:
            cells = [(c, "5", s) for c in cs]
            if all(x in q for x in cells):
                for meas, methods in (("emplvl", {"key": f"jobs_private_{s}"}),
                                      ("total_wages", {"key (pay index)": f"wages_private_{s}", "jobs, no pay index": f"jobs_private_{s}"}),
                                      ("estabs", {"key (ZBP)": f"est_{s}", "jobs instead of ZBP": f"jobs_private_{s}"})):
                    if s == "92" and meas == "estabs":
                        continue
                    tests.append((f"private {meas}", s, cells, meas, methods))
        for own, methods in (("1", {"key": "jobs_federal", "LODES only": "jobs_federal_lodes"}),
                             ("2", {"key": "jobs_state", "LODES only": "jobs_state_lodes"}), ("3", {"key": "jobs_state_local"})):
            cells = [(c, own, "10") for c in cs]
            if all(x in q for x in cells):
                tests.append((f"ownership {own} emplvl", "10", cells, "emplvl", methods))
        cells = [(c, "0", "10") for c in cs]
        tests.append(("total emplvl", "10", cells, "emplvl", {"key": "jobs_total"}))
        tests.append(("total total_wages", "10", cells, "total_wages", {"key (pay index)": "wages_total", "jobs, no pay index": "jobs_total"}))
        for fam, ind, cells, meas, methods in tests:
            truth = {c: q[(c, o, i)][meas] for c, o, i in cells}
            if any(v is None for v in truth.values()) or not sum(truth.values()):
                continue
            total = sum(truth.values())
            res = {}
            for label, kname in list(methods.items()) + [("baseline: population", None), ("baseline: all jobs", None)]:
                key = base["population"] if label == "baseline: population" else base["all jobs"] if label == "baseline: all jobs" else {c: K(kname).get(c, 0) for c in cs}
                al = split(total, key)
                res[label] = err(al, truth) if al else None
            for label, e in res.items():
                rows.append({"metro": m, "family": fam, "industry": ind, "method": label, "metro_total": round(total), "error": "" if e is None else round(e, 4)})
    with open(os.path.join(HERE, "validation.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0])); w.writeheader(); w.writerows(rows)
    # summary: total-weighted mean error and median, by family and method (controls excluded)
    agg = collections.defaultdict(list)
    for r in rows:
        if r["error"] != "" and "control" not in r["metro"]:
            agg[(r["family"], r["method"])].append((float(r["error"]), r["metro_total"]))
    print(f"{'measure':28s} {'method':24s} {'cells':>5s} {'weighted':>9s} {'median':>7s}")
    for (fam, meth), v in sorted(agg.items()):
        wm = sum(e * t for e, t in v) / sum(t for _, t in v)
        print(f"{fam:28s} {meth:24s} {len(v):5d} {100 * wm:8.1f}% {100 * statistics.median(e for e, _ in v):6.1f}%")


def residence():
    metros = {m: cs for m, cs in METROS.items() if "control" not in m}
    counties = {c for cs in metros.values() for c in cs}
    tp = bk.tract_pop()
    area_of = {g: g[:5] for g in tp if g[:5] in counties}
    rk, _, _ = bk.acs_keys(area_of)
    hh_income = {c: sum(rk[k][c] for k in ("res_wage_income", "res_selfemp_income", "res_dir_income", "res_social_security_income", "res_ssi_pa_income")) for c in counties}
    popk = collections.Counter()
    for g, c in area_of.items():
        popk[c] += tp[g]
    pi4, _, _ = ab.load("CAINC4", counties)
    t35, _, _ = ab.load("CAINC35", counties)
    rows, pcap = [], collections.defaultdict(list)
    for m, cs in metros.items():
        if not all(c in pi4 for c in cs):
            continue
        base = {"baseline: population": {c: popk[c] for c in cs}, "baseline: one key (household income)": {c: hh_income[c] for c in cs}}
        def test(fam, line, truth, methods):
            if any(v is None for v in truth.values()) or not sum(truth.values()):
                return {}
            total = sum(truth.values()); out = {}
            for label, key in list(methods.items()) + list(base.items()):
                al = split(total, key)
                out[label] = al
                rows.append({"metro": m, "family": fam, "line": line, "method": label, "metro_total": round(total),
                             "error": "" if not al else round(err(al, truth), 4)})
            return out
        # components (2024)
        comp = {}
        for line, kname in (("45", "res_wage_selfemp_income"), ("46", "res_dir_income")):
            comp[line] = test({"45": "net earnings by residence", "46": "dividends, interest, rent"}[line], line,
                              {c: pi4[c].get(line) for c in cs}, {"key": {c: rk[kname][c] for c in cs}})
        mix = {l: sum(t35[c].get(l) or 0 for c in cs) for l in ab.TRANSFER_LEAVES}
        tm = sum(mix.values())
        ckey = {c: sum(mix[l] / tm * (rk[k][c] / sum(rk[k][x] for x in cs) if sum(rk[k][x] for x in cs) else 0)
                       for l, k in ab.TRANSFER_LEAVES.items()) for c in cs}
        comp["47"] = test("transfers (composite)", "47", {c: pi4[c].get("47") for c in cs}, {"key": ckey})
        # personal income: component method = sum of the three allocated components
        truth = {c: pi4[c].get("10") for c in cs}
        if all(comp.get(l) and comp[l].get("key") for l in ("45", "46", "47")) and all(v is not None for v in truth.values()):
            al = {c: sum(comp[l]["key"][c] for l in ("45", "46", "47")) for c in cs}
            total = sum(truth.values()); scale = total / sum(al.values()); al = {c: v * scale for c, v in al.items()}
            rows.append({"metro": m, "family": "personal income", "line": "10", "method": "key (by component)", "metro_total": round(total), "error": round(err(al, truth), 4)})
            other = {}
            for label, key in base.items():
                b = split(total, key)
                rows.append({"metro": m, "family": "personal income", "line": "10", "method": label, "metro_total": round(total), "error": round(err(b, truth), 4)})
                other[label] = b
            for c in cs:  # per capita income, absolute % error by county (population: BEA's)
                pop = pi4[c].get("20")
                if pop:
                    pcap["key (by component)"].append(abs(al[c] - truth[c]) / truth[c])
                    for label, b in other.items():
                        pcap[label].append(abs(b[c] - truth[c]) / truth[c])
        # transfer types (2022)
        for l, kname in ab.TRANSFER_LEAVES.items():
            test(f"transfer {l}", l, {c: t35[c].get(l) for c in cs}, {"key": {c: rk[kname][c] for c in cs}})
    with open(os.path.join(HERE, "validation_residence.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0])); w.writeheader(); w.writerows(rows)
    agg = collections.defaultdict(list)
    for r in rows:
        if r["error"] != "":
            agg[(r["family"], r["method"])].append((float(r["error"]), r["metro_total"]))
    print(f"{'measure':30s} {'method':38s} {'metros':>6s} {'weighted':>9s} {'median':>7s}")
    for (fam, meth), v in sorted(agg.items()):
        wm = sum(e * t for e, t in v) / sum(t for _, t in v)
        print(f"{fam:30s} {meth:38s} {len(v):6d} {100 * wm:8.1f}% {100 * statistics.median(e for e, _ in v):6.1f}%")
    print("per capita personal income by county, mean absolute % error:", {k: round(100 * statistics.mean(v), 1) for k, v in pcap.items()})


if __name__ == "__main__":
    main()
