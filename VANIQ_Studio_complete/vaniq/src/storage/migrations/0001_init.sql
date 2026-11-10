-- VANIQ schema v1
CREATE TABLE sources (
    id                TEXT PRIMARY KEY,            -- first 16 hex chars of SHA-256 of the uploaded file
    original_name     TEXT NOT NULL,
    stored_path       TEXT NOT NULL,
    normalized_path   TEXT,
    sha256            TEXT NOT NULL,
    source_url        TEXT NOT NULL DEFAULT 'UNKNOWN',
    speaker_id        TEXT NOT NULL DEFAULT 'UNKNOWN',
    dialect_label     TEXT NOT NULL DEFAULT 'UNKNOWN',   -- human-asserted label, never model-inferred
    permission_status TEXT NOT NULL DEFAULT 'UNKNOWN',   -- UNKNOWN | granted | denied
    permitted_usage   TEXT NOT NULL DEFAULT 'UNKNOWN',   -- UNKNOWN | private_research | internal_training | public_release
    consent_notes     TEXT NOT NULL DEFAULT '',
    duration_s        REAL,
    segmentation_status TEXT NOT NULL DEFAULT 'pending', -- success | no_speech | error | pending
    is_demo           INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL
);

CREATE TABLE clips (
    id                TEXT PRIMARY KEY,
    source_id         TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    start_s           REAL NOT NULL,
    end_s             REAL NOT NULL,
    duration_s        REAL NOT NULL,
    path              TEXT NOT NULL,
    rms_dbfs          REAL,
    peak_dbfs         REAL,
    clipping_count    INTEGER,
    silence_ratio     REAL,
    quality_flags     TEXT NOT NULL DEFAULT '[]',        -- JSON list of strings
    review_status     TEXT NOT NULL DEFAULT 'needs_review', -- needs_review | in_review | verified | rejected
    reference_transcript TEXT,                           -- human-verified reference (ground truth)
    reference_script  TEXT,
    reference_by      TEXT,
    reference_at      TEXT,
    notes             TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL
);
CREATE INDEX idx_clips_source ON clips(source_id);

CREATE TABLE transcripts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id           TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    provider          TEXT NOT NULL,                     -- gnani | demo-mock | imported
    provider_label    TEXT NOT NULL DEFAULT '',
    is_synthetic      INTEGER NOT NULL DEFAULT 0,        -- 1 => NOT a real transcription of the audio
    model             TEXT,
    language_code_requested TEXT,
    detected_language_code  TEXT,                        -- STT's language ID; NOT dialect identification
    request_id        TEXT,
    transcript_raw    TEXT NOT NULL,                     -- immutable raw STT output
    script            TEXT,
    latency_s         REAL,
    raw_response      TEXT,                              -- full provider JSON
    created_at        TEXT NOT NULL
);
CREATE INDEX idx_transcripts_clip ON transcripts(clip_id);

CREATE TABLE suggestions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_id     INTEGER NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    start_char        INTEGER NOT NULL,
    end_char          INTEGER NOT NULL,
    original          TEXT NOT NULL,
    replacement       TEXT NOT NULL,
    kind              TEXT NOT NULL,                     -- lexical | spelling | normalization | manual
    backend           TEXT NOT NULL,                     -- rule-based | human | <future model name>
    rule_id           TEXT,
    confidence        REAL,
    confidence_basis  TEXT NOT NULL DEFAULT '',
    explanation       TEXT NOT NULL DEFAULT '',
    uncertain         INTEGER NOT NULL DEFAULT 1,
    status            TEXT NOT NULL DEFAULT 'pending',   -- pending | accepted | rejected | modified
    final_replacement TEXT,
    decided_by        TEXT,
    decided_at        TEXT,
    created_at        TEXT NOT NULL
);
CREATE INDEX idx_suggestions_transcript ON suggestions(transcript_id);

CREATE TABLE lexicon_entries (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_form       TEXT NOT NULL,
    target_form       TEXT NOT NULL,
    kind              TEXT NOT NULL DEFAULT 'lexical',
    context_prev      TEXT NOT NULL DEFAULT '',          -- optional required previous token
    context_next      TEXT NOT NULL DEFAULT '',          -- optional required next token
    status            TEXT NOT NULL DEFAULT 'candidate', -- demo | candidate | verified
    provenance        TEXT NOT NULL DEFAULT '',
    notes             TEXT NOT NULL DEFAULT '',
    enabled           INTEGER NOT NULL DEFAULT 1,
    is_demo           INTEGER NOT NULL DEFAULT 0,
    created_by        TEXT,
    created_at        TEXT NOT NULL
);

CREATE TABLE eval_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at        TEXT NOT NULL,
    params            TEXT NOT NULL,
    results           TEXT NOT NULL
);

CREATE TABLE audit_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                TEXT NOT NULL,
    actor             TEXT NOT NULL,
    action            TEXT NOT NULL,
    entity            TEXT NOT NULL,
    entity_id         TEXT NOT NULL,
    detail            TEXT NOT NULL DEFAULT '{}'
);
