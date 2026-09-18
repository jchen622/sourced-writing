#!/usr/bin/env python3
"""Emit a source-traceability QC document from the provenance records.

Two independent manuscripts converged on the same ten-section structure, which is what makes
it a template rather than one project's habit. This builds that document from data, so the
parts that can go stale never do.

    python3 qc_document.py --config sourcing.json --out qc_generated.md

Populated from the records: the source register, the claim-to-source table, the provenance
summary, the confidentiality attestation, and a numeric worksheet.

Left as labelled stubs: the compliance table, the automated verification log, the discrepancy
log, the interpretation log, and author information. Those need judgment, and a generator that
invented them would produce exactly the confident-looking artifact this skill exists to
prevent. Every stub says so on its own line, and the run prints how many there are.

What it deliberately does NOT do: count total coverage. Deciding what is "a value" in a
manuscript is project-specific, and a second counter that disagrees with the project's own is
worse than no counter. Pass --coverage with a project-emitted JSON to include that table.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, OrderedDict
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import custody  # noqa: E402

STUB = "> **UNFILLED.** %s"
# Written into every generated file. The tool refuses to overwrite anything lacking it,
# so pointing --out at a hand-maintained QC document cannot destroy it.
MARKER = "sourced-writing-qc-document"


def load_config(p: Path):
    cfg = json.loads(p.read_text(encoding="utf-8"))
    base = p.resolve().parent
    return cfg, base


def records_for(base: Path, cfg: dict, override=None):
    """Prefer the collapsed current file; fall back to a single-file log."""
    for name in ([override] if override else
                 [cfg.get("records"), "provenance_current.jsonl", "provenance.jsonl"]):
        if not name:
            continue
        p = base / name
        if p.exists():
            return custody.collapse_latest(custody.read_jsonl(p)), p.name
    return [], None


def reference_list(md: str, heading: str):
    m = re.search(r"^%s\s*\n(.*?)(?=^## |\Z)" % re.escape(heading), md, re.M | re.S)
    if not m:
        return {}
    return {int(a): b.strip() for a, b in re.findall(r"^(\d+)\.\s+(.*)$", m.group(1), re.M)}


def section_of(rec):
    """The manuscript section a record belongs to, when the record carries one."""
    ap = rec.get("as_printed", "")
    if " · " in ap:
        head = ap.split(" · ")[0].strip()
        if head and len(head) < 70:
            return head
    return "Claims not mapped to a section"


def esc(s):
    return re.sub(r"\s+", " ", str(s or "")).replace("|", "/").strip()


def build(cfg, base, recs, src_name, coverage=None, requirements=None, metrics=None):
    metrics = metrics or {}
    md_path = base / cfg.get("manuscript", "manuscript_full.md")
    md = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    refs = reference_list(md, cfg.get("references_heading", "## References"))
    today = date.today().isoformat()
    urls, docs = {}, {}
    for r in recs:
        if r.get("ref") is not None:
            urls.setdefault(int(r["ref"]), r.get("url", ""))
            docs.setdefault(int(r["ref"]), r.get("doc", ""))

    author = [r for r in recs if r.get("origin") == "author"]
    sourced = [r for r in recs if r.get("origin") != "author"]
    stubs = []
    o = []
    A = o.append

    A("# Sourced-writing skill QC document\n")
    A("<!-- %s: generated file, safe to overwrite. A project's own hand-maintained QC\n"
      "document is a different file and this tool will not write over it. -->\n" % MARKER)
    A("Produced by the `sourced-writing` skill on request. It is **not** a substitute for a\n"
      "project's own QC document: it records what the provenance data supports, and marks\n"
      "everything else as unfilled.\n")
    A("Generated %s from `%s`. Regenerate after any change; the populated sections are "
      "derived from the records and go stale otherwise.\n" % (today, src_name or "no records"))

    # ---------------------------------------------------------------- 1
    A("## 1. Purpose\n")
    A("Every factual and numeric claim in the deliverable can be checked against a named "
      "source without re-deriving anything. Each claim carries the source, a locator precise "
      "enough to find it by eye, and the source's own words.\n")
    A("Provenance here was recorded when each value was written, not reconstructed by "
      "searching afterwards. A value with no record is reported as unresolved rather than "
      "matched to a plausible passage.\n")

    # ---------------------------------------------------------------- 2
    A("## 2. Source register\n")
    if refs:
        A("| ID | Source | Link | Records |")
        A("|---|---|---|---|")
        per = Counter(int(r["ref"]) for r in recs if r.get("ref") is not None)
        for n in sorted(refs):
            u = urls.get(n, "")
            A("| %d | %s | %s | %d |" % (n, esc(refs[n])[:150],
                                         "[open](%s)" % u if u else "no link recorded",
                                         per.get(n, 0)))
        A("")
    else:
        stubs.append("source register")
        A(STUB % "No numbered reference list was found in the manuscript. List each source "
                 "with an ID, its type, and a live link.\n")

    # ---------------------------------------------------------------- 3
    A("## 3. Claim-to-source table\n")
    A("The Location column carries the source's **own words**, never a paraphrase.\n")
    groups = OrderedDict()
    for r in sourced:
        groups.setdefault(section_of(r), []).append(r)
    # Order the groups as the manuscript does, not as the records happen to fall. A checker
    # works down the deliverable; a claim table in record order makes them hunt.
    heads = [h.strip() for h in re.findall(r"^#{2,3}\s+(.+)$", md, re.M)]
    def where(sec):
        for i, h in enumerate(heads):
            if h == sec or h.startswith(sec) or sec.startswith(h):
                return i
        return len(heads) + 1
    for sec in sorted(groups, key=where):
        rows = groups[sec]
        A("### %s\n" % sec)
        A("| Value | Claim as printed | Source | Location and verbatim quote |")
        A("|---|---|---|---|")
        for r in rows:
            loc = esc(r.get("locator"))
            q = esc(r.get("quote"))
            cell = (loc + (' \u00b7 verbatim: "%s"' % q[:220] if q else "")) or "no locator recorded"
            A("| `%s` | %s | %s | %s |" % (esc(r.get("value")), esc(r.get("as_printed"))[:150],
                                           esc(r.get("doc"))[:60], cell[:320]))
        A("")

    # ---------------------------------------------------------------- 3b author-entered
    if author:
        A("### Author-entered values, unsourced by design\n")
        A("Values the author wrote. No quote is attached: only the author knows the origin. "
          "The courtesy check reports what the cited reference contains, which is a different "
          "and lesser claim.\n")
        A("| Value | Claim as printed | Reason | Courtesy check |")
        A("|---|---|---|---|")
        for r in author:
            cc = r.get("courtesy_check") or {}
            A("| `%s` | %s | %s | %s |" % (
                esc(r.get("value")), esc(r.get("as_printed"))[:120],
                esc(r.get("unsourced_reason"))[:90],
                "%s%s" % (cc.get("result", "not checked"),
                          (', passage: "%s"' % esc(cc.get("passage"))[:130]) if cc.get("passage") else "")))
        A("")

    # ---------------------------------------------------------------- 4
    # Venue-neutral on purpose. A journal, a health authority, a conference and an internal
    # template all impose different limits, and this skill has no business assuming any of
    # them. The requirements come from whoever is submitting.
    A("## 4. Submission requirements compliance\n")
    req = cfg.get("requirements") or requirements or {}
    limits = req.get("limits") or []
    if limits:
        if req.get("venue"):
            A("Requirements as set by **%s**%s.\n"
              % (req["venue"], ", from %s" % req["source"] if req.get("source") else ""))
        A("| Requirement | Limit | Measured | Met |")
        A("|---|---|---|---|")
        for lim in limits:
            item = esc(lim.get("item"))
            got = lim.get("measured", metrics.get(lim.get("key", item), ""))
            met = lim.get("met", "" if got == "" else "")
            A("| %s | %s | %s | %s |" % (item, esc(lim.get("limit")),
                                         esc(got) if got != "" else "not measured",
                                         esc(met) if met != "" else "\u2610"))
        A("")
        missing = [l for l in limits
                   if l.get("measured", metrics.get(l.get("key", l.get("item")), "")) == ""]
        if missing:
            stubs.append("measured values for %d requirement(s)" % len(missing))
            A(STUB % ("%d requirement(s) have no measured value. Measure them with the "
                      "project's own counters and supply them with --metrics, rather than "
                      "letting this tool invent a second counter that disagrees.\n"
                      % len(missing)))
    else:
        stubs.append("submission requirements")
        A(STUB % "No requirements were supplied, and this tool does not assume a venue.\n")
        A("Ask whoever is submitting for the applicable guide, then answer these:\n")
        A("- which body of text the word limit applies to, and what it excludes")
        A("- the abstract or summary limit, if any")
        A("- the reference cap, and whether references cited only in tables count")
        A("- the figure and table cap, and whether supplementary items count")
        A("- any prescribed section order or required sections")
        A("- anything else the venue enforces mechanically\n")
        A("Supply them as a `requirements` block in the config, or with `--requirements`:\n")
        A("```json\n{\"venue\": \"...\", \"source\": \"...\",\n"
          " \"limits\": [{\"item\": \"Body words\", \"limit\": \"2000 to 3000\", "
          "\"key\": \"body_words\"},\n"
          "             {\"item\": \"References\", \"limit\": \"25 max\", "
          "\"key\": \"references\"}]}\n```\n")

    # ---------------------------------------------------------------- 5
    A("## 5. Automated verification log\n")
    stubs.append("automated verification log")
    A(STUB % "Record what each gate checked and what it found, with the date it ran. At "
             "minimum: source resolution, page-citation resolution, provenance verification, "
             "and the rounding check.\n")

    A("### 5a. Provenance records\n")
    ev = Counter(r.get("evidence", "unlabelled") for r in sourced)
    A("- records: **%d** sourced, **%d** author-entered" % (len(sourced), len(author)))
    A("- with a verbatim quote: **%d**" % sum(1 for r in sourced if r.get("quote")))
    A("- source figure differs from the printed value (rounding): **%d**"
      % sum(1 for r in sourced if r.get("source_value") not in (None, r.get("value"))))
    if len(ev) > 1 or "unlabelled" not in ev:
        A("- evidence path: " + ", ".join("%s %d" % kv for kv in sorted(ev.items())))
    A("\nVerify with:\n")
    A("```bash\npython3 verify_provenance.py %s --root ..\n```\n" % (src_name or "records.jsonl"))

    if coverage:
        A("### 5b. Coverage\n")
        A("Every value resolves to exactly one state. A value in none of them is a failure.\n")
        A("| State | Meaning | Count |")
        A("|---|---|---|")
        for k, lbl in (("A", "sourced, verified"), ("B", "author-entered, reason recorded"),
                       ("C", "declared not a claim"), ("D", "unproven")):
            A("| %s | %s | %s |" % (k, lbl, coverage.get(k, "?")))
        A("")

    # ---------------------------------------------------------------- 6, 7, 8
    for num, title, hint in (
            ("6", "Discrepancy log",
             "One row per defect found, as Item / Detail / Resolution. Include defects in the "
             "TOOLING, not only the manuscript: a check that passed while something was wrong "
             "is the most valuable row in this table."),
            ("7", "Interpretation log",
             "One row per point where the brief was descriptive and a judgment call was "
             "referred to the author, as # / Point / Status. Record the decision, not only "
             "the question."),
            ("8", "Author information",
             "Authorship, affiliations, conflicts of interest, and funding.")):
        A("## %s. %s\n" % (num, title))
        stubs.append(title.lower())
        A(STUB % (hint + "\n"))

    # ---------------------------------------------------------------- 9
    A("## 9. Numeric verification worksheet\n")
    A("One row per recorded value, grouped by source so each document is opened once rather "
      "than once per row. Work down, click the source, confirm the value, tick the box.\n")
    by_ref = OrderedDict()
    for r in sorted(recs, key=lambda x: (x.get("ref") is None, x.get("ref") or 0)):
        by_ref.setdefault(r.get("ref"), []).append(r)
    n = 0
    for ref, rows in by_ref.items():
        label = docs.get(ref, "") or (refs.get(ref, "") if ref else "") or "no source recorded"
        u = urls.get(ref, "")
        A("### Reference %s: %s%s\n" % (ref if ref is not None else "none", esc(label)[:90],
                                        " ([open](%s))" % u if u else ""))
        A("| ☐ | # | Value | Where in the deliverable | What the source says | Check |")
        A("|---|---|---|---|---|---|")
        for r in rows:
            n += 1
            A("| ☐ | %d | `%s` | %s | %s | %s |" % (
                n, esc(r.get("value")), esc(r.get("as_printed"))[:110],
                esc(r.get("quote"))[:170] or "no quote recorded", esc(r.get("locator"))[:90]))
        A("")

    # ---------------------------------------------------------------- 10
    A("## 10. Confidentiality attestation\n")
    A("Every claim traces to a source in Section 2. Confirm before release that all of them "
      "are publicly accessible without an internal login, and that no unpublished analysis, "
      "internal document, or patient-level data was used.\n")
    stubs.append("confidentiality attestation confirmation")
    A(STUB % "Confirm the statement above, or list any exception and its approval.\n")

    text = "\n".join(o) + "\n"
    check_tables(text)
    return text, stubs, len(recs)


def check_tables(text):
    """Every row in a markdown table must have its header's column count.

    A separator character written into a cell after escaping adds a column and breaks the
    table silently: it still renders, just wrongly, which is the failure mode this whole
    skill is about. 281 rows broke this way once.
    """
    header, bad = None, []
    for i, line in enumerate(text.split("\n"), 1):
        if not line.startswith("|"):
            header = None
            continue
        n = line.count("|")
        if header is None:
            header = n
        elif set(line.replace("|", "").strip()) <= set("-: "):
            continue
        elif n != header:
            bad.append((i, n, header, line[:90]))
    if bad:
        raise AssertionError(
            "%d table row(s) have the wrong column count, most likely a raw '|' in a cell:\n"
            % len(bad) + "\n".join("  line %d: %d columns, header has %d: %s" % b for b in bad[:5]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="sourcing.json")
    ap.add_argument("--records", help="override the records file")
    ap.add_argument("--coverage", help="JSON with A/B/C/D counts from the project's own counter")
    ap.add_argument("--requirements", help="JSON of the venue's limits; the tool assumes none")
    ap.add_argument("--metrics", help="JSON of measured values, keyed to each requirement's key")
    ap.add_argument("--out", default="sourced-writing-qc.md",
                    help="named distinctly so it is never confused with, or written over,\n                          a project's own QC document")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an output file that this tool did not generate")
    a = ap.parse_args()

    cfgp = Path(a.config)
    if not cfgp.exists():
        print("no config at %s" % cfgp)
        return 2
    cfg, base = load_config(cfgp)
    recs, src = records_for(base, cfg, a.records)
    if not recs:
        print("no provenance records found beside %s" % cfgp)
        return 2
    cov = json.loads(Path(a.coverage).read_text(encoding="utf-8")) if a.coverage else None

    req = json.loads(Path(a.requirements).read_text(encoding="utf-8")) if a.requirements else None
    met = json.loads(Path(a.metrics).read_text(encoding="utf-8")) if a.metrics else None
    text, stubs, n = build(cfg, base, recs, src, cov, req, met)

    out = Path(a.out)
    if out.exists() and not a.force:
        existing = out.read_text(encoding="utf-8", errors="replace")[:600]
        if MARKER not in existing:
            print("REFUSING to overwrite %s: it was not generated by this tool and may be a "
                  "hand-maintained QC document. Choose another --out, or pass --force if you "
                  "are certain." % out)
            return 2
    out.write_text(text, encoding="utf-8")
    print("wrote %s from %d records" % (a.out, n))
    print("UNFILLED sections needing judgment: %d" % len(stubs))
    for s in stubs:
        print("   - %s" % s)
    if not (cfg.get("requirements") or a.requirements):
        print("no venue requirements supplied: section 4 asks for them rather than assuming "
              "a journal. Pass --requirements once you have the applicable guide.")
    if not cov:
        print("coverage table omitted: pass --coverage with the project's own A/B/C/D counts "
              "rather than letting this tool invent a second, disagreeing counter")
    return 0


if __name__ == "__main__":
    sys.exit(main())
