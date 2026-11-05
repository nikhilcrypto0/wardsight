"""Code tables: LOINC for observations, ICD-10-CM for diagnoses."""

# analyte key -> (LOINC code, display name, unit)
LOINC = {
    "creatinine": ("2160-0", "Creatinine [Mass/volume] in Serum or Plasma", "mg/dL"),
    "sodium": ("2951-2", "Sodium [Moles/volume] in Serum or Plasma", "mmol/L"),
    "hemoglobin": ("718-7", "Hemoglobin [Mass/volume] in Blood", "g/dL"),
    "platelets": ("777-3", "Platelets [#/volume] in Blood", "10*3/uL"),
    "bilirubin": ("1975-2", "Bilirubin.total [Mass/volume] in Serum or Plasma", "mg/dL"),
    "lactate": ("2524-7", "Lactate [Moles/volume] in Serum or Plasma", "mmol/L"),
    "wbc": ("6690-2", "Leukocytes [#/volume] in Blood", "10*3/uL"),
    "bnp": ("30934-4", "Natriuretic peptide B [Mass/volume] in Serum or Plasma", "pg/mL"),
    "pao2": ("2703-7", "Oxygen [Partial pressure] in Arterial blood", "mm[Hg]"),
    "lvef": ("10230-1", "Left ventricular Ejection fraction", "%"),
    "heart_rate": ("8867-4", "Heart rate", "/min"),
    "resp_rate": ("9279-1", "Respiratory rate", "/min"),
    "sbp": ("8480-6", "Systolic blood pressure", "mm[Hg]"),
    "dbp": ("8462-4", "Diastolic blood pressure", "mm[Hg]"),
    "map": ("8478-0", "Mean blood pressure", "mm[Hg]"),
    "spo2": ("59408-5", "Oxygen saturation in Arterial blood by Pulse oximetry", "%"),
    "temp": ("8310-5", "Body temperature", "Cel"),
    "o2_flow": ("3151-8", "Inhaled oxygen flow rate", "L/min"),
}

# ICD-10-CM code -> description
ICD10 = {
    # principal reasons for admission
    "J18.9": "Pneumonia, unspecified organism",
    "N39.0": "Urinary tract infection, site not specified",
    "L03.116": "Cellulitis of left lower limb",
    "J44.1": "Chronic obstructive pulmonary disease with (acute) exacerbation",
    "R55": "Syncope and collapse",
    "K92.2": "Gastrointestinal hemorrhage, unspecified",
    # target conditions
    "N17.9": "Acute kidney failure, unspecified",
    "A41.9": "Sepsis, unspecified organism",
    "E87.1": "Hypo-osmolality and hyponatremia",
    "D62": "Acute posthemorrhagic anemia",
    "J96.01": "Acute respiratory failure with hypoxia",
    "I50.21": "Acute systolic (congestive) heart failure",
    "I50.9": "Heart failure, unspecified",
    # chronic conditions
    "I10": "Essential (primary) hypertension",
    "E11.9": "Type 2 diabetes mellitus without complications",
    "N18.30": "Chronic kidney disease, stage 3 unspecified",
    "J44.9": "Chronic obstructive pulmonary disease, unspecified",
}

CHRONIC_ICD10 = {"htn": "I10", "dm2": "E11.9", "ckd3": "N18.30", "copd": "J44.9"}
CHRONIC_TERMS = {
    "htn": "hypertension",
    "dm2": "type 2 diabetes",
    "ckd3": "chronic kidney disease stage 3",
    "copd": "COPD",
}

PRINCIPAL_TERMS = {
    "J18.9": "community-acquired pneumonia",
    "N39.0": "urinary tract infection",
    "L03.116": "cellulitis of the left lower leg",
    "J44.1": "COPD exacerbation",
    "R55": "syncope",
    "K92.2": "upper GI bleed",
}
