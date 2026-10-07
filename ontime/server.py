"""MCP server: Cityflo route on-time review. Run: uv run python -m ontime.server  (stdio)."""
from __future__ import annotations

import functools

import pandas as pd
from mcp.server.mcpserver import MCPServer

from . import analysis as A
from .redact import redact

mcp = MCPServer(
    name="cityflo-ontime",
    instructions=(
        "Answers 'which routes were actually late this week, by how much, and which three were worst'. "
        "Start with methodology and data_quality_report, then route_verdicts and worst_routes; drill into "
        "route_detail / trips for evidence. Defaults are the committed decision rules (SPEC.md); parameters "
        "exist only for what-if replay. Datasets are named folders under the configured data root."
    ),
)


def _params(tolerance_min, late_share, min_median, incident_day_median_min) -> A.Params:
    return A.Params(tolerance_min=tolerance_min, late_share=late_share, min_median=min_median,
                    incident_day_median_min=incident_day_median_min)


def tool(fn):
    """Register a tool; every result is redacted at the output boundary (directive (a))."""
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return redact(fn(*args, **kwargs))
        except ValueError as e:
            return {"error": str(e)}
    return mcp.tool()(wrapped)


def _not_default(p: A.Params) -> bool:
    return p != A.Params()


def _trip_record(r) -> dict:
    def ts(x):
        return None if pd.isna(x) else x.strftime("%Y-%m-%d %H:%M")
    return {
        "trip_id": r.trip_id, "route": r.route, "date": r.date, "weekday": r.weekday,
        "vehicle_series": r.vehicle_series, "scheduled_departure": r.scheduled_departure,
        "actual_arrival_raw": r.actual_arrival_raw, "tz_offset": r.tz_offset, "arrival_ist": ts(r.arrival_ist),
        "export_runtime_min": A._r(r.export_runtime_min, 0),
        "applicable_runtime_min": A._r(getattr(r, "applicable_runtime_min", None), 0),
        "runtime_source": getattr(r, "runtime_source", None) if isinstance(getattr(r, "runtime_source", None), str) else None,
        "lateness_min": A._r(getattr(r, "lateness_min", None), 1),
        "status": r.status, "flags": list(r.flags),
    }


@tool
def list_datasets() -> dict:
    """List the datasets available under the configured data root, and which one is the default."""
    return {"datasets": A.list_datasets(), "default": A.default_dataset(),
            "how_to_add": "drop trips.csv (+ optional schedule_v2.csv, ops_log.txt, incidents.csv) into a new folder "
                          "under the data root; tools take its folder name via `dataset`."}


@tool
def methodology() -> dict:
    """The committed decision rules (D1-D11) with their default parameters. Read this first."""
    return {
        "default_params": A.params_dict(A.Params()),
        "lateness (D1)": "arrival (normalised to IST) - (scheduled_departure + applicable runtime), minutes",
        "applicable runtime (D2)": "export scheduled_runtime_min, except REC-114 revised runtime for trips that are "
                                   "IDENTIFIABLY 4xx (vehicle_series/vehicle_class exactly 4NN) on/after effective_date",
        "exclusions (D3,D4)": "unparseable timestamps (e.g. 08:60), invalid runtime, invalid OR MISSING tz_offset "
                              "([impl] conservative: assuming IST would be an unsupported repair), arrival not after "
                              "scheduled departure. Each is reported by trip id; none is repaired.",
        "timezone (D5)": "arrival converted from its stamped offset to +05:30 and kept",
        "late trip (D7)": "lateness > tolerance_min (5)",
        "route verdict (D8)": "LATE iff late_share >= 0.30 AND median >= +3, on all valid trips",
        "incident days (D9)": "[impl] route-day with median lateness > 15 min (an analytical implementation choice, "
                              "not an assignment requirement). Incidents are NEVER removed from the D8 verdict; instead "
                              "each LATE route is characterised: systematic (no incident days), mixed (D8 still passes "
                              "without incident days), incident_driven (D8 passes only because of incident days). NOT "
                              "LATE routes with an incident day are marked incident_day_only. Incident trips stay in "
                              "rider-impact totals",
        "worst-N (D10)": "sort by late_share desc, median desc, route code asc; stability from a seeded day-level "
                         "bootstrap (1000 draws)",
        "rider impact (D11)": "trips_late and excess_minutes = sum(max(0, lateness-5)), reported separately",
        "ops log (D6)": A.OPS_CAVEAT,
    }


