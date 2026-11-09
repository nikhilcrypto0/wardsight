"""Query rules check: deterministic gate every drafted query must pass.

Rules follow the ACDIS/AHIMA "Guidelines for Achieving a Compliant Query
Practice" (2022 update): a query must not lead the provider to a specific
diagnosis, must not mention financial impact, must be supported by clinical
indicators from the record, and multiple-choice queries include "other" and
"unable to determine". Plus one AI-specific rule: no number may appear that
is not in the cited chart indicators (no invented values).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from wardsight.engine.documentation import LEXICON
from wardsight.queries.options import OTHER, UNDETERMINED

TARGET_CODE = {"aki": "N17.9", "sepsis": "A41.9", "hyponatremia": "E87.1",
               "abla": "D62", "arf": "J96.01", "hf": "I50.21"}

FINANCIAL = re.compile(
    r"\b(drg|ms-drg|reimburse\w*|payment|paid|pay|revenue|billing|bill|money|dollars?|cost|"
    r"cc|mcc|case mix|cmi|severity of illness|soi|rom|profit|financial|denials?)\b|\$", re.IGNORECASE)

LEADING = re.compile(
    r"please (document|add|chart|code)|consider documenting|can you document|should be documented|"
    r"supports? (a |the )?diagnosis of|meets? (the )?criteria for|consistent with|indicative of|"
    r"confirm(ing)? (the |a )?diagnosis|we recommend|you should|agree that|it is likely",
    re.IGNORECASE)

NUMBER = re.compile(r"\d+(?:\.\d+)?")
MAX_STEM_CHARS = 700
# A new-diagnosis query needs a clinical picture; a validation query must at least show
# what the record actually contains for the documented diagnosis.
MIN_INDICATORS = {"missing_dx": 2, "unsupported_dx": 1}
YES_NO = {"yes", "no"}


@dataclass(frozen=True)
class LintResult:
    ok: bool
    problems: tuple[str, ...]


def _target_phrases(condition: str) -> tuple[str, ...]:
    return LEXICON[TARGET_CODE[condition]]


def lint_query(stem: str, options: tuple[str, ...], indicators: tuple[str, ...],
               condition: str, kind: str) -> LintResult:
    problems: list[str] = []
    text = stem.lower()

    if m := FINANCIAL.search(stem):
        problems.append(f"mentions financial impact: '{m.group(0)}'")
    if m := LEADING.search(stem):
        problems.append(f"leading wording: '{m.group(0)}'")
    if kind == "missing_dx":
        for phrase in _target_phrases(condition):
            if re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", text):
                problems.append(f"names the diagnosis in the question: '{phrase}' (belongs only in the options)")
                break

    if len(indicators) < MIN_INDICATORS[kind]:
        problems.append(f"cites {len(indicators)} clinical indicator(s); at least {MIN_INDICATORS[kind]} required")
    allowed_numbers = {n for ind in indicators for n in NUMBER.findall(ind)}
    invented = sorted({n for n in NUMBER.findall(stem)} - allowed_numbers)
    if invented:
        problems.append(f"numbers not found in the chart indicators: {', '.join(invented)}")

    lowered = {o.lower() for o in options}
    if OTHER not in options or UNDETERMINED not in options:
        problems.append("options must include 'Other (please specify)' and 'Unable to determine'")
    if kind == "missing_dx" and lowered & YES_NO:
        problems.append("yes/no options may not be used to introduce a new diagnosis")
    if len(options) - 2 < 2:
        problems.append("needs at least two clinically reasonable choices besides Other / Unable to determine")

    if "?" not in stem and "clarify" not in text:
        problems.append("must ask a question (end with '?' or ask the provider to clarify)")
    if len(stem) > MAX_STEM_CHARS:
        problems.append(f"too long ({len(stem)} chars, max {MAX_STEM_CHARS})")
    return LintResult(not problems, tuple(problems))
