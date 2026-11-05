"""Gap planter: decides each chart's test group and writes the answer key.

The planter knows the TRUTH (what the evidence supports) and decides what the
notes will SAY. Where the two disagree on purpose, the answer key records the
flag a correct detector must raise. It is deliberately independent of the
milestone-2 detection rules: it works from scenario labels, never from
reading values back out of the chart.
"""

from __future__ import annotations

import random
from dataclasses import replace

from wardsight.codes import CHRONIC_ICD10, CHRONIC_TERMS, PRINCIPAL_TERMS
from wardsight.models import (
    CONDITIONS,
    EVIDENCE_ABSENT,
    EVIDENCE_CONFOUNDER,
    EVIDENCE_MEETS,
    EVIDENCE_NEAR_MISS,
    AnswerKeyRow,
    Encounter,
    Mention,
    PatientSeed,
)
from wardsight.scenarios import build_chart, choose_principal

SIM_DAYS = 14

GROUP_COUNTS = {
    "dev": {"missing": 50, "unsupported": 25, "correct": 40,
            "near_miss": 30, "confounder": 15, "routine": 40},
    "heldout": {"missing": 25, "unsupported": 12, "correct": 20,
                "near_miss": 15, "confounder": 8, "routine": 20},
}

GROUP_EVIDENCE = {"missing": EVIDENCE_MEETS, "unsupported": EVIDENCE_ABSENT,
                  "correct": EVIDENCE_MEETS, "near_miss": EVIDENCE_NEAR_MISS,
                  "confounder": EVIDENCE_CONFOUNDER, "routine": None}

TRUE_ICD10 = {"aki": "N17.9", "sepsis": "A41.9", "hyponatremia": "E87.1",
              "abla": "D62", "arf": "J96.01", "hf": "I50.21"}

# (standard term, synonym a careful detector must also recognize)
TERMS = {
    "aki": ("acute kidney injury", "acute renal failure"),
    "sepsis": ("sepsis", "sepsis secondary to the infection"),
    "hyponatremia": ("hyponatremia", "hypotonic hyponatremia"),
    "abla": ("acute blood loss anemia", "acute posthemorrhagic anemia"),
    "arf": ("acute hypoxic respiratory failure", "acute respiratory failure with hypoxia"),
    "hf": ("acute systolic heart failure", "acute HFrEF exacerbation"),
}

NEGATIONS = {
    "aki": "acute kidney injury ruled out",
    "sepsis": "no evidence of sepsis",
    "hyponatremia": "sodium mildly low, not clinically significant",
    "abla": "no acute blood loss anemia; mild drop is dilutional",
    "arf": "not in respiratory failure",
    "hf": "no acute heart failure",
}

SYNONYM_SHARE = 1 / 3
NEGATION_SHARE = 1 / 2


def plan_slots(split: str, rng: random.Random) -> list[tuple[str, str | None]]:
    """(group, condition) for every chart in the split, shuffled."""
    slots: list[tuple[str, str | None]] = []
    for offset, (group, count) in enumerate(GROUP_COUNTS[split].items()):
        for i in range(count):
            if group == "routine":
                condition = None
            elif group == "confounder":
                condition = "aki"
            else:
                condition = CONDITIONS[(i + offset) % len(CONDITIONS)]
            slots.append((group, condition))
    rng.shuffle(slots)
    return slots


def build_split(split: str, patients: list[PatientSeed], seed: int) -> tuple[list[Encounter], list[AnswerKeyRow]]:
    rng = random.Random(f"{seed}-{split}")
    slots = plan_slots(split, rng)
    if len(patients) < len(slots):
        raise ValueError(f"{split} needs {len(slots)} patients, got {len(patients)}")
    prefix = split[0].upper()
    encounters, answers = [], []
    for i, ((group, condition), patient) in enumerate(zip(slots, patients), start=1):
        enc_id = f"{prefix}{i:04d}"
        enc, ans = _build_one(rng, split, enc_id, group, condition, patient)
        encounters.append(enc)
        answers.append(ans)
    return encounters, answers


def _build_one(rng: random.Random, split: str, enc_id: str, group: str,
               condition: str | None, patient: PatientSeed) -> tuple[Encounter, AnswerKeyRow]:
    evidence = GROUP_EVIDENCE[group]
    if group == "confounder":
        patient = replace(patient, chronic=patient.chronic | {"ckd3"})
    principal = choose_principal(rng, condition, evidence)
    los, events = build_chart(rng, patient, principal, condition, evidence)
    mentions = _mentions(rng, group, condition, principal, patient)
    encounter = Encounter(enc_id, split, patient, rng.randrange(SIM_DAYS * 24), los,
                          principal, condition, evidence, group, events, mentions)
    return encounter, _answer(enc_id, split, group, condition, evidence)


def _mentions(rng: random.Random, group: str, condition: str | None,
              principal: str, patient: PatientSeed) -> tuple[Mention, ...]:
    out = [Mention(principal, PRINCIPAL_TERMS[principal], "present")]
    out += [Mention(CHRONIC_ICD10[c], CHRONIC_TERMS[c], "present") for c in sorted(patient.chronic)]
    if condition is None:
        return tuple(out)
    standard, synonym = TERMS[condition]
    true_code = TRUE_ICD10[condition]
    if group == "missing" and condition == "hf":
        out.append(Mention("I50.9", "CHF", "present"))  # specificity gap
    elif group == "unsupported":
        out.append(Mention(true_code, standard, "present"))
    elif group == "correct":
        term = synonym if rng.random() < SYNONYM_SHARE else standard
        out.append(Mention(true_code, term, "present"))
    elif group in ("near_miss", "confounder") and rng.random() < NEGATION_SHARE:
        out.append(Mention(true_code, NEGATIONS[condition], "negated"))
    return tuple(out)


def _answer(enc_id: str, split: str, group: str, condition: str | None,
            evidence: str | None) -> AnswerKeyRow:
    true_code = TRUE_ICD10.get(condition) if evidence == EVIDENCE_MEETS else None
    if group == "missing":
        documented = "I50.9" if condition == "hf" else None
        detail = ("evidence supports acute systolic HF; notes say only CHF"
                  if condition == "hf" else f"evidence meets criteria; {condition} never documented")
        return AnswerKeyRow(enc_id, split, group, condition, evidence, true_code,
                            documented, "missing_dx", detail)
    if group == "unsupported":
        return AnswerKeyRow(enc_id, split, group, condition, evidence, None,
                            TRUE_ICD10[condition], "unsupported_dx",
                            f"{condition} documented but evidence is normal")
    documented = true_code if group == "correct" else None
    details = {"correct": "evidence and documentation agree",
               "near_miss": "evidence close to but below criteria; no flag expected",
               "confounder": "creatinine high from CKD baseline, stable; not AKI",
               "routine": "no target condition"}
    return AnswerKeyRow(enc_id, split, group, condition, evidence, true_code,
                        documented, "none", details[group])
