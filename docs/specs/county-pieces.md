# County pieces

Status: draft, 2026-11-22. Every county with 1.0M+ residents (50 counties, 23,869 tracts) is split into 134 pieces of about 0.8M (0.45–1.1M). 36 counties use an official or Census division, 10 are inferred by Louvain, and 4 stay whole. Job centres stay whole and pieces are compact (rules 12–13). A nested tier of 809 subareas follows 2020 PUMA lines (rule 14). Pieces carry region names and stable IDs (rule 15). Geography release 1.0.1 (2026-11-27): `regions/pieces/releases/1.0.1/`; inputs frozen in `regions/pieces/inputs/`. Groupings come from `regions/pieces/build_groups.py` (see Expansion to 1.0M+ counties). Still open: the LA County GIS cross-check, SBCTA subareas, DCP's own pages for NYC, the Maricopa lead, the H-GAC subregions, and newer SACOG and MTC files (hosts refused; see Re-check list).

Every county with 1.0M+ residents (Census Vintage 2025) is split into **county pieces** of 0.45–1.1M residents, built from 2020 census tracts. There are 50 such counties. (Until 2026-11-22: 1.5M+, 28 counties holding 75.5M residents and 37.5M jobs.) Pieces are the smallest unit in every pillar; a county is the sum of its pieces. Subregions and 70 districts depend on them.

Source of the plan: *Metro Economic Atlas: Index Framework and Integration Plan*, section "Sub-county method" and its table "Proposed division source (to verify)". That table was written from memory; this spec records what was checked against primary sources.

## Rules

1. **Unit size.** Each piece holds 0.45–1.1M residents (2025), aiming at about 0.8M. Target count per county = residents ÷ 0.8M, rounded, raised where needed so every piece fits under the cap and lowered where needed so every piece reaches the floor (at least 2). Exception: a county of 1.0–1.25M with no natural two-way split stays one piece (Contra Costa, Pima, Fresno, Gwinnett; see Review items 6–8). Pieces are built to 0.46–1.07M to leave margin for the 2025 estimate. (History: 0.4–1.5M with a 1.2M target, then 0.4–1.2M with a 1.0M target, then 0.3–0.8M with a 0.6M target, then 0.45–0.8M; on 2026-11-22 the target rose to 0.8M, see Target raised to 0.8M.)
2. **Built from 2020 tracts.** Every populated 2020 tract belongs to exactly one piece. Water-only tracts (population 0) go to the piece they touch most.
3. **Official divisions first.** Where a county has an official, stable, county-wide sub-county division with a boundary file, fit it to tracts and group its units into pieces by commuting (LODES 2024 tract flows) and contiguity.
4. **Inferred otherwise.** Where there is none, infer pieces with the Los Angeles method: Louvain on LODES tract commuting, incorporated cities kept whole, contiguous. A city too large for one piece (over 1.17M in 2025: Houston, Phoenix, Dallas) is split along tract lines.
5. **Tract fitting.** When a division does not nest in tracts, assign each tract to the unit holding its largest 2020 population share (blocks from the 2020 block assignment files); if block data is not prepared, use the tract internal point. Record every split tract and its population error.
6. **Freeze one dated file.** Every input is listed in `inputs/manifest.csv` (source, publisher, license as stated, retrieval date, last-edit date, SHA-256). Local-government boundary layers are snapshotted in `inputs/snapshot/` and read from there, except where the publisher discourages redistribution (SanGIS, San Diego), which is pinned by SHA-256 only; Census and LEHD files are pinned by SHA-256, and the build stops if a download differs. Political districts (commissioner precincts) are allowed only as a frozen, dated version. See Versions, IDs and edits.
7. **County-only data** (QCEW wages, BEA GDP, BFS, OEWS, IRS) is allocated to pieces by LODES jobs by sector and flagged as modelled in Reliability. Point, ZIP, tract and block data split for real.
8. **Coverage.** Pieces must cover the whole county, including unincorporated land, reservations and enclaves. A division set with holes is filled before grouping (see Cook, Suffolk).
9. **Census county divisions as the official fallback.** For counties added at the 1.0M threshold, Census 2020 county subdivisions are used when every one fits under the cap and a valid grouping exists; otherwise rule 4 applies.
10. **Oversized units.** An official unit larger than the cap (2025) is split along tract lines and its tracts grouped like the rest (LA West Valley HD, Fort Worth and San Bernardino CCDs). LA's San Fernando HD is split into tracts although under the cap, because it spans the San Gabriel Mountains. If no valid grouping of a county's official units exists, the county falls back to rule 4.
11. **One build.** All groupings come from `build_groups.py`: units (official, CCD, or places + tracts), LODES 2024 commuting between units, adjacency on shoreline-clipped land polygons, Louvain starts plus every-unit-alone, merged to the target count (under-floor groups first) and refined for modularity within the limits. Candidates are ranked by modularity minus a boundary-length term (rule 13); the best one whose final tract assignment stays contiguous and has no narrow neck wins; exhaustive search where small.
12. **Job centres stay whole.** No piece line cuts a dense job core: connected tracts with at least 10,000 LODES jobs per km² of land and 40,000 jobs in all (tightened where a core would fill more than half a piece). Named districts are also kept whole: the Las Vegas Strip and airport (all of Paradise CDP), downtown Miami with Brickell, downtown Dallas with the Park Cities, and Houston's Memorial Villages. Where commuting draws a line across a strong local divide, anchor sets go to different pieces: Dallas (north, south and west, and east of the Trinity / I-30), Los Angeles (North County apart from the San Fernando Valley, at the Newhall Pass), Allegheny (north of the Allegheny and Ohio rivers apart from the south and west hills).
13. **Compact pieces, no necks.** Grouping penalizes boundary length (modularity − 1.0 × share of internal boundary cut). A boundary between two tracts of the same 2020 PUMA counts three times, so lines follow PUMA lines where commuting allows. A grouping is rejected when a piece's main body splits into populated parts once shrunk by about 350 m, i.e. is joined only by a strip narrower than about 700 m.
14. **Subareas.** Each piece is cut along 2020 PUMA lines into subareas (median 121k residents, 3–11 per piece). A PUMA part under 30,000 residents joins the neighbouring subarea in its piece. A subarea that holds a whole PUMA takes ACS 1-year PUMA estimates and PUMS directly. County-only data (BEA, QCEW) is never allocated below the piece.
15. **Names.** Each piece has a region name ("Henderson & East Valley", "Inner Houston"): an established region name where one exists, otherwise a direction plus no more than three anchor places. Names live in `piece_registry.csv` with the piece IDs, each tied to an anchor tract near the piece's population centre (see Versions, IDs and edits). The mechanical label (top three component units or places) is kept as `piece_components`.

Rule 9 as written for the first 28 counties: where no local planning or statistical division with a boundary file fits rule 1, use the Census 2020 county subdivisions (CCDs). Use them only if they group into contiguous pieces within 0.4–1.5M. They are public domain, cover the county, and nest in tracts or nearly so (checked in Riverside, San Bernardino, Alameda, Tarrant, Bexar, Broward, Palm Beach, Hillsborough, Orange FL). Order of preference: local division (rule 3), then CCDs, then Louvain (rule 4). A local division whose file is older than 2020 is still used, fitted by rule 5, and refreshed when a newer file is reachable (Santa Clara, Sacramento).

## Expansion to 1.0M+ counties (2026-11-22)

The county threshold dropped from 1.5M to 1.0M, and pieces from about 1.0M (0.4–1.2M) to about 0.6M (0.3–0.8M); later the floor rose to 0.45M and then the target to 0.8M (0.45–1.1M). There are now 50 counties and 138 pieces. The bullets below describe the 0.6M build; the table is for the current 0.8M build (see Target raised to 0.8M).

- **Built by:** `build_groups.py`, `build_crosswalk.py`, `build_demographics.py` and `build_geojson.py`, in that order.
- **New counties (22):** the Bronx uses DCP CDTAs. Census county divisions are used where every one fits and a grouping exists: Collin, Oakland, Hennepin, Wake, Cuyahoga, Allegheny, Fairfax, Montgomery MD, Denton, Duval, Gwinnett, Westchester. The rest use Louvain.
  - One place is too big for one piece: Nassau (Hempstead town), Travis (Austin), Franklin (Columbus), Mecklenburg (Charlotte), Salt Lake, Pima.
  - No grouping of their divisions fits: Contra Costa, Fulton, Fresno.
- **Existing counties with finer official units:**
  - Cook: Chicago community areas plus the 155 CCDPH municipality and township features, instead of 4 districts.
  - King: 61 Health Reporting Areas, instead of 4 regions.
  - Miami-Dade: 32 Minor Statistical Areas, instead of 7 major areas.
  - San Diego: 41 SRAs.
  - LA: 26 Health Districts, with West Valley (0.86M) split into tracts.
  - Hillsborough fell back to Louvain: no 3-piece grouping of its CCDs fits.
- **Checks (0.45M floor build):** 23,869 tracts, each in one piece. All 172 pieces are 460,003–779,352 in 2025, and each county's pieces sum to its 2025 total.
  - 85 tracts are assigned by largest block-population share, 9 moved for contiguity, and 26 water-only tracts joined the nearest tract's piece.
  - Six pieces are multi-part, all islands: Catalina, City Island, Governors Island, Fishers Island, Vashon–Maury, and a Potomac island in Fairfax.
  - Theil H median 0.031; highest Cook 0.186, Wayne 0.168, Cuyahoga 0.128. Median share working in own piece 31%; smaller pieces keep less commuting inside than the earlier 1.0M pieces.
- **Fixes made during this build** (each re-run from scratch):
  - Adjacency used bounding-box hits from the spatial index, so pieces could join units that do not touch; it now needs a real intersection. The earlier Louvain builds had the same flaw, masked by the contiguity repair.
  - The contiguity repair now respects the size limits.
  - Groupings are rejected when the final tract assignment breaks contiguity.
  - LA's coarse Health Districts needed singleton starts and under-floor-first merging to find a valid 16-piece grouping (at the 0.3M floor).

### Floor raised to 0.45M (2026-11-22)

The floor rose from 0.3M to 0.45M (built to 0.46M) so that pieces keep more commuting inside. The cap (0.8M) and target (0.6M) are unchanged, so the piece count stays at 172: every county's target count already fits the higher floor.

