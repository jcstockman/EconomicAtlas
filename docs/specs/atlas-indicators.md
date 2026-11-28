# Atlas indicators

Status: draft, 2026-11-28. Built on atlas units (pieces release 1.3.1), QCEW 2024 and BEA 2024 by unit, and the districts and subregions. Scripts and outputs are in `regions/atlas/`.

The atlas publishes one indicator table per level:
- atlas units (3,315);
- districts (255);
- subregions (81);
- metro areas (58: the 57 CBSAs of 1.0M+ and the rest of Puerto Rico).

Every level is computed in the same way from additive components per unit. As a result, a district's figures are exactly its units' figures combined, and any other union of units can be computed the same way.

## Rules

1. **Components are additive counts per unit.** Each one is summed over the unit's members:
   - **Population:** the 2020 census and the Vintage 2025 estimates (`regions/units`), and land area from the 2020 Gazetteer tracts.
   - **ACS 2020–2024:** five-year estimates summed from 2020 tracts. Every unit is a set of whole tracts, so no allocation is needed.
   - **QCEW 2024:** establishments, jobs and wages; government jobs; the 11 private supersectors.
   - **BEA 2024:** GDP (current and real), personal income, transfer receipts, earnings by place of work and population.
2. **Indicators are components, or ratios of two summed components.**
   - A rate is the sum of its numerators over the sum of its denominators. It is never an average of unit rates.
   - **Medians** of household income (B19001, 16 brackets) and of home value (B25075, 26 brackets) are estimated from the summed brackets. The estimate interpolates linearly within the bracket that holds the median; the open top bracket returns its lower edge. This follows the Census Bureau's method for medians of combined areas.
3. **Missing values.** A level's value is missing when any member's component is missing. This happens in three cases:
   - a QCEW or BEA cell withheld at the county;
   - an ACS cell with no estimate;
   - BEA in Puerto Rico, which BEA does not cover.

   Nothing is imputed at this stage.
   - **Government jobs** are QCEW total minus private jobs, both of which BLS always publishes, so a withheld federal, state or local cell does not blank them.
   - **Supersector shares** are blank wherever a member county has that supersector withheld.
4. **BEA combined areas.** BEA reports Virginia's independent cities together with a neighbouring county, and Maui with Kalawao. These units have no BEA values of their own. A district or metro that holds every member of a combined area takes the combined area's figure.
5. **Population, 2025 and change.**
   - **Counties:** the 2025 figure is the Census Bureau's Vintage 2025 estimate. Change is measured from the April 2020 estimates base, as the Census Bureau does. The census count differs from that base by 0.5%+ in 49 counties; in Luce County, Michigan, using the count gave +18.7% instead of −1.2%.
   - **County pieces (the sub-county method):** before this, a piece got its county's estimate shared by 2020 counts, so every piece showed its county's growth rate.
     1. Each 2020 block (PL 94-171) is grown by its area's 2020–2025 growth in the Census Bureau's city and town estimates (`sub-est2025`): the part of a place within a county subdivision where those are estimated (18.5% of residents in split counties), otherwise the incorporated place or the balance of the county (81.5%).
     2. The county's 2025 estimate is shared among its pieces by the grown weights (largest remainder, so pieces add up exactly).
     3. A piece's 2020 base is the county's estimates base times the piece's share of the 2020 count.
     4. A piece's BEA population, the denominator of per capita income, is shared like its 2025 estimate.
   - **Example:** North Collin (McKinney & Frisco) grew 42.6% against 5.2% for South Collin (Plano & Allen), where both showed the county's 21.7% before.
   - **Geography files:** the atlas units and districts files still carry the county-share 2025 population for pieces, so their figures differ from these tables in 118 districts (−13.6% to +17.2%).
6. **Mean commute time** counts commuters (workers not working from home) only in tracts that have an aggregate travel time (B08013), to match its numerator. 1,016 tracts have no travel time; nearly all are empty or tiny.

## Indicators

The full list is in `indicator_catalogue.csv`, with each indicator's numerator, denominator, scale, source and year. There are 46:

- **Population:** 2020, 2025, change 2020–25, density.
- **Age:** shares under 18 and 65 and over.
- **Origin:** Hispanic; non-Hispanic White, Black and Asian; foreign-born.
- **Households and income:** households; median household income; poverty rate.
- **Education and work:** bachelor's degree or higher; labour force participation; unemployment rate; uninsured.
- **Housing:** owner-occupied share; median home value; renters paying 30%+ of income on rent; households without a vehicle.
- **Commuting:** working from home; mean commute time.
- **QCEW 2024:**
  - establishments, jobs, average weekly wage;
  - jobs per employed resident;
  - government share of jobs, and each private supersector's share.
