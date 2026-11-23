"""Utilization review board and leadership metrics, computed from the live chart state."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, replace
from datetime import datetime
from statistics import median

import duckdb

from wardsight.engine.chart import load_charts
from wardsight.engine.drg import coded_diagnoses, group
from wardsight.engine.drg_table import facts
from wardsight.engine.gaps import find_flags
from wardsight.engine.ur import case_mix, codes_if_resolved, review

SPLIT = "dev"
STALE_AFTER_HOURS = 48  # a query unanswered this long needs a follow-up before the patient leaves
SENT_ACTIONS = ("approved_and_sent", "edited_approved_and_sent")


def _admits(con: duckdb.DuckDBPyConnection) -> dict:
    return dict(con.execute("SELECT encounter_id, admit_ts FROM ehr.encounters WHERE split = ?",
                            [SPLIT]).fetchall())


def ur_board(con: duckdb.DuckDBPyConnection) -> dict:
    admits = _admits(con)
    rows = [review(c, admits[c.encounter_id], find_flags(c)) for c in load_charts(con, SPLIT)]
    order = {"long_stay": 0, "observation_review": 1, "explained_by_gap": 2, "no_benchmark": 3, "ok": 4}
    rows.sort(key=lambda r: (order[r.status], -(r.los_days - (r.gmlos or 0))))
    return {"counts": dict(Counter(r.status for r in rows)), "rows": [asdict(r) for r in rows]}


def response_times(con: duckdb.DuckDBPyConnection, now: datetime | None = None) -> dict:
    """How fast physicians answer, which sent queries have gone stale, and agreement by physician.

    Times come from the append-only audit log, counted from the last demo reset.
    """
    now = now or datetime.now()
    since = con.execute("SELECT max(ts) FROM ops.audit WHERE action = 'reset'").fetchone()[0] or datetime.min
    sent: dict[str, datetime] = {}
    answered: dict[str, datetime] = {}
    for ts, action, query_id in con.execute(
            "SELECT ts, action, query_id FROM ops.audit WHERE ts >= ? ORDER BY ts", [since]).fetchall():
        if action in SENT_ACTIONS:
            sent.setdefault(query_id, ts)
        elif action == "answered":
            answered.setdefault(query_id, ts)
    waits = [(answered[q] - sent[q]).total_seconds() / 3600 for q in answered if q in sent]
    open_rows = con.execute("""SELECT query_id, encounter_id FROM ops.queries
                               WHERE split = ? AND status = 'sent'""", [SPLIT]).fetchall()
    stale = sorted(({"query_id": q, "encounter_id": e, "hours_waiting": round((now - sent[q]).total_seconds() / 3600, 1)}
                    for q, e in open_rows if q in sent and (now - sent[q]).total_seconds() / 3600 > STALE_AFTER_HOURS),
                   key=lambda r: -r["hours_waiting"])
    physicians: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for who, status in con.execute("""SELECT answered_by, status FROM ops.queries
                                      WHERE split = ? AND status IN ('answered', 'resolved')""", [SPLIT]).fetchall():
        physicians[who][0] += 1
        physicians[who][1] += status == "resolved"
    return {
        "median_hours_to_answer": round(median(waits), 1) if waits else None,
        "stale_after_hours": STALE_AFTER_HOURS,
        "stale": stale,
        "by_physician": [{"physician": who, "answered": n, "agreed": agreed, "agreement_rate": round(agreed / n, 3)}
                         for who, (n, agreed) in sorted(physicians.items())],
    }


def leadership(con: duckdb.DuckDBPyConnection) -> dict:
    charts = load_charts(con, SPLIT)
    first, current, potential = [], [], []
    for chart in charts:
        original = replace(chart, notes=tuple(n for n in chart.notes if n.note_type != "addendum"))
        first.append(group(original, coded_diagnoses(original)).drg)
        current.append(group(chart, coded_diagnoses(chart)).drg)
        potential.append(group(chart, codes_if_resolved(chart, find_flags(chart))).drg)

    queries = con.execute("SELECT condition, kind, status, drg_before, drg_after FROM ops.queries "
                          "WHERE split = ?", [SPLIT]).fetchall()
    statuses = Counter(q[2] for q in queries)
    by_condition: dict[str, dict] = defaultdict(lambda: {"gaps": 0, "missing": 0, "unsupported": 0,
                                                         "resolved": 0, "weight_change": 0.0})
    for condition, kind, status, before, after in queries:
        row = by_condition[condition]
        row["gaps"] += 1
        row["missing" if kind == "missing_dx" else "unsupported"] += 1
        if status == "resolved":
            row["resolved"] += 1
            if (b := facts(before or 0)) and (a := facts(after or 0)):
                row["weight_change"] = round(row["weight_change"] + a.weight - b.weight, 4)

    answered = statuses["answered"] + statuses["resolved"]
    sent = answered + statuses["sent"]
    return {
        "case_mix": asdict(case_mix(first, current, potential)),
        "queries": {"drafted": len(queries), "sent": sent, "answered": answered,
                    "resolved": statuses["resolved"], "pending_review": statuses["pending_review"],
                    "response_rate": round(answered / sent, 3) if sent else None,
                    "agreement_rate": round(statuses["resolved"] / answered, 3) if answered else None},
        "by_condition": [{"condition": k, **v} for k, v in sorted(by_condition.items())],
        "responses": response_times(con),
        "weights_source": "CMS IPPS FY2027 Table 5 (v44), via quickintell.com; verify before real use",
    }
