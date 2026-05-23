# SpecLint

SpecLint treats product requirements like code. Paste a feature spec and it emits compiler-style warnings for ambiguity, missing edge cases, unverifiable claims, permission gaps, lifecycle gaps, data constraints, failure modes, acceptance tests, and a tighter rewritten spec.

The goal is not to generate code. The goal is to catch vague thinking before code exists.

## What It Does

- Extracts actors, entities, actions, states, and explicit rules
- Flags ambiguous or unverifiable language
- Detects missing permission boundaries and lifecycle states
- Generates edge cases and Given/When/Then acceptance tests
- Produces a traceability map from requirements to tests and open questions
- Rewrites the spec into a more build-ready version

## Run Locally

```powershell
python -m uvicorn backend.app.main:app --reload --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Deploy

Netlify can serve the static frontend, but it does not run the FastAPI server.

- Connect the repo to Netlify and keep `netlify.toml` at the repo root.
- Netlify publishes `frontend/` and rewrites `/` to `frontend/static/index.html`.
- Deploy the FastAPI backend on Render, then set `SPECLINT_API_BASE_URL` in Netlify to the Render service origin.

Example Netlify value:

```text
SPECLINT_API_BASE_URL=https://speclint-api.onrender.com
```

For Netlify Drop, uploading `frontend/` is cleanest. Uploading the whole repository also works because the root `_redirects` file points Netlify to the static app.

### Render Backend

Render can deploy the FastAPI backend from this same GitHub repository. The root `render.yaml` file defines a free Python Web Service with:

```text
Build command: pip install -r requirements.txt
Start command: python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
Health check: /api/health
```

If creating the service manually in Render, use:

```text
Service type: Web Service
Runtime: Python 3
Branch: main
Build command: pip install -r requirements.txt
Start command: python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
Instance type: Free
```

After the Render deployment succeeds, verify:

```text
https://your-service.onrender.com/api/health
```

Expected response:

```text
{"status":"ok","app":"SpecLint"}
```

Then set Netlify's `SPECLINT_API_BASE_URL` environment variable to the Render origin, without a trailing slash, and redeploy Netlify.

## Stack

- FastAPI backend
- Vanilla HTML, CSS, and JavaScript frontend
- Deterministic Python analyzer, no API key required
- `unittest` + FastAPI `TestClient` for tests

## API

- `GET /api/health`
- `GET /api/examples`
- `POST /api/analyze`

Example request:

```json
{
  "title": "Workspace invites",
  "spec_text": "Users can invite teammates to a workspace. Guests can view projects.",
  "strictness": "balanced"
}
```

## Project Shape

- `backend/app/analyzer.py` contains the deterministic compiler-style analysis passes.
- `backend/app/models.py` defines the public API schema.
- `frontend/static/` contains the single-page interface.
- `tests/test_speclint.py` covers the core analysis and API response.

SpecLint is intentionally offline-first for the MVP. A later version can add an LLM pass, but the current version already gives stable, explainable reports without API keys.
