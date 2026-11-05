"""Write the doctor notes for every chart with the OpenAI API.

    uv run wardsight-notes --limit 3      # small paid smoke test first
    uv run wardsight-notes                # all charts still missing notes

Needs OPENAI_API_KEY and WARDSIGHT_OPENAI_MODEL in this project's .env.
Notes that fail the check are retried with the problems listed, then skipped
and logged; a chart without notes is never silently filled in.
"""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from wardsight.notes.budget import BudgetExceeded, Ledger, load_budget
from wardsight.notes.spec import SYSTEM_PROMPT, NoteSet, check_notes, user_prompt
from wardsight.reload import load_encounters

log = logging.getLogger("wardsight.notes")

NOTES_DDL = """CREATE TABLE IF NOT EXISTS ehr.notes (encounter_id VARCHAR, note_type VARCHAR,
    hospital_day INTEGER, ts TIMESTAMP, text VARCHAR)"""

# (system, user) -> (parsed NoteSet or None, input_tokens, output_tokens)
Generate = Callable[[str, str], tuple[NoteSet | None, int, int]]


def openai_generate(model: str, max_output_tokens: int) -> Generate:
    from openai import OpenAI

    client = OpenAI()

    def call(system: str, user: str) -> tuple[NoteSet | None, int, int]:
        rsp = client.responses.parse(model=model, instructions=system, input=user,
                                     text_format=NoteSet, max_output_tokens=max_output_tokens)
        usage = rsp.usage
        return rsp.output_parsed, usage.input_tokens, usage.output_tokens

    return call


def write_notes(db: Path, config: Path, generate: Generate, model: str, limit: int | None) -> dict[str, int]:
    budget = load_budget(config)
    stats = {"written": 0, "failed": 0}
    with duckdb.connect(str(db)) as con:
        con.execute(NOTES_DDL)
        ledger = Ledger(con, budget, "notes")
        done = {r[0] for r in con.execute("SELECT DISTINCT encounter_id FROM ehr.notes").fetchall()}
        todo = [e for e in load_encounters(con) if e.encounter_id not in done][:limit]
        log.info("%d charts need notes", len(todo))
        try:
            for enc in todo:
                ok = _one(con, ledger, generate, model, enc, budget.max_attempts_per_item)
                stats["written" if ok else "failed"] += 1
        except BudgetExceeded as exc:
            log.error("HALTED: %s (%d tokens this run)", exc, ledger.run_tokens)
            stats["halted"] = 1
    log.info("notes: %s, tokens this run: %d", stats, ledger.run_tokens)
    return stats


def _one(con, ledger: Ledger, generate: Generate, model: str, enc, attempts: int) -> bool:
    prompt = user_prompt(enc)
    for attempt in range(1, attempts + 1):
        ledger.check_before_call()
        parsed, tokens_in, tokens_out = generate(SYSTEM_PROMPT, prompt)
        result = check_notes(parsed, enc.mentions) if parsed else None
        status = "ok" if result and result.ok else "rejected"
        ledger.record(enc.encounter_id, model, tokens_in, tokens_out, status)
        if result and result.ok:
            _save(con, enc, parsed)
            return True
        problems = result.problems if result else ("output did not match the note schema",)
        log.info("%s attempt %d rejected: %s", enc.encounter_id, attempt, "; ".join(problems))
        prompt = user_prompt(enc) + "\n\nYOUR LAST DRAFT WAS REJECTED. Fix: " + "; ".join(problems)
    log.warning("%s: no valid notes after %d attempts", enc.encounter_id, attempts)
    return False


def _save(con, enc, note_set: NoteSet) -> None:
    admit = con.execute("SELECT admit_ts FROM ehr.encounters WHERE encounter_id = ?",
                        [enc.encounter_id]).fetchone()[0]
    con.executemany("INSERT INTO ehr.notes VALUES (?, ?, ?, ?, ?)",
                    [(enc.encounter_id, n.note_type, n.hospital_day,
                      admit + timedelta(days=n.hospital_day, hours=10), n.text) for n in note_set.notes])


def main() -> None:
    parser = argparse.ArgumentParser(description="Write synthetic doctor notes with the OpenAI API.")
    parser.add_argument("--db", type=Path, default=Path("data/wardsight.duckdb"))
    parser.add_argument("--config", type=Path, default=Path("wardsight.toml"))
    parser.add_argument("--limit", type=int, default=None, help="only this many charts (smoke test)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_dotenv()
    model = os.environ.get("WARDSIGHT_OPENAI_MODEL")
    if not os.environ.get("OPENAI_API_KEY") or not model:
        raise SystemExit("Set OPENAI_API_KEY and WARDSIGHT_OPENAI_MODEL in .env (see .env.example).")
    budget = load_budget(args.config)
    write_notes(args.db, args.config, openai_generate(model, budget.max_output_tokens_per_call),
                model, args.limit)


if __name__ == "__main__":
    main()
