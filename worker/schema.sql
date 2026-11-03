-- D1 Database Schema for The Digital Toolkit Backend

-- 1. Table: processed_topics (persistent topic history & deduplication)
CREATE TABLE IF NOT EXISTS processed_topics (
  id TEXT PRIMARY KEY,
  topic_title TEXT NOT NULL,
  fingerprint TEXT NOT NULL UNIQUE,
  category TEXT NOT NULL,
  post_id TEXT,
  post_url TEXT,
  publish_mode TEXT NOT NULL DEFAULT 'draft',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_processed_fingerprint ON processed_topics(fingerprint);
CREATE INDEX IF NOT EXISTS idx_processed_category ON processed_topics(category);

-- 2. Table: pipeline_runs (historical telemetry & report summaries)
CREATE TABLE IF NOT EXISTS pipeline_runs (
  run_id TEXT PRIMARY KEY,
  overall_status TEXT NOT NULL,
  selected_topic TEXT,
  total_duration_seconds REAL,
  dry_run INTEGER NOT NULL DEFAULT 1,
  publish_mode TEXT NOT NULL DEFAULT 'draft',
  post_id TEXT,
  post_url TEXT,
  report_json TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_runs_created_at ON pipeline_runs(created_at);
