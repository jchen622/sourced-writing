# The QC document

A source-traceability record that ships beside the deliverable. Its job is to let someone who
was not there confirm every claim without re-deriving anything, and to make the gaps visible
rather than absent.

Generate it with `scripts/qc_document.py`. This file is the reasoning the generator cannot
carry: what belongs in each section, and the conventions that make it checkable.

*All examples below are synthetic.*

## The ten sections

Two unrelated manuscripts arrived at this structure independently, which is the reason to
trust it. Sections 1 to 3, 5a, 9 and 10 are generated from the records; the rest need
judgment and come out as labelled stubs.

**1. Purpose.** What the document is for, and the date its links were last verified. A
"verified" with no date decays silently and is worse than nothing.

**2. Source register.** Every source with an ID, a type, and a live link. The ID is what the
claim table and the worksheet point at, so it has to be stable. Note how many records cite
each source: a source with zero is either uncited or a renumbering casualty.

**3. Claim-to-source table.** Claim, source, and location, grouped **in manuscript order** so
a checker can work down the deliverable rather than hunt. The location column carries the
source's **own words**:

> | Value | Claim as printed | Source | Location and verbatim quote |
> | `42.6%` | 42.6% higher in biomarker-positive patients | Falk 2021 | Table 2, median marker row · verbatim: "Median marker (mg/L) 9.8 (0.4, 148) 20.25 (0.8, 184) 42.6" |

A paraphrase here defeats the purpose. The reader is checking whether the deliverable says
what the source says, and they cannot do that against your summary of it.

**3b. Author-entered values.** Values the author typed, recorded as unsourced **with the
reason**. No quote is attached, because only the author knows the origin. A courtesy check may
report whether the cited reference contains the value, kept in its own field so it can never be
mistaken for provenance.

**4. Submission requirements compliance.** Venue-neutral by design: a journal, a health
authority, a conference and an internal template all impose different limits, and this skill
assumes none of them. **Ask whoever is submitting for the applicable guide.** With no
requirements supplied the section asks for them by name rather than emitting a generic stub:
which text the word limit covers and what it excludes, the abstract limit, the reference cap
and whether table-only citations count, the figure and table cap, and any prescribed section
order.

Supply them as a `requirements` block in the config or with `--requirements`, and the measured
values with `--metrics`. The generator fills the limits and leaves a checkbox in the Met
column, because deciding whether "3,225" satisfies "2,000 to 3,000, excluding abstract and
references" is a reading of the guide, not a comparison.

**5. Automated verification log.** What each gate checked, what it found, and when it ran.
Include the checks that passed: a reader needs to know what was examined, not only what broke.

**5a. Provenance records.** Counts by evidence path, how many carry a verbatim quote, and how
many show a source figure differing from the printed value.

**5b. Coverage.** Every value in exactly one state: sourced, author-entered, declared not a
claim, or unproven. A value in none is a failure. See below.

**6. Discrepancy log.** Item, detail, resolution. **Include defects in the tooling**, not only
the manuscript. A check that passed while something was wrong is the most valuable row in this
table, and the one most likely to go unwritten.

**7. Interpretation log.** Points where the brief was descriptive and a judgment call went to
the author. Record the decision, not only the question.

**8. Author information.** Authorship, affiliations, conflicts, funding.

**9. Numeric verification worksheet.** One row per value with a checkbox, **grouped by source
document** so each is opened once rather than once per row. That grouping is the single biggest
saving in hand-checking time.

**10. Confidentiality attestation.** An explicit statement that every source is public and no
internal document or unpublished analysis was used. Explicit, because the absence of a
statement is not evidence of anything.

## Coverage is closed

| State | Meaning |
|---|---|
| **A** sourced | a verified record with a verbatim quote |
| **B** author-entered | recorded as unsourced, with the reason |
| **C** not a claim | an explicit confirmed declaration, with a stated reason |
| **D** unproven | named individually, never reported only as a total |

A value in none of the four is a hard failure. There is no fifth bucket, because a silent
residual is indistinguishable from an oversight.

**D is named, not counted.** "188 unresolved" tells a reader nothing about whether those are
structural labels or untraceable claims. List them with a disposition each.

## Conventions that were paid for

- **Locators are deep links.** `#page=N` for a PDF, so clicking lands on the claim. Once a page
  number is a link it becomes a promise, and a gate should check it resolves.
- **A page locator on a source with no pages is a defect.** It usually means locator prose was
  inherited from a different reference. The link can be right while the pointer misleads.
- **Display truncation must never reach the evidence path.** A worksheet column capped for
  table width is a rendering choice; scoring or matching against that truncated string throws
  away the context the check depends on.
- **A quote is copied, never re-parsed from a rendered table.** Escaping a pipe for markdown
  turns the quote into something that no longer appears in the source.
- **Regenerate, never hand-edit the generated sections.** Counts in prose go stale the moment
  anything changes, and a stale count reads as authoritative.
- **Two counters that can disagree will.** If the project already enumerates values, feed that
  count in rather than computing a second one.

## Stubs stay visibly stubs

The generator marks every unfilled section and prints how many there are. Leave the markers
until the section is genuinely filled. A document that is half empty and looks complete is
worse than one that is half empty and says so, which is the same principle as reporting an
honest twelve unresolved rather than a wrong zero.
