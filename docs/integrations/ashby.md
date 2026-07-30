# Ashby (ATS) — n8n setup

Used by the A3 end-to-end archetype for candidate lookup by email and writing the
finished screen back as a candidate note. Ashby sits behind the same normalized
`add_note` contract as Lever (see `lever.md`), so the workflow's provider switch
treats them identically at the contract level and only differs in request shape.

> Verify the exact endpoint names and body fields against the current Ashby API
> docs (https://developers.ashbyhq.com) before going live. The shapes below match
> the documented API at time of writing; Ashby versions its API and this pack
> cannot hit it during the build.

## Auth

- Base URL: `https://api.ashbyhq.com`
- All calls are **POST** with a JSON body (Ashby's RPC-style API).
- **HTTP Basic auth**: the API key is the Basic-auth **username**, password blank.
  This is the same scheme as Lever, so one n8n `httpBasicAuth` credential shape
  works for either provider (you create one per provider with its own key).

## Provider setup

1. In Ashby: **Admin -> Integrations -> API** (requires an admin role). Generate
   an API key and copy it immediately.
2. Scope the key to the minimum needed:
   - Read candidates (for `candidate.search` / lookup by email).
   - Write candidate notes (for `candidate.createNote`).
3. Paste the key into an n8n credential of type **Header Auth** or **Basic Auth**:
   - Basic Auth: username = the API key, password = empty.

### Sandbox

Ashby does not offer a separate sandbox host. Test against a disposable candidate
record you create in your own Ashby instance, and keep `TEST_MODE=true` in the
workflow until you have confirmed the request shape in the Dry Run Preview.

## Endpoints the pack uses

### Find candidate by email

```
POST https://api.ashbyhq.com/candidate.search
Content-Type: application/json
Authorization: Basic base64(<API_KEY>:)

{ "email": "candidate@example.com" }
```

Response contains `results[]`; take `results[0].id` as the `candidate_id`. If
`results` is empty, the pack skips the ATS note and still delivers the doc.

### Add a note to a candidate

```
POST https://api.ashbyhq.com/candidate.createNote
Content-Type: application/json
Authorization: Basic base64(<API_KEY>:)

{
  "candidateId": "<candidate_id>",
  "note": "<the formatted screen summary + doc link>",
  "sendNotifications": false
}
```

Some Ashby API versions expect `note` as an object (`{ "value": "...", "type":
"text/plain" }`) rather than a string. If a string is rejected, switch to the
object form; both are handled by the `Build ATS Note` node's Ashby branch (edit
the one expression).

## Normalized contract (for parity with Lever)

| Concept | Ashby | Lever |
|---|---|---|
| Find by email | `POST /candidate.search {email}` | `GET /opportunities?email=` |
| Candidate id | `results[0].id` | `data[0].id` (opportunity id) |
| Add note | `POST /candidate.createNote {candidateId, note}` | `POST /opportunities/{id}/notes {value}` |
| Auth | Basic, key as username | Basic, key as username |

## Connection test (synthetic only)

A read-only probe (search a known test email) proves the key authenticates and the
response shape is as expected. Do not run write probes against a production
instance; use a disposable candidate and `TEST_MODE`.
