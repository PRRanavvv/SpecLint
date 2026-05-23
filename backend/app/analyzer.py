from __future__ import annotations

import re

from .models import (
    AcceptanceTest,
    CategoryDoc,
    EdgeCase,
    ExtractedIntent,
    IssueType,
    ScoreBreakdown,
    ScorePenalty,
    Severity,
    SpecAnalysisResponse,
    SpecIssue,
    Strictness,
    TraceItem,
)
from .text_utils import compact_quote, contains_any, split_sentences, stable_id, tokenize, top_terms


ACTORS = {
    "admin",
    "admins",
    "buyer",
    "customer",
    "customers",
    "guest",
    "guests",
    "manager",
    "member",
    "members",
    "moderator",
    "owner",
    "owners",
    "seller",
    "staff",
    "teammate",
    "teammates",
    "user",
    "users",
}

ENTITIES = {
    "account",
    "accounts",
    "comment",
    "comments",
    "data",
    "email",
    "emails",
    "file",
    "files",
    "invite",
    "invites",
    "invitation",
    "invitations",
    "invoice",
    "invoices",
    "message",
    "messages",
    "notification",
    "notifications",
    "order",
    "orders",
    "payment",
    "payments",
    "profile",
    "project",
    "projects",
    "report",
    "reports",
    "role",
    "roles",
    "task",
    "tasks",
    "team",
    "teams",
    "workspace",
    "workspaces",
}

ACTION_TERMS = {
    "accept",
    "add",
    "approve",
    "archive",
    "assign",
    "cancel",
    "change",
    "create",
    "delete",
    "download",
    "edit",
    "export",
    "invite",
    "join",
    "login",
    "pay",
    "publish",
    "remove",
    "reset",
    "restore",
    "send",
    "share",
    "sign",
    "submit",
    "update",
    "upload",
    "view",
}

STATE_TERMS = {
    "accepted",
    "active",
    "archived",
    "cancelled",
    "deleted",
    "disabled",
    "draft",
    "expired",
    "failed",
    "inactive",
    "invited",
    "locked",
    "paid",
    "pending",
    "published",
    "refunded",
    "rejected",
    "removed",
    "sent",
    "shipped",
    "suspended",
}

VAGUE_TERMS = {
    "appropriate",
    "as needed",
    "clean",
    "easy",
    "eventually",
    "fast",
    "friendly",
    "good",
    "intuitive",
    "later",
    "maybe",
    "nice",
    "normal",
    "probably",
    "quickly",
    "relevant",
    "seamless",
    "simple",
    "smart",
    "soon",
    "things",
    "user-friendly",
}

PERMISSION_ACTIONS = {"add", "approve", "archive", "assign", "delete", "edit", "export", "invite", "remove", "share", "update", "view"}
LIFECYCLE_ENTITIES = {"invite", "invites", "invitation", "invitations", "order", "orders", "payment", "payments", "subscription", "subscriptions"}
DATA_CONSTRAINT_ENTITIES = {"account", "accounts", "email", "emails", "file", "files", "invoice", "invoices", "payment", "payments", "workspace", "workspaces"}
SECURITY_TERMS = {"access", "admin", "admins", "delete", "export", "guest", "guests", "invite", "share", "token", "upload"}

SEVERITY_WEIGHTS = {
    Severity.critical: 28,
    Severity.high: 17,
    Severity.medium: 9,
    Severity.low: 4,
}

STRICTNESS_MULTIPLIERS = {
    Strictness.lenient: 0.75,
    Strictness.balanced: 1.0,
    Strictness.ruthless: 1.2,
}

STRICTNESS_NOTES = {
    Strictness.lenient: "Lenient lowers penalties by 25% and is meant for rough early ideas.",
    Strictness.balanced: "Balanced uses the default rubric for specs that are close to planning.",
    Strictness.ruthless: "Ruthless raises penalties by 20% and adds a warning when no hard rules are present.",
}

