#!/usr/bin/env python3
"""Offline validation for Screen Scribe (Layers 1 and 2).

No third-party deps, no network, no credentials. Exits non-zero on any failure.
Run after tools/build_workflows.py.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
TEMPLATES = ROOT / "templates"

failures: list[str] = []
checks = 0


def ok(cond, msg):
    global checks
    checks += 1
    if not cond:
        failures.append(msg)


def load(p):
    return json.loads(Path(p).read_text())


REQUIRED_NODE_KEYS = ("parameters", "id", "name", "type", "typeVersion", "position")

TEMPLATE_FILES = {
    "A1": TEMPLATES / "A1-minimal-screen-to-doc.template.json",
    "A2": TEMPLATES / "A2-enriched-cemented-questions.template.json",
    "A3": TEMPLATES / "A3-endtoend-ats.template.json",
}


def validate_workflow(name, path):
    wf = load(path)
    node_names = {n["name"] for n in wf["nodes"]}
    ok(wf.get("active") is False, f"{name}: active must be false")
    ok(len(node_names) == len(wf["nodes"]), f"{name}: duplicate node names")

    for n in wf["nodes"]:
        for k in REQUIRED_NODE_KEYS:
            ok(k in n, f"{name}: node '{n.get('name','?')}' missing key '{k}'")
        # credentials must be placeholders, never real ids
        for cred in (n.get("credentials") or {}).values():
            cid = cred.get("id", "")
            ok(str(cid).startswith("REPLACE_WITH_"),
               f"{name}: node '{n['name']}' has non-placeholder credential id '{cid}'")

    # every connection references an existing node (source + targets)
    for src, groups in wf["connections"].items():
        ok(src in node_names, f"{name}: connection source '{src}' is not a node")
        for _typ, outs in groups.items():
            for out in outs:
                for c in out:
                    ok(c["node"] in node_names,
                       f"{name}: connection '{src}' -> missing node '{c['node']}'")

    # there is exactly one trigger + an error trigger
    types = [n["type"] for n in wf["nodes"]]
    ok("n8n-nodes-base.manualTrigger" in types, f"{name}: no manual trigger")
    ok("n8n-nodes-base.errorTrigger" in types, f"{name}: no error trigger")
    return wf


def validate_enrichment(name, wf, schema):
    parsers = [n for n in wf["nodes"] if n["type"].endswith("outputParserStructured")]
    ok(len(parsers) == 1, f"{name}: expected exactly one structured output parser")
    if parsers:
        parsed = json.loads(parsers[0]["parameters"]["inputSchema"])
        ok(parsed == schema, f"{name}: parser inputSchema does not match config/output-schema.json")


def validate_ats(name, wf):
    blob = json.dumps(wf)
    for needle in [
        "https://api.lever.co/v1/opportunities",   # lever lookup + note base
        "/notes",                                   # lever add note
        "https://api.ashbyhq.com/candidate.search", # ashby lookup
        "https://api.ashbyhq.com/candidate.createNote",  # ashby add note
        "candidateId", "\"value\"",                 # both note body shapes
    ]:
        ok(needle in blob, f"{name}: A3 missing ATS request piece: {needle}")


def validate_analyst_profile():
    """The analyst profile (config/analyst-*, company-profile, legal-reference).

    Same offline contract as the workflows: everything the docs promise is
    checked here, so a broken profile fails before it reaches a candidate.
    """
    schema = load(CONFIG / "analyst-output-schema.json")
    profile = load(CONFIG / "company-profile.json")
    legal = load(CONFIG / "legal-reference.json")

    ok(schema.get("type") == "object" and "properties" in schema,
       "analyst-output-schema.json: not an object schema")
    ok(schema.get("required") == ["candidate_info", "qualifications", "compliance"],
       "analyst-output-schema.json: unexpected required[] (renderer expects "
       "candidate_info, qualifications, compliance)")

    # company-profile is the only file an operator edits; every field the prompt
    # renderer needs must be present and non-empty.
    for section, field in (
        ("company", "name"), ("company", "industry"), ("company", "location"), ("company", "context"),
        ("work_policy", "label"), ("work_policy", "detail"),
        ("report", "analyst_persona"), ("report", "recommendation_placeholder"), ("report", "accent_color"),
    ):
        ok((profile.get(section) or {}).get(field),
           f"company-profile.json: {section}.{field} is missing or empty")
    accent = (profile.get("report") or {}).get("accent_color") or ""
    ok(len(accent) == 6 and all(c in "0123456789abcdefABCDEF" for c in accent),
       f"company-profile.json: report.accent_color must be a 6-digit hex string without '#' (got '{accent}')")

    state = (profile.get("jurisdiction") or {}).get("state")
    supplements = legal.get("state_supplements") or {}
    ok(state is None or state in supplements,
       f"company-profile.json: jurisdiction.state '{state}' has no supplement in "
       f"legal-reference.json (ships: {', '.join(sorted(supplements))})")

    # legal-reference categories are the vocabulary the scrub reports against
    ids, labels = set(), set()
    for cat in legal.get("categories") or []:
        for key in ("id", "label", "scope", "framework", "unacceptable"):
            ok(key in cat, f"legal-reference.json: category '{cat.get('id','?')}' missing '{key}'")
        ok(cat.get("scope") in ("federal", "state"),
           f"legal-reference.json: category '{cat.get('id','?')}' has unknown scope '{cat.get('scope')}'")
        ids.add(cat.get("id"))
        labels.add(cat.get("label"))
    ok(len(ids) == len(legal.get("categories") or []), "legal-reference.json: duplicate category ids")
    ok(len(labels) == len(legal.get("categories") or []), "legal-reference.json: duplicate category labels")

    # the sample report is the renderer's fixture — it must match the contract
    sample_path = ROOT / "tools" / "sample-analyst-report.json"
    ok(sample_path.exists(), "sample-analyst-report.json: missing")
    if sample_path.exists():
        sample = load(sample_path)
        for req in schema["required"]:
            ok(req in sample, f"sample-analyst-report.json: missing required key '{req}'")
        ok(sample.get("recruiter_recommendation") is None,
           "sample-analyst-report.json: recruiter_recommendation must be null — the renderer refuses otherwise")
        comp = sample.get("compliance") or {}
        if comp.get("violations"):
            ok(comp.get("scrubbed_from_analysis") is True,
               "sample-analyst-report.json: violations present but scrubbed_from_analysis is not true")
        for v in comp.get("violations") or []:
            ok(v.get("category") in labels,
               f"sample-analyst-report.json: violation category '{v.get('category')}' "
               "is not a label in legal-reference.json")

    # the built prompt must exist and be current (tools/render_prompt.py --check)
    built = ROOT / "build" / "analyst-prompt.md"
    ok(built.exists(), "build/analyst-prompt.md: missing - run python tools/render_prompt.py")
    if built.exists():
        text = built.read_text()
        leftover = sorted(set(re.findall(r"\{\{([a-z_.]+)\}\}", text)))
        ok(not leftover,
           f"build/analyst-prompt.md: unresolved placeholder(s): {', '.join(leftover)}")
        ok(profile["company"]["name"] in text,
           "build/analyst-prompt.md: stale - does not carry the current company name")
        ok("# LEGAL REFERENCE" in text and "Category id:" in text,
           "build/analyst-prompt.md: legal reference was not inlined")


def main():
    # --- Layer 2: config sanity ---
    schema = load(CONFIG / "output-schema.json")
    ok(schema.get("type") == "object" and "properties" in schema,
       "output-schema.json: not an object schema")
    ok(isinstance(schema.get("required"), list) and schema["required"],
       "output-schema.json: missing required[]")

    questions = load(CONFIG / "standard-questions.json")["questions"]
    ok(len(questions) >= 1, "standard-questions.json: no questions")
    for q in questions:
        ok("id" in q and "question" in q, f"standard-questions.json: bad entry {q}")

    template_md = (CONFIG / "screen-doc.template.md").read_text()
    ok("{{candidate.name}}" in template_md, "doc template: missing candidate.name placeholder")
    ok("{{#standard_answers}}" in template_md, "doc template: missing standard_answers section")

    # sample enriched object has all required keys
    if (ROOT / "tools" / "sample-enriched.json").exists():
        sample = load(ROOT / "tools" / "sample-enriched.json")
        for req in schema["required"]:
            ok(req in sample, f"sample-enriched.json: missing required key '{req}'")

    # --- Layer 1: each workflow ---
    for name, path in TEMPLATE_FILES.items():
        ok(path.exists(), f"{name}: template file missing ({path.name}) - run build_workflows.py")
        if not path.exists():
            continue
        wf = validate_workflow(name, path)
        if name in ("A2", "A3"):
            validate_enrichment(name, wf, schema)
        if name == "A3":
            validate_ats(name, wf)

    # --- the analyst profile (docs/ANALYST-PROFILE.md) ---
    validate_analyst_profile()

    print(f"ran {checks} checks")
    if failures:
        print(f"\nFAILED ({len(failures)}):")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
