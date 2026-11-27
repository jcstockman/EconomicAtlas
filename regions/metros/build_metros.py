"""Subregions and districts for the 57 CBSAs of 1.0M+ (docs/specs/subregions-districts.md).

Districts (0.35-1.5M): every atlas unit of 0.35M+ (a county piece, or a county) is a district; counties under 0.35M
join, by LODES commuting (their residents' jobs), an adjacent district or small-county group in the same region, until
every group holds 0.35M+. A region is an OMB metropolitan division (divisions under 0.6M first join the neighbouring
division their residents commute to most), or the whole CBSA where it has no divisions or is under 2.5M.
Subregions (0.6-3.5M, CBSAs of 2.5M+ only): unions of districts. A division of 0.6-3.5M is one subregion; a larger one
is split, and a CBSA without divisions is grouped (into 2 or more), by commuting (modularity with a compactness term,
contiguous; the pieces' engine, build_groups.Part): first within the aim of 1.0-2.5M, then 0.6-2.5M, then 0.6-3.5M, each
number of parts the band allows, keeping the best-scoring valid grouping. Where the greedy district joins leave a district
outside 0.35-1.5M, that region's districts are made by the same engine (units of 0.35M+ kept apart).
District view: shown in subregions over 1.5M and in CBSAs of 1.0-2.5M with two or more districts; elsewhere it falls
through to the subregion or CBSA.
IDs: subregion <CBSA>-S<nn>, district <CBSA>-D<nn>, tied in metro_registry.csv to an anchor unit (the group's largest),
kept across rebuilds as for pieces. Figures for districts and subregions are sums of atlas-unit figures.

Inputs: atlas units (regions/units), OMB July 2023 delineation (list1_2023.xlsx), LODES 8 OD main + aux (all jobs) for
the 40 states of the covered CBSAs (latest year published, 2024 back to 2021). LODES does not cover Puerto Rico: there,
commuting is the ACS 2016-2020 county-to-county flows (table 1, workers 16+), which suffice because every Puerto Rico
unit is a whole municipio.
Writes next to this script: crosswalk_unit_metro.csv, districts.csv, subregions.csv, districts.geojson,
subregions.geojson, metro_units.geojson (the covered units' shapes, for the map), metro_registry.csv.
usage: python3 build_metros.py --cache DIR
"""
import argparse, collections, csv, gzip, json, math, os, sys, urllib.error

import networkx as nx
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pieces"))
import build_crosswalk as bx  # noqa: E402
import build_groups as bg  # noqa: E402

DELIN = "https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list1_2023.xlsx"
ACS_FLOWS = "https://www2.census.gov/programs-surveys/demo/tables/metro-micro/2020/commuting-flows-2020/table1.xlsx"
ACS_FLOW_STATES = {"72"}  # states whose commuting comes from the ACS flows instead of LODES
OD = "https://lehd.ces.census.gov/data/lodes/LODES8/{st}/od/{st}_od_{part}_JT00_{yr}.csv.gz"
ABBR = {"01": "al", "04": "az", "05": "ar", "06": "ca", "08": "co", "09": "ct", "10": "de", "11": "dc", "12": "fl", "13": "ga",
        "17": "il", "18": "in", "19": "ia", "20": "ks", "21": "ky", "24": "md", "25": "ma", "26": "mi", "27": "mn", "28": "ms",
        "29": "mo", "31": "ne", "32": "nv", "33": "nh", "34": "nj", "36": "ny", "37": "nc", "39": "oh", "40": "ok", "41": "or",
        "42": "pa", "44": "ri", "45": "sc", "47": "tn", "48": "tx", "49": "ut", "51": "va", "53": "wa", "54": "wv", "55": "wi"}
COVER, BIG = 1_000_000, 2_500_000
D_LO, D_HI = 350_000, 1_500_000
S_LO, S_HI, S_AIM_LO, S_AIM_HI = 600_000, 3_500_000, 1_000_000, 2_500_000
VIEW_MIN = 1_500_000
S_MU = 0.25  # compactness weight in subregion grouping (pieces use 1.0; between large counties boundary length says little)
ADJ_BUF = 0.01  # degrees (~1 km): unit shapes are simplified, and some neighbours face each other across a river


