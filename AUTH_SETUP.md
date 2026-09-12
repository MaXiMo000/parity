# Setting up real GitHub OAuth for parity

Registering a GitHub OAuth App requires your own GitHub account — this is
the one step in Phase 3a that can't be automated.

## 1. Register the app

1. Go to <https://github.com/settings/developers> → **OAuth Apps** → **New OAuth App**.
2. **Application name**: `parity (dev)` (anything you like — it's only shown on GitHub's consent screen).
3. **Homepage URL**: `http://localhost:5173`
4. **Authorization callback URL**: `http://localhost:8123/api/auth/github/callback`
   — this must match `GITHUB_CALLBACK_URL` below *exactly*, including the port.
5. Click **Register application**.
6. Copy the **Client ID**.
7. Click **Generate a new client secret**, copy it immediately (GitHub only shows it once).

## 2. Set the real environment variables

Before starting the backend, export these (or add them to however you already set `DATABASE_URL`):

```bash
export GITHUB_CLIENT_ID="<the real client id from step 1>"
export GITHUB_CLIENT_SECRET="<the real client secret from step 1>"
export GITHUB_CALLBACK_URL="http://localhost:8123/api/auth/github/callback"
export SESSION_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export FRONTEND_ORIGIN="http://localhost:5173"
```

`SESSION_SECRET_KEY` signs the session cookie — generate a real random
one (the command above does this for you); never reuse the app's own
`dev-only-insecure-secret-change-before-any-real-deploy` default outside
local dev with no real OAuth app registered.

## 3. Run it and sign in for real

```bash
cd backend && docker compose up -d
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/alembic upgrade head
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/uvicorn app.main:app --port 8123

cd frontend && npm run dev
```

Open `http://localhost:5173`, click **Sign in with GitHub**, approve the
real consent screen, and confirm you land back in the app with your real
GitHub username showing in the top bar.

## Generating a FERNET_KEY (for encrypted credential storage, Phase 3b)

```bash
export FERNET_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

Like `SESSION_SECRET_KEY`, this is required at boot in every environment
(dev included) — there is no default. Unlike a session secret, rotating
this key permanently locks you out of any credential already stored
under the old one (SPEC.md §12) — generate it once and keep it, the same
discipline as any real secrets-manager key.
