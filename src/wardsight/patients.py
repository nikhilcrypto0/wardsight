"""Patient seeds: from Synthea FHIR output, or a small built-in generator.

Synthea supplies who the patient is (age, sex, chronic history). Everything
that happens during the hospital stay comes from the scenario engine, because
Synthea does not model inpatient lab trends at hourly resolution.
"""

from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path

from wardsight.models import PatientSeed

SIM_START = date(2026, 3, 1)
MIN_AGE = 45

# Synthea condition display text -> chronic flag used by the scenario engine
SYNTHEA_CHRONIC = {
    "hypertension": "htn",
    "diabetes": "dm2",
    "chronic kidney disease": "ckd3",
    "chronic obstructive": "copd",
    "pulmonary emphysema": "copd",
    "chronic obstructive bronchitis": "copd",
}

BUILTIN_RATES = {"htn": 0.55, "dm2": 0.30, "ckd3": 0.15, "copd": 0.15}


def builtin_patients(n: int, seed: int) -> list[PatientSeed]:
    rng = random.Random(f"{seed}-patients")
    return [
        PatientSeed(
            patient_id=f"P{i:04d}",
            age=rng.randint(MIN_AGE, 90),
            sex=rng.choice(("female", "male")),
            chronic=frozenset(k for k, rate in BUILTIN_RATES.items() if rng.random() < rate),
            source="builtin",
        )
        for i in range(1, n + 1)
    ]


def _age_on(birth: str, on: date) -> int:
    b = date.fromisoformat(birth[:10])
    return on.year - b.year - ((on.month, on.day) < (b.month, b.day))


def _chronic_flags(bundle: dict) -> frozenset[str]:
    flags = set()
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        if res.get("resourceType") != "Condition" or "abatementDateTime" in res:
            continue
        text = (res.get("code", {}).get("text") or "").lower()
        flags.update(flag for needle, flag in SYNTHEA_CHRONIC.items() if needle in text)
    return frozenset(flags)


def synthea_patients(fhir_dir: Path, n: int) -> list[PatientSeed]:
    """Read Synthea patient bundles; keep living adults aged MIN_AGE+."""
    seeds: list[PatientSeed] = []
    for path in sorted(fhir_dir.glob("*.json")):
        if path.name.startswith(("hospitalInformation", "practitionerInformation")):
            continue
        bundle = json.loads(path.read_text())
        patient = next((e["resource"] for e in bundle.get("entry", [])
                        if e.get("resource", {}).get("resourceType") == "Patient"), None)
        if not patient or "deceasedDateTime" in patient or "birthDate" not in patient:
            continue
        age = _age_on(patient["birthDate"], SIM_START)
        if age < MIN_AGE:
            continue
        seeds.append(PatientSeed(f"P{len(seeds) + 1:04d}", age, patient.get("gender", "female"),
                                 _chronic_flags(bundle), "synthea"))
        if len(seeds) == n:
            return seeds
    raise ValueError(f"Synthea output in {fhir_dir} has only {len(seeds)} usable adults; need {n}")
