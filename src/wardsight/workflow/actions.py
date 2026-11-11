"""Query workflow: review -> send -> physician answer -> addendum -> rescan.

Statuses:
  pending_review  drafted and passed the rules check, waiting for a CDI reviewer
  needs_rewrite   failed the rules check after all retries; a human must write it
  rejected        reviewer decided not to send it
  sent            approved by a reviewer, waiting in the physician's inbox
  answered        physician answered; the flag is still open (disagreed / undetermined)
  resolved        physician answered and the rescan cleared the flag

Nothing reaches the physician without a reviewer's approval, and every step is
written to the append-only audit log (ops.audit).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

import duckdb

from wardsight.engine.chart import load_charts
from wardsight.engine.drg import coded_diagnoses, group
from wardsight.engine.scan import scan, scan_encounter
from wardsight.queries.draft import template_drafter
from wardsight.queries.lint import lint_query
from wardsight.queries.options import OTHER, UNDETERMINED
from wardsight.queries.run import draft_all, ensure_queries_table
from wardsight.workflow.physician import rule_based_reply

AUDIT_DDL = """CREATE SCHEMA IF NOT EXISTS ops;
CREATE TABLE IF NOT EXISTS ops.audit (ts TIMESTAMP, actor VARCHAR, action VARCHAR,
    query_id VARCHAR, detail VARCHAR)"""

# What the addendum says when the physician confirms the queried diagnosis
CONFIRMED_PHRASE = {"aki": "acute kidney injury", "sepsis": "sepsis", "hyponatremia": "hyponatremia",
                    "abla": "acute blood loss anemia", "arf": "acute hypoxic respiratory failure",
                    "hf": "acute systolic heart failure"}
HF_ACUTE_ON_CHRONIC = "Acute on chronic systolic heart failure"


class WorkflowError(ValueError):
    """Raised for an action that is not allowed in the query's current state."""


@dataclass(frozen=True)
class QueryRow:
    query_id: str
    encounter_id: str
    condition: str
    kind: str
    stem: str
    options: tuple[str, ...]
    indicators: tuple[str, ...]
    status: str


def ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    ensure_queries_table(con)
    con.execute(AUDIT_DDL)


def audit(con: duckdb.DuckDBPyConnection, actor: str, action: str, query_id: str, detail: str) -> None:
    con.execute("INSERT INTO ops.audit VALUES (?, ?, ?, ?, ?)", [datetime.now(), actor, action, query_id, detail])


def get_query(con: duckdb.DuckDBPyConnection, query_id: str) -> QueryRow:
    row = con.execute("SELECT query_id, encounter_id, condition, kind, stem, options, indicators, status "
                      "FROM ops.queries WHERE query_id = ?", [query_id]).fetchone()
    if not row:
        raise KeyError(query_id)
    return QueryRow(row[0], row[1], row[2], row[3], row[4], tuple(json.loads(row[5])),
                    tuple(json.loads(row[6])), row[7])


def _require(q: QueryRow, *allowed: str) -> None:
    if q.status not in allowed:
        raise WorkflowError(f"query {q.query_id} is '{q.status}'; this action needs {' or '.join(allowed)}")


def _set_status(con: duckdb.DuckDBPyConnection, query_id: str, status: str, **fields: object) -> None:
    sets = ", ".join(["status = ?", "updated_ts = ?", *(f"{k} = ?" for k in fields)])
    con.execute(f"UPDATE ops.queries SET {sets} WHERE query_id = ?",
                [status, datetime.now(), *fields.values(), query_id])


def approve(con: duckdb.DuckDBPyConnection, query_id: str, reviewer: str, edited_stem: str | None = None) -> None:
    """Reviewer approves (optionally after editing); an edit must pass the rules check again."""
    q = get_query(con, query_id)
    _require(q, "pending_review", "needs_rewrite")
    stem = (edited_stem or q.stem).strip()
    result = lint_query(stem, q.options, q.indicators, q.condition, q.kind)
    if not result.ok:
        raise WorkflowError("; ".join(result.problems))
    _set_status(con, query_id, "sent", stem=stem, passed_check=True)
    audit(con, reviewer, "approved_and_sent" if edited_stem is None else "edited_approved_and_sent",
          query_id, stem)


def reject(con: duckdb.DuckDBPyConnection, query_id: str, reviewer: str, reason: str) -> None:
    q = get_query(con, query_id)
    _require(q, "pending_review", "needs_rewrite")
    _set_status(con, query_id, "rejected")
    audit(con, reviewer, "rejected", query_id, reason)


def addendum_text(q: QueryRow, option: str, comment: str) -> str | None:
    if option in (OTHER, UNDETERMINED):
        return None
    if q.kind == "missing_dx" and option == q.options[0]:
        statement = CONFIRMED_PHRASE[q.condition]
    elif q.kind == "missing_dx" and option == HF_ACUTE_ON_CHRONIC:
        statement = "acute on chronic systolic heart failure"
    else:
        statement = option
    return f"ADDENDUM in response to documentation query: {statement}. {comment}"


def answer(con: duckdb.DuckDBPyConnection, query_id: str, option_index: int, comment: str,
           physician: str) -> str:
    """Record the physician's answer, write the addendum, rescan. Returns the new status."""
    q = get_query(con, query_id)
    _require(q, "sent")
    if not 0 <= option_index < len(q.options):
        raise WorkflowError(f"option {option_index} does not exist")
    option = q.options[option_index]
    chart = load_charts(con, encounter_id=q.encounter_id)[0]
    drg_before = group(chart, coded_diagnoses(chart)).drg

    text = addendum_text(q, option, comment)
    if text:
        admit, los = con.execute("SELECT admit_ts, los_days FROM ehr.encounters WHERE encounter_id = ?",
                                 [q.encounter_id]).fetchone()
        con.execute("INSERT INTO ehr.notes VALUES (?, 'addendum', ?, ?, ?, 'physician')",
                    [q.encounter_id, los - 1, admit + timedelta(days=los - 1, hours=16), text])
    flags = scan_encounter(con, q.encounter_id)
    chart = load_charts(con, encounter_id=q.encounter_id)[0]
    drg_after = group(chart, coded_diagnoses(chart)).drg
    still_open = any(f.condition == q.condition and f.kind == q.kind for f in flags)
    status = "answered" if still_open else "resolved"
    _set_status(con, query_id, status, answer=option, answer_comment=comment, answered_by=physician,
                drg_before=drg_before, drg_after=drg_after)
    audit(con, physician, "answered", query_id, f"{option} | {comment}")
    if status == "resolved":
        audit(con, "wardsight", "flag_resolved", query_id, f"DRG {drg_before} -> {drg_after}")
    return status


def simulate_answer(con: duckdb.DuckDBPyConnection, query_id: str) -> str:
    q = get_query(con, query_id)
    reply = rule_based_reply(query_id, q.kind, q.options)
    return answer(con, query_id, reply.option_index, reply.comment, "Dr. Simulated (physician agent)")


def reset(con: duckdb.DuckDBPyConnection, actor: str = "demo") -> None:
    """Remove all physician addenda, rescan the dev split and redraft its queries."""
    ensure_schema(con)
    con.execute("DELETE FROM ehr.notes WHERE note_type = 'addendum'")
    scan(con, "dev")
    draft_all(con, "dev", template_drafter, "template", 1)
    audit(con, actor, "reset", "", "addenda removed, dev rescanned, queries redrafted")
