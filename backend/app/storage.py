from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from .models import (
    DecisionCreateRequest,
    DecisionRecord,
    DecisionStatus,
    ProjectDomain,
    RiskOverlay,
    SpecAnalysisResponse,
    Strictness,
    ReviewResolutionRequest,
    SuppressionCreateRequest,
    SuppressionRecord,
    SuppressionReopenRequest,
    SuppressionStatus,
)
from .text_utils import compact_quote, stable_id


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "backend" / "data" / "speclint.sqlite3"


def _database_path() -> Path:
    return Path(os.getenv("SPECLINT_DB_PATH", DEFAULT_DB_PATH))


def _connect() -> sqlite3.Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS spec_versions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            spec_text TEXT NOT NULL,
            spec_hash TEXT NOT NULL,
            strictness TEXT NOT NULL,
            domain TEXT NOT NULL DEFAULT 'general',
            risk_overlays_json TEXT NOT NULL DEFAULT '[]',
            score INTEGER NOT NULL,
            verdict TEXT NOT NULL,
            issues_json TEXT NOT NULL,
            acceptance_tests_json TEXT NOT NULL,
            rewritten_spec TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS spec_versions_created_at_idx
            ON spec_versions (created_at DESC);

        CREATE TABLE IF NOT EXISTS suppressions (
            id TEXT PRIMARY KEY,
            spec_version_id TEXT NOT NULL,
            issue_id TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            issue_title TEXT NOT NULL,
            evidence_snapshot TEXT NOT NULL,
            evidence_hash TEXT NOT NULL,
            raw_evidence_hash TEXT,
            normalized_evidence_hash TEXT,
            owner TEXT NOT NULL,
            reason TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reopened_by TEXT,
            reopened_at TEXT,
            reopened_reason TEXT
        );

        CREATE INDEX IF NOT EXISTS suppressions_spec_version_idx
            ON suppressions (spec_version_id, status, expires_at);

        CREATE INDEX IF NOT EXISTS suppressions_issue_idx
            ON suppressions (issue_id);

        CREATE UNIQUE INDEX IF NOT EXISTS suppressions_one_active_idx
            ON suppressions (spec_version_id, issue_id)
            WHERE status = 'active';

        CREATE TABLE IF NOT EXISTS decisions (
            id TEXT PRIMARY KEY,
            spec_version_id TEXT NOT NULL,
            issue_id TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            issue_title TEXT NOT NULL,
            evidence_snapshot TEXT NOT NULL,
            evidence_hash TEXT NOT NULL,
            raw_evidence_hash TEXT,
            normalized_evidence_hash TEXT,
            owner TEXT NOT NULL,
            decision_note TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'decided',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reopened_by TEXT,
            reopened_at TEXT,
            reopened_reason TEXT
        );

        CREATE INDEX IF NOT EXISTS decisions_spec_version_idx
            ON decisions (spec_version_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS decisions_issue_idx
            ON decisions (issue_id);

        CREATE UNIQUE INDEX IF NOT EXISTS decisions_one_per_issue_idx
            ON decisions (spec_version_id, issue_id);
        """
    )
    _ensure_column(connection, "spec_versions", "domain", "TEXT NOT NULL DEFAULT 'general'")
    _ensure_column(connection, "spec_versions", "risk_overlays_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(connection, "suppressions", "raw_evidence_hash", "TEXT")
    _ensure_column(connection, "suppressions", "normalized_evidence_hash", "TEXT")
    _ensure_column(connection, "decisions", "raw_evidence_hash", "TEXT")
    _ensure_column(connection, "decisions", "normalized_evidence_hash", "TEXT")
    _ensure_column(connection, "decisions", "reopened_by", "TEXT")
    _ensure_column(connection, "decisions", "reopened_at", "TEXT")
    _ensure_column(connection, "decisions", "reopened_reason", "TEXT")
    connection.commit()


def _ensure_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def save_spec_version(
    report: SpecAnalysisResponse,
    *,
    title: str,
    spec_text: str,
    strictness: Strictness,
    domain: ProjectDomain,
    risk_overlays: list[RiskOverlay],
) -> str:
    spec_hash = _hash_text(spec_text)
    overlay_key = ",".join(sorted(overlay.value for overlay in risk_overlays))
    spec_version_id = stable_id(
        "spec",
        title.strip() or "Untitled spec",
        strictness.value,
        domain.value,
        overlay_key,
        spec_hash,
    )
    now = _now()
    with _connect() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO spec_versions (
                id,
                title,
                spec_text,
                spec_hash,
                strictness,
                domain,
                risk_overlays_json,
                score,
                verdict,
                issues_json,
                acceptance_tests_json,
                rewritten_spec,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                spec_version_id,
                report.title,
                spec_text,
                spec_hash,
                strictness.value,
                domain.value,
                json.dumps([overlay.value for overlay in risk_overlays]),
                report.score,
                report.verdict,
                json.dumps([issue.model_dump(mode="json") for issue in report.issues]),
                json.dumps([test.model_dump(mode="json") for test in report.acceptance_tests]),
                report.rewritten_spec,
                now,
            ),
        )
        _sync_review_artifacts(connection, report, spec_version_id, now)
        connection.commit()
    return spec_version_id


def list_suppressions(
    *,
    spec_version_id: str | None = None,
    status: SuppressionStatus | None = None,
) -> list[SuppressionRecord]:
    conditions: list[str] = []
    params: list[str] = []
    today = date.today().isoformat()

    if spec_version_id:
        conditions.append("spec_version_id = ?")
        params.append(spec_version_id)

    if status == SuppressionStatus.active:
        conditions.append("status = 'active'")
        conditions.append("expires_at >= ?")
        params.append(today)
    elif status == SuppressionStatus.expired:
        conditions.append("status = 'active'")
        conditions.append("expires_at < ?")
        params.append(today)
    elif status == SuppressionStatus.pending_review:
        conditions.append("status = 'pending_review'")
    elif status == SuppressionStatus.reopened:
        conditions.append("status = 'reopened'")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM suppressions
            {where}
            ORDER BY created_at DESC
            """,
            params,
        ).fetchall()
    return [_record_from_row(row) for row in rows]