CATEGORY_DOCS = [
    CategoryDoc(
        type=IssueType.ambiguity,
        label="Ambiguity",
        checks_for="Missing actors, unclear references, and wording that can be implemented multiple ways.",
    ),
    CategoryDoc(
        type=IssueType.unverifiable_claim,
        label="Unverifiable claim",
        checks_for="Words like fast, easy, simple, or soon that need measurable pass/fail criteria.",
    ),
    CategoryDoc(
        type=IssueType.permission_gap,
        label="Permission gap",
        checks_for="Sensitive actions without role boundaries, denial behavior, or abuse controls.",
    ),
    CategoryDoc(
        type=IssueType.lifecycle_gap,
        label="Lifecycle gap",
        checks_for="Objects with states such as invited, expired, paid, cancelled, or failed but no transitions.",
    ),
    CategoryDoc(
        type=IssueType.data_constraint_gap,
        label="Data constraint gap",
        checks_for="Persistent data without limits, uniqueness, ownership, retention, or validation rules.",
    ),
    CategoryDoc(
        type=IssueType.failure_mode_gap,
        label="Failure mode gap",
        checks_for="Happy-path-only specs that omit errors, retries, timeouts, empty states, or recovery.",
    ),
    CategoryDoc(
        type=IssueType.contradiction,
        label="Contradiction",
        checks_for="Rules that cannot both be true unless the spec defines explicit precedence.",
    ),
]


def analyze_spec(title: str, spec_text: str, strictness: Strictness = Strictness.balanced) -> SpecAnalysisResponse:
    sentences = split_sentences(spec_text)
    intent = _extract_intent(spec_text, sentences)
    issues = _collect_issues(spec_text, sentences, intent, strictness)
    edge_cases = _edge_cases(intent, issues)
    acceptance_tests = _acceptance_tests(title, intent, issues, sentences)
    traceability = _traceability(sentences, issues, acceptance_tests)
    score, score_breakdown = _score(issues, strictness)
    verdict = _verdict(score, issues)
    summary = _summary(score, verdict, issues, intent)
    rewritten_spec = _rewrite(title, intent, issues, edge_cases, acceptance_tests)
    return SpecAnalysisResponse(
        title=title.strip() or "Untitled spec",
        verdict=verdict,
        score=score,
        score_breakdown=score_breakdown,
        severity_counts=_severity_counts(issues),
        category_docs=CATEGORY_DOCS,
        strictness_note=STRICTNESS_NOTES[strictness],
        summary=summary,
        intent=intent,
        issues=issues,
        edge_cases=edge_cases,
        acceptance_tests=acceptance_tests,
        traceability=traceability,
        rewritten_spec=rewritten_spec,
    )


def _extract_intent(spec_text: str, sentences: list[str]) -> ExtractedIntent:
    tokens = tokenize(spec_text)
    token_set = set(tokens)
    actors = sorted(_singularize(term) for term in token_set & ACTORS)
    entities = sorted(_singularize(term) for term in token_set & ENTITIES)
    actions = sorted(_stem_action(term) for term in token_set & ACTION_TERMS)
    states = sorted(_singularize(term) for term in token_set & STATE_TERMS)
    explicit_rules = [
        sentence
        for sentence in sentences
        if re.search(r"\b(must|cannot|can't|only|never|required|requires|allowed|not allowed)\b", sentence, re.I)
    ][:8]
    return ExtractedIntent(
        actors=sorted(set(actors)),
        entities=sorted(set(entities)),
        actions=sorted(set(actions)),
        states=sorted(set(states)),
        explicit_rules=explicit_rules,
    )


