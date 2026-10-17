#!/usr/bin/env python3
"""PreToolUse hook: fire the sourcing rule the moment a reference source is opened.

An instruction in a project file is a reminder that competes with everything else in context.
This fires at the exact moment it matters, when a source is actually being read, which is the
only point at which "record it now" is still possible rather than retrospective.

Deliberately NON-BLOCKING. A hook that refused reads would make exploration impossible and
would be routed around within a day. The enforcement that bites is the coverage gate, which
fails the build when a value has no record, no author reason and no declaration. This hook
exists so nobody walks into that gate by accident.

Wire it up in ~/.claude/settings.json:

    "hooks": {
      "PreToolUse": [
        {"matcher": "Read|WebFetch|Bash",
         "hooks": [{"type": "command",
                    "command": "python3 ~/.claude/skills/sourced-writing/scripts/source_read_hook.py"}]}
      ]
    }
"""
from __future__ import annotations

import json
import os
import re
import sys

# Domains that publish the kind of document a value gets taken from. Deliberately broad:
# a false positive costs one line of reminder, a false negative costs a lost record.
DOMAINS = re.compile(
    r"(doi\.org|pubmed|pmc\.ncbi|ncbi\.nlm\.nih\.gov|clinicaltrials\.gov|"
    r"fda\.gov|accessdata\.fda|ema\.europa\.eu|dailymed|medicines\.org\.uk|"
    r"who\.int|cochrane|embase|scopus|webofscience|sciencedirect|springer|"
    r"nature\.com|wiley|onlinelibrary|nejm\.org|thelancet|jamanetwork|bmj\.com|"
    r"ascopubs|aacrjournals|biorxiv|medrxiv|osf\.io|zenodo)", re.I)

# A local path that looks like a held source rather than working code.
#
# `text/`, `extracts/` and `corpus/` matter as much as `sources/`. A project that
# downloads PDFs into sources/ but writes the extracted plain text to text/ will
# take every quote from the extract, so a hook watching only sources/ stays
# silent through the entire job. That happened on a real review. A corpus
# directory is a held source whatever it is named.
PATHS = re.compile(
    r"(^|/)(sources?|references?|literature|labels?|sourcedocs|text|extracts?|corpus|"
    r"transcripts?|minutes|harvest)/", re.I)

# Document management and collaboration systems are sources too. In regulated
# industry a value arrives from a company document repository far more often
# than from a journal, and reading one through its API looks nothing like
# reading a PDF.
#
# Site-specific hostnames belong in the environment, not in this file: set
# SOURCED_WRITING_SOURCE_HOSTS to a comma-separated list (for example an
# intranet search host and a document-viewer host) and they are matched too.
INTERNAL = re.compile(
    r"(veevavault\.com|sharepoint\.com|sharepoint-df\.com|box\.com|egnyte\.com|"
    r"confluence|docs\.google\.com|drive\.google\.com|"
    r"googleapis\.com/(?:drive|docs|sheets|slides))", re.I)

_extra = [h.strip() for h in os.environ.get("SOURCED_WRITING_SOURCE_HOSTS", "").split(",")
          if h.strip()]
EXTRA = re.compile("|".join(re.escape(h) for h in _extra), re.I) if _extra else None

REMINDER = (
    "sourced-writing: a value leaving this source needs a provenance record written in the "
    "SAME action, not later. Paste the quote verbatim, put the source's own unrounded figure "
    "in source_value, and give a locator someone can follow. If no quote can be pasted, the "
    "number does not go in."
)


def target(tool: str, ti: dict) -> str:
    if tool == "Read":
        return str(ti.get("file_path", ""))
    if tool == "WebFetch":
        return str(ti.get("url", ""))
    if tool == "Bash":
        return str(ti.get("command", ""))
    return ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0                      # never break the tool call over a hook
    tool = payload.get("tool_name", "")
    t = target(tool, payload.get("tool_input", {}) or {})
    if not t:
        return 0
    if (DOMAINS.search(t) or PATHS.search(t) or INTERNAL.search(t)
            or (EXTRA is not None and EXTRA.search(t))):
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": REMINDER,
            }
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
