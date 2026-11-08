#!/usr/bin/env python3
"""Is every value in the deliverable accounted for? Exits non-zero if any is not.

    python3 check_coverage.py --config sourcing.json
    python3 check_coverage.py --config sourcing.json --list        # print every residual

SKILL.md has always said coverage is closed, not best-effort: every value resolves either to a
provenance record or to an explicit `not_a_claim.json` entry, and a value in neither is a hard
failure. **Nothing enforced it.** `not_a_claim.json` appeared nowhere outside that paragraph, so
the rule was advice. On one review that left an uncited "22%" and an uncited "approximately 4500
patients across 12 trials" in a manuscript that had passed every gate, alongside roughly 136
other unresolved values. A reviewer found them by reading.

Two deliberate choices.

**Extraction is imported from `check_rounding`, never re-implemented.** Same `NUM`, same
citation stripping, same bare-small-integer exclusion. A second counter that disagrees with the
project's own is worse than no counter, because then neither number can be trusted.

**Matching is on the numeric token, not the whole printed string.** A record may hold
`0.34-0.62` where the deliverable prints `0.34 to 0.62`, and house style legitimately reformats
thousands separators and dates. The question this script answers is "is this figure recorded
anywhere", not "is this exact string recorded", so it tokenizes both sides. String-level
matching would bury the real gaps under formatting noise and the output would be ignored.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_rounding import NUM, dec, load_config, statements, strip_citations  # noqa: E402
from custody import collapse_latest, read_jsonl  # noqa: E402

TOKEN = re.compile(r'\d+(?:[.,]\d+)*')


def tokens(s: str) -> set:
    return {t.replace(',', '') for t in TOKEN.findall(str(s or ''))}


def deliverable_values(md: str, cfg: dict):
    """(printed, unit, sentence) for every value in scope, by check_rounding's own rules."""
    patterns = cfg['citation_patterns']
    out = []
    # include_uncited is the whole point: a value with no citation is the gap being looked for.
    for sent, _refs in statements(md, cfg['references_heading'], patterns, include_uncited=True):
        bare = strip_citations(sent, patterns)
        for m in NUM.finditer(bare):
            printed, unit = m.group(1), m.group(2)
            if dec(printed) is None:
                continue
            if '.' not in printed and dec(printed) < 10 and not unit:
                continue          # bare small integers are section and cycle numbers, not claims
            out.append((printed, unit, sent))
    return out


def load_not_a_claim(path: Path) -> tuple[set, list]:
    """Returns (exempt tokens, refusals).

    An entry must say why. An allowlist whose entries carry no reason stops being a record of
    judgement and becomes a way to make the gate quiet, which is the failure mode that
    `rounding_adjudications.json` already guards against by demanding a source quote.
    """
    if not path.exists():
        return set(), []
    raw = json.loads(path.read_text())
    entries = raw if isinstance(raw, list) else raw.get('entries', [])
    exempt, refused = set(), []
    for e in entries:
        why = str(e.get('why', '')).strip()
        if not why:
            refused.append(e.get('value', '(no value)'))
            continue
        exempt |= tokens(e.get('value', ''))
    return exempt, refused


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default='sourcing.json')
    ap.add_argument('--provenance', default=None, help='default: provenance.jsonl beside config')
    ap.add_argument('--not-a-claim', default=None, help='default: not_a_claim.json beside config')
    ap.add_argument('--list', action='store_true', help='print every residual, not just a sample')
    a = ap.parse_args()

    cfg, base = load_config(Path(a.config))
    md_path = base / cfg['manuscript']
    if not md_path.exists():
        print(f'manuscript not found: {md_path}', file=sys.stderr)
        return 2
    values = deliverable_values(md_path.read_text(), cfg)

    prov = Path(a.provenance) if a.provenance else base / 'provenance.jsonl'
    records = collapse_latest(read_jsonl(prov))
    recorded = set()
    for r in records:
        recorded |= tokens(r.get('value'))
        recorded |= tokens(r.get('source_value'))

    nac_path = Path(a.not_a_claim) if a.not_a_claim else base / 'not_a_claim.json'
    exempt, refused = load_not_a_claim(nac_path)

    residual = [(p, u, s) for p, u, s in values
                if not (tokens(p) & recorded) and not (tokens(p) & exempt)]

    distinct = {p for p, _, _ in values}
    print(f'values in the deliverable        : {len(values)} ({len(distinct)} distinct)')
    print(f'records read                     : {len(records)} from {prov.name}')
    print(f'not_a_claim exemptions           : {len(exempt)} token(s) from '
          f'{nac_path.name if nac_path.exists() else "no not_a_claim.json"}')
    print(f'UNRESOLVED (no record, no exempt): {len(residual)}')

    if refused:
        print(f'\nREFUSED {len(refused)} not_a_claim entr(ies) with an empty "why": '
              f'{", ".join(map(str, refused[:8]))}')
        print('  An exemption without a reason is not a judgement on file. Say why, or record it.')

    if residual:
        shown = residual if a.list else residual[:25]
        print(f'\n--- unresolved values, each needs a record or a not_a_claim entry ---')
        for p, u, s in shown:
            where = s.strip()[:110]
            print(f'  {p}{u or "":<10} {where}')
        if len(residual) > len(shown):
            print(f'  … and {len(residual)-len(shown)} more; re-run with --list')

    # Coverage is closed or it is not. A silent residual is indistinguishable from an oversight,
    # which is why this exits non-zero rather than printing a score.
    return 1 if (residual or refused) else 0


if __name__ == '__main__':
    sys.exit(main())
