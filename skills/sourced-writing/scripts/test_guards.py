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
import re
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from custody import (  # noqa: E402
    AMBIGUOUS, MIN_CONTEXT, assert_append_only, collapse_latest, content_key, fidelity_flags,
    courtesy_check, locator_ok, resolve_interval, resolve_source_value, split_value,
    endpoints_any, same_interval, stable_id, unique_quantity, words,
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
# 5c. Confidence intervals. Both bounds must be found close together; the co-occurrence of
#     two specific decimals is the evidence, so a source containing them far apart, or only
#     one of them, must not resolve.
# --------------------------------------------------------------------------
TBL = [(11, "CR, n (%) [95% CI] | 58 (61.7) [51.1-71.5] | 54 (60.0) [49.1-70.2] |")]
LBL = [(2, "Complete response (CR), n (%) 54 (60) (95% CI) (49, 70)")]
check("interval resolves against a dash-separated table cell",
      (resolve_interval("95% CI 49.1 to 70.2", TBL, words("complete response")) or [None])[0]
      == "49.1-70.2")
check("interval resolves against a comma-separated label cell",
      (resolve_interval("95% CI 49 to 70", LBL, words("complete response")) or [None])[0]
      == "49, 70")
check("an interval absent from the source does not resolve",
      resolve_interval("95% CI 11.1 to 22.2", TBL, words("x")) is None)
check("a non-interval value is not treated as one",
      resolve_interval("44.4%", TBL, words("x")) is None)

FAR = [(9, "The lower value was 49.1 in the first cohort. " + ("filler text " * 12) +
           "A separate analysis reported 70.2 in an unrelated population.")]
check("bounds far apart in the source do not resolve as an interval",
      resolve_interval("95% CI 49.1 to 70.2", FAR, words("cohort")) is None,
      str(resolve_interval("95% CI 49.1 to 70.2", FAR, words("cohort")))[:90])
check("only the lower bound present does not resolve",
      resolve_interval("95% CI 51.1 to 99.9", TBL, words("complete response")) is None)

# --------------------------------------------------------------------------
# 5d. Ranges. "1.6 to 45 mg" is not a number with the unit "to 45 mg". Treating it that way
#     found 1.61 in the source as a "rounding parent" of 1.6 and asserted the manuscript had
#     rounded, which is a fabricated defect on a value that was never a single number.
# --------------------------------------------------------------------------
num, unit = split_value("1.6 to 45 mg")
check("a range is not split into a number and a bogus unit", unit is None or "to" not in unit,
      "split to (%r, %r)" % (num, unit))

RNG = [(6, "The compound exhibited dose-proportional pharmacokinetics over the dose range "
           "of 1.6 mg to 45 mg following subcutaneous administration.")]
got = resolve_interval("1.6 to 45 mg", RNG, words("dose proportional range subcutaneous"))
check("a bare range resolves when both endpoints sit together", got is not None,
      str(got)[:100])

DAYS = [(8, "predicted cumulative area under the concentration-time curve over 0-84 days")]
check("a day range resolves against a hyphenated source form",
      resolve_interval("0 to 84 days", DAYS, words("cumulative area under curve")) is not None)

SPLIT = [(9, "The value 1.6 appeared in the first cohort. " + ("filler " * 20) +
             "Separately, 45 was observed in an unrelated analysis.")]
check("endpoints far apart do not resolve as a range",
      resolve_interval("1.6 to 45 mg", SPLIT, words("cohort")) is None,
      str(resolve_interval("1.6 to 45 mg", SPLIT, words("cohort")))[:90])

# --------------------------------------------------------------------------
# 5e. Fixture 4. Proximity is not a separator. Two endpoints 44 characters apart, with a
#     sentence boundary and four other figures between them, were accepted as an interval
#     and the whole intervening span returned as the source value. Verification then read
#     that span as a rounding parent and reported a defect that did not exist. An interval's
#     endpoints are joined by interval punctuation and nothing else.
#     (Synthetic, reconstructed to preserve the shape of the failure.)
# --------------------------------------------------------------------------
NOTSEP = [(8, "Cohort A: Cycle 1 (step-up dosing, 21 day cycle): 1 mg D1, 2 mg D8 and "
              "30 mg D15. 28 day Cycle 2-12: 30 mg D1.")]
check("two figures separated by prose are not an interval",
      resolve_interval("21 to 28 days", NOTSEP, words("cycle dosing step up")) is None,
      str(resolve_interval("21 to 28 days", NOTSEP, words("cycle dosing step up")))[:110])

NODIG = [(8, "values of 21 and 30 and 28 were recorded")]
check("an intervening third figure blocks an interval match",
      resolve_interval("21 to 28", NODIG, words("values recorded")) is None,
      str(resolve_interval("21 to 28", NODIG, words("values recorded")))[:110])

check("a legitimate separator with words still resolves",
      resolve_interval("49.1 to 70.2", [(11, "the 95% CI was 49.1 to 70.2 overall")],
                       words("overall")) is not None)

check("two renderings of one interval compare equal",
      same_interval("0 to 84 days", "0-84") and same_interval("95% CI 49.1 to 70.2", "49.1-70.2"))
check("different intervals never compare equal",
      not same_interval("0 to 84 days", "0-42") and not same_interval("1.6 to 45 mg", "1.6 to 44 mg"))
check("a non-interval never compares equal to an interval",
      not same_interval("44.4%", "0-84"))
# The renderings a source actually produces, which broke the first attempt at this.
for src in ("70, 88", "63 \u2012 84", "1.6 mg to 45", "49.1\u201370.2", "1.54\u22122.36"):
    check("source rendering %r parses to endpoints" % src, endpoints_any(src) is not None)
check("manuscript and label renderings of one interval agree",
      same_interval("95% CI 70 to 88", "70, 88") and same_interval("63 to 84 days", "63 \u2012 84")
      and same_interval("1.6 to 45 mg", "1.6 mg to 45"))
check("strict endpoints still refuses a comma pair, so routing is unchanged",
      __import__("custody").endpoints("70, 88") is None)

# --------------------------------------------------------------------------
# 5e. Unique quantity: a SECOND evidence path, not a lowered threshold.
#
#     A value carrying a unit that occurs exactly once in the cited document is uniquely
#     identified by that document, however little prose surrounds it. Terse sentences
#     ("SC bioavailability is 89.8%.") offer almost nothing to overlap on, yet "89.8%"
#     appears once in the whole label. The strictness lives in the conditions: a unit is
#     required, and exactly one occurrence is required.
# --------------------------------------------------------------------------
ONE = [(6, "Absolute bioavailability Bioavailability 89.8% following subcutaneous injection.")]
got = unique_quantity("89.8", "%", ONE)
check("a unit-bearing value occurring exactly once qualifies", got is not None, str(got)[:90])

TWICE = [(6, "Rate was 89.8% in cohort A. A separate analysis reported 89.8% in cohort B.")]
check("the same quantity twice does NOT qualify", unique_quantity("89.8", "%", TWICE) is None)

BARE = [(2, "A total of 90 patients were enrolled. Of these, 90 were evaluable.")]
check("a bare number never qualifies, however unique",
      unique_quantity("90", None, [(2, "Exactly 90 patients were enrolled.")]) is None)

check("a value absent from the source does not qualify",
      unique_quantity("77.7", "%", ONE) is None)

OTHERUNIT = [(6, "Half-life was 89.8 days in the population.")]
check("a unit mismatch does not qualify", unique_quantity("89.8", "%", OTHERUNIT) is None)

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

# --------------------------------------------------------------------------
# 8. Defects found by review of this skill itself. Every case below is a bug that shipped in
#    the first version of these scripts, which is the same bar as every case above.
#    The suite previously imported only from custody, which is exactly why the bugs in
#    provenance.py and verify_provenance.py went unseen here. These import those modules.
# --------------------------------------------------------------------------
import subprocess  # noqa: E402

from check_rounding import NUM, all_occurrences, dec, unit_key  # noqa: E402
from custody import clause_sha  # noqa: E402
from provenance import _forget_seq_cache, _same_figure, record  # noqa: E402
from verify_provenance import appears_as_number, value_in_quote  # noqa: E402


def raises_valueerror(fn):
    try:
        fn()
        return False
    except ValueError:
        return True


# -- the number regex had no right-hand boundary -----------------------------
check("a 5-digit number is captured whole, not truncated to its first 4",
      [x for x, _ in NUM.findall("12345")] == ["12345"], str(NUM.findall("12345")))
_src = [("9", "the cohort enrolled 12345 participants overall in the pooled analysis set")]
_w = words("a total of 1234 participants were enrolled in the pooled analysis set cohort")
check("1234 is NOT confirmed against a source that only prints 12345",
      all_occurrences("1234", None, _src, _w, True) == [],
      "the digit-anywhere failure, reintroduced inside the matcher")
# ... and the guard must block a following digit only, never a comma. A comma after a decimal
# is ordinary punctuation, and blocking it silently cost 12 confirmed quotes on a live corpus.
check("a comma-separated interval still yields both endpoints",
      [x for x, _ in NUM.findall("0.940 (0.908, 0.974)")] == ["0.940", "0.908", "0.974"],
      str(NUM.findall("0.940 (0.908, 0.974)")))
check("a thousands separator still parses as one number",
      [x for x, _ in NUM.findall("1,234 patients")] == ["1,234"])

# -- currency was captured as a bare number ---------------------------------
check("a currency magnitude suffix is captured, not dropped",
      NUM.findall("$1.2M revenue") == [("$1.2", "M")], str(NUM.findall("$1.2M revenue")))
check("dec() strips a currency symbol so callers still get a number", dec("$1.2") == dec("1.2"))

# -- the unit guard no-opped outside a 10-item whitelist --------------------
_ng = [("9", "steady state trough concentration was 50 ng per mL in the pooled analysis cohort set")]
_wng = words("the dose was 50 mg in the pooled analysis cohort set steady state")
check("a source's 50 ng does not satisfy a manuscript's 50 mg",
      all_occurrences("50", "mg", _ng, _wng, True) == [])
check("a matching unit is still accepted (the guard is not merely strict)",
      all_occurrences("50", "ng", _ng, _wng, True) != [])
check("an ordinary trailing word is not treated as a conflicting unit",
      unit_key("and") is None and unit_key("ng") == "ng",
      "firing on any trailing word rejected 3 true quotes on live corpora")

# -- the VALUE check was plain substring containment ------------------------
check("source_value 2.6 is NOT found in a quote reading 42.6",
      not appears_as_number("2.6", "median marker 42.6 in the treated arm"))
check("source_value 50 is NOT found in a quote reading 50.5",
      not appears_as_number("50", "exposure was 50.5 units"))
check("a number ending a sentence is still found",
      appears_as_number("50", "the observed value was 50."))
check("the figure the quote really does state is still found",
      appears_as_number("42.6", "median marker 42.6 in the treated arm"))
# Non-numeric claims are supported and in live use, so the numeric rule must not apply to them.
check("a prose source_value is matched by containment, not by the numeric rule",
      value_in_quote("no more popPK analysis will be done after DBL",
                     "Confirmed: no more popPK analysis will be done after DBL."))
check("a prose source_value absent from the quote still fails",
      not value_in_quote("no more popPK analysis will be done", "Analysis is ongoing."))

# -- the write-time guard rejected its own documented example ---------------
check("value 42.6% is accepted against source_value 42.6 (unit only)",
      _same_figure("42.6%", "42.6"))
check("a rounded value is still refused at write time", not _same_figure("43", "42.6"))
check("trailing zeros are still data, not formatting", not _same_figure("7.10", "7.1"))
check("one interval written two ways is accepted", _same_figure("5.9-8.7", "5.9 to 8.7"))
check("two different prose claims are still refused", not _same_figure("increased", "decreased"),
      "digit comparison alone makes every non-numeric pair equal")

# -- records with no doc_path counted as verified ---------------------------
VP = str(Path(__file__).resolve().parent / "verify_provenance.py")
with tempfile.TemporaryDirectory() as td:
    jl = Path(td) / "provenance.jsonl"
    jl.write_text("".join(json.dumps({
        "id": "p%02d" % i, "value": "42.6", "source_value": "42.6",
        "as_printed": "42.6 in the treated arm", "doc": "Falk 2021",
        "url": "https://example.org", "locator": "Table 2",
        "quote": "median marker 42.6 in the treated arm", "retrieved": "2026-09-17",
    }) + "\n" for i in range(5)), encoding="utf-8")
    out = subprocess.run([sys.executable, VP, str(jl)], capture_output=True, text=True)
    check("5 records with no doc_path report 0 verified, not 5",
          "0/5 verified" in out.stdout, out.stdout.strip()[-200:])
    check("...and they are still reported, not dropped", "5 unverifiable" in out.stdout)
    strict = subprocess.run([sys.executable, VP, str(jl), "--strict"],
                            capture_output=True, text=True)
    check("--strict exits non-zero when nothing could be opened", strict.returncode != 0)
    bad = Path(td) / "bad.jsonl"
    bad.write_text(json.dumps({"id": "pq", "value": "1"}) + "\n", encoding="utf-8")
    mal = subprocess.run([sys.executable, VP, str(bad)], capture_output=True, text=True)
    check("a record missing required fields is named, not a bare KeyError",
          "MALFORMED" in mal.stderr and "KeyError" not in mal.stderr, mal.stderr[-160:])

# -- id collisions were silently dropped -----------------------------------
_a = {"id": "px", "value": "1", "clause_sha": clause_sha("one clause")}
_b = {"id": "px", "value": "2", "clause_sha": clause_sha("a different clause")}
check("two different claims sharing one id are refused, not collapsed",
      raises_valueerror(lambda: collapse_latest([_a, _b])))
check("a genuine correction under the same id still supersedes",
      [r["value"] for r in collapse_latest([_a, dict(_b, clause_sha=_a["clause_sha"])])] == ["2"])
check("a record with no id reports itself rather than raising KeyError",
      raises_valueerror(lambda: collapse_latest([{"value": "1"}])))
check("legacy records without clause_sha still load",
      [r["value"] for r in collapse_latest([{"id": "py", "value": "1"},
                                            {"id": "py", "value": "2"}])] == ["2"])
_chg = {}
collapse_latest([{"id": "pz", "value": "1", "quote": "a"},
                 {"id": "pz", "value": "2", "quote": "a"}], changes=_chg)
check("a supersede reports which fields changed (content_key is no longer dead)",
      _chg.get("pz") == ["value"], str(_chg))

# -- _next_seq was O(n^2) and is now cached: ids must stay byte-identical ---
_REC = dict(value="42.6", source_value="42.6", as_printed="42.6 in the treated arm",
            doc="Falk 2021", url="https://example.org", locator="Table 2",
            quote="median marker 42.6")
with tempfile.TemporaryDirectory() as td:
    jl = Path(td) / "p.jsonl"
    _forget_seq_cache()
    ids = [record(path=jl, **_REC)["id"] for _ in range(4)]
    check("cached sequential ids are still dense and in order",
          ids == ["p0001", "p0002", "p0003", "p0004"], str(ids))
    _forget_seq_cache()
    check("a cold cache re-seeds from the file and does not restart at 1",
          record(path=jl, **_REC)["id"] == "p0005")

# --------------------------------------------------------------------------
# A reference number is a document, not a folder of related ones.
#
# `local_sources` let one reference map to many files and pooled them into a single searchable
# string, so a value present only in an agency *review* of a label was reported as confirmed
# against a reference that is the label. Two real claims passed that way on a live review: a
# pre-specified non-inferiority threshold and a secondary endpoint, neither of which appears
# anywhere in the cited Prescribing Information. A reviewer found both by reading.
# --------------------------------------------------------------------------
CR = str(Path(__file__).resolve().parent / "check_rounding.py")
CC = str(Path(__file__).resolve().parent / "check_coverage.py")

LABEL = ("the geometric mean ratio (GMR) (90% CI) for cycle 1 ctrough was 1.05 (0.88, 1.24) "
         "and auc0-21days was 0.87 (0.83, 0.92); the steady state ctrough was 1.15 (1.05, 1.26).")
REVIEW = ("the lower bound of the 90% ci for the pre-specified geometric mean ratio (gmr) was "
          "0.8. the gmr for aucinf at cycle 1 value was 0.97 (90% ci: 0.91, 1.05).")


def _project(td, body, *, register, nac=None, prov=None):
    d = Path(td)
    (d / "label.txt").write_text(LABEL, encoding="utf-8")
    (d / "review.txt").write_text(REVIEW, encoding="utf-8")
    cfg = {"manuscript": "m.md", "cache": "absent.json",
           "local_sources": {"3": ["label.txt", "review.txt"]}}
    if register:
        cfg["references"] = {"3": {"is": "the label", "authoritative": ["label.txt"],
                                   "supporting": ["review.txt"]}}
    (d / "sourcing.json").write_text(json.dumps(cfg), encoding="utf-8")
    (d / "m.md").write_text(body + "\n\n## References\n\n3. The label.\n", encoding="utf-8")
    if nac is not None:
        (d / "not_a_claim.json").write_text(json.dumps(nac), encoding="utf-8")
    if prov is not None:
        (d / "provenance.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in prov), encoding="utf-8")
    return str(d / "sourcing.json")


# the exact claim that slipped through: a secondary endpoint only the agency review carries
AUCINF = "The Cycle 1 AUCinf GMR was 0.97 (90% CI 0.91 to 1.05) (3)."
with tempfile.TemporaryDirectory() as td:
    cfgp = _project(td, AUCINF, register=True)
    out = subprocess.run([sys.executable, CR, "--config", cfgp, "--check"],
                         capture_output=True, text=True)
    nwrong = re.search(r"WRONG DOCUMENT FOR THE CITATION   : (\d+)", out.stdout)
    # 0.97 appears only in the review. 1.05 legitimately appears in the label too, as part of
    # "1.15 (1.05, 1.26)", so the confirmed count is not expected to be zero: what matters is
    # that the value the label does NOT carry is the one reported as the wrong document.
    check("a value only in a supporting document is NOT confirmed for the cited reference",
          bool(nwrong) and int(nwrong.group(1)) > 0
          and "WRONG DOCUMENT  0.97" in out.stdout,
          out.stdout.strip()[-260:])
    check("...and --check exits non-zero on it", out.returncode != 0)
    check("...and it is named as the wrong document, not reported as unsourced",
          "is not in reference 3" in out.stdout, out.stdout.strip()[-200:])

# negative control: the guard must not refuse a value the cited reference genuinely contains
with tempfile.TemporaryDirectory() as td:
    cfgp = _project(td, "Cycle 1 AUC0-21days GMR was 0.87 (90% CI 0.83 to 0.92) (3).",
                    register=True)
    out = subprocess.run([sys.executable, CR, "--config", cfgp, "--check"],
                         capture_output=True, text=True)
    m = re.search(r"exact quotes confirmed in context : (\d+)", out.stdout)
    check("a value genuinely in the authoritative document still confirms",
          bool(m) and int(m.group(1)) > 0
          and "WRONG DOCUMENT FOR THE CITATION   : 0" in out.stdout,
          out.stdout.strip()[-200:])
    check("...and that run exits clean", out.returncode == 0)

# negative control: a project with no register keeps working, and says why that is a risk
with tempfile.TemporaryDirectory() as td:
    cfgp = _project(td, AUCINF, register=False)
    out = subprocess.run([sys.executable, CR, "--config", cfgp], capture_output=True, text=True)
    check("with no `references` entry the old pooling behaviour is preserved",
          "WRONG DOCUMENT FOR THE CITATION   : 0" in out.stdout
          and "exact quotes confirmed in context : 0" not in out.stdout,
          out.stdout.strip()[-200:])
    check("...but a multi-file reference now warns instead of staying silent",
          "pools 2 files with no `references` entry" in out.stderr, out.stderr.strip()[-200:])

# the same hole from the record side: a quote in *some* file proved nothing about the reference
with tempfile.TemporaryDirectory() as td:
    cfgp = _project(td, AUCINF, register=True)
    jl = Path(td) / "p.jsonl"
    jl.write_text(json.dumps({
        "id": "p0001", "value": "0.97", "source_value": "0.97", "ref": 3,
        "as_printed": "Cycle 1 AUCinf GMR 0.97", "doc": "the label", "locator": "s12.3",
        "url": "https://example.org", "doc_path": "review.txt", "retrieved": "2026-11-07",
        "quote": "the gmr for aucinf at cycle 1 value was 0.97 (90% ci: 0.91, 1.05)."}) + "\n",
        encoding="utf-8")
    out = subprocess.run([sys.executable, VP, str(jl), "--config", cfgp],
                         capture_output=True, text=True)
    check("a record whose doc_path is not the cited reference fails REF",
          "REF" in out.stdout and out.returncode != 0, out.stdout.strip()[-240:])
    out2 = subprocess.run([sys.executable, VP, str(jl)], capture_output=True, text=True)
    check("...and without --config the record still verifies, so old logs are unaffected",
          out2.returncode == 0, out2.stdout.strip()[-200:])

# --------------------------------------------------------------------------
# Coverage was documented as closed and enforced by nothing. An uncited "22%" and an uncited
# "approximately 4500 patients across 12 trials" sat in a manuscript that passed every gate.
# --------------------------------------------------------------------------
CLAIM22 = "The maximum decrease in clearance with time was 22.4%."
_REC22 = {"id": "p1", "value": "22.4", "source_value": "22.4", "ref": 3,
          "as_printed": "22.4%", "doc": "d", "locator": "l", "quote": "q", "url": "u"}
for name, nac, prov, want_resid, want_rc in [
        ("a value with no record and no exemption is an UNRESOLVED failure", None, None, 1, True),
        ("a not_a_claim exemption carrying a real reason closes the value",
         [{"value": "22.4", "where": "4.1", "why": "a count the document derives itself"}],
         None, 0, False),
        ("a value carried by a provenance record is covered", None, [_REC22], 0, False)]:
    with tempfile.TemporaryDirectory() as td:
        cfgp = _project(td, CLAIM22, register=True, nac=nac, prov=prov)
        out = subprocess.run([sys.executable, CC, "--config", cfgp],
                             capture_output=True, text=True)
        check(name, (f"UNRESOLVED (no record, no exempt): {want_resid}" in out.stdout
                     and (out.returncode != 0) == want_rc), out.stdout.strip()[-200:])

with tempfile.TemporaryDirectory() as td:
    cfgp = _project(td, CLAIM22, register=True,
                    nac=[{"value": "22.4", "where": "4.1", "why": "   "}])
    out = subprocess.run([sys.executable, CC, "--config", cfgp], capture_output=True, text=True)
    check("an exemption with an empty reason is refused, not honoured",
          "REFUSED 1" in out.stdout and out.returncode != 0, out.stdout.strip()[-200:])

print()
print("=" * 62)
print("passed %d, FAILED %d" % (len(PASS), len(FAIL)))
for n, d in FAIL:
    print("  FAIL  %s%s" % (n, ("\n          " + d) if d else ""))
sys.exit(1 if FAIL else 0)
