# DECISION — which routes were late, week of 3–9 Aug 2026

For Priya, Friday review. Every number here comes from the `cityflo-ontime` MCP server (dataset
`week-2026-08-03`, committed defaults, `what_if: false` unless stated otherwise). Each one can be
traced to individual trips with the `trips` and `route_detail` tools. The rules are in [SPEC.md](SPEC.md).

## 1. Verdict

**Five routes were late this week, and all five were systematically late, not one bad day.**

| Rank | Route | Trips >5 min late | Median | p95 | Days the rule passes |
|---|---|---|---|---|---|
| **1** | **R-14** | 85 / 118 (72.0%) | +8 | +16 | 7/7 |
| **2** | **R-33** | 49 / 104 (47.1%) | +5 | +11 | 7/7 |
| **3** | **R-26** | 44 / 103 (42.7%) | +4 | +10 | 5/7 |
| 4 | R-37 | 42 / 105 (40.0%) | +4 | +10 | 6/7 |
| 5 | R-31 | 37 / 112 (33.0%) | +4 | +9 | 4/7 |

- **The worst three are R-14, R-33 and R-26.** R-14 and R-33 are clear calls. **R-26 vs R-37 is a
  close call (§3.2).** We rank R-26 third under the committed rule and recommend **joint operational
  follow-up on R-26 and R-37**.
- **The LATE line is marginal at both edges.** R-31 is LATE with 3 late trips to spare. R-17 is NOT
  LATE, 4 late trips short of the line (§3.3).
- **R-35 is not systematically late, but it had the week's worst single-day disruption.** On Wed 5 Aug
  all 19 trips were 36–61 min late, giving 880 excess rider-minutes (§3.4).
- **REC-114 is applied to every trip the data identifies as 4xx. This week's export identifies zero
  such trips.** If REC-114 were instead applied to whole routes, the worst three would change (§4).
- **Data quality:** 5,292 rows, 5,250 valid, 42 excluded. Even under the worst-case treatment of the
  excluded rows, no verdict and no worst-three position changes (§5).

## 2. The rules (re-runnable on next week's data)

| # | Rule |
|---|---|
| D1 | `lateness = actual_arrival (in IST) − (scheduled_departure + applicable runtime)`, in minutes. |
| D2 | The applicable runtime is the export's `scheduled_runtime_min`. The exception is a trip that is **identifiably 4xx** (`vehicle_series`/class is exactly `4NN`) on or after `schedule_v2.effective_date`: that trip uses `revised_runtime_min`. The REC-114 impact is always shown separately. |
| D3 | An unparseable `actual_arrival` (e.g. `08:60`) is excluded and listed by trip id. It is never repaired. |
| D4 | An arrival not after the scheduled departure is excluded from the lateness calculation and stays visible in the data-quality output. |
| D5 | Each arrival is converted from its stamped `tz_offset` to +05:30 and kept. A missing offset excludes the trip `[impl]`. |
| D6 | The ops log is context only. Its entries have no date, so it never excludes, adjusts or excuses a trip. |
| D7 | A trip is **late** when lateness is > 5 min. |
| D8 | A route is **LATE** when ≥ 30% of its valid trips are > 5 min late **and** its median lateness is ≥ +3 min, computed on all valid trips. Otherwise it is **NOT LATE**. |
| D9 | Incident days are **never removed** from D8. A route-day whose median lateness is > 15 min is an incident day `[impl]`. A LATE route is labelled *systematic* (no incident days), *mixed* (still LATE without them) or *incident_driven* (LATE only because of them). A NOT LATE route that has an incident day is labelled *incident_day_only*. |
| D10 | Worst-N is ranked by late share (descending), then median (descending), then route code (ascending). Day-bootstrap rank stability (1,000 seeded draws) is reported as supporting evidence. |
| D11 | Rider impact (late trips; excess minutes = Σ max(0, lateness − 5)) is reported separately and never drives the ranking. |

Re-run: `route_verdicts`, then `worst_routes`, `route_detail <route>`, `data_quality_report` and
`rec114_impact`, all on the new dataset folder.

## 3. Consequential calls

