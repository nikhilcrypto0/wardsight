"""Answer options for each query, decided by code, never by the AI.

Multiple-choice queries offer clinically reasonable alternatives plus
"Other" and "Unable to determine", as the ACDIS/AHIMA query practice brief
(2022 update) describes. Yes/no is never used to introduce a new diagnosis.
"""

from __future__ import annotations

OTHER = "Other (please specify)"
UNDETERMINED = "Unable to determine"

MISSING_DX_OPTIONS: dict[str, tuple[str, ...]] = {
    "aki": ("Acute kidney injury", "Chronic kidney disease without acute injury",
            "Prerenal azotemia / dehydration without acute kidney injury"),
    "sepsis": ("Sepsis", "Localized infection without sepsis"),
    "hyponatremia": ("Hyponatremia", "Low sodium value, not clinically significant"),
    "abla": ("Acute blood loss anemia", "Dilutional drop in hemoglobin", "Chronic anemia"),
    "arf": ("Acute hypoxic respiratory failure", "Hypoxemia without respiratory failure"),
    "hf": ("Acute systolic (HFrEF) heart failure", "Acute on chronic systolic heart failure",
           "Acute diastolic (HFpEF) heart failure", "Chronic heart failure, not acute"),
}

# "Not fully specified": the vague term is documented; the options are the specific types.
UNSPECIFIED_OPTIONS: dict[str, tuple[str, ...]] = {
    "hf": MISSING_DX_OPTIONS["hf"],
    "abla": ("Acute blood loss anemia", "Iron deficiency anemia", "Anemia of chronic disease",
             "Dilutional drop in hemoglobin"),
}

CONDITION_NAMES = {"aki": "acute kidney injury", "sepsis": "sepsis", "hyponatremia": "hyponatremia",
                   "abla": "acute blood loss anemia", "arf": "acute hypoxic respiratory failure",
                   "hf": "acute systolic heart failure"}


def options_for(condition: str, kind: str) -> tuple[str, ...]:
    if kind == "missing_dx":
        return (*MISSING_DX_OPTIONS[condition], OTHER, UNDETERMINED)
    if kind == "unspecified_dx":
        return (*UNSPECIFIED_OPTIONS[condition], OTHER, UNDETERMINED)
    name = CONDITION_NAMES[condition]
    if kind == "conflicting_dx":  # the notes disagree: ask which is right, without favouring either
        return (f"{name[0].upper()}{name[1:]} is present", f"{name[0].upper()}{name[1:]} has been ruled out",
                OTHER, UNDETERMINED)
    return (f"{name[0].upper()}{name[1:]} is clinically supported (please document the supporting findings)",
            f"{name[0].upper()}{name[1:]} has been ruled out", OTHER, UNDETERMINED)
