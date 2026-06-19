# ☀ Sunshine

A self-contained survey tool with participant email invitations and two pricing
research methods: **Choice-Based Conjoint (CBC)** analysis and the
**Van Westendorp Price Sensitivity Meter**. Build a study, invite respondents by
email, collect responses through a web survey, and get the analysis — all in one
FastAPI app.

## What it does

- **Survey types**
  - **Choice-Based Conjoint** — define attributes (e.g. *Price*, *Brand*,
    *Size*) and levels, auto-generate a randomized choice design (configurable
    options per task, optional "None of these"), and present choice tasks.
  - **Van Westendorp** — respondents answer the four classic price questions;
    the tool computes the Optimal Price Point (OPP), Indifference Price (IPP),
    and the acceptable price range (PMC–PME), with a curve chart.
  - **Ranking / Rating** — define a list of items respondents either **rate**
    on a shared scale (the matrix grid, with optional endpoint labels) or
    **rank** in order; results show mean, distribution, and top-choice share
    per item.
  - **MaxDiff** (best-worst scaling) — define items, auto-generate a
    count-balanced design of small sets, and respondents pick the **best** and
    **worst** in each; results report the best-minus-worst score per item.
- **Invite participants by email** — each respondent gets a unique survey link.
  Works with any SMTP provider, or runs in a no-credentials *console mode* for
  local development.
- **Conjoint analysis** — aggregate **multinomial logit (MNL)** estimation of
  part-worth utilities with **significance stats** (std. errors, t, p, 95% CI),
  relative attribute importance, and model fit (McFadden pseudo-R²).
  - **Willingness-to-pay** — money value of each level, derived from a numeric
    price attribute.
  - **Market simulator** — define competing products and see predicted
    share-of-preference.
- **Admin authentication** — the researcher UI is protected by a browser login
  screen (session cookie), enabled by setting `ADMIN_PASSWORD`. Respondent
  survey links stay public.

## Quick start

```bash
# 1. Install dependencies (Python 3.11+)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. (optional) configure email + base URL
cp .env.example .env        # leave SMTP_HOST blank for console mode

# 3. Run the app
uvicorn app.main:app --reload
# open http://localhost:8000
```

### See it with sample data

```bash
python -m scripts.seed_demo     # creates a conjoint + a Van Westendorp demo,
                                # each with 60 simulated responses
# then open the printed /surveys/<id>/results URLs
```

## Front end

A companion Vite + React single-page app lives in [`frontend/`](frontend) — a
daily affirmation with live weather that links over to this survey tool. See
[`frontend/README.md`](frontend/README.md) for develop/build instructions. Set
`VITE_SURVEY_URL` when the survey tool is deployed at a different host than the
front end.

## Deploy (containers)

Sunshine ships with a `Dockerfile`, `docker-compose.yml`, and `Procfile` for
container hosts (Render, Railway, Fly.io, plain Docker). The app is stateful —
its SQLite database lives on a mounted volume — so a container host with a
persistent disk fits better than serverless.

```bash
# Local container, with a named volume for the database
docker compose up --build
# open http://localhost:8000
```

The image runs `uvicorn` and honors `$PORT` (set by most platforms). The
database defaults to `sqlite:////data/sunshine.db`, so mount a persistent volume
at `/data`. For production also set:

- `BASE_URL` — your public URL (used to build invitation links).
- `ADMIN_PASSWORD` — enables admin login (see below).
- `SMTP_*` — to send real invitation email (otherwise console mode).

For heavier traffic, point `DATABASE_URL` at a hosted Postgres instead of SQLite.

## How to run a study

1. **Create a survey** on the home page — choose **Conjoint** or **Van
   Westendorp** and a currency.
2. **Conjoint only:** add attributes & levels (each needs 2+ levels), set the
   design (tasks, options per task, optional "None", and which attribute is the
   *price* attribute for WTP), then **Generate design**. Van Westendorp needs no
   design step and is ready immediately.
3. **Add participants** (paste emails) and click **Send invitations**.
4. Respondents complete the survey via their unique link.
5. Open **View analysis** for results. Conjoint surveys also have a **Market
   simulator**. **Close** the survey when you're done collecting.

## Email configuration

Set these in `.env` (see `.env.example`):