def od_file(st, part):
    yrs = ("2024", "2023", "2022", "2021")
    for yr in yrs:  # a year already downloaded first (no needless 404s), then the network
        if os.path.exists(os.path.join(bx.CACHE, OD.format(st=st, part=part, yr=yr).rsplit("/", 1)[1])):
            return bx.fetch(OD.format(st=st, part=part, yr=yr)), yr
    for yr in yrs:
        try:
            return bx.fetch(OD.format(st=st, part=part, yr=yr)), yr
        except urllib.error.HTTPError:
            continue
    raise SystemExit(f"no LODES OD {part} file for {st}")


def delineation():
    import openpyxl
    rows = list(openpyxl.load_workbook(bx.fetch(DELIN), read_only=True).active.iter_rows(values_only=True))
    hi = [i for i, r in enumerate(rows) if r and r[0] == "CBSA Code"][0]; h = rows[hi]
    out = [dict(zip(h, r)) for r in rows[hi + 1:] if r and r[0] and str(r[0]).isdigit()]
    return [d for d in out if d["Metropolitan/Micropolitan Statistical Area"] == "Metropolitan Statistical Area"]


def acs_flows(units_in):
    """ACS 2016-2020 county-to-county flows for the ACS_FLOW_STATES: ({(home unit, work unit): workers}, {home unit:
    workers}) among units_in (whole counties). Workers by home count every workplace, in or outside the units."""
    import openpyxl
    flows, jobs_of = collections.Counter(), collections.Counter()
    ws = openpyxl.load_workbook(bx.fetch(ACS_FLOWS, "acs_commuting_flows_2016_2020_table1.xlsx"), read_only=True).active
    for r in ws.iter_rows(min_row=9, values_only=True):
        if r[0] in ACS_FLOW_STATES and r[1] and r[8]:
            h = r[0] + r[1]
            if h in units_in:
                jobs_of[h] += int(r[8])
                w = (r[4] or "")[-2:] + (r[5] or "")
                if w in units_in:
                    flows[(h, w)] += int(r[8])
    return flows, jobs_of


def group(nodes, pop, adj, flows, blen, k, lo, hi, apart=(), mu=None):
    """Split nodes into k contiguous groups within lo-hi by the pieces' engine (modularity - MU x boundary cut);
    no two nodes of `apart` share a group. Returns (score, groups) or None."""
    if k <= 1:
        return [set(nodes)]
    G = nx.Graph(); G.add_nodes_from(nodes)
    for (a, b), n in flows.items():
        if a in nodes and b in nodes and a != b:
            G.add_edge(a, b, weight=G[a][b]["weight"] + n if G.has_edge(a, b) else n)
    saved = (bg.LO, bg.HI, bg.MU)
    bg.LO, bg.HI = lo, hi
    if mu is not None:
        bg.MU = mu
    try:
        P = bg.Part(G, {n: pop[n] for n in nodes}, {n: adj[n] & set(nodes) for n in nodes}, 1.0,
                    collections.defaultdict(dict, {n: {m: w for m, w in blen.get(n, {}).items() if m in nodes} for n in nodes}))
        P.apart = set(apart)
        cands = []
        starts = [nx.algorithms.community.louvain_communities(G, weight="weight", resolution=r, seed=s) for r in (0.5, 1, 2, 4) for s in range(4)]
        starts.append([{n} for n in nodes])
        for comms in starts:
            parts = P.split_apart([x for c in comms for x in P.components(c)])
            if len(parts) < k:
                continue
            parts = P.merge_to(parts, k)
            if parts is None:
                continue
            parts = P.refine(parts)
            if P.penalty(parts) > 0:
                parts = P.rebalance(parts)
            if P.penalty(parts) == 0 and all(P.connected(x) for x in parts):
                cands.append((P.score(parts), parts))
        if k ** len(nodes) <= 2_000_000:
            cands += [(sc, parts) for sc, q, parts in bg.exhaustive(P, sorted(nodes), k)]
        if not cands:
            return None
        return max(cands, key=lambda c: c[0])
    finally:
        bg.LO, bg.HI, bg.MU = saved


