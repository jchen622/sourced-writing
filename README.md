# sourced-writing

**The moment a number leaves a source and enters a deliverable, the link between them is
written down. It is never reconstructed afterwards.**

An agent skill for documents where a wrong figure is expensive: manuscripts, regulatory
submissions, briefing books, anything that gets checked by someone who was not there when it
was written.

## Why reconstructing provenance does not work

A review was once driven to "386 of 386 sourced" by a matcher built *after* the text existed.
It was matching digits anywhere in a megabyte:

| Printed | Matched to | Actually |
|---|---|---|
| `43%` marker higher in biomarker-positive patients | `N = 43` | a sample size in a different trial |
| `21%` change in sum of lesion diameters | `White (64%) and Asian (21%)` | a race distribution |
| `12%` performance status 1 more frequent | `minimum 12%, maximum 38%` | a clearance range |

Every one carried a checkmark reading "confirmed". 87 of 386 rows shared zero content words
with their claimed source. Those three cases are the first fixtures in the regression suite;
if the guards cannot reject them, the guards do not work.

*(Figures are synthetic, reconstructed to preserve the shape of each failure.)*

## What this adds over the neighbours

Two excellent projects already exist, and this borrows from both:

- **[ali-demirbas/research](https://github.com/ali-demirbas/research)** — collection-time
  evidence chains with a deterministic validator, and origin tracing that counts independence
  over a root identity rather than URLs. The record contract and the "confidence is computed,
  never asserted by the model" stance come from there.
- **[aliradid/citation-needed](https://github.com/aliradid/citation-needed)** — post-hoc audit
  of a draft against live sources, returning an evidence ledger. Its `PARAPHRASED` verdict is
  the ancestor of the fidelity check here.

Both target claims gathered from the live web. This targets **figures transcribed into a
document and checked against a fixed corpus**, which needs four things neither provides:

1. **Rounding as a defect.** `source_value` is resolved *from the source*, never copied from
   the printed value. A generator that writes `"source_value": value` silently disables the
   check, because it then compares a value to itself.
2. **Closed coverage.** Every numeric token in the finished document resolves to exactly one
   of: a provenance record, an author-entered record carrying its reason, or an explicit
   `not_a_claim` declaration. A value in none of the three fails the build. No silent residual.
3. **Context-scored matching against held documents**, with ambiguity declared rather than
   guessed when two candidate figures tie.
4. **Append-only custody across revisions**, with content-hash ids that survive text being
   added elsewhere and reference numbers being renumbered.

## Install

```bash
claude plugin marketplace add <owner>/sourced-writing
claude plugin install sourced-writing@sourced-writing
```

Or copy `skills/sourced-writing/` into `~/.claude/skills/`.

## Use

```bash
S=~/.claude/skills/sourced-writing/scripts

python3 $S/verify_provenance.py provenance_current.jsonl   # quote -> source, exactness, rounding
python3 $S/check_rounding.py --config sourcing.json        # values rounded out of their source
python3 $S/check_fidelity.py provenance_current.jsonl      # clause claims more than the quote
python3 $S/test_guards.py -v                               # the regression suite
```

`scripts/custody.py` is the library: `stable_id`, `resolve_source_value`, `courtesy_check`,
`locator_ok`, `fidelity_flags`, `assert_append_only`.

### Fire the rule when a source is opened

A `PreToolUse` hook that reminds at the moment of use rather than in a file nobody rereads.
Non-blocking on purpose; the gate that bites is coverage.

```json
"hooks": {"PreToolUse": [{"matcher": "Read|WebFetch|Bash",
  "hooks": [{"type": "command",
             "command": "python3 ~/.claude/skills/sourced-writing/scripts/source_read_hook.py"}]}]}
```

## Values the author typed

A number the author writes into the document is **legitimately unsourced**, not an error, and
is recorded as such with its reason. The tool must never go and find a quote for it, which
would be inventing a source for a value nobody watched being sourced.

As a courtesy it still checks that value against the reference the author cited, reporting
`consistent`, `not_found` or `no_citation` in a separate `courtesy_check` object that can
never be mistaken for provenance. The useful outcome is `not_found`.

## The QC document

**Offered, never assumed.** When the skill runs a QC pass it asks once whether you want it.
Many projects already keep their own QC document and a silent second one is confusing.

```bash
python3 skills/sourced-writing/scripts/qc_document.py \
        --config sourcing.json --coverage coverage.json \
        --requirements requirements.json --metrics metrics.json
```

Writes `sourced-writing-qc.md`, named so it is never confused with your own QC file, and it
**refuses to overwrite any file it did not generate**.

Ten sections, arrived at independently by two unrelated manuscripts:

| # | Section | Source |
|---|---|---|
| 1 | Purpose, and the date links were verified | generated |
| 2 | Source register, every source with a live link | generated |
| 3 | Claim-to-source table, in document order, with the source's own words | generated |
| 4 | Submission requirements compliance | from your guide |
| 5 | Automated verification log | stub |
| 5a | Provenance summary, by evidence path | generated |
| 5b | Coverage, A / B / C / D | from your counts |
| 6 | Discrepancy log | stub |
| 7 | Interpretation log | stub |
| 8 | Author information | stub |
| 9 | Numeric worksheet, grouped by source document | generated |
| 10 | Confidentiality attestation | stub |

Sections needing judgment come out as labelled stubs and the run prints how many remain. A
generator that invented a discrepancy log would produce exactly the confident-looking artifact
this repo exists to prevent.

**Section 4 is venue-neutral.** A journal, a health authority, a conference and an internal
template impose different limits, and this tool assumes none. With no requirements supplied it
asks for them by name: which text the word limit covers and what it excludes, the abstract
limit, the reference cap and whether table-only citations count, the figure and table cap, and
any prescribed section order.

It will not compute coverage, and it will not decide whether a measured value satisfies a
limit. Both are project and venue specific, and a second counter that disagrees with yours is
worse than none.

`references/qc-document.md` explains what belongs in each section.

## Coverage is closed

Every value resolves to exactly one state. A value in none of them fails the build.

| State | Meaning |
|---|---|
| **A** sourced | a verified record with a verbatim quote |
| **B** author-entered | recorded as unsourced, with the reason |
| **C** not a claim | an explicit confirmed declaration, with a stated reason |
| **D** unproven | **named individually**, never reported only as a total |

"188 unresolved" tells a reader nothing about whether those are structural labels or
untraceable claims. D is a list, not a number.

## A record, field by field

```json
{"id":"p3f9a1c204","value":"42.6%","as_printed":"42.6% higher in biomarker-positive patients",
 "source_value":"42.6%","doc":"Falk 2021, J Appl Pharmacol","doc_path":"sources/falk2021.txt",
 "ref":16,"locator":"Table 2, median marker row","url":"https://example.org/falk2021",
 "quote":"Median marker (mg/L) 9.8 (0.4, 148) 20.25 (0.8, 184) 42.6","retrieved":"2026-09-18"}
```

| Field | Why it exists |
|---|---|
| `id` | content hash, so it survives text being added elsewhere and references being renumbered |
| `value` / `source_value` | what the deliverable prints against what the source prints. Equal unless someone rounded, which is a defect |
| `as_printed` | the surrounding clause, so a reader can judge whether the claim matches the quote |
| `quote` | copied verbatim. Typed from memory, it is decorative |
| `locator` | precise enough to find by eye. `#page=N` for a PDF, so clicking lands on the claim |
| `doc_path` | a local extract, which is what makes the record machine-verifiable |

## The honest part

`status` on a machine-generated record reads `candidate, not human-confirmed`, because that is
what it is. Provenance cannot be established retroactively: for a document already drafted
without records, write a baseline marked `baseline, origin not witnessed` and treat that line
as the start of custody rather than as evidence.

No similarity threshold, edit distance, or best-available fallback belongs anywhere in
verification. Every relaxation added to the matcher that failed was individually defensible,
and their sum was a system that could confirm anything.

MIT.
