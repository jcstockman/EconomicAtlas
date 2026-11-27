# Atlas units

Status: draft, 2026-11-27. Built from county pieces release 1.3 (`docs/specs/county-pieces.md`). Scripts and outputs in `regions/units/`.

Every 2020 census tract in the 50 states and DC belongs to exactly one **atlas unit**: a county piece in the 64 counties with 0.92M+ residents, a whole county everywhere else. Atlas units are the geography the atlas reports on and the base for subregions and districts.

## Rules

1. **Counties are the Vintage 2025 county-equivalents.** 3,144 counties and county-equivalents in the 50 states and DC, as in the Census Bureau's Vintage 2025 estimates (`co-est2025-alldata.csv`). Puerto Rico is not included.
2. **Connecticut uses its nine planning regions** (county-equivalents since 2022), not its eight former counties, so that unit figures line up with current county data. A 2020 tract goes to the planning region holding its internal point; tracts nest in towns and towns in planning regions. Planning-region shapes: TIGERweb ACS 2024 counties (a fixed vintage). Each region's 2020 census count is within 0.15% of the Census Bureau's 2020 estimates base for it.
3. **Pieces come from a frozen pieces release.** The tract crosswalk and registry are read from `regions/pieces/releases/<version>/` (default: the latest), so the units table changes only when a new pieces release is cut. The release used is recorded on every row.
4. **Unit IDs.** A piece keeps its stable piece ID (`06037-01`, county FIPS plus a two-digit number); the four whole-county pieces (Contra Costa, Pima, Fresno, Gwinnett) are pieces too (`06013-01`). A county unit's ID is its 5-digit county FIPS code (`01001`). The hyphen tells them apart.
5. **Population.** `pop2020` is the 2020 census count (sum of tracts; it can differ from the estimates base, e.g. Luce County MI by 20% after a count question resolution). `pop2025_est` is the county's Vintage 2025 estimate; a piece takes its 2020 share of its county, rounded per piece exactly as in the pieces release, so a split county's pieces may sum to within one resident per piece of its estimate.

## Outputs

`build_units.py --cache DIR [--pieces VERSION]` writes:

- `crosswalk_tract_unit.csv`: `tract_geoid, county_fips_2020, county_fips, unit_id, unit_type`. `county_fips_2020` is the tract's county in the 2020 census; `county_fips` the Vintage 2025 county-equivalent (they differ only in Connecticut).
- `atlas_units.csv`: `unit_id, unit_type (piece | county), county_fips, county, state_fips, state, unit_name, pop2020, pop2025_est, tracts, pieces_release`. Piece names are the region names from the pieces registry; county units carry the county name.
- `atlas_units.geojson` (8.2 MB): pieces from `regions/pieces/pieces.geojson`, other counties from the 2024 cartographic boundary file (`cb_2024_us_county_500k`), simplified about 200 m.

Inputs go through the pieces loaders, so they are logged and pinned in `regions/pieces/inputs/manifest.csv` (454 inputs after this build).

## Build 2026-11-27 (pieces release 1.3)

- 84,414 tracts, all in exactly one unit. 3,237 units: 157 pieces (64 counties) and 3,080 whole counties (release 1.2: 3,234 units, 147 pieces in 57 counties). Piece counties are read from the pieces crosswalk's `county_fips`, so the Capitol Planning Region (2020 tracts in Hartford and Tolland counties) is recognised; release 1.0.1 had 3,228 units (134 pieces).
- 2020: 331,449,281 residents, the census total for the 50 states and DC. 2025: 341,784,858, one more than the Vintage 2025 total (per-piece rounding).
- Every piece matches the pieces release (2020 and 2025 residents).
- Shapes: each split county's pieces cover 98.6–100% of its 2024 county shape (Los Angeles lowest: uninhabited islands are left off) and extend at most 0.2% outside it (simplification and shoreline differences).

## Next steps

1. **Allocation keys** for county-only data (BEA GDP and income, QCEW): decide how county figures are shared among a split county's pieces (for example LODES jobs by sector for employment and wages, ACS or IRS figures for income), and document each key per dataset. County units need none.
2. **Subregions and the 70 districts:** rebuild them from atlas units and re-check the district size rule (0.35–1.5M). That code is not in this repository.
3. **Time series:** map 2010 tracts to atlas units with the Census 2010–2020 tract relationship file, for series before 2020.
4. **Checks script** for the units table (now done inside the build: coverage, county match, piece match), and a units release that pins the pieces release and the county file.
5. **Puerto Rico** (78 municipios): add if the atlas covers it.

## 2010 tracts (2026-11-27)

`regions/units/build_tract2010.py --cache DIR` maps every 2010 census tract (73,057 in the 50 states and DC) to atlas units, so that series published on 2010 geography (ACS before 2020-2024 five-year tables on 2020 tracts, LODES 7, the 2010 census, older local data) can be carried to the atlas.

- **Method:** at block level. Each 2010 block's residents and housing units (2010 census, PL 94-171) and jobs (LODES 7 WAC, all jobs, which is on 2010 blocks) are shared among the 2020 blocks it overlaps in proportion to the land they share (Census 2010-2020 block relationship files; shares taken against the overlaps' own total, water area where a block has no land). A 2020 block belongs to its 2020 tract and so to one atlas unit. County changes since 2010 come through the blocks: Connecticut's planning regions, Bedford city VA (into Bedford County), Shannon/Oglala Lakota SD, Wade Hampton/Kusilvak AK and Valdez-Cordova AK.
- **Slivers:** small boundary realignments between 2010 and 2020 leave fragments of a tract in a neighbouring unit (a few hundredths of a person). A part with under 0.1% of a tract's residents, housing units and jobs and under 1% of its land is folded into the tract's largest unit (4,339 such parts), so totals stay exact.
- **Output:** `crosswalk_tract2010_unit.csv` (tract2010_geoid, county2010_fips, unit_id, pop2010, hu2010, jobs_lodes7, aland_m2, and each as a share of the 2010 tract: pop_share, hu_share, jobs_share, aland_share; a tract with no residents takes the next available basis, a water-only tract splits equally) and `tract2010_summary.csv` (per state: tracts, tracts in more than one unit, residents, housing units, jobs, LODES 7 year).
- **Result:** 74,092 rows. 1,023 tracts (1.5% of 2010 residents) fall in more than one unit; the rest map whole. Residents (308,745,538) and housing units (131,704,730) match the 2010 census; the rows sum to within 9 residents of it (rounding). Every tract's shares sum to 1. LODES 7 year: 2019, except Alaska 2016 and Arkansas and Mississippi 2018 (the latest each publishes).
- **Use:** counts on 2010 tracts are carried with the share that matches what they count (residents or households with pop_share or hu_share, jobs with jobs_share); a 2010 block file (LODES 7) can instead go block by block through the same relationship files.
