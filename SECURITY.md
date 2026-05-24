# Security Policy

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.  
Email **security@clozehive.com** with:
- A description of the issue and its potential impact
- Steps to reproduce (proof-of-concept if available)
- Affected version / component

We aim to acknowledge reports within 48 hours and release a fix within 14 days.

---

## Known Credential Exposure — IMMEDIATE ACTION REQUIRED

The credentials below were previously committed to this repository and **must be treated as compromised**. Rotate them immediately even if the commit is no longer on the default branch.

| Credential | Where to rotate |
|---|---|
| `JWT_SECRET` | Generate a new 64-char secret (`openssl rand -hex 32`). Update in all deployment envs. All existing refresh tokens are invalidated automatically on restart. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google Cloud Console → APIs & Services → Credentials → delete and recreate the OAuth 2.0 client. |
| `OPENAI_API_KEY` (`sk-proj-uZ703...`) | OpenAI Platform → API keys → revoke and generate a new key. |
| `ANTHROPIC_API_KEY` (`sk-ant-api03-...`) | Anthropic Console → API keys → revoke and generate a new key. |
| `LANGSMITH_API_KEY` (`lsv2_pt_...`) | LangSmith → Settings → API keys → revoke and regenerate. |
| `OPENWEATHER_API_KEY` | OpenWeatherMap → My API keys → regenerate. |
| `REMBG_API_KEY` | Your remove.bg account → API keys → regenerate. |
| GCP Service Account (`gcp-sa.json`) | Google Cloud Console → IAM → Service Accounts → `clozehive` project → Keys → delete the exposed key and create a new one. Download the new JSON and store it **only in your secrets manager**, never in the repo. |

---

## Removing Secrets from Git History

Use [`git-filter-repo`](https://github.com/newren/git-filter-repo) (recommended over BFG):

```bash
# Install
pip install git-filter-repo

# Remove .env files from history
git filter-repo --path services/api-gateway/.env --invert-paths
git filter-repo --path .env --invert-paths

# Remove gcp-sa.json from history
git filter-repo --path gcp-sa.json --invert-paths

# Force-push all branches (coordinate with teammates first)
git push origin --force --all
git push origin --force --tags
```

After this, **all collaborators must re-clone** the repository. Cached GitHub Pages / CDN copies can be invalidated by contacting GitHub support.

---

## Secret Management Rules

1. **Never commit secrets.** The root `.gitignore` blocks `.env`, `gcp-sa.json`, and similar patterns. Run `git status` before every commit.
2. **Use `.env.example` as the template.** It contains only placeholder values. Copy it to `.env` locally and fill in real values.
3. **Production deployments** should inject secrets via environment variables from a secrets manager (AWS Secrets Manager, GCP Secret Manager, Doppler, etc.). Never write a real `.env` to a container image.
4. **GCP credentials** must be passed via the `GCS_CREDENTIALS_JSON` environment variable (base-64 encoded JSON) or via Workload Identity — never as a file on disk in production.
5. **Rotate secrets on personnel changes.** If a team member with access to secrets leaves, rotate all shared credentials immediately.

---

## Secret Scanning

Enable automatic scanning on every push:

- **GitHub**: Settings → Code security → Secret scanning → Enable. Also enable "Push protection" to block secrets before they land in history.
- **Pre-commit hook** (optional): install [`detect-secrets`](https://github.com/Yelp/detect-secrets) and add it to `.pre-commit-config.yaml`.

---

## Environment-specific Cookie Settings

The refresh-token HttpOnly cookie is configured by three env vars:

| Variable | Development | Production |
|---|---|---|
| `COOKIE_SECURE` | `false` | `true` (HTTPS only) |
| `COOKIE_SAMESITE` | `Lax` | `Strict` |
| `COOKIE_DOMAIN` | *(blank)* | `yourdomain.com` |

---

## Security Hardening Completed

| # | Fix | Status |
|---|---|---|
| 1 | Refresh token moved to HttpOnly cookie | ✅ Done |
| 2 | LLM prompt-injection sanitizer (`llm_safety.py`) | ✅ Done |
| 3 | Password-reset flow (forgot + reset endpoints + pages) | ✅ Done |
| 4 | `.env` & `gcp-sa.json` in `.gitignore`, `.env.example` updated | ✅ Done |
| 5 | GCS cleanup on account deletion | ✅ Done |
| 6 | GitHub Actions CI (build + lint + unit tests) | ✅ Done |
