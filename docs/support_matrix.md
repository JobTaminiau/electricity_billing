# Tariff support matrix

Generated from the tariff metadata by `python scripts/generate_tariff_docs.py`; do not edit.

Verification status (spec 5.1): `unverified` values have unknown provenance; `transcribed` values cite a leaf, revision and page of a checksummed source; `owner_verified` needs an entry in `coned_billing/tariffs/v1/verification_record.yml`, which only the owner edits.

Effective dates are dates of service, start inclusive, end exclusive. Rates and options not listed here are rejected (D3).

## `sc1_rate1`: SC-1 Rate I - Residential and Religious

Voltage: n/a. Zone: not zone-specific.

| Version | Effective (service dates) | Status | Modes | Source leaves | Notes |
|---|---|---|---|---|---|
| legacy | undated | unverified | scenario | uncited |  |
| 2019-01-01 | 2019-01-01 to 2020-02-01 | transcribed | historical, scenario | 388 r11 |  |
| 2020-02-01 | 2020-02-01 to 2021-01-01 | transcribed | historical, scenario | 388 r13 |  |
| 2021-01-01 | 2021-01-01 to 2022-01-01 | transcribed | historical, scenario | 388 r14 |  |
| 2022-01-01 | 2022-01-01 to 2023-08-01 | transcribed | historical, scenario | 388 r15 |  |
| 2023-08-01 | 2023-08-01 to 2024-01-01 | transcribed | historical, scenario | 388 r17 |  |
| 2024-01-01-r18 | 2024-01-01 to 2024-02-04 | transcribed | historical, scenario | 388 r18 | ambiguous: overlaps 2024-01-01-r19 |
| 2024-01-01-r19 | 2024-01-01 to 2024-02-04 | transcribed | historical, scenario | 388 r19 | ambiguous: overlaps 2024-01-01-r18 |
| 2024-02-04 | 2024-02-04 to 2025-01-01 | transcribed | historical, scenario | 388 r20 |  |
| 2025-01-01 | 2025-01-01 to 2026-02-01 | transcribed | historical, scenario | 388 r21 |  |
| 2026-02-01 | 2026-02-01 to open (checked 2026-10-23) | transcribed | historical, scenario | 388 r23 |  |

Implemented components (latest transcribed version, 2026-02-01):

- `customer_charge` (fixed_charge): 21 USD/month; holidays excluded: none
- `energy_delivery_summer` (delivery_energy): 0-250: 0.16402 USD/kWh; over 250: 0.18858 USD/kWh; months 6,7,8,9; holidays excluded: none
- `energy_delivery_other` (delivery_energy): 0.16402 USD/kWh; months 1,2,3,4,5,10,11,12; holidays excluded: none

Excluded components:

- `additional_delivery_charges_gr26`: Additional Delivery Charges and Adjustments (General Rule 26). Set by monthly statements (e.g. MAC, surcharges, adjustment factors) that are not transcribed; not modeled.
- `supply_charges_gr25`: Supply and supply-related charges (General Rule 25: Market Supply Charge, Merchant Function Charge). Supply is not part of this delivery tariff version; calculations must supply an explicit supply assumption (D5). A packaged, sourced MSC dataset is WP8.
- `increase_in_rates_gr30`: Increase in Rates and Charges (General Rule 30). Percentage increase shown on a separate statement; not transcribed, not modeled.

Required account inputs: none.

## `sc2_rate1`: SC-2 Rate I - General - Small

Voltage: n/a. Zone: not zone-specific.

