"""2010 census tracts to atlas units (docs/specs/atlas-units.md, 2010 tracts), for series published on 2010 geography.

Each 2010 block's residents and housing units (2010 census, PL 94-171) and jobs (LODES 7, which is on 2010 blocks) are
shared among the 2020 blocks it overlaps in proportion to the land they share (Census 2010-2020 block relationship
files; water area where a block has no land). A 2020 block belongs to its 2020 tract and so to one atlas unit. Summed
by 2010 tract and unit, this gives the share of each 2010 tract's residents, housing units, jobs and land in each unit.
County changes since 2010 (Connecticut's planning regions, Bedford city VA, Shannon/Oglala Lakota SD, Wade Hampton/
Kusilvak AK, Valdez-Cordova AK) are handled by the blocks themselves. 50 states and DC; Puerto Rico is not in the atlas.

Inputs (logged and pinned through the pieces loaders): TAB2010_TAB2020_ST<ss>.zip, <st>2010.pl.zip, LODES 7 WAC
(all jobs, the latest year published, 2019 back to 2015), and regions/units/crosswalk_tract_unit.csv.
Writes next to this script:
  crosswalk_tract2010_unit.csv  tract2010_geoid, county2010_fips, unit_id, pop2010, hu2010, jobs_lodes7, aland_m2,
                                pop_share, hu_share, jobs_share, aland_share (shares of the 2010 tract; a tract with no
                                residents takes housing units, then jobs, then land, for pop_share; a water-only
                                tract splits equally). Slivers from boundary realignments (under 0.1% of a tract's
                                residents, housing and jobs, under 1% of its land) are folded into its largest unit.
  tract2010_summary.csv         per state: 2010 tracts, tracts in more than one unit, residents, housing units, jobs
usage: python3 build_tract2010.py --cache DIR
"""
import argparse, collections, csv, gzip, io, os, sys, urllib.error, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pieces"))
import build_crosswalk as bx  # noqa: E402

REL = "https://www2.census.gov/geo/docs/maps-data/data/rel2020/t10t20/TAB2010_TAB2020_ST{ss}.zip"
PL = "https://www2.census.gov/census_2010/redistricting_file--pl_94-171/{name}/{st}2010.pl.zip"
LODES7 = "https://lehd.ces.census.gov/data/lodes/LODES7/{st}/wac/{st}_wac_S000_JT00_{yr}.csv.gz"
STATES = {"01": ("Alabama", "al"), "02": ("Alaska", "ak"), "04": ("Arizona", "az"), "05": ("Arkansas", "ar"), "06": ("California", "ca"),
          "08": ("Colorado", "co"), "09": ("Connecticut", "ct"), "10": ("Delaware", "de"), "11": ("District_of_Columbia", "dc"),
          "12": ("Florida", "fl"), "13": ("Georgia", "ga"), "15": ("Hawaii", "hi"), "16": ("Idaho", "id"), "17": ("Illinois", "il"),
          "18": ("Indiana", "in"), "19": ("Iowa", "ia"), "20": ("Kansas", "ks"), "21": ("Kentucky", "ky"), "22": ("Louisiana", "la"),
          "23": ("Maine", "me"), "24": ("Maryland", "md"), "25": ("Massachusetts", "ma"), "26": ("Michigan", "mi"), "27": ("Minnesota", "mn"),
          "28": ("Mississippi", "ms"), "29": ("Missouri", "mo"), "30": ("Montana", "mt"), "31": ("Nebraska", "ne"), "32": ("Nevada", "nv"),
          "33": ("New_Hampshire", "nh"), "34": ("New_Jersey", "nj"), "35": ("New_Mexico", "nm"), "36": ("New_York", "ny"),
          "37": ("North_Carolina", "nc"), "38": ("North_Dakota", "nd"), "39": ("Ohio", "oh"), "40": ("Oklahoma", "ok"), "41": ("Oregon", "or"),
          "42": ("Pennsylvania", "pa"), "44": ("Rhode_Island", "ri"), "45": ("South_Carolina", "sc"), "46": ("South_Dakota", "sd"),
          "47": ("Tennessee", "tn"), "48": ("Texas", "tx"), "49": ("Utah", "ut"), "50": ("Vermont", "vt"), "51": ("Virginia", "va"),
          "53": ("Washington", "wa"), "54": ("West_Virginia", "wv"), "55": ("Wisconsin", "wi"), "56": ("Wyoming", "wy")}
