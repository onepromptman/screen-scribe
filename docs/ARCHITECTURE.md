# Screen Scribe: architecture

## What this is

A packageable n8n infrastructure that turns raw recruiter-screen notes into a
finished screen writeup and delivers it wherever you want it. It generalizes a
common one-off (an AI notetaker captures the screen, someone reformats it, a row
lands in a sheet) into a customizable pipeline that anyone can point at their own
storage, model, template, and destination.

The design goal is flexibility, not a single hard-wired flow. Everything that
tends to differ between teams (where notes come from, which model runs the
enrichment, what the output looks like, where it lands) is a named, swappable
module. You customize by swapping a module, not by rewiring the graph.

## The spine (five swappable modules)

Every archetype is a subset of one five-stage spine. Each stage is a module you
can replace without touching the others.

```
SOURCE  ->  RESOLVE  ->  ENRICH  ->  FORMAT  ->  SINK
(notes)   (identity)   (model)     (template)  (deliver)
```

| Stage | Job | Default | Swap to |
|---|---|---|---|
| 1. SOURCE | Trigger on a finished screen and load the notes text plus meeting metadata | Manual/Test trigger with pasted notes; production swap is a Gmail trigger on the notetaker email or a Drive folder watch | OneDrive, local folder, calendar-event-ended, chat/Slack command |
| 2. RESOLVE | Derive candidate identity and enrichment inputs | Fields from the calendar invite (attendee email) plus anything pasted; an optional resume auto-downloaded from `candidate_resume_link` (`fetch_resume`) | Email lookup, ATS lookup by email (A3), LinkedIn enrichment API |
| 3. ENRICH | Turn notes plus context plus the cemented questions into structured output | n8n AI Agent + Anthropic model + structured output parser | Any model (Gemini/OpenAI by swapping the model node), or template-only (no model) |
| 4. FORMAT | Render the structured output through a user template | Markdown/Google Doc template (config/screen-doc.template.md) | Doc tab, email body, ATS note body |
| 5. SINK | Deliver to the destination | Google Doc + a row appended to a Sheet tab; an optional PDF export dropped in the Drive folder (`deliver_pdf`) | Email, Doc tab, ATS candidate note (Ashby/Lever) |

### Why the notes come from an AI notetaker, not a transcript

The v1 model is: an AI notetaker (for example Gemini in Google Meet) already
produces a clean notes summary during the screen. This pack starts from that
summary, so SOURCE is "a finished notes artifact appeared," not "record and
transcribe audio." That keeps the pack model-agnostic on the capture side: any
notetaker that can drop a doc in a folder or send an email works.

## The three archetypes

The three ship as self-contained workflows (one file each). A2 is A1 plus ENRICH
and RESOLVE. A3 is A2 plus the ATS lookup and the ATS note sink.

### A1 Minimal: Screen Notes to Doc

The generalized v1. No model. Deterministic reformat of the notes into your
template, then a Google Doc plus a row in a Sheet tab.

```
Manual/Test Trigger -> Set Config -> Fetch Notes (SOURCE)
  -> Format Screen (FORMAT, template, no model)
  -> Live Writes? (TEST_MODE gate)
       true  -> Dry Run Preview
       false -> Create Doc -> Insert Doc Body -> Append Screen Row (Sheet tab) -> Slack Notify
  [Error Trigger -> Extract Error -> Log to Sheet -> Alert Slack]
```

Use when you want consistency of place and format, and you trust the notetaker's
notes as-is.

### A2 Enriched: cemented questions + candidate context

Adds the intelligence layer. An AI Agent reads the notes plus any candidate
context and answers every cemented standard question, emitting the structured
schema. The template is filled from that structured output.

```
Manual/Test Trigger -> Set Config -> Fetch Notes (SOURCE)
  -> Resolve Context (RESOLVE: identity + enrichment inputs)
  -> Fetch Resume? (optional: Download Resume -> Extract Resume Text -> Merge Resume)
  -> Use Model? (enrichment_level gate; off -> deterministic passthrough)
       true  -> Enrich Model + AI Enrich (agent) + Structured Output Parser -> Parse Enrich Output
       false -> Passthrough (A1 behavior, fail-open)
  -> Format Screen (FORMAT, filled from structured output)
  -> Live Writes? gate -> Create Doc -> Insert Doc Body
       -> Deliver PDF? (optional: Export Doc as PDF -> Save PDF to Drive)
       -> Append Screen Row -> Slack Notify
  [Error branch]
```

Use when you want a consistent, structured writeup that answers the same
questions for every candidate, regardless of how the notetaker phrased things.

### A3 End-to-end: enrichment plus ATS upload

