#!/usr/bin/env python3
"""Chain-of-custody helpers for provenance records.

`verify_provenance.py` answers "is this record true?". These answer the four questions it
cannot:

  ROUNDING   what figure does the source actually print, as opposed to what the deliverable
             prints? A record that sets source_value equal to value defeats the ROUND check
             entirely, because it then compares a value to itself.
  CONTEXT    was this occurrence the right one, or merely the only one with those digits?
  FIDELITY   does the deliverable's clause say what the quote says, or has direction,
             causation or scope been added in the retelling?
  HISTORY    what was this value before, and when did it change? Row-numbered ids and a file
             rewritten on every run answer neither.

The contextual scorer is imported from check_rounding rather than reimplemented. Two scorers
would drift, and the one there is already tuned: content-word overlap plus co-occurring
figures, which makes a match harder to earn by accident.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

from check_rounding import (  # noqa: F401
    MIN_CONTEXT, NUM, all_occurrences, best_occurrence, dec, words,
)

AMBIGUOUS = "ambiguous"


# ------------------------------------------------------------------ identity
def _flat(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def stable_id(section: str, value: str, clause: str) -> str:
    """An id that survives edits elsewhere in the document.

    Worksheet row numbers were the previous scheme, and they shift whenever a sentence is
    added anywhere above, so "the same id" never meant the same value twice. Hashing the
    value together with its section and surrounding clause means the id changes only when the
    claim itself changes, which is exactly when a superseding record is wanted.
    """
    key = "%s|%s|%s" % (_flat(section), _flat(value), _flat(clause)[:200])
    return "p" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]


# ------------------------------------------------------------------ rounding + context
def resolve_source_value(value, unit, sources, want, siblings=()):
    """What the source prints for this value, scored in context.

    Returns (source_value, score, window, ref, rounded) or None.

    Mirrors check_rounding's decision, which is the one that avoids both failure modes: an
    exact occurrence that matches in context settles it, whatever other precision the source
    carries elsewhere. Only when no exact occurrence matches in context, and a more precise
    figure does, is the deliverable's value a rounded form.
    """
    exact = all_occurrences(value, unit, sources, want, True, siblings)
    if exact and exact[0][0] >= MIN_CONTEXT:
        s, v, ref, win = exact[0]
        return v, s, win, ref, False

    parents = all_occurrences(value, unit, sources, want, False, siblings)
    strong = [p for p in parents if p[0] >= MIN_CONTEXT]
    if strong:
        top = strong[0][0]
        tied = {p[1] for p in strong if p[0] == top}
        s, v, ref, win = strong[0]
        # Two different precise figures, equally well matched, both rounding to the printed
        # value. Picking the first is how the wrong parent gets recorded as fact; the honest
        # output names the problem and leaves a human to settle it.
        return (AMBIGUOUS if len(tied) > 1 else v), top, win, ref, True

    if exact:
        s, v, ref, win = exact[0]
        return v, s, win, ref, False
    return None


def split_value(value: str):
    """('4.2 days') -> ('4.2', 'days'). Unit is None when the value is bare."""
    m = re.match(r"^\s*([\d.,]+)\s*(.*)$", str(value))
    if not m:
        return str(value), None
    return m.group(1), (m.group(2).strip() or None)


# ------------------------------------------------------------------ courtesy check
def courtesy_check(value, unit, sources, want, siblings=(), ref=None, checked=None):
    """Does the reference the AUTHOR cited contain the value they wrote?

    This is not provenance and must never be stored as such. Provenance answers "where did
    this come from", which for an author-entered value only the author knows. This answers
    the narrower question "does the document you cited contain this figure", which is worth
    asking precisely because a `not_found` is informative.

    The result is deliberately kept in its own object by callers, so a passage found here can
    never be mistaken for a witnessed quote.
    """
    out = {"ref": ref, "result": "no_citation", "score": None, "passage": "",
           "checked": checked}
    if ref is None or not sources:
        return out
    res = resolve_source_value(value, unit, sources, want, siblings)
    if res is None or res[1] < MIN_CONTEXT:
        out["result"] = "not_found"
        out["score"] = None if res is None else res[1]
        return out
    out["result"] = "consistent"
    out["score"] = res[1]
    out["passage"] = re.sub(r"\s+", " ", res[2]).strip()
    return out


# ------------------------------------------------------------------ locator sanity
def locator_ok(locator: str, url: str, paged_refs=(), ref=None):
    """Why a locator is wrong, or None when it is fine.

    Two ways a locator misleads even when the quote is correct. It can link to a document the
    record does not cite, and it can name a page in a source that has no pages, which happens
    when locator prose is inherited from a claim row belonging to a different reference.
    """
    links = re.findall(r"\((https?://[^)]+)\)", locator or "")
    if url and links:
        base = url.split("#")[0].rstrip("/")
        if not any(l.split("#")[0].rstrip("/") == base for l in links):
            return "locator links to %s but the record cites %s" % (links[0][:60], base[:60])
    if re.search(r"\bpp?\.\s*\d+", locator or "") and ref is not None and ref not in paged_refs:
        return "locator names a page but reference %s is not a paged source" % ref
    return None


# ------------------------------------------------------------------ fidelity
# Language that asserts something a bare figure cannot. If the clause carries it and the
# quote does not, the deliverable has added meaning in the retelling. That is not always
# wrong, the source may say it elsewhere, so this produces a review list and not a verdict.
FIDELITY = {
    "direction": r"\b(higher|lower|greater|increased?|reduced?|decreased?|improved?|superior|"
                 r"inferior|better|worse|more frequent|less frequent)\b",
    "causation": r"\b(because|due to|attributable|driven by|results? in|leads? to|caused? by|"
                 r"owing to)\b",
    "inference": r"\b(significant(?:ly)?|non-?inferior(?:ity)?|met the|demonstrat\w+|"
                 r"confirm\w+|establish\w+|support\w+)\b",
    "scope": r"\b(IV|SC|intravenous|subcutaneous|steady-state|Cycle \d+|monotherapy|"
             r"treatment-naive|relapsed)\b",
}


# Abbreviation pairs that mean the same thing. Folding them is formatting tolerance for a
# known synonym, not fuzzy matching: without it every clause saying "SC" is flagged against
# every quote saying "subcutaneous", and a list that is 90% noise gets ignored.
SYNONYMS = [("iv", "intravenous"), ("sc", "subcutaneous"), ("po", "oral"),
            ("qd", "once daily"), ("bid", "twice daily")]


def _fold(s: str) -> str:
    s = _flat(s)
    for short, long in SYNONYMS:
        s = re.sub(r"\b%s\b" % re.escape(long), short, s)
    return s


def fidelity_flags(as_printed: str, quote: str):
    """Terms present in the deliverable's clause and absent from its quote."""
    out = []
    q = _fold(quote)
    for kind, pat in FIDELITY.items():
        for m in set(x if isinstance(x, str) else x[0]
                     for x in re.findall(pat, as_printed or "", re.I)):
            if m and _fold(m) and _fold(m) not in q:
                out.append((kind, m))
    return sorted(set(out))


