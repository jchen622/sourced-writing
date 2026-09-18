---
name: sourced-writing
description: Record provenance at write time for any deliverable where numbers, dates, or factual claims are taken from sources - manuscripts, reviews, regulatory documents, slide decks, memos, briefing books, literature summaries. Use whenever pulling a value out of a paper, label, review document, database, or web page and putting it into a deliverable, and whenever QC-ing, fact-checking, or building a number-by-number verification worksheet for one. Also use when asked to check every number, verify sources, trace a claim, confirm a value is real, build a QC document or source-traceability record, audit citations, or show where a figure came from. Covers rounding defects, quotes matched on digits alone, claims that assert more than their quote supports, and values an author entered that were never sourced. Default to invoking this rather than not.
---

# Record provenance at write time

**The rule, in one line: the moment a number leaves a source and enters a deliverable, the
link between them is written down. It is never reconstructed afterwards.**

Everything else here follows from that. Retrieval after the fact is the failure mode this
skill exists to prevent, and it is a failure mode that produces *confident wrong answers*, not
visible gaps, which is why it survives review.

## What went wrong the one time this was not done

On a scientific review, numbers were pulled from sources during drafting and the link
discarded. A fuzzy matcher was built afterwards to find the sources again. Driven to
"386 of 386 sourced", it was in fact matching digits anywhere in a megabyte of text:

| Printed | Matched to | Actually |
|---|---|---|
| `43%` marker higher in biomarker-positive patients | `N = 43` | a sample size in a different trial |
| `21%` change in sum of lesion diameters | `White (64%) and Asian (21%)` | a race distribution |
| `12%` performance status 1 more frequent | `minimum 12%, maximum 38%` | a clearance range |

Every one carried a checkmark reading "confirmed". 87 of 386 rows shared **zero** content words
with their claimed source. A reviewer checked four rows by hand and three were wrong.

The diagnosis: *if you pulled the result and the reference to write the paper, how can the
source not be traceable?* It cannot. The information existed and was thrown away.

*Figures throughout this file are synthetic, chosen to preserve the shape of each failure.*

## The record

Append one JSON object per line to `provenance.jsonl` beside the deliverable, **in the same
action that writes the text**, never in a later cleanup pass.

```json
{"id":"p3f9a1c204","value":"42.6%","as_printed":"42.6% higher in biomarker-positive patients","source_value":"42.6%","doc":"Falk 2021, J Appl Pharmacol","doc_path":"sources/falk2021_fulltext.txt","ref":16,"locator":"Table 2, median marker row","url":"https://example.org/falk2021","quote":"Median marker (mg/L) 9.8 (0.4, 148) 20.25 (0.8, 184) 42.6","retrieved":"2026-09-17"}
```

| Field | Required | Notes |
|---|---|---|
| `id` | yes | stable content hash, see **Identity** below |
| `value` | yes | exactly as printed in the deliverable |
| `as_printed` | yes | the surrounding clause, so context can be judged |
| `source_value` | yes | what the source prints, **resolved from the source, never copied from `value`** |
| `doc` | yes | human-readable source name |
| `doc_path` | where local | path to a local text extract, which makes the record machine-verifiable |
| `url` | yes | resolvable link a reader can open |
| `locator` | yes | page, table, section. Enough to find it by eye. |
| `quote` | yes | **copied verbatim**, never paraphrased or reconstructed |
| `ref` | where numbered | reference number in the deliverable, so citations cross-check mechanically |
| `retrieved` | yes | ISO date |

Use `scripts/provenance.py` so recording is one call and the schema cannot drift.

## Four rules that make it hold

1. **No number is written without a record.** If no verbatim quote can be pasted, the number
   does not go in. Write `[UNSOURCED: description]` and surface it. An honest gap costs one
   line to fix now; a false confirmation costs a retraction.
2. **`quote` is copied, not written.** The instant a quote is typed from memory rather than
   pasted from the source, the record is decorative.