Adds identity resolution against your ATS and writes the finished screen back as
a candidate note. Ashby and Lever are supported behind one provider switch;
Greenhouse is deliberately out of scope because it does not allow scorecard
writes over the API (the note path exists but the pack targets Ashby/Lever).

```
... A2 up to Parse Enrich Output, then Format Screen (FORMAT) ...
  -> Live Writes? (TEST_MODE gate)
       true (TEST_MODE) -> Dry Run Preview (shows the exact writes + ATS request, nothing sent)
       false -> Create Doc -> Insert Doc Body
                -> Deliver PDF? (optional: Export Doc as PDF -> Save PDF to Drive)
                -> Build ATS Lookup (provider switch: ashby|lever) -> ATS Find Candidate
                -> Parse Candidate -> Found in ATS? -> Build ATS Note -> ATS Add Note
                -> Append Screen Row -> Slack Notify
  [Error branch]
```

The ATS upload lands as a candidate **note/feedback**, not a native scorecard.

## The customization surface

This is the part you actually tune. It is deliberately concentrated in three
places so a non-engineer can own it.

### 1. Cemented standard questions (config/standard-questions.json)

The locked screen questions. The ENRICH agent answers every question in this list
from the notes. Edit the list once and the enrichment adapts with no workflow
change. In n8n the list is pasted into the `standard_questions` field of the
`Set Config` node (or loaded from an n8n Data Table if you prefer a UI). This
file is the source of truth in the repo.

### 2. Output shape (config/output-schema.json)

The structured shape ENRICH produces and FORMAT consumes. Change this to change
what the writeup contains (add a score, drop a section). It is a JSON Schema, fed
to the structured output parser so the model is held to it.

### 3. The template (config/screen-doc.template.md)

What the finished screen looks like. Reorder sections, change headings, add
fields. Placeholders in `{{ }}` map to the output schema.

### Config flags (the `Set Config` node)

| Flag | Meaning |
|---|---|
| `TEST_MODE` | true = dry run, no external writes; the SINK is replaced by a preview of what would be written |
| `enrichment_level` | `off` = deterministic template-only (also the fail-open fallback); `low` = extract-only, no inference or ratings; `medium` = light evidence-flagged inference (default); `high` = full synthesis + suggestions |
| `fetch_resume` | true = download the resume at `candidate_resume_link`, extract its text, and feed it to enrichment (A2/A3) |
| `deliver_pdf` | true = export the finished Google Doc to PDF and drop it in the Drive folder |
| `company_context` | Placeholder org description injected into the enrichment prompt |
| `ats_provider` | `ashby` or `lever` (A3) |
| source/sink ids | Drive folder id, Sheet id, Sheet tab name, doc template id |

## Data contract between stages

Each stage passes a single normalized object forward, so a swap on one stage does
not ripple:

- SOURCE emits `{ notes_text, meeting_title, meeting_time, attendees[] }`.
- RESOLVE adds `{ candidate: { name, email, role, linkedin_url, resume_text } }`.
- ENRICH emits the full object in config/output-schema.json.
- FORMAT emits `{ doc_title, doc_body_markdown }`.
- SINK consumes those plus the resolved `candidate` for the ATS note.

## Robustness (recreating v1 with an n8n agent)

- The ENRICH agent uses a structured output parser, so malformed model output is
  retried against the schema rather than passed downstream.
- `enrichment_level=off` is a genuine fallback path: if the model is unavailable or
  you do not want it, the pack degrades to deterministic formatting and still ships
  a doc. Enrichment failure never blocks delivery. `low` keeps the model but bars
  inference, reporting only what the notes actually say.
- Every workflow carries a built-in error branch (Error Trigger -> log to a Sheet
  -> alert Slack), so failures are captured and surfaced instead of lost.
- `TEST_MODE` makes the whole pipeline safe to run before any credential or id is
  real: it exercises SOURCE, RESOLVE, ENRICH, and FORMAT and previews the SINK.

## Design decisions

- **Self-contained workflows over shared sub-workflows.** Each archetype is one
  importable file. This trades a little duplication for a package a stranger can
  import and run without rewiring `executeWorkflow` id references (a common failure
  mode when archetypes share sub-workflows). The five modules above are the conceptual contract;
  they are realized as node groups inside each file, not as separate workflows.
- **AI notetaker as the source, model-agnostic capture.** See above.
- **ATS as an adapter.** The A3 sink uses a normalized `add_note` contract
  (candidate id plus note body), implemented in-workflow with `httpRequest` so the
  pack has no external runtime dependency. Adding a provider means adding one
  branch to the two "Build ATS ..." nodes.
- **Greenhouse intentionally excluded** for the scorecard-write reason above; it
  can be added later as a third provider branch if only the note path is needed.
