-- migration_001.sql
-- Hermes Governance & Memory Layer (Phase 3.1)
-- Status: LOCKED

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS model_registry (
    canonical_slug TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    context_window INTEGER CHECK(context_window > 0),
    input_price REAL CHECK(input_price >= 0),
    output_price REAL CHECK(output_price >= 0),
    last_synced_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS memory_items (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK(type IN ('fact', 'preference', 'lesson', 'skill', 'dna_proposal', 'trust_event')),
    content TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0 CHECK(confidence >= 0.0 AND confidence <= 1.0),
    status TEXT NOT NULL DEFAULT 'candidate' CHECK(status IN ('candidate', 'approved', 'retired')),
    approved_by TEXT DEFAULT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'IDEA' CHECK(status IN ('IDEA', 'DRAFT', 'WORKER_RETURNED', 'M_REVIEWING', 'REVISION_REQUIRED', 'REVIEWED', 'APPROVED', 'REJECTED', 'RETIRED')),
    hash TEXT NOT NULL,
    author TEXT NOT NULL,
    parent_version INTEGER DEFAULT NULL,
    related_task TEXT DEFAULT NULL,
    test_status TEXT DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (artifact_id, version),
    FOREIGN KEY (parent_version) REFERENCES artifacts(version) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS worker_packets (
    task_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    objective TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT', 'SENT', 'UNDERSTANDING_RECEIVED', 'APPROVED_TO_EXECUTE', 'COMPLETED', 'FAILED', 'REJECTED')),
    payload TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
