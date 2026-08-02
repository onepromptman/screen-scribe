# Compliance notes

**This is not legal advice.** `config/legal-reference.json` is an engineering
default assembled from public guidance. Have employment counsel review it before
you point this at real candidates.

## What the scrub actually does

Step 1 of the analyst prompt runs *before* extraction. It reads the whole
transcript, flags anything touching a protected characteristic or prohibited
topic, logs it to Section 3, and removes it from the material Steps 2 and 3 get to
see. The order matters: a scrub that ran afterwards would be a redaction pass over
an already-contaminated analysis.

Three rules that are easy to get wrong:

- **Volunteered information is still scrub material.** A candidate mentioning
  their kids unprompted does not make family status usable. It makes it a Section
  3 entry.
- **Intent is irrelevant.** A friendly rapport-building question about someone's
  hometown is logged the same as a deliberate one.
- **Every item is logged.** There is no threshold and no discretion to omit.

## Export control is not a national-origin question

`company-profile.json` has a `regulatory.regimes` field. If you work somewhere
ITAR, EAR, or a clearance genuinely applies, this is the one place where a
citizenship-adjacent question can be lawful — and the distinction is narrow:

| Lawful | Not lawful |
|---|---|
| "This role requires access to export-controlled technical data. Are you a U.S. person as defined by ITAR?" | "Where are you from?" |
| A yes/no legal-status question, scripted by counsel, asked of every candidate for the role | "What's your first language?" / "Is that an accent?" |
| Applied because the role actually touches controlled data | Applied because the company is *generally* regulated |

The legal reference reflects this: `national_origin.note` permits a scripted
U.S.-person question and prohibits everything adjacent to it. Leave
`regulatory.regimes` empty unless a specific regime applies to the specific role —
an empty list is the safe default, and the scrub is stricter with it empty.

## AI in the hiring loop

This tool applies a model to hiring input, which several jurisdictions regulate
directly (see `legal_reference.ai_specific`). NYC Local Law 144 requires a bias
audit and candidate notice for automated employment decision tools; Illinois
requires notice and consent for AI analysis of video interviews; the EU AI Act
classifies employment AI as high-risk.

The through-line across all of them: **disclose that AI is in the loop, keep a
human decision-maker, retain records.**

Screen Scribe's design answers the middle one structurally — the renderer refuses
to emit a document with a pre-filled `recruiter_recommendation`, so a human always
writes the verdict. It does not answer the other two for you. Notice and retention
are your policy decisions.

## Retention

The pipeline writes a `.docx`, optionally a Sheet row, and optionally an ATS note.
All three are candidate records subject to whatever retention obligations apply to
you (federal recordkeeping is generally one year from the action; some states and
contractor obligations are longer). Screen Scribe does not delete anything and has
no retention timer — set one wherever these land.

Transcripts are the sharper risk: they contain the protected-characteristic
content the scrub removed from the report. If you keep the transcript alongside
the report, the scrub has narrowed what gets *read*, not what exists. Decide
deliberately where raw transcripts live and how long they survive.
