#!/usr/bin/env python3
"""Verify recorded provenance. Does NOT search for sources.

    python3 verify_provenance.py provenance.jsonl [--root DIR] [--quiet]

Three checks per record:

  QUOTE   the quote still appears in doc_path, after documented normalization only
  VALUE   source_value appears inside the quote
  ROUND   value is a correct rounding of source_value

Exits non-zero if any check fails. Records without doc_path are reported as UNVERIFIED
rather than passed, because an unopenable source is not a checked source.

The one rule this file enforces by omission: there is no similarity score, no edit
distance, and no best-available fallback. A quote either is in the document or it is not.
Every tolerance added to the matcher this replaced was individually reasonable, and their
sum was a system that confirmed a CRP ratio against a sample size.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
import custody  # noqa: E402
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from provenance import load  # noqa: E402

DASHES = dict.fromkeys(map(ord, '‐‑‒–—―−'), '-')
QUOTES = {ord('‘'): "'", ord('’'): "'", ord('“'): '"', ord('”'): '"'}


def norm(s: str) -> str:
    """Fold formatting that differs between a source PDF and a manuscript. Nothing else.

    Deliberately NOT the same function as check_rounding.norm(), and they must not be merged.
    This one casefolds and folds dashes and quotes, because it compares a quote against a PDF
    extract. That one must not casefold, because its output feeds words() and the context
    scorer was tuned against its exact normalization. Two readers have now tried to unify them.
    """
    s = unicodedata.normalize('NFKC', s)
    s = re.sub(r'(?<=\d)·(?=\d)', '.', s)   # Lancet sets the decimal point as a middle dot
    s = s.translate(DASHES).translate(QUOTES)
    s = re.sub(r'\s+', ' ', s)                   # PDF extracts wrap mid-sentence
    return s.strip().casefold()


def num(s: str):
    """First number in `s`, or None. See norm() on why this is not check_rounding.dec()."""
    m = re.search(r'-?\d[\d,]*\.?\d*', str(s))
    if not m:
        return None
    try:
        return Decimal(m.group().replace(',', ''))
    except InvalidOperation:
        return None


def appears_as_number(needle: str, haystack: str) -> bool:
    """Is `needle` present in `haystack` as a whole number, not as a digit substring?

    Plain containment is what let source_value "2.6" be confirmed against a quote reading
    "42.6", which is the digit-anywhere failure this file exists to refuse. Both guards are
    needed and neither is redundant:
      (?<![\\d.])   not the tail of a longer number: "2.6" inside "42.6"
      (?!\\d)       not the head of a longer one:    "50" inside "505"
      (?!\\.\\d)     not truncated before a decimal:  "50" inside "50.5"
    The last is written as two lookaheads rather than (?![\\d.]) on purpose, so a number
    ending a sentence ("... was 50.") still matches.
    """
    return re.search(r'(?<![\d.])' + re.escape(needle.strip()) + r'(?!\d)(?!\.\d)',
                     haystack) is not None


def value_in_quote(source_value: str, quote: str) -> bool:
    """VALUE check, branching on type because non-numeric claims are supported and in use.

    A boundary-aware NUMERIC search applied to prose would reject every text record, and text
    records are real: the live faster-filing register carries claims like "no more popPK
    analysis will be done after DBL". So numbers get the strict boundary test and prose keeps
    normalized substring containment, which is the correct test for it.
    """
    sv, q = str(source_value), str(quote)
    n = num(sv)
    if n is None:                            # no number in it at all: prose claim
        return norm(sv) in norm(q)
    nq = norm(q)
    # `is not None`, never truthiness: Decimal('0') is falsy, and a source_value of 0 would
    # otherwise silently fall through to the raw-string path.
    if appears_as_number(norm(str(n)), nq):  # the bare figure
        return True
    return appears_as_number(norm(sv), nq)   # as written, e.g. carrying a unit or a sign


def rounds_to(source, printed) -> bool:
    """True if printed is source rounded to printed's own precision."""
    a, b = num(source), num(printed)
    if a is None or b is None:
        return False
    if a == b:
        return True
    dp = -b.as_tuple().exponent
    try:
        return a.quantize(Decimal(1).scaleb(-dp)) == b
    except InvalidOperation:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', nargs='?', default='provenance.jsonl')
    ap.add_argument('--root', default=None, help='resolve doc_path against this directory')
    ap.add_argument('--quiet', action='store_true', help='print failures only')
    ap.add_argument('--strict', action='store_true',
                    help='also exit non-zero when any record is unverifiable (no doc_path)')
    ap.add_argument('--config', default=None,
                    help='sourcing.json carrying a `references` register. When given, a record '
                         'whose ref is registered must have its doc_path inside that '
                         "reference's authoritative list, so a record cannot verify against a "
                         'document the cited reference is not.')
    args = ap.parse_args()

    root = Path(args.root) if args.root else Path(args.path).resolve().parent

    # ref -> set of authoritative doc_paths, resolved absolute so the comparison does not depend
    # on how the record happens to spell a relative path.
    registry = {}
    if args.config:
        cpath = Path(args.config)
        if not cpath.exists():
            print(f'config not found: {cpath}', file=sys.stderr)
            return 2
        cbase = cpath.resolve().parent
        for ref, spec in (json.loads(cpath.read_text()).get('references') or {}).items():
            registry[str(ref)] = {str((cbase / f).resolve())
                                  for f in (spec.get('authoritative') or [])}
    records = load(args.path)
    if not records:
        print(f'no records in {args.path}', file=sys.stderr)
        return 1

    # Report a malformed record as a record, with its id and the field it is missing. The file
    # is hand-editable, so a bare KeyError traceback from deep inside the loop is the one
    # outcome that tells the reader nothing about which line to go and look at.
    REQUIRED = ('value', 'source_value', 'doc', 'locator', 'quote')
    bad = [(i, r.get('id', f'(line {i})'), [k for k in REQUIRED if k not in r])
           for i, r in enumerate(records, 1)]
    bad = [(i, rid, miss) for i, rid, miss in bad if miss]
    if bad:
        for i, rid, miss in bad:
            print(f'MALFORMED record {i} ({rid}): missing {", ".join(miss)}', file=sys.stderr)
        print(f'\n{len(bad)} record(s) cannot be checked because required fields are absent.',
              file=sys.stderr)
        return 2

    cache, fails, unverified, author, baseline = {}, [], [], [], []

    for r in records:
        rid = r.get('id', '?')
        problems = []

        # An author-entered value is not provenance and is not verified as such. It has
        # no witnessed quote by definition, so running QUOTE/VALUE/ROUND over it would
        # fail every record for the wrong reason. Counted and printed separately, never
        # silently dropped: the point is that the reader sees it was excluded.
        if r.get('origin') == 'author':
            author.append(r)
            continue

        # SKILL.md tells the writer to open a register on an already-drafted deliverable by
        # marking the first entries `"status": "baseline, origin not witnessed"`. Nothing read
        # that field, so those records went through QUOTE/VALUE/ROUND and failed by
        # construction, which made the documented workflow unusable. Same treatment as an
        # author-entered value: excluded from the verified count, printed, never dropped.
        if str(r.get('status', '')).strip().casefold().startswith('baseline'):
            baseline.append(r)
            continue

        # Exactness, not rounding tolerance. Rounding is the defect, not the allowance:
        # 106.6% written as 107% cannot afterwards be found in the source that states it.
        # An interval written two ways is one interval. Endpoint equality, not string
        # equality: both endpoints must match exactly, so this cannot conflate two
        # different ranges.
        if (norm(str(r['value'])) != norm(str(r['source_value']))
                and not custody.same_interval(r['value'], r['source_value'])):
            if rounds_to(r['source_value'], r['value']):
                problems.append(
                    f'ROUND  value {r["value"]!r} is a ROUNDED form of source_value '
                    f'{r["source_value"]!r}; quote the exact figure')
            else:
                problems.append(
                    f'VALUE  value {r["value"]!r} does not match source_value '
                    f'{r["source_value"]!r}')

        ends = custody.endpoints_any(r['source_value'])
        if ends:
            lo, hi = ends
            sv_in_quote = (appears_as_number(norm(lo), norm(r['quote']))
                           and appears_as_number(norm(hi), norm(r['quote'])))
        else:
            sv_in_quote = value_in_quote(r['source_value'], r['quote'])
        if not sv_in_quote:
            problems.append(
                f'VALUE  source_value {r["source_value"]!r} does not appear in the quote')

        dp = r.get('doc_path')
        if not dp:
            unverified.append((rid, r['value'], r['doc']))
        else:
            f = (root / dp) if not Path(dp).is_absolute() else Path(dp)
            if not f.exists():
                problems.append(f'QUOTE  doc_path not found: {f}')
            else:
                if f not in cache:
                    cache[f] = norm(f.read_text(encoding='utf-8', errors='replace'))
                if norm(r['quote']) not in cache[f]:
                    problems.append(f'QUOTE  not found verbatim in {dp}')

            # A verbatim quote in *some* document proves nothing about the reference the
            # deliverable cites. Without this, a record could read `ref: 3` while its doc_path
            # pointed at the agency review of reference 3, and verify cleanly: the same
            # wrong-document hole that `check_rounding`'s reference register closes.
            allowed = registry.get(str(r.get('ref')))
            if allowed and str(f.resolve()) not in allowed:
                problems.append(
                    f'REF    record cites ref {r.get("ref")} but doc_path is not that '
                    f'reference: {dp}')

        if problems:
            fails.append((rid, r, problems))

    total = len(records)
    for rid, r, problems in fails:
        print(f'\nFAIL {rid}  {r["value"]}  ({r["doc"]}, {r["locator"]})')
        for p in problems:
            print(f'     {p}')

    if unverified and not args.quiet:
        print(f'\nUNVERIFIED, no doc_path ({len(unverified)}):')
        for rid, value, doc in unverified:
            print(f'     {rid}  {value}  {doc}')

    if baseline and not args.quiet:
        print(f'\nBASELINE, origin not witnessed ({len(baseline)}):')
        for r in baseline:
            print(f'     {r.get("id", "?")}  {r["value"]}  {r["doc"]}')

    # `unverified` must be subtracted, not merely listed. It used to count toward `ok`, so a
    # file whose records all lacked doc_path printed "5/5 verified" and exited 0 while nothing
    # had been opened at all: the module docstring promises the opposite, and a checkmark over
    # an unperformed check is the exact failure this tool was written to stop.
    checked = total - len(author) - len(baseline)
    ok = checked - len(fails) - len(unverified)
    print(f'\n{ok}/{checked} verified, {len(fails)} failed, '
          f'{len(unverified)} unverifiable without a local extract')
    if author:
        print(f'{len(author)} author-entered (not provenance, not verified); '
              f'reasons recorded in the records themselves')
    if baseline:
        print(f'{len(baseline)} baseline (origin not witnessed, excluded by status)')
    if unverified and not args.strict:
        print('(unverifiable records are not failures; re-run with --strict to treat them as such)')
    return 1 if (fails or (unverified and args.strict)) else 0


if __name__ == '__main__':
    sys.exit(main())
