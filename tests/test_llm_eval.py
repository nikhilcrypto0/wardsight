"""The AI-notes evaluation, run end to end with a fake model (no API calls, no cost)."""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
from test_notes import config, fake_model

from wardsight.factory import run
from wardsight.llm_eval import refresh_work, run_eval
from wardsight.notes.template import write_template_notes
from wardsight.reload import load_encounters


def test_eval_scores_dev_only_on_a_copy(tmp_path: Path):
    run(tmp_path, seed=5, synthea_dir=None)
    db = tmp_path / "wardsight.duckdb"
    with duckdb.connect(str(db)) as con:          # the real database starts with template notes
        write_template_notes(con, load_encounters(con), seed=0)
    untouched = tmp_path / "before.duckdb"
    shutil.copy(db, untouched)
    work, report = tmp_path / "llm.duckdb", tmp_path / "report.md"
    generate, _ = fake_model(leak_first=False)

    result = run_eval(db, work, config(tmp_path, 10_000_000), generate, "fake", 6, report)

    assert result["written"] == 6 and result["llm_charts"] == 6
    assert db.read_bytes() == untouched.read_bytes()  # the original database is never changed
    text = report.read_text()
    assert "Template notes" in text and "AI-written notes" in text and "6 of" in text
    assert result["baseline_caught"] > 0          # the baseline really is the template-note score

    again = run_eval(db, work, config(tmp_path, 10_000_000), generate, "fake", None, report)
    with duckdb.connect(str(work), read_only=True) as con:
        dev = con.execute("SELECT count(*) FROM ehr.encounters WHERE split = 'dev'").fetchone()[0]
        splits = {s for (s,) in con.execute("""SELECT DISTINCT e.split FROM ehr.notes n
                                               JOIN ehr.encounters e USING (encounter_id)
                                               WHERE n.source = 'llm'""").fetchall()}
        heldout_scored = con.execute("SELECT count(*) FROM information_schema.tables "
                                     "WHERE table_name = 'heldout_runs'").fetchone()[0]
    # resumes: the first 6 are not paid for twice; a chart whose notes fail the leak check keeps its template notes
    assert again["written"] + again["failed"] == dev - 6
    assert again["llm_charts"] == 6 + again["written"]
    assert splits == {"dev"}                      # held-out charts never get AI notes
    assert heldout_scored == 0                    # and the final exam is never run


def test_refresh_keeps_paid_notes_only_for_unchanged_charts(tmp_path: Path):
    run(tmp_path, seed=5, synthea_dir=None)
    db, work = tmp_path / "wardsight.duckdb", tmp_path / "llm.duckdb"
    with duckdb.connect(str(db)) as con:
        write_template_notes(con, load_encounters(con), seed=0)
    generate, _ = fake_model(leak_first=False)
    run_eval(db, work, config(tmp_path, 10_000_000), generate, "fake", 3, tmp_path / "r.md")
    with duckdb.connect(str(work), read_only=True) as con:
        paid = [e for (e,) in con.execute("SELECT DISTINCT encounter_id FROM ehr.notes WHERE source = 'llm' "
                                          "ORDER BY 1").fetchall()]
    with duckdb.connect(str(db)) as con:  # the ward is rebuilt and one paid-for chart changes
        con.execute("UPDATE ehr.events SET value = value + 1 WHERE encounter_id = ? AND value IS NOT NULL",
                    [paid[0]])
    assert refresh_work(db, work) == len(paid) - 1
    with duckdb.connect(str(work), read_only=True) as con:
        kept = {e for (e,) in con.execute("SELECT DISTINCT encounter_id FROM ehr.notes WHERE source = 'llm'").fetchall()}
        ledger = con.execute("SELECT count(*) FROM ops.llm_ledger").fetchone()[0]
    assert kept == set(paid[1:])       # the changed chart's notes were not reused
    assert ledger >= len(paid)         # the bill so far is kept
