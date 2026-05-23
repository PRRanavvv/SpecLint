CREATE TABLE IF NOT EXISTS spec_reports (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    spec_text TEXT NOT NULL,
    score INTEGER NOT NULL,
    verdict TEXT NOT NULL,
    issues JSONB NOT NULL,
    acceptance_tests JSONB NOT NULL,
    rewritten_spec TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS spec_reports_created_at_idx
    ON spec_reports (created_at DESC);

