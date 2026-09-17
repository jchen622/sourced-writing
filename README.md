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

## The honest part

`status` on a machine-generated record reads `candidate, not human-confirmed`, because that is
what it is. Provenance cannot be established retroactively: for a document already drafted
without records, write a baseline marked `baseline, origin not witnessed` and treat that line
as the start of custody rather than as evidence.

No similarity threshold, edit distance, or best-available fallback belongs anywhere in
verification. Every relaxation added to the matcher that failed was individually defensible,
and their sum was a system that could confirm anything.

MIT.
