# Modeling datasets

| File | One row per | Rows |
|---|---|---|
| `model_route_month.csv` | route × month | 677 |
| `model_system_month.csv` | month (whole system) | 31 |

Period: Jan 2024 – Jul 2026. Built by `merge.py`.

## `model_route_month.csv`

| Column | Meaning |
|---|---|
| `month` | YYYY-MM |
| `route_key` | Unique route ID: `era:route_name_clean` |
| `era` | `pre` (before Aug 2025 redesign), `transition` (Aug–Sep 2025), `post` |
| `route_code` | Route number/code (e.g. `6A`, `DR`) |
| `route_name_clean` | Standardized route name |
| `route_group` | `campus_apartment`, `community`, or `dr_vp` (demand response / vanpool) |
| `in_service` | 1 = route running that month (0 = summer-off campus route or suspended) |
| `pax_suspect` | 1 = passengers look copied from prior year; exclude from modeling |
| `miles_hours_suspect` | 1 = miles/hours unreliable (Jan–Mar 2026 fixed routes) |
| `total_miles`, `total_hours` | Vehicle revenue miles / hours |
| `pax_per_hour`, `pax_per_mile` | Passengers ÷ hours / miles (blank if suspect) |
| `pax_lag1`, `pax_lag12` | Passengers 1 / 12 months earlier, same `route_key` |
| `group_*` | One-hot of `route_group` |
| *calendar, weather, flags* | See shared columns below |
| **`passengers`** | **Target: monthly boardings** |

## `model_system_month.csv`

| Column | Meaning |
|---|---|
| `month` | YYYY-MM |
| `{group}_passengers` | Boardings per route group |
| `{group}_total_miles`, `{group}_total_hours` | Revenue miles / hours per route group |
| `system_passengers`, `system_hours` | Sum across all groups |
| *calendar, weather, flags* | See shared columns below |

`{group}` = `campus_apartment`, `community`, `dr_vp`.

## Shared columns (both files)

**Calendar** (Purdue academic calendar; counts are days in the month)

| Column | Meaning |
|---|---|
| `session_days` / `session_weekdays` | Days / weekdays with fall or spring classes in session |
| `finals_days`, `break_days`, `closed_days` | Final exam / break / university-closed days |
| `summer_session_days` | Summer term days |
| `commencement`, `term_start` | 1 = month has commencement / first day of classes |
| `days_in_month` | Calendar days |
| `session_share` | `session_days / days_in_month` |

**Weather** (Lafayette airport, LAF)

| Column | Meaning |
|---|---|
| `mean_temp` | Avg temperature (°F) |
| `mean_wind` | Avg wind speed (mph) |
| `precip_in` | Total precipitation (inches) |
| `rain_days`, `snow_days`, `fog_days`, `thunder_days` | Days with that condition reported |
| `heavy_precip_days` | Days with ≥ 0.5 in precipitation |
| `extreme_cold_days` | Days with feels-like < 0 °F |
| `hot_days` | Days with high ≥ 90 °F |
| `low_vis_hours` | Hours with visibility < 1 mile |

**Time / policy**

| Column | Meaning |
|---|---|
| `month_sin`, `month_cos` | Cyclical encoding of calendar month |
| `post_redesign` | 1 = Aug 2025 onward (network redesign) |
| `fare_change` | 1 = Jan 2026 onward (new fares) |