def _collect_issues(
    spec_text: str,
    sentences: list[str],
    intent: ExtractedIntent,
    strictness: Strictness,
) -> list[SpecIssue]:
    issues: list[SpecIssue] = []
    lowered = spec_text.lower()

    for term in sorted(VAGUE_TERMS, key=len, reverse=True):
        if term in lowered:
            sentence = _sentence_with(sentences, term)
            issues.append(
                _issue(
                    IssueType.unverifiable_claim,
                    Severity.medium,
                    "Unverifiable language needs a measurable target",
                    sentence,
                    f"'{term}' cannot be tested without a threshold or observable behavior.",
                    "Replace the vague phrase with a measurable constraint, limit, or user-visible outcome.",
                    "What exact condition would make this pass or fail?",
                )
            )

    if re.search(r"\b(it|they|them|this|that|these|those)\b", lowered) and len(intent.entities) >= 2:
        issues.append(
            _issue(
                IssueType.ambiguity,
                Severity.medium,
                "Pronoun reference may be ambiguous",
                _sentence_matching(sentences, r"\b(it|they|them|this|that|these|those)\b"),
                "The spec mentions multiple entities, so pronouns can point to the wrong object during implementation.",
                "Restate the noun directly in rules that affect permissions, state changes, or data updates.",
                "Which exact entity does the pronoun refer to?",
            )
        )

    if intent.actions and not intent.actors:
        issues.append(
            _issue(
                IssueType.ambiguity,
                Severity.high,
                "Actor is missing",
                sentences[0] if sentences else spec_text,
                "The behavior describes actions but does not name who can perform them.",
                "Name the actor for every action, such as admin, member, guest, customer, or system.",
                "Who initiates this behavior?",
            )
        )

    if set(intent.actions) & PERMISSION_ACTIONS and not _has_permission_boundary(lowered):
        issues.append(
            _issue(
                IssueType.permission_gap,
                Severity.high,
                "Permission boundary is underspecified",
                _sentence_matching(sentences, r"\b(invite|delete|edit|export|share|remove|view|update|approve|archive)\b"),
                "The spec grants a sensitive action without saying which roles can or cannot perform it.",
                "Define role-specific permissions and denial behavior for unauthorized actors.",
                "Which roles are allowed, denied, or conditionally allowed?",
            )
        )

    if set(intent.entities) & LIFECYCLE_ENTITIES and not _mentions_lifecycle(lowered):
        issues.append(
            _issue(
                IssueType.lifecycle_gap,
                Severity.high,
                "Invitation lifecycle is incomplete" if "invite" in set(intent.actions + intent.entities) else "Lifecycle states are incomplete",
                _sentence_matching(sentences, r"\b(invite|invitation|order|payment|subscription)\b"),
                "Lifecycle objects need states for creation, expiry, cancellation, retry, and completion.",
                "List the allowed states, transitions, expiry behavior, and terminal states.",
                "What happens after the object is accepted, expired, cancelled, or retried?",
            )
        )

    if set(intent.entities) & DATA_CONSTRAINT_ENTITIES and not _mentions_data_constraints(lowered):
        issues.append(
            _issue(
                IssueType.data_constraint_gap,
                Severity.medium,
                "Data constraints are missing",
                _sentence_matching(sentences, r"\b(email|account|file|invoice|payment|workspace|data)\b"),
                "The spec touches persistent data but does not define uniqueness, limits, ownership, or retention.",
                "Add constraints for duplicates, ownership, limits, retention, and validation failures.",
                "What input is invalid, duplicate, too large, or no longer allowed?",
            )
        )

    if intent.actions and not _mentions_failure_modes(lowered):
        issues.append(
            _issue(
                IssueType.failure_mode_gap,
                Severity.medium,
                "Failure behavior is not specified",
                sentences[-1] if sentences else spec_text,
                "The happy path is described, but the system behavior is undefined when the action fails.",
                "Add expected errors, retry behavior, empty states, and recovery paths.",
                "What should the user see when the operation fails?",
            )
        )

    if contains_any(spec_text, SECURITY_TERMS) and not re.search(r"\b(audit|log|rate limit|abuse|permission|role|private|security|token|access control)\b", lowered):
        issues.append(
            _issue(
                IssueType.permission_gap,
                Severity.medium,
                "Security and abuse controls are unstated",
                _sentence_matching(sentences, r"\b(access|admin|delete|export|guest|invite|share|upload)\b"),
                "The feature changes access or data movement but does not mention auditability or abuse prevention.",
                "State audit logging, rate limits, and access-control checks for sensitive operations.",
                "How would the system prevent or investigate misuse?",
            )
        )

    if _has_possible_contradiction(lowered):
        issues.append(
            _issue(
                IssueType.contradiction,
                Severity.critical,
                "Possible contradiction between universal and restrictive rules",
                _sentence_matching(sentences, r"\b(all|every|any|never|only|except|unless)\b"),
                "Universal rules and exception rules can both be true only if their precedence is explicit.",
                "Define precedence: which rule wins when the universal rule and exception overlap?",
                "Which rule should win in the conflicting case?",
            )
        )

    if strictness == Strictness.ruthless and not intent.explicit_rules:
        issues.append(
            _issue(
                IssueType.ambiguity,
                Severity.medium,
                "No hard requirements detected",
                compact_quote(spec_text),
                "The spec reads like intent, but lacks must/cannot/only rules that constrain implementation.",
                "Add explicit invariants using must, cannot, only, required, or not allowed.",
                "Which behavior is mandatory versus optional?",
            )
        )

    return _dedupe_issues(issues)