POP_2010, HU_2010 = 308_745_538, 131_704_730  # 2010 census, 50 states + DC


def pl_blocks(ss):
    """2010 block -> (residents, housing units) from the state's PL 94-171 file."""
    name, st = STATES[ss]
    z = zipfile.ZipFile(bx.fetch(PL.format(name=name, st=st)))
    logrec = {}
    with z.open(f"{st}geo2010.pl") as fh:
        for line in io.TextIOWrapper(fh, encoding="latin-1"):
            if line[8:11] == "750":  # block
                logrec[line[18:25]] = line[27:29] + line[29:32] + line[54:60] + line[61:65]
    pop, hu = {}, {}
    with z.open(f"{st}000012010.pl") as fh:
        for line in io.TextIOWrapper(fh, encoding="latin-1"):
            f = line.split(",", 6); b = logrec.get(f[4])
            if b:
                pop[b] = int(f[5])
    with z.open(f"{st}000022010.pl") as fh:
        for line in io.TextIOWrapper(fh, encoding="latin-1"):
            f = line.rstrip("\n").split(","); b = logrec.get(f[4])
            if b:
                hu[b] = int(f[149])  # H0010001: after 5 header fields, P3 (71) and P4 (73)
    return pop, hu


def lodes7(st):
    for yr in ("2019", "2018", "2017", "2016", "2015"):
        try:
            p = bx.fetch(LODES7.format(st=st, yr=yr), f"lodes7_{st}_wac_S000_JT00_{yr}.csv.gz")
        except urllib.error.HTTPError:
            continue
        jobs = {}
        with gzip.open(p, "rt") as fh:
            r = csv.reader(fh); next(r)
            for row in r:
                jobs[row[0]] = int(row[1])
        return jobs, yr
    raise SystemExit(f"no LODES 7 WAC file for {st}")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", required=True)
    a = ap.parse_args(); bx.CACHE = a.cache; bx.fix_hash_seed()
    unit_of = {r["tract_geoid"]: r["unit_id"] for r in csv.DictReader(open(os.path.join(HERE, "crosswalk_tract_unit.csv")))}
    acc = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])  # (tract10, unit) -> pop, hu, jobs, land
    summary, years, missing20 = [], {}, set()
    for ss in sorted(STATES):
        name, st = STATES[ss]
        pop, hu = pl_blocks(ss)
        jobs, years[st] = lodes7(st)
        rows = collections.defaultdict(list)  # block2010 -> [(block2020, land, water)]
        tot = {}
        with zipfile.ZipFile(bx.fetch(REL.format(ss=ss))) as z:
            with z.open(z.namelist()[0]) as fh:
                r = csv.reader(io.TextIOWrapper(fh, encoding="utf-8-sig"), delimiter="|"); h = next(r); ix = {k: i for i, k in enumerate(h)}
                for row in r:
                    b10 = row[ix["STATE_2010"]] + row[ix["COUNTY_2010"]] + row[ix["TRACT_2010"]] + row[ix["BLK_2010"]]
                    b20 = row[ix["STATE_2020"]] + row[ix["COUNTY_2020"]] + row[ix["TRACT_2020"]] + row[ix["BLK_2020"]]
                    rows[b10].append((b20, int(row[ix["AREALAND_INT"]] or 0), int(row[ix["AREAWATER_INT"]] or 0)))
                    tot[b10] = (int(row[ix["AREALAND_2010"]] or 0), int(row[ix["AREAWATER_2010"]] or 0))
        st_tracts = set()
        for b10, parts in rows.items():
            # shares by the overlaps' own totals: in a few blocks the overlaps' land falls slightly short of the block's
            land, water = sum(l for _, l, _ in parts), sum(wa for _, _, wa in parts)
            if land > 0:
                w = [(b20, l / land, l) for b20, l, _ in parts if l > 0]
            elif water > 0:
                w = [(b20, wa / water, 0) for b20, _, wa in parts if wa > 0]
            else:
                w = [(b20, 1 / len(parts), 0) for b20, _, _ in parts]
            p, h_, j = pop.get(b10, 0), hu.get(b10, 0), jobs.get(b10, 0)
            t10 = b10[:11]; st_tracts.add(t10)
            for b20, s, l in w:
                u = unit_of.get(b20[:11])
                if u is None:
                    missing20.add(b20[:11]); continue
                x = acc[(t10, u)]; x[0] += p * s; x[1] += h_ * s; x[2] += j * s; x[3] += l
        sp = sum(pop.values()); sh = sum(hu.values()); sj = sum(jobs.values())
        print(f"{st} {name}: 2010 blocks {len(rows):,} (PL {len(pop):,}), residents {sp:,}, housing units {sh:,}, jobs {sj:,} (LODES 7 {years[st]})", flush=True)
        summary.append({"state_fips": ss, "state": name.replace("_", " "), "tracts2010": len(st_tracts), "pop2010": sp, "hu2010": sh,
                        "jobs_lodes7": sj, "lodes7_year": years[st]})
    if missing20:
        raise SystemExit(f"{len(missing20)} 2020 tracts in the relationship files are not in the atlas crosswalk, e.g. {sorted(missing20)[:5]}")

    by_tract = collections.defaultdict(list)
    for (t, u), v in acc.items():
        by_tract[t].append((u, v))
    # slivers from small boundary realignments (under 0.1% of a tract's residents, housing units and jobs, and under 1%
    # of its land: a few hundredths of a person at most) fold into the tract's largest unit, so totals stay exact
    keep, dropped = [], 0
    for t, parts in sorted(by_tract.items()):
        tp = [sum(v[i] for _, v in parts) for i in range(4)]
        frac = lambda v, i: v[i] / tp[i] if tp[i] else 0
        small = [(u, v) for u, v in parts if all(frac(v, i) < 0.001 for i in range(3)) and frac(v, 3) < 0.01]
        big = [(u, v) for u, v in parts if (u, v) not in small] or [max(parts, key=lambda x: (x[1][0], x[1][3]))]
        if small and len(big) < len(parts):
            host = max(big, key=lambda x: (x[1][0], x[1][3]))[1]
            for u, v in small:
                if v is not host:
                    for i in range(4):
                        host[i] += v[i]
                    dropped += 1
        basis = next((i for i in range(4) if tp[i] > 0), 3)
        for u, v in sorted(big):
            sh = lambda i: round(v[i] / tp[i], 6) if tp[i] else round(1 / len(big), 6)  # water-only tracts: equal shares
            keep.append({"tract2010_geoid": t, "county2010_fips": t[:5], "unit_id": u, "pop2010": round(v[0], 3), "hu2010": round(v[1], 3),
                         "jobs_lodes7": round(v[2], 3), "aland_m2": int(v[3]), "pop_share": sh(basis), "hu_share": sh(1) if tp[1] else sh(basis),
                         "jobs_share": sh(2) if tp[2] else sh(basis), "aland_share": sh(3)})
    with open(os.path.join(HERE, "crosswalk_tract2010_unit.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, list(keep[0])); w.writeheader(); w.writerows(keep)
    nsplit = collections.Counter(r["tract2010_geoid"] for r in keep)
    for s in summary:
        s["tracts_in_several_units"] = sum(1 for t, n in nsplit.items() if t[:2] == s["state_fips"] and n > 1)
    with open(os.path.join(HERE, "tract2010_summary.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, ["state_fips", "state", "tracts2010", "tracts_in_several_units", "pop2010", "hu2010", "jobs_lodes7", "lodes7_year"])
        w.writeheader(); w.writerows(summary)

    tp, th = sum(s["pop2010"] for s in summary), sum(s["hu2010"] for s in summary)
    xp = sum(r["pop2010"] for r in keep)
    split_pop = sum(r["pop2010"] for r in keep if nsplit[r["tract2010_geoid"]] > 1)
    print(f"2010 tracts {len(nsplit):,}; in more than one unit {sum(1 for n in nsplit.values() if n > 1):,} ({split_pop / tp:.2%} of residents); "
          f"rows {len(keep):,} (empty slivers dropped {dropped:,})")
    print(f"residents {tp:,} (census {POP_2010:,}; crosswalk sums to {xp:,.0f}); housing units {th:,} (census {HU_2010:,})")
    if tp != POP_2010 or th != HU_2010 or abs(xp - POP_2010) > 50:
        raise SystemExit("2010 totals do not match the census")
    print("checks: totals match")


if __name__ == "__main__":
    main()
