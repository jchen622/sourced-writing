#!/usr/bin/env python3
"""Regression suite for the provenance custody guards.

Every case here is a defect that once shipped, or a negative control proving the guard has
not been tuned into uselessness. A suite that only proves things fail is as worthless as one
that only proves things pass, so roughly a third of these assert that correct input is
accepted.

    python3 test_guards.py            # all cases
    python3 test_guards.py -v         # show each case

Fixtures only. Nothing here reads or writes the live manuscript files.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from custody import (  # noqa: E402
    AMBIGUOUS, MIN_CONTEXT, assert_append_only, collapse_latest, content_key, fidelity_flags,
    courtesy_check, locator_ok, resolve_source_value, split_value, stable_id, words,
)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    if "-v" in sys.argv:
        print("  %s  %s%s" % ("ok  " if cond else "FAIL", name, ("  <- " + detail) if detail and not cond else ""))


# --------------------------------------------------------------------------
# 1. The three false confirmations that started this.
#
# Each shipped with a checkmark reading "confirmed", and in each the printed figure was
# matched to digits that had nothing to do with the claim. The guard must refuse all three.
# Figures are synthetic; the failure shapes are reproduced exactly.
# --------------------------------------------------------------------------
SRC = (
    "Baseline characteristics. Race was recorded as White (64%) and Asian (21%), with the "
    "remainder unknown. A total of N = 43 patients were enrolled in the companion cohort. "
    "Clearance ranged from a minimum 12%, maximum 38% across the population. "
    "Median marker (mg/L) 9.8 (0.4, 148) 20.25 (0.8, 184) 42.6 higher in biomarker-positive "
    "patients. The sum of lesion diameters increased by 20.8% over baseline in "
    "biomarker-positive patients."
)
ECOG = ("Performance status 1 was more frequent in biomarker-positive patients, "
        "11.7% versus 4.1%, across the safety population.")
SOURCES = [(16, SRC)]

CASES = [
    ("43%", "marker higher in biomarker-positive patients", "42.6", "N = 43", SOURCES),
    ("21%", "sum of lesion diameters increased over baseline", "20.8", "Asian (21%)", SOURCES),
    ("12%", "performance status 1 more frequent in biomarker-positive patients",
     "11.7", "minimum 12%, maximum 38%", [(16, ECOG)]),
]
for printed, claim, truth, decoy, src in CASES:
    num, unit = split_value(printed)
    got = resolve_source_value(num, unit, src, words(claim), siblings=())
    # SAFETY, the property that matters: the decoy is never returned as a confirmed exact quote.
    check("%s is never confirmed against the decoy %r" % (printed, decoy),
          got is None or got[4] is True or got[0] != num,
          "resolved to %r" % (got,))
    # QUALITY: when it does resolve, it must name the right figure, or declare ambiguity.
    check("%s resolves to %s, or declines, but never to a wrong figure" % (printed, truth),
          got is None or got[0] in (truth, AMBIGUOUS),
          "resolved to %r" % (got,))

# Ambiguity must be declared, not guessed: two precise figures both rounding to the printed
# value, both scoring in context, must not silently pick one.
TIE = [(9, "Group A marker response 11.6% in treated patients. "
           "Group B marker response 11.7% in treated patients.")]
got = resolve_source_value("12", "%", TIE, words("marker response treated patients"))
check("a tie between two precise parents is declared ambiguous, not guessed",
      got is not None and got[0] == AMBIGUOUS, "resolved to %r" % (got,))

# --------------------------------------------------------------------------
# 2. Negative controls: correct input must still be accepted.
# --------------------------------------------------------------------------
GOOD = [(11, "Objective response rate was 76.6% (95% CI: 66.7-84.7) and complete response "
             "rate was 61.7% (95% CI: 51.1-71.5) in the treated cohort.")]
num, unit = split_value("76.6%")
got = resolve_source_value(num, unit, GOOD, words("objective response rate treated cohort"),
                           siblings=("61.7",))
check("an exact quote in context is accepted and not called rounded",
      got is not None and got[0] == "76.6" and got[4] is False, "resolved to %r" % (got,))

DENSE = [(8, "Cohort A 1/2/60/30 mg route X N = 90 Cohort B 5/45/45 mg route Y N = 68 "
             "C3 Ctrough GMR 1.39 90% CI 1.20-1.61 AUC GMR 1.06 90% CI 0.92-1.21")]
got = resolve_source_value("1.39", None, DENSE, words("cycle 3 ctrough geometric mean ratio"),
                           siblings=("1.20", "1.61"))
check("a dense table row with little prose still resolves via co-occurring figures",
      got is not None and got[0] == "1.39" and got[4] is False, "resolved to %r" % (got,))

# --------------------------------------------------------------------------
# 3. Stable ids.
# --------------------------------------------------------------------------
a = stable_id("6. Clinical efficacy", "60.0%", "Complete response rate was 60.0% (95% CI 49.1 to 70.2)")
b = stable_id("6. Clinical efficacy", "60.0%", "Complete response rate was 60.0% (95% CI 49.1 to 70.2)")
c = stable_id("6. Clinical efficacy", "61.7%", "Complete response rate was 61.7% (95% CI 51.1 to 71.5)")
check("the same claim yields the same id", a == b)
check("a different value yields a different id", a != c)
check("id is stable under whitespace and case", a == stable_id(
    "6.  CLINICAL efficacy", "60.0%", "Complete  response rate  was 60.0% (95% CI 49.1 to 70.2)"))

# --------------------------------------------------------------------------
# 4. Locator sanity: a page cited against a source that has no pages.
# --------------------------------------------------------------------------
check("a page locator on a non-paged source is rejected",
      locator_ok('[p. 87, verbatim: "as assessed"](https://example.org/journal/a)',
                 "https://example.org/journal/a", paged_refs={3, 8}, ref=11) is not None)
check("a page locator on a paged source is accepted",
      locator_ok("[p. 87](https://example.org/review.pdf#page=87)",
                 "https://example.org/review.pdf", paged_refs={3, 8}, ref=3) is None)
check("a locator linking to another document is rejected",
      locator_ok("[Section 12.3](https://example.org/label/other)",
                 "https://example.org/journal/a", paged_refs={3, 8}, ref=11) is not None)
check("a locator with no link is accepted",
      locator_ok("Section 12.3, Table 10", "https://example.org/label/x",
                 paged_refs={3, 8}, ref=6) is None)

# --------------------------------------------------------------------------
# 5. Fidelity: meaning added in the retelling.
# --------------------------------------------------------------------------
f = fidelity_flags("CRS was significantly reduced with SC dosing",
                   "CRS events were reported in 29.8% of patients, a numerically lower rate")
check("'significantly' absent from the quote is flagged", any(k == "inference" for k, _ in f), str(f))
check("'reduced' absent from the quote is flagged", any(k == "direction" for k, _ in f), str(f))
f2 = fidelity_flags("Steady-state C_max was 4.4 ug/mL by the SC route",
                    "Cmax 7.0 ug/mL following infusion by the other route")
check("a route named in the clause but not the quote is flagged",
      any(k == "scope" for k, _ in f2), str(f2))
f3 = fidelity_flags("Complete response rate was 61.7%",
                    "complete response rate, 61.7% (95% CI: 51.1-71.5)")
check("a faithful clause raises no flag", f3 == [], str(f3))

# --------------------------------------------------------------------------
# 5b. Courtesy check on author-entered values. Not provenance: it reports what the cited
#     document contains, never where the author got the number.
# --------------------------------------------------------------------------
CITED = [(11, "Objective response rate was 76.6% (95% CI: 66.7-84.7) in the treated cohort "
              "at the primary analysis.")]
cc = courtesy_check("76.6", "%", CITED, words("objective response rate treated cohort"),
                    ref=11, checked="2026-09-17")
check("courtesy: value present in the cited reference reads consistent",
      cc["result"] == "consistent" and cc["passage"], str(cc)[:110])

cc = courtesy_check("88.1", "%", CITED, words("objective response rate treated cohort"),
                    ref=11, checked="2026-09-17")
check("courtesy: value absent from the cited reference reads not_found",
      cc["result"] == "not_found", str(cc)[:110])

cc = courtesy_check("76.6", "%", [], words("anything"), ref=None)
check("courtesy: nothing cited reads no_citation", cc["result"] == "no_citation", str(cc)[:110])

check("courtesy result never carries a field named quote", "quote" not in cc)

# --------------------------------------------------------------------------
# 6. Append-only history.
# --------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as d:
    h = Path(d) / "provenance.jsonl"
    first = ['{"id": "pa", "value": "1"}', '{"id": "pb", "value": "2"}']
    h.write_text("\n".join(first) + "\n", encoding="utf-8")
    prior = h.read_text(encoding="utf-8").splitlines()

    h.write_text("\n".join(first + ['{"id": "pa", "value": "3"}']) + "\n", encoding="utf-8")
    try:
        assert_append_only(h, prior); ok = True
    except AssertionError:
        ok = False
    check("appending a superseding record is allowed", ok)

    h.write_text("\n".join([first[0], '{"id": "pb", "value": "CHANGED"}']) + "\n", encoding="utf-8")
    try:
        assert_append_only(h, prior); ok = False
    except AssertionError:
        ok = True
    check("editing a historical line in place is rejected", ok)

    h.write_text(first[0] + "\n", encoding="utf-8")
    try:
        assert_append_only(h, prior); ok = False
    except AssertionError:
        ok = True
    check("truncating history is rejected", ok)

recs = [{"id": "pa", "value": "1"}, {"id": "pb", "value": "2"}, {"id": "pa", "value": "3"}]
col = collapse_latest(recs)
check("collapse keeps the last record per id",
      [r["value"] for r in col] == ["3", "2"], str(col))
check("content_key ignores fields that are not the claim",
      content_key({"value": "1", "run": "A"}) == content_key({"value": "1", "run": "B"}))

# --------------------------------------------------------------------------
# 7. The hardcode that started this: source_value must never be set equal to value blindly.
# --------------------------------------------------------------------------
# Point this at a tree of real projects to scan their generators, e.g.
#     PROVENANCE_SCAN_ROOT=~/work python3 test_guards.py
# Skipped, loudly, when unset: a case that silently matches nothing is the same trap as a
# gate that cannot fail.
import os  # noqa: E402

root = os.environ.get("PROVENANCE_SCAN_ROOT")
if root:
    EP = Path(root).expanduser()
    cands = sorted(EP.rglob("*/_build/emit_provenance.py"))
    check("the hardcode detector found generators to scan under %s" % EP, bool(cands),
          "found none; check PROVENANCE_SCAN_ROOT")
else:
    cands = []
    print("  skip  generator hardcode scan (set PROVENANCE_SCAN_ROOT to enable)")
for f in cands:
    src = f.read_text(encoding="utf-8")
    check("%s does not hardcode source_value = value" % f.parent.parent.name[:28],
          '"source_value": value,' not in src,
          "found the literal hardcode that defeats the ROUND check")

print()
print("=" * 62)
print("passed %d, FAILED %d" % (len(PASS), len(FAIL)))
for n, d in FAIL:
    print("  FAIL  %s%s" % (n, ("\n          " + d) if d else ""))
sys.exit(1 if FAIL else 0)
