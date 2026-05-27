# SpecLint

SpecLint is a simple web app that helps people write better product requirements before development starts.

A product requirement is the note that explains what a feature should do. The problem is that many requirements sound clear at first, but they still miss important details like permissions, edge cases, error handling, or what should happen after a user takes an action.

SpecLint reads that requirement and gives feedback, almost like a spell checker for product specs.

## What The Project Does

SpecLint helps turn a rough feature idea into something easier for a developer, designer, or product manager to understand.

It can:

- Find unclear words like "simple", "fast", "safe", or "easy"
- Point out missing edge cases and failure situations
- Check if user roles and permissions are not explained well
- Give the spec a score out of 100
- Show issues by severity, from low to critical
- Generate acceptance tests in a Given/When/Then format
- Rewrite the requirement into a cleaner version
- Keep a short run history so the user can compare improvements
- Save product decisions when a warning needs a team call
- Let users accept a warning with an owner, reason, and expiry date
- Store accepted risks in a backend decision log
- Support both light theme and dark theme

The goal is not to replace thinking. The goal is to help catch weak spots before they become bugs later.

## Why I Built It

When a feature is not explained clearly, the team can build the wrong thing even if the code is good. A small missing detail in the requirement can become a big problem during development.

SpecLint tries to solve that by asking:

- Who is allowed to do this?
- What happens if something fails?
- What should the system do after the action is complete?
- Are there any security or permission problems?
- Can this requirement actually be tested?

This makes the spec more useful before anyone starts building.

## How To Use It

1. Enter a title for the feature.
2. Paste or write the product requirement.
3. Choose a strictness mode.
4. Click Analyze.
5. Read the score, issues, acceptance tests, and rewritten spec.
6. Improve the requirement and run it again.

There are three strictness modes:

- Lenient: best for early ideas
- Balanced: best for normal planning
- Ruthless: best before handing the spec to engineers

## Example

Input:

```text
Users can invite teammates to a workspace. Guests can view projects.
```

SpecLint may point out that the requirement does not explain:

- Who is allowed to invite people
- What happens if an invite expires
- Whether guests can edit or only view
- What tests should prove the feature works

Then it suggests a clearer version of the spec.

## Run The Project Locally

First, make sure Python is installed. Then run:

```powershell
python -m uvicorn backend.app.main:app --reload --port 8000
```

Open this in the browser:

```text
http://127.0.0.1:8000
```

## Deploying The Project

The project has two parts:

- The frontend, which is the page the user sees
- The backend, which checks the spec and sends back the results

Netlify can host the frontend. Render can host the backend.

For Netlify:

- Keep `netlify.toml` in the project root
- Publish the `frontend/` folder
- Set `SPECLINT_API_BASE_URL` to the Render backend URL

Example:

```text
SPECLINT_API_BASE_URL=https://speclint-api.onrender.com
```

For Render, use these settings:

```text
Build command: pip install -r requirements.txt
Start command: python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
Health check: /api/health
```

After deployment, this URL should return a simple health response:

```text
https://your-service.onrender.com/api/health
```

Expected response:

```json
{"status":"ok","app":"SpecLint"}
```

## Tech Used

SpecLint uses:

- FastAPI for the backend
- HTML, CSS, and JavaScript for the frontend
- Python logic for analyzing requirements
- SQLite for the decision log
- Unit tests to check that the main features still work

It does not need an API key or an online AI model for the current version. The analysis is built into the project.

## Project Structure

```text
backend/app/        Main backend code
backend/data/       Local database storage
frontend/static/    Web page, styles, and browser logic
tests/              Project tests
schema.sql          Database starter file
netlify.toml        Netlify setup
render.yaml         Render setup
```

## API Routes

These are the main backend routes:

```text
GET  /api/health
GET  /api/examples
POST /api/analyze
GET  /api/suppressions
POST /api/suppressions
PATCH /api/suppressions/{id}/reconfirm
PATCH /api/suppressions/{id}/reopen
GET  /api/decisions
POST /api/decisions
PATCH /api/decisions/{id}/reconfirm
PATCH /api/decisions/{id}/reopen
GET  /api/decisions/export
```

Most users do not need to call these directly. The website uses them in the background to analyze specs, keep the accepted-risk log in sync, save requirement decisions, and mark older decisions as needing review when the spec text changes in a meaningful way.

## Current Status

SpecLint is an MVP, which means it is a working first version. It already gives useful feedback without needing any paid API. A future version could add an AI review step, but the current version is meant to stay simple, fast, and explainable.

The decision log now keeps accepted risks and product decisions attached to spec versions. If only punctuation or casing changes, SpecLint keeps the decision active. If the actual evidence text changes, it marks that decision as `pending_review` so the owner can reconfirm it or reopen the warning.
