from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .analyzer import SpecInputError, analyze_spec
from .models import (
    DecisionCreateRequest,
    DecisionRecord,
    DecisionStatus,
    ExampleSpec,
    ReviewResolutionRequest,
    SpecAnalysisRequest,
    SpecAnalysisResponse,
    SuppressionCreateRequest,
    SuppressionRecord,
    SuppressionReopenRequest,
    SuppressionStatus,
)
from .storage import (
    create_decision,
    create_suppression,
    decisions_markdown,
    list_decisions,
    list_suppressions,
    reconfirm_decision,
    reconfirm_suppression,
    reopen_decision,
    reopen_suppression,
    save_spec_version,
)


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
        report = analyze_spec(
            title=request.title,
            spec_text=request.spec_text,
            source_spec_text=request.source_spec_text,
            strictness=request.strictness,
        )
        report.spec_version_id = save_spec_version(
            report,
            title=request.title,
            spec_text=request.spec_text,
            strictness=request.strictness,
        )
        return report
    except SpecInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/suppressions", response_model=list[SuppressionRecord])
def suppressions(
    spec_version_id: str | None = None,
    status: SuppressionStatus | None = None,
) -> list[SuppressionRecord]:
    return list_suppressions(spec_version_id=spec_version_id, status=status)


@app.post("/api/suppressions", response_model=SuppressionRecord)
def suppress(payload: SuppressionCreateRequest) -> SuppressionRecord:
    return create_suppression(payload)


@app.patch("/api/suppressions/{suppression_id}/reopen", response_model=SuppressionRecord)
def reopen(
    suppression_id: str,
    payload: SuppressionReopenRequest,
) -> SuppressionRecord:
    record = reopen_suppression(suppression_id, payload)
    if not record:
        raise HTTPException(status_code=404, detail="Suppression not found.")
    return record


@app.patch("/api/suppressions/{suppression_id}/reconfirm", response_model=SuppressionRecord)
def reconfirm_suppression_review(
    suppression_id: str,
    payload: ReviewResolutionRequest,
) -> SuppressionRecord:
    record = reconfirm_suppression(suppression_id, payload)
    if not record:
        raise HTTPException(status_code=404, detail="Suppression not found.")
    return record


@app.get("/api/decisions", response_model=list[DecisionRecord])
def decisions(
    spec_version_id: str | None = None,
    status: DecisionStatus | None = None,
) -> list[DecisionRecord]:
    return list_decisions(spec_version_id=spec_version_id, status=status)


@app.post("/api/decisions", response_model=DecisionRecord)
def decide(payload: DecisionCreateRequest) -> DecisionRecord:
    return create_decision(payload)


@app.patch("/api/decisions/{decision_id}/reconfirm", response_model=DecisionRecord)
def reconfirm_decision_review(
    decision_id: str,
    payload: ReviewResolutionRequest,
) -> DecisionRecord:
    record = reconfirm_decision(decision_id, payload)
    if not record:
        raise HTTPException(status_code=404, detail="Decision not found.")
    return record


@app.patch("/api/decisions/{decision_id}/reopen", response_model=DecisionRecord)
def reopen_decision_review(
    decision_id: str,
    payload: SuppressionReopenRequest,
) -> DecisionRecord:
    record = reopen_decision(decision_id, payload)
    if not record:
        raise HTTPException(status_code=404, detail="Decision not found.")
    return record


@app.get("/api/decisions/export", response_class=PlainTextResponse)
def export_decisions(spec_version_id: str | None = None) -> str:
    return decisions_markdown(spec_version_id=spec_version_id)
