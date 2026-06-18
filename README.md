# ☀ Sunshine

A self-contained survey tool for **Choice-Based Conjoint (CBC) analysis** with
participant email invitations. Build a study, auto-generate the choice design,
invite respondents by email, collect their choices through a web survey, and
estimate part-worth utilities and attribute importance — all in one FastAPI app.

## What it does

- **Design a study** — define attributes (e.g. *Price*, *Brand*, *Size*) and
  their levels.
- **Auto-generate a CBC design** — randomized choice tasks with a configurable
  number of options per task and an optional "None of these" alternative.
- **Invite participants by email** — each respondent gets a unique survey link.
  Works with any SMTP provider, or runs in a no-credentials *console mode* for
  local development.
- **Collect responses** — a clean, mobile-friendly web survey presents one
  choice task at a time.
- **Analyze** — aggregate **multinomial logit (MNL)** estimation produces
  part-worth utilities (with standard errors), relative attribute importance,
  and model fit (McFadden pseudo-R²). Includes a share-of-preference simulator.

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
python -m scripts.seed_demo     # creates a demo study + 60 simulated responses
# then open the printed /surveys/<id>/results URL
```

## How to run a real study

1. **Create a survey** on the home page.
2. **Add attributes & levels** (each attribute needs at least two levels).
3. **Set the design** — number of choice tasks, options per task, and whether to
   include a "None" option — then **Generate design**.
4. **Add participants** (paste emails) and click **Send invitations**.
5. Respondents complete the survey via their unique link.
6. Open **View analysis** for utilities and importance. **Close** the survey
   when you're done collecting.

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

## The methodology, briefly

Each respondent completes several **choice tasks**; in each they pick the option
they prefer from a set of profiles (plus an optional "None"). We dummy-code each
profile's attribute levels (the first level of each attribute is the reference,
fixed at utility 0) and fit a conditional/multinomial logit model by maximum
likelihood:

```
P(choose j) = exp(xⱼ·β) / Σₖ exp(xₖ·β)
```

The estimated coefficients are **part-worth utilities**. **Attribute importance**
is the utility range of each attribute as a share of the total range. Standard
errors come from the inverse observed-information matrix.

This is the standard *aggregate* CBC estimator. Individual-level estimation
(hierarchical Bayes) and D-optimal/balanced designs are natural next steps.

## Project layout

```
app/
  main.py          FastAPI app + routes wiring
  config.py        Settings (env / .env)
  database.py      SQLAlchemy engine & session
  models.py        ORM: Survey, Attribute, Level, Task, Concept, Participant, Response
  design.py        CBC choice-design generation
  analysis.py      Multinomial-logit estimation, importance, share simulation
  email_utils.py   SMTP delivery + console/dev fallback
  services.py      Bridges ORM <-> engine
  routes/          admin.py (researcher UI), survey.py (respondent UI)
  templates/       Jinja2 HTML
scripts/seed_demo.py   Demo data with simulated responses
tests/             Design, analysis (recovers known utilities), and end-to-end tests
```

## Tests

```bash
pytest
```

The analysis tests simulate choices from known preferences and confirm the
estimator recovers them; the app test drives the full create → invite → respond
→ analyze flow.
