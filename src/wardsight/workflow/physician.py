"""Simulated physician who answers queries (rule-based; an LLM version can replace it).

Behaves like a busy real physician, not a rubber stamp: usually agrees with a
well-supported query, sometimes picks an alternative, sometimes cannot decide,
and pushes back on most validation queries. Deterministic per query, so a demo
replays the same way every time.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

AGREE_PCT = 75        # new-diagnosis query: picks the first (queried) option
ALTERNATIVE_PCT = 15  # picks the second option instead
RULE_OUT_PCT = 70     # validation query: rules the documented diagnosis out


@dataclass(frozen=True)
class Reply:
    option_index: int
    comment: str


def _roll(query_id: str) -> int:
    return int(hashlib.sha256(query_id.encode()).hexdigest(), 16) % 100


def rule_based_reply(query_id: str, kind: str, options: tuple[str, ...]) -> Reply:
    roll = _roll(query_id)
    undetermined = len(options) - 1
    if kind == "unsupported_dx":
        if roll < RULE_OUT_PCT:
            return Reply(1, "Reviewed the labs again; agree it is not supported. Ruled out.")
        return Reply(0, "I still believe this is present clinically; will add my reasoning to the note.")
    if roll < AGREE_PCT:
        return Reply(0, "Agree, thank you. Addendum entered.")
    if roll < AGREE_PCT + ALTERNATIVE_PCT:
        return Reply(1, "Clinically I think this fits better. Addendum entered.")
    return Reply(undetermined, "Not enough to call it either way at this point.")
