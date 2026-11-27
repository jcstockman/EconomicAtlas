"""Group units into county pieces for every county with 1.0M+ residents (docs/specs/county-pieces.md, rules 1, 3, 4, 9).

Units per county:
  official  - the county's planning or statistical division (OFFICIAL below); units over the cap are split into tracts
  ccd       - Census 2020 county subdivisions, used for a new county when every CCD fits under the cap (rule 9)
  inferred  - incorporated places kept whole (unless over the cap) plus remaining tracts (rule 4)
Graph: LODES OD (main, JT00, S000) commuting between units, both ends in the county, symmetric.
Adjacency: shoreline-clipped land polygons (cb_2020_us_tract_500k); an island unit links to its nearest unit.
Job centres (rule 12): dense LODES job cores and the named KEEP districts are contracted into one node, so no piece
line cuts them. APART anchor sets go to different pieces.
Search: Louvain (networkx) over resolutions and seeds, split into contiguous parts, merged to the target count, refined
by single-unit moves within the build limits LO-HI (2025 estimate), rebalanced where a piece falls outside them.
Score = modularity - MU x share of internal boundary cut (compactness; boundaries inside one 2020 PUMA count PUMA_WEIGHT
times, so lines follow PUMA lines where commuting allows). The best-scoring grouping whose tract assignment is
contiguous and has no neck narrower than ~2 x NECK wins.

usage: python3 build_groups.py --cache DIR [--fips ...]
Writes groups.json next to this script (read by build_crosswalk.py).
"""
import argparse, collections, csv, gzip, json, math, os, sys, urllib.request

import networkx as nx
from shapely.geometry import Point, shape
from shapely.strtree import STRtree
from shapely.validation import make_valid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_crosswalk as bx  # noqa: E402  (shared loaders and caches)

HERE = os.path.dirname(os.path.abspath(__file__))
MIN_COUNTY = 920_000
TARGET, LO, HI = 800_000, 460_000, 1_070_000  # rule 1: about 0.8M within 0.45-1.1M; build limits leave margin
# rule 1a (release 1.2): a 0.9M cap (build 0.88M) where a trial showed more even pieces with equal or better commuting,
# demographic and geographic coherence (docs/specs/county-pieces.md, Cap 0.9M)
CAP = {"53033": 880_000, "48439": 880_000, "06059": 880_000, "48201": 880_000, "06073": 880_000, "12086": 880_000,
       "17031": 880_000, "12099": 880_000}  # Cook and Palm Beach since release 1.3
ST = {"06": "ca", "48": "tx", "17": "il", "12": "fl", "36": "ny", "53": "wa", "42": "pa", "25": "ma", "26": "mi", "04": "az",
      "32": "nv", "39": "oh", "27": "mn", "37": "nc", "49": "ut", "51": "va", "13": "ga", "24": "md", "09": "ct", "18": "in",
      "29": "mo", "15": "hi", "34": "nj", "55": "wi"}
LODES_YEAR = {"mi": "2021"}
AG = bx.AG
BRONX_MERGE = {"BX26": "BX08", "BX27": "BX11", "BX28": "BX10", "QN01": "BX02"}  # parks; Rikers Island (CDTA QN01) -> Hunts Point


def cook_units():
    ca = bx.poly(bx.socrata("https://data.cityofchicago.org/resource/igwz-8jzy.geojson?$limit=200"),
                 lambda p: "Chicago: " + p["community"].title())
    sub = bx.poly(bx.socrata("https://datacatalog.cookcountyil.gov/resource/tvy4-qfgw.geojson?$limit=5000"), lambda p: p["city"])
    return ca + sub


def nyc(co):
    rows = bx.cached("nyc-eq", lambda: bx._open("https://data.cityofnewyork.us/resource/hm78-6dwm.json?$limit=5000"),
                     "https://data.cityofnewyork.us/resource/hm78-6dwm.json")
    name = {r["cdtacode"]: r["cdtaname"].split(" (")[0][5:] for r in rows}
    merge = dict(bx.NYC_MERGE, **(BRONX_MERGE if co == "005" else {}))
    if co != "005":
        merge.pop("QN01", None)
    if co == "061":
        merge["BX08"] = "MN12"
    ov = {r["geoid"]: merge.get(r["cdtacode"], r["cdtacode"]) for r in rows if r["countyfips"] == co}
    return ov, {k: f"{k} {name.get(k, k)}" for k in set(ov.values())}


# fips: (source_id, loader returning [(unit, geom)] or None, override loader returning ({tract: unit}, {unit: label}) or None)
OFFICIAL = {
    "06037": ("lacdph_hd_2022", lambda: bx.poly(bx.arcgis(AG + "RmCCgQtiZLDCtblq/ArcGIS/rest/services/Health_Districts_2022_view/FeatureServer/0"), lambda p: p["HD_NAME"]), None),
    "17031": ("chicago_ca_ccdph_municipalities", cook_units, None),
    "06073": ("sandag_sra_2020", lambda: bx.poly(bx.arcgis("https://geo.sandag.org/server/rest/services/Hosted/Subregional_Areas_2020/FeatureServer/0"), lambda p: p["name"].title()), None),
    "12086": ("miamidade_minor_statistical_areas", lambda: bx.poly(bx.arcgis(AG + "8Pc9XBTAsYuxx9Ny/arcgis/rest/services/MinorStatisticalArea_gdb/FeatureServer/0"), lambda p: f"MSA {float(p['ID']):.1f}"), None),
    "36047": ("nyc_dcp_cdta_2020", None, lambda: nyc("047")),
    "36081": ("nyc_dcp_cdta_2020", None, lambda: nyc("081")),
    "36061": ("nyc_dcp_cdta_2020", None, lambda: nyc("061")),
    "36005": ("nyc_dcp_cdta_2020", None, lambda: nyc("005")),
    "53033": ("phskc_hra_2020", lambda: bx.poly(bx.arcgis(AG + "Ej0PsM5Aw677QF1W/arcgis/rest/services/HEALTH_REPORTING_2020_AREA_2919/FeatureServer/0"), lambda p: p["name"]), None),
    "06085": ("mtc_superdistricts_taz1454", lambda: bx.poly(bx.arcgis("https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/Travel_Analysis_Zones/FeatureServer/0"), lambda p: f"SD {p['SUPERD']}"), None),
    "06067": ("sacog_rad_2007", lambda: bx.poly(bx.arcgis("https://services6.arcgis.com/YBp5dUuxCMd8W1EI/arcgis/rest/services/Regional_Analysis_Districts_2007/FeatureServer/0"), lambda p: p["RAD07_desp"]), None),
    "42101": ("phila_planning_districts", lambda: bx.poly(bx.arcgis(AG + "fLeGjb7u4uXqeF9q/arcgis/rest/services/Planning_Districts/FeatureServer/0"), lambda p: p["dist_name"]), None),
    "26163": ("census_cousub_2020", lambda: bx.ccd("26163", lambda v: v.replace(" city", "").replace(" charter township", " Twp").replace(" township", " Twp")), None),
    "25017": ("census_cousub_2020", lambda: bx.ccd("25017", lambda v: v.replace(" Town", ""), "BASENAME"), None),
    "36103": ("census_cousub_2020", lambda: bx.ccd("36103", lambda v: v.replace(" town", "")), None),
}
for _f in ("06065", "06071", "06001", "48439", "48029", "12011", "12099", "12057", "12095"):
    OFFICIAL[_f] = ("census_ccd_2020", (lambda f: lambda: bx.ccd(f))(_f), None)