### 3.1 Worst #1 R-14 and #2 R-33
- **Rule:** D10 on D8-valid trips.
- **Where it could break:**
  - R-14 is #1 only under the export timetable. If REC-114 were applied to every R-14 trip, it would
    fall to #3 or out of LATE altogether (§4).
  - A mean-lateness ranking would put R-35 (+8.05) level with R-14 (+8.07), purely because of one day.
  - We keep D10 because the export timetable is the only runtime the data can support. The mean is the
    floor the brief warns about.
- **Robustness:**
  - Late every day: 7/7 days pass for both routes.
  - Bootstrap probability of a top-three finish: 1.00 for R-14, 0.94 for R-33.
  - R-14 vs R-33 is a real gap: 72.0% vs 47.1%, z ≈ 3.8 (arithmetic on the tool's counts).
- **Cost / who pays:** the R-14 and R-33 depot heads carry the "worst" label. Their riders absorbed 85
  and 49 late trips, and 416 and 182 excess minutes.
- **What would change it:** a reliable 4xx vehicle mapping that places R-14 trips on the revised
  timetable; or evidence that R-14's export runtimes are wrong. R-14 runs about +7 to +8.5 late in
  *every* runtime band from 35 to 55 min, so it is uniformly slow, not mis-scheduled for one slot.

### 3.2 Worst #3: R-26 over R-37, a close call
- **Rule:** D10. R-26 is late on 42.7% of trips against 40.0% for R-37. Both medians are +4, so the
  median doesn't separate them.
- **Where it breaks:** R-37 passes the rule on 6/7 days to R-26's 5/7, and has one more trip over 10
  minutes (5 vs 4). The share gap is about 3 trips: R-26 needs only 3 fewer late trips (41/103 = 39.8%)
  to fall below R-37. By arithmetic on the counts the difference is not statistically meaningful
  (z ≈ 0.4, p ≈ 0.7). Bootstrap probability of a top-three finish is 0.66 for R-26 and 0.29 for R-37.
- **Why we keep R-26 third:** every other measure is level or favours R-26.
  - **Day by day,** R-26 has the higher late share on 5 of 7 days. R-37 is higher on 1, and 1 is tied.
  - **R-37's extra passing days are fragile.** It passes on Sat and Sun at exactly 33.3% (5 of 15
    trips), so a single trip flips each one.
  - **Magnitude:** R-26's mean is higher (+4.51 vs +4.13), as are its excess minutes (131 vs 125) and
    late minutes (482 vs 474). The p85 and p95 are identical.
  - **Evening peak (16–20):** R-26 is 55.6% late at +7, against 26.9% at +3 for R-37. R-37's worst
    time bands are before 07:00 and after 20:00, with 10–11 trips each.
  - **Other settings:** R-26 stays third at a 3-minute tolerance, at share thresholds from 25% to 35%,
    at median floors from +2 to +4, and under the worst-case data-quality bound.
- **Cost / who pays:** R-26's depot head takes the "worst three" label on a ~3-trip margin. If follow-up
  covered only the top three, R-37's 42 late trips and 125 excess minutes would get no attention, so
  **we recommend joint follow-up on R-26 and R-37.**
- **What would change it:**
  - 3 of R-26's late trips are shown to be data errors.
  - Ridership data shows R-37's late trips carried more riders.
  - A 4xx mapping changes either route's runtimes.
  - "Worst" is redefined as severe (>10 min) lateness. On that measure R-37 is 4.8% and R-26 3.9%.

  The excluded rows cannot cause the switch (§5).

### 3.3 The LATE line: R-31 is LATE, R-17 is NOT LATE (both marginal)

| | R-31 | R-17 |
|---|---|---|
| Valid trips | 112 | 147 |
| Late (>5) | 37 (33.0%) | 41 (27.9%) |
| Median | +4 | +3 |
| Trips >10 min | 0 | 7 |
| Excess minutes | 91 | 130 |
| Days the rule passes | 4/7 | 2/7 |
| Margin to the 30% line | needs ≥34; 3 trips spare, flips at 4 fewer | needs ≥45; 4 trips short |