3. **Quote values exactly. Never round.** `value` must equal `source_value`, including trailing
   zeros: if the source prints `0.20 L/day`, so do you. Rounding is not a style choice, it is
   what breaks traceability. In the case above the deliverable printed 43%, 21% and 12% where
   the source said 42.6%, 20.8% and 11.7%, and those three values then could not be found in
   the source at all, because the source never contained them. *Whenever you quote values from
   a reference, it needs to be exact instead of round.*

   Two things this does not forbid. Quoting an approximation the source itself states
   ("approximately 4500 patients") is exact. And where a source prints the same quantity at two
   precisions, quote the passage you are actually citing: if a Results section gives
   `7.1 (95% CI, 5.9-8.7) months` while the Key Points box gives `7.06`, and you are quoting
   that sentence's confidence intervals, `7.1` is the exact quote.
4. **`provenance.jsonl` is append-only.** Correct a bad record by appending a superseding one
   with the same `id`; the last wins and the history stays legible.

## Identity: ids must survive edits elsewhere

An id keyed to a line or row number changes whenever a sentence is added above it, so "the same
id" never means the same value twice and rule 4 cannot work. Use
`custody.stable_id(section, value, clause)`, a hash of the claim itself. The id then changes
only when the claim changes, which is exactly when a superseding record is wanted.

## The four things verification must cover

`scripts/verify_provenance.py` answers *is this record true?* Three further checks answer what
it cannot. All live in `scripts/custody.py`.

**Rounding.** `source_value` must be resolved from the source. A generator that writes
`"source_value": value` silently disables the ROUND check, because it then compares a value to
itself and can never fire. This is the easiest way to make a passing gate meaningless, and it
is worth grepping for.

**Context.** A figure is confirmed only when an occurrence matches *in context*, scored by
content-word overlap plus co-occurring figures from the same claim. Digit uniqueness is not
enough. When two candidate figures tie on score, report ambiguity rather than naming one: an
arbitrary pick is how the wrong parent gets recorded.

