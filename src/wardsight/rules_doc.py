"""The clinical rules in plain words, with sources, built from the same constants the rules use.

Shown on the evaluation page and in every audit-defense packet, so the wording cannot drift
from what the engine actually checks. Keyed by condition, plus the two documentation alerts.
"""

from __future__ import annotations

from wardsight import criteria as c
from wardsight.engine.evidence import ARF_MIN_INDICATORS, SERIAL_DRAWS_48H


def clinical_rules() -> list[dict]:
    """What each evidence rule checks, built from the same constants the rules use."""
    return [
        {"key": "sepsis", "condition": "Sepsis", "source": "Sepsis-3 (Singer et al., JAMA 2016)",
         "rule": (f"Suspected infection (blood cultures and antibiotics) plus a SOFA rise of at least "
                  f"{c.SEPSIS_SOFA_DELTA}: MAP < {c.SOFA_MAP_MMHG} mmHg, platelets < {c.SOFA_PLATELETS_K} K/uL, "
                  f"bilirubin ≥ {c.SOFA_BILIRUBIN_MG_DL} mg/dL, creatinine rise from the patient's own low")},
        {"key": "aki", "condition": "Acute kidney injury", "source": "KDIGO 2012 AKI guideline",
         "rule": (f"Creatinine up ≥ {c.AKI_ABS_RISE_MG_DL} mg/dL within {c.AKI_ABS_WINDOW_H} h, or to "
                  f"≥ {c.AKI_REL_RISE}x an earlier value within 7 days. A stable high baseline (CKD) does not count")},
        {"key": "hyponatremia", "condition": "Hyponatremia", "source": "Serum sodium < 135 mmol/L (standard definition)",
         "rule": (f"Sodium < {c.HYPONATREMIA_NA_MMOL_L} mmol/L that was clinically significant: treated "
                  f"(fluid restriction, salt tablets, tolvaptan, hypertonic saline) or checked "
                  f"≥ {SERIAL_DRAWS_48H} times in 48 h")},
        {"key": "abla", "condition": "Acute blood loss anemia", "source": "Common CDI clinical indicators",
         "rule": (f"Hemoglobin drop ≥ {c.ABLA_HGB_DROP_G_DL:g} g/dL with a documented bleeding source "
                  f"or a transfusion")},
        {"key": "arf", "condition": "Acute hypoxic respiratory failure", "source": "Common CDI clinical indicators",
         "rule": (f"At least {ARF_MIN_INDICATORS} of: SpO2 < {c.ARF_SPO2_PCT}% on room air, PaO2 < "
                  f"{c.ARF_PAO2_MMHG} mmHg, respiratory rate > {c.ARF_RR_PER_MIN}/min; plus oxygen therapy")},
        {"key": "unspecified_dx", "condition": "Not fully specified (alert)",
         "source": "ACDIS/AHIMA compliant query practice (2022): imprecise documentation",
         "rule": ("The evidence meets a specific diagnosis but the notes use only a vague term: 'CHF' for "
                  "acute systolic heart failure, 'anemia' for acute blood loss anemia")},
        {"key": "conflicting_dx", "condition": "Conflicting documentation (alert)",
         "source": "ACDIS/AHIMA compliant query practice (2022): conflicting documentation",
         "rule": ("One note states a diagnosis and another note rules it out, with no physician addendum "
                  "settling it. A diagnosis stated and later marked 'resolved' is a change, not a conflict")},
        {"key": "hf", "condition": "Acute systolic heart failure", "source": "2022 AHA/ACC/HFSA guideline; ESC BNP guidance",
         "rule": (f"LVEF ≤ {c.HFREF_LVEF_PCT}%, BNP > {c.HF_BNP_PG_ML} pg/mL and an IV loop diuretic")},
    ]


def rule_for(key: str) -> dict:
    return next(r for r in clinical_rules() if r["key"] == key)
