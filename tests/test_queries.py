"""Query rules check against a labeled set of bad and good queries, plus the draft/retry loop."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from wardsight.notes.budget import Budget, Ledger
from wardsight.queries.draft import (
    QueryRequest,
    draft_query,
    indicators_from_evidence,
    make_request,
    template_drafter,
)
from wardsight.queries.lint import lint_query
from wardsight.queries.options import options_for

IND = ("MAP 61 mmHg at hour 0", "platelets 116 K/uL at hour 1", "blood cultures drawn at hour 1.5")
OPTS = options_for("sepsis", "missing_dx")
GOOD = ("Clinical indicators in this record: MAP 61 mmHg at hour 0; platelets 116 K/uL at hour 1. "
        "Based on your clinical judgment, can you please clarify the condition being evaluated and treated?")

BAD = [
    ("Documenting this would move the DRG to a higher tier. Can you clarify the condition?", "financial"),
    ("MAP 61 mmHg and platelets 116 K/uL. This affects reimbursement. Please clarify?", "financial"),
    ("MAP 61 mmHg, platelets 116 K/uL. Please document sepsis in your next note?", "leading"),
    ("MAP 61 mmHg, platelets 116 K/uL. These findings meet criteria for a new diagnosis. Clarify?", "leading"),
    ("MAP 61 mmHg, platelets 116 K/uL. Is the picture consistent with an infection-related process?", "leading"),
    ("MAP 61 mmHg and platelets 116 K/uL at hour 1. Does this patient have sepsis?", "names the diagnosis"),
    ("MAP 58 mmHg and platelets 116 K/uL at hour 1. Can you clarify the condition being treated?", "numbers not found"),
    ("Lactate 4.2 mmol/L and MAP 61 mmHg at hour 0. Can you clarify the condition being treated?", "numbers not found"),
    ("MAP 61 mmHg and platelets 116 K/uL at hour 1 were noted in the chart for this admission.", "must ask"),
]


def test_good_query_passes():
    assert lint_query(GOOD, OPTS, IND, "sepsis", "missing_dx").ok


@pytest.mark.parametrize("stem,expected", BAD)
def test_bad_query_is_blocked(stem, expected):
    result = lint_query(stem, OPTS, IND, "sepsis", "missing_dx")
    assert not result.ok
    assert any(expected in p for p in result.problems), result.problems


def test_yes_no_and_missing_escape_options_are_blocked():
    yes_no = lint_query(GOOD, ("Yes", "No", "Other (please specify)", "Unable to determine"), IND,
                        "sepsis", "missing_dx")
    assert any("yes/no" in p for p in yes_no.problems)
    no_escape = lint_query(GOOD, ("Sepsis", "Localized infection without sepsis"), IND, "sepsis", "missing_dx")
    assert any("Unable to determine" in p for p in no_escape.problems)


def test_new_diagnosis_query_needs_two_indicators():
    result = lint_query(GOOD, OPTS, IND[:1], "sepsis", "missing_dx")
    assert any("at least 2" in p for p in result.problems)


def test_validation_query_may_name_the_documented_diagnosis():
    opts = options_for("aki", "unsupported_dx")
    stem = ("The record documents acute kidney injury. Clinical indicators in the record: creatinine 0.72 to "
            "0.77 mg/dL across the stay. Based on your clinical judgment, can you please clarify whether "
            "this diagnosis is clinically supported?")
    assert lint_query(stem, opts, ("creatinine 0.72 to 0.77 mg/dL across the stay",), "aki", "unsupported_dx").ok


def test_hf_specificity_query_may_say_heart_failure_but_not_the_specific_type():
    opts, ind = options_for("hf", "missing_dx"), ("BNP 957 pg/mL at hour 1", "LVEF 25% at hour 20")
    ok = "The record documents heart failure. BNP 957 pg/mL at hour 1. Please clarify the type and acuity?"
    leaked = "The record documents heart failure. BNP 957 pg/mL at hour 1. Is this acute systolic heart failure?"
    assert lint_query(ok, opts, ind, "hf", "missing_dx").ok
    assert not lint_query(leaked, opts, ind, "hf", "missing_dx").ok


def test_indicator_parsing():
    assert indicators_from_evidence("h0: MAP 61 mmHg; h1.5: blood cultures drawn") == (
        "MAP 61 mmHg at hour 0", "blood cultures drawn at hour 1.5")
    assert indicators_from_evidence("h1: creatinine 0.7 to 0.8 mg/dL across the stay") == (
        "creatinine 0.7 to 0.8 mg/dL across the stay",)


def test_template_drafts_pass_for_every_condition_and_kind():
    evidence = "h0: MAP 61 mmHg; h1: platelets 116 K/uL; h3: Furosemide 40 mg IV"
    for condition in ("aki", "sepsis", "hyponatremia", "abla", "arf", "hf"):
        for kind, detail in (("missing_dx", "evidence meets criteria"),
                             ("unsupported_dx", "notes state 'x' but the chart does not meet criteria")):
            req = make_request("E1", condition, kind, detail, evidence)
            assert draft_query(req, template_drafter, "template", 1).lint.ok, (condition, kind)


@pytest.fixture()
def ledger(tmp_path: Path):
    con = duckdb.connect(str(tmp_path / "l.duckdb"))
    yield Ledger(con, Budget(100, 100_000, 1_000_000, 3), "queries"), con
    con.close()


def _req() -> QueryRequest:
    return make_request("E1", "sepsis", "missing_dx", "evidence meets criteria",
                        "h0: MAP 61 mmHg; h1: platelets 116 K/uL")


def test_rejected_draft_is_retried_with_problems(ledger):
    seen: list[tuple[str, ...]] = []

    def fake_llm(req, problems):
        seen.append(problems)
        if not problems:
            return "MAP 61 mmHg and platelets 116 K/uL suggest sepsis. Please document sepsis?", 40, 20
        return template_drafter(req, problems)[0], 40, 20

    led, con = ledger
    result = draft_query(_req(), fake_llm, "fake", 3, led, "fake")
    assert result.lint.ok and result.attempts == 2
    assert any("leading" in p for p in seen[1])  # the retry was told what was wrong
    assert [r[0] for r in con.execute("SELECT status FROM ops.llm_ledger ORDER BY ts").fetchall()] == [
        "rejected", "ok"]


def test_draft_that_never_passes_is_left_for_a_human(ledger):
    led, _ = ledger
    result = draft_query(_req(), lambda req, p: ("Bill this as sepsis for the DRG?", 10, 10), "fake", 3, led)
    assert not result.lint.ok and result.attempts == 3
