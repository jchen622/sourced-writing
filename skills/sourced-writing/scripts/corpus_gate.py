#!/usr/bin/env python3
"""Regression gate: run the checkers over real registers and refuse silent changes.

    python3 corpus_gate.py --snapshot          # before touching a checker
    python3 corpus_gate.py --check             # after; non-zero on any unexplained change
    python3 corpus_gate.py --check --verbose   # print the full diff

WHY THIS EXISTS, WHICH IS NOT OBVIOUS FROM THE NAME
---------------------------------------------------
test_guards.py is a defect ratchet and it is not sufficient. In the 2026-10 review round two
separate fixes to check_rounding.py **passed all 57 unit tests and were wrong on real data**:

  1. The number-boundary guard, written `(?![\\d,])`, also blocks a comma after a decimal. A
     comma there is ordinary punctuation, so in "0.940 (0.908, 0.974)" it captured a bare "0"
     instead of "0.908". Cost: 12 confirmed quotes lost and one rounding defect invented, on
     a corpus where the headline count barely moved.
  2. The unit-mismatch guard, comparing raw trailing tokens, read the "and" in "10.9 and 10.1
     months" as a unit conflicting with "months". Cost: three true exact quotes rejected.

Neither was reachable from a fixture, because both depend on how real sources punctuate. Both
were caught by diffing the full report against a pre-change baseline. That diff was ad hoc,
run once, in one session. This file makes it repeatable.

COMPARE WHOLE REPORTS, NOT HEADLINE COUNTS
------------------------------------------
Defect 1 above moved `exact quotes confirmed` by a visible amount, but a smaller change can
move individual values between buckets while the totals stay put. The gate stores and diffs
the entire report, including the `--unmatched` listing, for that reason.

THE REGISTRY IS LOCAL AND IS NOT COMMITTED
------------------------------------------
It names paths to real deliverables, which are confidential. Copy
`corpus_gate.example.json` to `corpus_gate.local.json`, point it at your own registers, and
keep it out of version control. The example ships with placeholder paths so the format is
documented without leaking anything.

    {"projects": [
       {"name": "proj-a", "records": "~/path/provenance.jsonl"},
       {"name": "proj-b", "records": "~/p/provenance.jsonl", "config": "~/p/sourcing.json"}
    ]}

`records` is a provenance register, run through verify_provenance. `config` is optional and
is a sourcing.json, run through check_rounding --unmatched.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_REGISTRY = HERE / "corpus_gate.local.json"
DEFAULT_SNAPDIR = Path.home() / ".cache" / "sourced-writing" / "corpus-gate"


def run(cmd):
    """Run a checker and return its output. A non-zero exit is normal here: a register with
    genuine failures still has a stable report, and stability is what is being gated."""
    p = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    return (p.stdout or "") + (p.stderr or "")


def fingerprint(registry):
    """Hash every input the checkers read, so a corpus edit cannot read as a code regression.

    This is not hypothetical. The first snapshot taken here disagreed with a baseline captured
    a few hours earlier (176 confirmed quotes versus 111) on identical code, because the
    manuscript, the sourcing config and the abstract cache had all been edited in between. A
    gate that reports that as "the scorer changed" trains its user to ignore it, which is the
    one failure mode a gate cannot survive. So the inputs are fingerprinted and reported
    separately from the output.
    """
    out = {}
    for proj in registry["projects"]:
        files = [Path(proj["records"]).expanduser()]
        cfg = proj.get("config")
        if cfg:
            cfgp = Path(cfg).expanduser()
            files.append(cfgp)
            if cfgp.exists():
                try:
                    c = json.loads(cfgp.read_text(encoding="utf-8"))
                except Exception:
                    c = {}
                base = cfgp.resolve().parent
                for key in ("manuscript", "cache", "adjudications"):
                    if c.get(key):
                        files.append(base / c[key])
                for lst in (c.get("local_sources") or {}).values():
                    files.extend(base / f for f in lst)
        for f in files:
            try:
                out[str(f)] = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
            except OSError:
                out[str(f)] = "ABSENT"
    return out


def reports(registry):
    """Yield (label, report_text) for every configured check."""
    for proj in registry["projects"]:
        name = proj["name"]
        rec = Path(proj["records"]).expanduser()
        if rec.exists():
            yield f"{name}::verify", run([str(HERE / "verify_provenance.py"), str(rec)])
        else:
            yield f"{name}::verify", f"MISSING REGISTER {rec}\n"
        cfg = proj.get("config")
        if cfg:
            cfgp = Path(cfg).expanduser()
            if cfgp.exists():
                yield f"{name}::rounding", run(
                    [str(HERE / "check_rounding.py"), "--config", str(cfgp), "--unmatched"])
            else:
                yield f"{name}::rounding", f"MISSING CONFIG {cfgp}\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    ap.add_argument("--snapdir", default=str(DEFAULT_SNAPDIR))
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    reg_path = Path(a.registry).expanduser()
    if not reg_path.exists():
        print(f"no registry at {reg_path}\n"
              f"copy corpus_gate.example.json to corpus_gate.local.json and point it at your "
              f"own registers. It is local by design: it names confidential paths.",
              file=sys.stderr)
        return 2
    registry = json.loads(reg_path.read_text(encoding="utf-8"))
    snap = Path(a.snapdir).expanduser()

    if a.snapshot:
        snap.mkdir(parents=True, exist_ok=True)
        (snap / "_inputs.json").write_text(
            json.dumps(fingerprint(registry), indent=2, sort_keys=True), encoding="utf-8")
        n = 0
        for label, text in reports(registry):
            (snap / (label.replace("::", "__") + ".txt")).write_text(text, encoding="utf-8")
            n += 1
            print(f"  snapshot  {label}  ({len(text.splitlines())} lines)")
        print(f"\n{n} report(s) snapshotted to {snap}")
        return 0

    if not a.check:
        print(__doc__)
        return 2

    if not snap.exists():
        print(f"no snapshot at {snap}; run --snapshot first", file=sys.stderr)
        return 2

    # Inputs first. If the corpus moved, the output diff below says nothing about the code.
    fp_now = fingerprint(registry)
    fp_file = snap / "_inputs.json"
    moved = []
    if fp_file.exists():
        fp_old = json.loads(fp_file.read_text(encoding="utf-8"))
        moved = sorted(k for k in set(fp_old) | set(fp_now)
                       if fp_old.get(k) != fp_now.get(k))
    if moved:
        print(f"  INPUTS CHANGED since the snapshot ({len(moved)} file(s)):")
        for k in moved[:10]:
            print(f"     {Path(k).name}")
        if len(moved) > 10:
            print(f"     ... and {len(moved) - 10} more")
        print("  The corpus itself moved, so any report difference below is NOT evidence about\n"
              "  the code. Re-snapshot on the current corpus, then make the code change.\n")

    changed, ok = [], 0
    for label, text in reports(registry):
        f = snap / (label.replace("::", "__") + ".txt")
        if not f.exists():
            changed.append((label, ["(no baseline for this report; run --snapshot)"]))
            continue
        before = f.read_text(encoding="utf-8")
        if before == text:
            ok += 1
            print(f"  ok        {label}  identical to baseline")
        else:
            d = list(difflib.unified_diff(before.splitlines(), text.splitlines(),
                                          "baseline", "now", lineterm="", n=1))
            changed.append((label, d))
            print(f"  CHANGED   {label}  ({sum(1 for x in d if x.startswith(('+','-')) and not x.startswith(('+++','---')))} lines differ)")

    if changed:
        print(f"\n{len(changed)} report(s) changed, {ok} identical.")
        for label, d in changed:
            print(f"\n--- {label} ---")
            for line in (d if a.verbose else d[:40]):
                print("   " + line)
            if not a.verbose and len(d) > 40:
                print(f"   ... {len(d) - 40} more lines, re-run with --verbose")
        print("\nEvery changed line is either a newly caught defect or a regression. Explain\n"
              "each one before accepting it; that is the whole point of the gate. To accept,\n"
              "re-run --snapshot.")
        return 1

    if moved:
        print(f"\nall {ok} report(s) identical, but {len(moved)} input file(s) changed: the "
              f"match is not meaningful. Re-snapshot.")
        return 1
    print(f"\nall {ok} report(s) identical to baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
