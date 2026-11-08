"""Load one encounter the way a hospital system would see it: `ehr` schema only.

The detection engine never reads `truth` (answer key, scenario labels, note
specs). tests/test_engine_isolation.py enforces that.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import duckdb

from wardsight.models import Event


@dataclass(frozen=True)
class NoteText:
    note_type: str
    hospital_day: int
    text: str


@dataclass(frozen=True)
class Chart:
    encounter_id: str
    split: str
    age: int
    sex: str
    los_days: int
    reason_for_admission: str
    problem_list: tuple[str, ...]  # ICD-10 codes of chronic conditions
    events: tuple[Event, ...]
    notes: tuple[NoteText, ...]

    def series(self, key: str) -> list[tuple[float, float]]:
        """(hour, value) for a measured analyte, in time order."""
        return [(e.t_hours, e.value) for e in self.events if e.key == key and e.value is not None]

    def texts(self, *kinds: str) -> list[tuple[float, str]]:
        """(hour, text) of orders, meds, imaging and text results, optionally by kind."""
        return [(e.t_hours, e.text) for e in self.events if e.text and (not kinds or e.kind in kinds)]


def load_charts(con: duckdb.DuckDBPyConnection, split: str | None = None) -> list[Chart]:
    where, params = ("WHERE e.split = ?", [split]) if split else ("", [])
    encounters = con.execute(f"""
        SELECT e.encounter_id, e.split, p.age, p.sex, e.los_days, e.reason_for_admission, e.patient_id
        FROM ehr.encounters e JOIN ehr.patients p USING (patient_id) {where}
        ORDER BY e.encounter_id""", params).fetchall()

    problems: dict[str, list[str]] = defaultdict(list)
    for pid, code in con.execute("SELECT patient_id, icd10 FROM ehr.problem_list").fetchall():
        problems[pid].append(code)

    events: dict[str, list[Event]] = defaultdict(list)
    for eid, t, kind, key, value, text in con.execute(
            "SELECT encounter_id, t_hours, kind, key, value, text FROM ehr.events "
            "ORDER BY encounter_id, t_hours").fetchall():
        events[eid].append(Event(t, kind, key, value, text))

    notes: dict[str, list[NoteText]] = defaultdict(list)
    has_notes = con.execute("SELECT count(*) FROM information_schema.tables "
                            "WHERE table_schema = 'ehr' AND table_name = 'notes'").fetchone()[0]
    if has_notes:
        for eid, note_type, day, text in con.execute(
                "SELECT encounter_id, note_type, hospital_day, text FROM ehr.notes "
                "ORDER BY encounter_id, hospital_day").fetchall():
            notes[eid].append(NoteText(note_type, day, text))

    return [Chart(eid, sp, age, sex, los, reason, tuple(sorted(problems[pid])), tuple(events[eid]),
                  tuple(notes[eid]))
            for eid, sp, age, sex, los, reason, pid in encounters]
