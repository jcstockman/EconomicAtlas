# Subregions and districts

Status: built, 2026-11-27 (`regions/metros/`, from atlas units on pieces release 1.3; first built on 1.0.1). The four decisions at the end were taken as proposed; results are under **Built**.

Two levels sit between atlas units (`docs/specs/atlas-units.md`) and CBSAs in the 57 largest metros: **subregions** in the 26 CBSAs of 2.5M+, and **districts** (an optional finer view) in those subregions and in mid-size CBSAs. Both are unions of atlas units, so every figure the atlas holds for units (QCEW, BEA, ACS, LODES) adds up to them with no new allocation.

The plan (*Metro Economic Atlas: Index Framework and Integration Plan*, sub-metropolitan units, decided 2026-11-21) set the rules below. They were written when pieces covered counties of 1.5M+ at 0.4–1.5M; pieces now cover counties of 1.0M+ at about 0.8M (0.45–1.1M), which simplifies districts. Overrides of the plan are marked **Change** with the reason.

## Ladder

tract → county / county piece (atlas unit) → district (optional view) → subregion → CBSA / OMB metropolitan division (overlay) → CSA → flow region / megaregion.

Outside the covered metros both new levels fall through to the CBSA (a county outside any CBSA falls through to itself). Delineations: OMB July 2023 (Census `list1_2023.xlsx`), which already uses Connecticut's planning regions; populations: Vintage 2025.

## Facts (Vintage 2025, OMB 2023)

- 26 CBSAs of 2.5M+ hold 145.8M residents; 13 have OMB metropolitan divisions. 30 CBSAs of 1.0–2.5M hold 49.2M; 9 of them are 2.0–2.5M. These match the plan's counts.
- Five divisions exceed the 3.5M subregion cap: New York–Jersey City–White Plains 12.3M, Los Angeles–Long Beach–Glendale 9.69M, Chicago–Naperville–Schaumburg 7.21M, Dallas–Plano–Irving 5.74M, Atlanta–Sandy Springs–Roswell 5.04M. Four counties exceed it on their own: Los Angeles 9.69M, Cook 5.19M, Harris 5.05M, Maricopa 4.69M; they can only be split with pieces.
- Two divisions fall under the 0.6M floor: San Rafael 0.25M, Rockingham County–Strafford County NH 0.46M.
- 13 of the 26 have no divisions, among them Houston 7.90M, Phoenix 5.23M and Riverside–San Bernardino 4.77M.
- The 26 CBSAs contain 113 pieces and 67 other counties of 0.35M+ (180 units that can stand as districts), plus 15.5M residents in smaller counties.

## Subregions (plan rules kept)

1. **Where:** every CBSA of 2.5M+ (26). Nested in the CBSA. The nine CBSAs of 2.0–2.5M get districts, not subregions.
2. **Size:** 0.6–3.5M, aiming at 1–2.5M.
3. **Built from** whole counties or county pieces (atlas units), starting from OMB divisions:
   - a division of 0.6–3.5M is a subregion;
   - a division over 3.5M is split into subregions by grouping its units on LODES commuting (the pieces method: modularity with compactness, contiguity, job centres whole);
   - a division under 0.6M joins the neighbouring division its residents commute to most (San Rafael joins San Francisco–San Mateo–Redwood City; Rockingham–Strafford joins Cambridge–Newton–Framingham);
   - a CBSA without divisions is grouped the same way from its units.
4. **Counties named in no division** join the non-core subregion their residents commute to most. (In the 2023 delineation every county of a divided CBSA is in a division, so the rule has no case to apply to.)
5. **Merges kept from the plan:** Outer Virginia into Northern Virginia & Jefferson WV; Adams & Broomfield into Denver, Jefferson, Adams & Broomfield. Re-checked on Vintage 2025 figures before freezing. **Outcome:** the Arlington–Alexandria–Reston division (3.25M, all of Northern and outer Virginia with Jefferson WV) is within the limits and stays one subregion, which is the plan's merge. Adams & Broomfield form one district, and the subregion is the plan's Denver, Jefferson, Adams & Broomfield (1.99M, with Park, Clear Creek and Gilpin), beside South Metro Denver (Arapahoe, Douglas, Elbert; 1.10M). The first build, with the pieces' compactness weight, had put Jefferson with Douglas instead (see How subregions are made).
6. **Change: subregions are unions of districts.** The plan's ladder puts districts under subregions; the build makes it exact by grouping districts (not raw units) into subregions, so no district crosses a subregion line.

