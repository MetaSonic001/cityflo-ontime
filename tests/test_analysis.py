"""Checks for the rules in SPEC.md. Run: uv run pytest -q"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ontime import analysis as A
from ontime import server as S
from ontime.redact import redact_text

WEEK = "week-2026-08-03"
RAW = A.REPO / "data" / WEEK / "trips.csv"


def call(tool, **kw):
    out = getattr(S, tool)(**kw)
    json.dumps(out)  # every tool result must be JSON-serialisable
    return out


# ------------------------------------------------------------------ this week's data

def test_exclusions_and_tz():
    t = A.load(WEEK)["trips"]
    counts = t["status"].value_counts().to_dict()
    assert counts["invalid_arrival"] == 24                      # D3: every 08:60 row
    assert counts["arrival_not_after_departure"] == 18          # D4
    assert counts["valid"] == 5250
    row = t[t.trip_id == "T1-02864"].iloc[0]                    # D5: UTC row kept, converted
    assert row.status == "valid" and "tz_corrected" in row["flags"] and row.lateness_min == -2


def test_rec114_not_applied_without_identifiable_4xx():
    t = A.load(WEEK)["trips"]
    assert not t["is_4xx"].any()
    assert (t.loc[t.status == "valid", "runtime_source"] == "export").all()
    dq = call("data_quality_report", dataset=WEEK)
    assert dq["rec114_identifiability"]["issue"].startswith("DATA-QUALITY ISSUE")


def test_independent_recompute_matches_tool():
    """Recompute verdicts and ranking from the raw CSV with a separate, minimal code path."""
    d = pd.read_csv(RAW, dtype=str, keep_default_na=False)
    dep = pd.to_datetime(d.scheduled_departure, format="%Y-%m-%d %H:%M", errors="coerce")
    arr = pd.to_datetime(d.actual_arrival, format="%Y-%m-%d %H:%M", errors="coerce")
    off = d.tz_offset.str.extract(r"([+-])(\d\d):(\d\d)")
    off_min = (off[1].astype(float) * 60 + off[2].astype(float)) * np.where(off[0] == "-", -1, 1)
    arr = arr - pd.to_timedelta(off_min, unit="min") + pd.Timedelta(minutes=330)
    late = (arr - dep).dt.total_seconds() / 60 - d.scheduled_runtime_min.astype(float)
    ok = arr.notna() & (arr > dep)
    g = pd.DataFrame({"route": d.route[ok], "late": late[ok]}).groupby("route").late
    share, med = g.apply(lambda x: (x > 5).mean()), g.median()
    expected_late = sorted(r for r in share.index if share[r] >= 0.30 and med[r] >= 3)
    order = sorted(share.index, key=lambda r: (-share[r], -med[r], r))[:3]

    v = call("route_verdicts", dataset=WEEK)
    w = call("worst_routes", dataset=WEEK)
    assert sorted(v["late_routes"]) == expected_late
    assert [r["route"] for r in w["worst"]] == order


def test_deterministic():
    a = call("worst_routes", dataset=WEEK)
    A._cache.clear()
    b = call("worst_routes", dataset=WEEK)
    assert a == b


def test_ops_log_context_only_and_redacted():
    o = call("ops_log", dataset=WEEK)
    assert "cannot be reliably joined" in o["caveat"]
    comp = [e for e in o["entries"] if e["category"] == "rider_complaint"]
    assert comp and all(e["text"] is None for e in comp)


# ------------------------------------------------------------------ synthetic datasets (debrief readiness)

def _write(root: Path, name: str, rows: list[dict], schedule: str | None = None, ops: str | None = None):
    d = root / name
    d.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(d / "trips.csv", index=False)
    if schedule:
        (d / "schedule_v2.csv").write_text(schedule)
    if ops:
        (d / "ops_log.txt").write_text(ops)


def _trip(i, route, day, late, series="01", rt=40, extra=None):
    dep = pd.Timestamp(f"2026-08-{day:02d} 08:00") + pd.Timedelta(minutes=i)
    arr = dep + pd.Timedelta(minutes=rt + late)
    r = dict(trip_id=f"X-{route}-{day}-{i}", route=route, vehicle_series=series, scheduled_departure=dep.strftime("%Y-%m-%d %H:%M"),
             scheduled_runtime_min=rt, actual_arrival=arr.strftime("%Y-%m-%d %H:%M"), tz_offset="+05:30", scheduled_lateness_min="")
    r.update(extra or {})
    return r


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "DATA_ROOT", tmp_path)
    A._cache.clear()
    yield tmp_path
    A._cache.clear()


def test_rec114_applied_to_identifiable_4xx_from_effective_date(root):
    rows = [_trip(i, "R-14", day, 8, series="414", rt=45) for day in (3, 4, 5, 6) for i in range(10)]
    _write(root, "s", rows, schedule="route,revised_runtime_min,effective_date,note\nR-14,53,2026-08-05,x\n")
    t = A.load("s")["trips"]
    before = t[t.date < "2026-08-05"]
    after = t[t.date >= "2026-08-05"]
    assert (before.runtime_source == "export").all() and (before.lateness_min == 8).all()
    assert (after.runtime_source == "REC-114").all() and (after.lateness_min == 0).all()


def test_incident_days_characterised_not_removed(root):
    rows = [_trip(i, "R-01", day, 1) for day in range(3, 9) for i in range(15)]
    rows += [_trip(i, "R-01", 9, 50) for i in range(15)]         # one terrible day: share 1/7 = 14% -> not late anyway
    rows += [_trip(i, "R-02", day, 4) for day in range(3, 7) for i in range(15)]
    rows += [_trip(i, "R-02", day, 40) for day in (7, 8) for i in range(15)]  # 2 of 6 days -> passes D8 only via incidents
    _write(root, "s", rows)
    v = {r["route"]: r for r in call("route_verdicts", dataset="s")["routes"]}
    # incidents are NOT removed from the primary verdict; they are characterised instead
    assert v["R-02"]["verdict"] == "LATE" and v["R-02"]["character"] == "incident_driven"
    assert v["R-02"]["ex_incident"]["rule_passes"] is False and v["R-02"]["excess_minutes"] > 0
    assert v["R-01"]["verdict"] == "NOT LATE" and v["R-01"]["character"] == "incident_day_only"
    inc = call("incidents", dataset="s")["incident_days"]
    assert {(i["route"], i["date"]) for i in inc} == {("R-01", "2026-08-09"), ("R-02", "2026-08-07"), ("R-02", "2026-08-08")}
    w = call("worst_routes", dataset="s")
    assert any("R-02" in x for x in w["warnings"])


def test_pii_never_leaves_tools(root):
    rows = [_trip(i, "R-01", 3, 6, extra={"rider_phone": "+91 98765 43210", "complaint_text": "driver was rude"})
            for i in range(25)]
    _write(root, "s", rows, ops="Mon 07:00  complaint from 9876543210 about rude driver TKT-881\nTue 08:00  rain, diverted\n")
    blob = json.dumps([call(t, dataset="s") for t in
                       ("data_quality_report", "route_verdicts", "worst_routes", "trips", "ops_log", "incidents",
                        "rider_impact", "rec114_impact")] + [call("route_detail", route="R-01", dataset="s")])
    for bad in ("98765", "9876543210", "rude"):
        assert bad not in blob
    dq = call("data_quality_report", dataset="s")
    assert set(dq["dropped_columns_not_loaded"]) == {"rider_phone", "complaint_text"}
    assert "TKT-881" in json.dumps(call("ops_log", dataset="s"))  # ticket id + category is allowed


def test_dataset_names_are_whitelisted(root):
    _write(root, "s", [_trip(0, "R-01", 3, 0)])
    for bad in ("../s", "..", "C:/Windows", "s/../s", "missing"):
        assert "error" in call("worst_routes", dataset=bad)


def test_redaction_leaves_timestamps_and_ids():
    for s in ("2026-08-03 17:11", "T1-00136", "T1-61234", "2026-08-09 08:60"):
        assert redact_text(s) == s
    for s in ("+91 98765 43210", "9876543210", "022-26541234", "a.b@x.com"):
        assert "[REDACTED]" in redact_text(s)


def test_mixed_and_systematic(root):
    rows = [_trip(i, "R-03", day, 8) for day in range(3, 10) for i in range(15)]                 # late every day
    rows += [_trip(i, "R-04", day, 8) for day in range(3, 9) for i in range(15)]
    rows += [_trip(i, "R-04", 9, 45) for i in range(15)]                                          # late + one incident
    _write(root, "s", rows)
    v = {r["route"]: r for r in call("route_verdicts", dataset="s")["routes"]}
    assert (v["R-03"]["verdict"], v["R-03"]["character"]) == ("LATE", "systematic")
    assert (v["R-04"]["verdict"], v["R-04"]["character"]) == ("LATE", "mixed")
