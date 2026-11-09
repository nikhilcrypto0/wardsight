"""FHIR round trip: export every chart to FHIR R4, import it back, get the same evidence results."""

from __future__ import annotations

import duckdb
import pytest

from wardsight.engine.chart import load_charts
from wardsight.engine.evidence import RULES
from wardsight.factory import run as build_ward
from wardsight.fhir_export import encounter_bundle
from wardsight.fhir_import import bundle_to_chart, evidence_report
from wardsight.reload import load_encounters


@pytest.fixture(scope="module")
def ward(tmp_path_factory):
    out = tmp_path_factory.mktemp("fhir")
    build_ward(out, seed=55, synthea_dir=None)
    with duckdb.connect(str(out / "wardsight.duckdb"), read_only=True) as con:
        encounters = {e.encounter_id: e for e in load_encounters(con) if e.split == "dev"}
        charts = {c.encounter_id: c for c in load_charts(con, "dev")}
    return encounters, charts


def test_round_trip_gives_identical_evidence_for_every_chart(ward):
    encounters, charts = ward
    mismatches = []
    for enc_id, enc in encounters.items():
        imported = bundle_to_chart(encounter_bundle(enc), enc_id)
        for condition, rule in RULES.items():
            direct, via_fhir = rule(charts[enc_id]), rule(imported)
            if direct.met != via_fhir.met:
                mismatches.append((enc_id, condition, direct.met, via_fhir.met))
    assert mismatches == [], mismatches[:5]


def test_round_trip_keeps_values_times_and_problem_list(ward):
    encounters, charts = ward
    enc_id = next(iter(encounters))
    imported = bundle_to_chart(encounter_bundle(encounters[enc_id]), enc_id)
    original = charts[enc_id]
    assert imported.series("creatinine") == original.series("creatinine")
    assert imported.series("map") == original.series("map")
    assert imported.problem_list == original.problem_list
    assert imported.los_days == original.los_days


def test_times_with_offsets_line_up_in_utc():
    from wardsight.fhir_import import _when

    assert _when("2026-03-01T05:00:00+05:00") == _when("2026-03-01T00:00:00Z")
    assert _when("2026-03-01") is not None


def test_report_shape():
    resources = [
        {"resourceType": "Patient", "gender": "female", "birthDate": "1950-01-01"},
        {"resourceType": "Observation", "effectiveDateTime": "2026-03-01T01:00:00Z",
         "code": {"coding": [{"system": "http://loinc.org", "code": "2951-2"}]},
         "valueQuantity": {"value": 126}},
    ]
    from wardsight.fhir_import import resources_to_chart

    report = evidence_report(resources_to_chart(resources))
    assert report["measured"] == ["sodium"] and set(report["rules"]) == set(RULES)
    assert report["rules"]["hyponatremia"]["met"] is False  # low once, never treated or monitored
