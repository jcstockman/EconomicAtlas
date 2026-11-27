# Allocation keys for county-only data (BEA, QCEW)

Status: built, 2026-11-27. All five recommendations adopted (see Decisions); keys in `regions/keys/` (see Build).

BEA's regional accounts and BLS's QCEW publish counties, not pieces. In the 55 counties split into several pieces (31.1% of US residents in 2025; 52 counties and 30.3% in release 1.2; 46 counties and 28.6% before pieces release 1.1; `docs/specs/atlas-units.md`), each county figure must be shared among its pieces by a **key**: a sub-county measure that tracks the figure. Whole-county units (3,094 counties and the four whole-county pieces) need no key; they take the published number.

## Principles

1. **Place of work vs. place of residence.** Output, jobs, wages and establishments are counted where the work is; personal income and transfers where people live. A key must be measured on the same basis. The gap is large inside counties (LODES 2024, release 1.0 pieces):

   | Piece | Residents | Jobs | Finance jobs | Jobs over $3,333/month |
   |---|---|---|---|---|
   | Midtown & Lower Manhattan (36061-02) | 40.3% | 82.8% | 98.5% | 84.3% |
   | Uptown Manhattan (36061-01) | 59.7% | 17.2% | 1.5% | 15.7% |
   | Inner Houston (48201-04) | 14.9% | 27.0% | 28.7% | 29.7% |
   | Downtown, Hollywood & Wilshire (06037-06) | 8.3% | 15.1% | 24.2% | 18.0% |
   | Crenshaw & South Central (06037-10) | 5.4% | 2.5% | 0.7% | 2.4% |

   A residence-based key would put most of Manhattan's GDP uptown.
2. **Allocate by industry, then add up.** A county figure published by sector is shared sector by sector with a sector key, then summed. A single all-industry key would give a piece of warehouses the county's average mix.
3. **Pieces sum to the county exactly.** `X_piece,s = X_county,s × K_piece,s / Σ K_county,s`. The published county number is never changed; only its split is modeled.
4. **Suppressed cells.** Where a county-by-sector cell is withheld (BEA "(D)", QCEW nondisclosure), the county residual (total minus disclosed sectors) is shared by the combined keys of the withheld sectors. No sector value is imputed or published for a piece where the county value is withheld.
5. **Label modeled values.** Every piece value from a key carries `method = allocated` and its key; county units carry `method = published`.
6. **Keys follow the data year where they exist.** LODES runs 2002–2024 (Michigan to 2021): use the same year, or the nearest. ACS 5-year: the period ending in the data year, or the latest.

## Proposed keys

### Place of work

| Data | Measure | Key (tract level, summed to pieces) | Source |
|---|---|---|---|
| QCEW | Employment by NAICS sector | Jobs by sector at the workplace | LODES WAC, CNS01–CNS20 |
| QCEW | Employment by ownership (private, federal, state, local) | Private: WAC JT02 by sector. Federal (civilian) and state: ACS-calibrated (see Government keys). Local: JT00 − JT02 − JT04 | LODES WAC by job type; ACS B08528, B23025 (places, counties) |
| QCEW | Total wages, average weekly wage by sector | Sector jobs × the piece's wage index (decision 1) | LODES WAC CNS, CE01–CE03 |
| QCEW | Establishments by sector | Establishments by sector in ZIP codes, ZCTA-to-tract by 2020 population | Census ZIP Code Business Patterns; 2020 ZCTA–tract relationship file |
| BEA CAEMP25N | Total employment by industry (wage and salary plus proprietors) | Wage and salary: as QCEW. Proprietors: self-employed workers at residence (no workplace source) | LODES WAC; ACS B24080 |
| BEA CAINC5N / CAINC6N | Earnings and compensation by industry | As QCEW total wages, by sector; proprietors' income by self-employed workers | as above |
| BEA CAGDP2 / CAGDP9 | GDP by industry (current and real) | As earnings by sector (decision 1); real estate split (decision 2); government by public jobs; military by armed forces at residence | LODES WAC; ACS B23025 |

### Place of residence

