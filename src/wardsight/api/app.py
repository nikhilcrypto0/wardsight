"""HTTP API for the WardSight web app (dev split only; the held-out set is never served).

    uv run wardsight-api            # http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from wardsight.engine.chart import load_charts
from wardsight.engine.drg import coded_diagnoses, group
from wardsight.queries.lint import lint_query
from wardsight.workflow import actions

SPLIT = "dev"
CHART_SERIES = ("creatinine", "sodium", "hemoglobin", "platelets", "wbc", "map", "spo2", "resp_rate",
                "heart_rate", "temp", "o2_flow")
ONE_OFF_LABS = ("bnp", "lvef", "lactate", "bilirubin", "pao2")
REVIEWER = "CDI reviewer"


class ApproveBody(BaseModel):
    stem: str | None = Field(default=None, max_length=700)
    reviewer: str = Field(default=REVIEWER, max_length=80)


class RejectBody(BaseModel):
    reason: str = Field(min_length=3, max_length=300)
    reviewer: str = Field(default=REVIEWER, max_length=80)


class AnswerBody(BaseModel):
    option_index: int = Field(ge=0, le=10)
    comment: str = Field(default="", max_length=400)
    physician: str = Field(default="Attending physician", max_length=80)


class LintBody(BaseModel):
    query_id: str
    stem: str = Field(max_length=2000)


def create_app(db_path: Path) -> FastAPI:
    app = FastAPI(title="WardSight API", description="Synthetic data only. Demo, not for clinical use.")

    @contextmanager
    def db() -> Iterator[duckdb.DuckDBPyConnection]:
        con = duckdb.connect(str(db_path))
        try:
            actions.ensure_schema(con)
            yield con
        finally:
            con.close()

    def rows(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> list[dict]:
        cur = con.execute(sql, params or [])
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    def run_action(fn, *args) -> object:
        try:
            with db() as con:
                return fn(con, *args)
        except KeyError as exc:
            raise HTTPException(404, f"not found: {exc}") from exc
        except actions.WorkflowError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/summary")
    def summary() -> dict:
        with db() as con:
            statuses = dict(con.execute("SELECT status, count(*) FROM ops.queries WHERE split = ? GROUP BY 1",
                                        [SPLIT]).fetchall())
            flags = dict(con.execute("SELECT kind, count(*) FROM ops.flags WHERE split = ? GROUP BY 1",
                                     [SPLIT]).fetchall())
            charts = con.execute("SELECT count(*) FROM ehr.encounters WHERE split = ?", [SPLIT]).fetchone()[0]
        return {"charts": charts, "open_flags": flags, "queries": statuses}

    @app.get("/api/worklist")
    def worklist() -> list[dict]:
        with db() as con:
            return rows(con, """
                SELECT q.query_id, q.encounter_id, q.condition, q.kind, q.status, q.updated_ts,
                       e.reason_for_admission, p.age, p.sex,
                       f.drg_now, f.severity_now, f.drg_if_resolved, f.severity_if_resolved,
                       q.drg_before, q.drg_after, q.answer
                FROM ops.queries q
                JOIN ehr.encounters e USING (encounter_id) JOIN ehr.patients p USING (patient_id)
                LEFT JOIN ops.flags f ON f.encounter_id = q.encounter_id AND f.condition = q.condition
                                      AND f.kind = q.kind
                WHERE q.split = ? ORDER BY q.encounter_id, q.condition""", [SPLIT])

    @app.get("/api/encounters/{encounter_id}")
    def encounter(encounter_id: str) -> dict:
        with db() as con:
            charts = load_charts(con, encounter_id=encounter_id)
            if not charts or charts[0].split != SPLIT:
                raise HTTPException(404, "encounter not found")
            chart = charts[0]
            drg = group(chart, coded_diagnoses(chart))
            flags = rows(con, "SELECT condition, kind, icd10, detail, evidence, drg_now, drg_now_desc, "
                              "severity_now, drg_if_resolved, drg_if_resolved_desc, severity_if_resolved "
                              "FROM ops.flags WHERE encounter_id = ?", [encounter_id])
            queries = rows(con, "SELECT * FROM ops.queries WHERE encounter_id = ?", [encounter_id])
        return {
            "encounter_id": chart.encounter_id, "age": chart.age, "sex": chart.sex, "los_days": chart.los_days,
            "reason_for_admission": chart.reason_for_admission, "problem_list": chart.problem_list,
            "drg": {"drg": drg.drg, "description": drg.description, "severity": drg.severity,
                    "principal": drg.principal, "secondary": drg.secondary},
            "series": {k: chart.series(k) for k in CHART_SERIES if chart.series(k)},
            "labs": {k: chart.series(k) for k in ONE_OFF_LABS if chart.series(k)},
            "timeline": [{"t": t, "kind": e.kind, "text": e.text} for e in chart.events
                         if (t := e.t_hours) is not None and e.text],
            "notes": [{"type": n.note_type, "day": n.hospital_day, "text": n.text} for n in chart.notes],
            "flags": flags,
            "queries": [{**q, "options": json.loads(q["options"]), "indicators": json.loads(q["indicators"]),
                         "problems": json.loads(q["problems"] or "[]")} for q in queries],
        }

    @app.post("/api/lint")
    def lint(body: LintBody) -> dict:
        with db() as con:
            try:
                q = actions.get_query(con, body.query_id)
            except KeyError as exc:
                raise HTTPException(404, "query not found") from exc
        result = lint_query(body.stem, q.options, q.indicators, q.condition, q.kind)
        return {"ok": result.ok, "problems": list(result.problems)}

    @app.post("/api/queries/{query_id}/approve")
    def approve(query_id: str, body: ApproveBody) -> dict:
        run_action(actions.approve, query_id, body.reviewer, body.stem)
        return {"status": "sent"}

    @app.post("/api/queries/{query_id}/reject")
    def reject(query_id: str, body: RejectBody) -> dict:
        run_action(actions.reject, query_id, body.reviewer, body.reason)
        return {"status": "rejected"}

    @app.get("/api/inbox")
    def inbox() -> list[dict]:
        with db() as con:
            items = rows(con, """
                SELECT q.query_id, q.encounter_id, q.condition, q.kind, q.stem, q.options, q.status,
                       q.answer, q.answer_comment, q.answered_by, q.drg_before, q.drg_after, q.updated_ts,
                       e.reason_for_admission, p.age, p.sex
                FROM ops.queries q JOIN ehr.encounters e USING (encounter_id) JOIN ehr.patients p USING (patient_id)
                WHERE q.split = ? AND q.status IN ('sent', 'answered', 'resolved')
                ORDER BY q.status = 'sent' DESC, q.updated_ts DESC""", [SPLIT])
        return [{**i, "options": json.loads(i["options"])} for i in items]

    @app.post("/api/queries/{query_id}/answer")
    def answer(query_id: str, body: AnswerBody) -> dict:
        status = run_action(actions.answer, query_id, body.option_index, body.comment, body.physician)
        return {"status": status}

    @app.post("/api/queries/{query_id}/simulate")
    def simulate(query_id: str) -> dict:
        return {"status": run_action(actions.simulate_answer, query_id)}

    @app.get("/api/audit")
    def audit_log() -> list[dict]:
        with db() as con:
            return rows(con, "SELECT * FROM ops.audit ORDER BY ts DESC LIMIT 300")

    @app.post("/api/admin/reset")
    def reset() -> dict:
        run_action(actions.reset)
        return {"status": "reset"}

    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Serve the WardSight API.")
    parser.add_argument("--db", type=Path, default=Path("data/wardsight.duckdb"))
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(args.db), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