| Version | Effective (service dates) | Status | Modes | Source leaves | Notes |
|---|---|---|---|---|---|
| legacy | undated | unverified | scenario | uncited |  |
| 2019-01-01 | 2019-01-01 to 2020-02-01 | transcribed | historical, scenario | 397 r11 |  |
| 2020-02-01 | 2020-02-01 to 2021-01-01 | transcribed | historical, scenario | 397 r13 |  |
| 2021-01-01 | 2021-01-01 to 2022-01-01 | transcribed | historical, scenario | 397 r14 |  |
| 2022-01-01 | 2022-01-01 to 2023-08-01 | transcribed | historical, scenario | 397 r15 |  |
| 2023-08-01 | 2023-08-01 to 2024-01-01 | transcribed | historical, scenario | 397 r17 |  |
| 2024-01-01-r18 | 2024-01-01 to 2024-02-04 | transcribed | historical, scenario | 397 r18 | ambiguous: overlaps 2024-01-01-r19 |
| 2024-01-01-r19 | 2024-01-01 to 2024-02-04 | transcribed | historical, scenario | 397 r19 | ambiguous: overlaps 2024-01-01-r18 |
| 2024-02-04 | 2024-02-04 to 2025-01-01 | transcribed | historical, scenario | 397 r20 |  |
| 2025-01-01 | 2025-01-01 to 2026-02-01 | transcribed | historical, scenario | 397 r21 |  |
| 2026-02-01 | 2026-02-01 to open (checked 2026-10-23) | transcribed | historical, scenario | 397 r23 |  |

Implemented components (latest transcribed version, 2026-02-01):

- `customer_charge` (fixed_charge): 34 USD/month; holidays excluded: none
- `energy_delivery_summer` (delivery_energy): 0.2038 USD/kWh; months 6,7,8,9; holidays excluded: none
- `energy_delivery_other` (delivery_energy): 0.1709 USD/kWh; months 1,2,3,4,5,10,11,12; holidays excluded: none

Excluded components:

- `customer_charge_unmetered`: Customer Charge for unmetered service (GR 6.9). Rate option not supported (D3).
- `additional_delivery_charges_gr26`: Additional Delivery Charges and Adjustments (General Rule 26). Set by monthly statements (e.g. MAC, surcharges, adjustment factors) that are not transcribed; not modeled.
- `supply_charges_gr25`: Supply and supply-related charges (General Rule 25: Market Supply Charge, Merchant Function Charge). Supply is not part of this delivery tariff version; calculations must supply an explicit supply assumption (D5). A packaged, sourced MSC dataset is WP8.
- `increase_in_rates_gr30`: Increase in Rates and Charges (General Rule 30). Percentage increase shown on a separate statement; not transcribed, not modeled.

Required account inputs: metered service (the unmetered General Rule 6.9 Customer Charge is not supported).

## `sc8_rate1_lt`: SC-8 Rate I - Multiple Dwellings - Redistribution

Voltage: low tension. Zone: not zone-specific.

| Version | Effective (service dates) | Status | Modes | Source leaves | Notes |
|---|---|---|---|---|---|
| legacy | undated | unverified | scenario | uncited |  |
| 2020-02-01 | 2020-02-01 to 2021-01-01 | transcribed | historical, scenario | 432 r12 |  |
| 2021-01-01 | 2021-01-01 to 2022-01-01 | transcribed | historical, scenario | 432 r13 |  |
| 2022-01-01 | 2022-01-01 to 2023-08-01 | transcribed | historical, scenario | 432 r14 |  |
| 2023-08-01 | 2023-08-01 to 2024-01-01 | transcribed | historical, scenario | 432 r16 |  |
| 2024-01-01 | 2024-01-01 to 2024-03-16 | transcribed | historical, scenario | 432 r17 |  |
| 2024-03-16 | 2024-03-16 to 2025-01-01 | transcribed | historical, scenario | 432 r18 |  |
| 2025-01-01 | 2025-01-01 to 2026-02-01 | transcribed | historical, scenario | 432 r19 |  |
| 2026-02-01 | 2026-02-01 to open (checked 2026-10-23) | transcribed | historical, scenario | 432 r21 |  |

Implemented components (latest transcribed version, 2026-02-01):

- `customer_charge` (fixed_charge): 59 USD/month; holidays excluded: none
- `demand_delivery_summer` (delivery_demand): 55.65 USD/kW; months 6,7,8,9; holidays excluded: none; demand: 30-minute integrated, fixed_clock
- `demand_delivery_other` (delivery_demand): 42.9 USD/kW; months 1,2,3,4,5,10,11,12; holidays excluded: none; demand: 30-minute integrated, fixed_clock
- `energy_delivery` (delivery_energy): 0.0123 USD/kWh; holidays excluded: none

