"""Working DRG vs final DRG: the billing category at every documentation point of a stay.

CDI teams track a "working" MS-DRG while the patient is in the hospital (what the record
supports so far) and the "final" one at discharge, and want to know which note changed it.
This replays the record note by note: after each note (and each physician addendum) it
regroups the documented diagnoses, records what that note added or removed, and shows what
the category would be if the gaps open at that moment were resolved.

Reads only the chart (events and notes), like the rest of the engine.
"""

from __future__ import annotations

from dataclasses import replace

from wardsight.codes import ICD10
from wardsight.engine.chart import Chart, NoteText
from wardsight.engine.drg import coded_diagnoses, group
from wardsight.engine.drg_table import facts
from wardsight.engine.gaps import find_flags
from wardsight.engine.ur import codes_if_resolved

NOTE_HOUR = 10       # notes are written mid-morning
ADDENDUM_HOUR = 16   # a physician answers a query in the afternoon
ORDER = {"history_and_physical": 0, "progress_note": 1, "discharge_summary": 2, "addendum": 3}


def _hour(note: NoteText) -> int:
    return note.hospital_day * 24 + (ADDENDUM_HOUR if note.note_type == "addendum" else NOTE_HOUR)


def _codes(items: set[str]) -> list[dict]:
    return [{"code": c, "name": ICD10.get(c, c)} for c in sorted(items)]


def drg_timeline(chart: Chart) -> list[dict]:
    """One step at admission, then one per note in the order they were written."""
    notes = sorted(chart.notes, key=lambda n: (n.hospital_day, ORDER.get(n.note_type, 9)))
    steps: list[dict] = []
    before: set[str] = set()
    for i in range(len(notes) + 1):
        hour = _hour(notes[i - 1]) if i else 0
        so_far = replace(chart, notes=tuple(notes[:i]), events=tuple(e for e in chart.events if e.t_hours <= hour))
        codes = coded_diagnoses(so_far)
        now = group(so_far, codes)
        flags = find_flags(so_far)
        potential = group(so_far, codes_if_resolved(so_far, flags)) if flags else now
        weight = facts(now.drg)
        steps.append({
            "hour": hour, "day": notes[i - 1].hospital_day if i else 0,
            "source": notes[i - 1].note_type if i else "admission",
            "drg": now.drg, "description": now.description, "severity": now.severity,
            "weight": weight.weight if weight else None,
            "added": _codes(codes - before) if i else [], "removed": _codes(before - codes),
            "open_gaps": len(flags),
            "potential_drg": potential.drg, "potential_description": potential.description,
        })
        before = codes
    return steps
