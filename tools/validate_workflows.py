#!/usr/bin/env python3
"""Offline validation for Screen Scribe (Layers 1 and 2).

No third-party deps, no network, no credentials. Exits non-zero on any failure.
Run after tools/build_workflows.py.
"""
from __future__ import annotations

import json
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

    print(f"ran {checks} checks")
    if failures:
        print(f"\nFAILED ({len(failures)}):")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
