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
