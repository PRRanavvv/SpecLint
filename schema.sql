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
