"""Data factory CLI: patients -> scenarios -> planted gaps -> DuckDB + FHIR.

    uv run wardsight-factory                      # built-in patients
    uv run wardsight-factory --synthea data/synthea/fhir
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from pathlib import Path

from wardsight.fhir_export import write_bundles
from wardsight.patients import builtin_patients, synthea_patients
from wardsight.planter import EXTRA_COUNTS, GROUP_COUNTS, build_extra, build_split
from wardsight.store import write_db

log = logging.getLogger("wardsight.factory")
DEFAULT_SEED = 7


def run(out: Path, seed: int, synthea_dir: Path | None) -> dict[str, Counter]:
    sizes = {split: sum(c.values()) for split, c in GROUP_COUNTS.items()}
    total = sum(sizes.values())
    extra = sum(sum(c.values()) for c in EXTRA_COUNTS.values())
    patients = (synthea_patients(synthea_dir, total + extra) if synthea_dir
                else builtin_patients(total + extra, seed))

    encounters, answers, start = [], [], 0
    for split, size in sizes.items():
        enc, ans = build_split(split, patients[start:start + size], seed)
        encounters += enc
        answers += ans
        start += size
    # U3 charts come last, from patients after the held-out slice, so the originals never shift
    for split, counts in EXTRA_COUNTS.items():  # dev batch first, then held-out: originals never shift
        size = sum(counts.values())
        enc, ans = build_extra(split, patients[start:start + size], seed)
        encounters += enc
        answers += ans
        start += size

    write_db(out / "wardsight.duckdb", encounters, answers)
    write_bundles(out / "fhir", encounters)
    summary = {split: Counter(a.group for a in answers if a.split == split) for split in sizes}
    for split, counts in summary.items():
        log.info("%s: %d charts %s", split, sum(counts.values()), dict(counts))
    log.info("events: %d, patients from %s", sum(len(e.events) for e in encounters),
             "synthea" if synthea_dir else "builtin generator")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the synthetic ward and its answer key.")
    parser.add_argument("--out", type=Path, default=Path("data"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--synthea", type=Path, default=None,
                        help="folder of Synthea FHIR patient bundles; omit for built-in patients")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run(args.out, args.seed, args.synthea)


if __name__ == "__main__":
    main()
