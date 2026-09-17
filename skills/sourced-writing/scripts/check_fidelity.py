#!/usr/bin/env python3
"""Does the deliverable's clause say what its quote says?

The verification chain runs value -> quote -> document. Every link can hold while the
sentence around the value still asserts something the source does not: a direction, a cause,
a significance claim, or a population the quote never mentions. That is rephrasing, and no
amount of quote-matching detects it.

Advisory by design. Some flags are the source saying the same thing in other words elsewhere,
which is legitimate, so this produces a ranked review list rather than a verdict. A pass/fail
here would either be trivially satisfied or block constantly, and both teach people to ignore
it.

    python3 check_fidelity.py provenance_current.jsonl
    python3 check_fidelity.py provenance_current.jsonl --kind scope
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from custody import fidelity_flags  # noqa: E402

# Rough ordering of how much a flag changes the meaning of a sentence.
WEIGHT = {"causation": 4, "inference": 3, "direction": 2, "scope": 1}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("records", nargs="?", default="provenance_current.jsonl")
    ap.add_argument("--kind", help="show only one flag kind")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    p = Path(a.records)
    if not p.exists():
        print("no such file: %s" % p)
        return 2
    recs = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

    rows = []
    for r in recs:
        flags = fidelity_flags(r.get("as_printed", ""), r.get("quote", ""))
        if a.kind:
            flags = [f for f in flags if f[0] == a.kind]
        if flags:
            rows.append((sum(WEIGHT.get(k, 1) for k, _ in flags), r, flags))
    rows.sort(key=lambda x: -x[0])

    kinds = {}
    for _, _, flags in rows:
        for k, _w in flags:
            kinds[k] = kinds.get(k, 0) + 1

    print("=" * 74)
    print("fidelity review: %d of %d records carry language absent from their quote"
          % (len(rows), len(recs)))
    print("by kind: " + (", ".join("%s %d" % kv for kv in sorted(kinds.items())) or "none"))
    print("=" * 74)
    if not a.quiet:
        for score, r, flags in rows:
            print("\n  %s  ref %s   %s" % (r.get("value"), r.get("ref"),
                                           ", ".join("%s:%s" % f for f in flags)))
            print("    clause: %s" % (r.get("as_printed", "")[:150]))
            print("    quote : %s" % (r.get("quote", "")[:150]))
    print("\nNot defects. Each needs a human to decide whether the source supports the")
    print("wording elsewhere, or the sentence is claiming more than the quote does.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