- **Rule:** D8 as written. The thresholds were not tuned.
- **Where it breaks:** R-17 has more late trips and more excess minutes than R-31, yet it is NOT LATE.
  - The totals are larger because R-17 runs 31% more trips. Per trip, excess lateness is about the
    same: 0.88 min vs 0.81.
  - D8 is built to flag routes that are *routinely* late. R-31 runs a steady +4 with no trip over 10
    minutes. R-17's lateness is lumpy: 52% of trips late on Friday, 14–33% on the other days.
- **Cost / who pays:**
  - A false LATE on R-31 costs its depot head the incentive on a 3-trip margin.
  - A false clear on R-17 leaves its riders' 41 late trips (130 excess minutes) out of the
    chronic-lateness list. They are still counted trip by trip in rider impact (D11), so the route
    verdict alone should never deny a refund.
- **What would change it:**
  - 4 of R-31's late trips are shown to be errors, which would make it NOT LATE.
  - 4 more of R-17's trips are confirmed late, which would make it LATE.
  - The stability check also changes the result: at a 35% share R-31 drops out; at 25%, or a 3-minute
    tolerance, R-17 comes in.

### 3.4 R-35: NOT LATE as a route, but the week's worst single disruption
> **R-35: not late as a route, but the week's worst single disruption.** On Wednesday 5 August every one
> of R-35's 19 trips ran 36–61 minutes late (median +52). That's 880 rider-minutes beyond tolerance,
> more than double R-14's whole week. Wednesday is included in R-35's verdict, not removed. The route is
> NOT LATE because the other six days ran on time (11.5% of trips late, median +1), so this looks like a
> one-day disruption, not a timetable problem. The cause is not established: no dated incident record
> was supplied, and the ops log is undated. R-35 needs an incident review and rider remediation for
> Wednesday, separate from the chronic-lateness list.

| Lens | R-35 |
|---|---|
| Rider experience this week | Bad. Wednesday was the network's worst route-day. Mean +8.05, level with R-14. |
| Systematic route lateness (D8, Wednesday **included**) | NOT LATE: 32/132 late (24.2%), median +2. 1/7 days pass. |
| Incident-driven (D9) | `incident_day_only`: Wed 5 Aug, 19/19 trips late, +36 to +61. |
| Rider impact (D11) | **#1 on the network**: 914 excess minutes, 880 of them on Wednesday. R-14 is #2 with 416. |

- **Rule:** D8 on all valid trips (D9: nothing is removed). Impact is reported under D11.
- **Where it breaks:** on a mean, or on a >10-minute measure, R-35 is #2 on the network. We keep the
  rule because the question for the worst-three is whether a route is chronically late. One day of
  disruption is a different problem with a different fix, and we report it in full here.
- **Cost / who pays:**
  - The riders on those 19 Wednesday trips are owed remediation (880 excess minutes).
  - If the disruption had a cause the depot controlled, the depot avoids a LATE label.
- **What would change it:**
  - A dated incident record showing a recurring, depot-controlled cause.
  - Further disruption days on R-35 in later weeks, which would make it systematic.

  R-35's verdict does not hinge on the 15-minute incident threshold. Its Wednesday median is +52 and its
  next-worst day is +2.

## 4. REC-114 (directive b)
HANDOFF: *"trips on the 4xx vehicle series are measured against the revised timetable in
`schedule_v2.csv` … so the numbers line up with what the review already has."*

**What we did:** REC-114 is applied, automatically, to every trip the data identifies as 4xx. **This
week's export identifies zero such trips**, so the primary result uses the export timetable everywhere.
- DATA_GUIDE defines `vehicle_series` as the *last two digits* of the vehicle class, so the field
  cannot tell 114 from 414.
- In the trips we checked, the series equals the route number: R-14 → "14", R-27 → "27", and all R-26
  trips → "26".
- `data_quality_report` raises this as an explicit data-quality issue.

**What applying it to whole routes would do (counterfactual, not the verdict).** Source: `rec114_impact`.
The re-rankings are arithmetic on its outputs.

