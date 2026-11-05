"""Note specs: what the LLM is told, and the check its output must pass.

The check is the guard that keeps the benchmark honest. A note that names a
diagnosis the planter left out would silently turn a "missing" chart into a
"documented" one, so every note is scanned for every target condition that
is not supposed to be there.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from wardsight.models import Encounter, Event, Mention

# Words that would count as documenting each target condition.
CONDITION_TERMS = {
    "N17.9": ("acute kidney injury", "aki", "acute renal failure", "kidney injury"),
    "A41.9": ("sepsis", "septic", "septicemia"),
    "E87.1": ("hyponatremia", "hyponatraemia"),
    "D62": ("blood loss anemia", "posthemorrhagic anemia", "acute anemia"),
    "J96.01": ("respiratory failure",),
    "I50.21": ("systolic heart failure", "hfref", "acute heart failure",
               "reduced ejection fraction heart failure", "acute chf"),
    "I50.9": ("heart failure", "chf"),
}
HEART_FAILURE = {"I50.21", "I50.9"}

NOTE_TYPES = ("history_and_physical", "progress_note", "discharge_summary")


class Note(BaseModel):
    note_type: str = Field(description="history_and_physical | progress_note | discharge_summary")
    hospital_day: int = Field(ge=0)
    text: str = Field(min_length=200)


class NoteSet(BaseModel):
    notes: list[Note]


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    problems: tuple[str, ...]


SYSTEM_PROMPT = """You write realistic inpatient physician notes for a SYNTHETIC teaching dataset.
Write exactly three notes: history_and_physical (day 0), progress_note (day 1 or 2),
discharge_summary (last day). Use normal clinical style: HPI, exam, data, assessment and plan.
Base every number on the chart data given. Diagnosis rules are strict:
- In the assessment you MUST name each REQUIRED diagnosis using its exact wording.
- You MUST include each REQUIRED NEGATION sentence fragment word for word.
- Do NOT name, suggest, or rule out any other diagnosis or syndrome. Describe findings
  (numbers, symptoms, treatments) without labeling them with a diagnosis."""


def chart_digest(enc: Encounter) -> str:
    """Compact, model-readable summary of the chart events."""
    lines = [f"Patient: {enc.patient.age}-year-old {enc.patient.sex}. Length of stay {enc.los_days} days."]
    by_day: dict[int, list[Event]] = {}
    for ev in enc.events:
        by_day.setdefault(int(ev.t_hours // 24), []).append(ev)
    for day in sorted(by_day):
        labs = _summarize(by_day[day], "lab")
        vitals = _summarize(by_day[day], "vital")
        actions = sorted({e.text for e in by_day[day] if e.kind in ("med", "order", "imaging") and e.text})
        reports = sorted({e.text for e in by_day[day] if e.kind == "lab" and e.text})
        lines.append(f"Day {day}: labs {labs}; vitals {vitals}")
        if actions or reports:
            lines.append(f"Day {day} orders/meds/results: {'; '.join([*reports, *actions])}")
    return "\n".join(lines)


def _summarize(events: list[Event], kind: str) -> str:
    values: dict[str, list[float]] = {}
    for e in events:
        if e.kind == kind and e.value is not None:
            values.setdefault(e.key, []).append(e.value)
    return ", ".join(f"{k} {min(v):g}-{max(v):g}" if min(v) != max(v) else f"{k} {v[0]:g}"
                     for k, v in sorted(values.items()))


def user_prompt(enc: Encounter) -> str:
    required = [m.term for m in enc.mentions if m.assertion == "present"]
    negations = [m.term for m in enc.mentions if m.assertion == "negated"]
    return "\n".join([
        "CHART DATA:", chart_digest(enc), "",
        "REQUIRED diagnoses (exact wording): " + "; ".join(required),
        "REQUIRED NEGATIONS (word for word): " + ("; ".join(negations) if negations else "none"),
    ])


def forbidden_terms(mentions: tuple[Mention, ...]) -> list[str]:
    """Every target-condition term the notes must not contain."""
    present = {m.icd10 for m in mentions if m.assertion == "present"}
    allowed = set(present)
    if present & HEART_FAILURE:
        allowed |= {"I50.9"}  # "heart failure" is fine once any HF code is documented
    terms: list[str] = []
    for code, words in CONDITION_TERMS.items():
        if code not in allowed:
            terms.extend(words)
    return terms


def check_notes(note_set: NoteSet, mentions: tuple[Mention, ...]) -> CheckResult:
    problems: list[str] = []
    types = sorted(n.note_type for n in note_set.notes)
    if types != sorted(NOTE_TYPES):
        problems.append(f"expected one note of each type {NOTE_TYPES}, got {types}")
    text = " ".join(n.text for n in note_set.notes).lower()
    for m in mentions:
        if m.term.lower() not in text:
            problems.append(f"missing required {m.assertion} wording: '{m.term}'")
    # Only negation phrases may contain a forbidden word ("no evidence of sepsis").
    # Present terms are NOT erased: erasing "CHF" would hide a leak like "acute CHF".
    scrubbed = text
    for m in mentions:
        if m.assertion == "negated":
            scrubbed = scrubbed.replace(m.term.lower(), " ")
    for word in forbidden_terms(mentions):
        if _contains_word(scrubbed, word):
            problems.append(f"names a diagnosis it must not: '{word}'")
    return CheckResult(not problems, tuple(problems))


def _contains_word(text: str, word: str) -> bool:
    start = text.find(word)
    while start != -1:
        before = text[start - 1] if start > 0 else " "
        after = text[start + len(word)] if start + len(word) < len(text) else " "
        if not before.isalnum() and not after.isalnum():
            return True
        start = text.find(word, start + 1)
    return False