@tool
def data_quality_report(dataset: str | None = None) -> dict:
    """Every excluded or flagged row by rule and trip id, dropped columns, and REC-114 4xx identifiability."""
    ds = A.load(dataset)
    t = ds["trips"]
    excl = t[t["status"] != "valid"]
    flagged = t[t["flags"].map(len) > 0]
    by_route = excl.groupby("route").size().sort_values(ascending=False)
    series_formats = sorted({("3-digit" if len(s.strip()) == 3 else f"{len(s.strip())}-digit")
                             for s in t["vehicle_series"]})
    return {
        "dataset": ds["name"], "rows": len(t), "valid": int((t["status"] == "valid").sum()),
        "excluded_by_reason": excl["status"].value_counts().to_dict(),
        "excluded_trips": [{"trip_id": r.trip_id, "route": r.route, "reason": r.status,
                            "scheduled_departure": r.scheduled_departure, "actual_arrival_raw": r.actual_arrival_raw,
                            "tz_offset": r.tz_offset} for r in excl.itertuples()],
        "excluded_per_route_max": {"route": by_route.index[0], "rows": int(by_route.iloc[0])} if len(by_route) else None,
        "flagged_trips": [{"trip_id": r.trip_id, "route": r.route, "flags": list(r.flags),
                           "lateness_min": A._r(r.lateness_min, 1)} for r in flagged.itertuples()],
        "dropped_columns_not_loaded": ds["dropped_columns"],
        "rec114_identifiability": {
            "vehicle_series_formats_seen": series_formats,
            "identifiable_4xx_trips": int(t["is_4xx"].sum()),
            "routes_in_schedule_v2": sorted(ds["schedule"]),
            "issue": None if t["is_4xx"].any() else
            "DATA-QUALITY ISSUE: no trip can be identified as 4xx (vehicle_series holds only the last two digits), "
            "so REC-114 is applied to 0 trips in the primary verdict. See rec114_impact for the counterfactual.",
        },
    }


@tool
def route_verdicts(dataset: str | None = None, tolerance_min: float = 5.0, late_share: float = 0.30,
                   min_median: float = 3.0, incident_day_median_min: float = 15.0) -> dict:
    """One verdict per route (D8, all valid trips) plus its D9 character with frequency, magnitude (median/p85/p95), day consistency,
    incident days and exclusion counts. Non-default parameters are a what-if, not the committed answer."""
    p = _params(tolerance_min, late_share, min_median, incident_day_median_min)
    ds = A.load(dataset)
    rows = sorted(A.route_table(ds, p), key=A.rank_key)
    late = [r["route"] for r in rows if r["verdict"] == "LATE"]
    # borderline: within 5 percentage points of the share threshold or 1 min of the median threshold
    border = [r["route"] for r in rows if r["n_valid"] and (abs(r["late_share"] - p.late_share) <= 0.05
                                                           or abs(r["median"] - p.min_median) <= 1.0)
              and (r["late_share"] >= p.late_share - 0.05 and r["median"] >= p.min_median - 1.0)]
    return {"dataset": ds["name"], "params": A.params_dict(p), "what_if": _not_default(p),
            "late_routes": late, "borderline_routes": border,
            "character_counts": {c: [r["route"] for r in rows if r["character"] == c]
                                 for c in ("systematic", "mixed", "incident_driven", "incident_day_only")},
            "routes": rows}


