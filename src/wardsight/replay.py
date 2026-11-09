"""Ward replay: the dev ward over 14 simulated days, as a time-ordered event stream.

Concurrent review, not retrospective: each gap is raised at the first hour its
evidence exists in the chart (re-running the same rules on the chart as it
stood then), not at discharge. The query workflow then plays out on a fixed
clock (approve +2 h, physician answer +10 h) using the simulated physician.

Reads the `ehr` schema and the engine only; never the answer key.

    uv run wardsight-replay                       # writes web/public/replay.json
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import replace
from pathlib import Path

import duckdb

from wardsight.engine.chart import Chart, load_charts
from wardsight.engine.evidence import RULES
from wardsight.engine.gaps import Flag, find_flags
from wardsight.queries.draft import indicators_from_evidence
from wardsight.queries.options import options_for
from wardsight.queries.run import query_id
from wardsight.store import SIM_START
from wardsight.workflow.physician import rule_based_reply

log = logging.getLogger("wardsight.replay")

SPLIT = "dev"
CHECK_EVERY_H = 6          # the engine re-reads each chart every 6 hours
UNSUPPORTED_AFTER_H = 48   # a documented diagnosis is judged unsupported after 48 h of data
APPROVE_AFTER_H = 2        # reviewer works the queue
ANSWER_AFTER_H = 10        # physician answers
NOTE_HOUR_OF_DAY = 10      # notes are written mid-morning
SIM_DAYS = 14
HF_ACUTE_ON_CHRONIC_OPTION = 1


def chart_at(chart: Chart, hour: float) -> Chart:
    """The chart as it stood `hour` hours after admission."""
    return replace(chart,
                   events=tuple(e for e in chart.events if e.t_hours <= hour),
                   notes=tuple(n for n in chart.notes if n.hospital_day * 24 + NOTE_HOUR_OF_DAY <= hour))


def detection_hour(chart: Chart, flag: Flag) -> float:
    stay_h = chart.los_days * 24
    if flag.kind == "unsupported_dx":
        return float(min(UNSUPPORTED_AFTER_H, stay_h - 1))
    hour = CHECK_EVERY_H
    while hour < stay_h:
        if RULES[flag.condition](chart_at(chart, hour)).met:
            return float(hour)
        hour += CHECK_EVERY_H
    return float(stay_h - 1)


def headline_indicator(evidence: str) -> str:
    """The most telling measured value for the live feed (not 'blood cultures drawn')."""
    indicators = indicators_from_evidence(evidence) if evidence else ()
    measured = [i for i in indicators if any(ch.isdigit() for ch in i.split(" at hour")[0])]
    return (measured or list(indicators) or [""])[0]


def _resolved(condition: str, kind: str, option_index: int) -> bool:
    """Same outcome rules as the live workflow (workflow/actions.py)."""
    if kind == "unsupported_dx":
        return option_index == 1  # ruled out
    if condition == "hf":
        return option_index in (0, HF_ACUTE_ON_CHRONIC_OPTION)  # both are acute systolic
    return option_index == 0


def assign_beds(stays: list[tuple[str, float, float]]) -> dict[str, int]:
    """Lowest free bed for each admission, in admission order."""
    bed_free_at: list[float] = []
    beds: dict[str, int] = {}
    for enc_id, start, end in sorted(stays, key=lambda s: s[1]):
        bed = next((i for i, free in enumerate(bed_free_at) if free <= start), None)
        if bed is None:
            bed = len(bed_free_at)
            bed_free_at.append(end)
        else:
            bed_free_at[bed] = end
        beds[enc_id] = bed
    return beds


def build_replay(con: duckdb.DuckDBPyConnection) -> dict:
    admits = {eid: (ts - SIM_START).total_seconds() / 3600 for eid, ts in con.execute(
        "SELECT encounter_id, admit_ts FROM ehr.encounters WHERE split = ?", [SPLIT]).fetchall()}
    charts = [replace(c, notes=tuple(n for n in c.notes if n.note_type != "addendum"))
              for c in load_charts(con, SPLIT)]
    stays = [(c.encounter_id, admits[c.encounter_id], admits[c.encounter_id] + c.los_days * 24) for c in charts]
    beds = assign_beds(stays)

    encounters, events = [], []
    for chart in charts:
        start = admits[chart.encounter_id]
        end = start + chart.los_days * 24
        encounters.append({"id": chart.encounter_id, "bed": beds[chart.encounter_id], "admit": start,
                           "discharge": end, "age": chart.age, "sex": chart.sex,
                           "reason": chart.reason_for_admission})
        events.append({"t": start, "type": "admit", "encounter_id": chart.encounter_id})
        events.append({"t": end, "type": "discharge", "encounter_id": chart.encounter_id})
        for flag in find_flags(chart):
            events += _workflow_events(chart, flag, start)

    events.sort(key=lambda e: (e["t"], e["type"] != "discharge"))
    # Admissions span SIM_DAYS; the replay runs until the last patient goes home.
    last_hour = max(e["t"] for e in events)
    return {"beds": max(beds.values()) + 1, "admit_days": SIM_DAYS, "hours": last_hour,
            "encounters": encounters, "events": events}


def _workflow_events(chart: Chart, flag: Flag, start: float) -> list[dict]:
    detected = start + detection_hour(chart, flag)
    qid = query_id(chart.encounter_id, flag.condition, flag.kind)
    reply = rule_based_reply(qid, flag.kind, options_for(flag.condition, flag.kind))
    options = options_for(flag.condition, flag.kind)
    resolved = _resolved(flag.condition, flag.kind, reply.option_index)
    base = {"encounter_id": chart.encounter_id, "condition": flag.condition, "kind": flag.kind}
    first_evidence = headline_indicator(flag.evidence)
    return [
        {**base, "t": detected, "type": "flag", "detail": flag.detail, "evidence": first_evidence,
         "drg_now": flag.drg_now.drg, "drg_if_resolved": flag.drg_if_resolved.drg},
        {**base, "t": detected + APPROVE_AFTER_H, "type": "query_sent"},
        {**base, "t": detected + ANSWER_AFTER_H, "type": "answered", "answer": options[reply.option_index],
         "resolved": resolved, "drg_from": flag.drg_now.drg,
         "drg_to": flag.drg_if_resolved.drg if resolved else flag.drg_now.drg},
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the ward replay timeline.")
    parser.add_argument("--db", type=Path, default=Path("data/wardsight.duckdb"))
    parser.add_argument("--out", type=Path, default=Path("web/public/replay.json"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with duckdb.connect(str(args.db), read_only=True) as con:
        data = build_replay(con)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, separators=(",", ":")))
    flags = sum(e["type"] == "flag" for e in data["events"])
    log.info("replay: %d patients, %d beds, %d gaps, %d events -> %s", len(data["encounters"]), data["beds"],
             flags, len(data["events"]), args.out)


if __name__ == "__main__":
    main()
