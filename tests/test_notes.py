"""Note writer: the leak check, retries, budget halts, all with a fake model (no API calls)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from wardsight.factory import run
from wardsight.models import Mention
from wardsight.notes.spec import Note, NoteSet, check_notes, forbidden_terms
from wardsight.notes.writer import write_notes
from wardsight.reload import load_encounters

FILLER = " Patient seen and examined, vitals and labs reviewed, plan discussed with nursing." * 4


def notes(*extra: str) -> NoteSet:
    body = FILLER + " " + " ".join(extra)
    return NoteSet(notes=[Note(note_type=t, hospital_day=d, text=body) for t, d in
                          (("history_and_physical", 0), ("progress_note", 1), ("discharge_summary", 3))])


PNEUMONIA = Mention("J18.9", "community-acquired pneumonia", "present")


def test_check_passes_clean_notes():
    assert check_notes(notes("Assessment: community-acquired pneumonia."), (PNEUMONIA,)).ok


def test_check_catches_leaked_diagnosis():
    result = check_notes(notes("community-acquired pneumonia, likely septic picture"), (PNEUMONIA,))
    assert not result.ok and any("septic" in p for p in result.problems)


def test_check_catches_missing_required_term():
    result = check_notes(notes("Assessment: lung infection."), (PNEUMONIA,))
    assert not result.ok


def test_negation_phrase_is_allowed_but_term_elsewhere_is_not():
    neg = Mention("A41.9", "no evidence of sepsis", "negated")
    assert check_notes(notes("community-acquired pneumonia; no evidence of sepsis"), (PNEUMONIA, neg)).ok
    leaked = check_notes(notes("community-acquired pneumonia; no evidence of sepsis. Sepsis bundle."),
                         (PNEUMONIA, neg))
    assert not leaked.ok


def test_hf_specificity_gap_forbids_acute_systolic_wording():
    chf = Mention("I50.9", "CHF", "present")
    words = forbidden_terms((PNEUMONIA, chf))
    assert "systolic heart failure" in words and "heart failure" not in words
    assert not check_notes(notes("community-acquired pneumonia, CHF, acute CHF flare"), (PNEUMONIA, chf)).ok


def test_word_boundaries():
    assert check_notes(notes("community-acquired pneumonia; aseptic technique used"), (PNEUMONIA,)).ok


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    run(tmp_path, seed=5, synthea_dir=None)
    return tmp_path / "wardsight.duckdb"


def config(tmp_path: Path, per_run: int) -> Path:
    path = tmp_path / "w.toml"
    path.write_text(f"[llm]\nmax_output_tokens_per_call = 100\nmax_tokens_per_run = {per_run}\n"
                    "max_tokens_per_day = 10000000\nmax_attempts_per_item = 3\n")
    return path


def fake_model(leak_first: bool):
    calls = {"n": 0}

    def generate(system: str, user: str):
        calls["n"] += 1
        required = user.split("REQUIRED diagnoses (exact wording): ")[1].split("\n")[0].split("; ")
        neg_line = user.split("REQUIRED NEGATIONS (word for word): ")[1].split("\n")[0]
        negations = [] if neg_line == "none" else neg_line.split("; ")
        leak = ["respiratory failure"] if leak_first and calls["n"] == 1 else []
        return notes(*required, *negations, *leak), 50, 50

    return generate, calls


def test_writer_retries_then_saves(db: Path, tmp_path: Path):
    generate, _ = fake_model(leak_first=True)
    stats = write_notes(db, config(tmp_path, 10_000_000), generate, "fake", limit=4)
    assert stats["written"] == 4 and stats["failed"] == 0
    with duckdb.connect(str(db), read_only=True) as con:
        assert con.execute("SELECT count(*) FROM ehr.notes").fetchone()[0] == 12
        statuses = [r[0] for r in con.execute("SELECT status FROM ops.llm_ledger ORDER BY ts").fetchall()]
    assert statuses[0] == "rejected" and statuses.count("ok") == 4


def test_writer_halts_on_budget(db: Path, tmp_path: Path):
    generate, calls = fake_model(leak_first=False)
    stats = write_notes(db, config(tmp_path, 450), generate, "fake", limit=None)
    assert stats.get("halted") == 1
    # 100 tokens per call, 200 headroom: 3rd call fits (200 + 200 <= 450), 4th does not (300 + 200)
    assert calls["n"] == 3


def test_reload_round_trip(db: Path):
    with duckdb.connect(str(db), read_only=True) as con:
        encounters = load_encounters(con)
        events = con.execute("SELECT count(*) FROM ehr.events").fetchone()[0]
    assert len(encounters) == 300
    assert sum(len(e.events) for e in encounters) == events
    assert all(e.mentions for e in encounters)