## Districts

1. **Where:** in subregions over 1.5M, and in CBSAs of 1.0–2.5M that yield two or more districts. Elsewhere the district level falls through to the subregion or CBSA.
2. **Size:** 0.35–1.5M.
3. **Change: a district is an atlas unit of 0.35M+, or a group of smaller counties.** Every piece (0.45–1.1M) and every county of 0.35M+ is a district on its own; counties under 0.35M join, by LODES commuting, an adjacent district in the same subregion (or CBSA), or form their own district once a contiguous group reaches 0.35M. The plan seeded districts from planned pieces (max(2, round(pop ÷ 1.2M)) per county of 1.5M+); the built pieces replace that seeding, and splitting or merging pieces again would make districts disagree with the units every figure is built on.
4. **Change: mid-size CBSAs by rule, not by list.** The plan kept 14 mid-size CBSAs whole. Under the current pieces two of them now split by rule: Raleigh (Wake County is two pieces) and Salt Lake City (Salt Lake County is two pieces). The rule "a CBSA of 1.0–2.5M gets districts when it yields two or more" is applied as written, and the list is whatever the rule gives.
5. **Change: expected count.** The plan counted 181 districts (143 in the large CBSAs, 70 depending on tract pieces). With pieces at about 0.8M, districts in the large CBSAs start from 180 units of 0.35M+ before small counties are grouped, so roughly 190–200 there; the exact count comes from the build.

## Build and outputs (same machinery as pieces)

- `regions/metros/build_metros.py`: districts, then subregions, from atlas units, LODES county-to-county and piece-to-piece commuting, OMB 2023 delineations and Vintage 2025 populations; contiguity on land; compactness term; job centres stay whole (they already sit inside pieces).
- Registry with stable IDs and anchor-tied names, as for pieces: subregion `<CBSA code>-S<nn>`, district `<CBSA code>-D<nn>`. Names: established names where they exist (OMB division titles, county names), otherwise direction plus anchor places.
- Outputs: `crosswalk_unit_metro.csv` (atlas unit → district → subregion → CBSA / division / CSA), summaries and GeoJSON for both levels, and a checks script (nesting, size limits, contiguity, every unit in a covered CBSA assigned exactly once). Figures for districts and subregions are sums of unit figures, never re-allocated.
- Released with the pieces' versioning: the metros build pins the pieces release it reads.

## Decisions (taken as proposed, 2026-11-27)

1. **District = piece** (proposed) or merge pieces back toward the plan's ~1.2M districts. Proposed: keep pieces as districts; merging would discard the finer geography the pieces now give and leave two competing ~1M layers.
2. **Mid-size CBSAs by rule** (proposed: Raleigh and Salt Lake City then get districts) or keep the plan's list of 14 whole CBSAs as written.
3. **Splitting the five oversized divisions and the 13 undivided CBSAs** by commuting (proposed) or by hand with local planning regions (for example, LA by SPA groups, Houston by H-GAC subregions) where a source exists and fits the sizes.
4. **Small divisions:** San Rafael (0.25M) and Rockingham–Strafford (0.46M) join their neighbour by commuting (proposed), or stay as named exceptions below the floor.

## Built

`python3 regions/metros/build_metros.py --cache DIR`, then `check_metros.py --cache DIR` (coverage, nesting, sizes, view rule, contiguity, totals, registry, files, names: all pass). The build is deterministic (fixed hash seed) and a rebuild against the registry reproduces every output byte for byte.

**Inputs.** Atlas units (`regions/units`); OMB July 2023 delineation (`list1_2023.xlsx`); LODES 8 OD main and aux, all jobs (JT00), 2024 for 39 states and 2021 for Michigan (latest published), residents to jobs, tract to unit. Adjacency: unit shapes buffered by 0.01° (about 1 km; shapes are simplified and some neighbours face each other across rivers), within the CBSA; a part cut off from the rest of its CBSA links to its nearest unit. Inputs are logged and pinned in `regions/pieces/inputs/manifest.csv` (629 inputs).

