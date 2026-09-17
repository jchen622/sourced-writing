#!/usr/bin/env python3
"""Detect values ROUNDED out of their cited source rather than quoted exactly.

Written after a review was found to print 43%, 21% and 12% where its source said 42.6%,
20.8% and 11.7%. Rounding is not a cosmetic choice: it is what made those three values
unverifiable, because the QC search looked for the printed figure and the source never
contained it. (Figures here are synthetic; the shapes are not.)

The test that actually works, and the two ways of getting it wrong:

  WRONG 1  "is the printed value absent from the source?"  The source contains "43" in other
           contexts (sample sizes, page numbers), so the defect reads as clean. This is the
           presence-versus-structure trap, which has cost these reviews four separate times.

  WRONG 2  "does any more precise source figure round to the printed one?"  Floods with false
           positives, and worse, it condemns values that are exact quotes. A product label
           really may print "0.2 L/day (29%)", and a paper's Results really may print
           "7.1 (95% CI, 5.9-8.7)" even though its Key Points box says 7.06.

  RIGHT    Locate the printed value IN CONTEXT. Score every occurrence in the cited sources by
           content-word overlap with the claim, plus co-occurrence of the claim's other
           figures. If a well-matched occurrence exists, the value is an exact quote and there
           is nothing to fix, whatever other precision the source carries elsewhere. Only when
           no occurrence matches in context, AND a more precise figure does, is it a defect.

Configure per project with a `sourcing.json` beside the manuscript; see load_config().

    python3 check_rounding.py                    # triage report, config in cwd
    python3 check_rounding.py --config path.json # explicit config
    python3 check_rounding.py --unmatched        # also list values with no contextual match
    python3 check_rounding.py --check            # exit non-zero if any open DEFECT
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Contexts where the source itself states an approximation. Quoting an approximation exactly
# is still exact, so these are legitimately imprecise and are counted separately.
ALLOW_APPROX = re.compile(r'approximately|about|around|roughly|more than|greater than|at least|'
                          r'up to|over |nearly|prespecified|threshold|criterion|target')

STOP = set(
    'the a an of in to and or for with was were is are be been that this those these by from at '
    'on as not no it its their there which than then also had has have we our study patients '
    'patient median value values levels higher lower more less between during across both other '
    'same each any all section table figure months days weeks year years dose doses'.split())

NUM = re.compile(r'(?<![\w.])(\d{1,4}(?:,\d{3})*(?:\.\d+)?)\s*(%|mg/kg|mg|L/day|µg/mL|mL|L|'
                 r'days|day|months|month|weeks|week|years|patients)?')

MIN_CONTEXT = 3   # score required to call an occurrence "the right one"

# Citation forms seen across these manuscripts: "(16)" and "(2,5)" in one house style,
# "<sup>2,5</sup>" in another. Both must be recognized, because a manuscript whose
# citations are not parsed yields zero cited values and the tool reports a clean sweep of
# nothing. Override with `citation_patterns` in sourcing.json for a house style not listed.
CITATIONS = [
    r'\((\d{1,2}(?:\s*,\s*\d{1,2})*)\)',
    r'<sup>\s*(\d{1,2}(?:\s*,\s*\d{1,2})*)\s*</sup>',
    r'\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]',
]

DEFAULTS = {
    'manuscript': 'manuscript_full.md',
    'adjudications': 'rounding_adjudications.json',
    'cache': 'abstract_cache.json',
    'local_sources': {},
    'references_heading': '## References',
    'citation_patterns': CITATIONS,
}


def cited_refs(text: str, patterns) -> list:
    return [x.strip() for p in patterns for g in re.findall(p, text) for x in g.split(',')]


def strip_citations(text: str, patterns) -> str:
    """Remove citation markers so their reference numbers are not read as claim values."""
    for p in patterns:
        text = re.sub(p, ' ', text)
    return text


def load_config(path: Path) -> tuple[dict, Path]:
    """Read sourcing.json, filling anything absent from DEFAULTS.

    Paths inside the config resolve relative to the config file, so a project can point at
    ../sources/*.txt without caring where the script was invoked from.
    """
    cfg = dict(DEFAULTS)
    if path.exists():
        cfg.update(json.loads(path.read_text()))
    elif '--config' in sys.argv:
        sys.exit(f'config not found: {path}')
    return cfg, path.resolve().parent


def norm(s: str) -> str:
    s = unicodedata.normalize('NFKC', s)
    s = re.sub(r'(?<=\d)·(?=\d)', '.', s)      # Lancet sets the decimal point as a middle dot
    return re.sub(r'\s+', ' ', s)


def words(s: str) -> set:
    return {w for w in re.findall(r'[a-z]{4,}', s.lower()) if w not in STOP}


def dec(s: str):
    try:
        return Decimal(s.replace(',', ''))
    except InvalidOperation:
        return None


def load_pool(cfg: dict, base: Path) -> dict:
    """reference number -> searchable source text."""
    pool = {}
    cache_path = base / cfg['cache']
    if cache_path.exists():
        for ref, v in json.loads(cache_path.read_text()).items():
            pool[ref] = norm((v.get('abstract') or '') + ' ' + (v.get('fulltext') or ''))
    for ref, files in cfg['local_sources'].items():
        texts = [(base / f).read_text(errors='replace') for f in files if (base / f).exists()]
        missing = [f for f in files if not (base / f).exists()]
        if missing:
            print(f'  warning: ref {ref} missing local source(s): {", ".join(missing)}',
                  file=sys.stderr)
        if texts:
            pool[ref] = norm(' '.join(texts))
    if not pool:
        sys.exit('no sources loaded: check `cache` and `local_sources` in sourcing.json')
    return pool


def statements(md: str, refs_heading: str, patterns):
    """Yield (sentence, [cited refs]) over body, abstract, boxed elements, tables, legends.

    Works on PARAGRAPHS, not lines. A hard-wrapped manuscript splits one sentence across
    several lines, and splitting on lines then hands the matcher a fragment with too few
    content words to score, so real defects report as "no contextual match" instead of as
    defects. That silent degradation is exactly the failure mode this tool exists to catch,
    so it must not depend on how the author happens to wrap text.
    """
    parts = md.split(refs_heading)
    body = parts[0] + (parts[-1].split('\n##', 1)[-1] if len(parts) > 1 else '')

    for block in re.split(r'\n\s*\n', body):
        lines = [ln.strip() for ln in block.split('\n') if ln.strip()]
        lines = [ln for ln in lines if not ln.startswith(('#', '!', '---', '```'))]
        if not lines:
            continue
        # Table rows are separate statements; prose lines join back into one paragraph.
        units = []
        prose = []
        for ln in lines:
            if ln.startswith('|'):
                if prose:
                    units.append(' '.join(prose))
                    prose = []
                cells = [c.strip() for c in ln.strip('|').split('|') if c.strip()]
                if not all(set(c) <= set('-: ') for c in cells):   # skip |---|---| rules
                    units.append(' · '.join(cells))
            else:
                prose.append(ln)
        if prose:
            units.append(' '.join(prose))

        for unit in units:
            for sent in re.split(r'(?<=[.;])\s+(?=[A-Z(])', unit):
                refs = cited_refs(sent, patterns)
                if refs:
                    yield sent, refs


def best_occurrence(value: str, unit, sources, want, exact: bool, siblings=()):
    """Highest-scoring occurrence of `value` (exact) or of a more precise rounding parent.

    Score is content-word overlap PLUS the count of the claim's other figures appearing in the
    window. The second term carries dense results strings such as
    "SC: 2907 ug d/ml (CV: 32%) versus IV: 3328 ug d/ml (CV: 20%); GMR, 0.87 (90% CI 0.83-0.92)",
    which have almost no prose to overlap on but where several co-occurring figures make
    coincidence implausible. Note it makes a match HARDER to earn by accident, not easier;
    that direction is the whole point.
    """
    hits = all_occurrences(value, unit, sources, want, exact, siblings)
    return hits[0] if hits else None


def all_occurrences(value: str, unit, sources, want, exact: bool, siblings=()):
    """Every scored occurrence, highest first. `best_occurrence` is the first of these.

    Exposed separately because the top score can be a tie between different figures, and a
    caller that needs to know the source's exact value must not be handed an arbitrary one of
    them. Reporting "rounded, ambiguous" is honest; naming the wrong parent is not.
    """
    pv = dec(value)
    if pv is None:
        return []
    dp = -pv.as_tuple().exponent
    out = []
    for ref, text in sources:
        for m in NUM.finditer(text):
            sv = dec(m.group(1))
            if sv is None:
                continue
            if exact:
                if m.group(1) != value:
                    continue
            else:
                if -sv.as_tuple().exponent <= dp:
                    continue
                try:
                    if sv.quantize(Decimal(1).scaleb(-dp)) != pv:
                        continue
                except InvalidOperation:
                    continue
            if unit and m.group(2) and unit != m.group(2):
                continue
            win = text[max(0, m.start() - 200):m.start() + 200]
            wnums = {x for x, _ in NUM.findall(win)}
            score = len(want & words(win)) + sum(1 for s in siblings if s in wnums)
            out.append((score, m.group(1), ref, win))
    out.sort(key=lambda x: -x[0])
    return out


def load_adjudications(base: Path, cfg: dict) -> set:
    """Dismissals, each of which must carry the source quote that justifies it.

    A dismissal without a quote is refused rather than ignored. Without that, the file becomes
    a silent allowlist and the check decays into the permissive matcher it replaced.
    """
    path = base / cfg['adjudications']
    if not path.exists():
        return set()
    entries = json.loads(path.read_text()).get('dismissed', [])
    bad = [d for d in entries if not str(d.get('quote', '')).strip()]
    if bad:
        sys.exit(f'{path}: {len(bad)} dismissal(s) carry no `quote`: '
                 f'{", ".join(str(d.get("value")) for d in bad)}. '
                 'Record the verbatim source text that justifies the dismissal, or remove it.')
    return {(d['value'], d.get('unit'), str(d['ref'])) for d in entries}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default='sourcing.json')
    ap.add_argument('--check', action='store_true', help='exit non-zero on any open defect')
    ap.add_argument('--unmatched', action='store_true', help='list values with no context match')
    args = ap.parse_args()

    cfg, base = load_config(Path(args.config))
    pool = load_pool(cfg, base)
    md = (base / cfg['manuscript']).read_text()

    defects, approx, quoted, unmatched = [], [], 0, []

    patterns = cfg['citation_patterns']
    for sent, refs in statements(md, cfg['references_heading'], patterns):
        srcs = [(r, pool[r]) for r in refs if r in pool]
        if not srcs:
            continue
        want = words(sent)
        # Citation markers are reference numbers, not claim values.
        bare = strip_citations(sent, patterns)
        allnums = [x for x, _ in NUM.findall(bare)]
        for m in NUM.finditer(bare):
            printed, unit = m.group(1), m.group(2)
            if dec(printed) is None:
                continue
            if '.' not in printed and dec(printed) < 10 and not unit:
                continue          # bare small integers match document section numbers as noise
            siblings = [x for x in allnums if x != printed]

            hit = best_occurrence(printed, unit, srcs, want, exact=True, siblings=siblings)
            if hit and hit[0] >= MIN_CONTEXT:
                quoted += 1
                continue          # exact quote in the right context. Nothing to fix.

            parent = best_occurrence(printed, unit, srcs, want, exact=False, siblings=siblings)
            if parent and parent[0] >= MIN_CONTEXT:
                ctx = sent[max(0, m.start() - 60):m.start() + 40]
                (approx if ALLOW_APPROX.search(ctx) else defects).append(
                    (printed, unit, parent, sent))
            else:
                unmatched.append((printed, unit, refs, sent))

    known = load_adjudications(base, cfg)
    open_defects, dismissed = [], []
    for printed, unit, parent, sent in defects:
        (dismissed if (printed, unit, parent[2]) in known else open_defects).append(
            (printed, unit, parent, sent))

    print(f'exact quotes confirmed in context : {quoted}')
    print(f'OPEN ROUNDING DEFECTS             : {len(open_defects)}')
    print(f'adjudicated, quote on file        : {len(dismissed)}')
    print(f'source-stated approximations, ok  : {len(approx)}')
    print(f'no contextual match either way    : {len(unmatched)}')

    for printed, unit, (ov, sv, ref, win), sent in open_defects:
        print(f'\nDEFECT  printed {printed}{unit or ""}  <-  source {sv}  [ref {ref}, score {ov}]')
        print(f'  claim : {sent[:150]}')
        print(f'  source: ...{win[120:300].strip()}...')

    if args.unmatched:
        print('\n--- no contextual match, needs sourcing by hand ---')
        for printed, unit, refs, sent in unmatched:
            print(f'  {printed}{unit or "":<8} refs {refs}  {sent[:110]}')

    return 1 if (args.check and open_defects) else 0


if __name__ == '__main__':
    sys.exit(main())