Excluded components:

- `additional_delivery_charges_gr26`: Additional Delivery Charges and Adjustments (General Rule 26). Set by monthly statements (e.g. MAC, surcharges, adjustment factors) that are not transcribed; not modeled.
- `reactive_power_demand_gr1011`: Reactive Power Demand Charge (General Rule 10.11). Needs kVAr metering data, which the package does not take; not modeled.
- `minimum_monthly_charge_gr1010`: Minimum Monthly Charge (General Rule 10.10, Contract Demand). The Contract Demand (highest registered demand in the most recent 18 months) can be computed with coned_billing.demand.contract_demand, but the comparison base (monthly Pure Base Revenue and the MAC, GR 10.10 c, continued on leaf 91, GR 2 and GR 26) was not obtained; not modeled.
- `supply_charges_gr25`: Supply and supply-related charges (General Rule 25: Market Supply Charge, Merchant Function Charge). Supply is not part of this delivery tariff version; calculations must supply an explicit supply assumption (D5). A packaged, sourced MSC dataset is WP8.
- `increase_in_rates_gr30`: Increase in Rates and Charges (General Rule 30). Percentage increase shown on a separate statement; not transcribed, not modeled.

Required account inputs: service voltage: low_tension.

Supported demand resolution: billed demand is the 30-minute integrated demand (GR 10.4), from interval data of that length or finer (`coned_billing.demand`). Hourly data are accepted only as a flagged `hourly_approximation`.

## `sc9_rate1_ht`: SC-9 Rate I - General - Large

Voltage: high tension. Zone: not zone-specific.

| Version | Effective (service dates) | Status | Modes | Source leaves | Notes |
|---|---|---|---|---|---|
| legacy | undated | unverified | scenario | uncited |  |
| 2020-02-01 | 2020-02-01 to 2021-01-01 | transcribed | historical, scenario | 445 r13 |  |
| 2021-01-01 | 2021-01-01 to 2022-01-01 | transcribed | historical, scenario | 445 r14 |  |
| 2022-01-01 | 2022-01-01 to 2023-08-01 | transcribed | historical, scenario | 445 r15 |  |
| 2023-08-01 | 2023-08-01 to 2024-01-01 | transcribed | historical, scenario | 445 r17 |  |
| 2024-01-01 | 2024-01-01 to 2024-03-16 | transcribed | historical, scenario | 445 r18 |  |
| 2024-03-16 | 2024-03-16 to 2025-01-01 | transcribed | historical, scenario | 445 r19 |  |
| 2025-01-01 | 2025-01-01 to 2026-02-01 | transcribed | historical, scenario | 445 r20 |  |
| 2026-02-01 | 2026-02-01 to open (checked 2026-10-23) | transcribed | historical, scenario | 445 r22 |  |

Implemented components (latest transcribed version, 2026-02-01):

- `customer_charge` (fixed_charge): 72 USD/month; holidays excluded: none
- `demand_delivery_summer` (delivery_demand): 30.41 USD/kW; months 6,7,8,9; holidays excluded: none; demand: 30-minute integrated, fixed_clock
- `demand_delivery_other` (delivery_demand): 21.17 USD/kW; months 1,2,3,4,5,10,11,12; holidays excluded: none; demand: 30-minute integrated, fixed_clock
- `energy_delivery` (delivery_energy): 0.0143 USD/kWh; holidays excluded: none

Excluded components:

- `additional_delivery_charges_gr26`: Additional Delivery Charges and Adjustments (General Rule 26). Set by monthly statements (e.g. MAC, surcharges, adjustment factors) that are not transcribed; not modeled.
- `reactive_power_demand_gr1011`: Reactive Power Demand Charge (General Rule 10.11). Needs kVAr metering data, which the package does not take; not modeled.
- `minimum_monthly_charge_gr1010`: Minimum Monthly Charge (General Rule 10.10, Contract Demand). The Contract Demand (highest registered demand in the most recent 18 months) can be computed with coned_billing.demand.contract_demand, but the comparison base (monthly Pure Base Revenue and the MAC, GR 10.10 c, continued on leaf 91, GR 2 and GR 26) was not obtained; not modeled.
- `supply_charges_gr25`: Supply and supply-related charges (General Rule 25: Market Supply Charge, Merchant Function Charge). Supply is not part of this delivery tariff version; calculations must supply an explicit supply assumption (D5). A packaged, sourced MSC dataset is WP8.
- `increase_in_rates_gr30`: Increase in Rates and Charges (General Rule 30). Percentage increase shown on a separate statement; not transcribed, not modeled.

