from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Strictness(str, Enum):
    lenient = "lenient"
    balanced = "balanced"
    ruthless = "ruthless"


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class SuppressionStatus(str, Enum):
    active = "active"
    expired = "expired"
    pending_review = "pending_review"
    reopened = "reopened"


class DecisionStatus(str, Enum):
    decided = "decided"
    pending_review = "pending_review"
    reopened = "reopened"


class IssueType(str, Enum):
    ambiguity = "ambiguity"
    missing_edge_case = "missing_edge_case"
    unverifiable_claim = "unverifiable_claim"
    permission_gap = "permission_gap"
    consent_gap = "consent_gap"
    lifecycle_gap = "lifecycle_gap"
    data_constraint_gap = "data_constraint_gap"
    failure_mode_gap = "failure_mode_gap"
    contradiction = "contradiction"


class SpecAnalysisRequest(BaseModel):
    title: str = Field(default="Untitled spec", max_length=140)
    spec_text: str = Field(min_length=20, max_length=12000)
    source_spec_text: str | None = Field(default=None, max_length=12000)
    strictness: Strictness = Strictness.balanced


class SpecIssue(BaseModel):
    id: str
    type: IssueType
    severity: Severity
    title: str
    evidence: str
    why_it_matters: str
    suggestion: str
    test_prompt: str


class ScorePenalty(BaseModel):
    severity: Severity
    count: int
    weight: int
    subtotal: float


class ScoreBreakdown(BaseModel):
    base_score: int = 100
    strictness: Strictness
    strictness_multiplier: float
    weights: dict[Severity, int]
    penalties: list[ScorePenalty] = Field(default_factory=list)
    total_penalty: float
    explanation: str


class CategoryDoc(BaseModel):
    type: IssueType
    label: str
    checks_for: str


class ExtractedIntent(BaseModel):
    actors: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    explicit_rules: list[str] = Field(default_factory=list)


class EdgeCase(BaseModel):
    title: str
    scenario: str
    expected_behavior: str


class AcceptanceTest(BaseModel):
    id: str
    name: str
    given: str
    when: str
    then: str
    covers_issue_ids: list[str] = Field(default_factory=list)


class TraceItem(BaseModel):
    requirement: str
    tests: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class SpecAnalysisResponse(BaseModel):
    spec_version_id: str | None = None
    title: str
    verdict: Literal["compiles", "compiles_with_warnings", "does_not_compile"]
    score: int = Field(ge=0, le=100)
    score_breakdown: ScoreBreakdown
    severity_counts: dict[Severity, int]
    category_docs: list[CategoryDoc]
    strictness_note: str
    summary: str
    intent: ExtractedIntent
    issues: list[SpecIssue] = Field(default_factory=list)
    edge_cases: list[EdgeCase] = Field(default_factory=list)
    acceptance_tests: list[AcceptanceTest] = Field(default_factory=list)
    traceability: list[TraceItem] = Field(default_factory=list)
    rewritten_spec: str


class ExampleSpec(BaseModel):
    title: str
    spec_text: str


class SuppressionCreateRequest(BaseModel):
    spec_version_id: str = Field(default="local", max_length=80)
    issue_id: str = Field(max_length=80)
    issue_type: IssueType
    severity: Severity
    issue_title: str = Field(max_length=180)
    evidence_snapshot: str = Field(max_length=600)
    evidence_hash: str | None = Field(default=None, max_length=80)
    owner: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=600)
    expires_at: date
    created_by: str | None = Field(default=None, max_length=120)

    @field_validator("expires_at")
    @classmethod
    def expiry_must_not_be_past(cls, value: date) -> date:
        if value < date.today():
            raise ValueError("expires_at must not be in the past")
        return value


class SuppressionReopenRequest(BaseModel):
    reopened_by: str = Field(default="Unknown", max_length=120)
    reopened_reason: str | None = Field(default=None, max_length=600)


class ReviewResolutionRequest(BaseModel):
    reviewed_by: str = Field(default="Unknown", max_length=120)
    review_note: str | None = Field(default=None, max_length=600)


class SuppressionRecord(BaseModel):
    id: str
    spec_version_id: str
    issue_id: str
    issue_type: IssueType
    severity: Severity
    issue_title: str
    evidence_snapshot: str
    evidence_hash: str
    raw_evidence_hash: str
    normalized_evidence_hash: str
    owner: str
    reason: str
    expires_at: date
    status: SuppressionStatus
    created_by: str
    created_at: datetime
    reopened_by: str | None = None
    reopened_at: datetime | None = None
    reopened_reason: str | None = None


class DecisionCreateRequest(BaseModel):
    spec_version_id: str = Field(default="local", max_length=80)
    issue_id: str = Field(max_length=80)
    issue_type: IssueType
    severity: Severity
    issue_title: str = Field(max_length=180)
    evidence_snapshot: str = Field(max_length=600)
    evidence_hash: str | None = Field(default=None, max_length=80)
    owner: str = Field(min_length=1, max_length=120)
    decision_note: str = Field(min_length=1, max_length=800)
    created_by: str | None = Field(default=None, max_length=120)


class DecisionRecord(BaseModel):
    id: str
    spec_version_id: str
    issue_id: str
    issue_type: IssueType
    severity: Severity
    issue_title: str
    evidence_snapshot: str
    evidence_hash: str
    raw_evidence_hash: str
    normalized_evidence_hash: str
    owner: str
    decision_note: str
    status: DecisionStatus
    created_by: str
    created_at: datetime
    reopened_by: str | None = None
    reopened_at: datetime | None = None
    reopened_reason: str | None = None
