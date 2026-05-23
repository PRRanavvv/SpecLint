from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .analyzer import SpecInputError, analyze_spec
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
        title="Transfer workspace ownership",
        spec_text=(
            "Workspace admins can transfer ownership to another member. "
            "The current owner should confirm the transfer and the new owner gets notified. "
            "The transfer should be simple and safe."
        ),
    ),
    ExampleSpec(
        title="Two-factor authentication setup",
        spec_text=(
            "Users can enable two-factor authentication from account settings. "
            "They scan a QR code and enter a verification code. "
            "The setup should be secure and easy to recover from."
        ),
    ),
    ExampleSpec(
        title="Password reset flow",
        spec_text=(
            "Users can reset their password by entering their email address. "
            "If the account exists, send a reset link. "
            "The link should expire and the process should prevent abuse."
        ),
    ),
    ExampleSpec(
        title="Connect GitHub repository",
        spec_text=(
            "Workspace admins can connect a GitHub repository to a project. "
            "The app imports pull requests and issues after authorization. "
            "The connection should be fast, reliable, and easy to disconnect."
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
    try:
        return analyze_spec(
            title=request.title,
            spec_text=request.spec_text,
            source_spec_text=request.source_spec_text,
            strictness=request.strictness,
        )
    except SpecInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
