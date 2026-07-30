# Validation plan

Validation is in three layers. Layers 1 and 2 need no credentials and no live
n8n. Layer 3 is a manual run in the n8n UI, because the n8n public REST API can
create and import workflows but does not execute an inactive workflow, and we keep
these inactive until you have reviewed them.

## Layer 1: structural (offline, no keys)

Run the bundled checker (or import into n8n, which performs the same parse):

- Every workflow JSON parses.
- Every connection references a node that exists.
- Every node has `id`, `name`, `type`, `typeVersion`, `position`.
- Credentials are placeholders (`REPLACE_WITH_*`), not real ids.
- `active` is `false`.
- The `Structured Output Parser` `inputSchema` (A2/A3) is valid JSON Schema and
  matches `config/output-schema.json`.

```bash
python tools/validate_workflows.py   # exits non-zero on any failure
```

## Layer 2: enrichment contract + node logic (offline)

Behavioral test of the real Code-node `jsCode` through a minimal n8n mock (needs
Node.js): drives Set Config -> Fetch Notes -> Resolve -> (injected enrichment) ->
Format (the template renderer) -> ATS lookup/note builders (both providers) ->
dry-run preview, and asserts the rendered doc and request shapes.

```bash
node tools/test_logic.js   # exits non-zero on any failure
```

This tests the deterministic logic (parsing, rendering, request building). It does
NOT test the live model call or the Google/Slack/ATS HTTP I/O; those are Layer 3.

Additional offline contract checks:

- `config/output-schema.json` is valid JSON Schema (draft-07).
- `config/standard-questions.json` parses and every question has `id`, `question`.
- A sample enriched object (in `tools/sample-enriched.json`) validates against the
  schema, proving FORMAT has a real object to render.
- The A3 ATS request builders produce the correct shape for both providers without
  sending (asserted against the documented Ashby and Lever contracts):
  - Lever add note: `POST https://api.lever.co/v1/opportunities/{id}/notes` body
    `{"value": "..."}`.
  - Ashby add note: `POST https://api.ashbyhq.com/candidate.createNote` body
    `{"candidateId": "...", "note": "..."}`.

## Layer 3: live smoke test (manual, in the n8n UI)

For each archetype, with `TEST_MODE=true`:

1. Open the imported workflow, click Execute Workflow (manual trigger).
2. Confirm SOURCE loads the sample notes.
3. Confirm RESOLVE emits an identity object (A2/A3).
4. Confirm ENRICH returns schema-valid structured output (A2/A3). If the model is
   unreachable, confirm `enrichment_level=off` still produces a formatted result.
5. Confirm FORMAT renders the template into `doc_body_markdown`.
6. Confirm the SINK is skipped and the Dry Run Preview shows the intended writes.
   For A3, confirm the preview shows the exact ATS request (URL, method, body) for
   the selected `ats_provider`, with nothing sent.

Then, when you are ready to go live on one candidate:

7. Set real ids and credentials, set `TEST_MODE=false`, and run once against a
   sandbox ATS candidate (Ashby/Lever sandbox). Confirm the doc is created and one
   note lands on the sandbox candidate. Only then activate the production trigger.

## Exit criteria

- Layers 1 and 2 pass for all three archetypes.
- Layer 3 steps 1 to 6 pass for all three in TEST_MODE.
- All three remain inactive until you activate them.
- No credential material is committed.
