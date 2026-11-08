"""Documentation reader: which target diagnoses do the notes actually state?

Finds diagnosis wording in the note text (with synonyms), then decides whether
each mention is affirmed or negated ("ruled out", "no evidence of"). Uses its
own lexicon, written independently of the generator's term list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from wardsight.engine.chart import NoteText

# ICD-10 code -> phrases that state it. Longest phrases are tried first.
LEXICON: dict[str, tuple[str, ...]] = {
    "N17.9": ("acute kidney injury", "acute kidney failure", "acute renal failure",
              "acute renal injury", "aki"),
    "A41.9": ("septic shock", "severe sepsis", "septicemia", "sepsis", "septic"),
    "E87.1": ("hypotonic hyponatremia", "hyponatremia", "hyponatraemia"),
    "D62": ("acute blood loss anemia", "acute posthemorrhagic anemia", "acute posthemorrhagic anaemia",
            "acute blood loss anaemia"),
    "J96.01": ("acute hypoxic respiratory failure", "acute hypoxemic respiratory failure",
               "acute respiratory failure with hypoxia", "acute respiratory failure", "respiratory failure"),
    "I50.21": ("acute on chronic systolic heart failure", "acute systolic heart failure",
               "acute systolic chf", "acute hfref", "acute heart failure with reduced ejection fraction"),
    "I50.9": ("congestive heart failure", "heart failure", "chf"),
}

PRE_NEGATION = ("no evidence of", "negative for", "ruled out", "rule out", "without", "denies",
                "not in", "not", "no")
POST_NEGATION = ("ruled out", "was ruled out", "unlikely", "is not present", "excluded")
CLAUSE_SPLIT = re.compile(r"[.;\n]")


@dataclass(frozen=True)
class Mention:
    icd10: str
    phrase: str
    negated: bool
    clause: str


def _phrase_re(phrase: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])")


PATTERNS = [(code, phrase, _phrase_re(phrase))
            for code, phrases in LEXICON.items() for phrase in sorted(phrases, key=len, reverse=True)]


def _is_negated(clause: str, start: int, end: int) -> bool:
    before, after = clause[:start], clause[end:]
    words_before = re.findall(r"[a-z]+", before)[-6:]
    window = " ".join(words_before)
    if any(re.search(rf"(?<![a-z]){re.escape(cue)}(?![a-z])", window) for cue in PRE_NEGATION):
        return True
    return any(after.strip().startswith(cue) for cue in POST_NEGATION)


def find_mentions(notes: tuple[NoteText, ...]) -> list[Mention]:
    mentions: list[Mention] = []
    for note in notes:
        for clause in CLAUSE_SPLIT.split(note.text.lower()):
            taken: list[tuple[int, int]] = []
            for code, phrase, pattern in PATTERNS:
                for m in pattern.finditer(clause):
                    if any(s < m.end() and m.start() < e for s, e in taken):
                        continue  # part of a longer phrase already matched
                    taken.append((m.start(), m.end()))
                    mentions.append(Mention(code, phrase, _is_negated(clause, m.start(), m.end()),
                                            clause.strip()))
    return mentions


def documented_codes(notes: tuple[NoteText, ...]) -> set[str]:
    """Codes stated as present (affirmed) anywhere in the notes."""
    return {m.icd10 for m in find_mentions(notes) if not m.negated}
