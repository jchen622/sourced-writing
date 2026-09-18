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
    """Fold formatting that differs between a source PDF and a manuscript. Nothing else."""
    s = unicodedata.normalize('NFKC', s)
    s = re.sub(r'(?<=\d)·(?=\d)', '.', s)   # Lancet sets the decimal point as a middle dot
    s = s.translate(DASHES).translate(QUOTES)
    s = re.sub(r'\s+', ' ', s)                   # PDF extracts wrap mid-sentence
    return s.strip().casefold()


def num(s: str):
    m = re.search(r'-?\d[\d,]*\.?\d*', str(s))
    if not m:
        return None
    try:
        return Decimal(m.group().replace(',', ''))
    except InvalidOperation:
        return None


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
    args = ap.parse_args()

    root = Path(args.root) if args.root else Path(args.path).resolve().parent
    records = load(args.path)
    if not records:
        print(f'no records in {args.path}', file=sys.stderr)
        return 1

    cache, fails, unverified, author = {}, [], [], []

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

        sv_in_quote = norm(str(num(r['source_value']) or r['source_value'])) in norm(r['quote'])
        if custody.endpoints_any(r['source_value']):
            lo, hi = custody.endpoints_any(r['source_value'])
            sv_in_quote = lo in norm(r['quote']) and hi in norm(r['quote'])
        if not sv_in_quote:
            if norm(r['source_value']) not in norm(r['quote']):
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

    ok = total - len(fails) - len(author)
    print(f'\n{ok}/{total - len(author)} verified, {len(fails)} failed, '
          f'{len(unverified)} unverifiable without a local extract')
    if author:
        print(f'{len(author)} author-entered (not provenance, not verified); '
              f'reasons recorded in the records themselves')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
