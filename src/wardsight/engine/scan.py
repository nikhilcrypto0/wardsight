"""Run the detection engine over a split and store its flags in ops.flags.

    uv run wardsight-scan --split dev
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from pathlib import Path

import duckdb

from wardsight.engine.chart import load_charts
from wardsight.engine.gaps import Flag, find_flags

log = logging.getLogger("wardsight.scan")

FLAGS_DDL = """CREATE SCHEMA IF NOT EXISTS ops;
CREATE TABLE IF NOT EXISTS ops.flags (encounter_id VARCHAR, split VARCHAR, condition VARCHAR,
    kind VARCHAR, icd10 VARCHAR, detail VARCHAR, evidence VARCHAR,
    drg_now INTEGER, drg_now_desc VARCHAR, severity_now VARCHAR,
    drg_if_resolved INTEGER, drg_if_resolved_desc VARCHAR, severity_if_resolved VARCHAR)"""


def scan(con: duckdb.DuckDBPyConnection, split: str) -> list[Flag]:
    con.execute(FLAGS_DDL)
    con.execute("DELETE FROM ops.flags WHERE split = ?", [split])
    charts = load_charts(con, split)
    if charts and not any(c.notes for c in charts):
        raise SystemExit("No notes found. Run `wardsight-notes --template` (or the LLM writer) first.")
    flags = [f for chart in charts for f in find_flags(chart)]
    con.executemany("INSERT INTO ops.flags VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        (f.encounter_id, split, f.condition, f.kind, f.icd10, f.detail, f.evidence,
         f.drg_now.drg, f.drg_now.description, f.drg_now.severity,
         f.drg_if_resolved.drg, f.drg_if_resolved.description, f.drg_if_resolved.severity)
        for f in flags])
    log.info("%s: %d charts scanned, %d flags %s", split, len(charts), len(flags),
             dict(Counter(f.kind for f in flags)))
    return flags


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan charts for documentation gaps.")
    parser.add_argument("--db", type=Path, default=Path("data/wardsight.duckdb"))
    parser.add_argument("--split", default="dev", choices=("dev", "heldout"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with duckdb.connect(str(args.db)) as con:
        scan(con, args.split)


if __name__ == "__main__":
    main()