# ------------------------------------------------------------------ append-only history
def read_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def assert_append_only(path, prior_lines):
    """Raise if history was rewritten rather than appended to.

    The guarantee is a prefix check, not a set check: every line that was there before must
    still be there, in the same order, byte for byte. A set check would let a record be
    quietly edited in place, which is the thing a custody trail exists to make impossible.
    """
    now = Path(path).read_text(encoding="utf-8").splitlines() if Path(path).exists() else []
    if now[:len(prior_lines)] != prior_lines:
        for i, (a, b) in enumerate(zip(prior_lines, now)):
            if a != b:
                raise AssertionError(
                    "provenance history was rewritten at line %d.\n  was: %s\n  now: %s"
                    % (i + 1, a[:120], b[:120]))
        raise AssertionError("provenance history lost %d line(s) from the end"
                             % (len(prior_lines) - len(now)))


def collapse_latest(records):
    """Last record wins per id, preserving first-seen order."""
    order, latest = [], {}
    for r in records:
        if r["id"] not in latest:
            order.append(r["id"])
        latest[r["id"]] = r
    return [latest[i] for i in order]


def content_key(r):
    """What makes a record different enough to supersede its predecessor."""
    return json.dumps({k: r.get(k) for k in
                       ("value", "source_value", "as_printed", "doc", "doc_path",
                        "ref", "locator", "url", "quote")},
                      sort_keys=True, ensure_ascii=False)
