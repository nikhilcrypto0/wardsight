"""Draft physician queries: code picks evidence + options, a drafter writes only the question.

Two drafters share one gate:
- template_drafter: fixed compliant wording, no AI (offline, free)
- openai_drafter:   an LLM writes the question stem from the evidence
Every draft goes through `lint_query`; a rejected draft is retried with the
problems listed, then left for a human to rewrite. Nothing is ever sent
without review: approved queries go to a human reviewer queue.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field

from wardsight.notes.budget import Ledger
from wardsight.queries.lint import LintResult, lint_query
from wardsight.queries.options import options_for

HOUR_PREFIX = re.compile(r"^h(\d+(?:\.\d+)?):\s*")


@dataclass(frozen=True)
class QueryRequest:
    encounter_id: str
    condition: str
    kind: str                # "missing_dx" | "unsupported_dx"
    documented_phrase: str   # what the notes say (unsupported) or "" (missing)
    vague_hf: bool           # notes say only unspecified heart failure
    indicators: tuple[str, ...]
    options: tuple[str, ...]


@dataclass(frozen=True)
class QueryResult:
    request: QueryRequest
    stem: str
    lint: LintResult
    attempts: int
    drafter: str


class Stem(BaseModel):
    stem: str = Field(min_length=40, max_length=700)


# request, problems from the last attempt -> (stem or None, input_tokens, output_tokens)
Drafter = Callable[[QueryRequest, tuple[str, ...]], tuple[str | None, int, int]]


def indicators_from_evidence(evidence: str) -> tuple[str, ...]:
    """'h0: MAP 61 mmHg; h1: platelets 116 K/uL' -> ('MAP 61 mmHg at hour 0', ...)."""
    out = []
    for part in (p.strip() for p in evidence.split(";") if p.strip()):
        m = HOUR_PREFIX.match(part)
        text = HOUR_PREFIX.sub("", part)
        if m and "across the stay" not in text:
            text = f"{text} at hour {m.group(1)}"
        out.append(text)
    return tuple(out)


def make_request(encounter_id: str, condition: str, kind: str, detail: str, evidence: str) -> QueryRequest:
    quoted = re.search(r"'([^']+)'", detail)
    phrase = quoted.group(1) if kind == "unsupported_dx" and quoted else ""
    vague = kind == "missing_dx" and "unspecified heart failure" in detail
    indicators = () if evidence.startswith("no relevant") else indicators_from_evidence(evidence)
    return QueryRequest(encounter_id, condition, kind, phrase, vague, indicators, options_for(condition, kind))


def template_stem(req: QueryRequest) -> str:
    listed = "; ".join(req.indicators)
    if req.kind == "unsupported_dx":
        return (f"The record documents {req.documented_phrase}. Clinical indicators in the record: {listed}. "
                f"Based on your clinical judgment, can you please clarify whether this diagnosis is "
                f"clinically supported?")
    if req.vague_hf:
        return (f"The record documents heart failure. Clinical indicators: {listed}. Based on your "
                f"clinical judgment, can you please clarify the type and acuity of the heart failure?")
    return (f"Clinical indicators in this record: {listed}. Based on your clinical judgment, can you "
            f"please clarify the condition being evaluated and treated?")


def template_drafter(req: QueryRequest, problems: tuple[str, ...]) -> tuple[str | None, int, int]:
    return template_stem(req), 0, 0


QUERY_SYSTEM_PROMPT = """You write the question stem of a clinical documentation (CDI) query to a physician.
Rules, all mandatory (ACDIS/AHIMA compliant query practice):
- Do not lead: never tell the physician what to document, never say the findings "support",
  "meet criteria for" or are "consistent with" a diagnosis.
- For a NEW diagnosis query, do not name any diagnosis in the stem; the answer options do that.
- Never mention money, billing, DRG, reimbursement, CC/MCC or severity scores.
- Cite the clinical indicators given, using only their numbers. Do not add any other number.
- End with a question asking the physician to clarify, based on their clinical judgment.
- Plain, respectful, under 90 words. Output only the stem; the options are added separately."""


def query_user_prompt(req: QueryRequest, problems: tuple[str, ...]) -> str:
    lines = [f"Query type: {'clinical validation of a documented diagnosis' if req.kind == 'unsupported_dx' else 'new diagnosis clarification'}",
             "Clinical indicators: " + "; ".join(req.indicators),
             "Answer options (shown separately): " + " | ".join(req.options)]
    if req.documented_phrase:
        lines.append(f"The record currently documents: {req.documented_phrase}")
    if req.vague_hf:
        lines.append("The record documents heart failure without type or acuity; ask for type and acuity.")
    if problems:
        lines.append("YOUR LAST DRAFT WAS REJECTED. Fix: " + "; ".join(problems))
    return "\n".join(lines)


def openai_drafter(model: str, max_output_tokens: int) -> Drafter:
    from openai import OpenAI

    client = OpenAI()

    def call(req: QueryRequest, problems: tuple[str, ...]) -> tuple[str | None, int, int]:
        rsp = client.responses.parse(model=model, instructions=QUERY_SYSTEM_PROMPT,
                                     input=query_user_prompt(req, problems), text_format=Stem,
                                     max_output_tokens=max_output_tokens)
        parsed = rsp.output_parsed
        return (parsed.stem if parsed else None), rsp.usage.input_tokens, rsp.usage.output_tokens

    return call


def draft_query(req: QueryRequest, drafter: Drafter, name: str, attempts: int,
                ledger: Ledger | None = None, model: str = "") -> QueryResult:
    problems: tuple[str, ...] = ()
    stem, result = "", LintResult(False, ("no draft produced",))
    for attempt in range(1, attempts + 1):
        if ledger:
            ledger.check_before_call()
        stem_or_none, tokens_in, tokens_out = drafter(req, problems)
        stem = stem_or_none or ""
        result = (lint_query(stem, req.options, req.indicators, req.condition, req.kind) if stem
                  else LintResult(False, ("output did not match the schema",)))
        if ledger:
            ledger.record(req.encounter_id, model, tokens_in, tokens_out, "ok" if result.ok else "rejected")
        if result.ok:
            return QueryResult(req, stem, result, attempt, name)
        problems = result.problems
    return QueryResult(req, stem, result, attempts, name)
