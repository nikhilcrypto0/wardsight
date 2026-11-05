"""Token budgets for every LLM step: per call, per run, per day. Breach = halt.

Budgets live in wardsight.toml, never in prompts. Every call is recorded in
the ops.llm_ledger table so the daily cap survives restarts.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import duckdb

log = logging.getLogger("wardsight.budget")


class BudgetExceeded(RuntimeError):
    """Raised to halt a run when any token budget would be breached."""


@dataclass(frozen=True)
class Budget:
    max_output_tokens_per_call: int
    max_tokens_per_run: int
    max_tokens_per_day: int
    max_attempts_per_item: int


def load_budget(path: Path) -> Budget:
    cfg = tomllib.loads(path.read_text())["llm"]
    return Budget(cfg["max_output_tokens_per_call"], cfg["max_tokens_per_run"],
                  cfg["max_tokens_per_day"], cfg["max_attempts_per_item"])


LEDGER_DDL = """CREATE SCHEMA IF NOT EXISTS ops;
CREATE TABLE IF NOT EXISTS ops.llm_ledger (ts TIMESTAMP, step VARCHAR, item_id VARCHAR,
    model VARCHAR, input_tokens INTEGER, output_tokens INTEGER, status VARCHAR);"""


class Ledger:
    def __init__(self, con: duckdb.DuckDBPyConnection, budget: Budget, step: str) -> None:
        con.execute(LEDGER_DDL)
        self._con, self._budget, self._step = con, budget, step
        self._run_tokens = 0

    def used_today(self) -> int:
        row = self._con.execute(
            "SELECT coalesce(sum(input_tokens + output_tokens), 0) FROM ops.llm_ledger "
            "WHERE CAST(ts AS DATE) = ?", [date.today()]).fetchone()
        return int(row[0])

    def check_before_call(self) -> None:
        """Halt if one more maximum-size call could cross a cap."""
        headroom = self._budget.max_output_tokens_per_call * 2
        if self._run_tokens + headroom > self._budget.max_tokens_per_run:
            raise BudgetExceeded(f"run budget {self._budget.max_tokens_per_run} tokens reached")
        if self.used_today() + headroom > self._budget.max_tokens_per_day:
            raise BudgetExceeded(f"daily budget {self._budget.max_tokens_per_day} tokens reached")

    def record(self, item_id: str, model: str, input_tokens: int, output_tokens: int, status: str) -> None:
        self._run_tokens += input_tokens + output_tokens
        self._con.execute("INSERT INTO ops.llm_ledger VALUES (?, ?, ?, ?, ?, ?, ?)",
                          [datetime.now(), self._step, item_id, model, input_tokens, output_tokens, status])
        log.debug("%s %s %s in=%d out=%d", self._step, item_id, status, input_tokens, output_tokens)

    @property
    def run_tokens(self) -> int:
        return self._run_tokens
