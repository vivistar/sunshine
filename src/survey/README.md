# Anticipated Trust Survey — build notes

Adapted from **TOAST** (Wojton, Porter, Lane, Bieber & Madhavan, *J. Social
Psychology*, 2020). The prospective rewording **breaks the original psychometric
validation** — every results surface labels output "anticipated trust (adapted
TOAST)", never "TOAST score." Citation confidence: moderate-high; verify before
publishing results.

## Host stack (confirmed by inspecting this repo, PRD §0/§7.1)
- **Framework:** React 18 + Vite 5 + Tailwind v4 (single-page app).
- **Deploy target:** Vercel static hosting (`vercel.json`, output `dist`).
- **Existing auth:** none. **Existing DB:** none — it was a static affirmation SPA.

## Decisions (PRD §7)
1. **Integration mode:** routes inside the existing app (chosen by owner).
   - `/survey` — public respondent link (no login). Reads `?study=` & `?condition=`
     (plus optional `?system=`, `?purpose=`, `?exposureVerb=` for the stem).
   - `/analyze` — passphrase-gated researcher dashboard.
   - SPA deep-links resolve via a catch-all rewrite in `vercel.json`.
2. **Storage:** **Vercel Postgres** via serverless functions in `/api`, with
   server-side passphrase enforcement. CSV import/export remains first-class.
   (localStorage is now only an offline fallback if the API is unreachable.)
3. **Statistics depth:** v1 descriptive only — means, SD, n. No CIs / significance
   tests (deferred to v2).
4. **Anonymous:** yes. No PII collected.
5. **Item-9 `drop_q9_for_low_exposure`:** default **off**, exposed as a dashboard
   toggle (PRD recommendation).
6. **Tense variant:** prospective wording only, versioned via
   `INSTRUMENT_VERSION` in `instrument.config.js`.

## Backend (Vercel Postgres + serverless functions)
True multi-respondent collection with server-enforced researcher access.

**API routes** (`/api`, Vercel Node functions):
- `POST /api/responses` — public. Submit one completed response (validated server-side).
- `GET  /api/responses[?study=]` — researcher. List responses. **Requires** the
  `x-survey-passcode` header, checked against `SURVEY_PASSCODE`.
- `DELETE /api/responses[?study=]` — researcher. Delete all / one study.
- `POST /api/import` — researcher. Bulk import rows; validates + reports rejects.
- `POST /api/tags` — researcher. Save manual q12 tags.

The `responses` table is auto-created on first request (`ensureSchema`) with the
PRD §5.2 columns; imports upsert (dedupe by `response_id`).

### Required setup in Vercel (one-time)
1. **Add a database:** Project → Storage → Create → **Postgres**, connect it to
   this project. Vercel injects `POSTGRES_URL` (and friends) as env vars — no code
   change needed; `@vercel/postgres` reads them automatically.
2. **Set the passphrase:** Project → Settings → Environment Variables →
   `SURVEY_PASSCODE` = your researcher passphrase. **Server-only — do NOT prefix
   with `VITE_`/`NEXT_PUBLIC_`.** Without it, `/analyze` returns a clear error.
3. Redeploy.

### Access & privacy
- The passphrase is verified **server-side**; it is never bundled into client JS.
- Responses live in Postgres and are only returned to a caller presenting the
  passphrase — the researcher-only read boundary is real, not cosmetic.
- Anonymous; no PII. `instrument_version` is stamped on every row.

### Offline fallback
If the API is unreachable (e.g. `npm run dev` locally with no DB, or before the
DB is provisioned): survey submissions are kept in the browser's localStorage and
can be exported to CSV; the dashboard shows example data in a labeled "offline
mode" with import/persistence disabled. Provision Postgres to switch to real
shared collection — no code change required.

## Modules
- `instrument.config.js` — fixed 12-item instrument, versioned. U/P/D labels internal only.
- `scoring.js` — **pure, unit-tested** engine (S1–S7). Usable headless.
- `scoring.test.js`, `csv.test.js` — worked-example tests (`npm test`).
- `csv.js` — validated import (reports rejects) + round-trip-safe export.
- `storage.js` — localStorage store + manual q12 tagging.
- `sampleData.js` — example rows so the dashboard is never an empty shell.
- `SurveyPage.jsx` — respondent flow (accessible Likert, inline validation).
- `AnalyzePage.jsx` — dashboard: U/P split by condition, U-vs-P plot (over-trust
  quadrant), exposure/certainty filters, exposure-mismatch warning, condition
  comparison, sufficiency gate, q12 review + tagging, CSV export.

## Run
- `npm run dev` — local UI. `/api/*` functions do NOT run under plain Vite, so the
  app is in offline mode; use `vercel dev` (with env vars) to exercise the API.
- `npm test` — scoring + CSV tests.
- `npm run build` — production build to `dist/`.

## Files
- `api/responses.js`, `api/import.js`, `api/tags.js` — serverless routes.
- `api/_lib/validate.js` — server-side validation + `checkAuth` (not routed).
- `api/_lib/db.js` — schema + upsert (`@vercel/postgres`).
- `src/survey/api.js` — frontend fetch client.