**Fidelity.** The chain value → quote → document never checks claim → meaning. A clause can add
direction ("reduced"), causation ("due to"), inference ("significantly") or scope ("in the
treated arm") that the quote does not support. `fidelity_flags()` lists these for human review.
Deliberately advisory: a pass/fail here would either be trivially satisfied or block constantly.

**History.** `assert_append_only()` requires that every line previously in the file is still
there, in order, byte for byte. A set comparison would let a record be edited in place, which
is the one thing a custody trail exists to prevent.

### Starting the trail on work already written

Provenance cannot be established retroactively; that is the whole premise. For a deliverable
already drafted without records, do not pretend otherwise. Write a **baseline** as the first
entries, every record marked `"status": "baseline, origin not witnessed"`, and treat that line
as the start of custody rather than as evidence. Everything appended after it is tracked
properly, and the honest gap stays visible instead of being papered over.

## Coverage is closed, not best-effort

Every value in the deliverable resolves to exactly one of two states: a provenance record, or
an explicit entry in `not_a_claim.json` giving the value, where it appears, and why it carries
no source (a structural label, a count the document itself derives, a credit year). A value in
neither is a hard failure. There is no third bucket, because a silent residual is
indistinguishable from an oversight.

## QC verifies records; it never searches

```bash
python3 ~/.claude/skills/sourced-writing/scripts/verify_provenance.py provenance_current.jsonl
```

For every record it checks the quote still appears in `doc_path` (after documented
normalization only), that `source_value` appears inside the quote, and that `value` is a
correct rounding of `source_value`. It exits non-zero on any failure.

**Do not infer a source for a value that has no record.** The correct output for an unrecorded
number is "unresolved", and the correct next step is to go back to the source or delete the
claim. It is never to search the corpus for a matching string. That search is precisely what
manufactured the three false confirmations above.

When building a human QC worksheet, generate it *from* the records. One row per record,
carrying the claim, the quote, the locator, and a working link. Rows then need judgment, not
detective work.

## The QC document: offer it, never assume it

**Do not generate this automatically.** When this skill is used for a QC, fact-check, or
verification pass, offer it once:

> "Do you want the sourced-writing QC document generated?"

Ask once per session. If the answer is no, do not ask again. Many projects already keep their
own QC document, and quietly producing a second one is confusing rather than helpful.

```bash
python3 ~/.claude/skills/sourced-writing/scripts/qc_document.py \
        --config sourcing.json --coverage coverage.json \
        --requirements requirements.json --metrics metrics.json
```

It writes `sourced-writing-qc.md`, named so it is never mistaken for a project's own QC file,
and it **refuses to overwrite any file it did not generate**. Pointing `--out` at a
hand-maintained QC document is rejected rather than obeyed.

Ten sections. The source register, claim-to-source table, provenance summary and numeric
worksheet are built from the records, so they cannot go stale. The verification log,
discrepancy log, interpretation log and author information come out as **labelled stubs**,
because they need judgment and a generator that invented them would produce the
confident-looking artifact this skill exists to prevent. The run prints how many stubs remain.

**Section 4 is venue-neutral. Ask for the guide.** A journal, a health authority, a conference
and an internal template all impose different limits, and this skill assumes none of them.
With no `requirements` supplied, the section asks for them by name: which text the word limit
covers and what it excludes, the abstract limit, the reference cap and whether table-only
citations count, the figure and table cap, and any prescribed section order. Ask whoever is
submitting, then pass them in.

Two things the generator will not do, both for the same reason. It will not compute coverage,
and it will not decide whether a measured value satisfies a limit. What counts as "a value"
and what a limit really covers are project and venue specific, and a second counter that
disagrees with the project's own is worse than no counter. Pass `--coverage` and `--metrics`.

`references/qc-document.md` explains what belongs in each section.

## Regression suite

```bash
python3 ~/.claude/skills/sourced-writing/scripts/test_guards.py -v
```

Every case is a defect that once shipped, or a negative control proving a guard has not been
tuned into uselessness. Run it after any change to the guards. A gate that has never failed is
not evidence of anything, so each case is written to fail before its fix and pass after.

## Starting a new deliverable

Drop a `sourcing.json` beside the manuscript and the exactness check works immediately. Nothing
else needs building.

```json
{
  "manuscript": "manuscript_full.md",
  "adjudications": "rounding_adjudications.json",
  "cache": "abstract_cache.json",
  "local_sources": {
    "2": ["../sources/LABEL.txt"],
    "3": ["../sources/agency_review.txt"]
  }
}
```

`cache` is an optional `{"<ref>": {"abstract": ..., "fulltext": ...}}` map; a project with only
local text extracts can omit it. `citation_patterns` defaults to `(1,2)`, `<sup>1,2</sup>` and
`[1,2]` and is overridable for another house style.

```bash
python3 ~/.claude/skills/sourced-writing/scripts/check_rounding.py --config _build/sourcing.json
                                                                   --check      # gate a build
                                                                   --unmatched  # triage list
```

Run it before every build. Record each dismissal in `rounding_adjudications.json` with the
verbatim source quote that justifies it; a dismissal carrying no quote is refused, which is what
keeps the file from decaying into a silent allowlist.

Two things to confirm on a new project before trusting the numbers, because both fail quietly:

- **Citations are being parsed.** If `exact quotes confirmed` is 0 or implausibly low, the
  citation form is not matched and the tool is sweeping nothing.
- **Cited references have searchable text.** A reference absent from both `cache` and
  `local_sources` cannot be checked, and its values land in `no contextual match` rather than
  being reported as unsourced. Treat that bucket as "not yet checked", never as "fine".

## Cross-check before every delivery

- **Re-verify after renumbering.** Reference numbers drift, and a QC table silently keeping the
  old ones points readers at the wrong sources. Compare `ref` in each record against the
  deliverable's actual citations. Anything else keyed by reference number, including cached
  source extracts, goes stale the same way and must be rebuilt.
- **Count coverage.** Extract every number in the deliverable and confirm each has a record.
  Report the uncovered count plainly. Zero is the target; a wrong zero is worse than an honest
  twelve.
- **State the residual.** Say what is unresolved and why, rather than reporting success.

## Normalization the verifier applies, and nothing more

Unicode NFKC; a middle-dot decimal (`0·74`) to a period; dash and quote variants folded;
whitespace collapsed, which is necessary because PDF extracts wrap mid-sentence; case folded.
This is formatting tolerance. It is not fuzzy matching, and no similarity threshold, edit
distance, or "best available" fallback belongs anywhere in verification. Every relaxation added
to that earlier matcher was individually defensible and their sum was a system that could
confirm anything.

One documented exception, because sources genuinely print dates three ways: a date value may
match `22 December 2022`, `December 22, 2022` or `12/22/2022`. Each pins the same day, month and
year, so a hit cannot be a different date. Nothing else gets alternative forms.
