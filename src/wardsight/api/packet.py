"""Audit-defense packet: everything an auditor or payer asks about one answered query, in one place.

Built from the append-only audit log and the chart. It shows the evidence values behind the alert
with the published rule they meet, the exact question the physician saw, proof that the question
passed the compliant-query rules check, who approved it and when, the physician's answer and
addendum, and the billing category before and after.
"""

from __future__ import annotations

import json

import duckdb

from wardsight.engine.drg_table import facts
from wardsight.queries.lint import lint_query
from wardsight.queries.options import CONDITION_NAMES
from wardsight.rules_doc import rule_for
from wardsight.workflow.actions import WorkflowError

QUERY_STANDARD = "ACDIS/AHIMA Guidelines for Achieving a Compliant Query Practice (2022 update)"
SENT_ACTIONS = ("approved_and_sent", "edited_approved_and_sent")


def _weight(drg: int | None) -> float | None:
    f = facts(drg) if drg else None
    return f.weight if f else None


def audit_packet(con: duckdb.DuckDBPyConnection, query_id: str) -> dict:
    row = con.execute("""
        SELECT q.encounter_id, q.condition, q.kind, q.stem, q.options, q.indicators, q.drafter, q.status,
               q.answer, q.answer_comment, q.answered_by, q.drg_before, q.drg_after,
               e.reason_for_admission, e.los_days, p.age, p.sex
        FROM ops.queries q JOIN ehr.encounters e USING (encounter_id) JOIN ehr.patients p USING (patient_id)
        WHERE q.query_id = ?""", [query_id]).fetchone()
    if not row:
        raise KeyError(query_id)
    (encounter_id, condition, kind, stem, options, indicators, drafter, status, answer, comment,
     answered_by, drg_before, drg_after, reason, los, age, sex) = row
    if status not in ("answered", "resolved"):
        raise WorkflowError(f"query {query_id} is '{status}'; a packet is made once the physician has answered")
    options, indicators = tuple(json.loads(options)), tuple(json.loads(indicators))

    since = con.execute("SELECT coalesce(max(ts), TIMESTAMP '1970-01-01') FROM ops.audit "
                        "WHERE action = 'reset'").fetchone()[0]
    trail = [{"ts": ts, "actor": actor, "action": action, "detail": detail}
             for ts, actor, action, detail in con.execute(
                 "SELECT ts, actor, action, detail FROM ops.audit WHERE query_id = ? AND ts >= ? ORDER BY ts",
                 [query_id, since]).fetchall()]
    sent = next((t for t in trail if t["action"] in SENT_ACTIONS), None)
    answered = next((t for t in trail if t["action"] == "answered"), None)
    addendum = con.execute("""SELECT text FROM ehr.notes WHERE encounter_id = ? AND note_type = 'addendum'
                              ORDER BY ts DESC LIMIT 1""", [encounter_id]).fetchone()
    check = lint_query(stem, options, indicators, condition, kind)  # re-run now on the text that was sent

    rules = [rule_for(condition)]
    if kind in ("unspecified_dx", "conflicting_dx"):
        rules.append(rule_for(kind))
    return {
        "query_id": query_id, "encounter_id": encounter_id,
        "patient": {"age": age, "sex": sex, "reason_for_admission": reason, "los_days": los},
        "condition": condition, "condition_name": CONDITION_NAMES[condition], "alert": kind,
        "evidence": list(indicators), "rules": rules,
        "query": {"stem": stem, "options": list(options), "drafter": drafter, "standard": QUERY_STANDARD,
                  "rules_check": {"ok": check.ok, "problems": list(check.problems)}},
        "approval": {"by": sent["actor"], "at": sent["ts"], "edited": sent["action"] != "approved_and_sent"}
        if sent else None,
        "answer": {"option": answer, "comment": comment, "by": answered_by, "at": answered["ts"] if answered else None},
        "addendum": addendum[0] if addendum else None,
        "outcome": {"status": status, "drg_before": drg_before, "drg_after": drg_after,
                    "weight_before": _weight(drg_before), "weight_after": _weight(drg_after)},
        "trail": trail,
    }
