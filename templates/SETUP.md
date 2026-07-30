# n8n templates: setup

Cloud-safe exports. Credentials and instance ids are `REPLACE_WITH_*` /
`<PLACEHOLDER>`. Each archetype is **self-contained** (one file, no sub-workflows),
so there are no workflow-id references to rewire on import.

## Import

1. n8n -> Workflows -> Import from File. Pick one archetype:
   - `A1-minimal-screen-to-doc.template.json`
   - `A2-enriched-cemented-questions.template.json`
   - `A3-endtoend-ats.template.json`
2. Create the credentials below and attach them to the nodes that ask (n8n shows a
   warning icon on nodes needing a credential; select yours by name).
3. Set your ids in the `Set Config` node (see below).
4. Keep `TEST_MODE=true` and run once (Execute Workflow) to preview end to end.

## Credentials to create (n8n -> Credentials)

| Credential type | Used by | Archetypes |
|---|---|---|
| `googleDocsOAuth2Api` | Create Doc, Insert Doc Body | A1, A2, A3 |
| `googleSheetsOAuth2Api` | Append Screen Row, Log Error to Sheet | A1, A2, A3 |
| `slackOAuth2Api` | Slack Notify, Alert Error to Slack | A1, A2, A3 |
| `anthropicApi` | Enrich Model | A2, A3 |
| `httpBasicAuth` (ATS key as username, blank password) | ATS Find Candidate, ATS Add Note | A3 |

For A3 you create one `httpBasicAuth` credential holding your Ashby **or** Lever
API key (key = username, password blank). See `docs/integrations/ashby.md`
and `docs/integrations/lever.md`.

## Set Config fields

| Field | Set to |
|---|---|
| `TEST_MODE` | `true` while testing; `false` to write for real |
| `USE_MODEL` | `true` to run enrichment (A2/A3); `false` for deterministic formatting |
| `company_context` | A short description of your company/role for the enrichment prompt |
| `sample_notes` | Fictional notes used only when TEST_MODE and no real trigger fired |
| `candidate_*` | Test candidate identity; production comes from SOURCE/RESOLVE |
| `drive_folder_id` | Google Drive folder id where the screen doc is created |
| `sheet_id` / `sheet_tab` | Sheet id and tab name for the log row (tab defaults to `Screens`) |
| `standard_questions` | The cemented questions (baked from config/standard-questions.json) |
| `doc_template` | The output template (baked from config/screen-doc.template.md) |
| `ats_provider` | `ashby` or `lever` (A3 only) |

## Per-workflow

| Template | Credentials | Nodes |
|---|---|---|
| A1-minimal-screen-to-doc | googleDocsOAuth2Api, googleSheetsOAuth2Api, slackOAuth2Api | 14 |
| A2-enriched-cemented-questions | + anthropicApi | 20 |
| A3-endtoend-ats | + httpBasicAuth (ATS) | 26 |

## Before activating

- Replace the Manual/Test trigger with your production SOURCE trigger (Gmail on the
  notetaker email, Drive/OneDrive folder watch, etc). See `docs/CUSTOMIZE.md`.
- Create the target Sheet with a `Screens` tab and an `Error Log` tab.
- Run one live pass against a sandbox ATS candidate (A3) with `TEST_MODE=false`.
- These templates are regenerated from `config/` by `tools/build_workflows.py`.
  If you edit the questions, schema, or template files, re-run it (or edit
  `Set Config` / the parser node directly in n8n).
