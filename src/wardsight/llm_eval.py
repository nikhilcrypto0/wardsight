"""One command to test the engine on AI-written doctor notes (development ward only).

    uv run wardsight-llm-eval --limit 5     # cheap smoke run first (needs .env)
    uv run wardsight-llm-eval               # all 200 development charts

Template notes use clean wording, so 75/75 on them is the easy case. This rewrites the
development charts' notes with the OpenAI model (hedged, abbreviated, like real notes),
rescans, and scores against the same answer key. It never touches the held-out ward and
never runs the final exam.

It works on a copy, data/wardsight-llm.duckdb, so the template baseline and the hosted
demo stay as they are. Re-running resumes: charts that already have AI notes are skipped,
so a run stopped by a budget cap never pays twice. Every call stays under the token
budgets in wardsight.toml. The report goes to docs/eval/llm-notes-dev.md.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import tempfile
from datetime import date
from pathlib import Path

import duckdb

from wardsight.bench import Score, mistakes, score
from wardsight.engine.chart import load_charts
from wardsight.engine.documentation import find_mentions
from wardsight.engine.scan import scan
from wardsight.notes.budget import load_budget
from wardsight.notes.template import NOTES_DDL
from wardsight.notes.writer import Generate, openai_generate, write_notes
from wardsight.queries.lint import TARGET_CODE
from wardsight.settings import check_model, openai_model

log = logging.getLogger("wardsight.llm_eval")

SPLIT = "dev"
CONDITION = {"aki": "acute kidney injury", "sepsis": "sepsis", "hyponatremia": "hyponatremia",
             "abla": "acute blood loss anemia", "arf": "acute hypoxic respiratory failure",
             "hf": "acute systolic heart failure"}
GROUP = {"missing": "missing diagnosis", "unsupported": "unsupported diagnosis",
         "correct": "correctly documented", "near_miss": "near-miss", "confounder": "confounder (CKD)",
         "routine": "routine admission"}
KIND = {"missing_dx": "missing diagnosis", "unsupported_dx": "unsupported diagnosis"}


def _fresh_scan_score(con: duckdb.DuckDBPyConnection) -> Score:
    con.execute(NOTES_DDL)
    con.execute("DELETE FROM ehr.notes WHERE note_type = 'addendum'")  # leftovers from demo clicks
    scan(con, SPLIT)
    return score(con, SPLIT)


def baseline(db: Path) -> Score:
    """The template-note score, recomputed on a throwaway copy so nothing is changed."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "baseline.duckdb"
        shutil.copy(db, copy)
        with duckdb.connect(str(copy)) as con:
            return _fresh_scan_score(con)


def _explain(con: duckdb.DuckDBPyConnection, m: dict) -> str:
    """One plain-English line per mistake, with what the note reader actually saw."""
    name = CONDITION.get(m["condition"], m["condition"])
    head = f"**{m['encounter_id']}** ({GROUP.get(m['group'], m['group'])}, {name}): "
    if m["missed"]:
        what = ("the evidence met the rule and the notes do not name it, but no gap was raised"
                if m["expected"] == "missing_dx" else
                "the notes name it without supporting evidence, but no gap was raised")
    else:
        raised = ", ".join(f"{CONDITION.get(c, c)} ({KIND.get(k, k)})" for c, k in
                           (r.split(":") for r in m["extra"]))
        what = f"should have stayed quiet, but raised {raised}"
    chart = load_charts(con, encounter_id=m["encounter_id"])[0]
    code = TARGET_CODE.get(m["condition"])
    seen = [f"\"{x.clause.strip()[:140]}\"{' (read as negated)' if x.negated else ''}"
            for x in find_mentions(chart.notes) if x.icd10 == code][:2]
    return head + what + (f". The note reader found: {'; '.join(seen)}" if seen else
                          ". The note reader found no mention of it")


def _report(base: Score, new: Score, errors: list[str], notes: dict, bill: dict, model: str) -> str:
    def line(s: Score) -> str:
        return (f"{s.caught}/{s.planted} planted gaps caught, {s.false_alarms} false alarms "
                f"on {s.quiet_charts} charts that should stay quiet")
    rows = "\n".join(f"| {GROUP.get(g, g)} | {n} | {ok} |" for g, n, ok, _ in new.by_group)
    return f"""# Engine on AI-written notes: development ward

Run {date.today().isoformat()} with `{model}`. Held-out ward untouched; final exam not run.

| Notes | Result |
| --- | --- |
| Template notes (clean wording, the easy case) | {line(base)} |
| AI-written notes | {line(new)} |

Charts with AI notes: {notes['llm']} of {notes['total']}{
    f" ({notes['total'] - notes['llm']} still have template notes: the AI draft failed the leak check "
    "three times, or the run stopped at a budget cap; re-run to finish)" if notes['llm'] < notes['total'] else ""}.

| Test group | Charts | Correct |
| --- | --- | --- |
{rows}

## Every mistake, in plain English

{chr(10).join(f"- {e}" for e in errors) if errors else "None."}

## Cost

{bill['calls']} model calls ({bill['rejected']} drafts rejected by the leak check and retried),
{bill['tokens']:,} tokens in total. Budget caps from wardsight.toml applied to every call.
"""


def run_eval(db: Path, work: Path, config: Path, generate: Generate, model: str,
             limit: int | None, report: Path) -> dict:
    base = baseline(db)
    if not work.exists():
        shutil.copy(db, work)
    stats = write_notes(work, config, generate, model, limit, split=SPLIT)
    with duckdb.connect(str(work)) as con:
        new = _fresh_scan_score(con)
        errors = [_explain(con, m) for m in mistakes(con, SPLIT)]
        total, llm = con.execute("""
            SELECT count(DISTINCT e.encounter_id),
                   count(DISTINCT n.encounter_id) FILTER (WHERE n.source = 'llm')
            FROM ehr.encounters e LEFT JOIN ehr.notes n USING (encounter_id)
            WHERE e.split = ?""", [SPLIT]).fetchone()
        calls, rejected, tokens = con.execute("""
            SELECT count(*), count(*) FILTER (WHERE status = 'rejected'),
                   coalesce(sum(input_tokens + output_tokens), 0)
            FROM ops.llm_ledger WHERE step = 'notes'""").fetchone()
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(_report(base, new, errors, {"total": total, "llm": llm},
                              {"calls": calls, "rejected": rejected, "tokens": tokens}, model))
    return {"baseline_caught": base.caught, "caught": new.caught, "planted": new.planted,
            "false_alarms": new.false_alarms, "mistakes": len(errors), "llm_charts": llm, **stats}


def main() -> None:
    parser = argparse.ArgumentParser(description="Score the engine on AI-written notes (dev only).")
    parser.add_argument("--db", type=Path, default=Path("data/wardsight.duckdb"))
    parser.add_argument("--work", type=Path, default=Path("data/wardsight-llm.duckdb"))
    parser.add_argument("--config", type=Path, default=Path("wardsight.toml"))
    parser.add_argument("--limit", type=int, default=None, help="only this many new charts (smoke test)")
    parser.add_argument("--report", type=Path, default=Path("docs/eval/llm-notes-dev.md"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    model = openai_model()
    check_model(model)  # free: stops a paid run on a misspelled or retired model
    budget = load_budget(args.config)
    result = run_eval(args.db, args.work, args.config,
                      openai_generate(model, budget.max_output_tokens_per_call), model, args.limit, args.report)
    print(result)
    print(f"report: {args.report}")


if __name__ == "__main__":
    main()
