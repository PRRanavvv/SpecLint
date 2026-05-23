from __future__ import annotations

from collections import Counter
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
from .text_utils import compact_quote, contains_any, split_sentences, stable_id, tokenize


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
    "access",
    "comment",
    "comments",
    "content",
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
    "link",
    "links",
    "message",
    "messages",
    "notification",
    "notifications",
    "order",
    "orders",
    "ownership",
    "payment",
    "payments",
    "password",
    "passwords",
    "profile",
    "project",
    "projects",
    "report",
    "reports",
    "review",
    "reviews",
    "role",
    "roles",
    "session",
    "sessions",
    "task",
    "tasks",
    "team",
    "teams",
    "token",
    "tokens",
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
    "connect",
    "create",
    "delete",
    "demote",
    "download",
    "edit",
    "export",
    "expire",
    "flag",
    "invite",
    "join",
    "login",
    "manage",
    "pay",
    "promote",
    "publish",
    "prompt",
    "grant",
    "remove",
    "request",
    "reset",
    "restore",
    "revoke",
    "reuse",
    "send",
    "share",
    "sign",
    "submit",
    "transfer",
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
    "visible",
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
    "common file types",
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
    "some time",
    "things",
    "user-friendly",
}

PERMISSION_ACTIONS = {"add", "approve", "archive", "assign", "delete", "edit", "export", "invite", "remove", "revoke", "share", "transfer", "update", "view"}
LIFECYCLE_ENTITIES = {"invite", "invites", "invitation", "invitations", "order", "orders", "ownership", "payment", "payments", "subscription", "subscriptions"}
DATA_CONSTRAINT_ENTITIES = {"account", "accounts", "email", "emails", "file", "files", "invoice", "invoices", "ownership", "password", "passwords", "payment", "payments", "token", "tokens", "workspace", "workspaces"}
SECURITY_TERMS = {"access", "admin", "admins", "delete", "export", "guest", "guests", "invite", "owner", "ownership", "share", "token", "transfer", "upload"}
CONTROL_TRANSFER_TERMS = {"access", "admin", "control", "guest", "member", "owner", "ownership", "permission", "role"}
PRIMARY_OBJECT_ACTIONS = {
    "connect",
    "create",
    "delete",
    "edit",
    "flag",
    "invite",
    "manage",
    "remove",
    "request",
    "reset",
    "send",
    "share",
    "submit",
    "transfer",
    "upload",
    "view",
}
OBJECT_TOKEN_ALIASES = {
    "accounts": "account",
    "comments": "comment",
    "content": "content",
    "emails": "email",
    "files": "file",
    "guests": "guest",
    "invites": "invitation",
    "invitations": "invitation",
    "links": "link",
    "members": "member",
    "messages": "message",
    "owners": "owner",
    "people": "member",
    "person": "member",
    "persons": "member",
    "projects": "project",
    "repo": "repository",
    "repositories": "repository",
    "repos": "repository",
    "reviews": "review",
    "roles": "role",
    "tasks": "task",
    "teammate": "member",
    "teammates": "member",
    "tokens": "token",
    "users": "user",
    "workspaces": "workspace",
}

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
    Strictness.lenient: "Lenient - early-stage ideas, ignores minor gaps, flags only blockers.",
    Strictness.balanced: "Balanced - close to planning, default rubric, catches real holes.",
    Strictness.ruthless: "Ruthless - pre-engineering handoff, flags everything, expect 8-12 issues on any real spec.",
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
        type=IssueType.consent_gap,
        label="Consent gap",
        checks_for="Transfers of ownership, role, or access where the receiving party may need to accept or decline.",
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