BEA's personal income (CAINC1, CAINC4, CAINC30, CAINC35) is measured where people live. It is allocated by component, each with the matching ACS household aggregate:

| BEA component | Key | ACS 5-year table (tract) |
|---|---|---|
| Net earnings by place of residence (earnings − social insurance contributions + residence adjustment) | Aggregate wage or salary income + self-employment income | B19062, B19063 |
| Dividends, interest and rent | Aggregate interest, dividends or net rental income | B19064 |
| Social Security and Medicare benefits | Aggregate Social Security income (Medicare: population 65+) | B19065; B01001 |
| Medicaid | People with Medicaid or means-tested coverage | C27007 |
| Income maintenance (SSI, SNAP, family assistance) | Aggregate SSI + public assistance income | B19066, B19067 |
| Unemployment insurance | Unemployed people | B23025 |
| Veterans' benefits | Civilian veterans | B21001 |
| Other transfers | Population | B01003 |
| Population, per capita income | Unit population: Vintage estimate split as in the units table | atlas units |

Per capita income for a piece = allocated personal income ÷ the piece's population.

## Known weaknesses and checks

- **LODES leaves out** the self-employed, the military, and informal work, and it places some multi-site employers' workers at one address. This affects school districts, state agencies, staffing firms (CNS14) and some public administration (CNS20). Check: compare LODES workplace shares by sector with ACS place-of-work counts (CTPP 2017–2021, workers by industry by workplace tract) for every split county. Where they differ by more than 10 points in education, public administration or administrative support, use the CTPP share for that sector.
- **ACS tract estimates are noisy.** Pieces hold 100+ tracts, so the noise largely cancels; report the margin of error of each key at the piece level.
- **QCEW suppression** is heavy for small sectors (mining, utilities, management of companies). The residual rule (principle 4) keeps county totals right but cannot place those sectors precisely.
- **Validation where truth exists:** NYC's boroughs and the whole-county units are published directly. Run the method on a known split as a test: for example, treat a five-county metro as one "county", allocate with the keys, and compare with the published county figures. Report the error by measure.

## Decisions needed

