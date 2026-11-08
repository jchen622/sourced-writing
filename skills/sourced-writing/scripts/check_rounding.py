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

# Both boundaries are load-bearing, and the right one was missing until a review caught it.
# `\d{1,4}` with no right-hand guard captures "1234" out of "12345", and the exact-match branch
# of all_occurrences() then confirms a value that the source never prints: the digit-anywhere
# failure this whole module exists to stop, reintroduced inside the matcher itself. So:
#   (?<![\w.])  not mid-word, and not the tail of a longer decimal ("6" of "42.6")
#   (?!\d)      not the head of a longer number ("1234" of "12345")
# The digit run is also widened from {1,4} to + because truncating a 5-digit number to its
# first 4 was the mechanism of the bug, not merely its symptom.
#
# The right guard blocks a following DIGIT only, never a following comma. `(?![\d,])` looks
# tighter and is wrong: a comma after a decimal is ordinary punctuation, so in the interval
# "0.940 (0.908, 0.974)" it refuses "0.908" and captures a bare "0" instead. That silently cost
# 12 confirmed quotes and invented a defect on a real manuscript corpus before the before/after
# diff caught it. Thousands groups are already handled by (?:,\d{3})*.
#
# Currency: the symbol rides in group 1 (dec() strips it) and the magnitude suffix joins the
# unit alternation, so "$1.2M" no longer reads as a bare 1.2 that matches unrelated 1.2s six
# orders of magnitude away. The group COUNT is deliberately still two: NUM.findall() is
# unpacked as `for x, _ in ...` in two places, so a third group would break both silently.
# The \b binds only the alphabetic alternatives; putting it after `%` would require a word
# character to follow the percent sign and break every "42.6% higher" in the corpus.
NUM = re.compile(r'(?<![\w.])([$€£]?\d+(?:,\d{3})*(?:\.\d+)?)(?!\d)\s*'
                 r'(%|mg/kg|mg|L/day|µg/mL|mL|L|'
                 r'(?:days|day|months|month|weeks|week|years|patients|'
                 r'M|B|K|bn|mn|million|billion)\b)?')

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
    """Normalize SOURCE POOL text for scoring. Deliberately not the same as
    verify_provenance.norm(), which additionally folds dashes and quotes and casefolds for
    quote matching. This one must not casefold: words() feeds the context scorer and the
    scorer was tuned against this exact normalization. Keep them separate on purpose.
    """
    s = unicodedata.normalize('NFKC', s)
    s = re.sub(r'(?<=\d)·(?=\d)', '.', s)      # Lancet sets the decimal point as a middle dot
    return re.sub(r'\s+', ' ', s)


# A token immediately after a number, whatever it is. NUM's own unit group recognizes only a
# short whitelist, so the mismatch guard below needs to see units outside it: without that,
# a source's "50 ng" satisfies a manuscript's "50 mg".
TRAILING = re.compile(r'\s*([A-Za-zµ%][A-Za-z0-9µ·/%]*)')

# The vocabulary the mismatch guard is allowed to reason about. A trailing token outside it is
# treated as "no unit stated", NOT as a conflicting unit, and that distinction is the whole
# design: sources habitually write "10.9 and 10.1 months", where the token after 10.9 is the
# word "and". Firing on any trailing word rejected three true exact quotes across the
# two oncology manuscript corpora before the
# before/after diff caught it. Only fire when BOTH sides name a unit this set knows and they
# disagree; otherwise fall through and let the context scorer decide, which is what the
# original code did and is the safe default.
UNITS = {
    '%', 'mg', 'g', 'kg', 'µg', 'ug', 'mcg', 'ng', 'pg',
    'l', 'ml', 'dl', 'µl', 'ul',
    'mg/kg', 'mg/ml', 'µg/ml', 'ug/ml', 'ng/ml', 'g/l', 'l/day', 'ml/min',
    'mmol/l', 'mol/l', 'nm', 'µm', 'mm',
    'day', 'days', 'week', 'weeks', 'month', 'months', 'year', 'years',
    'h', 'hr', 'hrs', 'hour', 'hours', 'min', 'mins', 'minute', 'minutes',
    'patients', 'm', 'b', 'k', 'bn', 'mn', 'million', 'billion',
}


