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
5. **Mean commute time** counts commuters (workers not working from home) only in tracts that have an aggregate travel time (B08013), to match its numerator. 1,016 tracts have no travel time; nearly all are empty or tiny.

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
