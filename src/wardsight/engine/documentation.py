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
            "acute blood loss anaemia", "abla"),
    "J96.01": ("acute hypoxic respiratory failure", "acute hypoxemic respiratory failure",
               "acute respiratory failure with hypoxia", "acute respiratory failure", "respiratory failure",
               "ahrf"),
    "I50.21": ("acute on chronic systolic heart failure", "acute systolic heart failure",
               "acute systolic chf", "acute hfref", "acute heart failure with reduced ejection fraction",
               "hfref exacerbation"),
    "I50.9": ("congestive heart failure", "heart failure", "chf"),
    "D64.9": ("anemia", "anaemia"),  # after D62, so "acute blood loss anemia" is matched whole first
}

# A cue before the diagnosis that it is absent, or not current ("history of", "s/p": a past problem).
PRE_NEGATION = ("no evidence of", "negative for", "ruled out", "without", "denies", "not in", "not", "no",
                "unlikely", "history of", "h/o", "s/p", "status post")
# Uncertainty is NOT negation. For an inpatient stay a diagnosis qualified as "probable", "suspected",
# "likely", "questionable", "possible" or "still to be ruled out" is coded as if it existed
# (ICD-10-CM Official Guidelines for Coding and Reporting, Section II.H and III.C). So "rule out
# sepsis" and "r/o sepsis" document sepsis; only the past tense "ruled out" excludes it.
UNCERTAIN = ("rule out", "r/o", "cannot rule out", "can't rule out", "possible", "probable", "likely",
             "suspected", "questionable", "concern for", "consistent with", "compatible with")
POST_NEGATION = ("ruled out", "was ruled out", "has been ruled out", "unlikely", "is not present",
                 "excluded")
CLAUSE_SPLIT = re.compile(r"[.;\n]")
ADDENDUM = "addendum"  # a physician's later clarification; it overrides earlier notes


@dataclass(frozen=True)
class Mention:
    icd10: str
    phrase: str
    negated: bool
    clause: str
    addendum: bool = False
    note_type: str = ""


def _phrase_re(phrase: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])")


PATTERNS = [(code, phrase, _phrase_re(phrase))
            for code, phrases in LEXICON.items() for phrase in sorted(phrases, key=len, reverse=True)]


def _last_cue(window: str, cues: tuple[str, ...]) -> int:
    """End position of the cue closest to the diagnosis, or -1."""
    ends = [m.end() for cue in cues for m in re.finditer(rf"(?<![a-z]){re.escape(cue)}(?![a-z])", window)]
    return max(ends, default=-1)


def _is_negated(clause: str, start: int, end: int) -> bool:
    before, after = clause[:start], clause[end:]
    words = list(re.finditer(r"[a-z/']+", before))[-6:]
    window = before[words[0].start():] if words else ""
    negation = _last_cue(window, PRE_NEGATION)
    if negation >= 0 and negation > _last_cue(window, UNCERTAIN):
        return True  # "no fever, likely sepsis": the uncertainty cue is closer, so not negated
    return any(after.strip().startswith(cue) for cue in POST_NEGATION)


def _near_miss_spelling(candidate: str, phrase: str) -> bool:
    """A one-slip typo of a long diagnosis word ("sespis", "hyponatermia"), never a different word.

    8+ letters: one insert, delete, swap or wrong letter. 6-7 letters: only two swapped
    neighbours, so "anemic" is not read as "anemia". Shorter words: exact only.
    """
    if candidate == phrase or len(phrase) < 6 or candidate[:1] != phrase[:1]:
        return False
    if len(phrase) < 8:
        return (len(candidate) == len(phrase) and sorted(candidate) == sorted(phrase)
                and sum(a != b for a, b in zip(candidate, phrase)) == 2
                and any(candidate[i] == phrase[i + 1] and candidate[i + 1] == phrase[i] and candidate[i] != phrase[i]
                        for i in range(len(phrase) - 1)))
    if abs(len(candidate) - len(phrase)) > 1:
        return False
    return _osa(candidate, phrase) == 1


def _osa(a: str, b: str) -> int:
    """Edit distance counting a swap of two neighbouring letters as one edit."""
    d = [[i + j if i * j == 0 else 0 for j in range(len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


def find_mentions(notes: tuple[NoteText, ...]) -> list[Mention]:
    mentions: list[Mention] = []
    for note in notes:
        for clause in CLAUSE_SPLIT.split(note.text.lower()):
            found: dict[tuple[int, int], Mention] = {}
            for code, phrase, pattern in PATTERNS:
                for m in pattern.finditer(clause):
                    if any(s < m.end() and m.start() < e for s, e in found):
                        continue  # part of a longer phrase already matched
                    found[(m.start(), m.end())] = Mention(code, phrase, _is_negated(clause, m.start(), m.end()),
                                                          clause.strip(), note.note_type == ADDENDUM,
                                                          note.note_type)
            _add_typos(clause, found, note)
            mentions += [found[span] for span in sorted(found)]
    return mentions


def _add_typos(clause: str, found: dict[tuple[int, int], Mention], note: NoteText) -> None:
    """Second pass: misspelled diagnosis wording. A misspelled longer phrase replaces a shorter exact
    match inside it ("acute blood los anemia" is ABLA, not just "anemia"); it never overlaps a longer one."""
    words = list(re.finditer(r"[a-z]+", clause))
    for code, phrase, _ in PATTERNS:
        n = phrase.count(" ") + 1
        for i in range(len(words) - n + 1):
            s, e = words[i].start(), words[i + n - 1].end()
            overlap = [span for span in found if span[0] < e and s < span[1]]
            if any(not (s <= a and b <= e) or b - a >= e - s for a, b in overlap):
                continue  # overlaps something it does not fully contain, or something as long
            if _near_miss_spelling(" ".join(w.group() for w in words[i:i + n]), phrase):
                for span in overlap:
                    del found[span]
                found[(s, e)] = Mention(code, phrase, _is_negated(clause, s, e), clause.strip(),
                                        note.note_type == ADDENDUM, note.note_type)


def documented_codes(notes: tuple[NoteText, ...]) -> set[str]:
    """Codes the record currently affirms.

    Affirmed anywhere in the notes, except that a physician addendum wins: a
    code the addendum rules out is removed, a code it confirms is added.
    """
    mentions = find_mentions(notes)
    affirmed = {m.icd10 for m in mentions if not m.negated and not m.addendum}
    ruled_out = {m.icd10 for m in mentions if m.negated and m.addendum}
    confirmed = {m.icd10 for m in mentions if not m.negated and m.addendum}
    return (affirmed - ruled_out) | confirmed