**How districts are made.** Within each region (an OMB division after the two small ones joined their neighbours, or the whole CBSA where it has no divisions or is under 2.5M), every unit of 0.35M+ starts as a district. First, a unit under 0.35M that lies inside the outline of one larger neighbour (90%+ of its area, the neighbour's holes filled) joins that neighbour: only Manassas and Manassas Park, both inside Prince William County, meet this test, and they join the Prince William district rather than the Fairfax district that commuting had given them. Then groups under 0.35M, smallest first, join the adjacent group their residents commute to most, never past 1.5M. Where that greedy order still leaves a district outside 0.35–1.5M, the region is grouped by the pieces' engine (modularity with the compactness term, contiguous, no two 0.35M+ units together), trying each feasible number of districts and keeping the best score. On pieces release 1.0.1 only Indianapolis needed this (the greedy joins piled eight counties onto a whole Marion County, 1.80M); since release 1.1 splits Marion, no region needs it: Indianapolis has North & East Indianapolis & Suburbs (0.88M), Downtown & South Indianapolis, Hendricks & Johnson (0.93M) and Hamilton & Tipton (0.40M).

**How subregions are made.** A division of 0.6–3.5M is one subregion. A larger division, and every CBSA of 2.5M+ without divisions (at least two subregions), is grouped from its districts by the same engine, first within the aim of 1.0–2.5M, then 0.6–2.5M, then 0.6–3.5M, trying every number of subregions the band allows and keeping the best-scoring valid grouping. Every split region found a grouping within the aim, except St. Louis under its pin (below). The compactness weight is 0.25 here, not the pieces' 1.0: between large counties the shared boundary length is mostly empty land, and at full weight it outweighed commuting. Lowering it changed exactly two metros against the first build: Pinal joins the East Valley (41% of its workers commute there; 2.26M, beside West Valley & Central Phoenix, 1.85M), and Denver gets the plan's split. Weight 0.5 changed nothing. (A first build that fixed the number at pop ÷ 1.75M and used the 0.6–3.5M limits directly gave lopsided results, such as Phoenix at 3.17 / 1.12 / 0.93M, and was dropped.)

**Rule variants tested and not adopted** (2026-11-27, against all 56 CBSAs): dropping the 1.0M floor of the aim (almost every split became a large core plus a small leftover: Denver 2.48 / 0.61M, Austin, Portland, San Diego, Orlando); after the greedy joins, moving each small county to the adjacent district most of its out-commuters reach (about 20 moves, mixed: Lincoln and Warren MO jumped to the St. Louis County district, leaving St. Charles alone, and Suffolk VA could not move without breaking contiguity); joining the strongest commuting tie first instead of the smallest county first (pulled districts into their cores: Norfolk, Virginia Beach, Chesapeake and Portsmouth became one district, Kansas City's Northland disappeared, Atlanta needed the fallback). `build_metros.py --set NAME=VALUE --out DIR` rebuilds with a changed rule constant into another folder, from cached flows in seconds.

**Local adjustments** (`metro_pins.csv`: level, unit_id, with_unit, name, reason; checked by the same size, contiguity and nesting checks). A district pin puts its two units in one group before the small counties are joined (so the joins work around it); a subregion pin groups the two units' districts as one node before the subregions are made:
- Hampton Roads: Suffolk, Isle of Wight, Surry and Gates join the Chesapeake–Portsmouth district (Chesapeake, Portsmouth & Western Tidewater, 0.56M), leaving the Virginia Peninsula (0.55M). Suffolk sends 44% of its workers to the Southside cities and 13% to the Peninsula; the smallest-first joins had carried it to the Peninsula through Isle of Wight, whose workers split between the two.
- St. Louis (since pieces release 1.1, which splits St. Louis County):
  - Districts: St. Louis City & North County (0.79M; 32% of the city's workers go to the North & Central piece, 16% to West & South County, 2% to Metro East); Metro East (Madison, St. Clair, Monroe and four smaller Illinois counties, 0.67M); West & South County, Jefferson & Franklin (0.82M); St. Charles, Lincoln & Warren (0.54M). Pins: the city starts with the North & Central piece, and Madison and Monroe with St. Clair. Without them the Metro East counties, which commute into downtown, draw the city and the piece into one 1.45M district.
  - Subregions: St. Louis City, North County & Metro East (1.45M) and West County & Missouri Suburbs (1.36M); pin: St. Charles with the West & South piece. By commuting alone the grouping pairs the two St. Louis County pieces and the city (1.61M) and leaves St. Charles with Metro East (1.20M), the wrap-around around the core; it keeps 70% of commuting inside subregions against 63% here.
  - On release 1.0.1 (St. Louis County whole) the pins were Monroe to Metro East and St. Charles with St. Louis County.
- Kept on review: Riverside–San Bernardino's Deserts & Mountains (High Desert with the Coachella Valley; the Coachella Valley sends at most 4% of its workers to any other district, so no grouping has a commuting basis); the Minneapolis west-suburbs district reaching round Anoka (Sherburne sends 34% of its workers into it against 11% to Anoka's district, Mille Lacs 25% against 10%); Atlanta city split between districts (it spans Fulton and DeKalb counties).

**Counts (Vintage 2025).**

| | Plan | Built |
|---|---|---|
| CBSAs covered | 56 (26 of 2.5M+) | 56 (26 of 2.5M+), 539 atlas units |
| Subregions | 94 | 81, 0.72–3.25M; 65 within 1.0–2.5M, 9 whole divisions above it, 7 below 1.0M |
| Districts in the 26 large CBSAs | 143 | 192, of which 145 in the district view |
| Mid-size CBSAs with districts | 16 (38 districts) | 20 (48 districts): the plan's 16 plus Raleigh, Salt Lake City, Hartford (pieces 1.1) and Buffalo (pieces 1.3) |
| Mid-size CBSAs kept whole | 14 | 10: Birmingham, Fresno, Grand Rapids, Greenville, Louisville, Memphis, Omaha, Rochester, Tucson, Tulsa |
| Districts in the district view | 181 | 193, 0.36–1.39M |

Subregions are fewer than planned because subregions now group whole districts (0.35–1.5M) rather than raw units, and because whole divisions of 2.5–3.5M (Nassau–Suffolk 2.95M, Cambridge–Newton–Framingham 2.96M, Arlington–Alexandria–Reston 3.25M, Anaheim–Santa Ana–Irvine 3.15M, Oakland–Fremont–Berkeley 2.81M, Miami 2.80M, Fort Worth–Arlington–Grapevine 2.74M, Warren–Troy–Farmington Hills 2.62M, Lakewood–New Brunswick 2.56M) stay whole, as the plan's rule says.

**IDs and names.** `<CBSA>-S<nn>` and `<CBSA>-D<nn>`, numbered by size at first build and tied in `metro_registry.csv` to an anchor unit (the group's largest), kept across rebuilds as for pieces; when an anchor county is later split into pieces, its largest piece becomes the anchor (so Fort Bend's subregion and the larger halves of Bergen, Prince George's, Marion and the Capitol Region kept their IDs in 1.1). Names are curated in `metro_names.csv` (id, level, name, confidence, note), keyed by ID so they survive rebuilds; the build writes the curated name to `name`, keeps the automatic one in `auto_name` and marks `name_source`, and the checks fail if an area lacks a curated name or two areas in a CBSA share one. The first set came from a review of all 323 names, 2026-11-27 (all subregions and 139 districts renamed; 261 at high confidence, 48 medium, 2 low). Rules:
- single-county district: "X County", with the state only where needed ("Lake County, IL"); places known by another name keep it (Denver, Baltimore City, Staten Island, District of Columbia; "Boston, Chelsea & Revere" for Suffolk County MA);
- several counties: "A, B & C", or an established regional name where it fits the composition (East Bay, East Valley, Northland, Long Island);
- a whole OMB division: its everyday name in place of the OMB title (Long Island, Central Jersey, East Bay, Orange County, Northern Virginia, Northwest Indiana); the OMB title is in the note;
- a mid-size CBSA that is one district: "Greater X" (Greater Louisville), or a common name (Buffalo Niagara, Rhode Island, Pima County);
- county pieces keep their reviewed names, except Dallas–Fort Worth D10, renamed "South Denton: Carrollton & The Colony" because Frisco names D09;
- a subregion that is a single district shares that district's name.
A second review (2026-11-27) of the 50 medium- and low-confidence names renamed 20 (for example Atlanta's "DeKalb, Clayton & I-20 East" to "DeKalb, Clayton, Rockdale & Newton", Minneapolis's "North & West Suburbs & Exurbs" to "Suburban Hennepin, Scott, Wright & Carver", Washington's "Loudoun & Lower Shenandoah Valley" to "Loudoun, Jefferson & Warren") and rated 46 of the 50 high. Four stay medium, for a local to confirm: Charlotte S01 "North & West Charlotte, Gaston & Cabarrus" (a Lake Norman name is possible), San Antonio D02 "West & South Bexar, Medina & Wilson", Indianapolis D03 "West & South Indianapolis, Hendricks & Johnson" (whether "Downtown" belongs in it) and New York D19 "White Plains, Northern Westchester & Putnam" (Port Chester and Rye). A third review (2026-11-27, against local usage) settled them, and all 331 names are now high confidence:
- **Charlotte S01 and San Antonio D02 are kept.** Locals use "Lake Norman" only for the lakeside towns, which leaves out Gaston, Cabarrus and Rowan. Alamo Ranch and the Far West Side are unincorporated Bexar County, and the "Side" names are for areas inside the city.
- **Indianapolis D03 becomes "Downtown, West & South Indianapolis, Hendricks & Johnson"**, using its piece's full name, so the district holding Downtown says so.
- **New York D19 becomes "Northern & Central Westchester & Putnam"**, its piece's name. It covers White Plains, the Sound Shore towns and the northern towns, and pairs with "Southern Westchester: Yonkers & New Rochelle".

**Files** (`regions/metros/`): `crosswalk_unit_metro.csv` (unit_id, unit_type, county_fips, cbsa, division, csa, subregion_id, district_id, district_view, pop2025, pieces_release); `districts.csv` and `subregions.csv` (ID, CBSA, name, pop2025, unit and district counts, district_view); `districts.geojson`, `subregions.geojson` (dissolved unit shapes); `metro_registry.csv`.

**Pieces release 1.1 (2026-11-27).** Rebuilt on the new atlas units (536 in the covered CBSAs): new districts South Bergen & Meadowlands / North & West Bergen (New York), Southern Prince George's & Charles / Northern Prince George's (Washington), Hartford, New Britain & Middletown / East of the River & North Capitol (Hartford, now with a district view), Indianapolis as above, and St. Louis as above; St. Louis's subregions and two districts took new IDs (41180-D02 and -S02 retired). Every other district and subregion is unchanged. 247 districts, 188 in the district view; 81 subregions; all checks pass.

**Open.** The subregion and district IDs were tidied once before any release (St. Louis S01/S02 and Denver S02 then named the adjusted areas). The metros build is not yet part of a numbered release.

**Map.** `regions/map.html`, Metro areas view: pick one of the 57 CBSAs; districts are filled by subregion (categorical slots in ID order) with subregion boundaries drawn heavier, numbered as in the table, with optional county and piece lines, zoom, and shading by work inside or residents. Districts outside the district view are greyed in the table. `districts.csv` and `subregions.csv` carry `work_inside` (employed residents whose LODES job is in the same area, cross-state commuting included) and districts carry `members` (unit names, largest first); `metro_units.geojson` holds the covered units' shapes for the map.

**Pieces release 1.2 (2026-11-27).** Districts follow the reshaped pieces in King, Tarrant, Orange CA, Harris, San Diego and Miami-Dade; their composition by unit changes only in San Diego (Mid-City, Kearny Mesa & East County replaces La Jolla, Poway & Encinitas as a district, 41740-D05; subregions Central, South Bay & East County and North County & North San Diego regroup), Dallas-Fort Worth (Wise joins Northeast Tarrant, Alliance & Wise) and Houston (subregions Inner Houston & Fort Bend and West Houston: Cypress, Memorial & Katy). District names that repeat a piece's name follow the piece. 247 districts, 188 in the district view; 81 subregions; all checks pass.

**Pieces release 1.3 (2026-11-27).** New districts from the new splits: St. Petersburg & South Pinellas and Clearwater & North Pinellas (Tampa); Buffalo & Southtowns and Amherst, Cheektowaga, Tonawanda & Niagara (Buffalo, now with a district view); Milwaukee North Side, Ozaukee & Washington and Milwaukee South Side & South Suburbs. Cook's districts follow its reshaped pieces (names updated; subregions South & Southwest Suburbs, Will & Grundy and Downtown, North Side & North Shore). Pierce and DuPage are now whole-county pieces, their districts unchanged. District names that repeat a piece's name follow the seven review renames. 250 districts, 193 in the district view; 81 subregions; all checks pass.

**Puerto Rico and San Juan (2026-11-27).** San Juan-Bayamón-Caguas (2.02M) is the 57th CBSA covered.
- **Commuting:** LODES does not cover Puerto Rico, so its commuting comes from the ACS 2016–2020 county-to-county flows (table 1, workers 16+; 670,799 workers between its 40 municipios). These are enough because every Puerto Rico unit is a whole municipio.
- **Districts:** the rules are unchanged, and no municipio reaches 0.35M, so all are joined by commuting into three districts, shown in the district view:
  - **D01** "San Juan, Carolina & the Northeast" (939k, 89% work inside)
  - **D02** "Bayamón, North Coast & Central Mountains" (620k, 61%)
  - **D03** "Caguas, Cayey & Humacao" (464k, 72%)
- **No subregions:** the metro is under 2.5M.
- **Names:** a local review kept all three, now high confidence. "The Northeast" follows the National Weather Service's Northeast zone and the Corredor Ecológico del Noreste; "North Coast" and "Central Mountains" are the tourism regions' English names; "Valle del Turabo" would cover only part of D03.
- **Other metros:** unchanged. All checks pass (57 CBSAs, 253 districts, 196 in the view, 81 subregions). Work-inside shares for San Juan use the ACS flows (2016–2020), not LODES 2024.

**The rest of Puerto Rico (2026-11-27).** Puerto Rico's other metros are all far below the 1.0M cover (Ponce 0.26M, Aguadilla 0.25M, Mayagüez 0.21M, Arecibo 0.18M, Guayama 0.06M), so the rest of the island, the 38 municipios outside San Juan-Bayamón-Caguas (1.16M), is one region of its own. It has the code `72999`, which is not an OMB area, and is districted like a mid-size CBSA, by ACS 2016–2020 commuting.
- **Districts:**
  - **D01** "Mayagüez, Aguadilla & Arecibo" (718k, 22 municipios, 90% work inside): the west, the north around Arecibo, and the inland towns.
  - **D02** "Ponce, Guayama, Vieques & Culebra" (443k, 16, 90%): the south coast from Guánica to Arroyo, with Vieques and Culebra.
- **Islands:** Vieques and Culebra are pinned to Patillas, the nearest unit of the region; their own neighbours, Ceiba and Fajardo, are in the San Juan metro.
- **Adjacency fix:** an island is now linked to the nearest unit already connected to the largest part. Before, the two islands, being nearer each other than the mainland, were linked only to each other. This changed nothing elsewhere.
- **Names:** a local review kept D01, because locals and the Health Department divide the area around Mayagüez, Aguadilla and Arecibo, and "Porta del Sol" would leave out a third of it. It renamed D02 from "Ponce, Guayama & the Island Municipalities": "Vieques & Culebra" is the fixed local pair, while "island municipalities" is an official description readers would not recognise. Both are now high confidence.
- **Totals:** all checks pass. 58 areas (57 CBSAs and this region), 255 districts (198 in the view), 81 subregions. With San Juan, every Puerto Rico municipio is in a district.
