#!/usr/bin/env python3
"""Resolve the analyst prompt template into a ready-to-paste system prompt.

config/analyst-prompt.md is the genericized source of truth: every
company-specific fact is a {{placeholder}}. This script resolves those from
config/company-profile.json, renders config/legal-reference.json into the
LEGAL REFERENCE section (federal categories always, state categories and the
matching state supplement gated on jurisdiction.state), and writes the result
to build/analyst-prompt.md.

Edit config/company-profile.json (not the prompt), then re-run:
    python tools/render_prompt.py
Then validate:  python tools/validate_workflows.py

    --check   exit non-zero if the committed build is stale or any
              placeholder is left unresolved (used by CI)

No third-party deps.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
OUT = ROOT / "build" / "analyst-prompt.md"

PROMPT_SRC = CONFIG / "analyst-prompt.md"
PROFILE_SRC = CONFIG / "company-profile.json"
LEGAL_SRC = CONFIG / "legal-reference.json"

BANNER = (
    "<!-- GENERATED FILE — do not edit.\n"
    "     Source:  config/analyst-prompt.md + config/company-profile.json + config/legal-reference.json\n"
    "     Rebuild: python tools/render_prompt.py\n"
    "     Paste the body below into the ENRICH agent's system prompt. -->\n\n"
)

PLACEHOLDER = re.compile(r"\{\{([a-z_.]+)\}\}")
HEADER_COMMENT = re.compile(r"\A<!--.*?-->\s*", re.DOTALL)


def shown(path: Path) -> str:
    """Repo-relative when it can be, absolute otherwise (--out may point anywhere)."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


# ---- derived clauses ------------------------------------------------------
# Four placeholders are not raw profile fields — they are sentences composed
# from several fields, so the prompt reads as prose whatever the profile says.

def negotiable_clause(profile) -> str:
    return (
        "This policy is not negotiable."
        if profile["work_policy"].get("negotiable") is False
        else "There is some flexibility in this policy; record any conditions the candidate raises."
    )


def regulatory_clause(profile) -> str:
    regimes = profile.get("regulatory", {}).get("regimes") or []
    if not regimes:
        # The strict default. See docs/COMPLIANCE.md — with no regime in play
        # there is no lawful route to a citizenship-adjacent question at all.
        return (
            "No export-control, clearance, or citizenship regime applies to this role. "
            "There is therefore no lawful basis for any citizenship, national-origin, or "
            "immigration-status question beyond general work authorization and sponsorship."
        )
    listed = ", ".join(regimes)
    return (
        f"This role is subject to {listed}. A narrowly-scoped, counsel-scripted legal-status "
        "question (for example U.S.-person status as defined by the applicable regime) is "
        "permitted and is not a national-origin question. Everything adjacent to it — origin, "
        "ancestry, first language, accent — remains prohibited."
    )


def jurisdiction_clause(profile) -> str:
    j = profile.get("jurisdiction", {})
    country = j.get("country") or "US"
    federal = ", ".join(j.get("federal_framework") or []) or "the applicable federal framework"
    state = j.get("state")
    if not state:
        return f"Screening is governed by {country} federal law: {federal}."
    state_fw = ", ".join(j.get("state_framework") or []) or "the applicable state framework"
    return (
        f"Screening is governed by {country} federal law ({federal}) and by {state} state law "
        f"({state_fw}). Where the two differ, apply the stricter of the two."
    )


def salary_history_clause(profile) -> str:
    return (
        "Salary history is prohibited: never record what the candidate currently or previously "
        "earned, even if they volunteered it — route any such figure to compliance.violations."
        if profile.get("jurisdiction", {}).get("salary_history_ban")
        else "Record forward-looking compensation expectations only; salary history is out of scope."
    )


# ---- legal reference ------------------------------------------------------