| View | R-14 | R-27 | Worst three |
|---|---|---|---|
| **Primary: data-supported, 0 trips revised** | 72.0% late, +8, LATE | 22.4%, +2, NOT LATE | **R-14, R-33, R-26** |
| Counterfactual: revised runtime for every trip from 5 Aug | 43.2%, +4, LATE | 43.4%, +4, LATE | R-33, R-27, R-14 |
| Counterfactual: revised runtime for every trip all week | 31.4%, 0, NOT LATE | 46.9%, +5, LATE | R-33, R-27, R-26 |

**Why the primary result does not apply REC-114 to whole routes:**
- **The directive is defined by vehicle, not by route.** `schedule_v2` lists which routes have a
  revised timetable. It does not say which trips ran on 4xx vehicles.
- **Applying it to every trip contradicts `schedule_v2`.** The file marks R-27 *"no change"*, yet a flat
  45-minute runtime applied to all of R-27 would move it from NOT LATE into the worst three.
- **It would turn late trips into early ones.** Trip **T1-01730** (R-14, Thu 6 Aug) took 48 minutes
  against a 35-minute slot, so it is +13 late. Against a flat 53 minutes it would count as 5 minutes
  early. Across R-14's 35-minute band the average would read 9.8 minutes "early".

**Rule:** apply REC-114 to identifiable 4xx trips only, and always publish the route-wide
counterfactual next to the verdict.
- **Where it breaks:** if the review's existing numbers were computed route-wide, ours will not match
  them. The table above is the reconciliation.
- **Cost / who pays:** route-wide application would relieve R-14's depot (excess minutes 416 → 249 or 166)
  and penalise R-27's (104 → 384 or 447). It would drop 34 to 48 of R-14's late trips out of the
  late count.
- **What would change it:** a vehicle register or a debrief dataset with a reliable 4xx mapping. The
  server then applies the revised runtime to those trips automatically, from the effective date. No
  rule change is needed.

## 5. Data quality and the worst-case bound
| Exclusion | Rows | Evidence it is an artifact |
|---|---|---|
| `actual_arrival` = `…08:60` (D3) | 24 | It's always exactly `08:60`, whatever the departure time. |
| Arrival before scheduled departure (D4) | 18 | Every one is exactly 5 minutes before departure. |
| Missing `tz_offset` (D5) | 0 | The rule exists; nothing triggered it this week. |
| *Converted, kept:* `+00:00` offset (D5) | 1 | T1-02864 (R-23) works out to −2 min after conversion to IST. |

- **The 24 `08:60` trips:** T1-00136, 00352, 00470, 00734, 01372, 02034, 02470, 02585, 02930, 03274,
  03297, 03396, 03414, 03490, 03641, 03669, 03716, 03733, 03822, 04337, 04466, 04646, 04846, 05210.
- **The 18 pre-departure trips:** T1-00361, 00392, 00417, 00673, 01111, 01303, 01419, 01691, 02488,
  02697, 02730, 03142, 03377, 03491, 03636, 04381, 04540, 05264.
- **The most excluded from any one route is 4 (R-27).** Among the LATE routes: R-14 1, R-33 1, R-26 2,
  R-37 0, R-31 0.

**Worst-case bound.** We treated every excluded row first as extremely late, then as on time:

