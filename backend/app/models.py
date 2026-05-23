from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Strictness(str, Enum):
    lenient = "lenient"
    balanced = "balanced"
    ruthless = "ruthless"


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class IssueType(str, Enum):
    ambiguity = "ambiguity"
    missing_edge_case = "missing_edge_case"
    unverifiable_claim = "unverifiable_claim"
    permission_gap = "permission_gap"
    lifecycle_gap = "lifecycle_gap"
    data_constraint_gap = "data_constraint_gap"
    failure_mode_gap = "failure_mode_gap"
    contradiction = "contradiction"


class SpecAnalysisRequest(BaseModel):
    title: str = Field(default="Untitled spec", max_length=140)
    spec_text: str = Field(min_length=20, max_length=12000)
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
