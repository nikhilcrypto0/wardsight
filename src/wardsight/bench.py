"""Benchmark: score the engine's flags against the answer key.

The only module (besides the note writer) allowed to read `truth`.
The held-out split may be scored ONCE; a second attempt is refused so the
published numbers cannot be tuned against it.

    uv run wardsight-bench --split dev
    uv run wardsight-bench --split heldout --final     # once, at the very end
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb

log = logging.getLogger("wardsight.bench")

HELDOUT_DDL = """CREATE SCHEMA IF NOT EXISTS ops;
CREATE TABLE IF NOT EXISTS ops.heldout_runs (ts TIMESTAMP, caught INTEGER, planted INTEGER,
    false_alarms INTEGER)"""


@dataclass(frozen=True)
class Score:
    split: str
    planted: int        # charts whose answer key expects a flag
    caught: int         # of those, flagged with the right condition AND kind
    false_alarms: int   # flags that match no planted gap
    quiet_charts: int   # charts that should raise no flag
    by_group: tuple[tuple[str, int, int, int], ...]  # (group, charts, correct, flags raised)

    @property
    def recall(self) -> float:
        return self.caught / self.planted if self.planted else 0.0

    @property
    def false_alarms_per_100(self) -> float:
        return 100 * self.false_alarms / self.quiet_charts if self.quiet_charts else 0.0


def _rows(con: duckdb.DuckDBPyConnection, split: str) -> list[tuple]:
    return con.execute("""
        SELECT a.encounter_id, a.grp, a.condition, a.expected_flag,
               list(f.condition || ':' || f.kind) FILTER (WHERE f.kind IS NOT NULL) AS raised
        FROM truth.answer_key a
        LEFT JOIN ops.flags f ON f.encounter_id = a.encounter_id AND f.split = a.split
        WHERE a.split = ? GROUP BY ALL ORDER BY a.encounter_id""", [split]).fetchall()


def score(con: duckdb.DuckDBPyConnection, split: str) -> Score:
    rows = _rows(con, split)
    planted = caught = false_alarms = quiet = 0
    groups: dict[str, list[int]] = {}
    for _, grp, condition, expected, raised in rows:
        raised = raised or []
        want = f"{condition}:{expected}" if expected != "none" else None
        hit = want in raised
        planted += want is not None
        caught += hit
        quiet += want is None
        false_alarms += len([r for r in raised if r != want])
        g = groups.setdefault(grp, [0, 0, 0])
        g[0] += 1
        g[1] += hit if want else not raised
        g[2] += len(raised)
    return Score(split, planted, caught, false_alarms, quiet,
                 tuple((k, *v) for k, v in sorted(groups.items())))


def mistakes(con: duckdb.DuckDBPyConnection, split: str) -> list[dict]:
    """Every chart the engine got wrong: a planted gap it missed, or a flag it should not have raised."""
    found = []
    for encounter_id, grp, condition, expected, raised in _rows(con, split):
        raised = raised or []
        want = f"{condition}:{expected}" if expected != "none" else None
        missed = want is not None and want not in raised
        extra = [r for r in raised if r != want]
        if missed or extra:
            found.append({"encounter_id": encounter_id, "group": grp, "condition": condition,
                          "expected": expected, "missed": missed, "extra": extra})
    return found


SEAL = Path(__file__).resolve().parents[2] / "heldout.seal.json"
# What the final exam is: the held-out charts and their answer key. Notes are excluded on purpose,
# because they are written later (template or AI) from these same charts.
SEALED_TABLES = ("ehr.encounters", "ehr.events", "truth.scenarios", "truth.answer_key")


def heldout_fingerprint(con: duckdb.DuckDBPyConnection) -> dict:
    prints = {}
    for table in SEALED_TABLES:
        rows = con.execute(f"""SELECT * FROM {table} WHERE encounter_id IN
                                   (SELECT encounter_id FROM ehr.encounters WHERE split = 'heldout')
                               ORDER BY ALL""").fetchall()
        prints[table] = {"rows": len(rows), "sha256": hashlib.sha256(repr(rows).encode()).hexdigest()}
    return prints


def seal_heldout(con: duckdb.DuckDBPyConnection, seal: Path = SEAL) -> dict:
    """Pin the final exam. Refuses to overwrite: changing a seal must be a visible act in git."""
    if seal.exists():
        raise SystemExit(f"{seal.name} already exists. The held-out set is sealed; delete the file in a "
                         "reviewed commit only if the exam itself has to change.")
    prints = heldout_fingerprint(con)
    seal.write_text(json.dumps({"sealed": datetime.now().date().isoformat(), "tables": prints}, indent=1) + "\n")
    return prints


def check_seal(con: duckdb.DuckDBPyConnection, seal: Path = SEAL) -> None:
    if not seal.exists():
        raise SystemExit("The held-out set is not sealed. Run `wardsight-bench --seal-heldout` first.")
    if json.loads(seal.read_text())["tables"] != heldout_fingerprint(con):
        raise SystemExit("The held-out charts or answer key changed since they were sealed. Not scoring.")


def run(con: duckdb.DuckDBPyConnection, split: str, final: bool, seal: Path = SEAL) -> Score:
    if split == "heldout":
        if not final:
            raise SystemExit("The held-out split is scored once, at the end. Pass --final to do it.")
        check_seal(con, seal)
        con.execute(HELDOUT_DDL)
        if con.execute("SELECT count(*) FROM ops.heldout_runs").fetchone()[0]:
            raise SystemExit("The held-out split was already scored. Its numbers are final.")
    result = score(con, split)
    if split == "heldout":
        con.execute("INSERT INTO ops.heldout_runs VALUES (?, ?, ?, ?)",
                    [datetime.now(), result.caught, result.planted, result.false_alarms])
    return result


def report(s: Score) -> str:
    lines = [(f"{s.split}: caught {s.caught} of {s.planted} planted gaps ({s.recall:.0%}); "
             f"{s.false_alarms} false alarms ({s.false_alarms_per_100:.1f} per 100 quiet charts)"),
             f"{'group':<12}{'charts':>8}{'correct':>9}{'flags':>7}"]
    lines += [f"{g:<12}{n:>8}{ok:>9}{fl:>7}" for g, n, ok, fl in s.by_group]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score engine flags against the answer key.")
    parser.add_argument("--db", type=Path, default=Path("data/wardsight.duckdb"))
    parser.add_argument("--split", default="dev", choices=("dev", "heldout"))
    parser.add_argument("--final", action="store_true", help="required to score the held-out split")
    parser.add_argument("--seal-heldout", action="store_true",
                        help="pin the held-out charts and answer key (does not score anything)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with duckdb.connect(str(args.db)) as con:
        if args.seal_heldout:
            log.info("sealed: %s", {t: v["rows"] for t, v in seal_heldout(con).items()})
            return
        log.info(report(run(con, args.split, args.final)))


if __name__ == "__main__":
    main()