INFERRED = {"48201", "48113", "32003", "04013", "06059"}  # no official division fits (spec: Inferred counties)
# Rule 12: job centres stay in one piece. Data-driven cores (below) plus these named districts, each kept whole:
# ("place", names) = every tract in those places/CDPs; ("points", [(lon, lat)]) = the tracts containing the points.
KEEP = {
    "32003": [("Las Vegas Strip and airport (Paradise)", "place", ["Paradise CDP"])],
    "12086": [("Downtown Miami and Brickell", "points", [(-80.1918, 25.7743), (-80.1937, 25.7617), (-80.1960, 25.7550), (-80.1890, 25.7820),
                                                          (-80.2196, 25.7655), (-80.2890, 25.7620)])],  # with Little Havana and Flagami (1.2)
    "17031": [("Austin with Oak Park", "points", [(-87.7656, 41.8940), (-87.7845, 41.8850)]),
              ("Ashburn and West Lawn with Beverly", "points", [(-87.7110, 41.7470), (-87.7225, 41.7725), (-87.6770, 41.7180)]),
              ("Lincoln Square with North Center", "points", [(-87.6890, 41.9750), (-87.6800, 41.9480)])],
    "12099": [("West Boca, Delray and Boynton with South County", "points", [(-80.1918, 26.3587), (-80.1500, 26.3600)])],
    "06073": [("Escondido and its backcountry", "points", [(-117.0864, 33.1192), (-117.0342, 33.2184), (-116.9800, 33.3000)])],
    "48113": [("Downtown Dallas and the Park Cities", "place", ["Highland Park town", "University Park city"]),
              ("Downtown Dallas and the Park Cities", "points", [(-96.7970, 32.7767), (-96.8000, 32.7900)])],
    "48201": [("Memorial Villages", "place", ["Bunker Hill Village city", "Hedwig Village city", "Hilshire Village city",
                                              "Hunters Creek Village city", "Piney Point Village city", "Spring Valley Village city"])],
}
# Anchor sets for counties where commuting alone draws a line across a strong local divide: the tracts holding each
# set's points stay in one piece, and different sets go to different pieces.
APART = {
    "17031": [  # release 1.3: under the 0.9M cap the North Shore and the West Side otherwise share a piece
        ("North Shore", [(-87.6877, 42.0451), (-87.7320, 42.0750)]),
        ("West Side", [(-87.7200, 41.9020), (-87.7190, 41.8600)]),
    ],
    "06037": [  # San Gabriel Mountains / Newhall Pass: North County apart from the San Fernando Valley
        ("North County (Santa Clarita and Antelope Valley)", [(-118.5400, 34.3900), (-118.1200, 34.5800), (-118.1500, 34.7000)]),
        ("Northeast San Fernando Valley", [(-118.4400, 34.2800), (-118.4100, 34.2600)]),
    ],
    "42003": [  # Allegheny and Ohio rivers: north of the rivers apart from south and west
        ("North Hills", [(-80.1845, 40.5367), (-80.0517, 40.4937), (-79.9600, 40.5700)]),
        ("South and West Hills", [(-80.0400, 40.3300), (-80.2100, 40.5100), (-80.1667, 40.5184)]),
    ],
    "48113": [  # Trinity River / I-30: north, south and west, east
        ("North Dallas", [(-96.8030, 32.8800), (-96.8000, 32.9600), (-96.7300, 32.9480), (-96.8900, 32.9800)]),
        ("South and West Dallas County", [(-96.8370, 32.7400), (-96.8570, 32.5900), (-97.0000, 32.7200), (-96.9490, 32.8140)]),
        ("East Dallas County", [(-96.6400, 32.9100), (-96.6000, 32.7700), (-96.6920, 32.7100)]),
    ],
}
SPLIT = {"06037": ["San Fernando"]}  # official units split into tracts even under the cap (San Fernando HD spans the mountains)
# Counties of 1.0-1.25M with no natural two-way split stay one piece (rule 1 exception; review 2026-11-22):
WHOLE = {"48157": "most workers leave for Houston; no split inside the county has a commuting basis",
         "53053": "no two contiguous pieces of 0.46M+ exist (Tacoma and its suburbs hold most residents)",
         "06029": "a split cuts Bakersfield and leaves a long desert and mountain piece",
         "48215": "a split cuts the one continuous McAllen-Edinburg urban area",
         "17043": "the township split is irregular and keeps little commuting inside (26-27%)", "06013": "Mount Diablo divides any split", "04019": "a split rings Tucson", "06019": "a split joins Clovis to the Sierra",
         "13135": "no split avoids a pinch"}