def render_legal_reference(legal, profile) -> str:
    """Markdown rendering of the categories that apply in this jurisdiction."""
    state = profile.get("jurisdiction", {}).get("state")
    lines: list[str] = []

    for cat in legal["categories"]:
        lines.append(f"### {cat['label']}")
        lines.append("")
        lines.append(f"- **Category id:** `{cat['id']}`  ·  **Scope:** {cat['scope']}")
        if cat.get("framework"):
            lines.append(f"- **Frameworks:** {', '.join(cat['framework'])}")
        for item in cat.get("unacceptable") or []:
            lines.append(f"- **Never ask / never record:** {item}")
        for item in cat.get("acceptable") or []:
            lines.append(f"- **Acceptable:** {item}")
        if not cat.get("acceptable"):
            lines.append("- **Acceptable:** nothing in this category is role-relevant.")
        if cat.get("note"):
            lines.append(f"- **Note:** {cat['note']}")
        lines.append("")

    supplement = (legal.get("state_supplements") or {}).get(state) if state else None
    if supplement:
        lines.append(f"### {state} supplement")
        lines.append("")
        if supplement.get("framework"):
            lines.append(f"- **Frameworks:** {', '.join(supplement['framework'])}")
        for item in supplement.get("adds") or []:
            lines.append(f"- {item}")
        lines.append("")
    elif state:
        # A state was named but no supplement ships for it. Say so in the prompt
        # rather than silently falling back to federal-only.
        lines.append(f"### {state} supplement")
        lines.append("")
        lines.append(
            f"- No {state} supplement ships with this pack. Federal rules above are the floor, "
            "not the ceiling — have counsel supply the state overlay before production use."
        )
        lines.append("")

    ai = legal.get("ai_specific") or {}
    if ai:
        lines.append("### AI in the hiring loop")
        lines.append("")
        if ai.get("note"):
            lines.append(f"- {ai['note']}")
        for item in ai.get("obligations") or []:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---- resolution -----------------------------------------------------------

# Fields the prompt cannot be rendered without. Checked up front so an operator
# who trims company-profile.json gets a pointer, not a KeyError traceback.
REQUIRED_PROFILE_FIELDS = (
    "company.name", "company.industry", "company.location", "company.context",
    "work_policy.label", "work_policy.detail",
    "report.analyst_persona", "report.recommendation_placeholder",
)


def check_profile(profile) -> list[str]:
    missing = []
    for dotted in REQUIRED_PROFILE_FIELDS:
        section, field = dotted.split(".")
        if not (profile.get(section) or {}).get(field):
            missing.append(dotted)
    return missing


def build_values(profile, legal) -> dict[str, str]:
    company = profile["company"]
    work = profile["work_policy"]
    report = profile["report"]
    return {
        "company.name": company["name"],
        "company.short_name": company.get("short_name") or company["name"],
        "company.industry": company["industry"],
        "company.location": company["location"],
        "company.context": company["context"],
        "work_policy.label": work["label"],
        "work_policy.detail": work["detail"],
        "work_policy.negotiable_clause": negotiable_clause(profile),
        "regulatory.clause": regulatory_clause(profile),
        "jurisdiction.clause": jurisdiction_clause(profile),
        "jurisdiction.salary_history_clause": salary_history_clause(profile),
        "report.analyst_persona": report["analyst_persona"],
        "report.recommendation_placeholder": report["recommendation_placeholder"],
        "legal_reference": render_legal_reference(legal, profile),
    }


def render(prompt_src: str, values: dict[str, str]) -> tuple[str, list[str]]:
    """Substitute every placeholder; return the body plus any that had no value."""
    missing: list[str] = []
    body = HEADER_COMMENT.sub("", prompt_src)

    def sub(match):
        key = match.group(1)
        if key not in values:
            missing.append(key)
            return match.group(0)
        return values[key]

    return PLACEHOLDER.sub(sub, body), sorted(set(missing))


def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve the analyst prompt template.")
    ap.add_argument("-o", "--out", default=str(OUT), help=f"output path (default {shown(OUT)})")
    ap.add_argument("--check", action="store_true",
                    help="verify the committed build is current; write nothing")
    args = ap.parse_args()

    profile = json.loads(PROFILE_SRC.read_text())
    legal = json.loads(LEGAL_SRC.read_text())

    absent = check_profile(profile)
    if absent:
        print("error: config/company-profile.json is missing required field(s): "
              + ", ".join(absent), file=sys.stderr)
        return 1

    body, missing = render(PROMPT_SRC.read_text(), build_values(profile, legal))

    if missing:
        print(f"error: {len(missing)} placeholder(s) have no value in "
              f"config/company-profile.json: {', '.join(missing)}", file=sys.stderr)
        return 1

    leftover = sorted(set(PLACEHOLDER.findall(body)))
    if leftover:
        print(f"error: unresolved placeholder(s) survived rendering: {', '.join(leftover)}",
              file=sys.stderr)
        return 1

    out_path = Path(args.out)
    rendered = BANNER + body

    if args.check:
        if not out_path.exists():
            print(f"error: {shown(out_path)} is missing — run python tools/render_prompt.py",
                  file=sys.stderr)
            return 1
        if out_path.read_text() != rendered:
            print(f"error: {shown(out_path)} is stale — run python tools/render_prompt.py",
                  file=sys.stderr)
            return 1
        print(f"{shown(out_path)} is current ({len(body.splitlines())} lines)")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered)
    print(f"wrote {shown(out_path)}: {len(body.splitlines())} lines, "
          f"{len(build_values(profile, legal))} placeholders resolved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
