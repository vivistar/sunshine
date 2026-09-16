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
2. **Storage:** client-side (`localStorage`) + **CSV import/export as the primary
   data path** (chosen by owner). See caveat below.
3. **Statistics depth:** v1 descriptive only — means, SD, n. No CIs / significance
   tests (deferred to v2).
4. **Anonymous:** yes. No PII collected.
5. **Item-9 `drop_q9_for_low_exposure`:** default **off**, exposed as a dashboard
   toggle (PRD recommendation).
6. **Tense variant:** prospective wording only, versioned via
   `INSTRUMENT_VERSION` in `instrument.config.js`.

## ⚠ Load-bearing caveat: no server
With a static SPA there is **no backend**, so:
- The dashboard passphrase is a **client-side gate, not a security boundary.**
  Set `VITE_SURVEY_PASSCODE` at build time to change it (default `sunshine`).
- Responses submitted on `/survey` are saved in **that browser's** localStorage.
  There is no automatic shared collection across devices — collection is
  **CSV-driven**: respondents/field staff export CSV, the researcher imports it
  on `/analyze`.
- For enforced researcher-only access and true multi-respondent collection, move
  responses to a server datastore (e.g. Vercel Postgres/KV + serverless
  functions) and check the passphrase server-side. The scoring/CSV modules are
  UI-independent and would port directly.

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
- `npm run dev` — local. `/`, `/survey`, `/analyze`.
- `npm test` — scoring + CSV tests.
- `npm run build` — production build to `dist/`.