def create_suppression(payload: SuppressionCreateRequest) -> SuppressionRecord:
    evidence_snapshot = compact_quote(payload.evidence_snapshot, limit=240)
    raw_evidence_hash, normalized_evidence_hash = _evidence_hashes(evidence_snapshot)
    evidence_hash = payload.evidence_hash or normalized_evidence_hash
    created_by = payload.created_by or payload.owner
    now = _now()
    with _connect() as connection:
        existing = connection.execute(
            """
            SELECT *
            FROM suppressions
            WHERE spec_version_id = ?
              AND issue_id = ?
              AND status IN ('active', 'pending_review')
            """,
            (payload.spec_version_id, payload.issue_id),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE suppressions
                SET issue_type = ?,
                    severity = ?,
                    issue_title = ?,
                    evidence_snapshot = ?,
                    evidence_hash = ?,
                    raw_evidence_hash = ?,
                    normalized_evidence_hash = ?,
                    owner = ?,
                    reason = ?,
                    expires_at = ?,
                    status = 'active',
                    created_by = ?
                WHERE id = ?
                """,
                (
                    payload.issue_type.value,
                    payload.severity.value,
                    payload.issue_title,
                    evidence_snapshot,
                    evidence_hash,
                    raw_evidence_hash,
                    normalized_evidence_hash,
                    payload.owner,
                    payload.reason,
                    payload.expires_at.isoformat(),
                    created_by,
                    existing["id"],
                ),
            )
            suppression_id = existing["id"]
        else:
            suppression_id = f"sup_{uuid4().hex[:12]}"
            connection.execute(
                """
                INSERT INTO suppressions (
                    id,
                    spec_version_id,
                    issue_id,
                    issue_type,
                    severity,
                    issue_title,
                    evidence_snapshot,
                    evidence_hash,
                    raw_evidence_hash,
                    normalized_evidence_hash,
                    owner,
                    reason,
                    expires_at,
                    status,
                    created_by,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    suppression_id,
                    payload.spec_version_id,
                    payload.issue_id,
                    payload.issue_type.value,
                    payload.severity.value,
                    payload.issue_title,
                    evidence_snapshot,
                    evidence_hash,
                    raw_evidence_hash,
                    normalized_evidence_hash,
                    payload.owner,
                    payload.reason,
                    payload.expires_at.isoformat(),
                    created_by,
                    now,
                ),
            )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM suppressions WHERE id = ?",
            (suppression_id,),
        ).fetchone()
    return _record_from_row(row)


