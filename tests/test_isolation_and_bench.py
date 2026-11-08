"""The engine must not see the answers, and the held-out set is scored only once."""

from __future__ import annotations

import ast
from pathlib import Path

import duckdb
import pytest

from wardsight.bench import run
from wardsight.engine.scan import scan
from wardsight.factory import run as build_ward
from wardsight.notes.template import write_template_notes
from wardsight.reload import load_encounters

ENGINE = Path(__file__).parents[1] / "src" / "wardsight" / "engine"
FORBIDDEN_MODULES = {"wardsight.scenarios", "wardsight.planter", "wardsight.reload", "wardsight.bench",
                     "wardsight.notes.spec", "wardsight.notes.template", "wardsight.notes.writer"}


def test_engine_never_imports_the_generator_or_reads_truth():
    for path in ENGINE.glob("*.py"):
        source = path.read_text()
        assert "truth." not in source, f"{path.name} reads the truth schema"
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module not in FORBIDDEN_MODULES, f"{path.name} imports {node.module}"


@pytest.fixture(scope="module")
def ward(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("ward")
    build_ward(out, seed=21, synthea_dir=None)
    db = out / "wardsight.duckdb"
    with duckdb.connect(str(db)) as con:
        write_template_notes(con, load_encounters(con), seed=21)
        scan(con, "dev")
        scan(con, "heldout")
    return db


def test_dev_score_on_template_notes(ward: Path):
    with duckdb.connect(str(ward)) as con:
        result = run(con, "dev", final=False)
    assert result.recall == 1.0 and result.false_alarms == 0


def test_heldout_is_scored_once(ward: Path):
    with duckdb.connect(str(ward)) as con:
        with pytest.raises(SystemExit, match="--final"):
            run(con, "heldout", final=False)
        run(con, "heldout", final=True)
        with pytest.raises(SystemExit, match="already scored"):
            run(con, "heldout", final=True)
