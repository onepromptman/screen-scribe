# Lever (ATS) — n8n setup

Used by the A3 end-to-end archetype for candidate lookup by email and writing the
finished screen back as a candidate note. Lever sits behind the same normalized
`add_note` contract as Ashby (see `ashby.md`), so the workflow's provider switch
treats them identically at the contract level and only differs in request shape.

Two auth modes exist. **API key via HTTP Basic** is the default and all this pack
needs — the key is the Basic-auth username, the password is blank. **OAuth2** is
only needed if you build a distributable partner integration; skip that section
for ordinary use.

---

## Provider setup

### API key path (recommended)

Requires **Lever Super Admin**. A regular admin will not see the key-generation UI.

1. Go to **hire.lever.co → Settings → Integrations and API → API Credentials** tab.
   Direct URL: `https://hire.lever.co/settings/integrations?tab=api`

2. Click **Generate key**. Name it clearly (e.g., `n8n-screen-scribe-readonly`). The
   name appears on any objects the key creates via write endpoints, so it also
   serves as an audit trail.

3. Set the minimum permission needed:
   - **Read only** — candidate lookup by email (enough if A3 only reads).
   - **Write** — required for the `add_note` write-back (A3 posts the screen
     summary as a candidate note).

   You are creating a **Lever API v1** key (authenticated, candidate/opportunity
   data). This is distinct from the unauthenticated public Postings API (job-board
   feed); do not confuse them.

4. Copy the generated key immediately and paste it into n8n's credential store (see
   next section). The key is shown only once.

5. The key is used as the **HTTP Basic username** against `https://api.lever.co/v1`.
   The password is always blank.

#### Sandbox

