"""Draft a query for every flag and put it in the human review queue (ops.queries).

    uv run wardsight-queries --split dev                 # template drafter (free)
    uv run wardsight-queries --split dev --llm --limit 3 # OpenAI drafter (needs .env)

Status 'pending_review' = passed the rules check, waiting for a human.
Status 'needs_rewrite'  = still failing after all retries; a human must write it.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from wardsight.notes.budget import BudgetExceeded, Ledger, load_budget
from wardsight.queries.draft import (
    Drafter,
    QueryResult,
    draft_query,
    make_request,
    openai_drafter,
    template_drafter,
)

log = logging.getLogger("wardsight.queries")

QUERIES_DDL = """CREATE SCHEMA IF NOT EXISTS ops;
CREATE TABLE IF NOT EXISTS ops.queries (encounter_id VARCHAR, split VARCHAR, condition VARCHAR,
    kind VARCHAR, stem VARCHAR, options VARCHAR, indicators VARCHAR, drafter VARCHAR,
    attempts INTEGER, passed_check BOOLEAN, problems VARCHAR, status VARCHAR, created_ts TIMESTAMP)"""


def draft_all(con: duckdb.DuckDBPyConnection, split: str, drafter: Drafter, name: str,
              attempts: int, ledger: Ledger | None = None, model: str = "",
              limit: int | None = None) -> list[QueryResult]:
    con.execute(QUERIES_DDL)
    con.execute("DELETE FROM ops.queries WHERE split = ?", [split])
    flags = con.execute("SELECT encounter_id, condition, kind, detail, evidence FROM ops.flags "
                        "WHERE split = ? ORDER BY encounter_id, condition", [split]).fetchall()
    results: list[QueryResult] = []
    try:
        for row in flags[:limit]:
            results.append(draft_query(make_request(*row), drafter, name, attempts, ledger, model))
    except BudgetExceeded as exc:
        log.error("HALTED: %s", exc)
    con.executemany("INSERT INTO ops.queries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        (r.request.encounter_id, split, r.request.condition, r.request.kind, r.stem,
         json.dumps(r.request.options), json.dumps(r.request.indicators), r.drafter, r.attempts,
         r.lint.ok, json.dumps(r.lint.problems), "pending_review" if r.lint.ok else "needs_rewrite",
         datetime.now()) for r in results])
    log.info("%s: %d queries drafted by %s; %s; first-draft pass %d/%d", split, len(results), name,
             dict(Counter("passed" if r.lint.ok else "needs_rewrite" for r in results)),
             sum(r.lint.ok and r.attempts == 1 for r in results), len(results))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft physician queries for every flag.")
    parser.add_argument("--db", type=Path, default=Path("data/wardsight.duckdb"))
    parser.add_argument("--config", type=Path, default=Path("wardsight.toml"))
    parser.add_argument("--split", default="dev", choices=("dev", "heldout"))
    parser.add_argument("--llm", action="store_true", help="use the OpenAI drafter (needs .env)")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    budget = load_budget(args.config)
    with duckdb.connect(str(args.db)) as con:
        if not args.llm:
            draft_all(con, args.split, template_drafter, "template", 1, limit=args.limit)
            return
        load_dotenv()
        model = os.environ.get("WARDSIGHT_OPENAI_MODEL")
        if not os.environ.get("OPENAI_API_KEY") or not model:
            raise SystemExit("Set OPENAI_API_KEY and WARDSIGHT_OPENAI_MODEL in .env (see .env.example).")
        ledger = Ledger(con, budget, "queries")
        draft_all(con, args.split, openai_drafter(model, budget.max_output_tokens_per_call), "openai",
                  budget.max_attempts_per_item, ledger, model, args.limit)


if __name__ == "__main__":
    main()
