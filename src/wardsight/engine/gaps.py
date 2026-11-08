"""Gap finder: compare evidence with documentation and raise flags.

- missing_dx:     evidence meets criteria, the notes never affirm the diagnosis
                  (for heart failure: notes say only unspecified "CHF")
- unsupported_dx: the notes affirm a diagnosis the evidence does not support
                  (denial risk: an insurer would likely reject it)
"""

from __future__ import annotations

from dataclasses import dataclass

from wardsight.engine.chart import Chart
from wardsight.engine.documentation import find_mentions
from wardsight.engine.drg import DrgResult, coded_diagnoses, group
from wardsight.engine.evidence import RULES, Evidence

CONDITION_CODE = {"aki": "N17.9", "sepsis": "A41.9", "hyponatremia": "E87.1",
                  "abla": "D62", "arf": "J96.01", "hf": "I50.21"}


@dataclass(frozen=True)
class Flag:
    encounter_id: str
    condition: str
    kind: str  # "missing_dx" | "unsupported_dx"
    icd10: str
    detail: str
    evidence: str
    drg_now: DrgResult
    drg_if_resolved: DrgResult


def find_flags(chart: Chart) -> list[Flag]:
    mentions = find_mentions(chart.notes)
    affirmed = {m.icd10 for m in mentions if not m.negated}
    codes_now = coded_diagnoses(chart)
    drg_now = group(chart, codes_now)
    flags: list[Flag] = []
    for condition, rule in RULES.items():
        code = CONDITION_CODE[condition]
        evidence: Evidence = rule(chart)
        if evidence.met and code not in affirmed:
            vague = condition == "hf" and "I50.9" in affirmed
            detail = ("notes say only unspecified heart failure; evidence supports acute systolic"
                      if vague else f"evidence meets criteria; {condition} not documented")
            fixed = (codes_now - {"I50.9"}) | {code}
            flags.append(Flag(chart.encounter_id, condition, "missing_dx", code, detail,
                              evidence.summary(), drg_now, group(chart, fixed)))
        elif code in affirmed and not evidence.met:
            phrase = next(m.phrase for m in mentions if m.icd10 == code and not m.negated)
            flags.append(Flag(chart.encounter_id, condition, "unsupported_dx", code,
                              f"notes state '{phrase}' but the chart does not meet criteria",
                              "no qualifying evidence found", drg_now, group(chart, codes_now - {code})))
    return flags