def trailing_token(text: str, end: int):
    """The raw token following a numeric match, or None. Whitelist-independent."""
    m = TRAILING.match(text, end)
    return m.group(1) if m else None


def unit_key(tok):
    """Normalized unit if `tok` is one this guard recognizes, else None (meaning 'unknown')."""
    t = (tok or '').strip().casefold()
    return t if t in UNITS else None


def words(s: str) -> set:
    return {w for w in re.findall(r'[a-z]{4,}', s.lower()) if w not in STOP}


def dec(s: str):
    # NUM group 1 may carry a leading currency symbol; strip it here so every caller that
    # turns a captured token into a number keeps working unchanged.
    try:
        return Decimal(s.replace(',', '').lstrip('$€£'))
    except InvalidOperation:
        return None


def _read_all(files, base: Path, ref: str, kind: str) -> list:
    texts, missing = [], []
    for f in files:
        p = base / f
        texts.append(p.read_text(errors='replace')) if p.exists() else missing.append(f)
    if missing:
        print(f'  warning: ref {ref} missing {kind} source(s): {", ".join(missing)}',
              file=sys.stderr)
    return texts


def load_pool(cfg: dict, base: Path) -> tuple[dict, dict]:
    """(authoritative, supporting), each reference number -> searchable source text.

    **A reference number names one document, not a folder of related ones.** Before the
    `references` register existed this function concatenated every file mapped to a reference
    into a single pool, so a value present only in an agency *review* of a label was reported
    as confirmed against a reference that is the label itself. Two real claims passed that way:
    a pre-specified non-inferiority threshold and a secondary endpoint, neither of which appears
    anywhere in the cited Prescribing Information.

    Only `authoritative` text can confirm. `supporting` text is still loaded, because knowing a
    value came from the agency review rather than the label is far more useful than reporting it
    as unsourced.
    """
    auth, support = {}, {}
    cache_path = base / cfg['cache']
    if cache_path.exists():
        for ref, v in json.loads(cache_path.read_text()).items():
            auth[ref] = norm((v.get('abstract') or '') + ' ' + (v.get('fulltext') or ''))

    reg = cfg.get('references') or {}
    for ref, files in cfg['local_sources'].items():
        if ref in reg:
            continue                      # the register governs this reference
        texts = _read_all(files, base, ref, 'local')
        if texts:
            auth[ref] = norm(' '.join(texts))
        # Silent today, visible from now on: more than one file behind one reference number is
        # exactly the condition under which a quote can be confirmed against the wrong document.
        if len(files) > 1:
            print(f'  warning: ref {ref} pools {len(files)} files with no `references` entry, so '
                  f'a quote in any of them will confirm it: {", ".join(files)}', file=sys.stderr)

    for ref, spec in reg.items():
        a = _read_all(spec.get('authoritative') or [], base, ref, 'authoritative')
        s = _read_all(spec.get('supporting') or [], base, ref, 'supporting')
        if a:
            auth[ref] = norm(' '.join(a))
        else:
            print(f'  warning: ref {ref} is registered but no authoritative source was readable; '
                  f'nothing can be confirmed against it', file=sys.stderr)
        if s:
            support[ref] = norm(' '.join(s))

    if not auth and not support:
        sys.exit('no sources loaded: check `cache`, `local_sources` and `references` in '
                 'sourcing.json')
    return auth, support