@tool
def worst_routes(dataset: str | None = None, n: int = 3, tolerance_min: float = 5.0, late_share: float = 0.30,
                 min_median: float = 3.0, incident_day_median_min: float = 15.0) -> dict:
    """Ranked worst-N (D10): late_share desc, median desc, route asc. Includes day-bootstrap rank stability
    (P in top-N, P same rank) and the next routes below the cut so the boundary can be challenged."""
    p = _params(tolerance_min, late_share, min_median, incident_day_median_min)
    ds = A.load(dataset)
    res = A.ranking(ds, p, n)
    cols = ["rank", "route", "verdict", "character", "late_share", "trips_late", "n_valid", "median", "p85",
            "p95", "mean", "trips_gt10", "days_rule_passes", "service_days", "excess_minutes", "p_in_top_n",
            "p_same_rank"]
    return {"dataset": ds["name"], "params": A.params_dict(p), "what_if": _not_default(p),
            "worst": [{k: r.get(k) for k in cols} for r in res["top"]],
            "next_below_cut": [{k: r.get(k) for k in cols} for r in res["ordered"][n:n + 4]],
            "warnings": res["warnings"]}


@tool
def route_detail(route: str, dataset: str | None = None) -> dict:
    """Everything behind one route's call: metrics, verdict with/without incident days, rank and stability,
    per-day breakdown, lateness by scheduled-runtime band, exclusions and REC-114 status."""
    p = A.Params()
    ds = A.load(dataset)
    t = ds["trips"]
    if route not in set(t["route"]):
        return {"error": f"unknown route {route!r}"}
    rank = next(r for r in A.ranking(ds, p, 3)["ordered"] if r["route"] == route)
    v = A.valid(ds)
    rv = v[v["route"] == route]
    inc = set(A.incident_days(v, p).query("route == @route")["date"])
    per_day = []
    for d, g in rv.groupby("date"):
        m = A.metrics(g["lateness_min"].values, p)
        per_day.append({"date": d, "weekday": g["weekday"].iloc[0], "n": m["n_valid"], "late_share": m["late_share"],
                        "median": m["median"], "max": A._r(g["lateness_min"].max(), 1),
                        "rule_passes": m["rule_passes"], "incident_day": d in inc})
    bands = [{"export_runtime_min": A._r(k, 0), "n": len(g), "median_lateness": A._r(g["lateness_min"].median(), 1)}
             for k, g in rv.groupby("export_runtime_min")]
    hours = [{"hour_band": b, **{k: A.metrics(g["lateness_min"].values, p)[k] for k in ("n_valid", "late_share", "median")}}
             for b, g in rv.groupby(pd.cut(rv["hour"], [0, 7, 10, 16, 20, 24], right=False,
                                           labels=["<07", "07-10 AM peak", "10-16", "16-20 PM peak", "20+"]),
                                    observed=True)]
    excl = t[(t["route"] == route) & (t["status"] != "valid")]
    return {"dataset": ds["name"], "route": route, **{k: rank.get(k) for k in rank},
            "per_day": per_day, "by_export_runtime_band": bands, "by_hour_band": hours,
            "excluded_trips": [{"trip_id": r.trip_id, "reason": r.status} for r in excl.itertuples()],
            "in_schedule_v2": route in ds["schedule"],
            "trips_using_rec114_runtime": int((rv["runtime_source"] == "REC-114").sum())}


@tool
def trips(route: str | None = None, date: str | None = None, status: str | None = None,
          min_lateness: float | None = None, flag: str | None = None, dataset: str | None = None,
          limit: int = 100) -> dict:
    """Trip-level drill-down. Filters: route, date (YYYY-MM-DD), status ('valid', 'excluded', or a reason code),
    min_lateness (minutes), flag (e.g. tz_corrected). Sorted by scheduled departure. Shows the raw and normalised
    timestamps and the runtime actually used, so any number can be recomputed by hand."""
    ds = A.load(dataset)
    t = ds["trips"]
    if route:
        t = t[t["route"] == route]
    if date:
        t = t[t["date"] == date]
    if status == "excluded":
        t = t[t["status"] != "valid"]
    elif status:
        t = t[t["status"] == status]
    if min_lateness is not None:
        t = t[t["lateness_min"] >= min_lateness]
    if flag:
        t = t[t["flags"].map(lambda f: flag in f)]
    t = t.sort_values(["dep", "trip_id"])
    limit = max(1, min(int(limit), 1000))
    return {"dataset": ds["name"], "matched": len(t), "returned": min(len(t), limit),
            "trips": [_trip_record(r) for r in t.head(limit).itertuples()]}