def _edge_cases(intent: ExtractedIntent, issues: list[SpecIssue]) -> list[EdgeCase]:
    cases: list[EdgeCase] = []
    actors = intent.actors or ["user"]
    primary_actor = actors[0]
    entities = intent.entities or ["record"]
    primary_entity = entities[0]

    if any(issue.type == IssueType.permission_gap for issue in issues):
        cases.append(
            EdgeCase(
                title="Unauthorized actor attempts the action",
                scenario=f"A role outside the allowed set tries to modify a {primary_entity}.",
                expected_behavior="The system blocks the action, explains the denial, and records the attempt when appropriate.",
            )
        )
    if any(issue.type == IssueType.lifecycle_gap for issue in issues):
        cases.append(
            EdgeCase(
                title="Expired or terminal state",
                scenario=f"{primary_actor.title()} tries to act on a {primary_entity} after it has expired, completed, or been cancelled.",
                expected_behavior="The system preserves the terminal state and gives a clear recovery path.",
            )
        )
    if any(issue.type == IssueType.data_constraint_gap for issue in issues):
        cases.append(
            EdgeCase(
                title="Duplicate or invalid data",
                scenario=f"{primary_actor.title()} submits a duplicate, malformed, or oversized {primary_entity}.",
                expected_behavior="The system rejects invalid data before persistence and returns a specific validation message.",
            )
        )
    if any(issue.type == IssueType.failure_mode_gap for issue in issues):
        cases.append(
            EdgeCase(
                title="Downstream operation fails",
                scenario="A dependency times out or rejects the operation after the user submits the action.",
                expected_behavior="The system avoids partial success, exposes retry status, and keeps the user-facing state consistent.",
            )
        )
    if not cases:
        cases.append(
            EdgeCase(
                title="No-result path",
                scenario=f"{primary_actor.title()} performs the action when there are no matching {primary_entity}s.",
                expected_behavior="The system shows a stable empty state instead of failing silently.",
            )
        )
    return cases[:6]


def _acceptance_tests(
    title: str,
    intent: ExtractedIntent,
    issues: list[SpecIssue],
    sentences: list[str],
) -> list[AcceptanceTest]:
    tests: list[AcceptanceTest] = []
    actor = (intent.actors or ["authorized user"])[0]
    action = (intent.actions or ["complete the action"])[0]
    entity = (intent.entities or ["item"])[0]
    issue_ids_by_type = {issue.type: issue.id for issue in issues}

    tests.append(
        AcceptanceTest(
            id=stable_id("test", title, "happy", actor, action, entity),
            name="Happy path is explicit",
            given=f"a valid {actor} and a valid {entity}",
            when=f"the {actor} attempts to {action} the {entity}",
            then="the system completes the action and exposes the resulting state to the user",
            covers_issue_ids=[],
        )
    )
    if IssueType.permission_gap in issue_ids_by_type:
        tests.append(
            AcceptanceTest(
                id=stable_id("test", title, "permission"),
                name="Unauthorized access is blocked",
                given=f"a role that is not allowed to {action} the {entity}",
                when=f"that role attempts to {action} the {entity}",
                then="the system rejects the action with a clear permission response and no data mutation",
                covers_issue_ids=[issue_ids_by_type[IssueType.permission_gap]],
            )
        )
    if IssueType.lifecycle_gap in issue_ids_by_type:
        tests.append(
            AcceptanceTest(
                id=stable_id("test", title, "lifecycle"),
                name="Terminal states are respected",
                given=f"a {entity} in an expired, cancelled, completed, or otherwise terminal state",
                when=f"the {actor} attempts to {action} it",
                then="the system preserves the terminal state and shows the allowed next step",
                covers_issue_ids=[issue_ids_by_type[IssueType.lifecycle_gap]],
            )
        )
    if IssueType.data_constraint_gap in issue_ids_by_type:
        tests.append(
            AcceptanceTest(
                id=stable_id("test", title, "data"),
                name="Invalid data is rejected",
                given=f"duplicate, malformed, unauthorized, or oversized data for the {entity}",
                when=f"the {actor} submits it",
                then="the system returns a validation error and does not persist invalid data",
                covers_issue_ids=[issue_ids_by_type[IssueType.data_constraint_gap]],
            )
        )
    if IssueType.failure_mode_gap in issue_ids_by_type:
        tests.append(
            AcceptanceTest(
                id=stable_id("test", title, "failure"),
                name="Failure path is recoverable",
                given="a dependency timeout, network failure, or rejected operation",
                when=f"the {actor} attempts to {action} the {entity}",
                then="the system communicates failure, avoids partial success, and provides retry or recovery behavior",
                covers_issue_ids=[issue_ids_by_type[IssueType.failure_mode_gap]],
            )
        )
    if sentences:
        tests.append(
            AcceptanceTest(
                id=stable_id("test", title, "source", sentences[0]),
                name="Original requirement is observable",
                given="the original product requirement",
                when="the feature is implemented",
                then="each claim in the requirement can be verified by a product, API, or UI test",
                covers_issue_ids=[
                    issue.id
                    for issue in issues
                    if issue.type in {IssueType.ambiguity, IssueType.unverifiable_claim}
                ][:3],
            )
        )
    return tests[:8]


