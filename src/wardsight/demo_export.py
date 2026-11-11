"""Export the hosted demo: the dev ward as static files plus every workflow outcome.

The public site has no server. Instead, this runs the real workflow on a throwaway copy
of the database: for every query and every answer a physician could give, it approves,
answers and rescans inside a transaction, records what changed, and rolls back. The
browser then replays exactly what the Python engine would have done.

    uv run wardsight-demo        # -> web/public/demo/  and  web/tests/lint-cases.json

Answers are precomputed with an empty physician comment; a comment typed in the hosted
demo is shown in the addendum but not re-read by the engine.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

import duckdb
from fastapi.encoders import jsonable_encoder

from wardsight.api import reports
from wardsight.api.app import REVIEWER, encounter_payload, rows, worklist_rows
from wardsight.engine.chart import Chart, load_charts
from wardsight.engine.documentation import LEXICON
from wardsight.engine.drg import coded_diagnoses, group
from wardsight.engine.drg_table import facts
from wardsight.engine.gaps import find_flags
from wardsight.engine.ur import codes_if_resolved, review
from wardsight.queries.lint import TARGET_CODE, lint_query
from wardsight.workflow import actions
from wardsight.workflow.physician import rule_based_reply

SPLIT = "dev"
PHYSICIAN = "Dr. Simulated (physician agent)"
WEB = Path(__file__).resolve().parents[2] / "web"

# Edits a reviewer might make, used to prove the browser rules check matches this one
MUTATIONS = (
    lambda s: s,
    lambda s: s + " Please document the diagnosis.",
    lambda s: s + " This affects the DRG and reimbursement.",
    lambda s: "Do the findings meet criteria for this condition? " + s,
    lambda s: s.replace("?", "."),
    lambda s: s.replace("clarify", "describe").replace("?", "."),
    lambda s: s + " Values were 999 and 12.5 earlier.",
    lambda s: s + " It is likely, consistent with the labs.",
    lambda s: s + " " + "x" * 700,
    lambda s: s + " Cost of care is a concern ($).",
)


def _drgs(chart: Chart) -> list[int]:
    """[as first documented, now, if every open gap were resolved], as the leadership view counts them."""
    original = replace(chart, notes=tuple(n for n in chart.notes if n.note_type != "addendum"))
    return [group(original, coded_diagnoses(original)).drg, group(chart, coded_diagnoses(chart)).drg,
            group(chart, codes_if_resolved(chart, find_flags(chart))).drg]


def _outcome(con: duckdb.DuckDBPyConnection, q: actions.QueryRow, option_index: int, admit: object) -> dict:
    con.begin()
    try:
        actions.approve(con, q.query_id, REVIEWER)
        status = actions.answer(con, q.query_id, option_index, "", PHYSICIAN)
        before, after = con.execute("SELECT drg_before, drg_after FROM ops.queries WHERE query_id = ?",
                                    [q.query_id]).fetchone()
        chart_after = encounter_payload(con, q.encounter_id)
        chart = load_charts(con, encounter_id=q.encounter_id)[0]
        return {
            "status": status, "drg_before": before, "drg_after": after,
            "addendum": actions.addendum_text(q, q.options[option_index], ""),
            "drg": chart_after["drg"], "flags": chart_after["flags"],
            "ur_row": asdict(review(chart, admit, find_flags(chart))), "drgs": _drgs(chart),
        }
    finally:
        con.rollback()


def lint_cases(queries: list[actions.QueryRow]) -> list[dict]:
    cases = []
    for q in queries:
        for mutate in MUTATIONS:
            stem = mutate(q.stem)
            for options in (q.options, ("Yes", "No", *q.options[-2:]), q.options[:-1]):
                r = lint_query(stem, options, q.indicators, q.condition, q.kind)
                cases.append({"stem": stem, "options": list(options), "indicators": list(q.indicators),
                              "condition": q.condition, "kind": q.kind, "ok": r.ok, "problems": list(r.problems)})
    return cases


def export(db_path: Path, out: Path, cases_path: Path) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "demo.duckdb"
        shutil.copy(db_path, work)
        con = duckdb.connect(str(work))
        actions.reset(con, actor="demo-export")
        con.execute("DELETE FROM ops.audit")
        admits = dict(con.execute("SELECT encounter_id, admit_ts FROM ehr.encounters WHERE split = ?",
                                  [SPLIT]).fetchall())

        enc_dir = out / "encounters"
        if enc_dir.exists():
            shutil.rmtree(enc_dir)
        enc_dir.mkdir(parents=True)
        case_mix: dict[str, list[int]] = {}
        for chart in load_charts(con, SPLIT):
            payload = jsonable_encoder(encounter_payload(con, chart.encounter_id))
            (enc_dir / f"{chart.encounter_id}.json").write_text(json.dumps(payload, separators=(",", ":")))
            case_mix[chart.encounter_id] = _drgs(chart)

        details = {r["query_id"]: r for r in rows(con, """
            SELECT q.*, e.reason_for_admission, p.age, p.sex FROM ops.queries q
            JOIN ehr.encounters e USING (encounter_id) JOIN ehr.patients p USING (patient_id)
            WHERE q.split = ?""", [SPLIT])}
        query_rows = [actions.get_query(con, qid) for qid in sorted(details)]
        flag_kinds = {e: [k for (k,) in con.execute("SELECT kind FROM ops.flags WHERE encounter_id = ?",
                                                      [e]).fetchall()] for e in {q.encounter_id for q in query_rows}}
        queries = {}
        for q in query_rows:
            d = details[q.query_id]
            reply = rule_based_reply(q.query_id, q.kind, q.options)
            queries[q.query_id] = {
                **{k: d[k] for k in ("query_id", "encounter_id", "condition", "kind", "stem", "status",
                                     "reason_for_admission", "age", "sex")},
                "options": list(q.options), "indicators": list(q.indicators),
                "problems": json.loads(d["problems"] or "[]"), "flag_kinds": flag_kinds[q.encounter_id],
                "simulated": {"option_index": reply.option_index, "comment": reply.comment},
                "outcomes": [_outcome(con, q, i, admits[q.encounter_id]) for i in range(len(q.options))],
            }

        drgs = {d for v in case_mix.values() for d in v} | {
            d for q in queries.values() for o in q["outcomes"] for d in (*o["drgs"], o["drg_before"], o["drg_after"])}
        index = {
            "charts": len(case_mix), "physician": PHYSICIAN, "reviewer": REVIEWER,
            "worklist": worklist_rows(con), "queries": queries, "ur": reports.ur_board(con),
            "case_mix_drgs": case_mix,
            "weights": {str(d): f.weight for d in sorted(x for x in drgs if x) if (f := facts(d))},
            "weights_source": reports.leadership(con)["weights_source"],
            "lint_targets": {c: list(LEXICON[code]) for c, code in TARGET_CODE.items()},
        }
        (out / "index.json").write_text(json.dumps(jsonable_encoder(index), separators=(",", ":")))
        # The browser replay must land where the engine does: approve every query, let the
        # simulated physician answer, and record the ward totals for web/tests/demo.test.mts.
        for q in query_rows:
            actions.approve(con, q.query_id, REVIEWER)
            actions.simulate_answer(con, q.query_id)
        expected = {
            "statuses": dict(con.execute("SELECT status, count(*) FROM ops.queries WHERE split = ? GROUP BY 1",
                                         [SPLIT]).fetchall()),
            "open_flags": dict(con.execute("SELECT kind, count(*) FROM ops.flags WHERE split = ? GROUP BY 1",
                                           [SPLIT]).fetchall()),
            "leadership": reports.leadership(con), "ur_counts": reports.ur_board(con)["counts"],
        }
        (cases_path.parent / "demo-expected.json").write_text(json.dumps(jsonable_encoder(expected), indent=2))
        cases = lint_cases(query_rows)
        cases_path.parent.mkdir(parents=True, exist_ok=True)
        cases_path.write_text(json.dumps(cases, separators=(",", ":")))
        con.close()
    return {"encounters": len(case_mix), "queries": len(queries), "lint_cases": len(cases)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the hosted demo's static data.")
    parser.add_argument("--db", type=Path, default=Path("data/wardsight.duckdb"))
    parser.add_argument("--out", type=Path, default=WEB / "public" / "demo")
    parser.add_argument("--cases", type=Path, default=WEB / "tests" / "lint-cases.json")
    args = parser.parse_args()
    print(export(args.db, args.out, args.cases))


if __name__ == "__main__":
    main()
