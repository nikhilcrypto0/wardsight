"""Gap finder: compare evidence with documentation and raise flags.

The four flag types follow the reasons to query in the ACDIS/AHIMA compliant query practice
brief (2022 update): documentation that is missing, unsupported, imprecise or conflicting.

- missing_dx:      evidence meets criteria, the notes never affirm the diagnosis
- unsupported_dx:  the notes affirm a diagnosis the evidence does not support
                   (denial risk: an insurer would likely reject it)
- unspecified_dx:  evidence supports a specific diagnosis, the notes use only a vague term
                   ("CHF" for acute systolic heart failure, "anemia" for acute blood loss anemia)
- conflicting_dx:  one note affirms a diagnosis that another note rules out, and no physician
                   addendum has settled it
"""

from __future__ import annotations

from dataclasses import dataclass

from wardsight.engine.chart import Chart
from wardsight.engine.documentation import Mention, documented_codes, find_mentions
from wardsight.engine.drg import DrgResult, coded_diagnoses, group
from wardsight.engine.evidence import RULES, Evidence, relevant_values

CONDITION_CODE = {"aki": "N17.9", "sepsis": "A41.9", "hyponatremia": "E87.1",
                  "abla": "D62", "arf": "J96.01", "hf": "I50.21"}
# The vague code a note uses instead of the specific one, and how it reads
VAGUE_CODE = {"hf": ("I50.9", "unspecified heart failure"), "abla": ("D64.9", "unspecified anemia")}


@dataclass(frozen=True)
class Flag:
    encounter_id: str
    condition: str
    kind: str  # "missing_dx" | "unsupported_dx" | "unspecified_dx" | "conflicting_dx"
    icd10: str
    detail: str
    evidence: str
    drg_now: DrgResult
    drg_if_resolved: DrgResult


def conflicting(mentions: list[Mention], code: str) -> tuple[str, str] | None:
    """(note that states it, note that rules it out), when two notes disagree and no addendum settled it."""
    if any(m.icd10 == code and m.addendum for m in mentions):
        return None
    stated = [m.note_type for m in mentions if m.icd10 == code and not m.negated]
    ruled_out = [m.note_type for m in mentions if m.icd10 == code and m.negated]
    for a in stated:
        for b in ruled_out:
            if a != b:
                return a, b
    return None


def find_flags(chart: Chart) -> list[Flag]:
    mentions = find_mentions(chart.notes)
    affirmed = documented_codes(chart.notes)
    codes_now = coded_diagnoses(chart)
    drg_now = group(chart, codes_now)
    flags: list[Flag] = []
    for condition, rule in RULES.items():
        code = CONDITION_CODE[condition]
        evidence: Evidence = rule(chart)
        clash = conflicting(mentions, code)
        if clash:
            stated, ruled_out = (t.replace("_", " ") for t in clash)
            summary = evidence.summary() or Evidence(condition, False, relevant_values(chart, condition)).summary()
            # resolving keeps the diagnosis if the evidence supports it, drops it if not
            fixed = codes_now | {code} if evidence.met else codes_now - {code}
            flags.append(Flag(chart.encounter_id, condition, "conflicting_dx", code,
                              f"the {stated} states it; the {ruled_out} rules it out",
                              summary or "no relevant measurements in the chart", drg_now, group(chart, fixed)))
        elif evidence.met and code not in affirmed:
            vague_code, vague_name = VAGUE_CODE.get(condition, (None, ""))
            if vague_code in affirmed:
                flags.append(Flag(chart.encounter_id, condition, "unspecified_dx", code,
                                  f"notes say only {vague_name}; evidence supports a more specific diagnosis",
                                  evidence.summary(), drg_now, group(chart, (codes_now - {vague_code}) | {code})))
            else:
                flags.append(Flag(chart.encounter_id, condition, "missing_dx", code,
                                  f"evidence meets criteria; {condition} not documented",
                                  evidence.summary(), drg_now, group(chart, codes_now | {code})))
        elif code in affirmed and not evidence.met:
            phrase = next(m.phrase for m in mentions if m.icd10 == code and not m.negated)
            observed = Evidence(condition, False, relevant_values(chart, condition)).summary()
            flags.append(Flag(chart.encounter_id, condition, "unsupported_dx", code,
                              f"notes state '{phrase}' but the chart does not meet criteria",
                              observed or "no relevant measurements in the chart",
                              drg_now, group(chart, codes_now - {code})))
    return flags
