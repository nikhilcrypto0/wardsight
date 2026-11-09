"""Utilization review board and leadership metrics, computed from the live chart state."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, replace

import duckdb

from wardsight.engine.chart import load_charts
from wardsight.engine.drg import coded_diagnoses, group
from wardsight.engine.drg_table import facts
from wardsight.engine.gaps import find_flags
from wardsight.engine.ur import case_mix, codes_if_resolved, review

SPLIT = "dev"


def _admits(con: duckdb.DuckDBPyConnection) -> dict:
    return dict(con.execute("SELECT encounter_id, admit_ts FROM ehr.encounters WHERE split = ?",
                            [SPLIT]).fetchall())


def ur_board(con: duckdb.DuckDBPyConnection) -> dict:
    admits = _admits(con)
    rows = [review(c, admits[c.encounter_id], find_flags(c)) for c in load_charts(con, SPLIT)]
    order = {"long_stay": 0, "observation_review": 1, "explained_by_gap": 2, "no_benchmark": 3, "ok": 4}
    rows.sort(key=lambda r: (order[r.status], -(r.los_days - (r.gmlos or 0))))
    return {"counts": dict(Counter(r.status for r in rows)), "rows": [asdict(r) for r in rows]}


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
        "weights_source": "CMS IPPS FY2027 Table 5 (v44), via quickintell.com; verify before real use",
    }