def adjacency(geo, cunits, upop, cbsas):
    """Adjacent units within each CBSA (shapes buffered by ADJ_BUF) with their shared boundary length; a part of a
    CBSA cut off from the rest (an island) is linked to its nearest unit."""
    adj = collections.defaultdict(set); blen = collections.defaultdict(dict)
    for c in cbsas:
        ids = sorted(cunits[c]); buf = [geo[k].buffer(ADJ_BUF) for k in ids]; tree = STRtree(buf)
        for i, k in enumerate(ids):
            for j in tree.query(buf[i], predicate="intersects"):
                if j != i:
                    adj[k].add(ids[j]); blen[k][ids[j]] = buf[i].intersection(buf[j]).area / (2 * ADJ_BUF)
        G0 = nx.Graph(); G0.add_nodes_from(ids); G0.add_edges_from((k, m) for k in ids for m in adj[k])
        comps = sorted(nx.connected_components(G0), key=lambda x: -sum(upop[k] for k in x))
        for comp in comps[1:]:
            rest = [k for k in ids if k not in comp]
            k, m = min(((k, m) for k in comp for m in rest), key=lambda km: geo[km[0]].distance(geo[km[1]]))
            adj[k].add(m); adj[m].add(k); blen[k][m] = blen[m][k] = 0.0
    return adj, blen


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True)
    ap.add_argument("--out", default=HERE, help="write outputs here (for trying rule variants; default: next to this script)")
    ap.add_argument("--set", action="append", default=[], metavar="NAME=VALUE", help="override a rule constant, e.g. S_MU=0.25")
    a = ap.parse_args(); bx.CACHE = a.cache; bx.fix_hash_seed()
    for kv in a.set:
        k_, v_ = kv.split("=", 1); globals()[k_] = type(globals()[k_])(eval(v_))
    OUT = a.out; os.makedirs(OUT, exist_ok=True)
    U = os.path.join(HERE, "..", "units")
    units = {u["unit_id"]: u for u in csv.DictReader(open(os.path.join(U, "atlas_units.csv")))}
    upop = {k: int(u["pop2025_est"]) for k, u in units.items()}
    unit_of_tract = {r["tract_geoid"]: r["unit_id"] for r in csv.DictReader(open(os.path.join(U, "crosswalk_tract_unit.csv")))}
    geo = {f["properties"]["unit_id"]: shape(f["geometry"]) for f in json.load(open(os.path.join(U, "atlas_units.geojson")))["features"]}
    release = next(iter(units.values()))["pieces_release"]

    D = delineation()
    cbsa_of, div_of, title, divtitle, csa_of = {}, {}, {}, {}, {}
    for d in D:
        f = d["FIPS State Code"] + d["FIPS County Code"]
        cbsa_of[f] = d["CBSA Code"]; title[d["CBSA Code"]] = d["CBSA Title"]
        if d["Metropolitan Division Code"]:
            div_of[f] = d["Metropolitan Division Code"]; divtitle[d["Metropolitan Division Code"]] = d["Metropolitan Division Title"]
        if d["CSA Code"]:
            csa_of[f] = d["CSA Code"]
    cunits = collections.defaultdict(list)
    for k, u in units.items():
        c = cbsa_of.get(u["county_fips"])
        if c:
            cunits[c].append(k)
    cpop = {c: sum(upop[k] for k in ks) for c, ks in cunits.items()}
    covered = sorted((c for c in cunits if cpop[c] >= COVER), key=lambda c: -cpop[c])
    big = {c for c in covered if cpop[c] >= BIG}
    cov_units = {k for c in covered for k in cunits[c]}
    print(f"covered CBSAs {len(covered)} ({len(big)} of 2.5M+), units {len(cov_units)}", flush=True)

    # commuting between units: LODES OD main (in-state) + aux (home in another state), residents -> jobs
    flows = collections.Counter(); years = {}
    jobs_of = collections.Counter()  # residents' jobs anywhere in the files read, by home unit
    ods = [(s2, part) + od_file(ABBR[s2], part) for s2 in sorted({units[k]["county_fips"][:2] for k in cov_units} - ACS_FLOW_STATES)
           for part in ("main", "aux")]
    years = {ABBR[s2]: yr for s2, part, p, yr in ods}
    # the unit flows are cached (a derived file, keyed by the OD files and the unit crosswalk) so rebuilds are quick
    import hashlib, pickle
    fkey = hashlib.md5(json.dumps([os.path.basename(p) for *_, p, yr in ods] + [os.path.getsize(p) for *_, p, yr in ods] +
                                  [os.path.getsize(os.path.join(U, "crosswalk_tract_unit.csv")), sorted(k for k in cov_units if units[k]["state_fips"] not in ACS_FLOW_STATES)]).encode()).hexdigest()
    fcache = os.path.join(bx.CACHE, f"metro_flows_{fkey}.pkl")
    if os.path.exists(fcache):
        flows, jobs_of = pickle.load(open(fcache, "rb"))
    for s2, part, p, yr in ([] if os.path.exists(fcache) else ods):
        st = ABBR[s2]
        if True:
            with gzip.open(p, "rt") as fh:
                r = csv.reader(fh); next(r)
                for w, h, n, *_ in r:
                    hu = unit_of_tract.get(h[:11])
                    if hu in cov_units:
                        jobs_of[hu] += int(n)
                        wu = unit_of_tract.get(w[:11])
                        if wu in cov_units:
                            flows[(hu, wu)] += int(n)
        print("  OD", st, part, yr, flush=True)
    if not os.path.exists(fcache):
        pickle.dump((flows, jobs_of), open(fcache, "wb"))
    acs_units = {k for k in cov_units if units[k]["state_fips"] in ACS_FLOW_STATES}
    if acs_units:  # Puerto Rico: ACS county-to-county commuting (no LODES)
        af, aj = acs_flows(acs_units)
        flows.update(af); jobs_of.update(aj)
        print(f"  ACS flows: {len(acs_units)} units, {sum(af.values()):,} workers among them", flush=True)

    def work_inside(ks):  # share of the group's employed residents whose job is in the group
        tot = sum(jobs_of[k] for k in ks)
        return round(sum(flows.get((h, w), 0) for h in ks for w in ks) / tot, 4) if tot else None

    adj, blen = adjacency(geo, cunits, upop, [c for c in covered])
    notes = []
    # enclosed units: a unit under 0.35M lying (90%+ of its area) inside the outline of one larger neighbour, holes filled
    # (Manassas and Manassas Park inside Prince William), always joins that neighbour's district
    def filled(g):
        return unary_union([Polygon(p.exterior) for p in ([g] if g.geom_type == "Polygon" else g.geoms)])
    pp = os.path.join(HERE, "metro_pins.csv")
    pins = list(csv.DictReader(open(pp))) if os.path.exists(pp) else []
    for pin in pins:
        for u_ in (pin["unit_id"], pin["with_unit"]):
            if u_ not in units:
                raise SystemExit(f"metro_pins.csv: unknown atlas unit {u_}")
    enclosed = {}
    for k in sorted(cov_units):
        if upop[k] < D_LO:
            for h in sorted(adj[k], key=lambda h: -upop[h]):
                if upop[h] > upop[k] and geo[k].intersection(filled(geo[h])).area >= 0.9 * geo[k].area:
                    enclosed[k] = h; notes.append(f"{units[k]["unit_name"]} lies inside {units[h]["unit_name"]}: joins its district"); break

    def outflow(src, dst):  # residents of src working in dst
        return sum(flows.get((h, w), 0) for h in src for w in dst)

    def touches(x, y):
        return any(adj[k] & y for k in x)

    # regions: divisions (small ones merged by commuting) or whole CBSAs
    regions = {}  # region id -> set of units
    region_cbsa, region_name = {}, {}
    for c in covered:
        divs = collections.defaultdict(set)
        for k in cunits[c]:
            d = div_of.get(units[k]["county_fips"]) if c in big else None
            divs[d or c].add(k)
        names = {d: (divtitle.get(d, title[c])) for d in divs}
        while True:
            small = [d for d in divs if sum(upop[k] for k in divs[d]) < S_LO and len(divs) > 1]
            if not small:
                break
            d = min(small, key=lambda x: sum(upop[k] for k in divs[x]))
            nb = [e for e in divs if e != d and touches(divs[d], divs[e])]
            e = max(nb, key=lambda e: outflow(divs[d], divs[e]))
            notes.append(f"division {names[d]} ({sum(upop[k] for k in divs[d]):,}) joins {names[e]}")
            divs[e] |= divs.pop(d); names[e] = names[e] + " + " + names.pop(d).split(",")[0]
        for d, ks in divs.items():
            regions[d] = ks; region_cbsa[d] = c; region_name[d] = names[d]

    # districts
    districts = {}  # temp id -> set
    district_region = {}
    for rid, ks in regions.items():
        cl = {k: {k} for k in ks}
        # district pins (metro_pins.csv): unit_id and with_unit start in one group, before the small counties are joined
        for pin in (x for x in pins if x["level"] == "district"):
            k, h = pin["unit_id"], pin["with_unit"]
            if (k in ks) != (h in ks):
                raise SystemExit(f"pin {k} -> {h}: not in the same region")
            if k in ks:
                top = lambda u: next(x for x, s_ in cl.items() if u in s_)
                a_, b_ = top(k), top(h)
                if a_ != b_:
                    cl[b_] |= cl.pop(a_)
                    notes.append(f"pin: {units[k]['unit_name']} starts in one district with {units[h]['unit_name']}")
        for k, h in enclosed.items():
            if k in ks and h in ks:
                top = lambda u: next(x for x, s in cl.items() if u in s)
                a, b = top(k), top(h)
                if a != b:
                    cl[b] |= cl.pop(a)
        while True:
            small = [x for x, s in cl.items() if sum(upop[k] for k in s) < D_LO]
            if not small or len(cl) == 1:
                break
            x = min(small, key=lambda x: sum(upop[k] for k in cl[x]))
            nb = [y for y in cl if y != x and touches(cl[x], cl[y])]
            if not nb:
                nb = [y for y in cl if y != x]
            ok = [y for y in nb if sum(upop[k] for k in cl[x] | cl[y]) <= D_HI] or nb
            y = max(ok, key=lambda y: (outflow(cl[x], cl[y]), outflow(cl[y], cl[x])))
            cl[y] |= cl.pop(x)
        sizes = [sum(upop[k] for k in s) for s in cl.values()]
        if len(cl) > 1 and any(not D_LO <= z <= D_HI for z in sizes):
            # the greedy joins left a district outside 0.35-1.5M: group the region's units by the pieces' engine
            # instead, every unit of 0.35M+ in a district of its own, trying each feasible number of districts
            seeds = {k for k in ks if upop[k] >= D_LO}
            p = sum(upop[k] for k in ks); fl = {kv: n for kv, n in flows.items() if kv[0] in ks and kv[1] in ks}
            tries = [group(set(ks), upop, {k: adj[k] & ks for k in ks}, fl, blen, kk, D_LO, D_HI, seeds)
                     for kk in range(max(len(seeds), math.ceil(p / D_HI)), int(p // D_LO) + 1)]
            tries = [t for t in tries if t]
            if not tries:
                raise SystemExit(f"{region_name[rid]}: no districts within {D_LO:,}-{D_HI:,}")
            best = max(tries, key=lambda t: t[0])[1]
            notes.append(f"{region_name[rid]}: joins by commuting gave sizes {sorted(sizes)}; grouped by the engine into {len(best)}")
            cl = {min(s): set(s) for s in best}
        for x, s in cl.items():
            tid = f"{rid}:{x}"; districts[tid] = s; district_region[tid] = rid

    # subregion pins (metro_pins.csv): the district holding unit_id shares a subregion with the district holding with_unit
    dist_of = lambda u: next(d for d, s_ in districts.items() if u in s_)
    spins = [(dist_of(x["unit_id"]), dist_of(x["with_unit"])) for x in pins if x["level"] == "subregion"]

    # subregions (CBSAs of 2.5M+): unions of districts
    subregions, sub_cbsa = {}, {}
    for c in sorted(big):
        rids = [r for r in regions if region_cbsa[r] == c]
        divided = any(r != c for r in rids)
        for rid in rids:
            all_d = [d for d in districts if district_region[d] == rid]
            p = sum(upop[k] for k in regions[rid])
            if divided and p <= S_HI:
                parts = [set(all_d)]
            else:
                # subregion pins: pinned districts are grouped as one node, expanded afterwards
                rep_ = {d: d for d in all_d}
                for a_, b_ in spins:
                    if a_ in rep_ and b_ in rep_:
                        ra, rb = rep_[a_], rep_[b_]
                        for d in all_d:
                            if rep_[d] == rb:
                                rep_[d] = ra
                        notes.append(f"pin: districts {a_} and {b_} share a subregion")
                node = collections.defaultdict(set)
                for d in all_d:
                    node[rep_[d]].add(d)
                districts_ = districts
                districts = {n: set().union(*(districts_[d] for d in ds)) for n, ds in node.items()}
                dids = list(node)
                dpop = {d: sum(upop[k] for k in districts[d]) for d in dids}
                dadj = {d: {e for e in dids if e != d and touches(districts[d], districts[e])} for d in dids}
                dfl = collections.Counter()
                for d in dids:
                    for e in dids:
                        if d != e:
                            dfl[(d, e)] = outflow(districts[d], districts[e])
                dbl = {d: {e: sum(blen[k].get(m, 0) for k in districts[d] for m in districts[e]) for e in dadj[d]} for d in dids}
                # the aim (1.0-2.5M) first, then the limits (0.6-3.5M); within a band, each number of subregions it allows,
                # keeping the best-scoring valid grouping (the score compares groupings of the same districts)
                parts = None
                for lo, hi in ((S_AIM_LO, S_AIM_HI), (S_LO, S_AIM_HI), (S_LO, S_HI)):
                    ks_ = range(max(math.ceil(p / hi), 1 if divided else 2), int(p // lo) + 1)
                    tries = [t for t in (group(set(dids), dpop, dadj, dfl, dbl, kk, lo, hi, mu=S_MU) for kk in ks_) if t]
                    if tries:
                        parts = max(tries, key=lambda t: t[0])[1]
                        if (lo, hi) != (S_AIM_LO, S_AIM_HI):
                            notes.append(f"{region_name[rid]}: no grouping within {S_AIM_LO:,}-{S_AIM_HI:,}; used {lo:,}-{hi:,}")
                        break
                districts = districts_
                if parts is None:
                    raise SystemExit(f"{region_name[rid]}: no valid grouping into subregions")
                parts = [set().union(*(node[n] for n in ps)) for ps in parts]
            for i, ps in enumerate(parts):
                sid = f"{rid}#{i}"; subregions[sid] = set(ps); sub_cbsa[sid] = c

    # IDs: registry (anchor unit = group's largest unit), as for pieces
    regp = os.path.join(HERE, "metro_registry.csv")  # read from here; written to OUT
    registry = list(csv.DictReader(open(regp))) if os.path.exists(regp) else []
    def assign_ids(groups, level, cbsa_of_group, members):
        out, used = {}, collections.defaultdict(set)
        for r in registry:
            if r["level"] == level:
                used[r["cbsa"]].add(int(r["id"].split(level[0].upper())[-1]))
        holder = {}
        for g in groups:
            for k in members(g):
                holder[k] = g
        for r in sorted((r for r in registry if r["level"] == level and r["status"] == "active"), key=lambda r: r["id"]):
            if r["anchor_unit"] not in units:  # the anchor county has since been split: its largest piece takes over
                alt = [k for k, u in units.items() if u["county_fips"] == r["anchor_unit"][:5]]
                if alt:
                    r["anchor_unit"] = max(alt, key=lambda k: upop[k])
            g = holder.get(r["anchor_unit"])
            if g is None or g in out:
                r["status"] = "retired"; continue
            out[g] = r["id"]
        for g in sorted(set(groups) - set(out), key=lambda g: -sum(upop[k] for k in members(g))):
            c = cbsa_of_group[g]; n = max(used[c], default=0) + 1; used[c].add(n)
            out[g] = f"{c}-{level[0].upper()}{n:02d}"
            registry.append({"id": out[g], "level": level, "cbsa": c, "anchor_unit": max(members(g), key=lambda k: upop[k]),
                             "status": "active", "since_version": "1.0"})
        return out
    dmembers = lambda d: districts[d]
    smembers = lambda s: set().union(*(districts[d] for d in subregions[s]))
    did = assign_ids(list(districts), "district", {d: region_cbsa[district_region[d]] for d in districts}, dmembers)
    sid = assign_ids(list(subregions), "subregion", sub_cbsa, smembers)

    def uname(k):
        u = units[k]
        return u["unit_name"] if u["unit_type"] == "piece" else u["county"].replace(" County", "").replace(" Planning Region", "")
    def gname(ks):
        top = sorted(ks, key=lambda k: -upop[k])
        if len(top) == 1:
            return uname(top[0])
        # unit names often hold "&" themselves, so units are joined with " / "; at most three named
        n = 3 if len(top) == 3 else 2
        return " / ".join(uname(k) for k in top[:n]) + (f" (+{len(top) - n})" if len(top) > n else "")

    # curated names (metro_names.csv, by ID) replace the automatic ones; IDs without one keep the automatic name
    np_ = os.path.join(HERE, "metro_names.csv")
    curated = {r["id"]: r["name"] for r in csv.DictReader(open(np_))} if os.path.exists(np_) else {}
    sub_of_district = {d: s for s, ds in subregions.items() for d in ds}
    rows_d, rows_s, xw = [], [], []
    for s, ds in subregions.items():
        ks = smembers(s); p = sum(upop[k] for k in ks); rid = next(iter(ds)).split(":")[0]
        nm = region_name[rid].split(",")[0] if len(subregions_of := [x for x in subregions if x.startswith(rid + "#")]) == 1 and rid != sub_cbsa[s] else gname(ks)
        rows_s.append({"subregion_id": sid[s], "cbsa": sub_cbsa[s], "cbsa_title": title[sub_cbsa[s]], "name": curated.get(sid[s], nm),
                       "name_source": "curated" if sid[s] in curated else "automatic", "auto_name": nm, "pop2025": p,
                       "units": len(ks), "districts": len(ds), "district_view": p > VIEW_MIN, "work_inside": work_inside(ks)})
    sview = {r["subregion_id"]: r["district_view"] for r in rows_s}
    ndist = collections.Counter(region_cbsa[district_region[d]] for d in districts)
    for d, ks in districts.items():
        c = region_cbsa[district_region[d]]; p = sum(upop[k] for k in ks)
        s = sid.get(sub_of_district.get(d)) if c in big else None
        view = (sview[s] if s else ndist[c] >= 2)
        rows_d.append({"district_id": did[d], "cbsa": c, "cbsa_title": title[c], "subregion_id": s or "", "name": curated.get(did[d], gname(ks)),
                       "name_source": "curated" if did[d] in curated else "automatic", "auto_name": gname(ks),
                       "pop2025": p, "units": len(ks), "district_view": view, "work_inside": work_inside(ks),
                       "members": "; ".join(uname(k) for k in sorted(ks, key=lambda k: -upop[k]))})
    dview = {r["district_id"]: r["district_view"] for r in rows_d}
    for d, ks in districts.items():
        c = region_cbsa[district_region[d]]
        s = sid.get(sub_of_district.get(d)) if c in big else ""
        for k in sorted(ks):
            f = units[k]["county_fips"]
            xw.append({"unit_id": k, "unit_type": units[k]["unit_type"], "county_fips": f, "cbsa": c, "division": div_of.get(f, ""),
                       "csa": csa_of.get(f, ""), "subregion_id": s or "", "district_id": did[d], "district_view": dview[did[d]],
                       "pop2025": upop[k], "pieces_release": release})

    # checks
    bad = []
    for r in rows_d:
        if not (D_LO <= r["pop2025"] <= D_HI) and r["district_view"]:
            bad.append(("district size", r["district_id"], r["pop2025"]))
    for r in rows_s:
        if not (S_LO <= r["pop2025"] <= S_HI):
            bad.append(("subregion size", r["subregion_id"], r["pop2025"]))
    for name, groups, mem in (("district", districts, dmembers), ("subregion", subregions, smembers)):
        for g in groups:
            ks = mem(g); G0 = nx.Graph(); G0.add_nodes_from(ks); G0.add_edges_from((k, m) for k in ks for m in adj[k] if m in ks)
            if not nx.is_connected(G0):
                bad.append((name + " not contiguous", g, len(ks)))
    if len({r["unit_id"] for r in xw}) != len(cov_units) or len(xw) != len(cov_units):
        bad.append(("coverage", len(xw), len(cov_units)))

    for fn, rows in (("crosswalk_unit_metro.csv", xw), ("districts.csv", sorted(rows_d, key=lambda r: r["district_id"])),
                     ("subregions.csv", sorted(rows_s, key=lambda r: r["subregion_id"]))):
        with open(os.path.join(OUT, fn), "w", newline="") as fh:
            w = csv.DictWriter(fh, list(rows[0])); w.writeheader(); w.writerows(rows)
    with open(os.path.join(OUT, "metro_registry.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, ["id", "level", "cbsa", "anchor_unit", "status", "since_version"]); w.writeheader()
        w.writerows(sorted(registry, key=lambda r: r["id"]))
    for fn, groups, mem, rows, key in (("districts.geojson", districts, dmembers, rows_d, "district_id"),
                                       ("subregions.geojson", subregions, smembers, rows_s, "subregion_id")):
        props = {r[key]: r for r in rows}
        ids_ = did if key == "district_id" else sid
        feats = [{"type": "Feature", "properties": props[ids_[g]],
                  "geometry": bx_round(mapping(unary_union([geo[k].buffer(0.002) for k in mem(g)]).buffer(-0.002).simplify(0.001)))}
                 for g in groups]
        json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(OUT, fn), "w"), separators=(",", ":"))

    # unit shapes of the covered CBSAs, for the map's county and piece lines
    feats = [{"type": "Feature", "properties": {"unit_id": r["unit_id"], "name": uname(r["unit_id"]), "unit_type": r["unit_type"],
                                                "cbsa": r["cbsa"], "district_id": r["district_id"], "pop2025": r["pop2025"]},
              "geometry": bx_round(mapping(geo[r["unit_id"]].simplify(0.001)))} for r in xw]
    json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(OUT, "metro_units.geojson"), "w"), separators=(",", ":"))

    print(f"districts {len(rows_d)} ({sum(1 for r in rows_d if r['district_view'])} in the district view), "
          f"subregions {len(rows_s)}; LODES years {dict(collections.Counter(years.values()))}")
    missing = [r[k] for rows, k in ((rows_s, "subregion_id"), (rows_d, "district_id")) for r in rows if r["name_source"] == "automatic"]
    print(f"names: {len(rows_s) + len(rows_d) - len(missing)} curated, {len(missing)} automatic {missing[:10]}")
    for n in notes:
        print("  ", n)
    print("checks failed:", len(bad), bad[:8])


def bx_round(o):
    if isinstance(o, float):
        return round(o, 5)
    if isinstance(o, (list, tuple)):
        return [bx_round(x) for x in o]
    if isinstance(o, dict):
        return {k: bx_round(v) for k, v in o.items()}
    return o


if __name__ == "__main__":
    main()
