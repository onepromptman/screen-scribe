#!/usr/bin/env python3
"""Deterministic builder for the three Screen Scribe archetypes.

Bakes the single-source config files (standard-questions, output-schema, doc
template) into n8n workflow JSON. A2 = A1 + RESOLVE + ENRICH.
A3 = A2 + ATS lookup + ATS note sink. Self-contained per archetype (one file).

Edit the config/ files (or this script), then re-run:  python tools/build_workflows.py
Then validate:  python tools/validate_workflows.py

No third-party deps.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
OUT = ROOT / "templates"

# ---- single-source config -------------------------------------------------
STANDARD_QUESTIONS = json.loads((CONFIG / "standard-questions.json").read_text())["questions"]
OUTPUT_SCHEMA = json.loads((CONFIG / "output-schema.json").read_text())
DOC_TEMPLATE = (CONFIG / "screen-doc.template.md").read_text()

CRED = {
    "anthropic": {"anthropicApi": {"id": "REPLACE_WITH_ANTHROPICAPI_CREDENTIAL_ID", "name": "Anthropic account"}},
    "docs": {"googleDocsOAuth2Api": {"id": "REPLACE_WITH_GOOGLEDOCSOAUTH2API_CREDENTIAL_ID", "name": "Google Docs OAuth2 API"}},
    "sheets": {"googleSheetsOAuth2Api": {"id": "REPLACE_WITH_GOOGLESHEETSOAUTH2API_CREDENTIAL_ID", "name": "Google Sheets OAuth2 API"}},
    "slack": {"slackOAuth2Api": {"id": "REPLACE_WITH_SLACKOAUTH2API_CREDENTIAL_ID", "name": "Slack OAuth2 API"}},
    "ats": {"httpBasicAuth": {"id": "REPLACE_WITH_ATS_HTTPBASICAUTH_CREDENTIAL_ID", "name": "ATS Basic Auth"}},
}

SAMPLE_NOTES = (
    "Recruiter screen with Jordan Rivera for the Senior Backend Engineer role.\n"
    "Jordan is currently a backend engineer at a fintech scale-up, 6 years experience, "
    "mostly Python and Go, owns their team's payments service.\n"
    "Motivated by wanting more ownership and a mission they care about; heard about us from a former colleague.\n"
    "Comp expectation around 210k base, flexible on equity. Available in 4 weeks (standard notice).\n"
    "Based in Austin, open to hybrid in SF two weeks a month, no visa needs.\n"
    "Strong on system design in the conversation, walked through a real incident well.\n"
    "One concern: has not led a team formally, though has mentored two juniors.\n"
)


def nid(name: str) -> str:
    return hashlib.md5(name.encode()).hexdigest()


def node(name, ntype, params, tv, x, y, creds=None, extra=None):
    n = {
        "parameters": params,
        "id": nid(name),
        "name": name,
        "type": ntype,
        "typeVersion": tv,
        "position": [x, y],
    }
    if creds:
        n["credentials"] = creds
    if extra:
        n.update(extra)
    return n


# ---- reusable JS ----------------------------------------------------------
JS_FETCH_NOTES = """// SOURCE: load the screen notes + meeting metadata.
// Production: replace the Manual/Test trigger with a Gmail/Drive/OneDrive
// trigger and point `incoming` at its output. TEST_MODE uses the pasted sample.
const cfg = $('Set Config').first().json;
const incoming = $input.first().json || {};
const notes_text = (incoming.notes_text || cfg.sample_notes || '').toString();
return { json: {
  ...cfg,
  notes_text,
  meeting_title: incoming.meeting_title || (cfg.candidate_name + ' screen'),
  meeting_time: incoming.meeting_time || $now.toISO(),
  attendees: incoming.attendees || [],
} };
"""

JS_RESOLVE = """// RESOLVE: derive candidate identity + enrichment inputs.
// Production: parse the calendar invite attendee email / LinkedIn, or read a
// resume dropped in Slack, and append to candidate.resume_text.
const j = $input.first().json;
const candidate = {
  name: j.candidate_name || '',
  email: (j.candidate_email || '').toLowerCase().trim(),
  role: j.candidate_role || '',
  linkedin_url: j.candidate_linkedin || null,
  resume_text: j.candidate_resume_text || null,
  resume_link: j.candidate_resume_link || null,
};
return { json: { ...j, candidate } };
"""

JS_PARSE_ENRICH = """// Normalize the agent's structured output into `enriched`.
const item = $input.first().json;
let out = item.output;
if (typeof out === 'string') {
  let raw = out.trim().replace(/^```(?:json)?\\s*/i, '').replace(/```\\s*$/, '').trim();
  const m = raw.match(/\\{[\\s\\S]*\\}/);
  out = JSON.parse(m ? m[0] : raw);
}
const ctx = $('Resolve Context (RESOLVE)').first().json;
out.candidate = out.candidate || ctx.candidate;
out.screen_date = out.screen_date || $now.toISODate();
return { json: { ...ctx, enriched: out } };
"""

JS_FORMAT = """// FORMAT: render the structured output through the doc template (mustache-lite).
const cfg = $('Set Config').first().json;
let data = ($input.first().json || {}).enriched || null;
if (!data) {
  // A1 / USE_MODEL=false: deterministic minimal object from the notes.
  const j = $input.first().json;
  const candidate = j.candidate || {
    name: cfg.candidate_name, email: cfg.candidate_email, role: cfg.candidate_role,
    linkedin_url: cfg.candidate_linkedin, resume_link: null,
  };
  data = {
    candidate,
    screen_date: $now.toISODate(),
    summary: (j.notes_text || '').split('\\n').filter(Boolean).slice(0, 3).join(' '),
    standard_answers: [], strengths: [], concerns: [],
    recommendation: 'maybe', follow_up_questions: [],
    next_steps: 'Reviewer to add next steps.', raw_notes: j.notes_text,
  };
}
function render(tpl, d) {
  tpl = tpl.replace(/{{#([\\w.]+)}}([\\s\\S]*?){{\\/\\1}}/g, function (m, key, inner) {
    const val = key.split('.').reduce(function (o, k) { return o == null ? undefined : o[k]; }, d);
    if (Array.isArray(val)) {
      return val.map(function (it) {
        if (it !== null && typeof it === 'object') return render(inner, it);
        return inner.replace(/{{\\.}}/g, it == null ? '' : String(it));
      }).join('');
    }
    if (val) return render(inner, d);
    return '';
  });
  tpl = tpl.replace(/{{([\\w.]+)}}/g, function (m, key) {
    const val = key.split('.').reduce(function (o, k) { return o == null ? undefined : o[k]; }, d);
    return val == null ? '' : String(val);
  });
  return tpl;
}
const tpl = cfg.doc_template || '# {{candidate.name}}\\n\\n{{summary}}';
let body;
try { body = render(tpl, data); }
catch (e) { body = '# ' + ((data.candidate || {}).name || 'Screen') + '\\n\\n' + (data.summary || '') + '\\n\\n' + (data.raw_notes || ''); }
const cand = data.candidate || {};
const title = (cand.name || 'Candidate') + ' - ' + (cand.role || 'Screen') + ' - Recruiter Screen';
return { json: { ...($input.first().json), doc_title: title, doc_body_markdown: body, screen_output: data } };
"""

JS_DRYRUN_A12 = """// TEST_MODE preview: show what WOULD be written; nothing is sent.
const j = $input.first().json;
return { json: {
  dry_run: true,
  would_create_doc: { title: j.doc_title, folder_id: j.drive_folder_id },
  would_insert_body_chars: (j.doc_body_markdown || '').length,
  would_append_sheet_row: {
    sheet_id: j.sheet_id, tab: j.sheet_tab,
    candidate: (j.screen_output && j.screen_output.candidate) || null,
    recommendation: j.screen_output && j.screen_output.recommendation,
  },
  doc_body_preview: (j.doc_body_markdown || '').slice(0, 1200),
} };
"""

JS_BUILD_ATS_LOOKUP = """// A3 RESOLVE via ATS: build the provider-specific candidate lookup request.
const j = $input.first().json;
const cfg = $('Set Config').first().json;
const provider = (cfg.ats_provider || 'ashby').toLowerCase();
const email = ((j.candidate && j.candidate.email) || cfg.candidate_email || '').trim();
let req;
if (provider === 'lever') {
  req = { method: 'GET', url: 'https://api.lever.co/v1/opportunities?email=' + encodeURIComponent(email), body: {} };
} else {
  req = { method: 'POST', url: 'https://api.ashbyhq.com/candidate.search', body: { email } };
}
return { json: { ...j, ats_provider: provider, ats_lookup: req } };
"""

JS_PARSE_CANDIDATE = """// Pull the candidate/opportunity id out of the ATS lookup response.
const resp = $input.first().json || {};
const arr = resp.results || resp.data || [];
const cid = (Array.isArray(arr) && arr.length) ? arr[0].id : null;
const prior = $('Build ATS Lookup').first().json;
return { json: { ...prior, ats_candidate_id: cid } };
"""

JS_BUILD_ATS_NOTE = """// A3 SINK: build the provider-specific add-note request (normalized add_note contract).
const j = $input.first().json;
const provider = j.ats_provider;
const cid = j.ats_candidate_id;
const fmt = $('Format Screen (FORMAT)').first().json;
const created = $('Create Doc').first().json || {};
const docLink = created.id ? ('https://docs.google.com/document/d/' + created.id + '/edit') : '';
const summary = (fmt.screen_output && fmt.screen_output.summary) ? fmt.screen_output.summary : '';
const noteText = summary + (docLink ? ('\\n\\nFull screen: ' + docLink) : '');
let req;
if (provider === 'lever') {
  req = { method: 'POST', url: 'https://api.lever.co/v1/opportunities/' + encodeURIComponent(cid) + '/notes', body: { value: noteText } };
} else {
  req = { method: 'POST', url: 'https://api.ashbyhq.com/candidate.createNote', body: { candidateId: cid, note: noteText, sendNotifications: false } };
}
return { json: { ...j, ats_note: req, ats_note_text: noteText } };
"""

JS_DRYRUN_A3 = """// TEST_MODE preview (A3): show the doc, sheet, AND ats requests; nothing sent.
const j = $input.first().json;
const cfg = $('Set Config').first().json;
const provider = (cfg.ats_provider || 'ashby').toLowerCase();
const email = ((j.candidate && j.candidate.email) || cfg.candidate_email || '').trim();
const summary = (j.screen_output && j.screen_output.summary) || '';
const lookup = provider === 'lever'
  ? { method: 'GET', url: 'https://api.lever.co/v1/opportunities?email=' + encodeURIComponent(email) }
  : { method: 'POST', url: 'https://api.ashbyhq.com/candidate.search', body: { email } };
const note = provider === 'lever'
  ? { method: 'POST', url: 'https://api.lever.co/v1/opportunities/{id}/notes', body: { value: summary + ' (+doc link)' } }
  : { method: 'POST', url: 'https://api.ashbyhq.com/candidate.createNote', body: { candidateId: '{id}', note: summary + ' (+doc link)', sendNotifications: false } };
return { json: {
  dry_run: true, ats_provider: provider,
  would_create_doc: { title: j.doc_title, folder_id: j.drive_folder_id },
  would_ats_lookup: lookup,
  would_ats_add_note: note,
  doc_body_preview: (j.doc_body_markdown || '').slice(0, 1200),
} };
"""

ENRICH_SYSTEM = (
    "You are a recruiting screen writer. You are given the notes from a recruiter "
    "screen, some candidate context, and a fixed list of standard screen questions. "
    "Your job is to answer EVERY standard question from the notes and context, then "
    "produce an overall read.\n\n"
    "Rules:\n"
    "- Answer strictly from the notes and context. Do not invent facts. If the notes "
    "do not cover a question, set the answer to 'Not covered in the screen' and "
    "confidence to 'low'.\n"
    "- Keep the same question ids and order as given.\n"
    "- The recommendation tier is the source of truth; the score is just a sort key.\n"
    "- Be concise and specific. A hiring manager should be able to skim the summary.\n"
    "- Output must match the provided JSON schema exactly."
)

ENRICH_TEXT = (
    "=COMPANY CONTEXT:\n{{ $json.company_context }}\n\n"
    "ROLE: {{ $json.candidate.role }}\n"
    "CANDIDATE: {{ $json.candidate.name }} <{{ $json.candidate.email }}>\n"
    "LINKEDIN: {{ $json.candidate.linkedin_url }}\n"
    "RESUME / EXTRA CONTEXT:\n{{ $json.candidate.resume_text || 'none provided' }}\n\n"
    "STANDARD QUESTIONS (answer every one, in order):\n{{ $json.standard_questions }}\n\n"
    "SCREEN NOTES:\n{{ $json.notes_text }}"
)


def set_config(archetype):
    a = [
        {"id": nid("a-testmode"), "name": "TEST_MODE", "value": True, "type": "boolean"},
        {"id": nid("a-usemodel"), "name": "USE_MODEL", "value": archetype != "A1", "type": "boolean"},
        {"id": nid("a-cc"), "name": "company_context",
         "value": "<org_name> is a placeholder company. Replace this with a short description of your company, the role's team, and what a strong hire looks like. It is injected into the enrichment prompt.",
         "type": "string"},
        {"id": nid("a-sample"), "name": "sample_notes", "value": SAMPLE_NOTES, "type": "string"},
        {"id": nid("a-cn"), "name": "candidate_name", "value": "Jordan Rivera", "type": "string"},
        {"id": nid("a-ce"), "name": "candidate_email", "value": "jordan.rivera@example.com", "type": "string"},
        {"id": nid("a-cr"), "name": "candidate_role", "value": "Senior Backend Engineer", "type": "string"},
        {"id": nid("a-cl"), "name": "candidate_linkedin", "value": "https://www.linkedin.com/in/example", "type": "string"},
        {"id": nid("a-crt"), "name": "candidate_resume_text", "value": "", "type": "string"},
        {"id": nid("a-df"), "name": "drive_folder_id", "value": "<DRIVE_FOLDER_ID>", "type": "string"},
        {"id": nid("a-sid"), "name": "sheet_id", "value": "<GOOGLE_SHEET_ID>", "type": "string"},
        {"id": nid("a-stab"), "name": "sheet_tab", "value": "Screens", "type": "string"},
        {"id": nid("a-dt"), "name": "doc_template", "value": DOC_TEMPLATE, "type": "string"},
    ]
    if archetype != "A1":
        a.append({"id": nid("a-sq"), "name": "standard_questions",
                  "value": json.dumps(STANDARD_QUESTIONS, indent=2), "type": "string"})
    if archetype == "A3":
        a.append({"id": nid("a-ats"), "name": "ats_provider", "value": "ashby", "type": "string"})
    return {"assignments": {"assignments": a}, "includeOtherFields": True, "options": {}}


def error_branch(wf_name, x0=-1200, y=760):
    nodes = [
        node("Error Trigger", "n8n-nodes-base.errorTrigger", {}, 1, x0, y),
        node("Extract Error Details", "n8n-nodes-base.set", {"assignments": {"assignments": [
            {"id": nid("e-ts"), "name": "error_timestamp", "value": "={{ $now.toISO() }}", "type": "string"},
            {"id": nid("e-wf"), "name": "workflow_name", "value": wf_name, "type": "string"},
            {"id": nid("e-node"), "name": "error_node",
             "value": "={{ ($json.execution && $json.execution.lastNodeExecuted) || 'Unknown' }}", "type": "string"},
            {"id": nid("e-msg"), "name": "error_message",
             "value": "={{ ($json.execution && $json.execution.error && $json.execution.error.message) || 'No message' }}", "type": "string"},
            {"id": nid("e-eid"), "name": "execution_id",
             "value": "={{ ($json.execution && $json.execution.id) || 'Unknown' }}", "type": "string"},
        ]}, "options": {}}, 3.4, x0 + 240, y),
        node("Log Error to Sheet", "n8n-nodes-base.googleSheets", {
            "operation": "append",
            "documentId": {"__rl": True, "mode": "id", "value": "<GOOGLE_SHEET_ID>"},
            "sheetName": {"__rl": True, "mode": "name", "value": "Error Log"},
            "columns": {"mappingMode": "defineBelow", "value": {
                "Timestamp": "={{ $json.error_timestamp }}", "Workflow": "={{ $json.workflow_name }}",
                "Error Node": "={{ $json.error_node }}", "Error Message": "={{ $json.error_message }}",
                "Execution ID": "={{ $json.execution_id }}"}, "schema": [], "matchingColumns": []},
            "options": {}}, 4.7, x0 + 480, y, creds=CRED["sheets"]),
        node("Alert Error to Slack", "n8n-nodes-base.slack", {
            "authentication": "oAuth2", "select": "channel",
            "channelId": {"__rl": True, "mode": "id", "value": "<SLACK_CHANNEL_ID>"},
            "text": "=:warning: *Screen workflow error* in {{ $json.workflow_name }} at {{ $json.error_node }}: {{ $json.error_message }}",
            "otherOptions": {}}, 2.2, x0 + 720, y, creds=CRED["slack"], extra={"webhookId": "REPLACE_WITH_WEBHOOK_ID"}),
    ]
    conns = {
        "Error Trigger": {"main": [[{"node": "Extract Error Details", "type": "main", "index": 0}]]},
        "Extract Error Details": {"main": [[{"node": "Log Error to Sheet", "type": "main", "index": 0}]]},
        "Log Error to Sheet": {"main": [[{"node": "Alert Error to Slack", "type": "main", "index": 0}]]},
    }
    return nodes, conns


def sink_doc_nodes(x, y):
    """Create Doc + Insert Body (shared by A1/A2/A3 live branch)."""
    return [
        node("Create Doc", "n8n-nodes-base.googleDocs", {
            "resource": "document", "operation": "create", "authentication": "oAuth2",
            "driveId": "myDrive",
            "folderId": "={{ $('Set Config').item.json.drive_folder_id }}",
            "title": "={{ $json.doc_title }}"}, 2, x, y, creds=CRED["docs"]),
        node("Insert Doc Body", "n8n-nodes-base.googleDocs", {
            "operation": "update", "authentication": "oAuth2",
            "documentURL": "={{ $json.id }}",
            "actionsUi": {"actionFields": [
                {"action": "insert", "text": "={{ $('Format Screen (FORMAT)').item.json.doc_body_markdown }}"}]}},
            2, x + 240, y, creds=CRED["docs"]),
    ]


def sheet_and_slack(x, y):
    return [
        node("Append Screen Row", "n8n-nodes-base.googleSheets", {
            "operation": "append",
            "documentId": {"__rl": True, "mode": "id", "value": "={{ $('Set Config').item.json.sheet_id }}"},
            "sheetName": {"__rl": True, "mode": "name", "value": "={{ $('Set Config').item.json.sheet_tab }}"},
            "columns": {"mappingMode": "defineBelow", "value": {
                "Date": "={{ $('Format Screen (FORMAT)').item.json.screen_output.screen_date }}",
                "Candidate": "={{ $('Format Screen (FORMAT)').item.json.screen_output.candidate.name }}",
                "Role": "={{ $('Format Screen (FORMAT)').item.json.screen_output.candidate.role }}",
                "Email": "={{ $('Format Screen (FORMAT)').item.json.screen_output.candidate.email }}",
                "Recommendation": "={{ $('Format Screen (FORMAT)').item.json.screen_output.recommendation }}",
                "Doc Link": "={{ 'https://docs.google.com/document/d/' + $('Create Doc').item.json.id + '/edit' }}",
                "Summary": "={{ $('Format Screen (FORMAT)').item.json.screen_output.summary }}"},
                "schema": [], "matchingColumns": []}, "options": {}}, 4.7, x, y, creds=CRED["sheets"]),
        node("Slack Notify", "n8n-nodes-base.slack", {
            "authentication": "oAuth2", "select": "channel",
            "channelId": {"__rl": True, "mode": "id", "value": "<SLACK_CHANNEL_ID>"},
            "text": "=:memo: Screen written for {{ $('Format Screen (FORMAT)').item.json.screen_output.candidate.name }} ({{ $('Format Screen (FORMAT)').item.json.screen_output.recommendation }}) - <https://docs.google.com/document/d/{{ $('Create Doc').item.json.id }}/edit|open doc>",
            "otherOptions": {}}, 2.2, x + 240, y, creds=CRED["slack"], extra={"webhookId": "REPLACE_WITH_WEBHOOK_ID"}),
    ]


def build(archetype: str) -> dict:
    wf_name = {
        "A1": "Screen Scribe - A1 Minimal (Notes to Doc)",
        "A2": "Screen Scribe - A2 Enriched (Cemented Questions)",
        "A3": "Screen Scribe - A3 End-to-end (+ ATS)",
    }[archetype]
    nodes, conns = [], {}

    def C(src, dst, so=0, di=0, typ="main"):
        conns.setdefault(src, {}).setdefault(typ, [])
        while len(conns[src][typ]) <= so:
            conns[src][typ].append([])
        conns[src][typ][so].append({"node": dst, "type": "main", "index": di})

    x = 0
    nodes.append(node("Manual / Test Trigger", "n8n-nodes-base.manualTrigger", {}, 1, x, 300)); x += 240
    nodes.append(node("Set Config", "n8n-nodes-base.set", set_config(archetype), 3.4, x, 300)); x += 240
    nodes.append(node("Fetch Notes (SOURCE)", "n8n-nodes-base.code", {"jsCode": JS_FETCH_NOTES}, 2, x, 300)); x += 240
    C("Manual / Test Trigger", "Set Config")
    C("Set Config", "Fetch Notes (SOURCE)")

    if archetype == "A1":
        nodes.append(node("Format Screen (FORMAT)", "n8n-nodes-base.code", {"jsCode": JS_FORMAT}, 2, x, 300)); x += 240
        C("Fetch Notes (SOURCE)", "Format Screen (FORMAT)")
    else:
        nodes.append(node("Resolve Context (RESOLVE)", "n8n-nodes-base.code", {"jsCode": JS_RESOLVE}, 2, x, 300)); x += 240
        C("Fetch Notes (SOURCE)", "Resolve Context (RESOLVE)")
        # Use Model? gate
        nodes.append(node("Use Model?", "n8n-nodes-base.if", {
            "conditions": {"options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
                           "conditions": [{"id": nid("c-um"), "leftValue": "={{ $json.USE_MODEL }}", "rightValue": True,
                                           "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                           "combinator": "and"}, "options": {}}, 2.3, x, 300)); x += 240
        C("Resolve Context (RESOLVE)", "Use Model?")
        # enrich chain (true branch)
        nodes.append(node("Enrich Model", "@n8n/n8n-nodes-langchain.lmChatAnthropic", {
            "model": {"__rl": True, "mode": "id", "value": "claude-sonnet-4-5-20250929"},
            "options": {"temperature": 0.2}}, 1.3, x, 520, creds=CRED["anthropic"]))
        nodes.append(node("AI Enrich", "@n8n/n8n-nodes-langchain.agent", {
            "promptType": "define", "text": ENRICH_TEXT,
            "hasOutputParser": True,
            "options": {"systemMessage": ENRICH_SYSTEM, "maxIterations": 3}}, 1.7, x, 300)); x += 240
        nodes.append(node("Structured Output Parser", "@n8n/n8n-nodes-langchain.outputParserStructured", {
            "schemaType": "manual", "inputSchema": json.dumps(OUTPUT_SCHEMA, indent=2)}, 1.3, x, 520))
        nodes.append(node("Parse Enrich Output", "n8n-nodes-base.code", {"jsCode": JS_PARSE_ENRICH}, 2, x, 300)); x += 240
        C("Use Model?", "AI Enrich", so=0)
        C("Enrich Model", "AI Enrich", typ="ai_languageModel")
        C("Structured Output Parser", "AI Enrich", typ="ai_outputParser")
        C("AI Enrich", "Parse Enrich Output")
        nodes.append(node("Format Screen (FORMAT)", "n8n-nodes-base.code", {"jsCode": JS_FORMAT}, 2, x, 300)); x += 240
        C("Parse Enrich Output", "Format Screen (FORMAT)")
        C("Use Model?", "Format Screen (FORMAT)", so=1)  # false branch -> deterministic

    # Live Writes? gate
    nodes.append(node("Live Writes?", "n8n-nodes-base.if", {
        "conditions": {"options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
                       "conditions": [{"id": nid("c-lw"), "leftValue": "={{ $('Set Config').item.json.TEST_MODE }}", "rightValue": True,
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                       "combinator": "and"}, "options": {}}, 2.3, x, 300)); x += 240
    C("Format Screen (FORMAT)", "Live Writes?")

    # TEST_MODE=true -> dry run preview (branch 0)
    dry_js = JS_DRYRUN_A3 if archetype == "A3" else JS_DRYRUN_A12
    nodes.append(node("Dry Run Preview", "n8n-nodes-base.code", {"jsCode": dry_js}, 2, x, 140))
    C("Live Writes?", "Dry Run Preview", so=0)

    # TEST_MODE=false -> live writes (branch 1)
    lx = x
    nodes += sink_doc_nodes(lx, 420)
    C("Live Writes?", "Create Doc", so=1)
    C("Create Doc", "Insert Doc Body")

    if archetype == "A3":
        # ATS lookup + note between Insert Doc Body and the sheet/slack
        nodes.append(node("Build ATS Lookup", "n8n-nodes-base.code", {"jsCode": JS_BUILD_ATS_LOOKUP}, 2, lx + 480, 420))
        nodes.append(node("ATS Find Candidate", "n8n-nodes-base.httpRequest", {
            "method": "={{ $json.ats_lookup.method }}", "url": "={{ $json.ats_lookup.url }}",
            "authentication": "genericCredentialType", "genericAuthType": "httpBasicAuth",
            "sendBody": True, "contentType": "json", "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.ats_lookup.body || {}) }}",
            "options": {"timeout": 30000}}, 4.4, lx + 720, 420, creds=CRED["ats"]))
        nodes.append(node("Parse Candidate", "n8n-nodes-base.code", {"jsCode": JS_PARSE_CANDIDATE}, 2, lx + 960, 420))
        nodes.append(node("Found in ATS?", "n8n-nodes-base.if", {
            "conditions": {"options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
                           "conditions": [{"id": nid("c-found"), "leftValue": "={{ $json.ats_candidate_id }}", "rightValue": "",
                                           "operator": {"type": "string", "operation": "exists", "singleValue": True}}],
                           "combinator": "and"}, "options": {}}, 2.3, lx + 1200, 420))
        nodes.append(node("Build ATS Note", "n8n-nodes-base.code", {"jsCode": JS_BUILD_ATS_NOTE}, 2, lx + 1440, 300))
        nodes.append(node("ATS Add Note", "n8n-nodes-base.httpRequest", {
            "method": "POST", "url": "={{ $json.ats_note.url }}",
            "authentication": "genericCredentialType", "genericAuthType": "httpBasicAuth",
            "sendBody": True, "contentType": "json", "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.ats_note.body) }}",
            "options": {"timeout": 30000}}, 4.4, lx + 1680, 300, creds=CRED["ats"]))
        sink = sheet_and_slack(lx + 1920, 420)
        nodes += sink
        C("Insert Doc Body", "Build ATS Lookup")
        C("Build ATS Lookup", "ATS Find Candidate")
        C("ATS Find Candidate", "Parse Candidate")
        C("Parse Candidate", "Found in ATS?")
        C("Found in ATS?", "Build ATS Note", so=0)   # found -> write note
        C("Build ATS Note", "ATS Add Note")
        C("ATS Add Note", "Append Screen Row")
        C("Found in ATS?", "Append Screen Row", so=1)  # not found -> skip note, still log
        C("Append Screen Row", "Slack Notify")
    else:
        sink = sheet_and_slack(lx + 480, 420)
        nodes += sink
        C("Insert Doc Body", "Append Screen Row")
        C("Append Screen Row", "Slack Notify")

    enodes, econns = error_branch(wf_name)
    nodes += enodes
    conns.update(econns)

    return {"name": wf_name, "nodes": nodes, "connections": conns, "active": False,
            "settings": {"executionOrder": "v1"}}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "A1": OUT / "A1-minimal-screen-to-doc.template.json",
        "A2": OUT / "A2-enriched-cemented-questions.template.json",
        "A3": OUT / "A3-endtoend-ats.template.json",
    }
    for a, path in files.items():
        wf = build(a)
        path.write_text(json.dumps(wf, indent=2) + "\n")
        print(f"wrote {path.name}: {len(wf['nodes'])} nodes, {len(wf['connections'])} connection groups")

    # sample enriched object for the validator (Layer 2)
    sample = {
        "candidate": {"name": "Jordan Rivera", "email": "jordan.rivera@example.com",
                      "role": "Senior Backend Engineer",
                      "linkedin_url": "https://www.linkedin.com/in/example", "resume_link": None},
        "screen_date": "2026-07-16",
        "summary": "Six years backend (Python/Go), owns a payments service. Strong system design, mission-motivated. Not covered: formal team leadership.",
        "standard_answers": [
            {"question_id": q["id"], "question": q["question"],
             "answer": "Sample answer from notes.", "evidence": None, "confidence": "medium"}
            for q in STANDARD_QUESTIONS
        ],
        "strengths": ["Strong system design", "Clear incident walkthrough"],
        "concerns": ["No formal team lead experience"],
        "recommendation": "advance",
        "score": 74,
        "follow_up_questions": ["Probe leadership scope in the next round."],
        "next_steps": "Advance to hiring manager screen.",
    }
    (ROOT / "tools" / "sample-enriched.json").write_text(json.dumps(sample, indent=2) + "\n")
    print("wrote tools/sample-enriched.json")


if __name__ == "__main__":
    main()