def reopen_suppression(
    suppression_id: str,
    payload: SuppressionReopenRequest,
) -> SuppressionRecord | None:
    now = _now()
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM suppressions WHERE id = ?",
            (suppression_id,),
        ).fetchone()
        if not row:
            return None
        connection.execute(
            """
            UPDATE suppressions
            SET status = 'reopened',
                reopened_by = ?,
                reopened_at = ?,
                reopened_reason = ?
            WHERE id = ?
            """,
            (
                payload.reopened_by,
                now,
                payload.reopened_reason,
                suppression_id,
            ),
        )
        connection.commit()
        updated = connection.execute(
            "SELECT * FROM suppressions WHERE id = ?",
            (suppression_id,),
        ).fetchone()
    return _record_from_row(updated)


def reconfirm_suppression(
    suppression_id: str,
    payload: ReviewResolutionRequest,
) -> SuppressionRecord | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM suppressions WHERE id = ?",
            (suppression_id,),
        ).fetchone()
        if not row:
            return None
        connection.execute(
            """
            UPDATE suppressions
            SET status = 'active',
                reopened_by = NULL,
                reopened_at = NULL,
                reopened_reason = NULL
            WHERE id = ?
            """,
            (
                suppression_id,
            ),
        )
        connection.commit()
        updated = connection.execute(
            "SELECT * FROM suppressions WHERE id = ?",
            (suppression_id,),
        ).fetchone()
    return _record_from_row(updated)


def list_decisions(
    *,
    spec_version_id: str | None = None,
    status: DecisionStatus | None = None,
) -> list[DecisionRecord]:
    conditions: list[str] = []
    params: list[str] = []
    if spec_version_id:
        conditions.append("spec_version_id = ?")
        params.append(spec_version_id)
    if status:
        conditions.append("status = ?")
        params.append(status.value)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM decisions
            {where}
            ORDER BY created_at DESC
            """,
            params,
        ).fetchall()
    return [_decision_from_row(row) for row in rows]


def create_decision(payload: DecisionCreateRequest) -> DecisionRecord:
    evidence_snapshot = compact_quote(payload.evidence_snapshot, limit=240)
    raw_evidence_hash, normalized_evidence_hash = _evidence_hashes(evidence_snapshot)
    evidence_hash = payload.evidence_hash or normalized_evidence_hash
    created_by = payload.created_by or payload.owner
    now = _now()
    with _connect() as connection:
        existing = connection.execute(
            """
            SELECT *
            FROM decisions
            WHERE spec_version_id = ?
              AND issue_id = ?
            """,
            (payload.spec_version_id, payload.issue_id),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE decisions
                SET issue_type = ?,
                    severity = ?,
                    issue_title = ?,
                    evidence_snapshot = ?,
                    evidence_hash = ?,
                    raw_evidence_hash = ?,
                    normalized_evidence_hash = ?,
                    owner = ?,
                    decision_note = ?,
                    status = 'decided',
                    created_by = ?
                WHERE id = ?
                """,
                (
                    payload.issue_type.value,
                    payload.severity.value,
                    payload.issue_title,
                    evidence_snapshot,
                    evidence_hash,
                    raw_evidence_hash,
                    normalized_evidence_hash,
                    payload.owner,
                    payload.decision_note,
                    created_by,
                    existing["id"],
                ),
            )
            decision_id = existing["id"]
        else:
            decision_id = f"dec_{uuid4().hex[:12]}"
            connection.execute(
                """
                INSERT INTO decisions (
                    id,
                    spec_version_id,
                    issue_id,
                    issue_type,
                    severity,
                    issue_title,
                    evidence_snapshot,
                    evidence_hash,
                    raw_evidence_hash,
                    normalized_evidence_hash,
                    owner,
                    decision_note,
                    status,
                    created_by,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'decided', ?, ?)
                """,
                (
                    decision_id,
                    payload.spec_version_id,
                    payload.issue_id,
                    payload.issue_type.value,
                    payload.severity.value,
                    payload.issue_title,
                    evidence_snapshot,
                    evidence_hash,
                    raw_evidence_hash,
                    normalized_evidence_hash,
                    payload.owner,
                    payload.decision_note,
                    created_by,
                    now,
                ),
            )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()
    return _decision_from_row(row)