Request a Lever sandbox from your Lever contact. It lives at `hire.sandbox.lever.co`
with API base `https://api.sandbox.lever.co/v1`. Generate a **separate** sandbox key
there and seed it with synthetic postings and opportunities before wiring any n8n
workflows. Do all development and testing against the sandbox only (see
[Connection test](#connection-test-synthetic-only)).

---

### OAuth2 path (partner builds only — skip for ordinary use)

1. Register at **hire.lever.co → Settings → Integrations → partner/OAuth registration**
   to obtain `client_id` and `client_secret`, and register your callback URI(s).

2. Endpoint reference:

   | Endpoint | Production | Sandbox |
   |---|---|---|
   | Authorize | `https://auth.lever.co/authorize` | `https://sandbox-lever.auth0.com/authorize` |
   | Token | `https://auth.lever.co/oauth/token` | `https://sandbox-lever.auth0.com/oauth/token` |
   | Audience | `https://api.lever.co/v1/` | `https://api.sandbox.lever.co/v1/` |

   Note: sandbox OAuth uses Auth0 hosts (`sandbox-lever.auth0.com`), not
   `auth.lever.co`. Mixing them causes invalid-client or redirect errors.

3. Scopes are space-separated in `resource:action:role` form (e.g.,
   `opportunities:read:admin postings:read:admin offline_access`). Include
   `offline_access` to receive a refresh token. Access tokens expire after 1 hour;
   refresh tokens rotate on each exchange and expire after ~1 year or 90 days idle.

4. The audience parameter **must end with a trailing slash** (`https://api.lever.co/v1/`).
   Omitting it breaks the flow silently.

---

## n8n credential setup

Lever has **no native node in n8n**. Do not search for a "Lever" credential type — it
does not exist. Use the **HTTP Request node** with a generic credential against the
Lever API base URL.

### API key (Basic Auth) — recommended

1. In n8n: **Settings → Credentials → New → Basic Auth**
2. Set:
   - **Username**: the Lever API key
   - **Password**: leave blank (empty string)
3. Name the credential (e.g., `Lever — sandbox` or `Lever — prod`).
4. In each HTTP Request node: set **Authentication = Generic Credential Type → Basic
   Auth**, then select this credential.
5. Base URL: `https://api.sandbox.lever.co/v1` for tests; `https://api.lever.co/v1`
   for prod.

### OAuth2 (partner builds only)

1. In n8n: **Settings → Credentials → New → OAuth2 API**
2. Set:
   - **Grant Type**: Authorization Code
   - **Authorization URL**: `https://auth.lever.co/authorize` (sandbox: `https://sandbox-lever.auth0.com/authorize`)
   - **Access Token URL**: `https://auth.lever.co/oauth/token` (sandbox: `https://sandbox-lever.auth0.com/oauth/token`)
   - **Client ID / Client Secret**: from Lever partner registration
   - **Scope**: space-separated list including `offline_access`
   - **Auth URL Query Parameters**: add `audience` = `https://api.lever.co/v1/` (trailing slash required; sandbox: `https://api.sandbox.lever.co/v1/`)
3. **Redirect URI to register in Lever**:

   ```
   https://<your-n8n-host>/rest/oauth2-credential/callback
   ```

   - Cloud: `https://<your-instance>.app.n8n.cloud/rest/oauth2-credential/callback`
   - Self-hosted: `https://<your-domain>/rest/oauth2-credential/callback`

   This URI must match **exactly** what is registered in Lever's partner settings. A
   mismatch (including a missing or extra slash, or a wrong hostname because
   `N8N_HOST`/`WEBHOOK_URL` is misconfigured) causes a redirect error at consent time.

4. Click **Connect my account** in n8n to complete the browser OAuth consent. n8n
   stores and auto-rotates the refresh token from that point forward.

Note: `$env` is blocked in n8n Cloud Code and expression nodes. Never use
`{{ $env.LEVER_API_KEY }}`. The credential must live in the n8n credential store and
be referenced server-side.

---

## Cloud vs self-hosted

| Scenario | n8n Cloud | Self-hosted docker n8n |
|---|---|---|
| API-key polling (normal Lever use) | Works — n8n makes outbound calls to `api.lever.co`. No public URL needed. | Same — outbound only, no public URL needed. |
| OAuth2 credential setup | Works — your n8n Cloud instance is already public + TLS; the callback is reachable at consent time. | Requires a stable public domain + TLS (reverse proxy) so the callback URL is reachable from your browser during consent. Set `N8N_HOST` and `WEBHOOK_URL` to match your registered Lever callback exactly. The n8n dev tunnel works for throwaway testing only. |
| Lever webhooks (optional — inbound events e.g., stage-change, offer-signed) | Works out of the box — the public Cloud URL receives Lever's webhook POSTs. Verify HMAC signatures on arrival. | Requires the public domain/tunnel. HMAC signature verification is separate from API-key polling — do not add HMAC headers to ordinary GET calls. |
| Execution data durability | n8n Cloud managed storage. | Run n8n against self-hosted Postgres (`DB_TYPE=postgresdb`) for durable execution history rather than relying on ephemeral execution logs. |

---

## Connection test (synthetic only)

All tests point at the **sandbox** (`https://api.sandbox.lever.co/v1`) using the
sandbox API key and sandbox-seeded synthetic postings and opportunities. Never point
a test at production, which holds real candidate PII.

### Smoke test (read)

In n8n, create an HTTP Request node:

- **Method**: GET
- **URL**: `https://api.sandbox.lever.co/v1/postings?limit=2`
- **Authentication**: Generic Credential Type → Basic Auth (sandbox credential)

Expected result: HTTP 200, JSON body with a top-level `data` array. A 401 means the
key is wrong, or it was entered in the password field instead of the username field.

### Write-path test (only if the key has Write permission)

HTTP Request node:

- **Method**: POST
- **URL**: `https://api.sandbox.lever.co/v1/opportunities/<synthetic-opportunity-id>/notes`
- **Body** (JSON): `{"value": "synthetic test note"}`

Expected result: HTTP 200, response echoes the new note ID. This is the same call
A3's `Build ATS Note` node makes on the Lever branch.

### Interchangeability check

Run A3 twice against the same fictional candidate — once with `ats_provider=lever`
(sandbox Lever key) and once with `ats_provider=ashby` (a disposable Ashby record).
Confirm the doc output is identical and only the ATS request shape differs. This
validates that the provider switch holds and swaps are safe.

---

## Gotchas

- **No native Lever node.** Do not search for a Lever credential type in n8n — it does
  not exist. Use HTTP Request + Basic Auth (or OAuth2 API for partner flows).

- **Basic-auth ordering trap.** The API key goes in the **Username** field. The
  **Password** must be blank. Entering the key in the password field produces 401s
  with no obvious explanation.

- **OAuth audience trailing slash.** The audience parameter is required and must end
  with `/` — `https://api.lever.co/v1/`. Omitting it or dropping the slash breaks the
  OAuth flow silently (no error at registration time; fails at token exchange).

- **Sandbox and prod OAuth use different auth hosts.** Sandbox uses Auth0
  (`sandbox-lever.auth0.com`); prod uses `auth.lever.co`. Mixing them causes
  invalid-client or redirect mismatch errors.

- **Redirect URI must match exactly.** On self-host, if `N8N_HOST` or `WEBHOOK_URL` is
  misconfigured, n8n generates a callback URL that does not match what is registered
  in Lever, and the OAuth flow fails at consent time.

- **Access tokens expire after 1 hour.** If you manually script OAuth instead of
  letting n8n manage it, you must refresh — and refresh tokens rotate, so you must
  persist the newest one each time. Let n8n manage the token lifecycle via its
  credential store.

- **Super Admin required for key generation.** A regular Lever admin will not see the
  Generate key button in API Credentials settings.

- **Postings API vs Lever API v1.** The public Postings API is unauthenticated and
  serves job-board data only. A3 needs the **authenticated Lever API v1** key. Do not
  confuse them.

- **Opportunity IDs, not application IDs.** Lever's pipeline unit is the opportunity
  (with epoch-ms timestamps), not a first-class application object. Candidate lookups
  and note write-backs are keyed by **opportunity id** (`data[0].id` from the lookup
  response). Passing a Greenhouse-style application id returns a 404.

- **HMAC headers are for webhooks only.** If you enable Lever webhooks (inbound
  events), payloads carry an HMAC signature to verify. Ordinary API-key GET/POST calls
  do not use HMAC; do not add HMAC headers to those requests.

- **`$env` is blocked in n8n Cloud.** Never reference `{{ $env.LEVER_API_KEY }}` in
  expressions or Code nodes. Use the n8n credential store server-side.

---

## Security

- The Lever API key is a bearer-equivalent secret. Store it **only** in the n8n
  credential store (Cloud or self-hosted). Never commit it to a repo, never embed it
  in workflow JSON, never put it in a committed `.env` file.

- Mask to last 4 characters in any logging or output. Do not echo full keys in n8n
  execution data.

- Issue keys with **least privilege**: a Read-only key for lookup-only use; a separate
  Write key strictly for the note write-back. Name each key for its integration (e.g.,
  `n8n-screen-scribe-readonly`) so objects created via write endpoints are
  attributable and keys are independently revocable.

- Use a **sandbox key + synthetic PII-free data** for all development and testing. Keep
  production keys out until the workflow is validated end to end.

- OAuth refresh tokens represent persistent access. Let n8n hold and rotate them in its
  encrypted credential store. Never log or export refresh tokens. Revoke from Lever
  Settings if a host is decommissioned.

- Rotate API keys periodically and immediately on any suspected exposure. Deleting a
  key in the Lever API Credentials tab revokes it immediately.

- Lever (optional) webhook payloads carry an HMAC signature. Verify it before
  processing inbound events; treat unverified payloads as untrusted input.