| Variable | Purpose |
| --- | --- |
| `SMTP_HOST` | SMTP server. **Leave blank for console mode** (emails are logged and saved to `dev_outbox/*.eml`). |
| `SMTP_PORT` | `587` for STARTTLS (default) or `465` for implicit SSL. |
| `SMTP_USER` / `SMTP_PASSWORD` | Credentials, if your server requires auth. |
| `SMTP_FROM` | From header, e.g. `Sunshine Surveys <no-reply@you.com>`. |
| `SMTP_USE_TLS` | `true` = STARTTLS (port 587), `false` = implicit SSL (port 465). |
| `BASE_URL` | Public base URL used to build invitation links. |

Works with Gmail, SendGrid, Mailgun, Amazon SES, etc. via standard SMTP.

## Admin authentication

The researcher/admin UI is protected by a browser **login screen** at `/login`
(backed by a signed session cookie), enforced **only when `ADMIN_PASSWORD` is
set**. Signed-out visitors to an admin page are redirected to `/login`; a **Log
out** link appears in the header once signed in. Respondent survey links
(`/survey/<token>`) and `/healthz` are always public.

**Fail closed:** if `ADMIN_PASSWORD` is empty the admin UI has no login, so the
app **refuses to start** rather than expose it. For local development without a
password, set `ALLOW_INSECURE_ADMIN=true` to explicitly allow the open UI.

Changing `ADMIN_PASSWORD` (or `SECRET_KEY`) invalidates all existing sessions,
logging everyone out — useful if you suspect unauthorized access.

Security-relevant actions are written to a `sunshine.audit` log: admin logins
(success and failure, with client IP) and survey creation/deletion.

| Variable | Purpose |
| --- | --- |
| `ADMIN_USER` | Admin username (default `admin`). Change it from the default. |
| `ADMIN_PASSWORD` | Admin password. **Empty = auth disabled** (app won't start unless `ALLOW_INSECURE_ADMIN=true`). Set a long, random value to require login. |
| `ALLOW_INSECURE_ADMIN` | Local dev only. `true` permits the open (no-login) admin UI when `ADMIN_PASSWORD` is empty. Never set in production. |
| `SECRET_KEY` | Optional. Signs the session cookie; defaults to a value derived from `ADMIN_PASSWORD`. Pin a long random value to keep sessions stable across password changes. |

## The methodology, briefly

**Conjoint.** Each respondent completes several **choice tasks**; in each they
pick the profile they prefer (plus an optional "None"). We dummy-code each
profile's levels (the first level of each attribute is the reference, fixed at
utility 0) and fit a conditional/multinomial logit model by maximum likelihood:

```
P(choose j) = exp(xⱼ·β) / Σₖ exp(xₖ·β)
```

The coefficients are **part-worth utilities**; standard errors come from the
inverse observed-information matrix, with t/p/CI derived from them. **Attribute
importance** is each attribute's utility range as a share of the total.
**Willingness-to-pay** divides a level's part-worth by the marginal utility of
money (the slope of utility vs. a numeric price attribute). The **simulator**
turns utilities into logit shares for a set of competing profiles.

This is the standard *aggregate* CBC estimator. Individual-level estimation
(hierarchical Bayes) and D-optimal/balanced designs are natural next steps.

**Van Westendorp.** Each respondent gives four prices (too cheap / cheap /
expensive / too expensive). Cumulative curves over the price range cross at the
Optimal Price Point (too cheap × too expensive), the Indifference Price (cheap ×
expensive), and the bounds of the acceptable range — PMC (too cheap × expensive)
and PME (too expensive × cheap).

## Project layout

```
app/
  main.py            FastAPI app + routes wiring + auth gating
  config.py          Settings (env / .env)
  auth.py            login screen + session-cookie guard for the admin UI
  database.py        SQLAlchemy engine & session
  models.py          ORM: Survey, Attribute, Level, Task, Concept, Participant,
                     Response, PricePerception
  design.py          CBC choice-design generation
  analysis.py        MNL estimation, importance, significance, WTP, share simulation
  van_westendorp.py  Price Sensitivity Meter curves & intersection points
  email_utils.py     SMTP delivery + console/dev fallback
  services.py        Bridges ORM <-> engines
  routes/            admin.py (researcher UI), survey.py (respondent UI)
  templates/         Jinja2 HTML
scripts/seed_demo.py   Conjoint + Van Westendorp demo data with simulated responses
tests/                 Design, analysis (recovers known utilities & price points),
                       auth, and end-to-end tests
```

## Tests

```bash
pytest
```

The analysis tests simulate choices from known preferences and confirm the
estimator recovers them (and that Van Westendorp recovers a known price point);
the app tests drive the full create → invite → respond → analyze flow for both
survey types, plus admin auth and the market simulator.
