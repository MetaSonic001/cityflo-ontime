"""Deterministic lateness analysis. Every rule here is specified in SPEC.md (section numbers in comments)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.environ.get("ONTIME_DATA_ROOT", REPO / "data")).resolve()

TRIP_COLUMNS = ["trip_id", "route", "vehicle_series", "vehicle_class", "scheduled_departure",
                "scheduled_runtime_min", "actual_arrival", "tz_offset"]
TS_FORMATS = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
IST = timedelta(hours=5, minutes=30)
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
BOOTSTRAP_SEED = 114
BOOTSTRAP_DRAWS = 1000


@dataclass(frozen=True)
class Params:
    tolerance_min: float = 5.0            # D7
    late_share: float = 0.30              # D8
    min_median: float = 3.0               # D8
    incident_day_median_min: float = 15.0  # D9 [impl]
    min_trips: int = 20                   # [impl]
    extreme_abs_min: float = 120.0        # flag only [impl]


# ---------------------------------------------------------------- datasets (controlled location, no paths)

def list_datasets() -> list[str]:
    if not DATA_ROOT.is_dir():
        return []
    return sorted(p.name for p in DATA_ROOT.iterdir() if p.is_dir() and (p / "trips.csv").is_file())


def default_dataset() -> str:
    env = os.environ.get("ONTIME_DATASET")
    names = list_datasets()
    if env and env in names:
        return env
    if not names:
        raise ValueError(f"no datasets under {DATA_ROOT.name}/ (each needs a trips.csv)")
    return names[-1]


def _resolve(name: str | None) -> Path:
    name = name or default_dataset()
    if name not in list_datasets():  # whitelist: only existing sub-folders of the data root
        raise ValueError(f"unknown dataset {name!r}; available: {list_datasets()}")
    return DATA_ROOT / name


# ---------------------------------------------------------------- parsing (SPEC §1, §2)

def _parse_ts(s: str):
    s = (s or "").strip()
    for f in TS_FORMATS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def _parse_offset(s: str):
    m = re.fullmatch(r"([+-])(\d{2}):(\d{2})", (s or "").strip())
    if not m or int(m.group(3)) >= 60:
        return None
    sign = 1 if m.group(1) == "+" else -1
    return sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))


def _is_4xx(series: str, vclass: str) -> bool:
    return any(re.fullmatch(r"4\d\d", (v or "").strip()) for v in (vclass, series))


def _load_schedule(path: Path) -> dict:
    if not path.is_file():
        return {}
    s = pd.read_csv(path, dtype=str, keep_default_na=False)
    out = {}
    for _, r in s.iterrows():
        try:
            out[r["route"].strip()] = {"revised_runtime_min": float(r["revised_runtime_min"]),
                                       "effective_date": datetime.strptime(r["effective_date"].strip(), "%Y-%m-%d").date(),
                                       "note": r.get("note", "")}
        except (ValueError, KeyError):
            continue
    return out


_cache: dict = {}


def load(name: str | None = None) -> dict:
    folder = _resolve(name)
    key = (folder.name, tuple((f.name, f.stat().st_mtime) for f in sorted(folder.iterdir()) if f.is_file()))
    if key in _cache:
        return _cache[key]

    raw = pd.read_csv(folder / "trips.csv", dtype=str, keep_default_na=False)
    dropped = [c for c in raw.columns if c not in TRIP_COLUMNS + ["scheduled_lateness_min"]]
    for c in TRIP_COLUMNS:
        if c not in raw.columns:
            raw[c] = ""
    raw = raw[TRIP_COLUMNS]
    schedule = _load_schedule(folder / "schedule_v2.csv")

    rows = []
    for r in raw.itertuples(index=False):
        dep, arr = _parse_ts(r.scheduled_departure), _parse_ts(r.actual_arrival)
        off = _parse_offset(r.tz_offset)
        try:
            rt = float(r.scheduled_runtime_min)
            rt = rt if rt > 0 else None
        except ValueError:
            rt = None
        is4 = _is_4xx(r.vehicle_series, r.vehicle_class)
        route = r.route.strip()
        rec = dict(trip_id=r.trip_id, route=route, vehicle_series=r.vehicle_series, vehicle_class=r.vehicle_class,
                   scheduled_departure=r.scheduled_departure, actual_arrival_raw=r.actual_arrival,
                   tz_offset=r.tz_offset, export_runtime_min=rt, is_4xx=is4, flags=[])
        if dep is None:
            status = "invalid_departure"
        elif arr is None:
            status = "invalid_arrival"
        elif rt is None:
            status = "invalid_runtime"
        elif off is None:
            status = "invalid_tz"
        else:
            arr_ist = arr - off + IST
            if off != IST:
                rec["flags"].append("tz_corrected")
            rec["arrival_ist"] = arr_ist
            status = "arrival_not_after_departure" if arr_ist <= dep else "valid"
            # applicable runtime (D2): revised only where the trip is identifiably 4xx
            sch = schedule.get(route)
            if is4 and sch and dep.date() >= sch["effective_date"]:
                rec["applicable_runtime_min"], rec["runtime_source"] = sch["revised_runtime_min"], "REC-114"
            else:
                rec["applicable_runtime_min"], rec["runtime_source"] = rt, "export"
            rec["lateness_min"] = (arr_ist - dep).total_seconds() / 60 - rec["applicable_runtime_min"]  # D1
        rec["status"] = status
        rec["dep"] = dep
        rows.append(rec)

    df = pd.DataFrame(rows)
    df["dep"] = pd.to_datetime(df["dep"])
    df["arrival_ist"] = pd.to_datetime(df["arrival_ist"]) if "arrival_ist" in df else pd.NaT
    df["date"] = df["dep"].dt.strftime("%Y-%m-%d")
    df["weekday"] = df["dep"].dt.weekday.map(lambda i: WEEKDAYS[int(i)] if pd.notna(i) else None)
    df["hour"] = df["dep"].dt.hour
    # non-excluding flags
    dup_id = df["trip_id"].duplicated(keep=False)
    dup_rec = df.drop(columns=["trip_id", "flags"]).astype(str).duplicated(keep=False)
    for i in df.index[dup_id]:
        df.at[i, "flags"] = df.at[i, "flags"] + ["duplicate_trip_id"]
    for i in df.index[dup_rec]:
        df.at[i, "flags"] = df.at[i, "flags"] + ["duplicate_record"]
    for i in df.index[(df["status"] == "valid") & (df["lateness_min"].abs() > Params.extreme_abs_min)]:
        df.at[i, "flags"] = df.at[i, "flags"] + ["extreme_lateness"]

    out = {"name": folder.name, "trips": df, "schedule": schedule, "dropped_columns": dropped,
           "ops_log": _parse_ops_log(folder / "ops_log.txt"), "incidents": _load_incidents(folder / "incidents.csv")}
    _cache.clear()
    _cache[key] = out
    return out


def valid(ds: dict) -> pd.DataFrame:
    t = ds["trips"]
    return t[t["status"] == "valid"]


# ---------------------------------------------------------------- metrics (SPEC §3, §4, §7)

def _r(x, nd=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), nd)


def metrics(late: np.ndarray, p: Params) -> dict:
    late = np.asarray(late, dtype=float)
    n = len(late)
    if n == 0:
        return {"n_valid": 0}
    is_late = late > p.tolerance_min
    share = is_late.mean()
    med = float(np.median(late))
    return {
        "n_valid": n,
        "trips_late": int(is_late.sum()),
        "late_share": _r(share, 4),
        "median": _r(med),
        "mean": _r(late.mean()),
        "p85": _r(np.percentile(late, 85)),
        "p95": _r(np.percentile(late, 95)),
        "trips_gt10": int((late > 10).sum()),
        "excess_minutes": _r(np.clip(late - p.tolerance_min, 0, None).sum(), 1),
        "late_minutes": _r(np.clip(late, 0, None).sum(), 1),
        "rule_passes": bool(share >= p.late_share and med >= p.min_median),
    }


def incident_days(v: pd.DataFrame, p: Params) -> pd.DataFrame:
    g = v.groupby(["route", "date"])["lateness_min"].agg(["median", "size"]).reset_index()
    return g[g["median"] > p.incident_day_median_min]


def route_table(ds: dict, p: Params) -> list[dict]:
    v = valid(ds)
    inc = incident_days(v, p)
    inc_keys = set(zip(inc["route"], inc["date"]))
    all_routes = sorted(ds["trips"]["route"].unique())
    out = []
    for route in all_routes:
        rv = v[v["route"] == route]
        m = metrics(rv["lateness_min"].values, p)
        days = sorted(rv["date"].unique())
        rinc = [d for d in days if (route, d) in inc_keys]
        ex = rv[~rv["date"].isin(rinc)]
        m_ex = metrics(ex["lateness_min"].values, p) if rinc else m
        per_day = [metrics(rv[rv["date"] == d]["lateness_min"].values, p)["rule_passes"] for d in days]
        excluded = int(((ds["trips"]["route"] == route) & (ds["trips"]["status"] != "valid")).sum())
        # D8: the primary verdict is the rule on ALL valid trips; incidents are never removed from it.
        # D9 characterisation (separate field) [impl]: systematic | mixed | incident_driven for LATE routes;
        # incident_day_only for NOT LATE routes that still had an incident day; None otherwise.
        if m["n_valid"] < p.min_trips:
            verdict, character = "INSUFFICIENT DATA", None
        elif m["rule_passes"]:
            verdict = "LATE"
            character = ("systematic" if not rinc else
                         "mixed" if m_ex.get("rule_passes", False) else "incident_driven")
        else:
            verdict, character = "NOT LATE", ("incident_day_only" if rinc else None)
        out.append({"route": route, "verdict": verdict, "character": character,
                    "incident_driven": character == "incident_driven", **m,
                    "excluded_rows": excluded, "service_days": len(days),
                    "days_rule_passes": int(sum(per_day)), "incident_days": rinc,
                    "ex_incident": None if not rinc else {k: m_ex.get(k) for k in
                                                         ("n_valid", "late_share", "median", "rule_passes")}})
    return out


def rank_key(r: dict):
    return (-r["late_share"], -r["median"], r["route"])  # D10


def ranking(ds: dict, p: Params, n: int = 3) -> dict:
    table = [r for r in route_table(ds, p) if r["verdict"] != "INSUFFICIENT DATA"]
    ordered = sorted(table, key=rank_key)
    stab = _stability(ds, p, n, [r["route"] for r in ordered])
    for i, r in enumerate(ordered, 1):
        r["rank"] = i
        r.update(stab.get(r["route"], {}))
    warnings = [f"{r['route']} is ranked #{r['rank']} with verdict {r['verdict']}"
                + (f", character {r['character']}" if r["character"] else "")
                for r in ordered[:n] if r["verdict"] != "LATE" or r["character"] in ("incident_driven", "mixed")]
    return {"ordered": ordered, "top": ordered[:n], "warnings": warnings}


def _stability(ds: dict, p: Params, n: int, routes: list[str]) -> dict:
    """Day-level bootstrap (SPEC §5): resample service days with replacement, re-rank with the same rule."""
    v = valid(ds)
    v = v[v["route"].isin(routes)]
    days = sorted(v["date"].unique())
    if len(days) < 2:
        return {}
    arrays = {(r, d): g["lateness_min"].values for (r, d), g in v.groupby(["route", "date"])}
    base_rank = {r: i for i, r in enumerate(routes, 1)}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    in_top = dict.fromkeys(routes, 0)
    same_rank = dict.fromkeys(routes, 0)
    for _ in range(BOOTSTRAP_DRAWS):
        pick = rng.choice(days, size=len(days), replace=True)
        rows = []
        for r in routes:
            parts = [arrays[(r, d)] for d in pick if (r, d) in arrays]
            if not parts:
                continue
            a = np.concatenate(parts)
            rows.append((-(a > p.tolerance_min).mean(), -np.median(a), r))
        rows.sort()
        for i, (_, _, r) in enumerate(rows, 1):
            if i <= n:
                in_top[r] += 1
            if i == base_rank[r]:
                same_rank[r] += 1
    return {r: {"p_in_top_n": round(in_top[r] / BOOTSTRAP_DRAWS, 3),
                "p_same_rank": round(same_rank[r] / BOOTSTRAP_DRAWS, 3)} for r in routes}


# ---------------------------------------------------------------- REC-114 (SPEC §6)

def rec114_impact(ds: dict, p: Params) -> list[dict]:
    v = valid(ds)
    out = []
    for route, sch in sorted(ds["schedule"].items()):
        rv = v[v["route"] == route]
        if rv.empty:
            out.append({"route": route, "note": "route not present in trips"})
            continue
        actual_rt = (rv["arrival_ist"] - rv["dep"]).dt.total_seconds() / 60
        on_or_after = rv["dep"].dt.date >= sch["effective_date"]
        export_late = actual_rt - rv["export_runtime_min"]
        from_eff = np.where(on_or_after, actual_rt - sch["revised_runtime_min"], export_late)
        all_week = actual_rt - sch["revised_runtime_min"]
        bands = (rv.assign(actual_rt=actual_rt, export_late=export_late)
                 .groupby("export_runtime_min").agg(n=("trip_id", "size"), mean_actual_runtime=("actual_rt", "mean"),
                                                    median_lateness_vs_export=("export_late", "median")))
        out.append({
            "route": route, "revised_runtime_min": sch["revised_runtime_min"],
            "effective_date": sch["effective_date"].isoformat(), "schedule_note": sch["note"],
            "identifiable_4xx_trips": int(rv["is_4xx"].sum()),
            "trips_using_revised_runtime_in_primary": int((rv["runtime_source"] == "REC-114").sum()),
            "primary_view": metrics(rv["lateness_min"].values, p),
            "export_timetable_view": metrics(export_late.values, p),
            "counterfactual_revised_from_effective_date": metrics(from_eff, p),
            "counterfactual_revised_all_week": metrics(all_week.values, p),
            "by_export_runtime_band": [{"export_runtime_min": _r(k, 0), "n": int(b.n),
                                        "mean_actual_runtime": _r(b.mean_actual_runtime, 1),
                                        "median_lateness_vs_export": _r(b.median_lateness_vs_export, 1),
                                        "lateness_vs_flat_revised": _r(b.mean_actual_runtime - sch["revised_runtime_min"], 1)}
                                       for k, b in bands.iterrows()],
        })
    return out


# ---------------------------------------------------------------- ops log / incidents (SPEC §8)

_CATEGORIES = [
    ("rider_complaint", r"complain|complaint|refund|rude|feedback"),
    ("weather_or_diversion", r"waterlog|rain|flood|divert|diversion|road closed"),
    ("crowding_or_event", r"crowd|festival|surge|rally|event"),
    ("staffing", r"no-show|no show|driver|absent|covered"),
    ("vehicle_swap_or_fault", r"swap|breakdown|fault|ac |a/c|tyre|engine"),
    ("normal", r"normal|good day|all ok"),
]
OPS_CAVEAT = ("Context only (D6): entries carry a weekday but no date, so they cannot be reliably joined to "
              "route-days (for the week-2026-08-03 bundle, HANDOFF calls it LAST week's log, while DATA_GUIDE says "
              "'from the week'). Never used to exclude, adjust or excuse a trip; dated incidents belong in incidents.csv.")


def _parse_ops_log(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        m = re.match(r"^\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\s+(\d{1,2}:\d{2})\s+(.*)$", line)
        wd, tm, text = (m.group(1), m.group(2), m.group(3)) if m else (None, None, line.strip())
        low = text.lower() + " "
        cat = next((c for c, rx in _CATEGORIES if re.search(rx, low)), "other")
        ticket = re.search(r"\b(?:TKT|TICKET|INC)[-#]?\d+\b", text, re.I)
        out.append({"line": i, "weekday": wd, "time": tm, "category": cat,
                    "ticket_id": ticket.group(0) if ticket else None,
                    # complaint text is never returned verbatim (directive (a))
                    "text": None if cat == "rider_complaint" else text})
    return out


def _load_incidents(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    s = pd.read_csv(path, dtype=str, keep_default_na=False)
    keep = [c for c in ("date", "route", "category", "ticket_id") if c in s.columns]
    return s[keep].to_dict("records")  # free-text columns are deliberately not loaded


def params_dict(p: Params) -> dict:
    return asdict(p)