- **Result:** the smallest pieces grew from 0.31M to 0.46M. Median share of employed residents working in their own piece rose from 30.1% to 31.0%; the lowest rose from 7.9% (Chicago Belmont Cragin) to 11.1% (Queens Elmhurst–Ridgewood). 27 pieces still keep under 20% inside, the same count as before; Belmont Cragin is now 13%.
- **Reading:** the floor removes the worst small pieces but barely moves the typical piece. Commuting inside a piece depends mostly on piece size overall, not on the smallest pieces. A larger gain needs a larger target (fewer pieces), not a higher floor.
- **Divisions lost:** five counties' divisions no longer group into pieces within 0.45–0.8M and fall back to Louvain: Los Angeles (Health Districts), Bexar, Alameda and Orange FL (CCDs), and Suffolk (towns). Hillsborough and Fulton needed every tract as its own unit (Tampa and Atlanta are too big to keep whole under the tighter limits).
- **Method change:** `build_groups.py` adds a rebalancing step. When a grouping has a piece outside the limits, it shifts boundary units along a chain of neighbouring pieces to the nearest piece with room, moving the units that cost the least within-piece commuting. A unit moves with any branch that hangs off it, so pieces stay connected. If whole places still fail, every tract becomes its own unit.
- **Geometry:** dissolving now closes gaps up to about 100 m (buffer 0.0005°, the same tolerance as grouping's adjacency), so river channels in the cartographic file no longer split a piece. Six pieces are multi-part, all islands, as before.

### Target raised to 0.8M (2026-11-22)

The target rose from 0.6M to 0.8M and the cap from 0.8M to 1.1M (built to 1.07M), keeping the 0.45M floor. Counties under 1.2M still split in two. 172 pieces became 138.

| Build | Pieces | 2025 range | Median work in piece | Lowest | Pieces under 20% |
|---|---|---|---|---|---|
| 0.6M target, 0.3M floor | 172 | 0.31–0.78M | 30.1% | 7.9% | 27 |
| 0.6M target, 0.45M floor | 172 | 0.46–0.78M | 31.0% | 11.1% | 27 |
| 0.8M target, 0.45M floor | 138 | 0.46–1.07M | 35.9% | 9.5% | 13 |

- **Commuting:** the median share of employed residents working in their own piece rose by about 5 points and the pieces under 20% halved. The lowest is now LA Southwest/South at 9.5%, a Health District grouping.
- **Divisions back:** with the wider range, official and Census divisions fit again in LA (Health Districts, now with no district split into tracts), Bexar, Alameda, Orange FL, Suffolk, and for the first time Hillsborough and Nassau (CCDs). 37 counties use divisions, 13 Louvain.
- **Louvain with every tract its own unit:** Travis, Franklin, Mecklenburg, Fulton. Austin, Columbus, Charlotte and Atlanta fit under the cap whole, but no grouping around them reaches the floor on the other side.
- **Checks:** 23,869 tracts, each in one piece; 51 assigned by largest block-population share, 2 moved for contiguity, 26 water-only. All 138 pieces are 460,048–1,069,683 in 2025, and each county's pieces sum to its 2025 total. Six pieces are multi-part, all islands. Theil H median 0.021; highest Wayne 0.162, Cuyahoga 0.128, Fulton 0.120.

### Review fixes: job centres, compactness, necks (2026-11-22)

An independent review asked whether residents would recognize the 0.8M pieces. It found Las Vegas splitting the Strip, Midtown Manhattan and downtown Miami each cut in two, sliver pieces in Phoenix and Houston, a north–south spine through Dallas, and pinched two-piece counties (Gwinnett, Santa Clara). Rules 12 and 13 address these; the build was re-run for all 50 counties.

| Build | Median work in piece | Lowest | Under 20% | Median Polsby–Popper | Pieces under 0.2 | Pieces with a neck |
|---|---|---|---|---|---|---|
| 0.8M target | 35.9% | 9.5% | 13 | 0.33 | 17 | 11 (review count) |
| With rules 12–13 | 34.8% | 8.5% | 12 | 0.38 | 2 | 0 |

- **Job centres:** 52 data-driven cores and 4 named districts are kept whole (in `groups.json`, `job_centres`). The Strip, Mandalay Bay and the airport now share one piece (Spring Valley, Paradise, Enterprise). Times Square, Grand Central, the Empire State Building and Rockefeller Center share one Manhattan piece; the line runs near Columbus Circle. Downtown Miami, Brickell and Coral Gables share one. The Loop and downtown LA are each whole.
- **Dallas:** North (downtown, the Park Cities, Preston Hollow, Far North Dallas, Richardson, Carrollton, Lake Highlands), South and West (Oak Cliff, DeSoto, Grand Prairie, Irving), East (Garland, Mesquite, Pleasant Grove).
- **Slivers:** Phoenix and Houston now have no piece under 0.30 Polsby–Popper (release 1.0). The Memorial Villages are in one piece with Alief and Sharpstown.
- **Two-piece counties:** Santa Clara is San Jose with South County and Los Gatos versus North County (Palo Alto, Sunnyvale, Milpitas), as the review proposed. Gwinnett is north and west (Norcross, Duluth, Lawrenceville, Buford) versus south (Lilburn, Snellville), with no neck.
- **Cost:** the median share working in their own piece fell by 1.1 points; total modularity changed little. The two pieces still under 0.2 are LA's West/Southwest Health District grouping (the West HD runs out to Malibu) and Suffolk's east end (the forks).
- **Checks:** 23,869 tracts, each in one piece; 57 assigned by largest block-population share, 2 moved for contiguity, 26 water-only. All 138 pieces are 460,783–1,082,594 in 2025 (the largest-share step pushes one past the 1.07M build limit, still under the 1.1M cap), and each county's pieces sum to its 2025 total. Six pieces are multi-part, all islands. Theil H median 0.021.
- Review items 6–8 followed on 2026-11-23 (next section).

### Review items 6–8: crossings, whole counties, names (2026-11-23)

- **LA North County:** the San Fernando Health District is split into tracts and North County is anchored apart from the Valley. Santa Clarita and the Antelope Valley form one piece (0.69M); Sylmar, San Fernando and Pacoima join the East Valley and Glendale.
- **Allegheny:** north of the rivers is anchored apart from the south and west hills. Pittsburgh, the North Hills (Sewickley, Bellevue) and the east form one piece (0.76M); the South and West Hills (Coraopolis, Moon, Mount Lebanon, McKeesport) the other (0.47M).
- **San Diego backcountry:** fixed already by rule 13. Ramona, Julian and Borrego Springs now sit with inland North County (Escondido), not with La Jolla.
- **Whole counties:** Contra Costa (1.17M; Mount Diablo divides any split), Pima (1.07M; the split ringed Tucson), Fresno (1.04M; the split joined Clovis to the Sierra) and Gwinnett (1.02M; no split avoids a pinch) stay one piece each. They keep their subareas (7–11 each).
- **Names:** all 134 pieces have region names (rule 15).
- **Result:** 134 pieces. Pieces of split counties are 466,473–1,069,679 (2025); whole counties up to 1,170,070. Median work in piece 35.7%, lowest 8.5% (southeast Denton: Frisco and Carrollton, which commute to Dallas and Collin), 11 pieces under 20%. Median Polsby–Popper 0.40; six multi-part pieces, all islands. 23,869 tracts: 48 by largest block-population share, 2 moved for contiguity, 26 water-only.

### Subareas: a PUMA tier inside pieces (2026-11-22)

`build_subareas.py` cuts each piece along 2020 PUMA lines (rule 14). PUMAs are the Census's own small areas (100k+ residents, fixed until 2030, named locally), so whole-PUMA subareas get ACS 1-year estimates and PUMS every year.

- **Result** (release 1.0): 809 subareas, 31,797–270,930 residents (2020; median 121k), 3–11 per piece. 534 are exact PUMAs, holding 72% of residents; 275 are PUMA parts, where a piece line (usually an official division) cuts a PUMA. Exact PUMAs: 397 of 574 subareas in counties with official divisions, 105 of 203 in Louvain counties, all 32 in whole counties.
- **Islands** (Catalina, City Island, Vashon, a Potomac island) and PUMA parts under 30,000 join the nearest subarea in their piece; 284 tracts are absorbed this way.
- **Commuting:** a median of 11% of employed residents work in their own subarea, so subareas are for resident measures (ACS, PUMS, demographics) and LODES job counts, not for commuting containment.
- **Names:** the PUMA's Census name without its county prefix (NYC: "Upper West Side (CD 7)"), with "(part)" where the subarea holds only part of the PUMA.

| County | 2025 | Units | Pieces | 2025 range | Modularity | Work in piece (median) | Theil H | Note |
|---|---|---|---|---|---|---|---|---|
| Los Angeles, California | 9.69M | LA DPH Health Districts | 12 | 0.50–1.05M | 0.271 | 30% | 0.095 | split into tracts: San Fernando |
| Cook, Illinois | 5.19M | Chicago CAs + suburban municipalities/townships | 6 | 0.47–1.07M | 0.238 | 29% | 0.109 |  |
| Harris, Texas | 5.05M | Louvain (places + tracts) | 6 | 0.72–1.07M | 0.225 | 28% | 0.026 | no division fits |
| Maricopa, Arizona | 4.69M | Louvain (places + tracts) | 6 | 0.51–1.05M | 0.179 | 35% | 0.054 | no division fits |
| San Diego, California | 3.28M | SANDAG SRAs | 4 | 0.62–0.96M | 0.259 | 41% | 0.050 |  |
| Orange, California | 3.15M | Louvain (places + tracts) | 4 | 0.56–1.01M | 0.244 | 27% | 0.049 | no division fits |
| Miami-Dade, Florida | 2.80M | Minor Statistical Areas | 4 | 0.51–0.99M | 0.193 | 36% | 0.100 |  |
| Dallas, Texas | 2.66M | Louvain (places + tracts) | 3 | 0.80–1.04M | 0.168 | 34% | 0.038 | no division fits |
| Kings, New York | 2.65M | DCP CDTAs | 3 | 0.81–0.92M | 0.176 | 19% | 0.061 |  |
| Riverside, California | 2.54M | Census CCDs/MCDs | 3 | 0.50–1.07M | 0.438 | 33% | 0.012 |  |
| Clark, Nevada | 2.41M | Louvain (places + tracts) | 3 | 0.65–1.06M | 0.099 | 50% | 0.014 | no division fits |
| Queens, New York | 2.36M | DCP CDTAs | 3 | 0.54–0.96M | 0.208 | 18% | 0.079 |  |
| King, Washington | 2.34M | PHSKC HRAs | 3 | 0.55–0.98M | 0.221 | 46% | 0.018 |  |
| Tarrant, Texas | 2.25M | Census CCDs/MCDs | 3 | 0.59–1.00M | 0.234 | 28% | 0.025 |  |
| San Bernardino, California | 2.22M | Census CCDs/MCDs | 3 | 0.62–0.93M | 0.335 | 31% | 0.030 |  |
| Bexar, Texas | 2.16M | Census CCDs/MCDs | 3 | 0.71–0.73M | 0.129 | 35% | 0.037 |  |
| Broward, Florida | 2.01M | Census CCDs/MCDs | 3 | 0.58–0.81M | 0.186 | 30% | 0.021 |  |
| Santa Clara, California | 1.91M | MTC superdistricts | 2 | 0.90–1.01M | 0.110 | 41% | 0.013 |  |
| Wayne, Michigan | 1.77M | Census towns/MCDs | 2 | 0.73–1.04M | 0.192 | 40% | 0.159 |  |
| Middlesex, Massachusetts | 1.67M | Census towns/MCDs | 2 | 0.83–0.84M | 0.237 | 42% | 0.002 |  |
| New York, New York | 1.66M | DCP CDTAs | 2 | 0.67–0.99M | 0.036 | 45% | 0.033 |  |
| Alameda, California | 1.64M | Census CCDs/MCDs | 2 | 0.67–0.97M | 0.278 | 36% | 0.026 |  |
| Sacramento, California | 1.62M | SACOG RADs (2007) | 2 | 0.78–0.84M | 0.143 | 40% | 0.013 |  |
| Palm Beach, Florida | 1.58M | Census CCDs/MCDs | 2 | 0.59–0.99M | 0.211 | 49% | 0.005 |  |
| Philadelphia, Pennsylvania | 1.57M | Planning districts | 2 | 0.57–1.01M | 0.132 | 44% | 0.013 |  |
| Hillsborough, Florida | 1.57M | Census CCDs/MCDs | 2 | 0.65–0.92M | 0.128 | 40% | 0.002 |  |
| Suffolk, New York | 1.55M | Census towns/MCDs | 2 | 0.66–0.89M | 0.239 | 45% | 0.004 |  |
| Orange, Florida | 1.53M | Census CCDs/MCDs | 2 | 0.50–1.03M | 0.122 | 41% | 0.006 |  |
| Bronx, New York | 1.41M | DCP CDTAs | 2 | 0.51–0.90M | 0.065 | 13% | 0.008 | new |
| Nassau, New York | 1.40M | Census CCDs/MCDs | 2 | 0.57–0.83M | 0.164 | 30% | 0.030 | new |
| Travis, Texas | 1.39M | Louvain (tracts) | 2 | 0.66–0.73M | 0.128 | 43% | 0.003 | new; no division fits |
| Franklin, Ohio | 1.36M | Louvain (tracts) | 2 | 0.66–0.70M | 0.122 | 47% | 0.054 | new; no division fits |
| Collin, Texas | 1.30M | Census CCDs/MCDs | 2 | 0.57–0.73M | 0.142 | 25% | 0.004 | new |
| Oakland, Michigan | 1.29M | Census CCDs/MCDs | 2 | 0.48–0.81M | 0.175 | 39% | 0.008 | new |
| Hennepin, Minnesota | 1.28M | Census CCDs/MCDs | 2 | 0.56–0.72M | 0.160 | 48% | 0.011 | new |
| Wake, North Carolina | 1.26M | Census CCDs/MCDs | 2 | 0.51–0.74M | 0.141 | 41% | 0.029 | new |
| Mecklenburg, North Carolina | 1.23M | Louvain (tracts) | 2 | 0.60–0.64M | 0.108 | 44% | 0.021 | new; no division fits |
| Cuyahoga, Ohio | 1.23M | Census CCDs/MCDs | 2 | 0.48–0.75M | 0.139 | 50% | 0.126 | new |
| Allegheny, Pennsylvania | 1.23M | Census CCDs/MCDs | 2 | 0.47–0.76M | 0.145 | 53% | 0.009 | new |
| Salt Lake, Utah | 1.22M | Louvain (places + tracts) | 2 | 0.56–0.66M | 0.115 | 52% | 0.016 | new; no division fits |
| Contra Costa, California | 1.17M | Whole county | 1 | 1.17–1.17M | 0.000 | 36% | 0.000 | new; Mount Diablo divides any split |
| Fairfax, Virginia | 1.17M | Census CCDs/MCDs | 2 | 0.53–0.63M | 0.132 | 38% | 0.008 | new |
| Fulton, Georgia | 1.10M | Louvain (tracts) | 2 | 0.48–0.62M | 0.229 | 38% | 0.126 | new; no division fits |
| Pima, Arizona | 1.07M | Whole county | 1 | 1.07–1.07M | 0.000 | 75% | 0.000 | new; a split rings Tucson |
| Montgomery, Maryland | 1.07M | Census CCDs/MCDs | 2 | 0.49–0.58M | 0.123 | 42% | 0.008 | new |
| Denton, Texas | 1.07M | Census CCDs/MCDs | 2 | 0.48–0.59M | 0.171 | 19% | 0.011 | new |
| Duval, Florida | 1.06M | Census CCDs/MCDs | 2 | 0.47–0.59M | 0.132 | 46% | 0.047 | new |
| Fresno, California | 1.04M | Whole county | 1 | 1.04–1.04M | 0.000 | 71% | 0.000 | new; a split joins Clovis to the Sierra |
| Gwinnett, Georgia | 1.02M | Whole county | 1 | 1.02–1.02M | 0.000 | 39% | 0.000 | new; no split avoids a pinch |
| Westchester, New York | 1.02M | Census CCDs/MCDs | 2 | 0.47–0.55M | 0.221 | 32% | 0.025 | new |

Earlier rounds below (Piece size change, Review, and the per-county sections) record sources and decisions made under the 1.5M and 1.2M rules; their piece tables are superseded by this one.

## Piece size change (2026-11-22, superseded)

Rule 1 moved from a 1.2M target within 0.4–1.5M to a 1.0M target within 0.4–1.2M. Pieces went from 74 to 84.

- **Counts:** residents ÷ 1.0M, rounded, raised where the 1.17M build ceiling needs it: Queens, Clark and King go to 3 instead of 2, Cook to 6. The 16 counties whose pieces were already under 1.17M kept them unchanged.
- **Harris:** its 4 commissioner precincts hold about 1.26M each, and its Houston CCD 3.46M, so no division fits. Harris is now inferred (Louvain, 5 pieces). Houston, Phoenix and Dallas are the cities split along tract lines.
- **Regrouped official counties:**
  - Los Angeles: 10 pieces from the 26 Health Districts, which no longer follow SPA lines.
  - Chicago: 3 pieces, by community-area sides.
  - Cook suburbs: 3 pieces from the CCDPH districts.
  - San Diego: 3 pieces from the 41 SRAs; the 7 MSAs are too coarse.
  - Miami-Dade, Brooklyn, Queens, Riverside, King: 3 pieces each.

  Each grouping was searched for the highest commuting modularity under contiguity and the 0.41–1.17M build limits (Louvain starts, constrained merge, then local search; exhaustive where small).
- **Judgement calls:**
  - Chicago: the modularity-best grouping (0.106) made a 0.42M northwest piece where under 10% of workers stay inside. The sides grouping (0.096) was used instead.
  - Queens: Astoria (QN01) and Flushing (QN07) touch only across Flushing Bay, so that link was dropped. The result scores higher anyway (0.2057).
  - King: Seattle + North / South / East was kept; the best grouping scored only 0.002 more.
- **Results:** every piece is 487,512–1,170,076 in 2025; 17,654 tracts; 38 tracts split by a piece line (19,284 residents moved by whole-tract assignment); 42 tracts moved for contiguity (see Review). Sections below that give 2- or 4-piece groupings for the regrouped counties describe the earlier rule; this table is current. Population mix is 2020 PL 94-171 (P2; non-Hispanic groups by race).

| Piece | County | Name | 2020 | 2025 est. | Work in piece | Hispanic | White | Black | Asian |
|---|---|---|---|---|---|---|---|---|---|
| 06037-01 | Los Angeles, CA | Alhambra, El Monte, Foothill and Pasadena HDs | 1,208,585 | 1.17M | 34.8% | 44% | 17% | 3% | 33% |
| 06037-02 | Los Angeles, CA | Central, Northeast, Southeast and Southwest HDs | 1,187,935 | 1.15M | 26.6% | 60% | 12% | 14% | 10% |
| 06037-03 | Los Angeles, CA | Hollywood-Wilshire and West HDs | 1,145,581 | 1.11M | 44.0% | 22% | 50% | 6% | 15% |
| 06037-04 | Los Angeles, CA | East LA, San Antonio, South and Whittier HDs | 1,116,025 | 1.08M | 23.8% | 82% | 7% | 5% | 4% |
| 06037-05 | Los Angeles, CA | Long Beach, Compton and Bellflower HDs | 1,103,928 | 1.07M | 25.4% | 54% | 17% | 12% | 13% |
| 06037-06 | Los Angeles, CA | Harbor, Inglewood and Torrance HDs | 1,080,610 | 1.05M | 35.7% | 40% | 24% | 14% | 16% |
| 06037-07 | Los Angeles, CA | Antelope Valley and San Fernando HDs | 946,744 | 0.92M | 31.1% | 47% | 31% | 8% | 9% |
| 06037-08 | Los Angeles, CA | West Valley HD | 892,407 | 0.86M | 31.9% | 39% | 40% | 4% | 12% |
| 06037-09 | Los Angeles, CA | East Valley and Glendale HDs | 787,488 | 0.76M | 35.8% | 37% | 46% | 3% | 11% |
| 06037-10 | Los Angeles, CA | Pomona HD | 544,706 | 0.53M | 20.9% | 49% | 19% | 4% | 25% |
| 17031-01 | Cook, IL | North suburbs | 1,106,048 | 1.09M | 40.4% | 16% | 60% | 4% | 17% |
| 17031-02 | Cook, IL | Chicago South Side | 1,033,053 | 1.02M | 19.5% | 31% | 11% | 50% | 5% |
| 17031-03 | Cook, IL | Chicago North, Central and West sides | 976,905 | 0.96M | 59.4% | 25% | 43% | 22% | 7% |
| 17031-04 | Cook, IL | South and southwest suburbs | 847,195 | 0.83M | 31.9% | 18% | 44% | 34% | 2% |
| 17031-05 | Cook, IL | Chicago Far North and Northwest sides | 760,446 | 0.75M | 15.9% | 34% | 45% | 7% | 10% |
| 17031-06 | Cook, IL | West suburbs | 551,894 | 0.54M | 25.1% | 43% | 39% | 13% | 3% |
| 48201-01 | Harris, TX | Houston / The Woodlands / Tomball | 1,064,840 | 1.14M | 32.0% | 36% | 36% | 15% | 10% |
| 48201-02 | Harris, TX | Houston / Pasadena / Baytown | 1,033,743 | 1.10M | 39.4% | 57% | 24% | 12% | 4% |
| 48201-03 | Harris, TX | Houston / Mission Bend / Katy | 1,032,373 | 1.10M | 33.5% | 41% | 27% | 17% | 12% |
| 48201-04 | Harris, TX | Houston / Atascocita / Spring | 814,200 | 0.87M | 23.8% | 49% | 19% | 27% | 2% |
| 48201-05 | Harris, TX | Houston / Bellaire / West University Place | 785,989 | 0.84M | 41.2% | 32% | 31% | 26% | 8% |
| 04013-01 | Maricopa, AZ | Phoenix / Goodyear / Avondale | 1,065,725 | 1.13M | 41.9% | 56% | 27% | 9% | 3% |
| 04013-02 | Maricopa, AZ | Phoenix / Glendale / Peoria | 1,062,558 | 1.13M | 35.0% | 26% | 60% | 5% | 4% |
| 04013-03 | Maricopa, AZ | Chandler / Gilbert / Tempe | 932,132 | 0.99M | 49.1% | 20% | 59% | 5% | 8% |
| 04013-04 | Maricopa, AZ | Phoenix / Scottsdale / Fountain Hills | 809,474 | 0.86M | 43.5% | 17% | 70% | 3% | 4% |
| 04013-05 | Maricopa, AZ | Mesa | 550,679 | 0.58M | 26.4% | 27% | 60% | 4% | 2% |
| 06073-01 | San Diego, CA | North County and northern San Diego city | 1,157,988 | 1.15M | 48.5% | 30% | 51% | 2% | 10% |
| 06073-02 | San Diego, CA | South Bay and East County | 1,152,338 | 1.15M | 36.2% | 47% | 31% | 6% | 10% |
| 06073-03 | San Diego, CA | Central San Diego and coast | 988,308 | 0.98M | 58.2% | 23% | 48% | 5% | 17% |
| 06059-01 | Orange, CA | Irvine / Mission Viejo / Newport Beach | 1,102,262 | 1.09M | 48.0% | 18% | 53% | 1% | 22% |
| 06059-02 | Orange, CA | Anaheim / Fullerton / Orange | 1,050,305 | 1.04M | 32.9% | 42% | 30% | 2% | 21% |
| 06059-03 | Orange, CA | Santa Ana / Huntington Beach / Garden Grove | 1,034,422 | 1.02M | 31.7% | 43% | 29% | 1% | 23% |
| 12086-01 | Miami-Dade, FL | Central-south and west Kendall (areas 5-6) | 991,238 | 1.03M | 39.2% | 78% | 14% | 4% | 2% |
| 12086-02 | Miami-Dade, FL | Beaches, northeast and north-central (areas 1, 2, 4) | 972,769 | 1.01M | 45.4% | 51% | 16% | 28% | 1% |
| 12086-03 | Miami-Dade, FL | Northwest and south county (areas 3, 7) | 737,760 | 0.77M | 31.7% | 80% | 9% | 8% | 1% |
| 48113-01 | Dallas, TX | Dallas / Garland / Mesquite | 944,016 | 0.96M | 27.4% | 43% | 27% | 20% | 7% |
| 48113-02 | Dallas, TX | Dallas / Irving / Carrollton | 865,546 | 0.88M | 43.1% | 32% | 43% | 9% | 12% |
| 48113-03 | Dallas, TX | Dallas / Grand Prairie / DeSoto | 803,977 | 0.82M | 31.6% | 46% | 13% | 37% | 2% |
| 36047-01 | Kings, NY | North Brooklyn | 1,151,859 | 1.12M | 19.6% | 25% | 32% | 30% | 7% |
| 36047-02 | Kings, NY | Central and east Brooklyn | 840,866 | 0.82M | 17.3% | 11% | 31% | 42% | 10% |
| 36047-03 | Kings, NY | Southwest Brooklyn | 743,349 | 0.72M | 26.2% | 19% | 45% | 4% | 29% |
| 06065-01 | Riverside, CA | Northwest Riverside and San Gorgonio Pass | 991,326 | 1.04M | 32.1% | 53% | 27% | 7% | 9% |
| 06065-02 | Riverside, CA | Southwest Riverside | 963,624 | 1.01M | 33.5% | 44% | 36% | 7% | 7% |
| 06065-03 | Riverside, CA | Coachella and Palo Verde valleys | 463,235 | 0.49M | 61.7% | 54% | 37% | 3% | 3% |
| 32003-01 | Clark, NV | Las Vegas / North Las Vegas / Sunrise Manor | 1,066,761 | 1.13M | 51.3% | 37% | 35% | 15% | 6% |
| 32003-02 | Clark, NV | Spring Valley / Enterprise / Paradise | 608,539 | 0.65M | 45.0% | 29% | 35% | 12% | 18% |
| 32003-03 | Clark, NV | Henderson / Paradise / Enterprise | 590,161 | 0.63M | 38.7% | 22% | 53% | 7% | 10% |
| 36081-01 | Queens, NY | Southeast Queens and the Rockaways | 1,021,830 | 1.00M | 18.0% | 22% | 15% | 33% | 20% |
| 36081-02 | Queens, NY | Western Queens | 808,608 | 0.79M | 14.5% | 35% | 35% | 4% | 21% |
| 36081-03 | Queens, NY | Elmhurst-Corona, Flushing and Bayside | 575,026 | 0.56M | 19.0% | 27% | 19% | 3% | 49% |
| 53033-01 | King, WA | Seattle and North King | 876,716 | 0.91M | 59.0% | 8% | 60% | 6% | 17% |
| 53033-02 | King, WA | South King | 803,235 | 0.83M | 40.9% | 16% | 47% | 10% | 17% |
| 53033-03 | King, WA | East King | 589,724 | 0.61M | 48.9% | 7% | 56% | 2% | 29% |
| 48439-01 | Tarrant, TX | Fort Worth | 938,512 | 1.00M | 41.6% | 36% | 38% | 19% | 3% |
| 48439-02 | Tarrant, TX | Northeast Tarrant | 617,006 | 0.66M | 28.0% | 20% | 57% | 8% | 8% |
| 48439-03 | Tarrant, TX | Arlington | 555,122 | 0.59M | 28.0% | 28% | 36% | 24% | 8% |
| 06071-01 | San Bernardino, CA | West Valley and High Desert | 1,142,934 | 1.17M | 30.8% | 49% | 28% | 8% | 11% |
| 06071-02 | San Bernardino, CA | East Valley and mountains | 1,038,720 | 1.06M | 40.7% | 59% | 24% | 8% | 5% |
| 48029-01 | Bexar, TX | Central and east Bexar | 1,045,449 | 1.12M | 48.2% | 68% | 19% | 8% | 1% |
| 48029-02 | Bexar, TX | North and west Bexar | 963,875 | 1.04M | 45.0% | 50% | 34% | 7% | 5% |
| 12011-01 | Broward, FL | South Broward | 1,076,648 | 1.11M | 38.8% | 38% | 28% | 25% | 4% |
| 12011-02 | Broward, FL | North Broward | 867,727 | 0.90M | 42.5% | 23% | 39% | 29% | 3% |
| 06085-01 | Santa Clara, CA | San Jose and south county | 1,100,267 | 1.09M | 33.5% | 34% | 23% | 2% | 36% |
| 06085-02 | Santa Clara, CA | North county and west valley | 835,992 | 0.83M | 53.9% | 14% | 36% | 2% | 43% |
| 26163-01 | Wayne, MI | Out-Wayne | 1,055,070 | 1.04M | 47.3% | 6% | 70% | 14% | 4% |
| 26163-02 | Wayne, MI | Detroit, Hamtramck, Highland Park and the Grosse Pointes | 738,491 | 0.73M | 32.7% | 7% | 16% | 70% | 3% |
| 25017-01 | Middlesex, MA | Outer Middlesex | 964,667 | 0.99M | 45.0% | 8% | 70% | 3% | 12% |
| 25017-02 | Middlesex, MA | Inner Core Middlesex | 667,335 | 0.68M | 37.0% | 10% | 61% | 7% | 15% |
| 36061-01 | New York, NY | Upper Manhattan | 1,011,796 | 0.99M | 19.8% | 30% | 41% | 16% | 8% |
| 36061-02 | New York, NY | Lower and Midtown Manhattan | 682,455 | 0.67M | 69.2% | 14% | 55% | 5% | 20% |
| 06001-01 | Alameda, CA | Central, South and East Alameda | 994,660 | 0.97M | 34.8% | 24% | 24% | 5% | 41% |
| 06001-02 | Alameda, CA | North Alameda | 687,693 | 0.67M | 36.8% | 23% | 34% | 16% | 19% |
| 06067-01 | Sacramento, CA | North and east Sacramento County | 899,731 | 0.92M | 36.8% | 22% | 50% | 8% | 12% |
| 06067-02 | Sacramento, CA | Sacramento core and south county | 685,324 | 0.70M | 44.1% | 26% | 30% | 11% | 25% |
| 12099-01 | Palm Beach, FL | North Palm Beach | 789,826 | 0.83M | 57.6% | 29% | 43% | 21% | 3% |
| 12099-02 | Palm Beach, FL | South Palm Beach | 702,365 | 0.74M | 40.5% | 17% | 62% | 13% | 3% |
| 42101-01 | Philadelphia, PA | North and Northeast Philadelphia | 972,179 | 0.95M | 30.9% | 20% | 30% | 38% | 7% |
| 42101-02 | Philadelphia, PA | Center, South and West Philadelphia | 631,618 | 0.62M | 56.2% | 7% | 41% | 39% | 10% |
| 12057-01 | Hillsborough, FL | Tampa and Keystone | 854,557 | 0.92M | 55.5% | 30% | 43% | 16% | 6% |
| 12057-02 | Hillsborough, FL | East and south Hillsborough | 605,205 | 0.65M | 25.4% | 28% | 49% | 14% | 3% |
| 36103-01 | Suffolk, NY | West Suffolk | 878,584 | 0.89M | 46.2% | 24% | 60% | 8% | 4% |
| 36103-02 | Suffolk, NY | East Suffolk | 647,336 | 0.66M | 43.0% | 19% | 68% | 6% | 4% |
| 12095-01 | Orange, FL | Orlando and east Orange | 963,737 | 1.03M | 46.9% | 36% | 34% | 20% | 5% |
| 12095-02 | Orange, FL | West Orange | 466,171 | 0.50M | 35.2% | 28% | 43% | 15% | 7% |

## Review: Houston, Los Angeles, contiguity, demographics, offshore (2026-11-22, under the 1.2M rule)

**Harris alternative: Houston super neighborhoods + suburbs.** Houston city tracts were grouped by the City of Houston's 88 super neighborhoods (`services.arcgis.com/NummVBqZSIJKUeVR/.../COH_Super_Neighborhoods_view/FeatureServer/3`, owner cohgis_ago) and suburban tracts by cities, with each side searched separately.

- **Contiguity:** neither side is contiguous on its own. Houston has detached areas (Kingwood, Lake Houston, Greenspoint/IAH, about 150k), and Bellaire, West University Place and the Memorial Villages are enclaves inside it. Those parts had to join the neighbouring piece they commute with most.
- **5 pieces:** with the city in 2, one city piece reaches 1.26M, over the cap. The alternative needs 6 pieces.

| Harris | Pieces (2025) | Work in piece | Modularity | Theil H |
|---|---|---|---|---|
| Current: Louvain, 5 | 0.84–1.14M | 34.1% | 0.2466 | 0.025 |
| Super neighborhoods (3) + suburbs (3) | 0.50–1.14M | 29.1% | 0.2126 | 0.014 |
| Super neighborhoods (2) + suburbs (3) | 0.70–1.26M (over cap) | 32.8% | 0.2143 | 0.013 |

**Los Angeles alternative: pieces nested in the 8 SPAs.** This needs 13 pieces, not 12: SPA 2 (2.14M) cannot split into 2 pieces under 1.17M with its Health Districts. Antelope Valley (SPA 1) stays whole at 0.405M, at the floor.

| Los Angeles | Pieces (2025) | Work in piece | Modularity | Theil H |
|---|---|---|---|---|
| Current: 10 HD pieces across SPAs | 0.53–1.17M | 31.7% | 0.2854 | 0.077 |
| Nested in SPAs, 13 pieces | 0.41–1.17M | 28.9% | 0.2673 | 0.097 |

- **Recommendation:** keep both current choices. They keep more commuting inside pieces, match the target count, and stay clear of the floor and cap.
- **Trade-off:** the alternatives keep administrative lines (Houston city limits, LA SPAs) that some users may expect.
- **Demographics:** the LA SPA version sorts groups more (East LA + San Antonio is 90% Hispanic, against 82% at most now). The Harris super-neighborhood version sorts slightly less; both Harris figures are low.

**Contiguity.** Every piece was checked on land polygons (2020 cartographic tracts).

- **Repair rule:** each piece keeps its most populous part. Another populated part that touches a different piece on land moves to the piece it borders most (`assign = contiguity`, 42 tracts).
  - Wayne: the Grosse Pointes (17 tracts, 61,970) and Hamtramck–Highland Park (14 tracts, 37,405) are cut off from Out-Wayne by Detroit, so they join the Detroit piece. It is renamed "Detroit, Hamtramck, Highland Park and the Grosse Pointes".
  - Cook: Norridge and Harwood Heights (5 tracts, 24,574), enclaves in Chicago, join the Chicago Far North and Northwest piece.
  - Six one- or two-tract exclaves move: in Harris (2,057), Dallas (2,153; 3,294), Maricopa (a Mesa exclave, 1,294) and Orange CA (3,794).
- **Islands kept** (the county spans water): Catalina (3,875), Vashon–Maury (11,055), Governors Island (5).
- **Still multi-part in the map:** LA South Bay (Catalina), Chicago Far North and Northwest (O'Hare, whose land strip is lost at 1:500k), Lower Manhattan (Governors Island), East Suffolk (Fishers Island), South King (Vashon).

**Demographics.** `tract_demographics.csv` and `piece_demographics.csv` give 2020 PL 94-171 P2 counts (Hispanic; non-Hispanic White, Black, Asian, other) for all 17,654 tracts (74,418,103 residents). Theil's multigroup index H measures how much a county's pieces sort groups apart (0 = every piece mirrors the county; 1 = full separation).

- **Overall:** H is under 0.10 in 26 of 28 counties.
- **Wayne (0.159):** Detroit's piece is 70% Black and Out-Wayne 70% White.
- **Cook (0.100):** the South Side piece is 50% Black, against 4% in the north suburbs.
- **Lowest:** Hillsborough (0.002) and Suffolk (0.004).
- **Cause:** the high values follow official lines (the Detroit city line, Chicago sides), not the grouping search.

**Offshore areas.** Piece boundaries now come from the Census 2020 cartographic tract file (`cb_2020_us_tract_500k`), clipped to the shoreline.

- **Water:** water-only tracts have no land polygon.
- **Islands cut from the geometry** (only the drawing changes; the figures keep everyone):
  - parts with no 2020 residents, such as Liberty Island and the Tampa Bay spoil islands;
  - parts with fewer than 1,000 residents more than 20 km from other land: San Clemente Island, which has 160 residents, mostly Navy.

## Population check

All 28 resident figures in the plan match the Census Bureau's Vintage 2025 county estimates (`co-est2025-alldata.csv`, `POPESTIMATE2025`) to 2 decimals, and no other county has 1.5M+. Near the cutoff: Orange FL is the smallest at 1,528,002; Philadelphia (1,574,281) is just above Hillsborough (1,574,115).

## How fit was tested

Tracts are TIGERweb 2020 (`tigerWMS_Census2020/MapServer/6`) with `POP100`. Each tract is assigned to the unit holding its internal point; a tract counts as **split** when less than 95% of its area that lies inside any unit falls in one unit (shares are of covered area, so shoreline clipping does not count). Populations below are 2020 by internal point unless marked otherwise; 2025 piece sizes are scaled by the county's 2025/2020 ratio and are estimates. Block-level checks were not run.

## Commuting check (LODES 2024)

This check scored the groupings made under the earlier 0.4–1.5M rule. The regrouped counties in Piece size change were searched directly under the new limits.


Run 2026-11-22 on LEHD LODES8 origin–destination files (`https://lehd.ces.census.gov/data/lodes/LODES8/<st>/od/<st>_od_main_JT00_2024.csv.gz`, all jobs, S000). Michigan has no year after 2021, so Wayne uses 2021. The *main* files hold only jobs in the home state, so cross-state commuting (for example New Jersey into Manhattan) is not counted.

- Blocks are aggregated to 2020 tracts and tracts to units as in "How fit was tested".
- **In-piece** = share of a piece's resident workers whose job is in the same piece.
- **Modularity** scores a grouping by within-piece commuting minus what piece sizes alone would predict, the measure Louvain maximizes (rule 4). Raw in-piece share was rejected as the objective: it rewards lopsided splits (in Manhattan it puts the job core in one 1.24M piece and leaves a 0.42M piece with 12% in-piece).
- For each county, the search tried every grouping of the same units into the same number of pieces that is contiguous and 0.4–1.5M in 2025. It was exhaustive except Chicago (77 community areas) and Sacramento (28 RADs), which used local search from the proposal.
- A grouping was changed when the best one raised modularity by 0.003 or more and kept every piece at or under 1.45M (2025), leaving margin for the estimate.

| County | Proposed: in-piece / modularity | Best found | Result |
|---|---|---|---|
| Los Angeles | 30.3% / 0.2734 | 31.2% / 0.2839 | **Revised** (SPAs 2, 3, 8) |
| Harris | 32.1% / 0.1717 | — | Fixed precincts |
| Cook | 39.9% / 0.2395 | 41.7% / 0.2472, but Chicago North 1.50M; with a 1.45M cap 40.2% / 0.2408 | Kept |
| San Diego | 48.8% / 0.2603 | 50.5% / 0.2616 (Central + North City, 1.43M) | Kept |
| Miami-Dade | 50.7% / 0.1621 | same | Confirmed |
| Brooklyn | 26.5% / 0.1937 | same | Confirmed |
| Queens | 20.1% / 0.1467 | 20.7% / 0.1650 | **Revised** |
| Manhattan | 46.0% / 0.0810 (MN07 south); 47.2% / 0.0864 (MN08 south) | 40.8% / 0.0949 | **Revised** |
| Riverside | 39.1% / 0.3088 | 39.9% / 0.3279 | **Revised** |
| San Bernardino | 35.5% / 0.2513 | 35.5% / 0.2534 | Kept |
| Alameda | 35.5% / 0.2784 | same | Confirmed |
| Tarrant | proposal not contiguous | 3 pieces: 34.0% / 0.2337 | **Revised** to 3 pieces |
| Bexar | 45.9% / 0.1121 | 46.6% / 0.1217 | **Revised** |
| Broward | 40.4% / 0.1701 | same | Confirmed |
| Palm Beach | 49.9% / 0.2243 | same | Confirmed |
| Hillsborough | 42.7% / 0.1436 | same | Confirmed |
| Orange FL | 42.8% / 0.1220 | same | Confirmed |
| King | 56.8% / 0.1695 | same | Confirmed |
| Santa Clara | 42.0% / 0.1305 | 42.2% / 0.1499 | **Revised** |
| Sacramento | 36.7% / 0.1027 | 40.0% / 0.1586 | **Revised** |
| Philadelphia | 42.2% / 0.1571 (spec example) | 41.4% / 0.1601 | **Revised** |
| Suffolk | 44.9% / 0.2436 | same | Confirmed |
| Middlesex | 41.7% / 0.2229 | not searched (MAPC line is fixed) | Fixed |
| Wayne | 41.6% / 0.1476 (LODES 2021) | — | Fixed |

- Tarrant: Northeast Tarrant and Arlington CCDs do not touch (a strip of Fort Worth CCD about 750 m wide runs between them). Every other 2-piece grouping exceeds 1.5M, so Tarrant takes 3 pieces: Fort Worth 938,512 (≈1.00M), Northeast Tarrant 617,006 (≈0.66M), Arlington 555,122 (≈0.59M).
- King with 3 pieces (Seattle + North / South / East) scores 0.2461, but modularity rises with piece count, so it is not comparable with 2 pieces. 2 pieces stay (rule 1 target).
- Weakest pieces by in-piece share: LA SPA 6 (13.7%), Manhattan North (19.8%), Queens (≈20–21%), Brooklyn North (21.5%). In New York these are large commuting flows to Manhattan, not grouping errors.

## Decisions by county

Status key: **Verified** = boundary file opened and tract fit tested. **Corrected** = verified, but the plan's proposed source changes. **Inferred** = no official option found; Louvain pieces.

| County | 2025 (M) | Status | Division to use | Units | Proposed pieces |
|---|---|---|---|---|---|
| Los Angeles, CA | 9.69 | Verified | LA County DPH Health Districts (2022), grouped across SPAs | 26 HDs | 10 |
| Cook, IL | 5.19 | Corrected | Chicago community areas + CCDPH districts, holes filled by host district | 77 CAs; 4 districts + 6 holes | 6 |
| Harris, TX | 5.05 | Inferred (precincts no longer fit) | Louvain, built; Houston split | 1,035 units | 5 |
| Maricopa, AZ | 4.69 | Inferred (MAG lead unchecked) | Louvain, built | 487 units (cities + Phoenix tracts) | 5 |
| San Diego, CA | 3.28 | Corrected | SANDAG 2020 Subregional Areas | 41 SRAs | 3 |
| Orange, CA | 3.15 | Inferred | Louvain, built | 75 units (cities + unincorporated tracts) | 3 |
| Miami-Dade, FL | 2.80 | Verified | County Minor Statistical Areas, grouped by major area | 32 MSAs, 7 major areas | 3 |
| Dallas, TX | 2.66 | Inferred | Louvain, built | 29 units | 3 |
| Kings, NY | 2.65 | Verified | DCP 2020 CDTAs (= 18 community districts) | 18 + 2 JIAs | 3 |
| Riverside, CA | 2.54 | Corrected | Census 2020 CCDs (RCTC areas have no file) | 17 CCDs | 3 |
| Clark, NV | 2.41 | Inferred | Louvain, built | 250 units | 3 |
| Queens, NY | 2.36 | Verified | DCP 2020 CDTAs (= 14 community districts) | 14 + 5 JIAs | 3 |
| King, WA | 2.34 | Verified | PHSKC 2020 health regions (built from 61 HRAs) | 4 regions | 3 |
| Tarrant, TX | 2.25 | Corrected | Census 2020 CCDs | 3 CCDs | 3 |
| San Bernardino, CA | 2.22 | Corrected | Census 2020 CCDs (SBCTA site down) | 12 CCDs | 2 |
| Bexar, TX | 2.16 | Corrected | Census 2020 CCDs | 7 CCDs | 2 |
| Broward, FL | 2.01 | Corrected | Census 2020 CCDs | 10 CCDs | 2 |
| Santa Clara, CA | 1.91 | Corrected | MTC travel-model superdistricts (TAZ1454) | 7 | 2 |
| Wayne, MI | 1.77 | Verified | City of Detroit vs. Out-Wayne (Census county subdivisions) | 43 MCDs | 2 |
| Middlesex, MA | 1.67 | Corrected | Towns; MAPC Inner Core vs. rest of county | 54 towns | 2 |
| New York, NY | 1.66 | Verified | DCP 2020 CDTAs (12 community districts) | 12 + 1 JIA | 2 |
| Alameda, CA | 1.64 | Corrected | Census 2020 CCDs = Alameda CTC planning areas | 6 CCDs, 4 areas | 2 |
| Sacramento, CA | 1.62 | Corrected | SACOG Regional Analysis Districts (2007) | 28 | 2 |
| Palm Beach, FL | 1.58 | Corrected | Census 2020 CCDs | 11 CCDs | 2 |
| Philadelphia, PA | 1.57 | Verified | Philadelphia planning districts | 18 | 2 |
| Hillsborough, FL | 1.57 | Corrected | Census 2020 CCDs | 7 CCDs | 2 |
| Suffolk, NY | 1.55 | Corrected | 10 towns + 2 reservations merged into host towns | 12 MCDs | 2 |
| Orange, FL | 1.53 | Corrected | Census 2020 CCDs | 6 CCDs | 2 |

Proposed piece counts for inferred counties are targets from rule 1, not results. Groupings below were first proposed by size and adjacency, then checked against LODES 2024 commuting (see Commuting check). Revised groupings are marked.

## Verified counties

### Los Angeles, CA — 8 SPAs, 3 split by Health Districts → 11 pieces

- Source: LA County Department of Public Health, *Service Planning Areas (2022)*, which replaced the 2012 SPAs, and *Health Districts (2022)*, which nest in the SPAs.
  - SPAs: `https://services.arcgis.com/RmCCgQtiZLDCtblq/ArcGIS/rest/services/DPH_Service_Planning_Areas_SPA/FeatureServer/17`
  - Health Districts: `https://services.arcgis.com/RmCCgQtiZLDCtblq/ArcGIS/rest/services/Health_Districts_2022_view/FeatureServer/0`
  - Tract crosswalk (CT20 → SPA22, HD22, city, CSA, 2024 population): `https://services.arcgis.com/RmCCgQtiZLDCtblq/ArcGIS/rest/services/CT20FIP24CSA_Pop24_Pov24/FeatureServer/1`
- Fit: built from 2020 tracts. All 2,496 tracts fall in exactly one SPA and one HD; no fitting step. Tract 990300 (water) has no SPA.
- This replaces the current 4 Los Angeles pieces.

| SPA | 2024 pop | Piece plan |
|---|---|---|
| 1 Antelope Valley | 414,006 | 1 piece (near the floor; keep whole) |
| 2 San Fernando | 2,162,349 | **Revised:** West Valley + San Fernando HDs (2020: 1,420,267; ≈1.37M) / East Valley + Glendale HDs (787,488; ≈0.76M) |
| 3 San Gabriel | 1,734,850 | **Revised:** El Monte + Foothill + Pomona HDs (1,274,595; ≈1.23M) / Alhambra + Pasadena HDs (478,696; ≈0.46M) |
| 4 Metro | 1,101,389 | 1 piece |
| 5 West | 647,061 | 1 piece |
| 6 South | 993,024 | 1 piece |
| 7 East | 1,259,972 | 1 piece |
| 8 South Bay | 1,520,033 | **Revised:** Harbor + Inglewood + Torrance HDs (1,080,610; ≈1.05M) / Long Beach HD (468,171; ≈0.45M) |

SPA populations are County eGIS 2024 estimates. Split-piece figures are 2020 Census by tract, then the 2025 estimate. The first proposal (West Valley alone; Pomona + El Monte; Inglewood + Torrance) scored lower on commuting.

Risk, still open: the ArcGIS Online org is not labelled as LA County on its face, though the services say they are maintained by DPH. The cross-check against `public.gis.lacounty.gov` (Administrative_Boundaries/MapServer/23) failed again on 2026-11-22: the REST endpoint answers with an Imperva bot challenge, not data.

### Harris, TX — 4 commissioner precincts → 4 pieces

- Source: Harris County Commissioners Court precincts 1–4, the 2021 plan adopted 2021-10-28 ("updated to reflect election results 1/1/23").
  - `https://services.arcgis.com/su8ic9KbA7PYVxPS/ArcGIS/rest/services/Precinct_2025/FeatureServer/0` (last edited 2025-05-24)
  - `https://services.arcgis.com/su8ic9KbA7PYVxPS/ArcGIS/rest/services/Commissioner_Precincts/FeatureServer/0` (data last edited 2026-10-27; areas match Precinct_2025 within rounding)
- 2020 residents by tract internal point: Pct 1 1,175,042; Pct 2 1,176,481; Pct 3 1,186,543; Pct 4 1,193,079 (1,115 tracts). About 1.26M each in 2025.
- Fit: precincts are built from voting precincts and blocks and split some tracts; apply rule 5.
- Rejected: City of Houston vs. rest (2.26M / 2.48M, both over the cap). Houston's 88 super neighborhoods cover only the city.
- Diff, tested 2026-11-22: *All_Pcts* (data edited 2023-04-18, "Ellis3 … updated to reflect election results 1/1/23"), *Precinct_2025* and *Commissioner_Precincts* (2026-10-27) have the same geometry (symmetric difference 0.0000 of each precinct's area) and the same tract assignment for all 1,115 tracts. The 2026-10-27 edit changed no boundary. Freeze *Commissioner_Precincts*.
- Not found: the County Attorney site (`cao.harriscountytx.gov`) has no redistricting or adopted-plan page, and its site search returns nothing for "redistricting" or "commissioners precinct". H-GAC subregions not checked (`www.h-gac.com` returns HTTP 403).
- Risk: political districts, redrawn after each census and possibly mid-decade. No license stated.

### Wayne, MI — Detroit vs. Out-Wayne → 2 pieces

- Source: Census TIGER 2020 county subdivisions (`tigerWMS_Census2020/MapServer/20`), public domain.
- 2020: Detroit 639,111; Out-Wayne (42 other MCDs) 1,154,450. Both in range at 2025 totals.
- Fit: 9 of 627 tracts straddle MCD lines; those touching Detroit hold 0–154 people.
- A SEMCOG Western Wayne / Downriver split was not checked and is not needed.

### Philadelphia, PA — 18 planning districts → 2 pieces

- Source: City of Philadelphia *Planning_Districts* (18 features, last edited 2026-06-25): `https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest/services/Planning_Districts/FeatureServer/0`
- Fit: 9 of 408 tracts straddle a line, most 95%+ in one district; majority-area assignment. Lower South (5,925) merges into a neighbour.
- Pieces, set by the commuting check: Center, South and West = Central, South, Lower South, Lower Southwest, University Southwest, West, West Park, Lower Northwest (2020: 631,615; ≈0.62M) / North, Northeast and Upper Northwest = the other 10 districts (972,182; ≈0.95M). Lower South (5,925) needs no merge in this grouping.
- Publisher: the ArcGIS item (`0960ea0f38f44146bb562f2b212075aa`, owner `maps.phl.data`, modified 2026-06-25) says the districts "are used by the Philadelphia City Planning Commission" under the Philadelphia2035 comprehensive plan. License: an "as is" disclaimer with a hold-harmless clause; no use or redistribution limit stated. `metadata.phila.gov` loads its records from `api.knackhq.com`, which is not allowed, so the City's metadata record itself was not read.

### Suffolk, NY — towns → 2 pieces (corrected)

- Source: Census TIGER 2020 county subdivisions (`tl_2020_36_cousub.zip`). There are 10 towns plus 2 reservations outside any town: Poospatuck (in Brookhaven) and Shinnecock (in Southampton). Merge each reservation into its host town.
- Fit: 381 of 385 tracts nest in one MCD; the 4 split tracts are resolved by the reservation merge, with zero population error.
- Pieces (2025): West = Babylon, Huntington, Islip, Smithtown (≈883k); East = Brookhaven, Riverhead, Southampton, East Hampton, Southold, Shelter Island + reservations (≈663k).
- Crosswalk: build from the 2020 block assignment file (MCD).

### Kings, Queens and New York, NY — DCP 2020 CDTAs → 2 pieces each

- Source: NYC Department of City Planning, *2020 Community District Tabulation Areas* (NYC Open Data `xn3r-zk6y`, 71 features citywide, current version 26c, rows updated 2026-11-02, refreshed quarterly) and *2020 Census Tracts to 2020 NTAs and CDTAs Equivalency* (`hm78-6dwm`, 2,327 tracts, rows updated 2021-09-20; water tracts excluded). CDTAs are built from whole 2020 tracts.
  - `https://data.cityofnewyork.us/resource/xn3r-zk6y.geojson`
  - `https://data.cityofnewyork.us/resource/hm78-6dwm.json`
- Units: Brooklyn 18 CDs + 2 joint interest areas (BK55 Prospect Park, 15 residents; BK56 Jamaica Bay West, 21); Queens 14 + 5 JIAs (QN80–QN84: LaGuardia, Flushing Meadows, Forest Park, JFK, Jamaica Bay East; 74 residents in all); Manhattan 12 + 1 JIA (MN64 Central Park, 129). Bronx 12 + 3 JIAs and Staten Island 3 + 1 JIA are not needed.
- Fit, tested: every equivalency tract matches its CDTA polygon. Brooklyn 805 tracts, 0 split; Manhattan 310, 0 split; Queens 725, 2 split by <7% of area at Forest Park edges (5,172 residents). Merge each JIA into the CD it touches most.
- Cross-borough cases, confirmed in the equivalency: tract 36061030900 (Marble Hill, 8,594) is Manhattan County but CDTA BX08; tract 36005000100 (Rikers Island) is Bronx County but CDTA QN01. Pieces follow the county.
- Replaces the Census PUMA version: same tracts in Brooklyn and Queens, and keeps all 12 Manhattan districts instead of 10 PUMAs.
- License: none stated on either dataset (agency credit: DCP). DCP's own BYTES page on `www.nyc.gov` was refused (HTTP 403), so the release note was not read.

| Borough | Piece | CDTAs | 2020 | 2025 est. |
|---|---|---|---|---|
| Brooklyn | North | BK01–06, 08, 09, 16, 17 + BK55 | 1,415,863 | ≈1.37M |
| Brooklyn | South | BK07, 10–15, 18 + BK56 | 1,320,175 | ≈1.28M |
| Queens | North (revised) | QN01–05, 07, 11 + QN80, 81 | 1,263,924 | ≈1.24M |
| Queens | South (revised) | QN06, 08–10, 12–14 + QN82–84 | 1,141,540 | ≈1.12M |
| Manhattan | Lower and Midtown (revised) | MN01–06 | 682,455 | ≈0.67M |
| Manhattan | Upper (revised) | MN07–12 + MN64 + Marble Hill | 1,011,796 | ≈0.99M |

JIA residents are left out of the Brooklyn 2020 figures and included in the revised Queens and Manhattan rows (at most 129 people per JIA). The commuting check revised Queens (QN06 and QN11 swap) and Manhattan (split at 59th/60th Street instead of putting MN07 or MN08 with the south).

### Middlesex, MA — towns, Inner Core vs. rest → 2 pieces (corrected)

- Units: 54 towns and cities (Census county subdivisions). All 357 tracts nest in towns; no fitting step.
- Correction: the proposed "MAPC vs. Northern Middlesex" split leaves the non-MAPC piece at 349,554 (2020), below the floor. NMCOG's *Our Communities* page lists 9 towns: Billerica, Chelmsford, Dracut, Dunstable, Lowell, Pepperell, Tewksbury, Tyngsborough, Westford (310,009). MAPC's subregion lists cover 40 Middlesex towns (1,282,448). The other 5 (Ashby, Ayer, Groton, Shirley, Townsend; 39,545) are presumably Montachusett; that membership is unverified (`mrpc.org` not tried).
- Use: MAPC Inner Core Committee towns in Middlesex vs. the rest. Membership confirmed on MAPC's *Subregions* page (21 ICC members); the 11 in Middlesex are Arlington, Belmont, Cambridge, Everett, Malden, Medford, Melrose, Newton, Somerville, Waltham, Watertown.
- 2020: Inner Core 667,335; rest (43 towns) 964,667.

### Cook, IL — Chicago community areas + CCDPH districts → 4 pieces (corrected)

- Chicago: *Boundaries – Community Areas*, City of Chicago (`igwz-8jzy`, 77 areas, rows updated 2025-04-22; license "See Terms of Use", terms page not opened): `https://data.cityofchicago.org/resource/igwz-8jzy.geojson`
  - Fit: 15 populated tracts (74,417 residents) have more than 5% of their in-city area in a second community area; largest-share assignment. The city line also splits two tracts (17031770700, 2,537; 17031810400, 5,409).
  - 2020 by community area: 2,745,830.
- Suburbs: Cook County Department of Public Health, *all.subcook* (`tvy4-qfgw`, 155 municipality and township features, rows dated 2017-04-14; **Public Domain**): `https://datacatalog.cookcountyil.gov/resource/tvy4-qfgw.geojson`
  - 4 districts: North 960,863; West 514,946; South 451,517; Southwest 366,685 (2020).
  - Holes (outside CCDPH jurisdiction): Evanston 78,110; Skokie 67,075; Oak Park 54,583; Burbank 25,127; Stickney 7,110; Forest View 3,695 (235,700 in all). University Park and Stickney Township hold no Cook tract internal points. Fill each hole into the district around it.
  - Fit: 18 populated tracts (85,187) split between districts; largest-share assignment.
- The township fallback is no longer needed. CCDPH's own site could not be read: `www.cookcountypublichealth.org` redirects to `cookcountypublichealth.org`, which is not allowed. The data catalog record above is the source.

| Piece | Units | 2020 | 2025 est. |
|---|---|---|---|
| Chicago North | Far North, Northwest, North and Central sides (CAs 1–22, 32, 33, 76, 77) + Humboldt Park (23), West Town (24) | 1,370,970 | ≈1.35M |
| Chicago South and West | CAs 25–31, 34–75 | 1,374,860 | ≈1.35M |
| North suburbs | North District + Evanston, Skokie | 1,106,048 | ≈1.09M |
| West and south suburbs | West, Southwest, South Districts + Oak Park, Burbank, Stickney, Forest View | 1,423,663 | ≈1.40M |

The "sides" are a common grouping of community areas, not a City file. A 3-piece Chicago (North 1,230,138; West + Southwest 862,979; South + Far Southeast + Far Southwest 652,713) also fits but gives Cook 5 pieces against a target of 4.

### San Diego, CA — SANDAG SRAs grouped into MSAs → 3 pieces (corrected)

- Source: SANDAG / SanGIS *Subregional_Areas_2020* (41 SRAs; "captured by dissolving the Series 15 MGRA geometry … so that SRAs align with 2020 Census block groups, tracts"; item modified 2026-07-14): `https://geo.sandag.org/server/rest/services/Hosted/Subregional_Areas_2020/FeatureServer/0`
- Correction: the only MSA file is *Major_Statistical_Area_2010* (7 MSAs, 2010 tract base). Build MSAs from 2020 SRAs instead: the SRA code's tens digit is the MSA (0 Central … 6 East County). Tested: 40 of 41 SRAs lie ≥97% in the matching 2010 MSA; Central San Diego is 94% (bay water).
- Rejected: County HHSA 6 regions (*Health_and_Human_Service_Regions_CN*, edited 2024-09-04). They are built from ZIP code polygons, so they do not nest in tracts.
- Fit: 7 populated tracts (24,863) have under 95% of their area in one SRA, all on San Diego Bay (Coronado, downtown); not checked with blocks. Tract 06073018301 (1,008, coast near Oceanside) has its internal point outside all SRAs; assign to North County West.
- License: SanGIS end-user agreement. Use as-is; SanGIS "discourages, but does not prohibit, the re-distribution of this data"; credit SanGIS.

| MSA (2020 SRAs) | 2020 | Piece |
|---|---|---|
| Central (SRAs 1–6) | 641,359 | A |
| South Suburban (20–22) | 422,628 | A |
| North City (10–17) | 799,237 | B |
| East Suburban (30–39) | 518,871 | B |
| North County West (40–43) | 426,238 (+1,008) | C |
| North County East (50–55) | 465,664 | C |
| East County (60–63) | 23,629 | C |

Pieces (2020): A Central + South 1,063,987; B North City + East Suburban 1,318,108; C North County + East County 916,539. 2025 ≈ the same (county ratio 0.994). Adjacency of North City and East Suburban not yet checked.

### Riverside, CA — Census CCDs → 2 pieces (corrected)

- RCTC confirms three Measure A areas (Western Riverside County, Coachella Valley, Palo Verde Valley) on its *Measure A* page but publishes no boundary file.
- Use: Census 2020 CCDs (17), public domain (`tigerWMS_Census2020/MapServer/20`). All 518 tracts nest; 0 split.
- Measure A areas in CCD terms (approximation): Coachella Valley = Coachella Valley, Cathedral City-Palm Desert, Desert Hot Springs, Palm Springs CCDs (441,531); Palo Verde = Blythe, Chuckwalla Valley (21,704); Western = the other 11 (1,954,950). Western is over the cap, so pieces cut across it.

| Piece | CCDs | 2020 | 2025 est. |
|---|---|---|---|
| Northwest (revised) | Riverside 479,141; Perris Valley 317,362 (Moreno Valley, Perris, Menifee); Corona 177,311; Jurupa 174,806; Elsinore Valley 128,890; Lake Mathews 28,249; Norco 25,283 | 1,331,042 | ≈1.40M |
| South and east (revised) | Murrieta 322,536; Coachella Valley 190,541; Hemet-San Jacinto 179,665; Cathedral City-Palm Desert 147,400; San Gorgonio Pass 106,536; Desert Hot Springs 59,643; Palm Springs 43,947; Idyllwild 15,171; Blythe 13,809; Chuckwalla Valley 7,895 | 1,087,143 | ≈1.14M |

Revised by the commuting check: Elsinore Valley moves to the Northwest piece.

### San Bernardino, CA — Census CCDs → 2 pieces (corrected)

- SBCTA Measure I subareas unverified: `sbcta-gis.sanbag.ca.gov` returned HTTP 503 or timed out on every try.
- Use: Census 2020 CCDs (12), public domain. Fit: 1 of 466 tracts split (06071012106, 2,107; 67% Victorville-Hesperia, rest Barstow).
- The Valley in CCD terms (Ontario + San Bernardino + Yucaipa CCDs) held 1,574,448 in 2020, so it must be split, as suspected.

| Piece | CCDs | 2020 | 2025 est. |
|---|---|---|---|
| West Valley and High Desert | Ontario 660,377 (Chino, Chino Hills, Montclair, Ontario, Rancho Cucamonga, Upland); Victorville-Hesperia 412,533; Barstow 43,451; Newberry Springs-Baker 11,084; Needles 6,982; Mount Baldy-Wrightwood 6,617; Searles Valley 1,890 | 1,142,934 | ≈1.16M |
| East Valley and mountains | San Bernardino 859,039 (incl. Fontana, Rialto, Redlands, Colton); Twentynine Palms-Yucca Valley 72,041; Yucaipa 55,032; Big Bear 26,826; Lake Arrowhead 25,782 | 1,038,720 | ≈1.06M |

Contiguity of the desert CCDs within each piece not yet checked.

### Alameda, CA — Census CCDs = Alameda CTC planning areas → 2 pieces (corrected)

- Alameda CTC planning areas, from its 2012 TEP fact sheets: North = Alameda, Albany, Berkeley, Emeryville, Oakland, Piedmont; Central = Hayward, San Leandro; South = Fremont, Newark, Union City; East = Dublin, Livermore, Pleasanton; each "and nearby unincorporated communities". The VRF page still distributes funds by these four areas. No GIS file.
- Use: Census 2020 CCDs (6), public domain. All 379 tracts nest; 0 split. City membership matches the CTC lists exactly; Castro Valley, Ashland, San Lorenzo, Cherryland and Fairview fall in Hayward CCD (Central), which answers the unincorporated question.
- Pieces: North = Oakland 464,821 + Berkeley 144,592 + Alameda 78,280 CCDs (687,693; ≈0.67M in 2025); Central + South + East = Hayward 402,646 + Fremont 347,173 + Livermore-Pleasanton 244,841 (994,660; ≈0.97M).

### King, WA — PHSKC health regions → 2 pieces

- Source: Public Health – Seattle & King County, *Health Reporting Areas 2020* (61 HRAs, "aggregates of Census 2020 blocks") and *Public Health Regions* (4: North, Seattle, South, East, built from HRAs). Data last edited 2026-10-14.
  - HRAs: `https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/HEALTH_REPORTING_2020_AREA_2919/FeatureServer/0`
  - Regions: `https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/HEALTH_REGION_2020_AREA_2924/FeatureServer/0`
  - Catalog: `https://www5.kingcounty.gov/sdc/?Layer=health_reporting_2020_area`
- Fit: block-built, so tracts split. HRAs: 132 of 495 tracts split (641,282 residents). Regions: 17 split (69,453). Use regions with largest-share assignment.
- 2020 by region: South 794,935; Seattle 737,027 (incl. 2 shoreline tracts, 12,032); East 593,495; North 144,218.
- Pieces: Seattle + North 881,245 (≈0.91M in 2025) / South + East 1,388,430 (≈1.43M). Alternative 3 pieces (Seattle + North / South / East ≈ 0.91 / 0.82 / 0.61M) all fit but exceed the target of 2.
- License: King County GIS terms permit copying and distributing; only sale needs a written agreement. Publishing derived tract groupings is allowed.

### Miami-Dade, FL — Minor Statistical Areas → 2 pieces

- Source: Miami-Dade County, *Minor Statistical Area* ("Planning and Zoning Minor Statistical Areas … representing groupings of Census"; "Updated: Every 10 yrs"; 35 polygons, 32 IDs from 1.1 to 7.6; data last edited 2018-11-13, so likely a 2010 tract base). License text read in part: an "as is" disclaimer; no redistribution terms seen.
  - `https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/MinorStatisticalArea_gdb/FeatureServer/0` (hub item `e2f0a8ff1e404913bfbc27ed2de54cd1`)
- Fit with 2020 tracts: 12 of 707 tracts split (36,365); 1 tract (12086012403, 1,881) has its internal point outside all areas.
- The file has no names. The first digit of the ID marks 7 major areas; by location: 1 beaches (144,565), 2 north-east (411,692), 3 north-west (413,689), 4 north-central (416,512), 5 central-south (638,760), 6 west Kendall (352,478), 7 south county and Everglades (322,190).
- Pieces: North = areas 1–4 (1,386,458; ≈1.44M in 2025) / South = 5–7 (1,313,428; ≈1.36M). North is close to the cap; recheck with 2025 tract estimates.

## CCD and regional-division counties (corrected)

These 8 counties were inferred in the plan; each now uses an official division (rule 3 or rule 9), adopted 2026-11-22. Each file below was opened and fit-tested against 2020 tracts. Pieces are contiguous by polygon adjacency; populations are 2020 by tract internal point, and 2025 is scaled by the county ratio. CCDs are Census 2020 county subdivisions (`tigerWMS_Census2020/MapServer/20`), public domain.

| County | Source | Fit | Piece A (2020 → 2025) | Piece B (2020 → 2025) |
|---|---|---|---|---|
| Tarrant | 3 CCDs | 449 tracts, 0 split | **3 pieces (revised):** Fort Worth 938,512 → ≈1.00M | Northeast Tarrant 617,006 → ≈0.66M; Arlington 555,122 → ≈0.59M (the two CCDs do not touch) |
| Bexar | 7 CCDs (all "San Antonio …") | 375 tracts, 0 split | **Revised:** Central 672,470 + Northeast 278,336 + South 52,062 + East 42,581 = 1,045,449 → ≈1.12M | North 380,994 + Northwest 338,971 + West 243,910 = 963,875 → ≈1.04M |
| Broward | 10 CCDs | 417 tracts, 0 split | Deerfield Beach, Pompano Beach, Coral Springs-Margate, Fort Lauderdale, Conservation = 867,727 → ≈0.90M | Plantation, Davie, Hollywood, Miramar-Pembroke Pines, Hallandale Beach = 1,076,648 → ≈1.11M |
| Palm Beach | 11 CCDs | 373 tracts, 2 split (8,317) | Jupiter, Riviera Beach, West Palm Beach, Lake Worth, Royal Palm Beach-West Jupiter, Western Community, Belle Glade-Pahokee, Glades = 789,826 → ≈0.84M | Boynton Beach-Delray Beach, Boca Raton, Sunshine Parkway = 702,365 → ≈0.74M |
| Hillsborough | 7 CCDs | 335 tracts, 1 split (12057014300, 4,809) | Tampa 711,263 + Keystone-Citrus Park 143,294 = 854,557 → ≈0.92M | Brandon, Wimauma-Riverview, Plant City, Ruskin, Palm River-Gibsonton = 605,205 → ≈0.65M |
| Orange FL | 6 CCDs | 267 tracts, 0 split | Orlando 642,865 + Union Park 261,814 + East Orange 59,058 = 963,737 → ≈1.03M | Southwest Orange 256,786 + Winter Garden-Ocoee 100,495 + Apopka 108,890 = 466,171 → ≈0.50M |
| Santa Clara | MTC superdistricts 8–14, from *Travel Analysis Zones (TAZ1454)* (`services3.arcgis.com/i2dkYWmb4wHvYPda/.../Travel_Analysis_Zones/FeatureServer/0`, owner MTC, modified 2019-06-26; no names, no license text) | 408 tracts; about 10 split between superdistricts (42,135) | **Revised:** SDs 8, 9, 10 (north county and west valley by location) = 835,992 → ≈0.82M | SDs 11, 12, 13, 14 (San Jose and south county) = 1,100,267 → ≈1.09M |
| Sacramento | SACOG *Regional Analysis Districts 2007* (`services6.arcgis.com/YBp5dUuxCMd8W1EI/.../Regional_Analysis_Districts_2007/FeatureServer/0`, item modified 2021-05-19; 2007 vintage) | 363 tracts, 21 split (88,254) | **Revised (local search):** city core and south county = Downtown, East Sacramento, Land Park-Pocket-Meadowview, South Sacramento, Rosemont, Vineyard, Laguna, Elk Grove, Franklin, Delta = 688,835 → ≈0.70M | north and east = the other 18 RADs (incl. Arden Arcade, Carmichael, North Sacramento, South Natomas, Folsom, Citrus Heights, Rancho Cordova, Galt) = 896,220 → ≈0.92M |

- Orange FL alternative rejected: Orlando + Apopka + Winter Garden-Ocoee vs. the rest leaves Southwest Orange cut off from Union Park and East Orange.
- Palm Beach: tract 12099005412 (3,001) straddles the piece line; 12099007917 (5,316) splits inside piece A.
- Santa Clara: MTC zones are an older travel-model geography (1,454 zones regionwide, pre-2020). A newer MTC file may exist on MTC's own open-data site, not tried. CCDs do not fit (San Jose CCD 1,797,266).
- Sacramento: SACOG's current zones (*Transportation Analysis Zone 2021*) are served from `services.sacog.org`, which is not allowed, so a newer RAD set may exist. CCDs do not fit: Sacramento CCD 1,200,486 and the rest 384,569, under the floor.

## Inferred counties

Harris, Dallas, Clark, Maricopa and Orange CA use inferred pieces (rule 4), built 2026-11-22 with `regions/pieces/build_inferred.py`. Harris joined when its precincts stopped fitting the 1.2M cap.

- **Units:** 2020 tracts; tracts whose internal point lies in the same incorporated place (TIGERweb 2020 layer 26) are merged, so each city is one unit. Cities over 1.17M in 2025 (Houston, Dallas, Phoenix) are left as tracts.
- **Graph:** LODES 2024 OD main, all jobs; home and job both in the county.
- **Search:** Louvain (networkx 3.7) at resolutions 0.5–2.0 with 5 seeds each. Each result is split into contiguous parts, merged to the target count by best modularity gain, then refined by single-unit moves under the contiguity and 0.41–1.17M (2025) limits. The valid result with the highest modularity is kept.
- **Outputs:** `regions/pieces/inferred_tract_piece.csv` (3,918 tracts, each in exactly one piece) and `regions/pieces/inferred_pieces.json` (per-piece cities, populations, workers).

Current pieces (rebuilt 2026-11-22 under the 0.4–1.2M rule) are listed in Piece size change. Modularity: Harris 0.2427, Dallas 0.1872, Clark 0.1208, Maricopa 0.2102, Orange 0.2437. Houston, Dallas and Phoenix are split along tract lines because each exceeds 1.17M. Piece names list the three largest places, census-designated places included (for example Paradise and Spring Valley in Clark).

Why no official division:


- **Dallas:** CCDs do not fit (Northeast Dallas 1,610,176; Southwest Dallas 1,003,363). NCTCOG publishes its 2050 demographic forecast only by TAZ, city and county. No district-level file was found.
- **Clark:** CCDs do not fit (Las Vegas 2,014,651; Clark 250,810). An ArcGIS Online search found no county-wide planning or statistical division.
- **Maricopa:** MAG Municipal Planning Areas / Regional Statistical Areas not checked. `geo.azmag.gov` answers with a Cloudflare challenge (HTTP 403). Census CCDs do not fit (Phoenix CCD 3,331,925).
- **Orange, CA — RSA lead not usable as proposed:** no Regional Statistical Area file or page was found on the CDR site. Its sitemap, *Census 2020* page and 2020 tract shapefile and workbook (`Shapefile_Census2020.shp.zip`, `Census2020_OC_CT.xlsx`) carry no RSA field. Census CCDs do not fit (Anaheim-Santa Ana-Garden Grove CCD 1,689,454).

Commissioner and supervisor districts exist in all of these counties but are political, not planning or statistical, divisions. They were not checked. Harris uses them only because nothing else covers the county.

## Outputs

Scripts and outputs in `regions/pieces/`, run in this order: `build_groups.py`, `build_crosswalk.py`, `build_demographics.py`, `build_geojson.py`, `build_subareas.py`; then `freeze_inputs.py`, `check_pieces.py` and `release.py` (see Versions, IDs and edits). Each takes `--cache DIR`. Figures are for release 1.0.

- `groups.json` (`build_groups.py`): per county, method (official | inferred | whole), source, units, modularity, boundary cut, job centres (label, units, residents, tracts), pieces and the tract assignment with its method and share.
- `crosswalk_tract_piece.csv` (`build_crosswalk.py`): `tract_geoid, county_fips, piece_id, piece_name, method, source_id, assign (nested | largest_share | internal_point | contiguity | pinned), pop2020_share`. 23,869 tracts in 50 counties, each in exactly one of 134 pieces: 23,793 nested, 48 by largest 2020 block-population share (rule 5), 26 water-only, 2 moved for contiguity.
- `split_tracts.csv`: populated tracts a piece line cuts, with 2020 residents on each side.
- `pieces_summary.csv`: `piece_id, county_fips, county, piece_name, piece_components, method, pop2020, pop2025_est` (2025: county Vintage 2025 total scaled by tract).
- `pieces.geojson` (`build_geojson.py`, 1.4 MB): dissolved cartographic (shoreline-clipped) tract boundaries, offshore island parts cut, simplified about 20 m. Properties: `piece_id, county_fips, county, name, components, method, source_id, neighbors, pop2020, pop2025, jobs_lodes, work_inside, lodes_year` and five population-mix shares.
- `tract_demographics.csv`, `piece_demographics.csv` (`build_demographics.py`): 2020 PL 94-171 P2 counts and shares.
- `crosswalk_tract_subarea.csv`, `subareas_summary.csv`, `subareas.geojson` (`build_subareas.py`): every tract's subarea and 2020 PUMA; per subarea its piece, name, main PUMA, `kind` (puma | puma_part), `puma_share`, residents, LODES jobs; the GeoJSON adds neighbors, `work_inside` and `lodes_year`.
- `piece_registry.csv`: stable piece IDs, anchor tracts and region names (rules 15, Versions). `pins.csv`: manual tract-to-piece pins (empty in 1.0). `VERSION`: the version being built.
- `inputs/manifest.csv`, `inputs/snapshot/` (`freeze_inputs.py`): every input with source, publisher, license, retrieval and last-edit dates, SHA-256; snapshots of 9 local-government layers (SanGIS pinned by hash only).
- `releases/<version>/` (`release.py`): frozen crosswalks and registry, `release.json`, and `changes.csv` against the previous release.
- `map.html`: preview page for `pieces.geojson` with a subarea overlay (serve the folder over HTTP to open it locally).

Geometry notes: see Review (contiguity and offshore areas).

## Versions, IDs and edits

**Stable IDs.** `piece_registry.csv` (`piece_id, county_fips, anchor_tract, piece_name, status, since_version, note`) is the list of piece IDs. A built piece takes the ID and name of the registry anchor tract it holds. A piece holding no active anchor gets the next unused number in its county and a note to name it; an ID whose anchor no longer marks its own piece (gone, or sharing a piece with a lower ID) is retired and never reused. Pieces that do not change keep their IDs whatever happens elsewhere. Subarea IDs are `<piece_id>-<PUMA5CE>` (a letter is added where one PUMA leaves several parts in a piece).

**Repeatable builds.** Every build script re-runs itself with `PYTHONHASHSEED=0`. Without it, Python's per-run ordering of sets of names changed tie-breaks in the search: two builds of the same code and inputs moved 977 tracts in five counties (found 2026-11-27).

**Frozen inputs.** `freeze_inputs.py` writes `inputs/manifest.csv` from the inputs the last build read (logged by the scripts) and snapshots the local-government layers in `inputs/snapshot/`. `PIECES_REFRESH=1` lets a build read newer sources on purpose; re-run `freeze_inputs.py` afterwards.

**Releases.** `VERSION` holds the geography version being built; new registry entries are stamped with it. `release.py --version X` runs `check_pieces.py`, refuses to release if any check fails, and writes `releases/X/` with the tract crosswalks, the registry, `release.json` (date, build commit, parameters, counts, checks, SHA-256 of every output and of the manifest) and, from the second release on, `changes.csv`: every tract whose piece or subarea changed, with its residents. Releases are never overwritten.

**Release 1.0 (2026-11-27).** The first repeatable build regrouped two counties against the earlier unseeded builds: Los Angeles (the West Health District stands alone as Westside; Crenshaw and South Central form a piece; NELA and Boyle Heights join Pasadena) and Maricopa (central Phoenix with Maryvale, Laveen and Avondale; Scottsdale with Paradise Valley and Arcadia; Gilbert with Mesa), plus 39 tracts in Harris, Travis and Orange CA. Before the release the freed IDs 06037-10 and 04013-06 were given to the new pieces and those counties renamed; from 1.0 on, IDs follow the registry rules. 39 names were also revised after a second review (pieces whose names left out large parts, such as Downriver in Wayne and the southwest suburbs in Hennepin). All checks pass. Inputs: 401 (10 local-government layers snapshotted, 7.4 MB; 391 Census and LEHD inputs pinned by SHA-256).

**Release 1.0.1 (2026-11-27).** Same geography as 1.0 (no tract changed). The SanGIS layer is pinned by SHA-256 only and its snapshot removed, because SanGIS discourages redistribution and the repository may go public: 9 layers snapshotted (6.0 MB), 392 inputs pinned.

**Editing later.**
- Rename a piece: edit `piece_name` in `piece_registry.csv`, re-run `build_crosswalk.py` and the later steps (about 15 minutes).
- Move single tracts: add `tract_geoid, piece_id, note` rows to `pins.csv` (applied after grouping and repair), re-run `build_crosswalk.py` onward. `check_pieces.py` catches pins that break contiguity, size or a job centre.
- Change one county's grouping (anchors, kept-whole districts, source division): edit `build_groups.py`, run `build_groups.py --fips <county>` (minutes), then `build_crosswalk.py` onward.
- Change the size rules or method for all counties: a full rebuild (about an hour), then review.
- Then: bump `VERSION`, run `check_pieces.py` and `release.py`. Downstream data re-aggregates from the tract crosswalk; `changes.csv` lists exactly which tracts moved.

## Checks before freezing

`check_pieces.py --cache DIR` checks the built outputs and exits non-zero on any failure:

- **coverage:** every 2020 tract of each 1.0M+ county in exactly one piece and one subarea.
- **registry:** every piece ID active, each anchor inside its own piece, names unique per county and at most 45 characters, no unnamed new piece, pins applied.
- **totals:** each county's pieces sum to its 2020 count and its Vintage 2025 estimate.
- **size:** split-county pieces within 0.45–1.1M (2025); whole counties 1.0–1.25M and listed as whole.
- **contiguity:** one populated land body per piece, apart from islands that touch no other piece.
- **necks:** no piece joined by a strip narrower than about 700 m (rule 13).
- **job centres:** every job core and named district in one piece; anchor sets in different pieces (rule 12).
- **subareas:** nested in their piece, at least 30,000 residents, exact-PUMA flags consistent.
- **files:** both GeoJSON files match their summaries.

Each district that depends on pieces is still rebuilt and re-checked against the district size rule (0.35–1.5M) outside this repository.

## Open questions

1. Pieces keep 36% of commuting inside (median). 11 pieces are under 20%: seven in the NYC boroughs (Bronx, Queens, Brooklyn, Upper Manhattan), three LA Health District groupings, and southeast Denton (Frisco and Carrollton, which commute to Dallas and Collin). Accept, or go larger for those counties?
5. Region names were written from general knowledge and revised once after a second review (39 changes). Six are 42–44 characters (Harris northeast, Broward central and north, Middlesex Inner Core, western Suffolk, southern Westchester). A local check, county by county, would still help.
6. SanGIS (San Diego) is pinned by hash only since release 1.0.1, so the repository can go public. Its snapshot is still in the git history of this branch (commits ce6a3ed and dae4839) unless that history is rewritten or squashed before the branch is published or merged. If SANDAG changes the layer, a fresh build stops at the hash check; keep a private copy of the frozen answer to rebuild 1.0 exactly.
2. Official sources for the 22 new counties were not searched (Census CCDs or Louvain used). Look for local planning or statistical areas, county by county?
3. Harris and Los Angeles: the Review's recommendation (Louvain for Harris; Health Districts across SPAs for LA) still holds at the smaller size. Revisit?
4. San Bernardino, Santa Clara, Sacramento: newer SBCTA, MTC and SACOG files once their hosts are reachable.

## Re-check list

Hosts tested on 2026-11-22 that still refuse or fail:

- Los Angeles: `public.gis.lacounty.gov` (REST answers with an Imperva challenge)
- San Bernardino: `sbcta-gis.sanbag.ca.gov` (HTTP 503 / timeout); `www.gosbcta.com` answers but was not searched
- NYC: `www.nyc.gov` (HTTP 403), for DCP's release notes and terms
- Maricopa: `geo.azmag.gov` (HTTP 403, Cloudflare challenge)
- Harris: `www.h-gac.com` (HTTP 403)
- Broward: `www.broward.org` (HTTP 403)
- Santa Clara: `sccgov.org` (no answer)

Hosts not on the allowlist that a check needed:

- `cookcountypublichealth.org` (where `www.cookcountypublichealth.org` redirects)
- `api.knackhq.com` (content behind `metadata.phila.gov`)
- `services.sacog.org` (SACOG's current zones)
- `www.mrpc.org` (Montachusett membership; not tried)
- MTC open data (host not identified)

Allowed and answering, but not searched this round: `wrcog.us`, `www.cvag.org`, `gisdata.kingcounty.gov`, `www.miamidade.gov`, `www.sacog.org`, `www.vta.org`, `www.saccounty.gov`, `www.sanantonio.gov`, `www.bexar.org`, `www.clarkcountynv.gov`, `discover.pbcgov.org`, `www.planhillsborough.org`, `www.ocfl.net`, `www.ocgov.com`, `octa.net`, `www.sandiegocounty.gov`, `hub.arcgis.com`, `gis-kingcounty.opendata.arcgis.com`.

## Sources opened

- Census Vintage 2025 county estimates: `https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/counties/totals/co-est2025-alldata.csv`
- Census TIGERweb 2020 (tracts layer 6, county subdivisions layer 20, incorporated places 26, CDPs 28): `https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2020/MapServer`
- Census TIGER/Line 2020 county subdivisions and PUMAs, tract-to-PUMA relationship file, 2020 block assignment files, 2020 PL 94-171 (NY, TX, WA): `https://www2.census.gov/geo/` and `https://www2.census.gov/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171/`
- LEHD LODES8 OD main and WAC files, JT00, 2024 (CA, TX, IL, FL, NY, WA, PA, MA, AZ, NV, OH, MN, NC, UT, VA, GA, MD) and 2021 (MI): `https://lehd.ces.census.gov/data/lodes/LODES8/`
- Census 2020 PL 94-171 redistricting files for the same 18 states (`www2.census.gov/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171/`), cartographic tracts `cb_2020_us_tract_500k`, TIGERweb places (layers 26, 28) and county subdivisions (layer 20)
- LA County DPH SPA, Health District and tract population services (`services.arcgis.com/RmCCgQtiZLDCtblq`)
- Harris County precinct, city limit and super neighborhood services (`services.arcgis.com/su8ic9KbA7PYVxPS`)
- City of Philadelphia planning districts (`services.arcgis.com/fLeGjb7u4uXqeF9q`)
- SANDAG: `https://geo.sandag.org/server/rest/services/Hosted` (Subregional_Areas_2020, Major_Statistical_Area_2010, Health_and_Human_Service_Regions_CN); portal item `https://geo.sandag.org/portal/sharing/rest/content/items/bf4a734115bc46d29f146f2b51107f2f`
- RCTC: `https://www.rctc.org/measure-a/`, `https://www.rctc.org/about/`
- Alameda CTC: `https://www.alamedactc.org/funding/fund-sources/vehicle-registration-fee`, `https://www.alamedactc.org/2012-alameda-county-transportation-expenditure-plan` and its four fact sheets (`/wp-content/uploads/2018/12/{North,Central,South,East}_County_TEP_Fact_Sheet_v6.pdf`)
- King County: `https://www5.kingcounty.gov/sdc/?Layer=health_reporting_2020_area`, `https://www5.kingcounty.gov/sdc/?Layer=health_region_2020_area`, services `services.arcgis.com/Ej0PsM5Aw677QF1W`, terms `https://kingcounty.gov/en/dept/kcit/data-information-services/gis-center/about/terms-conditions-copyrights`
- City of Chicago: `https://data.cityofchicago.org/api/views/igwz-8jzy.json` and its GeoJSON export
- Cook County: `https://datacatalog.cookcountyil.gov/api/views/tvy4-qfgw.json` and its GeoJSON export
- MAPC: `https://www.mapc.org/get-involved/subregions/`
- NYC Open Data: `https://data.cityofnewyork.us/api/views/hm78-6dwm.json`, `https://data.cityofnewyork.us/api/views/xn3r-zk6y.json` and their exports
- CDR, Cal State Fullerton: `https://www.fullerton.edu/cdr/`, `https://www.fullerton.edu/cdr/sitemap.xml`, `https://www.fullerton.edu/cdr/demographics/census2020.html`, `https://www.fullerton.edu/cdr/mapping/index.html` and the 2020 tract files
- Miami-Dade: `https://gis-mdc.opendata.arcgis.com/api/search/v1/collections/all/items/e2f0a8ff1e404913bfbc27ed2de54cd1`, service `services.arcgis.com/8Pc9XBTAsYuxx9Ny/.../MinorStatisticalArea_gdb`
- Harris County: services `All_Pcts`, `Precinct_2025`, `Commissioner_Precincts` and the service list at `services.arcgis.com/su8ic9KbA7PYVxPS/ArcGIS/rest/services`; `https://cao.harriscountytx.gov/` and `/about/redistricting`
- NMCOG: `https://www.nmcog.org/27/Who-We-Are`, `https://www.nmcog.org/165/Our-Communities`
- Philadelphia: `https://www.arcgis.com/sharing/rest/content/items/0960ea0f38f44146bb562f2b212075aa`
- ArcGIS Online search (`https://www.arcgis.com/sharing/rest/search`) for SACOG, MTC, NCTCOG and county planning layers
- SACOG: `services6.arcgis.com/YBp5dUuxCMd8W1EI/arcgis/rest/services/Regional_Analysis_Districts_2007/FeatureServer/0`
- MTC: `services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/Travel_Analysis_Zones/FeatureServer/0`
- Secondary only: Wikipedia, *Community areas in Chicago*; *Metropolitan Area Planning Council*