@tool
def incidents(dataset: str | None = None, incident_day_median_min: float = 15.0) -> dict:
    """Incident route-days (median lateness > threshold) with affected trips and rider impact (D9/D11), plus any
    dated incident context from incidents.csv. Ops-log entries are NOT joined (undated); see ops_log."""
    p = A.Params(incident_day_median_min=incident_day_median_min)
    ds = A.load(dataset)
    v = A.valid(ds)
    out = []
    for r in A.incident_days(v, p).itertuples():
        g = v[(v["route"] == r.route) & (v["date"] == r.date)]
        m = A.metrics(g["lateness_min"].values, p)
        ctx = [i for i in ds["incidents"] if i.get("date") == r.date and i.get("route") in (r.route, "ALL")]
        out.append({"route": r.route, "date": r.date, "weekday": g["weekday"].iloc[0], "n": m["n_valid"],
                    "trips_late": m["trips_late"], "median": m["median"], "min": A._r(g["lateness_min"].min(), 1),
                    "max": A._r(g["lateness_min"].max(), 1), "excess_minutes": m["excess_minutes"],
                    "trip_ids": g.sort_values("dep")["trip_id"].tolist(), "dated_incident_context": ctx})
    return {"dataset": ds["name"], "threshold_median_min": p.incident_day_median_min, "incident_days": out,
            "dated_incidents_file_present": bool(ds["incidents"])}


@tool
def rider_impact(dataset: str | None = None, top: int = 10) -> dict:
    """Rider-impact view (D11), kept separate from the systematic ranking: trips >5 late, excess minutes beyond
    tolerance, and how much of each route's impact sits on incident days."""
    p = A.Params()
    ds = A.load(dataset)
    v = A.valid(ds)
    inc = set(zip(*[A.incident_days(v, p)[c] for c in ("route", "date")])) if len(v) else set()
    rows = []
    for r, g in v.groupby("route"):
        m = A.metrics(g["lateness_min"].values, p)
        on_inc = g[[(r, d) in inc for d in g["date"]]]
        mi = A.metrics(on_inc["lateness_min"].values, p) if len(on_inc) else {"trips_late": 0, "excess_minutes": 0.0}
        rows.append({"route": r, "trips_late": m["trips_late"], "excess_minutes": m["excess_minutes"],
                     "late_minutes": m["late_minutes"], "trips_late_on_incident_days": mi["trips_late"],
                     "excess_minutes_on_incident_days": mi["excess_minutes"]})
    rows.sort(key=lambda x: (-x["excess_minutes"], x["route"]))
    return {"dataset": ds["name"], "note": "Supporting impact metric, not the worst-N ranking (D10/D11).",
            "network_trips_late": int(sum(x["trips_late"] for x in rows)), "routes": rows[:max(1, top)]}


@tool
def rec114_impact(dataset: str | None = None) -> dict:
    """REC-114 shown separately (D2): identifiable 4xx trips, the primary view, and counterfactual views as if the
    whole route ran on the revised flat runtime (from effective date / all week), plus lateness by runtime band."""
    ds = A.load(dataset)
    return {"dataset": ds["name"], "routes": A.rec114_impact(ds, A.Params()),
            "primary_verdict_policy": "revised runtime applied only to identifiable 4xx trips; counterfactual views "
                                      "never feed the verdict"}


@tool
def ops_log(dataset: str | None = None) -> dict:
    """Ops-log entries as weekday/time/category (D6). Complaint lines are category-only; all text is redacted."""
    ds = A.load(dataset)
    return {"dataset": ds["name"], "caveat": A.OPS_CAVEAT, "entries": ds["ops_log"]}


def main():
    mcp.run("stdio")


if __name__ == "__main__":
    main()
