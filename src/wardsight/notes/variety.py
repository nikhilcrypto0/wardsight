"""Real-world wording for the 'variety' test: each planned diagnosis written the way physicians write it.

Every variant keeps the meaning the answer key expects under the coding rules, so a miss is the
note reader's fault, not the test's:
- abbreviations and synonyms ("AKI", "AHRF", "ABLA", "HFrEF exacerbation")
- uncertainty, which counts as documented for an inpatient stay: ICD-10-CM Official Guidelines,
  Section II.H and III.C ("probable", "suspected", "likely", "questionable", "possible",
  "still to be ruled out" -> code as if it existed)
- one-letter typos ("sespis"): a coder reading the note still codes it
- other forms of negation for ruled-out diagnoses ("negative for", "excluded", "unlikely")

Not used: "urosepsis". The guidelines give it no code and say the provider must be queried
(Section I.C.1.d.1.a.ii), so it would change the meaning, not just the wording.
"""

from __future__ import annotations

import random
from dataclasses import replace

from wardsight.models import Mention

PRESENT: dict[str, tuple[str, ...]] = {
    "N17.9": ("AKI", "probable acute kidney injury", "concern for AKI", "acute kidny injury"),
    "A41.9": ("likely sepsis", "possible sepsis", "r/o sepsis", "sespis"),
    "E87.1": ("probable hyponatremia", "suspected hyponatremia", "hyponatermia"),
    "D62": ("ABLA", "likely acute blood loss anemia", "acute blood los anemia"),
    "J96.01": ("AHRF", "acute hypoxemic respiratory failure", "likely acute hypoxic respiratory failure",
               "acute hypoxic respiratory failre"),
    "I50.21": ("HFrEF exacerbation", "acute systolic CHF", "acute systolic hart failure"),
}

NEGATED: dict[str, tuple[str, ...]] = {
    "N17.9": ("no AKI", "negative for acute kidney injury", "AKI excluded"),
    "A41.9": ("sepsis ruled out", "sepsis unlikely", "negative for sepsis"),
    "E87.1": ("no hyponatremia", "hyponatremia excluded"),
    "D62": ("no ABLA", "acute blood loss anemia ruled out"),
    "J96.01": ("no AHRF", "respiratory failure ruled out"),
}


def vary(mentions: tuple[Mention, ...], rng: random.Random) -> tuple[Mention, ...]:
    """Swap each planned diagnosis wording for a same-meaning variant (or keep it, one time in four)."""
    out = []
    for m in mentions:
        pool = (PRESENT if m.assertion == "present" else NEGATED).get(m.icd10, ())
        if pool and "," not in m.term and rng.random() >= 0.25:  # keep 'X, resolved' and odd phrasings as planned
            m = replace(m, term=rng.choice(pool))
        out.append(m)
    return tuple(out)


def variety_rng(encounter_id: str, seed: int = 0) -> random.Random:
    """The same chart always gets the same wording, so retries and reruns are reproducible."""
    return random.Random(f"{seed}-variety-{encounter_id}")
