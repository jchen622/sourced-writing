#!/usr/bin/env python3
"""Append-only provenance recording, called at the moment a value is written.

The whole point is that this is cheaper than not doing it. If recording provenance ever
feels like a separate chore, it will be skipped under deadline and the deliverable will
ship with unverifiable numbers. One import, one call.

    from provenance import record
    record(value="42.6%", as_printed="42.6% higher in biomarker-positive patients",
           source_value="42.6", doc="Falk 2021, J Appl Pharmacol",
           doc_path="sources/falk2021_fulltext.txt", ref=16,
           locator="Table 2, median marker row",
           url="https://example.org/falk2021",
           quote="Median marker (mg/L) 9.8 (0.4, 148) 20.25 (0.8, 184) 42.6")

Corrections are made by appending a record with the same id, not by editing the file.
load() collapses to last-wins so the history stays readable while the effective set stays
unambiguous.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

DEFAULT_PATH = Path(os.environ.get('PROVENANCE_PATH', 'provenance.jsonl'))

REQUIRED = ('value', 'as_printed', 'source_value', 'doc', 'url', 'locator', 'quote')


def record(*, value, as_printed, source_value, doc, url, locator, quote,
           doc_path=None, ref=None, retrieved=None, id=None, path=None, **extra):
    """Append one provenance record. Returns the record written.

    Raises ValueError on a missing or empty required field, deliberately: a half-filled
    record is worse than none, because it looks like coverage.
    """
    rec = {
        'value': str(value),
        'as_printed': str(as_printed),
        'source_value': str(source_value),
        'doc': str(doc),
        'url': str(url),
        'locator': str(locator),
        'quote': str(quote),
        'retrieved': retrieved or date.today().isoformat(),
    }
    if doc_path is not None:
        rec['doc_path'] = str(doc_path)
    if ref is not None:
        rec['ref'] = ref
    rec.update(extra)

    missing = [k for k in REQUIRED if not rec.get(k, '').strip()]
    if missing:
        raise ValueError(
            f'provenance record missing {", ".join(missing)} for value {rec["value"]!r}. '
            'If no verbatim quote can be pasted, do not write the number: emit '
            '[UNSOURCED: ...] and surface it instead.')

    # Catch rounding at write time, where it costs one line, rather than at QC, where it
    # presents as a value that simply cannot be found in the source that states it.
    if rec['value'].strip() != rec['source_value'].strip():
        raise ValueError(
            f'value {rec["value"]!r} does not match source_value {rec["source_value"]!r}. '
            'Quote the source exactly, trailing zeros included. If the source really does '
            'print two precisions, quote the passage you are citing and say so in `locator`.')

    target = Path(path) if path else DEFAULT_PATH
    rec['id'] = id or f'p{_next_seq(target):04d}'

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return rec


def load(path=None, *, last_wins=True):
    """Read records. With last_wins, a later record supersedes an earlier one of the same id."""
    target = Path(path) if path else DEFAULT_PATH
    if not target.exists():
        return []
    out = []
    for n, line in enumerate(target.read_text(encoding='utf-8').splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f'{target}:{n}: malformed JSON: {exc}') from None
    if not last_wins:
        return out
    merged = {}
    for r in out:
        merged[r.get('id') or f'_anon{len(merged)}'] = r
    return list(merged.values())


def _next_seq(target):
    if not target.exists():
        return 1
    return sum(1 for ln in target.read_text(encoding='utf-8').splitlines() if ln.strip()) + 1