CORE_DENSITY, CORE_JOBS = 10_000, 40_000  # jobs per km2 of land, jobs per core (LODES WAC 2024)
MU = 1.0       # weight of boundary length (compactness) against modularity
PUMA_WEIGHT = 3.0  # a boundary between two tracts of the same 2020 PUMA counts this many times (pieces follow PUMA lines)
NECK = 0.0035  # degrees (~350 m): a piece whose body splits when shrunk this much is joined by a neck < ~700 m
UNIT_NAMES = {"09110", "34003", "06037", "17031", "06073", "36047", "36081", "36061", "36005", "53033", "06067", "42101", "26163", "25017", "36103"}


class Part:
    """Partition of units with incremental undirected modularity and size/contiguity limits."""

    def __init__(self, G, upop, adj, scale, L=None):
        self.G, self.upop, self.adj, self.scale = G, upop, adj, scale
        self.deg = dict(G.degree(weight="weight")); self.m2 = sum(self.deg.values()) or 1
        self.L = L or collections.defaultdict(dict)  # shared boundary length between adjacent units
        self.apart = set()
        self.Ltot = sum(w for a in self.L for w in self.L[a].values()) / 2 or 1

    def cut(self, comms):
        """Share of internal unit boundary that lies between pieces (lower = more compact pieces)."""
        where = {u: i for i, c in enumerate(comms) for u in c}
        return sum(w for a in self.L for b, w in self.L[a].items() if a < b and where.get(a) != where.get(b)) / self.Ltot

    def score(self, comms):
        return self.q(comms) - MU * self.cut(comms)

    def q(self, comms):
        return nx.algorithms.community.modularity(self.G, comms, weight="weight")

    def size(self, c):
        return sum(self.upop[u] for u in c) * self.scale

    def connected(self, c):
        c = set(c)
        if not c:
            return False
        s = next(iter(c)); seen = {s}; st = [s]
        while st:
            x = st.pop()
            for y in self.adj[x]:
                if y in c and y not in seen:
                    seen.add(y); st.append(y)
        return seen == c

    def components(self, c):
        c = set(c); out = []
        while c:
            s = c.pop(); seen = {s}; st = [s]
            while st:
                x = st.pop()
                for y in self.adj[x]:
                    if y in c and y not in seen:
                        seen.add(y); c.discard(y); st.append(y)
            out.append(seen)
        return out

    def link(self, a, b):
        return sum(self.G[u][v]["weight"] for u in a for v in self.G[u] if v in b)

    def merge_to(self, comms, k):
        """Merge adjacent groups down to k: first never over the cap, then absorbing under-floor groups, then by
        modularity gain. Keeps group-to-group weights and adjacency incrementally."""
        comms = {i: set(c) for i, c in enumerate(comms)}
        where = {u: i for i, c in comms.items() for u in c}
        W = collections.defaultdict(lambda: collections.defaultdict(float))
        A = collections.defaultdict(set)
        for u, v, d in self.G.edges(data=True):
            a, b = where[u], where[v]
            if a != b:
                W[a][b] += d["weight"]; W[b][a] += d["weight"]
        LB = collections.defaultdict(lambda: collections.defaultdict(float))
        for u in self.L:
            for v, w in self.L[u].items():
                if u in where and v in where and where[u] != where[v]:
                    LB[where[u]][where[v]] += w
        for u in where:
            for v in self.adj[u]:
                if v in where and where[v] != where[u]:
                    A[where[u]].add(where[v])
        D = {i: sum(self.deg.get(u, 0) for u in c) for i, c in comms.items()}
        S = {i: self.size(c) for i, c in comms.items()}
        AN = {i: bool(self.apart & c) for i, c in comms.items()}
        while len(comms) > k:
            best = None
            for a in comms:
                for b in A[a]:
                    if b <= a or (AN[a] and AN[b]):
                        continue
                    over = max(0, S[a] + S[b] - HI)
                    small = 0 if min(S[a], S[b]) < LO else 1
                    gain = 2 * W[a][b] / self.m2 - 2 * D[a] * D[b] / self.m2 ** 2 + MU * LB[a][b] / self.Ltot
                    key = (over, small, -gain)
                    if best is None or key < best[0]:
                        best = (key, a, b)
            if best is None:
                return None
            _, a, b = best
            comms[a] |= comms.pop(b); D[a] += D.pop(b); S[a] += S.pop(b); AN[a] = AN[a] or AN.pop(b)
            for c, w in W.pop(b, {}).items():
                if c != a:
                    W[a][c] += w; W[c][a] += w
                W[c].pop(b, None)
            W[a].pop(a, None)
            for c, w in LB.pop(b, {}).items():
                if c != a:
                    LB[a][c] += w; LB[c][a] += w
                LB[c].pop(b, None)
            LB[a].pop(a, None)
            for c in A.pop(b, set()):
                if c != a:
                    A[a].add(c); A[c].add(a)
                A[c].discard(b)
            A[a].discard(a)
        return list(comms.values())

    def clash(self, c):
        return len(self.apart & set(c)) > 1

    def split_apart(self, comms):
        """Split any group holding more than one APART anchor: each unit joins the anchor nearest by adjacency."""
        out = []
        for c in comms:
            c = set(c); anc = list(self.apart & c)
            if len(anc) <= 1:
                out.append(c); continue
            owner = {a: a for a in anc}; frontier = list(anc)
            while frontier:
                nxt = []
                for x in frontier:
                    for y in self.adj[x]:
                        if y in c and y not in owner:
                            owner[y] = owner[x]; nxt.append(y)
                frontier = nxt
            for a in anc:
                out.append({u for u in c if owner.get(u) == a})
            rest = {u for u in c if u not in owner}
            if rest:
                out.append(rest)
        return [x for c in out for x in self.components(c)]

    def penalty(self, comms):
        if any(self.clash(c) for c in comms):
            return 1e6
        return sum(max(0, LO - self.size(c)) + max(0, self.size(c) - HI) for c in comms) / 1e6

    def rebalance(self, comms, max_rounds=200):
        """Fix pieces outside LO-HI by shifting boundary units along a chain of neighbouring pieces to the nearest
        piece with room (or surplus), each hop moving the units that cost the least within-piece commuting."""
        comms = [set(c) for c in comms]
        for _ in range(max_rounds):
            sizes = [self.size(c) for c in comms]
            bad = [i for i, x in enumerate(sizes) if x < LO or x > HI]
            if not bad:
                return comms
            v = bad[0]; under = sizes[v] < LO
            need = (LO - sizes[v]) if under else (sizes[v] - HI)
            nb = lambda i: {j for j, c in enumerate(comms) if j != i and any(self.adj[u] & c for u in comms[i])}
            # breadth-first search to a piece that can give (under) or take (over) `need` residents
            prev = {v: None}; queue = [v]; found = None
            while queue and found is None:
                i = queue.pop(0)
                for j in nb(i):
                    if j in prev:
                        continue
                    prev[j] = i
                    if (under and sizes[j] - need >= LO) or (not under and sizes[j] + need <= HI):
                        found = j; break
                    queue.append(j)
            if found is None:
                return comms
            path = [found]
            while prev[path[-1]] is not None:
                path.append(prev[path[-1]])
            # path runs donor ... v (under) or v ... receiver after reversal (over)
            hops = list(zip(path[:-1], path[1:])) if under else list(zip(reversed(path[1:]), reversed(path[:-1])))
            for a, b in hops:  # move `need` residents from a to b
                moved = 0.0
                while moved < need:
                    cand = [u for u in comms[a] if self.adj[u] & comms[b]]
                    best = None
                    for u in cand:
                        rest = self.components(comms[a] - {u})
                        if not rest:
                            continue
                        rest.sort(key=lambda c: -self.size(c))
                        grp = {u}.union(*rest[1:])  # u plus any branch that hangs off it moves together
                        g = self.size(grp)
                        if g > need - moved + 40_000:  # no overshoot: each hop moves about `need`
                            continue
                        if self.apart & grp and self.apart & comms[b]:
                            continue
                        loss = sum(d["weight"] for x in grp for w, d in self.G[x].items() if w in comms[a] and w not in grp) \
                            - sum(d["weight"] for x in grp for w, d in self.G[x].items() if w in comms[b])
                        if best is None or loss < best[0]:
                            best = (loss, grp, g)
                    if best is None:
                        break
                    comms[a] -= best[1]; comms[b] |= best[1]; moved += best[2]
        return comms

    def refine(self, comms, lam=5.0, max_moves=50000):
        comms = [set(c) for c in comms]
        where = {u: i for i, c in enumerate(comms) for u in c}
        D = [sum(self.deg.get(u, 0) for u in c) for c in comms]
        P = [self.size(c) for c in comms]
        kin = lambda u, i: sum(d["weight"] for v, d in self.G[u].items() if where.get(v) == i and v != u)
        lin = lambda u, i: sum(w for v, w in self.L.get(u, {}).items() if where.get(v) == i)
        pen = lambda sz: (max(0, LO - sz) + max(0, sz - HI)) / 1e6
        improved, n = True, 0
        while improved and n < max_moves:
            improved = False
            for u in list(where):
                i = where[u]
                targets = {where[v] for v in self.adj[u]} - {i}
                if not targets or len(comms[i]) == 1:
                    continue
                du = self.deg.get(u, 0); pu = self.upop[u] * self.scale
                best = None
                for j in targets:
                    if u in self.apart and self.apart & comms[j]:
                        continue
                    dq = 2 * (kin(u, j) - kin(u, i)) / self.m2 + 2 * du * (D[i] - du - D[j]) / self.m2 ** 2
                    dp = pen(P[i] - pu) + pen(P[j] + pu) - pen(P[i]) - pen(P[j])
                    score = dq + MU * (lin(u, j) - lin(u, i)) / self.Ltot - lam * dp
                    if score > 1e-9 and (best is None or score > best[0]):
                        best = (score, j)
                if best is None or not self.connected(comms[i] - {u}):
                    continue
                j = best[1]
                comms[i].discard(u); comms[j].add(u); where[u] = j
                D[i] -= du; D[j] += du; P[i] -= pu; P[j] += pu
                improved = True; n += 1
        return comms


