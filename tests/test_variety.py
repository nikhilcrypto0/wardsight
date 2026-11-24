"""Real-world wording: the note reader follows the coding rules for uncertain diagnoses, abbreviations,
typos and negation, and the variety note mode keeps every chart's meaning intact."""

from __future__ import annotations

import random

import pytest

from wardsight.engine.chart import NoteText
from wardsight.engine.documentation import documented_codes, find_mentions
from wardsight.models import Mention
from wardsight.notes.variety import NEGATED, PRESENT, vary


def codes(text: str) -> set[str]:
    return documented_codes((NoteText("progress_note", 1, text),))


@pytest.mark.parametrize("text", [
    "Assessment: rule out sepsis.",            # still being ruled out: coded as if present (ICD-10-CM II.H)
    "Assessment: r/o sepsis.",
    "Cannot rule out sepsis.",
    "Possible sepsis.", "Probable sepsis.", "Likely sepsis.", "Suspected sepsis.", "Concern for sepsis.",
    "Afebrile, no leukocytosis, likely sepsis.",  # an uncertainty cue closer to the term beats an earlier 'no'
])
def test_uncertain_diagnosis_counts_as_documented(text: str):
    assert "A41.9" in codes(text)


@pytest.mark.parametrize("text", [
    "Sepsis ruled out.", "Sepsis was ruled out.", "No evidence of sepsis.", "Negative for sepsis.",
    "Sepsis unlikely.", "History of sepsis.", "H/o sepsis.", "S/p sepsis last year.",
])
def test_ruled_out_or_past_is_not_documented(text: str):
    assert "A41.9" not in codes(text)


@pytest.mark.parametrize(("text", "code"), [
    ("AHRF on 4 L nasal cannula.", "J96.01"),
    ("ABLA from GI bleed.", "D62"),
    ("HFrEF exacerbation, diuresing.", "I50.21"),
    ("Sespis from urinary source.", "A41.9"),            # one-letter typo in a long word
    ("Acute kidny injury, creatinine rising.", "N17.9"),
    ("Hyponatermia, fluid restrict.", "E87.1"),
])
def test_abbreviations_and_typos(text: str, code: str):
    assert code in codes(text)


def test_urosepsis_is_not_sepsis():
    # ICD-10-CM I.C.1.d.1.a.ii: 'urosepsis' has no default code; the provider must be queried
    assert "A41.9" not in codes("Urosepsis, on ceftriaxone.")


@pytest.mark.parametrize("text", ["Old septal infarct on ECG.", "Ak noted on exam.", "Anemic appearing.",
                                  "Patient ate breakfast."])
def test_typo_tolerance_does_not_invent_diagnoses(text: str):
    assert not find_mentions((NoteText("progress_note", 1, text),))


def test_every_variant_reads_back_as_planned():
    for code, variants in PRESENT.items():
        for v in variants:
            assert code in codes(f"Assessment: {v}."), v
    for code, variants in NEGATED.items():
        for v in variants:
            assert code not in codes(f"Assessment: {v}."), v


def test_vary_is_reproducible_and_keeps_placement():
    planned = (Mention("A41.9", "sepsis", "present", ("history_and_physical",)),
               Mention("A41.9", "no evidence of sepsis", "negated", ("progress_note",)),
               Mention("N17.9", "acute kidney injury, resolved", "present"))
    a, b = vary(planned, random.Random(1)), vary(planned, random.Random(1))
    assert a == b
    assert [m.notes for m in a] == [m.notes for m in planned]
    assert a[2].term == "acute kidney injury, resolved"  # odd phrasings are kept as planned
