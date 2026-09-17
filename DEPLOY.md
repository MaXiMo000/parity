# Deploying parity (Phase 3c)

This is a real split-origin deploy: the backend and frontend live on two
different domains (Render assigns each service its own subdomain), not
one shared origin the way local dev's Vite proxy fakes it. That's the
one topology decision `render.yaml` makes concrete — see its own header
comment for why.

## 1. One-time manual steps (nobody else can do these for you)

1. **Register a real GitHub OAuth App** for production, separate from
   any dev app you made following `AUTH_SETUP.md` — a production
   callback URL is a different registration, not a field you edit on the
   dev one. Homepage URL = your real `parity-frontend` URL; Authorization
   callback URL = `https://<your-backend-domain>/api/auth/github/callback`.
2. **Generate the two real secrets** (do this once, store them somewhere
   real — a password manager, not a scratch file):
   ```bash
   python3 -c 'import secrets; print(secrets.token_urlsafe(32))'          # SESSION_SECRET_KEY
   python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'  # FERNET_KEY
   ```
   `FERNET_KEY` can never be rotated without permanently locking out
   every credential already stored under the old one (SPEC.md §12) —
   generate it once, keep it safe, treat it like any other production
   secret.

## 2. Deploy the blueprint

In the Render dashboard: **New +** → **Blueprint**, point it at this
repo. Render reads `render.yaml` and creates:

- `parity-db` — managed Postgres.
- `parity-backend` — the FastAPI web service. Its build command runs
  `alembic upgrade head` for you on every deploy, so migrations are
  never a separate manual step.
- `parity-frontend` — the Vite static site.

## 3. Fill in the values `render.yaml` deliberately leaves blank

`sync: false` in `render.yaml` means Render won't manage these for you —
set each one once in the dashboard, under each service's **Environment**
tab:

| Service | Variable | Value |
|---|---|---|
| `parity-backend` | `SESSION_SECRET_KEY` | from step 1 above |
| `parity-backend` | `FERNET_KEY` | from step 1 above |
| `parity-backend` | `GITHUB_CLIENT_ID` | from your production OAuth app |
| `parity-backend` | `GITHUB_CLIENT_SECRET` | from your production OAuth app |
| `parity-backend` | `GITHUB_CALLBACK_URL` | `https://<parity-backend real URL>/api/auth/github/callback` |
| `parity-backend` | `FRONTEND_ORIGIN` | `https://<parity-frontend real URL>` (exact, no trailing slash — it's matched literally for CORS) |
| `parity-frontend` | `VITE_API_BASE_URL` | `https://<parity-backend real URL>` (no trailing slash) |

Render assigns each service's real `onrender.com` URL on its first
deploy — you'll only know both real values after that first deploy, so
the order is: deploy once (it'll come up half-broken, OAuth-wise), fill
in the table above with the real URLs Render assigned, then redeploy
both services once (`FRONTEND_ORIGIN`/`GITHUB_CALLBACK_URL` are read at
backend boot; `VITE_API_BASE_URL` is baked into the frontend's build
output at build time — a dashboard edit alone doesn't retroactively
change an already-built bundle, the frontend service needs a fresh
build).

`PARITY_ENV=production` (already set by `render.yaml`, not something you
set yourself) is what makes the missing values above a boot-time
`RuntimeError` instead of a confusing first-request 500 — see
`backend/app/main.py`'s own startup checks.

## 4. Verify it for real

1. Open the real `parity-frontend` URL. You should see the "Sign in with
   GitHub" gate, not a blank page or a CORS error in the console.
2. Click through the real GitHub consent screen for your production OAuth
   app. You should land back in the app with your real GitHub username in
   the top bar.
3. Create a real workspace against a real public API (e.g.
   `https://petstore3.swagger.io/api/v3/openapi.json`) and confirm the 3D
   graph renders and Send produces a real result.

If step 1 shows a CORS error instead of the sign-in gate, `FRONTEND_ORIGIN`
on the backend doesn't exactly match the frontend's real URL (scheme,
host, and no trailing slash all have to match — `CORSMiddleware` checks
it literally, per `backend/app/main.py`).

## Free-tier note

Render's free web-service plan spins down after inactivity — the first
request after a while sleeping will be slow (a real cold start), not
broken. This is a Render platform behavior, not something this project's
own code can paper over on the free tier.
