"""Published clinical thresholds used to GENERATE synthetic scenarios.

Every constant cites where it comes from. The detection rules (milestone 2)
are written separately and must never import the generation code in
`scenarios.py`; sharing a published threshold is fine, sharing logic is not.
"""

# KDIGO 2012 Clinical Practice Guideline for Acute Kidney Injury:
# serum creatinine rise >= 0.3 mg/dL within 48 h, or >= 1.5x baseline within 7 days.
AKI_ABS_RISE_MG_DL = 0.3
AKI_ABS_WINDOW_H = 48
AKI_REL_RISE = 1.5

# Sepsis-3 (Singer et al., JAMA 2016): suspected infection plus an acute
# SOFA score increase of >= 2 points.
SEPSIS_SOFA_DELTA = 2
SOFA_MAP_MMHG = 70          # cardiovascular: MAP < 70 mmHg = 1 point
SOFA_PLATELETS_K = 150      # coagulation: platelets < 150 x10^3/uL = 1 point
SOFA_BILIRUBIN_MG_DL = 1.2  # liver: bilirubin 1.2-1.9 mg/dL = 1 point

# Hyponatremia: serum sodium < 135 mmol/L.
HYPONATREMIA_NA_MMOL_L = 135

# Acute blood loss anemia: hemoglobin drop >= 2 g/dL with a bleeding source,
# a common CDI clinical indicator (paired here with transfusion or serial H/H).
ABLA_HGB_DROP_G_DL = 2.0

# Acute hypoxemic respiratory failure, common CDI clinical indicators:
# SpO2 < 91% on room air, PaO2 < 60 mmHg, respiratory rate > 28/min.
ARF_SPO2_PCT = 91
ARF_PAO2_MMHG = 60
ARF_RR_PER_MIN = 28

# Heart failure with reduced ejection fraction: LVEF <= 40%
# (2022 AHA/ACC/HFSA Heart Failure Guideline). BNP > 400 pg/mL makes heart
# failure likely (ESC heart failure guidance).
HFREF_LVEF_PCT = 40
HF_BNP_PG_ML = 400
