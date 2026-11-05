"""Rebuild Encounter records from the database (for steps that run after the factory)."""

from __future__ import annotations

from collections import defaultdict

import duckdb

from wardsight.models import Encounter, Event, Mention, PatientSeed
from wardsight.store import SIM_START


def load_encounters(con: duckdb.DuckDBPyConnection) -> list[Encounter]:
    chronic: dict[str, set[str]] = defaultdict(set)
    flag_by_code = {"I10": "htn", "E11.9": "dm2", "N18.30": "ckd3", "J44.9": "copd"}
    for pid, code in con.execute("SELECT patient_id, icd10 FROM ehr.problem_list").fetchall():
        chronic[pid].add(flag_by_code[code])

    events: dict[str, list[Event]] = defaultdict(list)
    for eid, t, kind, key, value, text in con.execute(
            "SELECT encounter_id, t_hours, kind, key, value, text FROM ehr.events ORDER BY encounter_id, t_hours"
    ).fetchall():
        events[eid].append(Event(t, kind, key, value, text))

    mentions: dict[str, list[Mention]] = defaultdict(list)
    for eid, code, term, assertion in con.execute(
            "SELECT encounter_id, icd10, term, assertion FROM truth.doc_spec").fetchall():
        mentions[eid].append(Mention(code, term, assertion))

    rows = con.execute("""
        SELECT e.encounter_id, e.split, e.patient_id, p.age, p.sex, p.source, e.admit_ts, e.los_days,
               s.principal_icd10, s.condition, s.evidence, s.grp
        FROM ehr.encounters e JOIN ehr.patients p USING (patient_id)
        JOIN truth.scenarios s USING (encounter_id) ORDER BY e.encounter_id""").fetchall()
    return [
        Encounter(eid, split, PatientSeed(pid, age, sex, frozenset(chronic[pid]), source),
                  int((admit - SIM_START).total_seconds() // 3600), los, principal, condition,
                  evidence, grp, tuple(events[eid]), tuple(mentions[eid]))
        for eid, split, pid, age, sex, source, admit, los, principal, condition, evidence, grp in rows
    ]