def analyze_spec(
    title: str,
    spec_text: str,
    strictness: Strictness = Strictness.balanced,
    source_spec_text: str | None = None,
) -> SpecAnalysisResponse:
    sentences = split_sentences(spec_text)
    source_sentences = split_sentences(source_spec_text or spec_text)
    intent = _extract_intent(spec_text, sentences)
    primary_object = _primary_entity(intent, spec_text, title)
    issues = _collect_issues(title, spec_text, sentences, intent, strictness, primary_object)
    edge_cases = _edge_cases(intent, issues, spec_text, title, primary_object)
    acceptance_tests = _acceptance_tests(title, intent, issues, sentences, primary_object)
    traceability = _traceability(source_sentences, issues, acceptance_tests)
    score, score_breakdown = _score(issues, strictness)
    verdict = _verdict(score, issues)
    summary = _summary(score, verdict, issues, intent, primary_object)
    rewritten_spec = _rewrite(title, intent, issues, edge_cases, acceptance_tests, primary_object)
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
    actions = sorted(
        stem
        for term in token_set
        if (stem := _stem_action(term)) in ACTION_TERMS
    )
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
    title: str,
    spec_text: str,
    sentences: list[str],
    intent: ExtractedIntent,
    strictness: Strictness,
    primary_object: str,
) -> list[SpecIssue]:
    issues: list[SpecIssue] = []
    lowered = spec_text.lower()

    if primary_object == "unspecified":
        issues.append(
            _issue(
                IssueType.ambiguity,
                Severity.critical,
                "Primary object could not be determined. Spec may be too vague to compile.",
                compact_quote(f"{title}. {spec_text}"),
                "The spec does not clearly name the thing being created, edited, deleted, submitted, viewed, shared, removed, uploaded, sent, or flagged.",
                "Name the object that receives the main action, then define its states, ownership, and constraints.",
                "What object is the feature changing?",
            )
        )

    for term in sorted(VAGUE_TERMS, key=len, reverse=True):
        if term in lowered:
            sentence = _sentence_with(sentences, term)
            title = (
                "Supported file types are undefined"
                if term == "common file types"
                else "Unverifiable language needs a measurable target"
            )
            suggestion = (
                "List the allowed MIME types or extensions, max size per type, and what error users see for unsupported files."
                if term == "common file types"
                else "Replace the vague phrase with a measurable constraint, limit, or user-visible outcome."
            )
            question = (
                "Which exact file types are supported or rejected?"
                if term == "common file types"
                else "What exact condition would make this pass or fail?"
            )
            issues.append(
                _issue(
                    IssueType.unverifiable_claim,
                    Severity.medium,
                    title,
                    sentence,
                    f"'{term}' cannot be tested without a threshold or observable behavior.",
                    suggestion,
                    question,
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

    if _has_control_transfer(lowered) and not _has_receiver_consent(lowered):
        issues.append(
            _issue(
                IssueType.consent_gap,
                Severity.critical,
                "Receiving party consent is unspecified",
                _sentence_matching(sentences, r"\b(transfer|ownership|owner|admin access|role|permission|invite)\b"),
                "A person can receive ownership, control, or elevated access without the spec saying whether they must accept first.",
                "Define whether the receiving party must accept or decline before the transfer takes effect, and what happens if they do nothing.",
                "Does the receiving party need to accept before access or ownership changes?",
            )
        )

    if _has_destructive_confirmation_ambiguity(lowered):
        issues.append(
            _issue(
                IssueType.consent_gap,
                Severity.critical,
                "Destructive confirmation consent is ambiguous",
                _sentence_matching(sentences, r"\b(confirmation email|email before|before deletion|confirm)\b"),
                "The spec says a destructive action is confirmed or emailed, but not whether the user must actively approve before deletion happens.",
                "Define whether deletion waits for an explicit click or approval, how long the confirmation is valid, and what happens if the user ignores it.",
                "Does the user need to click or approve before the destructive action is processed?",
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

    if _has_shared_content_orphan_gap(lowered):
        issues.append(
            _issue(
                IssueType.lifecycle_gap,
                Severity.high,
                "Shared content ownership after deletion is undefined",
                _sentence_matching(sentences, r"\b(shared content|content remains|visible to other|team members|comments|attribution)\b"),
                "The account can be deleted while shared content remains, but the spec does not say who owns, edits, attributes, or moderates that content afterward.",
                "Define post-deletion ownership, attribution labels, edit permissions, comment behavior, and whether content becomes orphaned or transferred.",
                "Who owns and can edit shared content after the original user is deleted?",
            )
        )

    if _has_member_removal_lifecycle_gap(lowered):
        issues.append(
            _issue(
                IssueType.lifecycle_gap,
                Severity.high,
                "Member removal lifecycle is undefined",
                _sentence_matching(sentences, r"\b(remove|removes|removed|revoke|revokes|kick|kicks)\b"),
                "Removing a person from a project changes access and membership state, but the spec does not say what they see, whether they are notified, or what happens to their existing work.",
                "Define notification, access revocation timing, created-content ownership, comments, rejoin behavior, and audit history after removal.",
                "What happens to the removed member and their project data after removal?",
            )
        )

    if _has_file_uploader_delete_permission_gap(lowered):
        issues.append(
            _issue(
                IssueType.permission_gap,
                Severity.high,
                "File deletion permissions are underspecified",
                _sentence_matching(sentences, r"\b(whoever uploaded|uploaded them|uploader|deleted by)\b"),
                "The uploader owns deletion rights, but the spec does not say what happens when the uploader leaves, when an admin needs to remove a file, or when shared recipients still depend on it.",
                "Define whether uploaders, project admins, owners, and removed members can delete shared files, and what denial behavior applies.",
                "Who can delete a file after it has been shared or after the uploader leaves?",
            )
        )

    if _has_shared_file_permanent_delete_conflict(lowered):
        issues.append(
            _issue(
                IssueType.contradiction,
                Severity.critical,
                "Shared file deletion semantics conflict",
                _sentence_matching(sentences, r"\b(shared|deleted|gone permanently|permanently)\b"),
                "The spec says files can be shared and also permanently deleted, but it does not define whether deletion removes every shared reference or only the uploader's copy.",
                "Define whether deleting a shared file removes it for all members, breaks shared links, preserves references, or requires an ownership transfer.",
                "When a shared file is deleted, what happens to every member's access and references?",
            )
        )

    if _has_reset_link_lifecycle_gap(lowered):
        issues.append(
            _issue(
                IssueType.lifecycle_gap,
                Severity.high,
                "Reset link lifecycle is incomplete",
                _sentence_matching(sentences, r"\b(reset link|link|expire|expires|expired|password)\b"),
                "Password reset links are security-sensitive lifecycle objects, but the spec does not fully define expiry, one-time use, invalidation, and terminal states.",
                "Define the exact expiry window, whether links are single-use, whether a new request invalidates older links, and what users see for expired or already-used links.",
                "When is a reset link valid, invalid, expired, or already used?",
            )
        )

    if _has_password_reset_identity_gap(lowered):
        issues.append(
            _issue(
                IssueType.permission_gap,
                Severity.high,
                "Password reset identity disclosure is undefined",
                _sentence_matching(sentences, r"\b(request a reset|reset link|email|forgot|forgets)\b"),
                "A password reset request can reveal whether an email belongs to an account unless the response and email behavior are specified.",
                "Define a neutral response for known and unknown emails, plus throttling or abuse controls for repeated reset requests.",
                "Should the reset request reveal whether the account exists?",
            )
        )

    if _has_password_reuse_scope_gap(lowered):
        issues.append(
            _issue(
                IssueType.data_constraint_gap,
                Severity.medium,
                "Password reuse rule is underspecified",
                _sentence_matching(sentences, r"\b(reuse|old password|previous password|password history)\b"),
                "The phrase old password can mean the current password, the last password, or the full password history, which leads to different validation behavior.",
                "Define whether users are blocked from reusing only their current password, the last N passwords, or all retained password history.",
                "Which previous passwords are blocked from reuse?",
            )
        )

    if _has_auto_login_session_gap(lowered):
        issues.append(
            _issue(
                IssueType.permission_gap,
                Severity.high,
                "Post-reset session behavior is undefined",
                _sentence_matching(sentences, r"\b(logged in automatically|automatically logged in|auto-?login|logs? (them|the user) in)\b"),
                "Automatically logging in after a password reset changes authentication state, but the spec does not say what happens to existing sessions, MFA, or the requesting device.",
                "Define whether reset revokes existing sessions, whether MFA is required, and whether auto-login only applies to the device that completed the reset.",
                "What sessions remain valid after the password is reset?",
            )
        )

    if set(intent.entities) & DATA_CONSTRAINT_ENTITIES and not _mentions_data_constraints(lowered) and not _has_password_reset_flow(lowered):
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
                _failure_mode_evidence(sentences, spec_text),
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


def _edge_cases(
    intent: ExtractedIntent,
    issues: list[SpecIssue],
    spec_text: str,
    title: str,
    primary_object: str,
) -> list[EdgeCase]:
    cases: list[EdgeCase] = []
    actors = intent.actors or ["user"]
    primary_actor = _primary_actor(intent, " ".join(issue.evidence for issue in issues))
    primary_entity = primary_object or _primary_entity(intent, spec_text, title)

    if any(issue.type == IssueType.permission_gap for issue in issues):
        cases.append(
            EdgeCase(
                title="Unauthorized actor attempts the action",
                scenario=f"A role outside the allowed set tries to modify a {primary_entity}.",
                expected_behavior="The system blocks the action, explains the denial, and records the attempt when appropriate.",
            )
        )
    if any(issue.type == IssueType.consent_gap for issue in issues):
        cases.append(
            EdgeCase(
                title="Receiver declines or ignores the transfer",
                scenario=f"{primary_actor.title()} starts a {primary_entity} transfer, but the receiving party does not accept it.",
                expected_behavior="The system keeps the original owner and permissions unchanged until acceptance rules are satisfied.",
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
    primary_object: str,
) -> list[AcceptanceTest]:
    tests: list[AcceptanceTest] = []
    spec_text = " ".join(sentences)
    actor = _primary_actor(intent, spec_text)
    entity = primary_object
    action_phrase = _primary_action_phrase(intent, spec_text, entity)
    issue_ids_by_type = {issue.type: issue.id for issue in issues}

    tests.append(
        AcceptanceTest(
            id=stable_id("test", title, "happy", actor, action_phrase, entity),
            name="Happy path is explicit",
            given=f"a valid {actor} and a valid {entity}",
            when=f"the {actor} attempts to {action_phrase}",
            then="the system completes the action and exposes the resulting state to the user",
            covers_issue_ids=[],
        )
    )
    if IssueType.consent_gap in issue_ids_by_type:
        tests.append(
            AcceptanceTest(
                id=stable_id("test", title, "consent"),
                name="Receiver consent is required before control changes",
                given=f"a pending {entity} transfer sent to a receiving party",
                when="the receiving party has not accepted it",
                then="the system keeps ownership, roles, and billing responsibility unchanged",
                covers_issue_ids=[issue_ids_by_type[IssueType.consent_gap]],
            )
        )
    if IssueType.permission_gap in issue_ids_by_type:
        tests.append(
            AcceptanceTest(
                id=stable_id("test", title, "permission"),
                name="Unauthorized access is blocked",
                given=f"a role that is not allowed to {action_phrase}",
                when=f"that role attempts to {action_phrase}",
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
                when=f"the {actor} attempts to {action_phrase}",
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
                when=f"the {actor} attempts to {action_phrase}",
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
    primary_object: str,
) -> str:
    spec_text = " ".join(test.when for test in tests)
    actor = _primary_actor(intent, spec_text)
    entity = primary_object
    action_phrase = _primary_action_phrase(intent, spec_text, entity)
    actions = ", ".join(intent.actions[:4]) or action_phrase
    denied = "Roles outside the allowed set cannot perform the action and receive a clear denial."
    consent = "Receiving parties must accept before ownership, access, role, or billing responsibility changes."
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
    if any(issue.type == IssueType.consent_gap for issue in issues):
        lines.append(f"- {consent}")
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


def _summary(score: int, verdict: str, issues: list[SpecIssue], intent: ExtractedIntent, primary_object: str) -> str:
    high_count = sum(1 for issue in issues if issue.severity in {Severity.critical, Severity.high})
    nouns = primary_object if primary_object != "unspecified" else ", ".join(intent.entities[:3])
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


def _raw_tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z0-9_-]*", text.lower())


def _has_permission_boundary(text: str) -> bool:
    return bool(re.search(r"\b(role|permission|allowed|not allowed|cannot|can't|only|admin|owner|member|guest|authorized|unauthorized)\b", text))


def _mentions_lifecycle(text: str) -> bool:
    return bool(re.search(r"\b(expire|expires|expired|cancel|cancelled|accepted|pending|retry|resent|revoked|completed|failed|state|status)\b", text))


def _mentions_data_constraints(text: str) -> bool:
    return bool(re.search(r"\b(unique|duplicate|required|optional|limit|maximum|max|minimum|min|validate|invalid|retention|owner|ownership|size)\b", text))


def _mentions_failure_modes(text: str) -> bool:
    return bool(re.search(r"\b(error|fail|fails|failure|fallback|retry|timeout|offline|empty state|denied|invalid|unavailable)\b", text))


def _failure_mode_evidence(sentences: list[str], fallback: str) -> str:
    for pattern in (
        r"\b(email with a link|link to join|invited person gets an email)\b",
        r"\b(invite|invited|invitation|email)\b",
        r"\b(remove|removed|delete|deletion|transfer|connect|export|reset|upload|payment)\b",
        r"\b(can|attempts?|tries?|submits?)\b",
    ):
        compiled = re.compile(pattern, re.I)
        for sentence in sentences:
            if compiled.search(sentence):
                return sentence
    return sentences[-1] if sentences else fallback


def _has_destructive_confirmation_ambiguity(text: str) -> bool:
    has_destructive_action = bool(
        re.search(r"\b(delete|deletes|deleted|deletion|remove|removes|removed|erase|erases|destroy|destroys)\b", text)
    )
    has_confirmation_message = bool(
        re.search(r"\b(confirmation email|confirmation link|confirm email|email before|receives? (a )?confirmation)\b", text)
    )
    has_explicit_pre_approval = bool(
        re.search(
            r"\b(must|needs to|required to|has to)\s+(click|approve|confirm|verify)|\b(click|approve|confirm|verify)\s+(the )?(link|email|deletion)\b",
            text,
        )
    )
    return has_destructive_action and has_confirmation_message and not has_explicit_pre_approval


def _has_shared_content_orphan_gap(text: str) -> bool:
    has_deleted_user = bool(re.search(r"\b(delete|deletes|deleted|deletion|remove|removed)\b.{0,80}\b(user|account|member|profile)\b|\b(user|account|member|profile)\b.{0,80}\b(delete|deletes|deleted|deletion|remove|removed)\b", text))
    has_persistent_shared_content = bool(
        re.search(r"\b(shared content|shared files|comments|messages|posts|content)\b.{0,100}\b(remain|remains|visible|kept|preserved|still visible)\b", text)
        or re.search(r"\b(remain|remains|visible|kept|preserved|still visible)\b.{0,100}\b(shared content|shared files|comments|messages|posts|content)\b", text)
    )
    has_ownership_policy = bool(re.search(r"\b(owned by|transferred to|attributed to|orphan|system-owned|workspace-owned|edit permission|moderation)\b", text))
    return has_deleted_user and has_persistent_shared_content and not has_ownership_policy


def _has_member_removal_lifecycle_gap(text: str) -> bool:
    for sentence in [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]:
        has_member_removal = bool(
            re.search(
                r"\b(remove|removes|removed|revoke|revokes|kick|kicks)\b.{0,80}\b(people|person|member|members|user|users)\b"
                r"|\b(people|person|member|members|user|users)\b.{0,80}\b(remove|removes|removed|revoked|kicked)\b",
                sentence,
            )
        )
        has_project_context = bool(re.search(r"\b(project|workspace|team)\b", sentence))
        has_removal_policy = bool(
            re.search(
                r"\b(notif(y|ies|ied|ication)|email|alert|access revoked|lose access|revoked immediately|created content|owned content|comments|audit|rejoin|removed state)\b",
                sentence,
            )
        )
        if has_member_removal and has_project_context and not has_removal_policy:
            return True
    return False


def _has_file_uploader_delete_permission_gap(text: str) -> bool:
    has_file_delete_by_uploader = bool(
        re.search(
            r"\b(file|files)\b.{0,120}\b(deleted|delete|removed|remove)\b.{0,80}\b(whoever uploaded|uploader|uploaded them|uploaded it)\b"
            r"|\b(whoever uploaded|uploader|uploaded them|uploaded it)\b.{0,80}\b(delete|deleted|remove|removed)\b.{0,80}\b(file|files)\b",
            text,
        )
    )
    has_admin_or_departure_policy = bool(
        re.search(
            r"\b(admin|owner|moderator)\b.{0,80}\b(delete|remove)\b"
            r"|\b(uploader|member|user)\b.{0,80}\b(leaves|removed|deactivated|loses access)\b"
            r"|\b(delete permission|deletion permission|ownership transfer|retained owner)\b",
            text,
        )
    )
    return has_file_delete_by_uploader and not has_admin_or_departure_policy


def _has_shared_file_permanent_delete_conflict(text: str) -> bool:
    has_shared_file = bool(
        re.search(r"\b(file|files)\b.{0,120}\b(shared|share)\b", text)
        or re.search(r"\b(shared|share)\b.{0,120}\b(file|files)\b", text)
    )
    has_permanent_delete = bool(
        re.search(r"\b(deleted|delete|removed|remove)\b.{0,80}\b(permanent|permanently|gone)\b", text)
        or re.search(r"\b(permanent|permanently|gone)\b.{0,80}\b(deleted|delete|removed|remove)\b", text)
    )
    has_shared_delete_policy = bool(
        re.search(
            r"\b(for everyone|for all members|all members lose access|shared links? (are )?(removed|revoked|invalidated)|references? (are )?(removed|preserved)|only removes? (the )?uploader|ownership transfers?)\b",
            text,
        )
    )
    return has_shared_file and has_permanent_delete and not has_shared_delete_policy


def _has_password_reset_flow(text: str) -> bool:
    return bool(
        re.search(r"\bpassword\b.{0,80}\breset\b", text)
        or re.search(r"\breset\b.{0,80}\b(password|link|email)\b", text)
        or re.search(r"\b(forgot|forget|forgets)\b.{0,80}\bpassword\b", text)
    )


def _has_reset_link_lifecycle_gap(text: str) -> bool:
    has_reset_link = _has_password_reset_flow(text) and bool(re.search(r"\b(link|token|email)\b", text))
    has_measurable_expiry = bool(
        re.search(r"\b(expire|expires|expired|valid for)\b.{0,50}\b(\d+\s*(minute|minutes|hour|hours|day|days)|\d+\s*(m|h|d)\b)", text)
    )
    has_one_time_use = bool(
        re.search(r"\b(one[- ]time|single[- ]use|used once|only once|cannot be reused|can't be reused|invalidated? after use)\b", text)
    )
    has_reissue_policy = bool(
        re.search(r"\b(new|latest|another|subsequent)\s+(reset )?(link|token|request)\b.{0,80}\b(invalidates?|revokes?|replaces?|cancels?)\b", text)
        or re.search(r"\b(invalidates?|revokes?|replaces?|cancels?)\b.{0,80}\b(previous|older|old)\s+(reset )?(link|token|request)\b", text)
    )
    return has_reset_link and not (has_measurable_expiry and has_one_time_use and has_reissue_policy)


def _has_password_reset_identity_gap(text: str) -> bool:
    if not _has_password_reset_flow(text):
        return False
    has_request = bool(re.search(r"\b(request|send|sent|email|link)\b", text))
    has_neutral_response = bool(
        re.search(
            r"\b(same response|same message|generic response|generic message|if (an )?account exists|known and unknown emails|unknown email|do(es)? not reveal|don't reveal|without revealing|enumeration)\b",
            text,
        )
    )
    has_throttle = bool(re.search(r"\b(rate limit|throttle|cooldown|abuse|captcha|limit reset requests)\b", text))
    return has_request and not (has_neutral_response and has_throttle)


def _has_password_reuse_scope_gap(text: str) -> bool:
    has_reuse_rule = bool(
        re.search(r"\b(can't|cannot|must not|not allowed to|should not|shouldn't)\b.{0,40}\breuse\b.{0,80}\b(old|previous|prior)?\s*password\b", text)
        or re.search(r"\bold password\b", text)
    )
    has_scope = bool(
        re.search(r"\b(current password|existing password|same password|last \d+ passwords?|previous \d+ passwords?|prior \d+ passwords?|password history|retained password)\b", text)
    )
    return has_reuse_rule and not has_scope


def _has_auto_login_session_gap(text: str) -> bool:
    has_auto_login = bool(
        re.search(r"\b(logged in automatically|automatically logged in|auto[- ]login|logs? (them|the user) in)\b", text)
    )
    has_session_policy = bool(
        re.search(r"\b(session|sessions|mfa|2fa|two-factor|two factor|multi-factor|re-auth|reauth|device|trusted device|revoke|invalidate|log out|logout)\b", text)
    )
    return has_auto_login and not has_session_policy


def _has_control_transfer(text: str) -> bool:
    has_transfer = bool(re.search(r"\b(transfer|transfers|invite|invites|promote|promotes|demote|demotes|grant|grants|assign|assigns)\b", text))
    has_control = bool(set(tokenize(text)) & CONTROL_TRANSFER_TERMS)
    return has_transfer and has_control


def _has_receiver_consent(text: str) -> bool:
    receiver_accepts = bool(
        re.search(
            r"\b(new|receiving|recipient|target|invitee)\s+(owner|member|user|admin|party)\b.{0,80}\b(accept|approve|confirm|consent|decline|reject)",
            text,
        )
    )
    passive_acceptance = bool(re.search(r"\b(must|required to|needs to|has to)\s+(accept|approve|confirm|consent)", text))
    return receiver_accepts or passive_acceptance


def _primary_actor(intent: ExtractedIntent, text: str = "") -> str:
    lowered = text.lower()
    for actor, pattern in (
        ("admin", r"\b(admin|admins)\b.{0,60}\b(can|may|must|attempt|request|invite|upload|delete|transfer|remove|connect|reset)\b"),
        ("owner", r"\b(owner|owners)\b.{0,60}\b(can|may|must|attempt|request|invite|upload|delete|transfer|remove|connect|reset)\b"),
        ("member", r"\b(member|members)\b.{0,60}\b(can|may|must|attempt|request|invite|upload|delete|transfer|remove|connect|reset)\b"),
        ("user", r"\b(user|users)\b.{0,60}\b(can|may|must|attempt|request|invite|upload|delete|transfer|remove|connect|reset|forget|forgets)\b"),
    ):
        if actor in intent.actors and re.search(pattern, lowered):
            return actor
    for preferred in ("owner", "admin", "member", "user"):
        if preferred in intent.actors:
            return preferred
    return (intent.actors or ["authorized user"])[0]


def _primary_entity(intent: ExtractedIntent, text: str, title: str = "") -> str:
    scores = _primary_object_scores(text)
    if not scores:
        return "unspecified"

    best_score = max(scores.values())
    candidates = [label for label, score in scores.items() if score == best_score]

    title_matches = [label for label in candidates if _object_label_in_text(label, title)]
    if title_matches:
        candidates = title_matches

    if len(candidates) > 1:
        rule_scores = {
            label: sum(1 for rule in intent.explicit_rules if _object_label_in_text(label, rule))
            for label in candidates
        }
        best_rule_score = max(rule_scores.values(), default=0)
        if best_rule_score:
            candidates = [label for label in candidates if rule_scores[label] == best_rule_score]

    candidates.sort(key=lambda label: _object_first_index(label, f"{title} {text}"))
    return _display_object_label(candidates[0], text, title)


def _primary_object_scores(text: str) -> Counter[str]:
    scores: Counter[str] = Counter()
    subject_counts = _acting_subject_counts(text)

    for sentence in split_sentences(text):
        tokens = _raw_tokens(sentence)
        for index, token in enumerate(tokens):
            action = _stem_action(token)
            if action in PRIMARY_OBJECT_ACTIONS:
                receiver = _receiver_after_action(tokens, index, text)
                if receiver:
                    scores[receiver] += 1
        scores.update(_passive_object_scores(tokens, text))

    actor_labels = {_singularize(term) for term in ACTORS}
    return Counter(
        {
            label: score
            for label, score in scores.items()
            if score > 0 and (label not in actor_labels or label not in subject_counts or score > subject_counts[label])
        }
    )


def _acting_subject_counts(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for sentence in split_sentences(text):
        tokens = _raw_tokens(sentence)
        for index, token in enumerate(tokens[:-1]):
            label = _object_label_for_token(token, text)
            if not label:
                continue
            lookahead = tokens[index + 1 : index + 8]
            if any(_stem_action(next_token) in PRIMARY_OBJECT_ACTIONS for next_token in lookahead) or any(
                next_token in {"can", "may", "must", "should", "will"} for next_token in lookahead[:3]
            ):
                counts[label] += 1
    return counts


def _receiver_after_action(tokens: list[str], action_index: int, text: str) -> str | None:
    skip_tokens = {
        "a",
        "an",
        "another",
        "common",
        "new",
        "old",
        "own",
        "requested",
        "required",
        "some",
        "it",
        "the",
        "their",
        "them",
        "this",
        "those",
        "to",
    }
    stop_tokens = {"after", "before", "by", "for", "from", "if", "in", "into", "of", "on", "when", "where", "with"}
    for token in tokens[action_index + 1 : action_index + 9]:
        if token in skip_tokens or _stem_action(token) in PRIMARY_OBJECT_ACTIONS:
            continue
        if token in stop_tokens:
            return None
        label = _object_label_for_token(token, text)
        if label:
            return label
    return None


def _passive_object_scores(tokens: list[str], text: str) -> Counter[str]:
    scores: Counter[str] = Counter()
    for index, token in enumerate(tokens):
        label = _object_label_for_token(token, text)
        if not label:
            continue
        for next_index, next_token in enumerate(tokens[index + 1 : index + 12], start=index + 1):
            action = _stem_action(next_token)
            prefix = tokens[index + 1 : next_index]
            if action in PRIMARY_OBJECT_ACTIONS and any(aux in prefix for aux in {"are", "be", "been", "being", "is", "was", "were"}):
                scores[label] += 1
    for index, token in enumerate(tokens[:-1]):
        action = _stem_action(token)
        if action in PRIMARY_OBJECT_ACTIONS:
            label = _object_label_for_token(tokens[index + 1], text)
            if label:
                scores[label] += 1
    return scores


def _object_label_for_token(token: str, text: str) -> str | None:
    token = token.lower()
    base = OBJECT_TOKEN_ALIASES.get(token, _singularize(token))
    if _has_password_reset_flow(text) and base in {"link", "password", "token"}:
        return "password reset token"
    candidate_labels = {
        *(_singularize(term) for term in ENTITIES),
        *(_singularize(term) for term in ACTORS),
        *OBJECT_TOKEN_ALIASES.values(),
        "repository",
    }
    if base in candidate_labels:
        return base
    return None


def _object_label_in_text(label: str, text: str) -> bool:
    normalized = text.lower()
    if label == "password reset token":
        return bool(re.search(r"\b(password reset|reset link|reset token|password|link|token)\b", normalized))
    return bool(re.search(rf"\b{re.escape(label)}s?\b", normalized))


def _object_first_index(label: str, text: str) -> int:
    normalized = text.lower()
    if label == "password reset token":
        positions = [
            position
            for term in ("password reset", "reset link", "reset token", "password", "link", "token")
            if (position := normalized.find(term)) >= 0
        ]
        return min(positions) if positions else 10_000
    match = re.search(rf"\b{re.escape(label)}s?\b", normalized)
    return match.start() if match else 10_000


def _display_object_label(label: str, text: str, title: str) -> str:
    lowered = f"{title} {text}".lower()
    if label == "ownership" and "workspace" in lowered:
        return "workspace ownership"
    if label == "repository":
        return "repository connection" if "connect" in lowered else "repository"
    return label


def _primary_action_phrase(intent: ExtractedIntent, text: str, entity: str) -> str:
    actions = set(intent.actions)
    lowered = text.lower()
    if entity == "unspecified":
        return "complete the requested action"
    if "transfer" in actions or "transfer" in lowered:
        return f"transfer {entity}"
    if "invite" in actions:
        return "send an invitation"
    if entity == "password reset token":
        return "request a password reset token"
    if "reset link" == entity:
        return "request a reset link"
    if "upload" in actions or "upload" in lowered:
        return f"upload the {entity}"
    if "share" in actions and entity == "file":
        return "share the file"
    if "delete" in actions and entity == "file":
        return "delete the file"
    if "reset" in actions:
        return f"reset the {entity}"
    if "connect" in actions:
        return f"connect the {entity}"
    if "send" in actions:
        return "send the required notification"
    if actions:
        action = sorted(actions)[0]
        return f"{action} the {entity}"
    return f"complete the {entity} workflow"


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
    if term.endswith("ss"):
        return term
    if term.endswith("ies"):
        return f"{term[:-3]}y"
    if term.endswith("s") and len(term) > 3:
        return term[:-1]
    return term


def _stem_action(term: str) -> str:
    if term.endswith("ies") and len(term) > 5:
        return f"{term[:-3]}y"
    if term.endswith("ing") and len(term) > 5:
        stem = term[:-3]
        if stem in ACTION_TERMS:
            return stem
        if f"{stem}e" in ACTION_TERMS:
            return f"{stem}e"
        return stem
    if term.endswith("ed") and len(term) > 4:
        stem = term[:-2]
        if stem in ACTION_TERMS:
            return stem
        if f"{stem}e" in ACTION_TERMS:
            return f"{stem}e"
        return stem
    if term.endswith("s") and len(term) > 3:
        return term[:-1]
    return term
