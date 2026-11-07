"""Synthea condition mapping must be narrow: wrong flags change the lab baselines."""

from __future__ import annotations

import json
from pathlib import Path

from wardsight.patients import _chronic_flags, _excluded, synthea_patients


def test_prediabetes_and_early_ckd_set_no_flags():
    assert _chronic_flags(["prediabetes (finding)", "chronic kidney disease stage 2 (disorder)"]) == frozenset()


def test_real_conditions_map():
    texts = ["diabetes mellitus type 2 (disorder)", "essential hypertension (disorder)",
             "chronic kidney disease stage 3 (disorder)", "pulmonary emphysema (disorder)"]
    assert _chronic_flags(texts) == {"dm2", "htn", "ckd3", "copd"}


def test_sleep_apnea_is_not_copd():
    assert _chronic_flags(["obstructive sleep apnea syndrome (disorder)"]) == frozenset()


def test_exclusions():
    assert _excluded(["chronic kidney disease stage 4 (disorder)"])
    assert _excluded(["history of renal transplant (situation)"])
    assert _excluded(["chronic congestive heart failure (disorder)"])
    assert not _excluded(["chronic kidney disease stage 3 (disorder)"])


def _bundle(birth: str, conditions: list[str]) -> dict:
    entries = [{"resource": {"resourceType": "Patient", "gender": "male", "birthDate": birth}}]
    entries += [{"resource": {"resourceType": "Condition", "code": {"text": t}}} for t in conditions]
    return {"resourceType": "Bundle", "entry": entries}


def test_loader_skips_excluded_and_young(tmp_path: Path):
    (tmp_path / "a.json").write_text(json.dumps(_bundle("1950-01-01", ["Prediabetes (finding)"])))
    (tmp_path / "b.json").write_text(json.dumps(_bundle("1950-01-01", ["End-stage renal disease (disorder)"])))
    (tmp_path / "c.json").write_text(json.dumps(_bundle("2000-01-01", [])))
    (tmp_path / "d.json").write_text(json.dumps(_bundle("1960-05-05", ["Diabetes mellitus type 2 (disorder)"])))
    seeds = synthea_patients(tmp_path, 2)
    assert [s.chronic for s in seeds] == [frozenset(), frozenset({"dm2"})]
