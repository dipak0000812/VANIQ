-- Studio layer: agent runs, workflows, knowledge. Additive; no existing table is altered.
CREATE TABLE agent_runs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT 'command',
    status TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '{}',
    steps TEXT NOT NULL DEFAULT '[]',
    note TEXT NOT NULL DEFAULT '',
    approved_by TEXT,
    approved_at TEXT,
    finished_at TEXT
);
CREATE INDEX idx_agent_runs_created ON agent_runs(created_at);

CREATE TABLE workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Custom',
    description TEXT NOT NULL DEFAULT '',
    graph TEXT NOT NULL,
    is_template INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE workflow_runs (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    status TEXT NOT NULL,
    graph TEXT NOT NULL,
    node_states TEXT NOT NULL DEFAULT '{}',
    approved_by TEXT,
    approved_at TEXT,
    finished_at TEXT,
    error TEXT
);
CREATE INDEX idx_workflow_runs_wf ON workflow_runs(workflow_id);

CREATE TABLE knowledge_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('convention','reference','note')),
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved')),
    provenance TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    approved_by TEXT,
    approved_at TEXT,
    updated_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE knowledge_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES knowledge_items(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    edited_by TEXT NOT NULL,
    edited_at TEXT NOT NULL
);
CREATE INDEX idx_knowledge_versions_item ON knowledge_versions(item_id);