def _traceability(
    sentences: list[str],
    issues: list[SpecIssue],
    tests: list[AcceptanceTest],
) -> list[TraceItem]:
    if not sentences:
        return []
    output: list[TraceItem] = []
    for index, sentence in enumerate(sentences[:6], start=1):
        matching_issues = [
            issue.test_prompt
            for issue in issues
            if issue.evidence and (issue.evidence in sentence or sentence in issue.evidence)
        ][:3]
        output.append(
            TraceItem(
                requirement=f"R{index}: {compact_quote(sentence, 120)}",
                tests=[test.id for test in tests[:2]],
                open_questions=matching_issues,
            )
        )
    return output


def _rewrite(
    title: str,
    intent: ExtractedIntent,
    issues: list[SpecIssue],
    edge_cases: list[EdgeCase],
    tests: list[AcceptanceTest],
) -> str:
    actor = (intent.actors or ["authorized user"])[0]
    entity = (intent.entities or ["target record"])[0]
    actions = ", ".join(intent.actions[:4]) or "perform the requested action"
    denied = "Roles outside the allowed set cannot perform the action and receive a clear denial."
    lifecycle = "The feature must define valid states, terminal states, and retry or expiry behavior."
    validation = "Invalid, duplicate, unauthorized, or oversized input must be rejected before persistence."
    failure = "Failures must leave the system in a consistent state and expose a retry or recovery path."
    lines = [
        f"# {title.strip() or 'Rewritten Spec'}",
        "",
        f"Primary actor: {actor}.",
        f"Primary object: {entity}.",
        f"Allowed actions: {actions}.",
        "",
        "Rules:",
    ]
    if intent.explicit_rules:
        lines.extend(f"- {rule}" for rule in intent.explicit_rules[:5])
    else:
        lines.append(f"- Only an explicitly authorized {actor} can act on the {entity}.")
    if any(issue.type == IssueType.permission_gap for issue in issues):
        lines.append(f"- {denied}")
    if any(issue.type == IssueType.lifecycle_gap for issue in issues):
        lines.append(f"- {lifecycle}")
    if any(issue.type == IssueType.data_constraint_gap for issue in issues):
        lines.append(f"- {validation}")
    if any(issue.type == IssueType.failure_mode_gap for issue in issues):
        lines.append(f"- {failure}")
    lines.extend(["", "Acceptance criteria:"])
    lines.extend(f"- Given {test.given}, when {test.when}, then {test.then}." for test in tests[:5])
    lines.extend(["", "Edge cases:"])
    lines.extend(f"- {case.title}: {case.expected_behavior}" for case in edge_cases[:5])
    return "\n".join(lines)


def _score(issues: list[SpecIssue], strictness: Strictness) -> tuple[int, ScoreBreakdown]:
    multiplier = STRICTNESS_MULTIPLIERS[strictness]
    counts = _severity_counts(issues)
    penalties = [
        ScorePenalty(
            severity=severity,
            count=counts[severity],
            weight=weight,
            subtotal=round(counts[severity] * weight * multiplier, 2),
        )
        for severity, weight in SEVERITY_WEIGHTS.items()
        if counts[severity]
    ]
    total_penalty = round(sum(penalty.subtotal for penalty in penalties), 2)
    score = max(0, min(100, round(100 - total_penalty)))
    breakdown = ScoreBreakdown(
        strictness=strictness,
        strictness_multiplier=multiplier,
        weights=SEVERITY_WEIGHTS,
        penalties=penalties,
        total_penalty=total_penalty,
        explanation="Score is out of 100: 100 minus severity-weighted issue penalties, adjusted by strictness.",
    )
    return score, breakdown


def _severity_counts(issues: list[SpecIssue]) -> dict[Severity, int]:
    return {
        severity: sum(1 for issue in issues if issue.severity == severity)
        for severity in Severity
    }


