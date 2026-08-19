# The analyst profile

Screen Scribe ships two output profiles. Both run on the same five-module spine
(SOURCE → RESOLVE → ENRICH → FORMAT → SINK); they differ only in what ENRICH is
asked to produce and what FORMAT renders.

| | **Screen writeup** (default) | **Analyst report** |
|---|---|---|
| Prompt | baked into the workflow | `config/analyst-prompt.md` |
| Contract | `config/output-schema.json` | `config/analyst-output-schema.json` |
| Output | Google Doc + Sheet row | **`.docx`** via `tools/render_docx.js` |
| Compliance scrub | — | ✅ Section 3 |
| Employer research | — | ✅ `[AI INSIGHT]`, cited |
| Audience | the next interviewer | hiring managers and executives |

Use the screen writeup for volume. Use the analyst report when the output will be
read by someone senior, or when you need the compliance trail.

## Run it

```bash
npm install          # one-time: pulls the docx renderer
npm run sample       # renders the bundled fictional sample to sample-report.docx
```

That renders the bundled sample so you can see the template before wiring
anything up.

## Build the prompt

`config/analyst-prompt.md` is a **template**, not a finished prompt — every
company-specific fact in it is a `{{placeholder}}`. Resolve them against your
profile:

```bash
npm run build:prompt   # or: python3 tools/render_prompt.py
```

That writes `build/analyst-prompt.md`: the same prompt with your company, work
policy, and jurisdiction filled in, and `config/legal-reference.json` inlined as
the LEGAL REFERENCE section — federal categories always, plus the supplement for
your `jurisdiction.state`. Paste the result into the ENRICH agent's system
prompt.

Re-run it whenever you edit `company-profile.json` or `legal-reference.json`.
`python3 tools/render_prompt.py --check` fails if the committed build is stale,
and `npm run validate` calls the same check.

## Make it yours

Edit **`config/company-profile.json`** and nothing else. It is the only file that
carries a company name, a work policy, or a jurisdiction — the prompt, the schema,
and the Word renderer all read from it.

| Field | What it drives |
|---|---|
| `company.*` | Prompt persona, masthead, the context paragraph fed to ENRICH |
| `work_policy.label` / `.detail` | The confirmation row every candidate is asked about, worded your way |
| `regulatory.regimes` | Optional export-control or clearance context. Leave empty if none applies — read `docs/COMPLIANCE.md` first |
| `jurisdiction.state` | Which state supplement the compliance scrub enforces (`config/legal-reference.json`) |
| `report.accent_color` | Document accent — masthead rule, section rules, callout bar |
| `report.recommendation_placeholder` | The text a human is prompted to replace |

Set `jurisdiction.state` to `null` for federal-only screening. Supplements ship
for California, New York, Illinois, Colorado, and Washington.

## What the renderer refuses to do

Three hard stops, all non-negotiable and all covered by `tools/test_render.js`:

1. **It will not render a report whose flagged content was never withheld.** If
   `compliance.violations` is non-empty and `compliance.scrubbed_from_analysis`
   is not `true`, the render fails with a non-zero exit.
2. **It will not render a pre-filled recommendation.** `recruiter_recommendation`
   must be `null`. The document prints the placeholder so a human types the
   assessment. The model never gets a vote on the verdict.
3. **It will not render a report that is missing a required section.** A
   malformed model response names the missing key and exits non-zero rather than
   producing a document with a hole in it.

The second one is the whole point of the profile. Everything else on the page is
evidence, provenance, and research; the judgement stays with the recruiter.

## Provenance

Every field in the candidate-information block carries a `source` — `transcript`
(with the verbatim quote), `ats`, `config`, or `not_found` — and the renderer
prints it under the value. A reader can always tell what was confirmed on the call
from what was carried in from the record.

Fields that were never covered render as `UNKNOWN` in muted italic. Fields the
transcript was too thin to support render as `INSUFFICIENT DATA`. Neither is ever
left blank, because a blank cell reads as a negative finding.

## Where this runs

`tools/render_docx.js` is an offline Node CLI, not an n8n node — n8n Code nodes
cannot `require` an external module like `docx` unless you self-host with
`NODE_FUNCTION_ALLOW_EXTERNAL` set. So the analyst profile today is: run ENRICH
however you like (the n8n agent, or any model call using the built prompt), save
the JSON it returns, then render it locally. The `.docx` step is not something
the shipped workflows do for you.

## Caveat

`config/legal-reference.json` is an engineering default, not legal advice. Have
counsel review it before you point this at real candidates, and read
`docs/COMPLIANCE.md`.