| Route | Excluded | Late share as reported | Range under both extremes |
|---|---|---|---|
| R-14 | 1 | 72.0% | 71.4–72.3% |
| R-33 | 1 | 47.1% | 46.7–47.6% |
| R-26 | 2 | 42.7% | 41.9–43.8% (always above R-37's fixed 40.0%) |
| R-37 / R-31 / R-17 | 0 | 40.0 / 33.0 / 27.9% | fixed |
| R-35 | 1 | 24.2% | at most 24.8% |
| R-27 | 4 | 22.4% | at most 24.5% |

**No verdict and no worst-three position changes under either extreme.** Excluding the rows is
therefore not doing the deciding. Including them would only add invented values.

## 6. Threshold sensitivity
These are what-if runs of `worst_routes` (`what_if: true`). Only the first row is the committed answer.

| Tolerance / share / median floor | LATE routes | Worst three |
|---|---|---|
| **5 / 30% / +3 (committed)** | R-14, R-33, R-26, R-37, R-31 | **R-14, R-33, R-26** |
| 3 / 30% / +3 | ≥ 12 (the five above, plus R-08, R-17, R-40, R-34, R-19, R-07, R-15) | R-14, R-33, R-26 |
| 5 / 25% / +3 | the five + R-17 | R-14, R-33, R-26 |
| 5 / 35% / +3 | R-14, R-33, R-26, R-37 (R-31 drops out) | R-14, R-33, R-26 |
| 5 / 30% / +2 and 5 / 30% / +4 | the five, unchanged | R-14, R-33, R-26 |
| 10 / 30% / +3 | none (the highest share over 10 min is R-14's 23.7%) | by share over 10 min: R-14, R-35, R-33 |

- **The worst three and the core of R-14, R-33, R-26 and R-37 hold across every 3–5-minute variant.**
  Only the two routes we already call marginal move.
- **A 10-minute tolerance asks a different question.** It measures severe lateness, where R-35's
  Wednesday naturally dominates. That is why §3.4 reports R-35 in its own right.

## 7. Why trust this when assumptions can move the ranking?
Not because the ranking can't move, but because we have shown exactly what moves it.

- **The rules were fixed before the ranking was seen,** and the thresholds were not tuned.
- **Every number traces to trip ids** through the same tools a reviewer can drive.
- **Within any reasonable 5-minute-style definition the answer holds.** Tolerance 3–5, share 25–35% and
  median floor +2 to +4 all leave the top two unchanged and R-26 third. Data errors cannot change any
  verdict, even in the worst case.
- **Two things genuinely change the answer, and both are named here:**
  1. **REC-114 applied to every trip on R-14 and R-27.** The data cannot support that, and it
     contradicts R-27's "no change" note. The full reconciliation is in §4.
  2. **Redefining "worst" as severe lateness.** That is a different question, answered by the R-35
     finding.
- **The call we are least sure of is #3, R-26 over R-37.** It is a statistical near-tie. We say so,
  commit to R-26 under the rule, and recommend acting on both.

## 8. Ops log (D6)
The ops log has six entries with a weekday but no date. HANDOFF calls it *last week's* log, while
DATA_GUIDE says it is from this week. It is shown, redacted and by category, through the `ops_log` tool,
and it never adjusts or excuses a trip.

Its Wednesday entry, a western-corridor diversion of about 35 minutes in the morning, does not match
R-35's all-day delay of +36 to +61 minutes. So it cannot be used to explain or excuse R-35.

## Appendix A: all 40 routes (`route_verdicts`, committed defaults)

Sorted by the D10 order. Character applies only to LATE routes, plus `incident_day_only` for NOT LATE routes that had an incident day.

| Route | Verdict | Character | Valid | Late >5 | Share | Median | p95 | Excess min | Days pass | Excluded |
|---|---|---|---|---|---|---|---|---|---|---|
| R-14 | **LATE** | systematic | 118 | 85 | 72.0% | +8 | 16 | 416 | 7/7 | 1 |
| R-33 | **LATE** | systematic | 104 | 49 | 47.1% | +5 | 11 | 182 | 7/7 | 1 |
| R-26 | **LATE** | systematic | 103 | 44 | 42.7% | +4 | 10 | 131 | 5/7 | 2 |
| R-37 | **LATE** | systematic | 105 | 42 | 40.0% | +4 | 10 | 125 | 6/7 | 0 |
| R-31 | **LATE** | systematic | 112 | 37 | 33.0% | +4 | 9 | 91 | 4/7 | 0 |
| R-17 | NOT LATE | — | 147 | 41 | 27.9% | +3 | 10 | 130 | 2/7 | 0 |
| R-35 | NOT LATE | incident_day_only | 132 | 32 | 24.2% | +2 | 54.45 | 914 | 1/7 | 1 |
| R-09 | NOT LATE | — | 146 | 33 | 22.6% | +2 | 9 | 100 | 2/7 | 1 |
| R-34 | NOT LATE | — | 124 | 28 | 22.6% | +3 | 9 | 74 | 2/7 | 2 |
| R-27 | NOT LATE | — | 143 | 32 | 22.4% | +2 | 9.9 | 104 | 0/7 | 4 |
| R-07 | NOT LATE | — | 147 | 32 | 21.8% | +3 | 9 | 91 | 1/7 | 0 |
| R-40 | NOT LATE | — | 152 | 33 | 21.7% | +3 | 9 | 83 | 0/7 | 2 |
| R-15 | NOT LATE | — | 119 | 25 | 21.0% | +3 | 10 | 77 | 1/7 | 0 |
| R-21 | NOT LATE | — | 124 | 26 | 21.0% | +2 | 8 | 55 | 1/7 | 2 |
| R-18 | NOT LATE | — | 154 | 32 | 20.8% | +2 | 8.35 | 86 | 0/7 | 0 |
| R-08 | NOT LATE | — | 126 | 26 | 20.6% | +3 | 8 | 73 | 2/7 | 0 |
| R-03 | NOT LATE | — | 103 | 21 | 20.4% | +2 | 9 | 54 | 1/7 | 2 |
| R-05 | NOT LATE | — | 105 | 20 | 19.1% | +2 | 8.8 | 62 | 0/7 | 0 |
| R-19 | NOT LATE | — | 125 | 23 | 18.4% | +3 | 8.8 | 63 | 1/7 | 1 |
| R-11 | NOT LATE | — | 137 | 23 | 16.8% | +2 | 9 | 84 | 0/7 | 3 |
| R-20 | NOT LATE | — | 145 | 24 | 16.6% | +2 | 9 | 77 | 0/7 | 2 |
| R-38 | NOT LATE | — | 146 | 24 | 16.4% | +1 | 8 | 75 | 0/7 | 1 |
| R-39 | NOT LATE | — | 154 | 25 | 16.2% | +2 | 8.35 | 73 | 0/7 | 0 |
| R-22 | NOT LATE | — | 112 | 18 | 16.1% | +2 | 7.45 | 43 | 1/7 | 0 |
| R-32 | NOT LATE | — | 133 | 21 | 15.8% | +1 | 7 | 49 | 0/7 | 0 |
| R-25 | NOT LATE | — | 139 | 20 | 14.4% | +1 | 8 | 59 | 2/7 | 1 |
| R-02 | NOT LATE | — | 105 | 15 | 14.3% | +2 | 7 | 31 | 0/7 | 0 |
| R-10 | NOT LATE | — | 126 | 18 | 14.3% | +1 | 8 | 51 | 0/7 | 0 |
| R-12 | NOT LATE | — | 112 | 15 | 13.4% | +2 | 7.9 | 47 | 0/7 | 0 |
| R-24 | NOT LATE | — | 146 | 16 | 11.0% | +1 | 6 | 45 | 0/7 | 1 |
| R-28 | NOT LATE | — | 151 | 15 | 9.9% | +1 | 7 | 36 | 0/7 | 3 |
| R-36 | NOT LATE | — | 132 | 13 | 9.8% | +1 | 7 | 30 | 0/7 | 1 |
| R-04 | NOT LATE | — | 144 | 14 | 9.7% | 0 | 6.85 | 27 | 0/7 | 3 |
| R-01 | NOT LATE | — | 153 | 13 | 8.5% | +1 | 8 | 47 | 0/7 | 1 |
| R-30 | NOT LATE | — | 147 | 11 | 7.5% | -1 | 7 | 33 | 0/7 | 0 |
| R-23 | NOT LATE | — | 132 | 8 | 6.1% | 0 | 6 | 15 | 0/7 | 1 |
| R-13 | NOT LATE | — | 133 | 8 | 6.0% | -1 | 6 | 16 | 0/7 | 0 |
| R-06 | NOT LATE | — | 117 | 6 | 5.1% | -2 | 5.2 | 14 | 0/7 | 2 |
| R-16 | NOT LATE | — | 146 | 7 | 4.8% | 0 | 5 | 18 | 0/7 | 1 |
| R-29 | NOT LATE | — | 151 | 6 | 4.0% | -1 | 5 | 20 | 0/7 | 3 |