Required account inputs: service voltage: high_tension.

Supported demand resolution: billed demand is the 30-minute integrated demand (GR 10.4), from interval data of that length or finer (`coned_billing.demand`). Hourly data are accepted only as a flagged `hourly_approximation`.

## `sc9_rate1_lt`: SC-9 Rate I - General - Large

Voltage: low tension. Zone: not zone-specific.

| Version | Effective (service dates) | Status | Modes | Source leaves | Notes |
|---|---|---|---|---|---|
| legacy | undated | unverified | scenario | uncited |  |
| 2020-02-01 | 2020-02-01 to 2021-01-01 | transcribed | historical, scenario | 445 r13 |  |
| 2021-01-01 | 2021-01-01 to 2022-01-01 | transcribed | historical, scenario | 445 r14 |  |
| 2022-01-01 | 2022-01-01 to 2023-08-01 | transcribed | historical, scenario | 445 r15 |  |
| 2023-08-01 | 2023-08-01 to 2024-01-01 | transcribed | historical, scenario | 445 r17 |  |
| 2024-01-01 | 2024-01-01 to 2024-03-16 | transcribed | historical, scenario | 445 r18 |  |
| 2024-03-16 | 2024-03-16 to 2025-01-01 | transcribed | historical, scenario | 445 r19 |  |
| 2025-01-01 | 2025-01-01 to 2026-02-01 | transcribed | historical, scenario | 445 r20 |  |
| 2026-02-01 | 2026-02-01 to open (checked 2026-10-23) | transcribed | historical, scenario | 445 r22 |  |

Implemented components (latest transcribed version, 2026-02-01):

- `customer_charge` (fixed_charge): 72 USD/month; holidays excluded: none
- `demand_delivery_summer` (delivery_demand): 44.05 USD/kW; months 6,7,8,9; holidays excluded: none; demand: 30-minute integrated, fixed_clock
- `demand_delivery_other` (delivery_demand): 34.5 USD/kW; months 1,2,3,4,5,10,11,12; holidays excluded: none; demand: 30-minute integrated, fixed_clock
- `energy_delivery` (delivery_energy): 0.0154 USD/kWh; holidays excluded: none

Excluded components:

- `additional_delivery_charges_gr26`: Additional Delivery Charges and Adjustments (General Rule 26). Set by monthly statements (e.g. MAC, surcharges, adjustment factors) that are not transcribed; not modeled.
- `reactive_power_demand_gr1011`: Reactive Power Demand Charge (General Rule 10.11). Needs kVAr metering data, which the package does not take; not modeled.
- `minimum_monthly_charge_gr1010`: Minimum Monthly Charge (General Rule 10.10, Contract Demand). The Contract Demand (highest registered demand in the most recent 18 months) can be computed with coned_billing.demand.contract_demand, but the comparison base (monthly Pure Base Revenue and the MAC, GR 10.10 c, continued on leaf 91, GR 2 and GR 26) was not obtained; not modeled.
- `supply_charges_gr25`: Supply and supply-related charges (General Rule 25: Market Supply Charge, Merchant Function Charge). Supply is not part of this delivery tariff version; calculations must supply an explicit supply assumption (D5). A packaged, sourced MSC dataset is WP8.
- `increase_in_rates_gr30`: Increase in Rates and Charges (General Rule 30). Percentage increase shown on a separate statement; not transcribed, not modeled.

Required account inputs: service voltage: low_tension.

