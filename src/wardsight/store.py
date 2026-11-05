"""DuckDB storage.

Two schemas, kept apart on purpose:
- `ehr`   = what a hospital system would hold. Engines may read ONLY this.
- `truth` = scenario labels, the answer key and the note specs. Only the
            benchmark and the note writer may read it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import duckdb

from wardsight.codes import CHRONIC_ICD10, ICD10, LOINC, PRINCIPAL_TERMS
from wardsight.models import AnswerKeyRow, Encounter

SIM_START = datetime(2026, 3, 1)

SCHEMA = """
CREATE SCHEMA IF NOT EXISTS ehr;
CREATE SCHEMA IF NOT EXISTS truth;
CREATE TABLE ehr.patients (patient_id VARCHAR PRIMARY KEY, age INTEGER, sex VARCHAR, source VARCHAR);
CREATE TABLE ehr.problem_list (patient_id VARCHAR, icd10 VARCHAR, description VARCHAR);
CREATE TABLE ehr.encounters (encounter_id VARCHAR PRIMARY KEY, split VARCHAR, patient_id VARCHAR,
    admit_ts TIMESTAMP, discharge_ts TIMESTAMP, los_days INTEGER, reason_for_admission VARCHAR);
CREATE TABLE ehr.events (encounter_id VARCHAR, ts TIMESTAMP, t_hours DOUBLE, kind VARCHAR,
    key VARCHAR, loinc VARCHAR, name VARCHAR, value DOUBLE, unit VARCHAR, text VARCHAR);
CREATE TABLE truth.scenarios (encounter_id VARCHAR PRIMARY KEY, split VARCHAR, grp VARCHAR,
    condition VARCHAR, evidence VARCHAR, principal_icd10 VARCHAR);
CREATE TABLE truth.doc_spec (encounter_id VARCHAR, icd10 VARCHAR, term VARCHAR, assertion VARCHAR);
CREATE TABLE truth.answer_key (encounter_id VARCHAR PRIMARY KEY, split VARCHAR, grp VARCHAR,
    condition VARCHAR, evidence VARCHAR, true_icd10 VARCHAR, documented_icd10 VARCHAR,
    expected_flag VARCHAR, detail VARCHAR);
"""


def admit_ts(enc: Encounter) -> datetime:
    return SIM_START + timedelta(hours=enc.admit_hour)


def write_db(path: Path, encounters: list[Encounter], answers: list[AnswerKeyRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    with duckdb.connect(str(path)) as con:
        con.execute(SCHEMA)
        con.executemany("INSERT INTO ehr.patients VALUES (?, ?, ?, ?)",
                        [(e.patient.patient_id, e.patient.age, e.patient.sex, e.patient.source)
                         for e in encounters])
        con.executemany("INSERT INTO ehr.problem_list VALUES (?, ?, ?)",
                        [(e.patient.patient_id, CHRONIC_ICD10[c], ICD10[CHRONIC_ICD10[c]])
                         for e in encounters for c in sorted(e.patient.chronic)])
        con.executemany("INSERT INTO ehr.encounters VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [(e.encounter_id, e.split, e.patient.patient_id, admit_ts(e),
                          admit_ts(e) + timedelta(days=e.los_days), e.los_days,
                          PRINCIPAL_TERMS[e.principal_icd10]) for e in encounters])
        con.executemany("INSERT INTO ehr.events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [_event_row(e, ev) for e in encounters for ev in e.events])
        con.executemany("INSERT INTO truth.scenarios VALUES (?, ?, ?, ?, ?, ?)",
                        [(e.encounter_id, e.split, e.group, e.condition, e.evidence,
                          e.principal_icd10) for e in encounters])
        con.executemany("INSERT INTO truth.doc_spec VALUES (?, ?, ?, ?)",
                        [(e.encounter_id, m.icd10, m.term, m.assertion)
                         for e in encounters for m in e.mentions])
        con.executemany("INSERT INTO truth.answer_key VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [(a.encounter_id, a.split, a.group, a.condition, a.evidence, a.true_icd10,
                          a.documented_icd10, a.expected_flag, a.detail) for a in answers])


def _event_row(enc: Encounter, ev) -> tuple:
    loinc, name, unit = LOINC.get(ev.key, (None, ev.text, None))
    ts = admit_ts(enc) + timedelta(hours=ev.t_hours)
    return (enc.encounter_id, ts, ev.t_hours, ev.kind, ev.key, loinc, name, ev.value, unit, ev.text)