def statements(md: str, refs_heading: str, patterns, *, include_uncited: bool = False):
    """Yield (sentence, [cited refs]) over body, abstract, boxed elements, tables, legends.

    Works on PARAGRAPHS, not lines. A hard-wrapped manuscript splits one sentence across
    several lines, and splitting on lines then hands the matcher a fragment with too few
    content words to score, so real defects report as "no contextual match" instead of as
    defects. That silent degradation is exactly the failure mode this tool exists to catch,
    so it must not depend on how the author happens to wrap text.

    `include_uncited` yields sentences carrying no citation at all, with an empty ref list.
    Rounding checks do not want those: with no cited source there is nothing to compare against.
    Coverage checks want exactly those, because a value with no citation is the gap they exist to
    find, and an extractor that silently skipped them would make `check_coverage` report a clean
    sheet over the very defects it was written for. One extractor, one set of rules, one flag.
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
                if refs or include_uncited:
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
            # Unit mismatch, fired only when both sides name a unit UNITS knows and they
            # disagree. m.group(2) alone no-ops for every unit outside its short whitelist,
            # which let a source's "50 ng" satisfy a manuscript's "50 mg"; an unrecognized
            # trailing token means "no unit stated" and falls through to the context scorer.
            claim_unit = unit_key(unit)
            if claim_unit:
                src_unit = unit_key(m.group(2) or trailing_token(text, m.end()))
                if src_unit and claim_unit != src_unit:
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
    auth, support = load_pool(cfg, base)
    md = (base / cfg['manuscript']).read_text()

    defects, approx, quoted, unmatched, misattributed = [], [], 0, [], []

    patterns = cfg['citation_patterns']
    for sent, refs in statements(md, cfg['references_heading'], patterns):
        srcs = [(r, auth[r]) for r in refs if r in auth]
        sup = [(r, support[r]) for r in refs if r in support]
        if not srcs and not sup:
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
                # Absent from every cited reference. If it sits in a *supporting* document of one
                # of them, the citation points at the wrong document: a defect, not a gap. Saying
                # "unsourced" here would be wrong and would get dismissed as noise.
                mis = (best_occurrence(printed, unit, sup, want, exact=True, siblings=siblings)
                       if sup else None)
                if mis and mis[0] >= MIN_CONTEXT:
                    misattributed.append((printed, unit, mis, sent))
                else:
                    unmatched.append((printed, unit, refs, sent))

    known = load_adjudications(base, cfg)
    open_defects, dismissed = [], []
    for printed, unit, parent, sent in defects:
        (dismissed if (printed, unit, parent[2]) in known else open_defects).append(
            (printed, unit, parent, sent))

    print(f'exact quotes confirmed in context : {quoted}')
    print(f'OPEN ROUNDING DEFECTS             : {len(open_defects)}')
    print(f'WRONG DOCUMENT FOR THE CITATION   : {len(misattributed)}')
    print(f'adjudicated, quote on file        : {len(dismissed)}')
    print(f'source-stated approximations, ok  : {len(approx)}')
    print(f'no contextual match either way    : {len(unmatched)}')

    for printed, unit, (ov, sv, ref, win), sent in open_defects:
        print(f'\nDEFECT  printed {printed}{unit or ""}  <-  source {sv}  [ref {ref}, score {ov}]')
        print(f'  claim : {sent[:150]}')
        print(f'  source: ...{win[120:300].strip()}...')

    for printed, unit, (ov, sv, ref, win), sent in misattributed:
        print(f'\nWRONG DOCUMENT  {printed}{unit or ""}  is not in reference {ref}; it is in a '
              f'supporting document of it  [score {ov}]')
        print(f'  claim : {sent[:150]}')
        print(f'  found : ...{win[120:300].strip()}...')
        print(f'  fix   : cite the document that contains it, or drop the claim.')

    if args.unmatched:
        print('\n--- no contextual match, needs sourcing by hand ---')
        for printed, unit, refs, sent in unmatched:
            print(f'  {printed}{unit or "":<8} refs {refs}  {sent[:110]}')

    return 1 if (args.check and (open_defects or misattributed)) else 0


if __name__ == '__main__':
    sys.exit(main())