Supported demand resolution: billed demand is the 30-minute integrated demand (GR 10.4), from interval data of that length or finer (`coned_billing.demand`). Hourly data are accepted only as a flagged `hourly_approximation`.

## `sc9_rate2_lt`: SC-9 Rate II - General - Large - Time-of-Day

Voltage: low tension. Zone: not zone-specific.

| Version | Effective (service dates) | Status | Modes | Source leaves | Notes |
|---|---|---|---|---|---|
| legacy | undated | unverified | scenario | uncited |  |
| 2020-02-01 | 2020-02-01 to 2021-01-01 | transcribed | historical, scenario | 449 r12 |  |
| 2021-01-01 | 2021-01-01 to 2022-01-01 | transcribed | historical, scenario | 449 r13 |  |
| 2022-01-01 | 2022-01-01 to 2023-08-01 | transcribed | historical, scenario | 449 r14 |  |
| 2023-08-01 | 2023-08-01 to 2024-01-01 | transcribed | historical, scenario | 449 r16 |  |
| 2024-01-01 | 2024-01-01 to 2025-01-01 | transcribed | historical, scenario | 449 r17 |  |
| 2025-01-01 | 2025-01-01 to 2026-02-01 | transcribed | historical, scenario | 449 r18 |  |
| 2026-02-01 | 2026-02-01 to open (checked 2026-10-23) | transcribed | historical, scenario | 449 r20 |  |

Implemented components (latest transcribed version, 2026-02-01):

- `customer_charge` (fixed_charge): 510 USD/month; holidays excluded: none
- `demand_summer_weekday_0800_1800` (delivery_demand): 11.33 USD/kW; months 6,7,8,9; Mon-Fri; 08:00-18:00; holidays excluded: none; demand: 30-minute integrated, fixed_clock
- `demand_summer_weekday_0800_2200` (delivery_demand): 22.82 USD/kW; months 6,7,8,9; Mon-Fri; 08:00-22:00; holidays excluded: none; demand: 30-minute integrated, fixed_clock
- `demand_summer_all_hours` (delivery_demand): 20.61 USD/kW; months 6,7,8,9; holidays excluded: none; demand: 30-minute integrated, fixed_clock
- `demand_other_weekday_0800_2200` (delivery_demand): 19.41 USD/kW; months 1,2,3,4,5,10,11,12; Mon-Fri; 08:00-22:00; holidays excluded: none; demand: 30-minute integrated, fixed_clock
- `demand_other_all_hours` (delivery_demand): 5.85 USD/kW; months 1,2,3,4,5,10,11,12; holidays excluded: none; demand: 30-minute integrated, fixed_clock
- `energy_delivery` (delivery_energy): 0.0079 USD/kWh; holidays excluded: none

Excluded components:

- `additional_delivery_charges_gr26`: Additional Delivery Charges and Adjustments (General Rule 26). Set by monthly statements (e.g. MAC, surcharges, adjustment factors) that are not transcribed; not modeled.
- `reactive_power_demand_gr1011`: Reactive Power Demand Charge (General Rule 10.11). Needs kVAr metering data, which the package does not take; not modeled.
- `minimum_monthly_charge_gr1010`: Minimum Monthly Charge (General Rule 10.10, Contract Demand). The Contract Demand (highest registered demand in the most recent 18 months) can be computed with coned_billing.demand.contract_demand, but the comparison base (monthly Pure Base Revenue and the MAC, GR 10.10 c, continued on leaf 91, GR 2 and GR 26) was not obtained; not modeled.
- `supply_charges_gr25`: Supply and supply-related charges (General Rule 25: Market Supply Charge, Merchant Function Charge). Supply is not part of this delivery tariff version; calculations must supply an explicit supply assumption (D5). A packaged, sourced MSC dataset is WP8.
- `increase_in_rates_gr30`: Increase in Rates and Charges (General Rule 30). Percentage increase shown on a separate statement; not transcribed, not modeled.

Required account inputs: service voltage: low_tension.

Supported demand resolution: billed demand is the 30-minute integrated demand (GR 10.4), from interval data of that length or finer (`coned_billing.demand`). Hourly data are accepted only as a flagged `hourly_approximation`.
