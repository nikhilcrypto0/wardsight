"""DRG impact: group the stay as documented, and as it would be if a flag is resolved.

Uses `msdrg`, an open-source port of the CMS MS-DRG grouper. Diagnosis codes
come from the problem list, the reason for admission, and what the notes
affirm. Sequencing rule used: sepsis present on admission is principal, with
the infection secondary.
"""

from __future__ import annotations

import atexit
from dataclasses import dataclass
from functools import lru_cache

import msdrg

from wardsight.engine.chart import Chart
from wardsight.engine.documentation import documented_codes

GROUPER_VERSION = 440  # MS-DRG v44.0
DISCHARGED_HOME = 1
SEX_CODE = {"male": 0, "female": 1}
SEPSIS = "A41.9"

# Reason-for-admission wording -> principal diagnosis code
REASON_CODES = (
    ("pneumonia", "J18.9"), ("urinary tract infection", "N39.0"), ("cellulitis", "L03.116"),
    ("copd exacerbation", "J44.1"), ("syncope", "R55"), ("gi bleed", "K92.2"),
)
TARGET_CODES = ("N17.9", "A41.9", "E87.1", "D62", "J96.01", "I50.21", "I50.9")


@dataclass(frozen=True)
class DrgResult:
    drg: int
    description: str
    severity: str  # "NONE" | "CC" | "MCC"
    principal: str
    secondary: tuple[str, ...]


@lru_cache(maxsize=1)
def _grouper() -> msdrg.MsdrgGrouper:
    grouper = msdrg.MsdrgGrouper()
    atexit.register(grouper.close)  # release the native grouper before interpreter shutdown
    return grouper


def principal_from_reason(reason: str) -> str:
    text = reason.lower()
    for needle, code in REASON_CODES:
        if needle in text:
            return code
    raise ValueError(f"no principal diagnosis mapping for reason: {reason!r}")


def coded_diagnoses(chart: Chart) -> set[str]:
    """Target codes affirmed in the notes, plus chronic problem-list codes."""
    codes = documented_codes(chart.notes) & set(TARGET_CODES)
    if "I50.21" in codes:
        codes.discard("I50.9")  # the specific code replaces the unspecified one
    return codes | set(chart.problem_list)


def group(chart: Chart, codes: set[str]) -> DrgResult:
    reason_code = principal_from_reason(chart.reason_for_admission)
    principal = SEPSIS if SEPSIS in codes else reason_code
    secondary = tuple(sorted((codes | {reason_code}) - {principal}))
    claim = msdrg.create_claim(
        version=GROUPER_VERSION, age=chart.age, sex=SEX_CODE.get(chart.sex, 2),
        discharge_status=DISCHARGED_HOME, pdx=principal.replace(".", ""), pdx_poa="Y",
        sdx=[(code.replace(".", ""), "Y") for code in secondary],
    )
    result = _grouper().group(claim)
    return DrgResult(int(result["final_drg"]), result["final_drg_description"],
                     result["final_severity"], principal, secondary)