- **BEA 2024:**
  - GDP (current and real), and GDP per QCEW job;
  - personal income, per capita personal income, and the share of income from transfers.

## Outputs

`build_indicators.py --cache DIR` writes:

- `indicator_catalogue.csv`: `indicator_id, label, unit, kind (count | rate | ratio | change | median), numerator, denominator, scale, source, year`.
- `components_units.csv`: every component for every unit, for re-aggregating to any union of units.
- `indicators_units.csv`, `indicators_districts.csv`, `indicators_subregions.csv`, `indicators_metros.csv`: one row per area. Each row has its ID, name and parent IDs (CBSA, subregion, district view, number of units, work inside), followed by the 46 indicators.

Rounding: dollars and density to whole numbers, minutes to one decimal, percentages and ratios to two decimals.

Also written:
- `indicators_counties.csv`: the 64 counties split into pieces, each the sum of its pieces, for comparison.
- `indicators_us.csv`: the 50 states, DC and Puerto Rico.
  - BEA figures leave out Puerto Rico, which BEA does not cover.
  - QCEW figures are BLS's national total, which also counts the US Virgin Islands (about 0.03% of jobs), because withheld county cells cannot be added up.
  - An ACS gap in a tiny unit (Kalawao County, 82 residents) is skipped.
- `indicators.json`: every level, the national row and the catalogue in theme order, in one compact file (1.0 MB) for the map.

## The atlas map

`regions/map.html` (published as "Economic Atlas Map") reads `atlas/indicators.json`:
- **Shading:** in every view, any indicator can shade the map. Colours are national classes: seven classes, each holding a seventh of a national reference set, so one value gets one colour in every view and area.
  - Rates, ratios, medians and changes use all 3,315 atlas units.
  - Size-dependent counts use every area of the kind drawn: all 255 districts, or all 3,315 units.
  - The geography measures (work inside, residents, jobs in the metro and county views) use all districts or all 157 pieces. The table then shows that indicator in place of its units or population-mix column.
- **Profiles:** clicking a district, a subregion row, the metro total, a piece or the county total opens a profile of all 46 indicators by theme. Each value is shown next to the metro or county (where there is one) and the US, with the area's rank among all its peers in the atlas: 255 districts, 81 subregions, 58 metro areas, 157 county pieces or 64 split counties.
- **Shading from a profile:** clicking an indicator in a profile shades the map by it.
- **United States view:** all 3,315 atlas units, from two files built by `build_us_shapes.py`: `atlas/us_units.geojson` (1.9 MB) and `atlas/us_states.geojson` (state borders). They are plain GeoJSON, so the page needs no library beyond d3.
  - **Shapes:** the 8.6 MB unit shapes, simplified topology-aware with mapshaper (keep 8%, coordinates to 0.001°, so neighbours share borders). Alaska and Hawaii are inset by Albers USA, and Puerto Rico in its own inset. A single state gets its own fit (Alaska a conic projection).
  - **Table:** the ten highest and ten lowest units in view (every unit for a state of 20 or fewer), with the US rank.
  - **Profiles:** a unit's profile compares it with its metro area (if any) and the US, ranks it among all 3,315 units, and links to the unit's metro and county views. With nothing selected, the profile shows the US.
  - **Links:** `#uUS` or `#u<state code>` open the view.

## Checks

`check_indicators.py --cache DIR` (writes `check_indicators.csv`) tests three things. All pass on the 2026-11-28 build:

- **Additivity.** District, subregion and metro population, households and jobs equal the sums of their units.
- **ACS against the county estimates.** For the 3,158 whole-county units, every ACS rate summed from tracts equals the ACS's own county estimate (0.00 points at the median and the 95th percentile). The tract estimates add up exactly to the county.
- **Estimated medians against the published ones.**
  - Household income: 0.65% at the median, 3.2% at the 95th percentile, against B19013.
  - Home value: 0.01% and 0.04%, against B25077.
  - The income gap comes from the Census Bureau's finer internal brackets.

## Limits and next steps

- **No margins of error.** ACS estimates for small pieces and districts are less precise than for counties; summing the published MOEs (root sum of squares) would give one.
- **Puerto Rico** has no BEA indicators.
- **Withheld QCEW supersectors** leave some shares blank, for example Information in 18 metros. A residual allocation (private total minus the published supersectors, shared by the withheld sectors' keys) could fill them.
- **Years differ by source:** ACS 2020–2024 against QCEW and BEA 2024. Time series are a later step.