def _verdict(score: int, issues: list[SpecIssue]) -> str:
    if any(issue.severity == Severity.critical for issue in issues) or score < 55:
        return "does_not_compile"
    if issues or score < 85:
        return "compiles_with_warnings"
    return "compiles"


def _summary(score: int, verdict: str, issues: list[SpecIssue], intent: ExtractedIntent) -> str:
    high_count = sum(1 for issue in issues if issue.severity in {Severity.critical, Severity.high})
    nouns = ", ".join((intent.entities or top_terms(" ".join(issue.evidence for issue in issues), 3))[:3])
    if verdict == "compiles":
        return f"This spec is testable enough to build. SpecLint found {len(issues)} minor issues."
    if verdict == "does_not_compile":
        return f"This spec is not build-ready. It has {high_count} high-risk gaps around {nouns or 'core behavior'}."
    return f"This spec is close, but needs tightening. SpecLint found {len(issues)} issues, including {high_count} high-risk gaps."


def _issue(
    issue_type: IssueType,
    severity: Severity,
    title: str,
    evidence: str,
    why_it_matters: str,
    suggestion: str,
    test_prompt: str,
) -> SpecIssue:
    return SpecIssue(
        id=stable_id("issue", issue_type, title, evidence),
        type=issue_type,
        severity=severity,
        title=title,
        evidence=compact_quote(evidence),
        why_it_matters=why_it_matters,
        suggestion=suggestion,
        test_prompt=test_prompt,
    )


def _dedupe_issues(issues: list[SpecIssue]) -> list[SpecIssue]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[SpecIssue] = []
    for issue in issues:
        key = (issue.type.value, issue.title, issue.evidence)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    severity_order = {Severity.critical: 0, Severity.high: 1, Severity.medium: 2, Severity.low: 3}
    return sorted(deduped, key=lambda issue: (severity_order[issue.severity], issue.title))[:12]


def _sentence_with(sentences: list[str], term: str) -> str:
    lowered = term.lower()
    for sentence in sentences:
        if lowered in sentence.lower():
            return sentence
    return term


def _sentence_matching(sentences: list[str], pattern: str) -> str:
    compiled = re.compile(pattern, re.I)
    for sentence in sentences:
        if compiled.search(sentence):
            return sentence
    return sentences[0] if sentences else ""


def _has_permission_boundary(text: str) -> bool:
    return bool(re.search(r"\b(role|permission|allowed|not allowed|cannot|can't|only|admin|owner|member|guest|authorized|unauthorized)\b", text))


def _mentions_lifecycle(text: str) -> bool:
    return bool(re.search(r"\b(expire|expires|expired|cancel|cancelled|accepted|pending|retry|resent|revoked|completed|failed|state|status)\b", text))


def _mentions_data_constraints(text: str) -> bool:
    return bool(re.search(r"\b(unique|duplicate|required|optional|limit|maximum|max|minimum|min|validate|invalid|retention|owner|ownership|size)\b", text))


def _mentions_failure_modes(text: str) -> bool:
    return bool(re.search(r"\b(error|fail|fails|failure|fallback|retry|timeout|offline|empty state|denied|invalid|unavailable)\b", text))


def _has_possible_contradiction(text: str) -> bool:
    sentences = split_sentences(text)
    for sentence in sentences:
        has_universal = bool(re.search(r"\b(all|every|any|always)\b", sentence))
        has_hard_block = bool(re.search(r"\b(never|cannot|can't)\b", sentence))
        has_conditional_exception = bool(re.search(r"\b(unless|except when|except if|as long as)\b", sentence))
        if has_universal and has_hard_block and not has_conditional_exception:
            return True
    has_universal_rule = bool(re.search(r"\b(all|every|any|always)\b", text))
    has_exclusive_rule = bool(re.search(r"\bonly\b", text))
    has_exception = bool(re.search(r"\b(unless|except when|except if|as long as)\b", text))
    return has_universal_rule and has_exclusive_rule and not has_exception


def _singularize(term: str) -> str:
    if term.endswith("ies"):
        return f"{term[:-3]}y"
    if term.endswith("s") and len(term) > 3:
        return term[:-1]
    return term


def _stem_action(term: str) -> str:
    if term.endswith("ing") and len(term) > 5:
        return term[:-3]
    if term.endswith("ed") and len(term) > 4:
        return term[:-2]
    return term
