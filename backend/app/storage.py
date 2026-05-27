from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from .models import (
    SpecAnalysisResponse,
    Strictness,
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
        """
    )
    connection.commit()


def save_spec_version(
    report: SpecAnalysisResponse,
    *,
    title: str,
    spec_text: str,
    strictness: Strictness,
) -> str:
    spec_hash = _hash_text(spec_text)
    spec_version_id = stable_id("spec", title.strip() or "Untitled spec", strictness, spec_hash)
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
                score,
                verdict,
                issues_json,
                acceptance_tests_json,
                rewritten_spec,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                spec_version_id,
                report.title,
                spec_text,
                spec_hash,
                strictness.value,
                report.score,
                report.verdict,
                json.dumps([issue.model_dump(mode="json") for issue in report.issues]),
                json.dumps([test.model_dump(mode="json") for test in report.acceptance_tests]),
                report.rewritten_spec,
                now,
            ),
        )
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
    evidence_hash = payload.evidence_hash or _hash_text(evidence_snapshot)
    created_by = payload.created_by or payload.owner
    now = _now()
    with _connect() as connection:
        existing = connection.execute(
            """
            SELECT *
            FROM suppressions
            WHERE spec_version_id = ?
              AND issue_id = ?
              AND status = 'active'
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
                    owner = ?,
                    reason = ?,
                    expires_at = ?,
                    created_by = ?
                WHERE id = ?
                """,
                (
                    payload.issue_type.value,
                    payload.severity.value,
                    payload.issue_title,
                    evidence_snapshot,
                    evidence_hash,
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
                    owner,
                    reason,
                    expires_at,
                    status,
                    created_by,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
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


def _record_from_row(row: sqlite3.Row) -> SuppressionRecord:
    status = row["status"]
    if status == SuppressionStatus.active.value and row["expires_at"] < date.today().isoformat():
        status = SuppressionStatus.expired.value
    return SuppressionRecord(
        id=row["id"],
        spec_version_id=row["spec_version_id"],
        issue_id=row["issue_id"],
        issue_type=row["issue_type"],
        severity=row["severity"],
        issue_title=row["issue_title"],
        evidence_snapshot=row["evidence_snapshot"],
        evidence_hash=row["evidence_hash"],
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


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
