"""Ward replay: gaps appear only once their evidence exists, beds never double-book."""

from __future__ import annotations

from collections import defaultdict
from itertools import pairwise
from pathlib import Path

import duckdb
import pytest

from wardsight.engine.chart import load_charts
from wardsight.engine.evidence import RULES
from wardsight.engine.scan import scan
from wardsight.factory import run as build_ward
from wardsight.notes.template import write_template_notes
from wardsight.reload import load_encounters
from wardsight.replay import CHECK_EVERY_H, assign_beds, build_replay, chart_at, headline_indicator


@pytest.fixture(scope="module")
def ward(tmp_path_factory) -> tuple[dict, dict]:
    out = tmp_path_factory.mktemp("replay")
    build_ward(out, seed=44, synthea_dir=None)
    with duckdb.connect(str(out / "wardsight.duckdb")) as con:
        write_template_notes(con, load_encounters(con), seed=44)
        scan(con, "dev")
        data = build_replay(con)
        charts = {c.encounter_id: c for c in load_charts(con, "dev")}
    return data, charts


def test_every_dev_gap_is_replayed_with_its_workflow(ward):
    data, _ = ward
    by_type = defaultdict(list)
    for e in data["events"]:
        by_type[e["type"]].append(e)
    assert len(by_type["admit"]) == len(by_type["discharge"]) == 200
    assert len(by_type["flag"]) == len(by_type["query_sent"]) == len(by_type["answered"]) == 75
    assert data["events"] == sorted(data["events"], key=lambda e: (e["t"], e["type"] != "discharge"))


def test_missing_gaps_are_raised_at_the_first_hour_evidence_exists(ward):
    data, charts = ward
    admit = {e["id"]: e["admit"] for e in data["encounters"]}
    for e in (x for x in data["events"] if x["type"] == "flag" and x["kind"] == "missing_dx"):
        chart, hour = charts[e["encounter_id"]], e["t"] - admit[e["encounter_id"]]
        assert RULES[e["condition"]](chart_at(chart, hour)).met, e  # evidence exists when raised
        if hour > CHECK_EVERY_H:
            assert not RULES[e["condition"]](chart_at(chart, hour - CHECK_EVERY_H)).met, e  # not before


def test_flags_fall_inside_the_stay_and_answers_follow(ward):
    data, _ = ward
    stay = {e["id"]: (e["admit"], e["discharge"]) for e in data["encounters"]}
    flag_time = {}
    for e in data["events"]:
        key = (e.get("encounter_id"), e.get("condition"), e.get("kind"))
        if e["type"] == "flag":
            start, end = stay[e["encounter_id"]]
            assert start < e["t"] < end
            flag_time[key] = e["t"]
        elif e["type"] == "answered":
            assert e["t"] > flag_time[key]
            assert (e["drg_to"] != e["drg_from"]) <= e["resolved"]  # DRG only moves when resolved


def test_beds_are_never_double_booked(ward):
    data, _ = ward
    by_bed = defaultdict(list)
    for e in data["encounters"]:
        by_bed[e["bed"]].append((e["admit"], e["discharge"]))
    for stays in by_bed.values():
        stays.sort()
        assert all(a_end <= b_start for (_, a_end), (b_start, _) in pairwise(stays))


def test_feed_headline_is_a_measured_value():
    assert headline_indicator("h1.5: blood cultures drawn; h2: antibiotics started; h0: MAP 61 mmHg") == (
        "MAP 61 mmHg at hour 0")
    assert headline_indicator("h1: creatinine 0.7 to 0.8 mg/dL across the stay") == (
        "creatinine 0.7 to 0.8 mg/dL across the stay")


def test_bed_assignment_reuses_freed_beds():
    beds = assign_beds([("A", 0, 10), ("B", 5, 15), ("C", 12, 20)])
    assert beds == {"A": 0, "B": 1, "C": 0}


def test_replay_never_reads_the_answer_key():
    source = (Path(__file__).parents[1] / "src" / "wardsight" / "replay.py").read_text()
    assert "truth." not in source and "planter" not in source and "scenarios" not in source