def reconfirm_decision(
    decision_id: str,
    payload: ReviewResolutionRequest,
) -> DecisionRecord | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()
        if not row:
            return None
        connection.execute(
            """
            UPDATE decisions
            SET status = 'decided',
                reopened_by = NULL,
                reopened_at = NULL,
                reopened_reason = NULL
            WHERE id = ?
            """,
            (
                decision_id,
            ),
        )
        connection.commit()
        updated = connection.execute(
            "SELECT * FROM decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()
    return _decision_from_row(updated)


def reopen_decision(
    decision_id: str,
    payload: SuppressionReopenRequest,
) -> DecisionRecord | None:
    now = _now()
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()
        if not row:
            return None
        connection.execute(
            """
            UPDATE decisions
            SET status = 'reopened',
                reopened_by = ?,
                reopened_at = ?,
                reopened_reason = ?
            WHERE id = ?
            """,
            (
                payload.reopened_by,
                now,
                payload.reopened_reason,
                decision_id,
            ),
        )
        connection.commit()
        updated = connection.execute(
            "SELECT * FROM decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()
    return _decision_from_row(updated)


def decisions_markdown(*, spec_version_id: str | None = None) -> str:
    decisions = list_decisions(spec_version_id=spec_version_id)
    lines = ["# SpecLint Requirements Decisions", ""]
    if not decisions:
        lines.append("No product decisions recorded.")
        return "\n".join(lines)

    for decision in decisions:
        lines.extend(
            [
                f"## {decision.issue_title}",
                "",
                f"- Decision ID: `{decision.id}`",
                f"- Spec version: `{decision.spec_version_id}`",
                f"- Issue: `{decision.issue_id}`",
                f"- Type: {decision.issue_type.value}",
                f"- Severity: {decision.severity.value}",
                f"- Status: {decision.status.value}",
                f"- Owner: {decision.owner}",
                f"- Created by: {decision.created_by}",
                f"- Created at: {decision.created_at.isoformat()}",
                "",
                "### Evidence",
                "",
                decision.evidence_snapshot,
                "",
                "### Decision",
                "",
                decision.decision_note,
                "",
            ]
        )
    return "\n".join(lines)


def _sync_review_artifacts(
    connection: sqlite3.Connection,
    report: SpecAnalysisResponse,
    spec_version_id: str,
    now: str,
) -> None:
    for issue in report.issues:
        _carry_forward_suppression(connection, issue, spec_version_id, report.title, now)
        _carry_forward_decision(connection, issue, spec_version_id, report.title, now)


def _carry_forward_suppression(
    connection: sqlite3.Connection,
    issue: object,
    spec_version_id: str,
    spec_title: str,
    now: str,
) -> None:
    if _current_artifact_exists(connection, "suppressions", issue, spec_version_id):
        return
    prior = _prior_suppression(connection, issue, spec_version_id, spec_title)
    if not prior:
        return

    evidence_snapshot, raw_hash, normalized_hash = _current_evidence_values(issue)
    status = _review_status(
        prior,
        normalized_hash,
        default_status=SuppressionStatus.active.value,
    )
    connection.execute(
        """
        INSERT INTO suppressions (
            id,
            spec_version_id,
            issue_id,
            issue_type,
            severity,
            issue_title,
            evidence_snapshot,
            evidence_hash,
            raw_evidence_hash,
            normalized_evidence_hash,
            owner,
            reason,
            expires_at,
            status,
            created_by,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"sup_{uuid4().hex[:12]}",
            spec_version_id,
            issue.id,
            issue.type.value,
            issue.severity.value,
            issue.title,
            evidence_snapshot,
            normalized_hash,
            raw_hash,
            normalized_hash,
            prior["owner"],
            prior["reason"],
            prior["expires_at"],
            status,
            prior["created_by"],
            now,
        ),
    )


def _carry_forward_decision(
    connection: sqlite3.Connection,
    issue: object,
    spec_version_id: str,
    spec_title: str,
    now: str,
) -> None:
    if _current_artifact_exists(connection, "decisions", issue, spec_version_id):
        return
    prior = _prior_decision(connection, issue, spec_version_id, spec_title)
    if not prior:
        return

    evidence_snapshot, raw_hash, normalized_hash = _current_evidence_values(issue)
    status = _review_status(
        prior,
        normalized_hash,
        default_status=DecisionStatus.decided.value,
    )
    connection.execute(
        """
        INSERT INTO decisions (
            id,
            spec_version_id,
            issue_id,
            issue_type,
            severity,
            issue_title,
            evidence_snapshot,
            evidence_hash,
            raw_evidence_hash,
            normalized_evidence_hash,
            owner,
            decision_note,
            status,
            created_by,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"dec_{uuid4().hex[:12]}",
            spec_version_id,
            issue.id,
            issue.type.value,
            issue.severity.value,
            issue.title,
            evidence_snapshot,
            normalized_hash,
            raw_hash,
            normalized_hash,
            prior["owner"],
            prior["decision_note"],
            status,
            prior["created_by"],
            now,
        ),
    )


def _current_artifact_exists(
    connection: sqlite3.Connection,
    table: str,
    issue: object,
    spec_version_id: str,
) -> bool:
    row = connection.execute(
        f"""
        SELECT id
        FROM {table}
        WHERE spec_version_id = ?
          AND status != 'reopened'
          AND (
            issue_id = ?
            OR (issue_type = ? AND issue_title = ?)
          )
        LIMIT 1
        """,
        (
            spec_version_id,
            issue.id,
            issue.type.value,
            issue.title,
        ),
    ).fetchone()
    return row is not None


def _prior_suppression(
    connection: sqlite3.Connection,
    issue: object,
    spec_version_id: str,
    spec_title: str,
) -> sqlite3.Row | None:
    today = date.today().isoformat()
    return connection.execute(
        """
        SELECT suppressions.*
        FROM suppressions
        JOIN spec_versions ON spec_versions.id = suppressions.spec_version_id
        WHERE spec_version_id != ?
          AND spec_versions.title = ?
          AND (
            issue_id = ?
            OR (issue_type = ? AND issue_title = ?)
          )
          AND (
            status = 'pending_review'
            OR (status = 'active' AND expires_at >= ?)
          )
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (
            spec_version_id,
            spec_title,
            issue.id,
            issue.type.value,
            issue.title,
            today,
        ),
    ).fetchone()


def _prior_decision(
    connection: sqlite3.Connection,
    issue: object,
    spec_version_id: str,
    spec_title: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT decisions.*
        FROM decisions
        JOIN spec_versions ON spec_versions.id = decisions.spec_version_id
        WHERE spec_version_id != ?
          AND spec_versions.title = ?
          AND (
            issue_id = ?
            OR (issue_type = ? AND issue_title = ?)
          )
          AND status IN ('decided', 'pending_review')
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (
            spec_version_id,
            spec_title,
            issue.id,
            issue.type.value,
            issue.title,
        ),
    ).fetchone()


def _current_evidence_values(issue: object) -> tuple[str, str, str]:
    evidence_snapshot = compact_quote(issue.evidence, limit=240)
    raw_hash, normalized_hash = _evidence_hashes(evidence_snapshot)
    return evidence_snapshot, raw_hash, normalized_hash


def _review_status(
    prior: sqlite3.Row,
    normalized_hash: str,
    *,
    default_status: str,
) -> str:
    prior_hash = prior["normalized_evidence_hash"] or _hash_text(
        _normalize_evidence(prior["evidence_snapshot"])
    )
    if prior["status"] == "pending_review" or prior_hash != normalized_hash:
        return "pending_review"
    return default_status


def _record_from_row(row: sqlite3.Row) -> SuppressionRecord:
    status = row["status"]
    if status == SuppressionStatus.active.value and row["expires_at"] < date.today().isoformat():
        status = SuppressionStatus.expired.value
    raw_evidence_hash = row["raw_evidence_hash"] or _hash_text(row["evidence_snapshot"])
    normalized_evidence_hash = row["normalized_evidence_hash"] or _hash_text(
        _normalize_evidence(row["evidence_snapshot"])
    )
    return SuppressionRecord(
        id=row["id"],
        spec_version_id=row["spec_version_id"],
        issue_id=row["issue_id"],
        issue_type=row["issue_type"],
        severity=row["severity"],
        issue_title=row["issue_title"],
        evidence_snapshot=row["evidence_snapshot"],
        evidence_hash=row["evidence_hash"],
        raw_evidence_hash=raw_evidence_hash,
        normalized_evidence_hash=normalized_evidence_hash,
        owner=row["owner"],
        reason=row["reason"],
        expires_at=row["expires_at"],
        status=status,
        created_by=row["created_by"],
        created_at=row["created_at"],
        reopened_by=row["reopened_by"],
        reopened_at=row["reopened_at"],
        reopened_reason=row["reopened_reason"],
    )


def _decision_from_row(row: sqlite3.Row) -> DecisionRecord:
    raw_evidence_hash = row["raw_evidence_hash"] or _hash_text(row["evidence_snapshot"])
    normalized_evidence_hash = row["normalized_evidence_hash"] or _hash_text(
        _normalize_evidence(row["evidence_snapshot"])
    )
    return DecisionRecord(
        id=row["id"],
        spec_version_id=row["spec_version_id"],
        issue_id=row["issue_id"],
        issue_type=row["issue_type"],
        severity=row["severity"],
        issue_title=row["issue_title"],
        evidence_snapshot=row["evidence_snapshot"],
        evidence_hash=row["evidence_hash"],
        raw_evidence_hash=raw_evidence_hash,
        normalized_evidence_hash=normalized_evidence_hash,
        owner=row["owner"],
        decision_note=row["decision_note"],
        status=row["status"] or DecisionStatus.decided.value,
        created_by=row["created_by"],
        created_at=row["created_at"],
        reopened_by=row["reopened_by"],
        reopened_at=row["reopened_at"],
        reopened_reason=row["reopened_reason"],
    )


def _evidence_hashes(value: str) -> tuple[str, str]:
    return _hash_text(value), _hash_text(_normalize_evidence(value))


def _normalize_evidence(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    normalized = re.sub(r"[^\w\s]", "", normalized)
    return normalized


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
