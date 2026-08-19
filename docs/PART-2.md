# Part 2: capture and scorecards

v1 starts from an artifact someone else made (your notetaker's summary) and ends
at a **note** on the candidate record. Part 2 is the question of whether to push
both ends: own the **capture** (record and transcribe the interview), and write
real structured **feedback** into the ATS instead of freeform prose.

This document is a scope, not a commitment. It exists so the decision gets made
on evidence rather than on enthusiasm.

**Status: not built.** Nothing described here ships in v1.

---

## 1. What the ATSs actually allow

This is the finding that determines everything else, so it goes first.

| ATS | Read a scorecard | **Write a scorecard** | Discover the form | Verdict |
|---|---|---|---|---|
| **Greenhouse** | `GET /v1/scorecards`, `/v1/applications/{id}/scorecards`, `/v1/scorecards/{id}` | **No.** No documented POST/PATCH/PUT anywhere in Harvest | — | Closed to third parties |
| **Ashby** | `applicationFeedback.list` | **Yes** — `POST applicationFeedback.submit` | `feedbackFormDefinition.info` / `.list` | **Open, self-serve** |
| **Kula** | `GET /v1/applications/{id}/scorecards` | **No.** No create/submit/update in Kula's own API client | — | Closed to third parties |

**Greenhouse.** Harvest exposes scorecards read-only — three `GET` endpoints and
nothing else — confirmed against Greenhouse's own open-source docs repository
(`grnhse/greenhouse-api-docs`, `_scorecards.md`, last modified 2026-07-30).
There is also no "scorecard created/submitted" webhook, only "scorecard deleted",
so you cannot even react to a human submitting one without polling. The two
partner APIs that sound relevant are not: the **Assessment Partner API** is
inverted (Greenhouse calls *your* endpoints, for coding-test score ingestion into
a dedicated stage) and gated behind a partnerships review; the **Candidate
Ingestion API** is for sourcing partners submitting candidates, not feedback.

Vendors that do fill Greenhouse scorecards — BrightHire most visibly — are doing
it under private grants. Greenhouse's own announcement calls the BrightHire
scorecard integration **exclusive**. That is not a path open to this project.

**This confirms v1's stated reason for excluding Greenhouse was correct**, and
the README now says so precisely.

**Ashby** is the opposite, and is the reason Part 2 is worth considering at all.
`applicationFeedback.submit` takes `feedbackForm`, `formDefinitionId`, and
`applicationId`; optionally `userId` (whom to credit — defaults to the API key's
own user) and `interviewEventId`. It needs the `candidatesWrite` permission,
which any Ashby admin can self-issue. Field values are typed (Score is
`{score: 1-4}`, RichText takes `{type: "PlainText", value: ...}`), and the form's
schema can be read first via `feedbackFormDefinition.info`. No partner agreement,
no approval gate. Ashby also exposes its own AI notetaker's transcript through
`notetakerTranscript.info` (a short-lived signed URL plus a `participants` array
that distinguishes interviewer from candidate), which is a capture path that
requires no bot and no new processor.

**Kula** has a public REST API (Bearer auth, `api.kula.ai`) with full interview
CRUD, but scorecard submissions are list-only. You can ask *Kula's* own AI to
fill a scorecard (`ai_scorecard_assist_enabled` on `create_interview`); you
cannot submit one you generated. Kula is out of scope for automated feedback
until that changes.

> **Confidence.** Greenhouse and Kula are confirmed from first-party open-source
> repositories. Ashby is confirmed from a third-party OpenAPI mirror
> cross-checked against independent search results quoting the live docs — the
> two agree on method, permission, and behavior, but **verify against
> `developers.ashbyhq.com` before building.** Vendor pricing below is
> secondary-source and was internally inconsistent across sources; treat it as
> an order of magnitude, not a quote.

---

## 2. The recorder landscape

| Vendor | Greenhouse | Ashby | Kula | Writes scorecard fields? | Notes |
|---|---|---|---|---|---|
| **BrightHire** | native | native | — | **GH: yes** (exclusive partnership, auto-draft). **Ashby: attach-only** | ~$15K–100K+/yr, enterprise sales |
| **Metaview** | native | native | — | **Both: yes**, via a Chrome extension autofill the interviewer then reviews | Pricing signals inconsistent; get a quote |
| **Fireflies** | native | native | — | **No** — attaches to general notes, not scorecard fields | Pending Illinois BIPA suit over voiceprint consent (*Cruz v. Fireflies.AI*, Dec 2025) |
| **Pillar, Yobs** | native | — | — | **Almost certainly no** — both integrate via a standard Harvest key, and Harvest scorecards are GET-only, whatever the marketing says | |
| **Greenhouse Notetaker** | first-party | — | — | **Yes**, natively | The zero-integration answer for Greenhouse shops |
| **Ashby AI Notetaker** | — | first-party | — | **Yes**, natively; transcript readable via API | Paid add-on, price undisclosed |
| **Recall.ai** | infra | infra | infra | n/a — it is the plumbing you'd build on | Bot joins Zoom/Meet/Teams; ~$0.50/recording-hr + $0.15/hr transcription |
| **Otter, Grain, Fathom, Read.ai, tl;dv** | — | — | — | No | General meeting recorders, no recruiting write path |

For raw ASR if you build capture yourself: Deepgram Nova-3 (~$0.0043/min batch,
diarization ~+$0.12/hr, lowest latency), AssemblyAI (diarization ~$0.02/hr,
bundles PII redaction), Whisper (~$0.36/hr, **no diarization** — needs a separate
speaker step, which makes it incomplete for interviews on its own).

**No vendor writes scorecards into all three ATSs.** That gap is itself the
finding.

---

## 3. The bug Part 2 would fix

There is a correctness problem in the shipped analyst profile that has nothing to
do with scorecards, and it is the strongest argument for Part 2.

The analyst profile is written for a **transcript**: `analyst-prompt.md` says
"Given a recruiter interview transcript"; the schema's provenance enum includes
`transcript` with a verbatim `quote`; the renderer prints "from the screen" under
those values. But v1's SOURCE is a **notes summary**.

Call it the **empty Section 3 problem**:

> A notetaker summary systematically omits the small talk and rapport-building
> where protected-characteristic content actually lives. Run the compliance scrub
> over a Gemini summary and `compliance.violations` comes back empty almost every
> time. The renderer then prints its explicit no-violations statement. A reader
> takes a clean compliance section as evidence of a clean interview. It is
> evidence of a lossy input.

The fix is small and does not require capture at all:

1. Add a required `source_fidelity` field (`transcript` | `notes_summary` |
   `mixed`) to both output schemas.
2. Add a **third renderer refusal**: when `source_fidelity !== "transcript"`, the
   renderer must not print the clean bill of health. It prints instead: *"The
   compliance scrub ran against a notes summary, not a transcript. Absence of
   flagged items is not evidence of compliant interviewing."*

That is one config field and about twenty lines of renderer code, and it is the
highest-value item in this document. It should ship whether or not anything else
here does.

---

## 4. If capture gets built

**Screen Scribe should not join the call.** The moment the project ships a
dispatcher that puts a bot with its own name into a meeting, its relationship to
the data changes: it stops reading an artifact someone else lawfully created and
starts *causing* the recording. Pull-based capture avoids that entirely.

Ranked:

1. **Platform-native + API pull** (Meet transcript into Drive, Zoom cloud
   recording, Teams). The platform shows its own consent UI to every participant.
   The pack never touches audio and engages no new processor. Attaches as a
   straight swap of the existing Drive/Gmail trigger. **Default.**
2. **Notetaker vendor transcript API**, including Ashby's own
   `notetakerTranscript.info`. Vendor already handles the join notice; the org
   already signed the DPA.
3. **Meeting bot** (Recall.ai-class). Document it; don't ship it. It needs a
   public webhook receiver, owns a consent surface the pack cannot discharge, and
   can join the wrong meeting on a recurring link.
4. **Raw ASR on audio.** Ships candidate audio to a new processor and needs its
   own DPA. Last resort.

All four should normalize into one contract (`config/transcript-schema.json`) so
SOURCE stays swappable, exactly as `{ notes_text, meeting_title, ... }` does today.

Three things break when input goes from a 500-word summary to a 12,000-word
transcript, and each needs a real answer, not a prompt tweak:

- **The scrub must become its own pipeline stage.** `docs/COMPLIANCE.md` is right
  that a scrub running after extraction is "a redaction pass over an already
  contaminated analysis" — but at transcript scale, "do not let this survive into
  Step 2" inside a single prompt is instruction-following, not a guarantee. Split
  it: a scrub call that emits **quotes**, then a deterministic node that redacts
  those exact spans and fails closed if a quote doesn't match. ENRICH then never
  sees the raw transcript, and `scrubbed_from_analysis: true` becomes structurally
  true rather than self-reported.
- **Quotes must be verified.** A real transcript makes real verbatim quotes
  possible — and makes a paraphrase printed inside quotation marks under a "from
  the screen" label a worse lie than v1 ever told. Exact-match every quote against
  the transcript; strip the ones that fail.
- **Speaker attribution is dangerous.** `compliance.violations[].speaker` already
  exists in the schema. If diarization flips the labels, the pack generates a
  written allegation that a named employee asked an illegal question and files it
  in a candidate record. Rule: `speaker` stays `null` unless the adapter resolves
  actual names — "Speaker 0" is not a name.

Cost, roughly: a two-stage windowed scrub plus extraction on a 45-minute
transcript runs about 8× v1's per-screen model cost — cents, not dollars, against
fifteen minutes of recruiter time. Latency is the real change: seconds becomes
one to three minutes.

---

## 5. The principle problem

Part 2's downstream half runs straight into the project's own stated rule.
`docs/ANALYST-PROFILE.md`: the renderer *"will not render a pre-filled
recommendation… The model never gets a vote on the verdict."* A scorecard write
is, on its face, exactly a pre-filled verdict pushed into the system of record.

The resolution is to notice that a scorecard is three different things:

| Layer | Example | Rule |
|---|---|---|
| Observations + evidence | "Owned the payments service end to end," verbatim | **Machine may author.** This is structured transcription. |
| Per-attribute ratings | "Relevant Experience: yes" | **Machine may draft; a named human approves the exact payload before submit.** |
| Overall recommendation | "Advance" | **Never filled. By anything. In any mode.** |

Which gives the rule Part 2 would be built around:

> Screen Scribe never writes a scorecard. A human submits a scorecard that Screen
> Scribe drafted, from evidence Screen Scribe verified, with the verdict field
> left empty for that human to fill in.

Consequences worth stating up front, because they constrain the design rather
than decorate it:

- The verdict rule is **code, not config** — absent from the mapping file so no
  operator can switch it on, and enforced the way `render_docx.js` enforces its
  refusals. A provider that makes the overall field mandatory is a provider the
  pack does not auto-submit to.
- **A competency the screen didn't cover is submitted blank**, with a reason —
  never a middle rating. A blank is visibly a gap; a fabricated "mixed" reads as
  a finding.
- **Scales are mapped, never computed.** An explicit value→value table per
  provider. Scaling a 1–4 onto a 1–5 asserts that 2/4 = 2.5/5, which is false.
- **`enrichment_level: high` blocks submission.** That is the mode that
  "synthesizes and suggests" — precisely the mode that should not be authoring
  ratings in the system of record.
- **Compliance violations and transcript text never leave the document.** Not as
  a note, not as an attachment. Violations are allegations about an employee,
  possibly diarization-wrong, sitting in a discoverable candidate record — and
  their content is exactly what the scrub exists to contain.
- **Default mode is `note_only`**, which renders the scorecard as text through
  v1's existing `add_note` path. v1's contract becomes v2's degradation path.
- **Idempotency is the pack's problem.** Assume no provider offers a key and no
  provider lets you un-submit. That means a ledger keyed on content hash, checked
  before the write, plus `retryOnFail: false` on the submit node — n8n's automatic
  node retry is exactly where a duplicate scorecard comes from.

### One thing to settle first

v1 already has a smaller version of this tension, and it should be resolved
before anything gets built on top of it: **`config/output-schema.json` requires
the model to emit a `recommendation`** (`strong_advance` → `no`), which the
screen-writeup template prints in the document header — while the analyst profile
refuses to let the model emit a verdict at all. Two shipped profiles, opposite
positions, same question.

Both are defensible: a screen writeup is triage read by the next interviewer, an
analyst report goes to an executive. But it should be a stated choice. If the
answer is "the model never renders a verdict," then `recommendation` becomes
nullable in v2 and the screen template prints a placeholder too. If the answer is
"triage is different," `docs/ARCHITECTURE.md` should say why. This is noted there
now, undecided.

---

## 6. Recommended shape

**Phase A — ship regardless.** `source_fidelity` plus the third renderer refusal
(§3). Fixes a live correctness bug, needs no capture and no ATS work.

**Phase B — capture, pull-based only.** Normalized transcript contract, the scrub
as a real stage with deterministic redaction, quote verification, and adapters
for Meet/Drive and notetaker APIs. No bot, no audio bytes, no public webhook.
Ships as a fourth archetype (A4) because ENRICH's graph genuinely changes.

**Phase C — scorecards, Ashby only, draft-first.** `applicationFeedback.submit`
behind a discovery step, a declarative question→attribute map, a required human
approval gate, and a ledger. Default `note_only`. Ships as A5.

**Not built:** Greenhouse or Kula scorecard writes (no public path — and faking
one by stuffing ratings into a custom text field would be worse than a note,
because it looks native and won't appear in the ATS's own reporting), meeting
bots, audio handling, scorecard updates or deletions, anything hosted.

**Where the line is for this project:** *it may generate the request; it must
never be the endpoint.* The repo stops being a reference implementation and
becomes a product — with a privacy policy, a DPA, and a support obligation the
MIT header disclaims — the moment it ships a hosted webhook receiver, a shared
bot account, or an API key the maintainer owns. If you run Screen Scribe, you are
the controller; the author operates nothing and receives nothing. That belongs in
`docs/COMPLIANCE.md` before any of this gets built.

One risk to weigh before Phase C specifically: a tool that emits **ratings on
evaluative attributes into the system of record** sits much closer to NYC Local
Law 144's "automated employment decision tool" definition, and to the EU AI
Act's high-risk employment category, than a tool that writes a summary. The empty
verdict field and the required human approval are arguments against that reading.
They are arguments, not immunity, and the call belongs with counsel rather than
with a config default.