1. **Wages and GDP within a sector.** (a) Sector jobs only, which assumes every piece pays the county's average wage in each sector. (b) Sector jobs × a piece wage index from the LODES earnings bands (share of jobs over $3,333/month), which raises high-wage cores like Midtown and lowers others. **Recommendation: (b)**, validated against CTPP workplace earnings, and falling back to (a) for any county where the index fails that check.
2. **Real estate GDP.** Housing (owner-occupied imputed rent plus tenant rent) is most of real estate GDP and belongs where homes are, not where real estate firms work. **Recommendation:** split the real estate sector's GDP between a housing part, keyed by aggregate home value and gross rent (ACS B25079, B25065), and a business part keyed by real estate jobs (CNS11), in national-accounts proportions.
3. **Establishments.** ZIP Code Business Patterns (proposed: closer to QCEW's count, but ZIP codes cross piece lines) vs. LODES jobs (simpler, but counts jobs, not establishments). **Recommendation: ZIP Code Business Patterns.**
4. **Personal income.** By component (proposed) vs. one key (aggregate household income, B19313). Components cost more but match BEA's structure. **Recommendation: by component.**
5. **Publishing allocated sector detail.** Publish piece values by sector, or only totals and broad sector groups? Allocated small sectors are uncertain. **Recommendation:** publish totals and about 10 sector groups for pieces, with full detail kept internally.

All five recommendations were adopted on 2026-11-27.

## Build (2026-11-27)

`regions/keys/build_keys.py --cache DIR` reads the atlas units (pieces release 1.3) and writes, for the 55 split counties (148 pieces):

- `keys.csv`: `key_id, county_fips, piece_id, value, share`. 144 keys; within every county and key the shares sum to 1. A key whose county total is zero (582 county–key pairs, mostly state and local government jobs in private-only sectors) has no share, and the figure uses the fallback key.
- `keys_catalog.csv`: what each key measures, its source and year.
- `measure_keys.csv`: which key splits which BEA or QCEW figure, with a fallback key.
- `sector_groups.csv`: NAICS sectors to the 10 publishing groups (decision 5: BLS supersectors, with public administration as its own group).
- `pay_index.csv`: per piece, the QCEW 2024 county average monthly pay, the calibrated mean of the top LODES earnings band, and the piece's pay index.
- `acs_imputed_share.csv`: how much of each ACS aggregate was imputed (below).

Sources: LODES 8 WAC 2024 (Michigan 2021), all, private and federal job types; QCEW 2024 annual county averages (BLS); ZIP Code Business Patterns 2023 with the 2020 ZCTA–tract relationship file; ACS 5-year 2020–2024 table-based summary files. All are logged and pinned in `regions/pieces/inputs/manifest.csv` (558 inputs).

**Results checked:**
- LODES job counts are 92–111% of QCEW employment by county.
- The pay index runs from 0.78 to 1.15 (highest: LA Downtown, Hollywood & Wilshire; Inner Houston 1.08). The calibrated top-band mean runs from $7,800 to $21,400 a month.
- Manhattan: Midtown & Lower Manhattan takes 84% of wage-weighted jobs, 74% of establishments and 98.5% of finance jobs, but 28% of Medicaid coverage and 41% of dividend, interest and rent income. Real estate GDP falls between, at 57%.

**ACS gaps.** Table-based summary files leave out a tract when an aggregate is withheld (too few sample cases), and some rows carry annotation codes instead of an estimate. Count tables are complete. A missing aggregate is imputed as the tract's base count times the ratio of aggregate to base over the reported tracts of its piece. Bases: households for income, households receiving SSI or public assistance for those, renter units for gross rent. For home value, where the median is published, median × owner units, scaled per piece to the reported aggregates; otherwise owner units. Share of each split-county aggregate imputed:

| ACS aggregate | Imputed |
|---|---|
| Wage or salary income (B19062) | 0.0% |
| Self-employment income (B19063) | 2.8% |
| Interest, dividends, rent (B19064) | 3.4% |
| Social Security (B19065) | 0.6% |
| SSI (B19066) | 9.3% |
| Public assistance (B19067) | 21.8% |
| Owner home value (B25079) | 42.8% (42.4% from calibrated medians) |
| Gross rent (B25065) | 0.1% |

**Assumptions to check:**
- Housing's share of real estate GDP is now read from BEA's GDP by industry (table TVA105, 2024): Housing is 71.5% of "real estate and rental and leasing", the line county GDP reports (the earlier placeholder was 0.72).
- `RENT_TO_VALUE = 0.05`: the annual imputed rent per dollar of owner home value, which sets how owner housing is weighted against tenant rent in `housing_services`.
- The LODES earnings bands are not broken down by sector, so the pay index raises or lowers every sector in a piece alike.

**Not yet done:**
- The CTPP check (LODES vs. ACS workplace shares by sector, with CTPP replacing LODES where they differ by more than 10 points in education, public administration or administrative support). CTPP data was not reachable from this environment.
- About 95,000 establishments nationally are in ZIP codes with no ZCTA (PO boxes, single-firm ZIP codes) and are left out of `est_*`.

**Fix (2026-11-27).** ZIP codes were spread over tracts using populations of the split counties' tracts only, so a ZIP straddling a county line put all its establishments on the split-county side. The keys now use every tract in the country (`build_keys.tract_pop`). The total establishment key moved by up to 7 points (Travis, Fulton); job, wage and residence keys were unchanged. The workplace, pay-index and establishment steps are now functions shared with the validation (`lodes_keys`, `pay_index`, `wage_keys`, `zbp_keys`).

## QCEW 2024 by atlas unit

`regions/data/apply_qcew.py --cache DIR` reads the QCEW 2024 annual single file (BLS) and writes:

- `qcew_2024_units.csv` (published table): for every unit, `estabs, emplvl, total_wages, avg_weekly_wage` for the total, the four ownerships (federal, state, local, private) and the 11 private supersectors (decision 5), with `method`: `published` (county units and the four whole-county pieces), `allocated` (pieces of split counties), `withheld` (the county cell is withheld by BLS, so the pieces get none).
- `qcew_2024_pieces_detail.csv` (internal): piece values by private NAICS sector, plus each piece's share of the county residual of withheld sectors.

Method: private sectors are split by their keys; the residual of withheld sectors (county private total minus published sectors) by the summed keys of the withheld sectors; supersectors by the summed keys of their sectors, where the county supersector is published; ownership totals by the government keys. Each published county cell's piece values are finally scaled to the county figure, because BLS's cells do not always add up exactly. Checks: every split county's pieces sum to its published total, ownership and supersector figures (0 failures). 3,227 units are covered; Kalawao County, Hawaii (15005) has no QCEW row (BLS includes it with Maui). Of the pieces' rows, 4 supersector and 4 ownership cells are withheld.

Example: Midtown & Lower Manhattan 2,043,120 jobs at $3,434 a week on average, Uptown Manhattan 423,678 at $1,925; Inner Houston 667,576 jobs, the most of Harris County's six pieces.

## Validation (2026-11-27)

`regions/keys/validate_keys.py --cache DIR` treats 15 multi-county metros as one "county" each (New York's five boroughs, Bay Area core, Dallas–Fort Worth, Houston, Atlanta, Twin Cities, Philadelphia, Detroit, the LA basin, South Florida, Seattle, Boston, Cleveland, Charlotte, Salt Lake; 50 counties). It shares each metro's QCEW 2024 total among its counties with keys built by the same code as for pieces, and compares with BLS's published county figures. Only cells published for every county of a metro are tested (`validation.csv`, every cell). Error = share of the metro total placed in the wrong county; the weighted mean weights by metro total:

| Measure | Cells | Key | Without pay index / ZBP | Baseline: all jobs | Baseline: population |
|---|---|---|---|---|---|
| Private employment, by sector | 261 | **1.3%** | | 10.2% | 15.2% |
| Private wages, by sector | 261 | **5.0%** | 6.3% (jobs only) | 16.7% | 25.4% |
| Private establishments, by sector | 261 | **4.6%** | 7.4% (jobs instead of ZBP) | 7.8% | 10.4% |
| Total wages | 15 | **6.2%** | 8.4% | 8.4% | 20.2% |
| Federal employment | 15 | **10.2%** | 14.2% (LODES only) | 18.5% | 22.0% |
| State government employment | 14 | **13.9%** | 17.2% (LODES only) | 18.2% | 24.4% |
| Local government employment | 14 | **5.9%** | | 9.3% | 6.8% |

- **Decisions 1 and 3 hold:** the pay index lowers wage error from 6.3% to 5.0%, and ZIP Code Business Patterns lowers establishment error from 7.4% to 4.6%.
- **Private employment by sector is close to exact** (median 1.2%); the worst cells are tiny sectors (Bay Area mining).
- **Wages are weakest in arts and entertainment** (sector 71: 19–29% in Boston, Philadelphia, LA and Detroit). Pro-sports payrolls are far above what the LODES earnings bands can show.
- **Government is the weak spot.** LODES alone places federal and state jobs at the wrong address for some employers: federal errors of 51% (Salt Lake) and 35% (Detroit, also on LODES 2021), state errors of 35% (Bay Area). The ACS-calibrated keys (Government keys, below) lower federal error from 14.2% to 10.2% (better in 10 of 15 metros; Detroit 35% to 13%, Salt Lake 51% to 34%, Twin Cities 18% to 5%; worse in Philadelphia, 5% to 15%, and the Bay Area, 4% to 10%) and state error from 17.2% to 13.9% (better in 13 of 14). Earlier alternatives were no clear improvement: ACS government workers at residence (federal 19.1%, state 20.9%, local 8.9%) and a 50/50 blend with LODES (federal 11.1% weighted but a worse median; state 18.9%; local 5.7%). Federal and state values for pieces are still indicative; publish them only at the ownership level.
- These tests split metros into counties of about 1M people; pieces are of similar size, so the errors should carry over, but splits inside one county may behave differently (for example, one large state campus).

## BEA by atlas unit (2026-11-27)

`regions/data/apply_bea.py --cache DIR` reads BEA's county files (apps.bea.gov, regional data):

| Table | Content | Year |
|---|---|---|
| CAGDP2, CAGDP9 | GDP by industry, current and chained 2017 dollars | 2024 |
| CAINC5N | Earnings by industry (place of work) | 2024 |
| CAINC4 | Personal income and its components (place of residence), population, per capita income | 2024 |
| CAINC35 | Transfer receipts by type | 2022 (latest published) |
| CAEMP25N | Employment by industry, including proprietors | 2022 (latest published) |

Outputs: `bea_units.csv` (every unit: totals, components and the industry groups, with `method` published / allocated / withheld / `bea_combined_area <area>`) and `bea_pieces_detail.csv` (internal: every allocated line for pieces, including industry detail).

Method, beyond the key table (`regions/keys/measure_keys.csv`, rebuilt with private-only keys for private industries):
- **Private industries** by wage-weighted private jobs (GDP and earnings) or private jobs (employment); real estate GDP by `gdp_real_estate`.
- **Government GDP** is one line for counties: it is first split by the county's 2024 government earnings mix (federal civilian, military, state, local, CAINC5N; state and local together where BEA withholds the split), each part by its key.
- **Withheld lines** ((D)) get their parent's residual, split among the withheld lines at the county by comparable proxy totals (wage-weighted jobs for industries), then among pieces by each line's key; pieces get no published value for a line BEA withholds.
- **Personal income** = net earnings by residence + dividends, interest and rent + transfers, each allocated with its residence key. 2024 transfers use the county's 2022 transfer mix (CAINC35) times each type's key. The adjustment for residence is derived per piece (net earnings by residence − earnings by place of work + contributions), so the BEA identity holds for every piece. Population: BEA's county population × each unit's 2020 share; per capita income = income ÷ population.
- **Exact sums:** every published county line's piece values are scaled to it. Check: 0 failures across all published lines.

**BEA combined areas.** BEA publishes 23 Virginia areas that join a county with its independent cities, and Maui + Kalawao (15901). Their 46 county units carry `bea_combined_area` and no value of their own. Fairfax County, a split county, is in BEA's area 51919 with Fairfax City and Falls Church: that area is shared among the two Fairfax pieces and the two cities. The cities get LODES workplace keys (with Fairfax's pay calibration) and residence keys scaled from Fairfax's per-person average, so their per capita income equals the Fairfax average by construction.

**Results:** Midtown & Lower Manhattan $888B GDP (2024), Uptown Manhattan $118B; per capita personal income $244,100 and $198,800 (both hold very high-income neighbourhoods). Within counties: Inner Houston $131,800 vs. Northeast Harris $61,100; LA Westside $174,800 vs. Crenshaw & South Central $53,200.

**Caveats:**
- **Proprietors in employment.** CAEMP25N's industry employment includes proprietors; its keys (LODES private jobs) do not, so industries with many proprietors (real estate, construction, other services) follow wage jobs.
- **Real GDP** (chained dollars) is allocated like current-dollar GDP; chained values do not add exactly, but each piece's components are scaled to the published county lines.
- **Validation:** the workplace keys are validated against QCEW (above) and the residence keys against BEA personal income (below).

## Validation of the residence keys (2026-11-27)

`regions/keys/validate_keys.py --part residence` runs the same metro test against BEA personal income: the 15 metros' county figures (CAINC4 2024, CAINC35 2022) are shared among their counties by ACS residence keys built by the same code as for pieces (`build_keys.acs_keys`, with withheld aggregates imputed within each county), and compared with BEA's published county figures (`validation_residence.csv`). Baselines: population, and one key for every component (total household income, ACS B19062–B19067: the alternative in decision 4). Error = share of the metro total placed in the wrong county, weighted by metro total:

| Measure (BEA line) | Key | One household-income key | Population |
|---|---|---|---|
| Personal income (CAINC4 10, sum of components) | **2.8%** | 3.7% | 9.1% |
| Net earnings by residence (45) | 3.0% | 2.9% | 8.9% |
| Dividends, interest and rent (46) | **4.6%** | 12.1% | 17.6% |
| Transfers, composite of 2022 types (47) | **3.0%** | 10.0% | 3.8% |
| Social Security (CAINC35 2110) | **1.0%** | 6.7% | 5.6% |
| Medicaid (2220) | **8.7%** | 19.5% | 12.5% |
| SSI (2310) | **7.5%** | 20.3% | 15.2% |
| EITC (2320) | **3.9%** | 15.8% | 9.4% |
| SNAP (2330) | **7.8%** | 18.5% | 11.9% |
| Unemployment insurance (2400) | **3.5%** | 11.1% | 4.4% |
| Veterans' benefits (2500) | **5.0%** | 11.3% | 8.7% |
| Medicare (2210) | 3.3% | 7.9% | 2.8% |
| Other retirement and disability (2120) | 6.6% | 5.7% | 6.0% |
| Military medical (2230) | 11.6% | 19.5% | 18.9% |

Per capita personal income by county: mean absolute error 5.5% with the component keys, 7.0% with one household-income key, 20.6% with population.

- **Decision 4 holds:** allocating by component beats one household-income key for personal income (2.8% vs. 3.7%) and per capita income (5.5% vs. 7.0%), mainly through dividends, interest and rent and the transfers.
- **Weak lines:** Medicare (65+ population 3.3% vs. total population 2.9%; median 2.6% vs. 2.7%), other retirement and disability benefits (every key tried 6–8%) and military medical benefits (veterans 11.6%, armed forces 15.9%). These are small lines; the keys are kept.
- Net earnings by residence follow the wage and self-employment key closely (3.0%); BEA's residence adjustment is itself built from commuting flows, which the ACS earnings at residence track well.

**Pieces release 1.1 (2026-11-27).** Keys, QCEW and BEA rebuilt for the six newly split counties (Capitol Region CT, Marion, St. Louis County, Honolulu, Bergen, Prince George's); every key value and every QCEW and BEA row of the earlier counties is unchanged, and all sum checks pass. Two Connecticut fixes: ACS tract codes since 2022 carry the planning region (translated to 2020 codes with `bx.tract_2020`), and BEA's CAINC35 (2022) still has Connecticut's old counties, so the Capitol Region's transfer receipts (CAINC4 line 47) are shared by the state's transfer mix instead of the county's. Validation (metro-as-county) does not depend on which counties are split and is unchanged.

**Pieces release 1.2 (2026-11-27).** Keys, QCEW and BEA rebuilt for the six counties with the 0.9M cap; counts unchanged (52 split counties, 142 pieces), all sum checks pass, validation unchanged.

**Pieces release 1.3 (2026-11-27).** Keys, QCEW and BEA rebuilt for Cook and Palm Beach (capped) and the newly split Pinellas, Erie and Milwaukee; 55 split counties, 148 pieces; all sum checks pass; validation unchanged.

## Workplace check (2026-11-27)

`regions/keys/check_workplace.py --cache DIR` tests where LODES puts jobs inside the split counties against where workers say they work. CTPP 2017-2021 (by workplace tract) is not reachable from the build environment, so the check uses the ACS's workplace-geography tables (2020-2024 five-year: B08528 class of worker, B08526 industry), which go down to places. In each of the 55 split counties, every place of 10,000+ ACS workers lying wholly in the county, plus the rest of the county, gets its share of the county's LODES jobs (2024; blocks to places by the Census 2020 block assignment files) and of its ACS workers; the misplaced share is sum |LODES share - ACS share| / 2. All jobs, 5.0% (job-weighted over the 55 counties), is the baseline: ACS sampling error, jobs vs workers, 2020 vs 2024 place lines.

| Class | Misplaced | Where it comes from (largest cases) |
| --- | --- | --- |
| All jobs (baseline) | 5.0% | |
| Private | 5.2% | |
| Education and health care | 5.8% | |
| State and local government | 12.4% | county and school-district payrolls at one office: Miami-Dade (LODES 84% in Miami city, ACS 35%), Fairfax (62% in Springfield CDP, ACS 3%), Broward (32% in Sunrise, ACS 5%), Los Angeles (59% in Los Angeles city, ACS 43%) |
| Public administration | 17.4% | the same, plus state government in Sacramento city (LODES 78%, ACS 55%) and Montgomery County MD government in Rockville (29% against 10%) |
| Federal government | 31.1% | LODES counts far fewer federal jobs than the ACS finds workers (Los Angeles 19,000 against 86,000) and puts them at a few addresses: Hillsborough (76% in University CDP, ACS 12%), Montgomery MD (26% in Potomac, ACS 5%; none at the Bethesda campuses) |
| Information | 18.8% | mostly industry coding, not place: LODES files studio and software payrolls at headquarters (Burbank 43% of Los Angeles County's information jobs, ACS 9%; Redmond 45% of King's, ACS 11%) while workers report other industries |
| Construction | 11.8% | LODES counts contractors' offices, the ACS the job site |

The check confirms the validation's weak spots (federal and state government) and locates them: a few counties whose government payrolls sit at one address. It led to the ACS-calibrated government keys below. Private employment, the bulk of every key, places as well as the baseline. Results in `workplace_check.csv` (county x class) and `workplace_check_areas.csv` (county x area x class).

## Government keys (2026-11-27)

Federal civilian and state government jobs are no longer keyed by LODES alone (`build_keys.gov_keys`, also used by the validation). Within each split county:

1. **Areas.** Every place of 10,000+ ACS workers lying wholly in the county, plus the rest of the county (as in the workplace check).
2. **Areas get their share of the county by ACS workplace counts** (2020–2024, B08528). Federal: federal workers minus armed forces at residence (B23025), because the ACS counts active-duty military as federal workers while QCEW and LODES count civilians. State: state government workers.
3. **Pieces get each area's jobs by LODES**: federal jobs (JT04); for state, state and local jobs (JT00 − JT02 − JT04), since LODES has no state/local split. An area with none of those jobs in LODES uses all jobs.

Key values stay in LODES jobs: federal sums to the county's LODES federal jobs, state to its LODES state and local jobs × the ACS state share. A county without ACS counts keeps the LODES key.

Uses:
- QCEW state employment uses `jobs_state`.
- BEA state government earnings and employment (CAINC5N and CAEMP25N line 2011) use `jobs_state`.
- Local government, and government by sector, keep `jobs_state_local`.
- For the Fairfax combination, the two cities' `jobs_state` is their LODES state and local jobs × Fairfax County's ACS state share.

Rejected:
- **ACS local government key.** The validation was a coin flip: 5.9% to 5.5%, better in 7 of 14 metros, and South Florida 3% to 14%.
- **One ACS key for state and local together.** State error rose to 19.5%.
- **Raw ACS federal, without removing armed forces.** 10.9%; it moves federal jobs toward bases, for example San Bernardino's desert piece from 19% to 67%.

**What moves.** 16% of the split counties' federal jobs change piece, with 33 of 55 counties moving more than 10%, mostly from central-city pieces outward. LODES's federal jobs come from federal personnel records and sit at a few office addresses, while QCEW also counts dispersed federal workers such as postal workers. Largest moves (old → new share of the county):
- Las Vegas & North Las Vegas: 77% → 26%
- Oakland & Berkeley: 92% → 44%
- Westside (Los Angeles): 59% → 15%
- Detroit & Grosse Pointes: 94% → 54%
- Urban Honolulu: 92% → 51%
- Pittsburgh: 85% → 48%
- Central & West Phoenix: 83% → 47%

State: 7% of jobs change piece, 13 counties more than 10%:
- Las Vegas: 76% → 43%
- City of Miami, Coral Gables & Kendall: 90% → 58%
- Eastern Fairfax: 93% → 63%
- I-270 Corridor & Upcounty: 79% → 55%
- St. Petersburg & South Pinellas: 22% → 47%

Small places' ACS federal counts carry wide margins, so a single piece's federal value is less certain than the validation average suggests.
