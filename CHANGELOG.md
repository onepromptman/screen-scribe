# Changelog

## 1.3.0 — consolidation for public release

The analyst profile shipped in 1.2.0 as a set of files beside the pack rather
than a part of it. This release makes it a first-class second profile: runnable,
validated, tested, and visible from the front page.

### Added

- `tools/render_prompt.py` — resolves `config/analyst-prompt.md` against
  `config/company-profile.json` and inlines `config/legal-reference.json`, then
  writes `build/analyst-prompt.md`. **The analyst prompt previously shipped with
  14 unresolved `{{placeholders}}` and no tool to resolve them**; the header
  named a build step that did not exist. `--check` fails when the committed
  build is stale.
- `tools/test_render.js` — 29 offline assertions covering the `.docx` renderer:
  both documented hard stops, the new shape check, schema/legal-reference
  consistency, and the optional-block variants. `docs/ANALYST-PROFILE.md` claimed
  these were tested; now they are.
- Analyst-profile coverage in `tools/validate_workflows.py` (684 → 784 checks):
  schema shape, required company-profile fields, accent-colour format,
  `jurisdiction.state` against the shipped supplements, unique category ids and
  labels, sample-report conformance, and that the built prompt is current and
  fully resolved.
- A third renderer refusal: a report missing a required top-level section now
  names the missing key instead of throwing from inside the layout code.
- `.github/workflows/check.yml` — offline CI: rebuild-and-diff, validate, test,
  credential scan.
- `docs/PART-2.md` — scope for a capture + scorecard extension, including
  verified findings on what Greenhouse, Ashby, and Kula actually allow.
- `CHANGELOG.md`.
- npm scripts: `build`, `build:prompt`, `check`.

### Fixed

- `tools/render_docx.js` reported a missing or malformed input file as a raw Node
  stack trace. It now gives a one-line reason and a non-zero exit, and catches
  the render promise rejection.
- `tools/render_docx.js` picked up the `-o` value as the input path when the flag
  came first.
- `config/legal-reference.json` said it was "inlined into the analyst prompt at
  build time" by a step that did not read it.
- `config/analyst-prompt.md` named the wrong tool and listed a placeholder
  (`company.short_name`) it never uses.
- `config/analyst-output-schema.json` said `compliance.violations[].category`
  must match a category **id**, while its own examples and the shipped sample use
  the **label**. The label is what the renderer prints; the schema now says so
  and the validator enforces it.

### Documentation

- `README.md` — the analyst profile, `npm install`, and the build/check commands
  were absent from the front page entirely. Added, along with the two docs that
  were unreachable from anywhere (`ANALYST-PROFILE.md`, `COMPLIANCE.md`).
- `README.md` — the Greenhouse exclusion is now stated precisely and is
  independently confirmed: Harvest exposes scorecards through three `GET`
  endpoints and no write path.
- `docs/ARCHITECTURE.md` — documents both output profiles, and flags that they
  take opposite positions on whether the model may emit a verdict.
- `docs/ANALYST-PROFILE.md` — the prompt build step, and a note that the `.docx`
  renderer is an offline CLI rather than something the workflows run.
- `docs/VALIDATION-PLAN.md` — Layer 2b for the analyst profile.

### Unchanged

No workflow behaviour changed. `templates/*.json` regenerate byte-identically
from `tools/build_workflows.py`.

## 1.2.0

Analyst report profile: genericized persona, templated Word output.

## 1.1.0

Enrichment level, resume auto-pull, PDF export.

## 1.0.0

Screen Scribe — turn a recruiter screen into a consistent writeup (n8n).
