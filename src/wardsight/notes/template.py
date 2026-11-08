"""Template notes: plain-code stand-in for the LLM notes (no API, no cost).

Lets the detection engine be built and tested offline. Every note set passes
the same leak check as the LLM notes. Replace with `wardsight-notes` (LLM)
for realistic wording; the engine reads ehr.notes either way.
"""

from __future__ import annotations

import random
from datetime import timedelta

import duckdb

from wardsight.codes import PRINCIPAL_TERMS
from wardsight.models import Encounter
from wardsight.notes.spec import Note, NoteSet, chart_digest, check_notes

NOTES_DDL = """CREATE TABLE IF NOT EXISTS ehr.notes (encounter_id VARCHAR, note_type VARCHAR,
    hospital_day INTEGER, ts TIMESTAMP, text VARCHAR, source VARCHAR)"""

OPENERS = ("Patient seen and examined at bedside.", "Chart, labs and overnight events reviewed.",
           "Patient interviewed and examined; nursing notes reviewed.")


def template_notes(enc: Encounter, rng: random.Random) -> NoteSet:
    digest_lines = chart_digest(enc).splitlines()
    first_day = "\n".join(line for line in digest_lines if line.startswith("Day 0"))
    later = "\n".join(line for line in digest_lines if line.startswith("Day 1"))
    assessment = " ".join(f"{m.term[0].upper()}{m.term[1:]}." for m in enc.mentions)
    reason = PRINCIPAL_TERMS[enc.principal_icd10]
    who = f"{enc.patient.age}-year-old {enc.patient.sex}"
    last_day = enc.los_days - 1
    texts = {
        "history_and_physical": (0, (f"HISTORY AND PHYSICAL. {rng.choice(OPENERS)} {who} admitted for {reason}. "
                                    f"Admission data:\n{first_day}\nAssessment and plan: {assessment}")),
        "progress_note": (1, (f"PROGRESS NOTE, hospital day 1. {rng.choice(OPENERS)} Data:\n{later}\n"
                             f"Assessment and plan: {assessment} Continue current management.")),
        "discharge_summary": (last_day, (f"DISCHARGE SUMMARY. {who}, length of stay {enc.los_days} days. "
                                        f"Hospital course: treated per the plan above with daily labs and "
                                        f"vital signs; stable for discharge. Medications reconciled and "
                                        f"return precautions reviewed. Discharge diagnoses: {assessment} "
                                        f"Follow up with primary care in one week. {rng.choice(OPENERS)}")),
    }
    return NoteSet(notes=[Note(note_type=k, hospital_day=d, text=t) for k, (d, t) in texts.items()])


def write_template_notes(con: duckdb.DuckDBPyConnection, encounters: list[Encounter], seed: int) -> int:
    """Replace all notes with template notes. Returns the number of charts written."""
    con.execute(NOTES_DDL)
    con.execute("DELETE FROM ehr.notes")
    rng = random.Random(f"{seed}-template-notes")
    rows = []
    for enc in encounters:
        note_set = template_notes(enc, rng)
        result = check_notes(note_set, enc.mentions)
        if not result.ok:
            raise ValueError(f"template notes for {enc.encounter_id} failed the check: {result.problems}")
        admit = con.execute("SELECT admit_ts FROM ehr.encounters WHERE encounter_id = ?",
                            [enc.encounter_id]).fetchone()[0]
        rows += [(enc.encounter_id, n.note_type, n.hospital_day,
                  admit + timedelta(days=n.hospital_day, hours=10), n.text, "template")
                 for n in note_set.notes]
    con.executemany("INSERT INTO ehr.notes VALUES (?, ?, ?, ?, ?, ?)", rows)
    return len(encounters)
