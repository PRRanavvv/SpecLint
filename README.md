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

