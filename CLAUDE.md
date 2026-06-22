# Sunshine — project guide for Claude

Sunshine is a FastAPI survey tool (conjoint, Van Westendorp, rating/ranking,
MaxDiff) with a researcher/admin UI and token-based respondent links. Tests run
with `pytest` (the FastAPI `TestClient` drives full flows).

## Security baseline

Apply this baseline proactively when adding features or scaffolding new
surfaces. Note in your summary which items you applied or deliberately skipped.

1. **Keep secrets out of git.** Credentials live in environment variables, never
   in code or committed files. `.gitignore` already covers `.env` / `.env.*`
   (keeping `*.env.example` templates), keys, credential JSON, and databases.
   Keep `.env.example` blank-valued.
2. **Fail closed on auth.** The admin UI requires login whenever `ADMIN_PASSWORD`
   is set, and the app **refuses to start** with an empty password unless
   `ALLOW_INSECURE_ADMIN=true` (local dev only) — see `app/main.py` lifespan and
   `app/auth.py`. Any new privileged surface must be auth-gated the same way; do
   not add a silent open mode.
3. **Secret-scanning pre-commit.** `.pre-commit-config.yaml` runs gitleaks; keep
   it working and pinned.
4. **Audit security-relevant actions.** Admin logins (success/failure, with IP)
   and survey create/delete are logged via `app/audit.py`. Route new destructive
   or admin actions through `audit.record(...)`.
5. **Least exposure.** Never echo secrets in logs or errors. Session cookies are
   `HttpOnly` + `SameSite`; prefer `Secure` + HTTPS in production. Respondent
   links use unguessable tokens — keep them that way.

These are defaults, not mandates — if a change clearly calls for something
different, say so and adapt.