def county_list(cache):
    p = os.path.join(cache, "co-est2025-alldata.csv")
    p = bx.fetch("https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/counties/totals/co-est2025-alldata.csv")
    rows = [r for r in csv.DictReader(open(p, encoding="latin-1")) if r["SUMLEV"] == "050" and int(r["POPESTIMATE2025"]) >= MIN_COUNTY]
    return {r["STATE"] + r["COUNTY"]: (f"{r['CTYNAME'].replace(' County', '')}, {r['STNAME']}", int(r["POPESTIMATE2025"])) for r in rows}


def target(p25):
    k = max(round(p25 / TARGET), math.ceil(p25 / HI), 2)
    return max(2, min(k, p25 // LO))  # no more pieces than the floor allows


def places(fips, bbox, layer):
    f = bx.cached(f"places{layer}-{fips}", lambda: _places(fips[:2], bbox, layer), f"{bx.TG}{layer} state {fips[:2]} near county {fips}")
    return [(x["properties"]["NAME"], make_valid(shape(x["geometry"]))) for x in f if x.get("geometry")]


def _places(st, bbox, layer):
    import urllib.parse
    minx, miny, maxx, maxy = bbox; out, off = [], 0
    while True:
        q = {"where": f"STATE='{st}'", "outFields": "NAME,POP100", "outSR": 4326, "f": "geojson", "geometry": f"{minx},{miny},{maxx},{maxy}",
             "geometryType": "esriGeometryEnvelope", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "resultOffset": off, "resultRecordCount": 1000}
        d = bx._open(bx.TG + str(layer) + "/query?" + urllib.parse.urlencode(q)); fs = d.get("features", []); out += fs
        if len(fs) < 1000:
            return out
        off += len(fs)


def tract_flows(fips, cache):
    st = ST[fips[:2]]; yr = LODES_YEAR.get(st, "2024")
    p = os.path.join(cache, f"{st}_od_main_JT00_{yr}.csv.gz")
    p = bx.fetch(f"https://lehd.ces.census.gov/data/lodes/LODES8/{st}/od/{st}_od_main_JT00_{yr}.csv.gz")
    F = collections.Counter()
    with gzip.open(p, "rt") as fh:
        r = csv.reader(fh); next(r)
        for w, h, n, *_ in r:
            if h[:2] == fips[:2] and bx.cty(h) == fips and bx.cty(w) == fips:
                F[(h[:11], w[:11])] += int(n)
    return F


def exhaustive(P, units, k):
    """Every labelling of units into k pieces (first unit fixed); the 300 valid ones with the best score."""
    import itertools
    idx = {u: i for i, u in enumerate(units)}
    edges = [(idx[a], idx[b], d["weight"]) for a, b, d in P.G.edges(data=True)]
    deg = [P.deg.get(u, 0) for u in units]; m2 = P.m2
    out = []
    for lab in itertools.product(range(k), repeat=len(units) - 1):
        lab = (0,) + lab
        if len(set(lab)) < k:
            continue
        parts = [{u for u, l in zip(units, lab) if l == i} for i in range(k)]
        if P.penalty(parts) > 0 or not all(P.connected(x) for x in parts):
            continue
        win = sum(2 * w for a, b, w in edges if lab[a] == lab[b])  # networkx: self-loop counts once in L_c, L_c/m = 2w/m2
        dsum = [0.0] * k
        for i, d in enumerate(deg):
            dsum[lab[i]] += d
        q = win / m2 - sum((x / m2) ** 2 for x in dsum)
        out.append((q - MU * P.cut(parts), q, parts))
    return sorted(out, key=lambda x: -x[0])[:300]


def build(fips, cache, name, p25, fallback=False):
    global HI
    saved = HI
    HI = CAP.get(fips, HI)
    try:
        return _build(fips, cache, name, p25, fallback)
    finally:
        HI = saved


def _build(fips, cache, name, p25, fallback=False):
    tr = {t["properties"]["GEOID"]: t["properties"] for t in bx.tracts(fips)}
    land = bx.land_tracts({fips})
    pop = {g: p["POP100"] for g, p in tr.items()}
    scale = p25 / sum(pop.values())
    pt = {g: Point(float(p["INTPTLON"]), float(p["INTPTLAT"])) for g, p in tr.items()}
    gids = [g for g in tr if g in land]  # water-only tracts have no land; build_crosswalk places them
    bbox = (min(land[g].bounds[0] for g in gids), min(land[g].bounds[1] for g in gids), max(land[g].bounds[2] for g in gids), max(land[g].bounds[3] for g in gids))
    cities = places(fips, bbox, 26); cdps = places(fips, bbox, 28)
    ctree = STRtree([g for _, g in cities]); dtree = STRtree([g for _, g in cdps])
    city_of = {g: next((cities[i][0] for i in ctree.query(pt[g]) if cities[i][1].contains(pt[g])), None) for g in gids}
    cdp_of = {g: next((cdps[i][0] for i in dtree.query(pt[g]) if cdps[i][1].contains(pt[g])), None) for g in gids}

    if fips in WHOLE:  # one piece: the whole county
        assign = {g: (0, "nested", 1.0) for g in gids}
        cnt = collections.Counter((city_of[g] or cdp_of[g] or "unincorporated").replace(" city", "").replace(" CDP", "") for g in gids)
        p20 = sum(pop[g] for g in gids)
        print(f"{fips} {name}: whole county ({WHOLE[fips]})", flush=True)
        return {"fips": fips, "county": name, "method": "whole", "source_id": "whole_county", "k": 1, "modularity": 0.0,
                "boundary_cut": 0.0, "job_centres": [], "resolution": None, "seed": None, "units": 1, "split_units": [],
                "pieces": [{"name": " / ".join(n for n, _ in cnt.most_common(3)), "units": [], "tracts": sorted(gids),
                            "pop2020": p20, "pop2025_est": round(p20 * scale)}], "assign": assign, "splits": []}
    method, source, labels = "inferred", "lodes_2024_louvain", {}
    unit_of = None; units = None
    if fips in OFFICIAL and not fallback:
        source, loader, override = OFFICIAL[fips]; method = "official"
        if override:
            ov, labels = override(); unit_of = {g: ov[g] for g in gids if g in ov}
            for g in gids:  # land tracts missing from the equivalency (none expected) go by nearest assigned tract
                if g not in unit_of:
                    unit_of[g] = unit_of[min(unit_of, key=lambda h: pt[h].distance(pt[g]))]
        else:
            units = loader(); utree = STRtree([u[1] for u in units])
            unit_of = {}
            for g in gids:
                hit = [units[i][0] for i in utree.query(pt[g]) if units[i][1].contains(pt[g])]
                unit_of[g] = hit[0] if hit else min(units, key=lambda u: u[1].distance(pt[g]))[0]
    elif fips not in INFERRED and not fallback:  # new county: CCDs if every CCD fits, else inferred
        units = bx.ccd(fips); utree = STRtree([u[1] for u in units]); uo = {}
        for g in gids:
            hit = [units[i][0] for i in utree.query(pt[g]) if units[i][1].contains(pt[g])]
            uo[g] = hit[0] if hit else min(units, key=lambda u: u[1].distance(pt[g]))[0]
        size = collections.Counter()
        for g, u in uo.items():
            size[u] += pop[g]
        if len(size) >= 2 and max(size.values()) * scale <= HI:
            unit_of, method, source = uo, "official", "census_ccd_2020"
        else:
            units = None
    if unit_of is None:  # inferred: places whole unless over the cap, else tracts
        cp = collections.Counter(city_of[g] for g in gids if city_of[g])
        cp = {c: sum(pop[g] for g in gids if city_of[g] == c) for c in cp}
        whole = HI if fallback != 2 else 0  # last resort: every tract its own unit
        unit_of = {g: (city_of[g] if city_of[g] and cp[city_of[g]] * scale <= whole else "T:" + g) for g in gids}
    # oversize official units are split into tracts
    usize = collections.Counter()
    for g, u in unit_of.items():
        usize[u] += pop[g]
    split_units = sorted(u for u, s in usize.items() if (s * scale > HI or u in SPLIT.get(fips, ())) and not u.startswith("T:"))
    for g in gids:
        if unit_of[g] in split_units:
            unit_of[g] = "T:" + g
    upop = collections.Counter()
    for g, u in unit_of.items():
        upop[u] += pop[g]
    # adjacency on land
    ttree = STRtree([land[g].buffer(0.0005) for g in gids]); adj = collections.defaultdict(set)
    for i, g in enumerate(gids):
        for j in ttree.query(land[g].buffer(0.0005), predicate="intersects"):  # true touches, not bounding boxes
            h = gids[j]
            if unit_of[h] != unit_of[g]:
                adj[unit_of[g]].add(unit_of[h]); adj[unit_of[h]].add(unit_of[g])
    ugeo = collections.defaultdict(list)
    for g in gids:
        ugeo[unit_of[g]].append(land[g])
    G0 = nx.Graph(); G0.add_nodes_from(upop); G0.add_edges_from((a, b) for a in adj for b in adj[a])
    comps = sorted(nx.connected_components(G0), key=lambda c: -sum(upop[u] for u in c))
    for c in comps[1:]:  # islands: link to the nearest unit outside the component
        from shapely.ops import unary_union
        cg = unary_union([x for u in c for x in ugeo[u]])
        near = min((u for u in upop if u not in c), key=lambda u: min(cg.distance(x) for x in ugeo[u]))
        a = min(c, key=lambda u: min(x.distance(y) for x in ugeo[u] for y in ugeo[near]))
        adj[a].add(near); adj[near].add(a)
    F = tract_flows(fips, cache)
    G = nx.Graph(); G.add_nodes_from(upop)
    for (h, w), n in F.items():
        a, b = unit_of.get(h), unit_of.get(w)
        if a and b:
            G.add_edge(a, b, weight=G[a][b]["weight"] + n if G.has_edge(a, b) else n)
    # shared boundary length between units (for compactness), from overlapping ~50 m buffers of land polygons
    puma = puma_of()
    buf = [land[g].buffer(0.0005) for g in gids]; L = collections.defaultdict(lambda: collections.defaultdict(float))
    tadj = collections.defaultdict(set)
    for i, g in enumerate(gids):
        for j in ttree.query(buf[i], predicate="intersects"):
            h = gids[j]
            if j <= i:
                continue
            tadj[g].add(h); tadj[h].add(g)
            if unit_of[h] != unit_of[g]:
                w = buf[i].intersection(buf[j]).area / 0.001 * (PUMA_WEIGHT if puma.get(g) and puma.get(g) == puma.get(h) else 1.0)
                L[unit_of[g]][unit_of[h]] += w; L[unit_of[h]][unit_of[g]] += w
    # rule 12: job centres stay whole; units holding one are contracted into a single node for the search
    locks = job_cores(fips, gids, land, tadj, unit_of, upop, scale, pop)
    for label, kind, what in KEEP.get(fips, []) + [(l, "points", pts) for l, pts in APART.get(fips, [])]:
        if kind == "place":
            tg = {g for g in gids if city_of[g] in what or cdp_of[g] in what}
        else:
            tg = {g for g in gids for x, y in what if land[g].contains(Point(x, y))}
        same = [i for i, (l, _) in enumerate(locks) if l == label]  # entries with one label form one group
        if same:
            locks[same[0]] = (label, locks[same[0]][1] | tg)
        else:
            locks.append((label, tg))
    rep = {u: u for u in upop}
    def find(u):
        while rep[u] != u:
            u = rep[u]
        return u
    for label, tg in locks:
        us = sorted({unit_of[g] for g in tg})
        for u in us[1:]:
            rep[find(u)] = find(us[0])
    members = collections.defaultdict(set)
    for u in upop:
        members[find(u)].add(u)
    node = {u: (r if len(members[r]) == 1 else "K:" + r) for r in members for u in members[r]}
    lock_report = [(label, len({unit_of[g] for g in tg}), round(sum(pop[g] for g in tg) * scale), sorted(tg)) for label, tg in locks]
    upopC = collections.Counter(); adjC = collections.defaultdict(set); LC = collections.defaultdict(lambda: collections.defaultdict(float))
    for u, n in upop.items():
        upopC[node[u]] += n
    for u in adj:
        for v in adj[u]:
            if node[u] != node[v]:
                adjC[node[u]].add(node[v])
    for u in L:
        for v, w in L[u].items():
            if node[u] != node[v]:
                LC[node[u]][node[v]] += w
    GC = nx.Graph(); GC.add_nodes_from(upopC)
    for u, v, d in G.edges(data=True):
        a, b = node[u], node[v]
        GC.add_edge(a, b, weight=GC[a][b]["weight"] + d["weight"] if GC.has_edge(a, b) else d["weight"])
    expand = lambda parts: [set().union(*({u for u in upop if node[u] == x} for x in c)) for c in parts]
    k = target(p25)
    P = Part(GC, dict(upopC), adjC, scale, LC)
    for label, tg in locks:
        if label in {l for l, _ in APART.get(fips, [])}:
            P.apart.add(node[unit_of[next(iter(tg))]])
    best = None; cands = []
    starts = [(r, seed, None) for r in (0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0) for seed in range(5)]
    if len(upopC) <= 400:
        starts.append(("singletons", 0, [{u} for u in upopC]))  # every unit alone, merged down to k
    for r, seed, given in starts:
        comms = given if given is not None else nx.algorithms.community.louvain_communities(GC, weight="weight", resolution=r, seed=seed)
        parts = P.split_apart([x for c in comms for x in P.components(c)])
        if len(parts) < k:
            continue
        parts = P.merge_to(parts, k)
        if parts is None:
            continue
        parts = P.refine(parts)
        if P.penalty(parts) > 0:
            bal = P.rebalance(parts); parts = P.refine(bal)
            if P.penalty(parts) > 0:
                parts = bal
        if P.penalty(parts) == 0 and all(P.connected(x) for x in parts):
            sc = P.score(parts)
            cands.append((sc, P.q(parts), parts, r, seed))
    if k ** len(upopC) <= 2_000_000:  # small unit sets: exhaustive search over every grouping
        cands += [(sc, q, parts, "exhaustive", 0) for sc, q, parts in exhaustive(P, sorted(upopC), k)]
    if not cands:
        if method == "official" and not fallback:
            print(f"{fips} {name}: no valid grouping of {source} units for k={k}; falling back to places + tracts", flush=True)
            return build(fips, cache, name, p25, fallback=True)
        if fallback != 2:
            print(f"{fips} {name}: no valid grouping with whole places for k={k}; trying tracts only", flush=True)
            return build(fips, cache, name, p25, fallback=2)
        raise SystemExit(f"{fips} {name}: no valid partition for k={k}")
    # best score (modularity minus boundary length) whose tract assignment is contiguous and has no narrow necks
    seen = set(); ranked = []
    for c in sorted(cands, key=lambda c: -c[0]):
        key = frozenset(frozenset(x) for x in c[2])
        if key not in seen:
            seen.add(key); ranked.append(c)
    chosen = None; fallback_pick = None
    for sc, q, parts, r, seed in ranked[:60]:
        parts = sorted(expand(parts), key=lambda c: -sum(upop[u] for u in c))
        assign, splits = final_assignment(fips, gids, pop, unit_of, units if method == "official" else None, parts, split_units)
        if not contiguous(assign, land, pop):
            continue
        nk = necks(assign, land, pop)
        if not nk:
            chosen = (sc, q, parts, r, seed, assign, splits); break
        if fallback_pick is None:
            fallback_pick = (sc, q, parts, r, seed, assign, splits, nk)
    if chosen is None:
        if fallback_pick is None:
            raise SystemExit(f"{fips} {name}: no contiguous candidate")
        print(f"  {fips}: WARNING every contiguous candidate has a neck; keeping the best (pieces {fallback_pick[7]})", flush=True)
        chosen = fallback_pick[:7]
    sc, q, parts, r, seed, assign, splits = chosen
    pieces = []
    for c in parts:
        tg = [g for g in gids if unit_of[g] in c]
        if fips in UNIT_NAMES:
            cnt = collections.Counter()
            for g in tg:
                u = unit_of[g]
                cnt[labels.get(u, u) if not u.startswith("T:") else
                    (city_of[g] or cdp_of[g] or "unincorporated").replace(" city", "").replace(" town", "").replace(" CDP", "").replace(" village", "")] += pop[g]
        else:
            cnt = collections.Counter()
            for g in tg:
                cnt[(city_of[g] or cdp_of[g] or "unincorporated").replace(" city", "").replace(" town", "").replace(" CDP", "").replace(" village", "")] += pop[g]
        nm = " / ".join(n for n, _ in cnt.most_common(3))
        pieces.append({"name": nm, "units": sorted(u for u in c if not u.startswith("T:")), "tracts": sorted(tg),
                       "pop2020": sum(pop[g] for g in tg), "pop2025_est": round(sum(pop[g] for g in tg) * scale)})
    for i, pc in enumerate(pieces):
        pc["tracts"] = sorted(g for g, (j, _, _) in assign.items() if j == i)
        pc["pop2020"] = sum(pop[g] for g in pc["tracts"]); pc["pop2025_est"] = round(pc["pop2020"] * scale)
    print(f"{fips} {name}: {method} ({source}), {len(upop)} units, split units {split_units}, k={k}, modularity {q:.4f}, cut {(q - sc) / MU if MU else 0:.3f}, locks {len(locks)}, "
          f"sizes {[round(p['pop2025_est'] / 1e6, 2) for p in pieces]}", flush=True)
    return {"fips": fips, "county": name, "method": method, "source_id": source, "k": k, "modularity": round(q, 4), "boundary_cut": round(q - sc, 4) if MU else None, "job_centres": lock_report,
            "resolution": r, "seed": seed, "units": len(upop), "split_units": split_units, "pieces": pieces,
            "assign": assign, "splits": splits}


def contiguous(assign, land, pop):
    """True if every piece's populated land parts form one body, apart from islands touching no other piece and
    small exclaves (<= 20,000 residents) that the crosswalk repair handles."""
    from shapely.ops import unary_union
    by = collections.defaultdict(list)
    for g, (i, _, _) in assign.items():
        by[i].append(g)
    allg = list(assign)
    tree = STRtree([land[g] for g in allg])
    for i, gs in by.items():
        u = unary_union([land[g].buffer(0.0005) for g in gs])
        if u.geom_type == "Polygon":
            continue
        parts = [(p, [g for g in gs if p.intersects(land[g].representative_point())]) for p in u.geoms]
        parts = [(p, t) for p, t in parts if sum(pop[g] for g in t) > 0]
        parts.sort(key=lambda x: -sum(pop[g] for g in x[1]))
        for p, t in parts[1:]:
            if sum(pop[g] for g in t) <= 20_000:
                continue  # small exclave: the crosswalk's contiguity repair moves it
            if any(assign[allg[j]][0] != i for j in tree.query(p) if p.intersects(land[allg[j]])):
                return False  # touches another piece on land: a real break, not an island
    return True


def puma_of():
    """2020 tract -> 2020 PUMA (state + PUMA5CE), from the Census relationship file."""
    p = os.path.join(bx.CACHE, "2020_Census_Tract_to_2020_PUMA.txt")
    p = bx.fetch("https://www2.census.gov/geo/docs/maps-data/data/rel2020/2020_Census_Tract_to_2020_PUMA.txt")
    return {r["STATEFP"] + r["COUNTYFP"] + r["TRACTCE"]: r["STATEFP"] + r["PUMA5CE"] for r in csv.DictReader(open(p, encoding="utf-8-sig"))}


def job_cores(fips, gids, land, tadj, unit_of, upop, scale, pop):
    """Rule 12: dense job cores (LODES WAC 2024): connected tracts with >= CORE_DENSITY jobs per km2 of land, holding
    >= CORE_JOBS jobs. A core whose units would exceed half the build cap is tightened (density threshold x1.5) until
    each remaining core fits. Returns [(label, tracts)]."""
    st = ST[fips[:2]]; yr = LODES_YEAR.get(st, "2024")
    p = os.path.join(bx.CACHE, f"{st}_wac_S000_JT00_{yr}.csv.gz")
    p = bx.fetch(f"https://lehd.ces.census.gov/data/lodes/LODES8/{st}/wac/{st}_wac_S000_JT00_{yr}.csv.gz")
    J = collections.Counter()
    with gzip.open(p, "rt") as fh:
        r = csv.reader(fh); next(r)
        for row in r:
            if row[0][:2] == fips[:2] and bx.cty(row[0]) == fips:
                J[row[0][:11]] += int(row[1])
    dens = {g: J[g] / max(0.05, land[g].area * 111.32 ** 2 * math.cos(math.radians(land[g].centroid.y))) for g in gids}
    def comps(pool, thr):
        hot = {g for g in pool if dens[g] >= thr and J[g] >= 500}; out = []
        while hot:
            s0 = hot.pop(); c = {s0}; stk = [s0]
            while stk:
                x = stk.pop()
                for y in tadj[x]:
                    if y in hot:
                        hot.discard(y); c.add(y); stk.append(y)
            out.append(c)
        return out
    usize = lambda c: sum(upop[u] for u in {unit_of[g] for g in c}) * scale
    todo = [(c, CORE_DENSITY) for c in comps(gids, CORE_DENSITY)]; cores = []
    while todo:
        c, thr = todo.pop()
        if sum(J[g] for g in c) < CORE_JOBS:
            continue
        if usize(c) > HI / 2:
            todo += [(x, thr * 1.5) for x in comps(c, thr * 1.5)]
            continue
        top = max(c, key=lambda g: J[g])
        cores.append((f"job core {top} ({sum(J[g] for g in c):,} jobs)", c))
    return cores


def necks(assign, land, pop):
    """Pieces whose main land body splits into populated parts when shrunk by NECK (joined only by a narrow strip)."""
    from shapely.ops import unary_union
    by = collections.defaultdict(list)
    for g, (i, _, _) in assign.items():
        by[i].append(g)
    bad = []
    for i, gs in by.items():
        u = unary_union([land[g].buffer(0.0005) for g in gs])
        body = max(getattr(u, "geoms", [u]), key=lambda x: sum(pop[g] for g in gs if x.intersects(land[g].representative_point())))
        tot = sum(pop[g] for g in gs if body.intersects(land[g].representative_point()))
        shrunk = body.buffer(-NECK)
        parts = [x for x in getattr(shrunk, "geoms", [shrunk]) if not x.is_empty]
        big = [x for x in parts if sum(pop[g] for g in gs if x.intersects(land[g].representative_point())) >= 0.1 * tot]
        if len(big) > 1:
            bad.append(i)
    return bad


def final_assignment(fips, gids, pop, unit_of, units, parts, split_units):
    """Tract -> (piece index, assign, pop share). Polygon divisions: a tract with >= 99% of its area in units of one
    piece is nested; otherwise its 2020 blocks go by internal point and the tract takes the piece with the largest
    block-population share (rule 5). Split units and inferred counties are tract-built (nested)."""
    piece_of_unit = {u: i for i, c in enumerate(parts) for u in c}
    base = {g: piece_of_unit[unit_of[g]] for g in gids}
    assign, splits = {}, []
    if units is None:
        return {g: (base[g], "nested", 1.0) for g in gids}, splits
    land = bx.land_tracts({fips}); full = {t["properties"]["GEOID"]: make_valid(shape(t["geometry"])) for t in bx.tracts(fips)}
    utree = STRtree([u[1] for u in units])
    piece_u = lambda u, g: base[g] if u in split_units else piece_of_unit.get(u, base[g])
    for g in gids:
        area = collections.Counter()
        for i in utree.query(full[g]):
            u, ug = units[i]
            a = full[g].intersection(ug).area
            if a > 0:
                area[piece_u(u, g)] += a
        cov = sum(area.values())
        if not cov:
            assign[g] = (base[g], "internal_point", 1.0); continue
        top, ta = area.most_common(1)[0]
        if ta / cov >= 0.99:
            assign[g] = (top, "nested", 1.0); continue
        bp = collections.Counter()
        for b in bx.blocks(g):
            q = b["properties"]
            if not q["POP100"]:
                continue
            pt = Point(float(q["INTPTLON"]), float(q["INTPTLAT"]))
            hit = [units[i][0] for i in utree.query(pt) if units[i][1].contains(pt)]
            u = hit[0] if hit else unit_of[g]
            bp[piece_u(u, g)] += q["POP100"]
        if not bp or pop[g] == 0:
            assign[g] = (top, "largest_share", round(ta / cov, 4)); continue
        top, tp = bp.most_common(1)[0]
        if len(bp) == 1:
            assign[g] = (top, "nested", 1.0); continue
        assign[g] = (top, "largest_share", round(tp / sum(bp.values()), 4))
        splits += [[g, i, n] for i, n in bp.items()]
    return assign, splits


def main():
    bx.fix_hash_seed()  # sets of unit names iterate in hash order: a fixed seed makes builds repeat exactly
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True); ap.add_argument("--fips", nargs="*")
    a = ap.parse_args(); bx.CACHE = a.cache; os.makedirs(a.cache, exist_ok=True)
    counties = county_list(a.cache)
    out_p = os.path.join(HERE, "groups.json")
    done = {c["fips"]: c for c in json.load(open(out_p))} if os.path.exists(out_p) and a.fips else {}
    for f in sorted(counties, key=lambda f: -counties[f][1]):
        if a.fips and f not in a.fips:
            continue
        done[f] = build(f, a.cache, *counties[f])
        json.dump([done[k] for k in sorted(done, key=lambda f: -counties[f][1]) if k in counties], open(out_p, "w"), indent=1)


if __name__ == "__main__":
    main()
