# Analytical specification

The deterministic rules the MCP server implements. Each rule is tagged with the decision it comes from
(D1–D11 are Shaun's decisions, recorded in `decisions.jsonl`). Rules tagged **[impl]** are
implementation details the agent proposed to make a decision executable. They are listed here so they can be
challenged; none of them changes this week's verdicts (see DECISION.md).

All defaults below are parameters on the tools, so a reviewer can replay a different threshold live.
The committed answer uses the defaults.

## 0. Inputs

A dataset is a folder under `data/` (configured root; tools take a dataset *name*, never a path):

| file | required | use |
|---|---|---|
| `trips.csv` | yes | trip rows (columns per DATA_GUIDE) |
| `schedule_v2.csv` | no | REC-114 revised runtimes (`route, revised_runtime_min, effective_date, note`) |
| `ops_log.txt` | no | free-text ops notes, context only |
| `incidents.csv` | no | dated incident context: `date, route, category[, ticket_id]` (`route` may be `ALL`) |

Only whitelisted `trips.csv` columns are loaded (`trip_id, route, vehicle_series, vehicle_class,
scheduled_departure, scheduled_runtime_min, actual_arrival, tz_offset`). Any other column (for example a rider
phone or complaint field in a future export) is dropped at load and reported by name only. [impl, from
directive (a)]

## 1. Row validity (D3, D4, D5)

A trip is evaluated in this order. The first failing rule excludes it, with a reason code.

1. `invalid_departure`: `scheduled_departure` fails a strict parse (`YYYY-MM-DD HH:MM[:SS]`, `T` separator allowed).
2. `invalid_arrival`: `actual_arrival` fails the same strict parse. `08:60` fails here. No repair is attempted. (D3)
3. `invalid_runtime`: `scheduled_runtime_min` is not a positive number.
4. `invalid_tz`: `tz_offset` does not match `±HH:MM`. A missing offset is invalid. [impl, approved turn 3:
   a conservative data-quality decision, because assuming a timezone would be an unsupported repair]
5. Timezone normalisation (D5): `arrival_ist = actual_arrival − tz_offset + 05:30`. `scheduled_departure` is local
   wall-clock (IST) per DATA_GUIDE. Rows whose offset ≠ `+05:30` are corrected and kept, flagged `tz_corrected`.
6. `arrival_not_after_departure`: `arrival_ist ≤ scheduled_departure`. The bus cannot arrive before it was
   scheduled to leave. Excluded from lateness, still visible in drill-down. (D4)

Non-excluding flags (shown in drill-down, never change a number) [impl]: `tz_corrected`,
`duplicate_trip_id`, `duplicate_record` (identical on every field except `trip_id`), `extreme_lateness`
(|lateness| > 120 min).

## 2. Applicable runtime and lateness (D1, D2)

- A trip is **identifiably 4xx** iff its `vehicle_class` or `vehicle_series` is exactly three digits
  starting with `4` (e.g. `414`). Two-digit series (this week's export: `01`…`40`) are **not** identifiable,
  because "14" can be 114, 214 or 414.
- Applicable runtime = `revised_runtime_min` from `schedule_v2.csv` **if** the trip is identifiably 4xx **and** its
  route is in schedule_v2 **and** the departure date ≥ `effective_date`; otherwise `scheduled_runtime_min`.
  (D2: apply the rule wherever it is identifiable.)
- **lateness_min = arrival_ist − (scheduled_departure + applicable runtime)**. (D1)
- REC-114 impact is reported separately (§6). It never rewrites the primary verdict for unidentifiable trips.

## 3. Trip-level late flag (D7)

A valid trip is **late** iff `lateness_min > 5` (`tolerance_min`). Exactly 5.0 is not late.

## 4. Route verdict (D8, D9)

For each route, over its valid trips:

- `late_share` = (# trips with lateness > 5) / (# valid trips)
- `median` = median lateness (standard median: mean of the two middle values for even n)
- **D8 rule passes** iff `late_share ≥ 0.30` **and** `median ≥ 3.0`.

**Primary verdict (D8)** = `LATE` iff the D8 rule passes on **all valid trips**. Incident days are never removed
from it, so the verdict answers "was this route materially late this week".

**Incident route-days (D9)** [impl, approved turn 3]: a (route, departure-date) is an *incident day* iff the median
lateness of its valid trips is > 15 min (`incident_day_median_min`, three times the tolerance). This threshold is an
analytical implementation choice, not something the assignment supplies. This week the largest non-incident
route-day median is +9, so the threshold is not near a decision boundary.

**Character** (D9, a separate field that never changes the verdict):

| verdict | incident days? | D8 rule without incident days | character |
|---|---|---|---|
| LATE | none | n/a | `systematic` |
| LATE | yes | passes | `mixed` |
| LATE | yes | fails | `incident_driven` |
| NOT LATE | yes | n/a | `incident_day_only` |
| NOT LATE | none | n/a | none |

The metrics without incident days are reported next to the verdict (`ex_incident`) so the characterisation can
be checked. Incident trips always count toward rider impact (§7). "Not systematically late" is never shown as
"nothing went wrong".

`min_trips` = 20 [impl]: a route with fewer valid trips gets verdict `INSUFFICIENT DATA` instead of a call.
This week's minimum is 103, so it does not bind.

## 5. Worst-three ranking (D10)

All routes are sorted by:

1. `late_share` descending
2. `median` descending
3. route code ascending (deterministic tie-break)

The top N (default 3) are the worst routes. If any of them is `NOT LATE`, or is `LATE` with character
`incident_driven` or `mixed`, the output warns explicitly rather than silently re-ranking. Supporting columns:

- `p85`, `p95` (numpy linear interpolation)
- `mean`
- `trips_late` (>5) and `trips_gt10`
- `days_rule_passes`: number of service days on which the D8 rule passes using that day's trips alone
- **rank stability**: day-level bootstrap. Resample service days with replacement (seed 114, 1000 draws), re-rank
  with the same rule, and report P(route in top N) and P(route at exactly its rank).

## 6. REC-114 impact (D2)

For each route in schedule_v2: count identifiable 4xx trips; then show route metrics and the D8 verdict under three
runtimes: (i) export runtime, (ii) revised runtime for **every** trip of the route from `effective_date`,
(iii) revised runtime for every trip all week. Views (ii) and (iii) are counterfactual ("if the whole route were
4xx"), shown so the review's numbers can be reconciled. They never feed the primary verdict.

## 7. Rider impact (D11)

Per route, and per incident route-day: `trips_late` (>5), `excess_minutes` = Σ max(0, lateness − 5), and
`late_minutes` = Σ max(0, lateness). Kept separate from the systematic verdict and ranking. Incident-day trips stay
in these totals (D9).

## 8. Ops log and incidents (D6)

- `ops_log.txt` is context only. It never excludes, adjusts or excuses a trip.
- Lines are returned as `{weekday, time, category}`. The category comes from keyword rules (weather/diversion,
  crowding, staffing, vehicle swap, rider complaint, normal, other). Free text is returned only after PII
  redaction, and **never** for lines categorised as a rider complaint. [impl, directive (a)]
- Every response states the temporal caveat: HANDOFF calls it *last week's* log; entries have weekdays but no
  dates, so they cannot be joined to route-days.
- `incidents.csv` (if supplied) is joined to route-days by date and route (`ALL` matches every route) and shown as
  context next to incident days. It also never changes a number.

## 9. Redaction (directive (a))

Every tool result passes through one redaction function before it is returned. It replaces these with
`[REDACTED]`:

- Indian mobile numbers (optional country code, `[6-9]` followed by 9 digits, optional single separator in the
  middle)
- landline numbers starting with `0` (STD code plus 6–8 digits)
- any bare run of 10 or more digits
- e-mail addresses

The patterns are anchored so that timestamps and trip ids don't match. Combined with the column
whitelist and the complaint rule in §8, no rider phone number or verbatim complaint text can leave a tool.
