"""End to end: the factory writes a valid database and valid FHIR R4 bundles."""

from __future__ import annotations

import json

import duckdb
import pytest
from fhir.resources.R4B.bundle import Bundle

from wardsight.factory import run


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    path = tmp_path_factory.mktemp("factory")
    run(path, seed=11, synthea_dir=None)
    return path


def test_database_tables(out):
    with duckdb.connect(str(out / "wardsight.duckdb"), read_only=True) as con:
        def count(sql: str) -> int:
            return con.execute(sql).fetchone()[0]

        assert count("SELECT count(*) FROM ehr.encounters") == 300
        assert count("SELECT count(*) FROM truth.answer_key") == 300
        assert count("SELECT count(*) FROM ehr.events WHERE kind = 'lab'") > 3000
        assert count("SELECT count(*) FROM ehr.events WHERE loinc IS NULL AND kind = 'vital'") == 0
        overlap = """SELECT count(*) FROM ehr.encounters d JOIN ehr.encounters h
                     ON d.patient_id = h.patient_id AND d.split = 'dev' AND h.split = 'heldout'"""
        assert count(overlap) == 0


def test_engine_schema_hides_truth(out):
    with duckdb.connect(str(out / "wardsight.duckdb"), read_only=True) as con:
        ehr_columns = {r[0] for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'ehr'").fetchall()}
    assert not ehr_columns & {"grp", "condition", "evidence", "expected_flag", "true_icd10"}


def test_fhir_bundles_validate(out):
    bundles = sorted((out / "fhir").rglob("*.json"))
    assert len(bundles) == 300
    for path in bundles[::25]:
        bundle = Bundle.model_validate(json.loads(path.read_text()))
        kinds = {e.resource.__resource_type__ for e in bundle.entry}
        assert {"Patient", "Encounter", "Observation"} <= kinds
