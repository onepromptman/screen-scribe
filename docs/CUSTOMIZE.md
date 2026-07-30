# Customizing Screen Scribe

Everything you tune lives in three files plus the `Set Config` node. You do not
edit the graph. This guide walks the common changes.

Two ways to apply a config change: (a) re-run `python tools/build_workflows.py`,
which bakes `config/` into the templates and you re-import; or (b) edit the
matching field in the running workflow directly (`Set Config` for questions and
template, the parser node for the schema). Use (a) as the source of truth; use (b)
for quick in-place tweaks.

## 1. Cement your standard questions

Open `config/standard-questions.json`. Each entry is:

```json
{ "id": "motivation", "question": "Why this role now?", "guidance": "Look for a specific reason." }
```

- `id` is a stable key (used in the output). Keep it short and unique.
- `question` is what the model answers from the notes.
- `guidance` steers the answer; it is advice to the model, not shown to readers.

Add, remove, or reword freely. Then copy the whole `questions` array into the
workflow: open the `Set Config` node, find the `standard_questions` field, and
paste the JSON array as the value. That is the only place the workflow reads them.

Prefer a UI over editing JSON in a node? Load the questions from an n8n Data Table
instead and point the `Load Standard Questions` node at it. The shape is the same.

## 2. Decide what the writeup contains

Open `config/output-schema.json`. This is the structured output the model must
produce. To add a field (say a `culture_fit` rating):

1. Add it under `properties` with a type and description.
2. Add it to `required` if the model must always fill it.
3. Reference it in the template (step 3) so it shows up.

The schema is pasted into the `Structured Output Parser` node's `inputSchema`
field (A2 and A3). Keeping the file and the node in sync is the only rule.

## 3. Design the output

Open `config/screen-doc.template.md`. This is plain Markdown with placeholders:

- `{{candidate.name}}` pulls a field from the output.
- `{{#strengths}} - {{.}} {{/strengths}}` repeats a list.
- `{{#score}}...{{/score}}` renders only if the field is present.

Reorder sections, change headings, add your logo line, whatever. The `Format
Screen` node applies this template. Changing the template never requires touching
logic.

## 4. Point SOURCE at your storage

The reference build ships a Manual/Test trigger so you can run it immediately. For
production, replace the trigger with one that fires when a screen finishes:

| Your setup | Swap the trigger to |
|---|---|
| Gemini/Meet emails a notes summary | `Gmail Trigger` filtered to the notetaker sender |
| Notetaker drops a Doc in a Drive folder | `Google Drive Trigger` (file created in folder) |
| Notes in OneDrive/SharePoint | `Microsoft OneDrive Trigger` |
| Notes in a local/self-hosted folder | `Local File Trigger` (self-hosted n8n only) |
| You paste notes into a channel | `Slack Trigger` or a form |

After swapping the trigger, point the `Fetch Notes (SOURCE)` node at the trigger's
output field. It already handles the TEST_MODE sample path, so leave that branch.

## 5. Choose the model (or none)

- Default is Anthropic via the `Enrich Model` node. To use Gemini or OpenAI,
  replace that one node with the matching model node and attach its credential.
  Nothing else changes; the agent and parser are model-agnostic.
- Set `USE_MODEL=false` in `Set Config` to skip enrichment entirely and format the
  raw notes deterministically. This is also the automatic fallback if enrichment
  fails.

## 6. Wire your destination (SINK)

Defaults are a Google Doc plus a row appended to a Sheet tab. To change:

- Email instead of a doc: replace `Create Doc` and `Insert Doc Body` with a Gmail
  node whose body is `{{ doc_body_markdown }}`.
- A tab in an existing doc: use the Google Docs `update` operation against a fixed
  document id instead of `create`.
- ATS note (A3): set `ats_provider` and attach the ATS Basic-auth credential. See
  `docs/ARCHITECTURE.md` and `docs/integrations/ashby.md` for the exact
  request shapes.

## 7. Add candidate context (A2/A3)

RESOLVE gathers identity and enrichment inputs. Out of the box it reads fields you
set (email, name, role) and any resume text pasted in. To enrich automatically:

- From the calendar invite: parse the attendee email and any LinkedIn URL in the
  description in `Resolve Context`.
- From Slack: let a recruiter drop a resume file referencing the candidate; add a
  branch that reads the file and appends its text to `candidate.resume_text`.
- From the ATS (A3): the `ATS Find Candidate` step already looks the candidate up
  by email and can pull the resume link.

## Safety rails

- Keep `TEST_MODE=true` until you have validated an end-to-end preview.
- Never paste API keys into `Set Config` or Code nodes. Use n8n credentials so
  keys stay encrypted at rest.
- Keep `company_context` generic if you will share the pack.
