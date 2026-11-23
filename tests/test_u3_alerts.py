"""U3: the 'not fully specified' and 'conflicting documentation' alerts, and that adding their
test charts left every original chart (dev and held-out) exactly as it was."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from wardsight import planter
from wardsight.engine.chart import NoteText, load_charts
from wardsight.engine.documentation import find_mentions
from wardsight.engine.gaps import conflicting, find_flags
from wardsight.engine.scan import scan
from wardsight.factory import run as build_ward
from wardsight.notes.template import write_template_notes
from wardsight.queries.draft import make_request, template_stem
from wardsight.queries.lint import lint_query
from wardsight.reload import load_encounters

H_AND_P, PROGRESS = "history_and_physical", "progress_note"


def notes(*pairs: tuple[str, str]) -> tuple[NoteText, ...]:
    return tuple(NoteText(note_type, day, text) for day, (note_type, text) in enumerate(pairs))


def test_two_notes_that_disagree_conflict():
    m = find_mentions(notes((H_AND_P, "Assessment: sepsis."), (PROGRESS, "No evidence of sepsis.")))
    assert conflicting(m, "A41.9") == (H_AND_P, PROGRESS)


def test_an_addendum_settles_the_conflict():
    m = find_mentions(notes((H_AND_P, "Assessment: sepsis."), (PROGRESS, "No evidence of sepsis."),
                           ("addendum", "ADDENDUM: sepsis.")))
    assert conflicting(m, "A41.9") is None


def test_one_note_with_both_is_not_a_conflict_between_notes():
    m = find_mentions(notes((H_AND_P, "Sepsis considered on arrival. No evidence of sepsis after cultures.")))
    assert conflicting(m, "A41.9") is None


def test_stated_then_resolved_is_not_a_conflict():
    m = find_mentions(notes((H_AND_P, "Acute kidney injury."), ("discharge_summary", "Acute kidney injury, resolved.")))
    assert conflicting(m, "N17.9") is None


@pytest.fixture(scope="module")
def ward(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("u3-ward")
    build_ward(out, seed=11, synthea_dir=None)
    db = out / "wardsight.duckdb"
    with duckdb.connect(str(db)) as con:
        write_template_notes(con, load_encounters(con), seed=11)
        scan(con, "dev")
    return db


def _flags_by_group(db: Path) -> dict[str, list[list[str]]]:
    with duckdb.connect(str(db), read_only=True) as con:
        groups = dict(con.execute("SELECT encounter_id, grp FROM truth.scenarios WHERE split = 'dev'").fetchall())
        charts = load_charts(con, "dev")
    out: dict[str, list[list[str]]] = {}
    for chart in charts:
        out.setdefault(groups[chart.encounter_id], []).append([f.kind for f in find_flags(chart)])
    return out


def test_new_groups_raise_the_right_alert_and_near_misses_stay_quiet(ward: Path):
    by_group = _flags_by_group(ward)
    assert all(kinds == ["unspecified_dx"] for kinds in by_group["unspecified"])
    assert all(kinds == ["conflicting_dx"] for kinds in by_group["conflicting"])
    assert all(kinds == [] for kinds in by_group["unspecified_near"] + by_group["conflict_near"])


def test_new_alerts_get_compliant_queries(ward: Path):
    with duckdb.connect(str(ward), read_only=True) as con:
        charts = {c.encounter_id: c for c in load_charts(con, "dev")}
    drafted = 0
    for chart in charts.values():
        for f in find_flags(chart):
            if f.kind in ("unspecified_dx", "conflicting_dx"):
                req = make_request(chart.encounter_id, f.condition, f.kind, f.detail, f.evidence)
                result = lint_query(template_stem(req), req.options, req.indicators, f.condition, f.kind)
                assert result.ok, (chart.encounter_id, result.problems)
                drafted += 1
    assert drafted == planter.EXTRA_COUNTS["dev"]["unspecified"] + planter.EXTRA_COUNTS["dev"]["conflicting"] + \
        sum(1 for g in _flags_by_group(ward)["missing"] if g == ["unspecified_dx"])


def _snapshot(db: Path) -> dict[str, list]:
    """Every row that describes the original charts (ids below D0201 and all held-out)."""
    original = "encounter_id < 'D0201' OR (encounter_id LIKE 'H%' AND encounter_id < 'H0101')"
    with duckdb.connect(str(db), read_only=True) as con:
        return {table: con.execute(f"SELECT * FROM {table} WHERE {original} ORDER BY ALL").fetchall()
                for table in ("ehr.encounters", "ehr.events", "truth.scenarios")}


def test_adding_u3_charts_changed_no_original_chart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with_u3, without_u3 = tmp_path / "with", tmp_path / "without"
    with_u3.mkdir()
    without_u3.mkdir()
    build_ward(with_u3, seed=11, synthea_dir=None)
    monkeypatch.setattr(planter, "EXTRA_COUNTS", {"dev": {}, "heldout": {}})
    monkeypatch.setattr("wardsight.factory.EXTRA_COUNTS", {"dev": {}, "heldout": {}})
    build_ward(without_u3, seed=11, synthea_dir=None)
    assert _snapshot(with_u3 / "wardsight.duckdb") == _snapshot(without_u3 / "wardsight.duckdb")


def _snapshot_except_heldout_batch(db: Path) -> dict[str, list]:
    """Every row for the charts that existed before the held-out U3 batch (H0101+)."""
    before = "NOT (encounter_id LIKE 'H%' AND encounter_id >= 'H0101')"
    with duckdb.connect(str(db), read_only=True) as con:
        return {table: con.execute(f"SELECT * FROM {table} WHERE {before} ORDER BY ALL").fetchall()
                for table in ("ehr.encounters", "ehr.events", "truth.scenarios", "truth.answer_key")}


def test_heldout_batch_changed_no_existing_chart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with_batch, without_batch = tmp_path / "with", tmp_path / "without"
    with_batch.mkdir()
    without_batch.mkdir()
    build_ward(with_batch, seed=11, synthea_dir=None)
    counts = {"dev": planter.EXTRA_COUNTS["dev"], "heldout": {}}
    monkeypatch.setattr(planter, "EXTRA_COUNTS", counts)
    monkeypatch.setattr("wardsight.factory.EXTRA_COUNTS", counts)
    build_ward(without_batch, seed=11, synthea_dir=None)
    assert _snapshot_except_heldout_batch(with_batch / "wardsight.duckdb") == \
        _snapshot_except_heldout_batch(without_batch / "wardsight.duckdb")
    with duckdb.connect(str(with_batch / "wardsight.duckdb"), read_only=True) as con:
        kinds = dict(con.execute("SELECT expected_flag, count(*) FROM truth.answer_key "
                                 "WHERE encounter_id >= 'H0101' AND split = 'heldout' GROUP BY 1").fetchall())
    assert kinds == {"unspecified_dx": 5, "conflicting_dx": 5, "none": 7}  # the final exam now covers both alerts
