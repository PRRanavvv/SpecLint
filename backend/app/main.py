from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .analyzer import analyze_spec
from .models import ExampleSpec, SpecAnalysisRequest, SpecAnalysisResponse


ROOT = Path(__file__).resolve().parents[2]
STATIC_PATH = ROOT / "frontend" / "static"

app = FastAPI(
    title="SpecLint API",
    description="A compiler-style linter for ambiguous product specs.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_PATH.exists():
    app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")


EXAMPLES = [
    ExampleSpec(
        title="Workspace invites",
        spec_text=(
            "Users can invite teammates to a workspace. Guests can view projects. "
            "The invite should be easy to accept and should work quickly."
        ),
    ),
    ExampleSpec(
        title="Data export",
        spec_text=(
            "Users should be able to export all data. The export should be fast and simple. "
            "Admins can see previous exports."
        ),
    ),
    ExampleSpec(
        title="Project deletion",
        spec_text=(
            "Project owners can delete projects. All project data is removed unless billing records must be kept. "
            "The user gets a confirmation."
        ),
    ),
]


@app.get("/")
def index() -> FileResponse:
    index_path = STATIC_PATH / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend static files are missing.")
    return FileResponse(index_path)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": "SpecLint"}


@app.get("/api/examples", response_model=list[ExampleSpec])
def examples() -> list[ExampleSpec]:
    return EXAMPLES


@app.post("/api/analyze", response_model=SpecAnalysisResponse)
def analyze(request: SpecAnalysisRequest) -> SpecAnalysisResponse:
    return analyze_spec(
        title=request.title,
        spec_text=request.spec_text,
        strictness=request.strictness,
    )

