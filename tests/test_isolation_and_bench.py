"""The engine must not see the answers, and the held-out set is scored only once."""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

import duckdb
import pytest
from counts import DEV_FLAGS

from wardsight.bench import check_seal, run, seal_heldout
from wardsight.engine.scan import scan
from wardsight.factory import run as build_ward
from wardsight.notes.template import write_template_notes
from wardsight.queries.draft import template_drafter
from wardsight.queries.run import draft_all
from wardsight.reload import load_encounters

ENGINE = Path(__file__).parents[1] / "src" / "wardsight" / "engine"
FORBIDDEN_MODULES = {"wardsight.scenarios", "wardsight.planter", "wardsight.reload", "wardsight.bench",
                     "wardsight.notes.spec", "wardsight.notes.template", "wardsight.notes.writer"}


def test_engine_never_imports_the_generator_or_reads_truth():
    for path in [*ENGINE.glob("*.py"), *ENGINE.parent.joinpath("queries").glob("*.py")]:
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


def test_every_dev_flag_gets_a_compliant_query(ward: Path):
    with duckdb.connect(str(ward)) as con:
        results = draft_all(con, "dev", template_drafter, "template", 1)
        statuses = {r[0] for r in con.execute("SELECT DISTINCT status FROM ops.queries").fetchall()}
    assert len(results) == DEV_FLAGS and all(r.lint.ok for r in results)
    assert statuses == {"pending_review"}


def test_heldout_is_scored_once(ward: Path, tmp_path: Path):
    seal = tmp_path / "heldout.seal.json"
    with duckdb.connect(str(ward)) as con:
        seal_heldout(con, seal)
        with pytest.raises(SystemExit, match="--final"):
            run(con, "heldout", final=False, seal=seal)
        run(con, "heldout", final=True, seal=seal)
        with pytest.raises(SystemExit, match="already scored"):
            run(con, "heldout", final=True, seal=seal)


def test_final_exam_refuses_unsealed_or_changed_heldout(ward: Path, tmp_path: Path):
    seal, copy = tmp_path / "heldout.seal.json", tmp_path / "ward.duckdb"
    shutil.copy(ward, copy)  # the shared fixture is not modified
    with duckdb.connect(str(copy)) as con:
        with pytest.raises(SystemExit, match="not sealed"):
            check_seal(con, seal)
        seal_heldout(con, seal)
        check_seal(con, seal)                              # untouched: passes
        with pytest.raises(SystemExit, match="already exists"):
            seal_heldout(con, seal)                        # a seal is never silently overwritten
        con.execute("UPDATE truth.answer_key SET expected_flag = 'none' "
                    "WHERE encounter_id = (SELECT min(encounter_id) FROM truth.answer_key WHERE split = 'heldout')")
        with pytest.raises(SystemExit, match="changed since they were sealed"):
            run(con, "heldout", final=True, seal=seal)
