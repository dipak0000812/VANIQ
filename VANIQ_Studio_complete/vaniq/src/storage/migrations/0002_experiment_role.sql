-- P0 linguistic integrity: label every transcript with its experiment role.
-- Additive and backward compatible. Existing provider rows become 'baseline'. Imported rows become 'human_import'.
ALTER TABLE transcripts ADD COLUMN experiment_role TEXT NOT NULL DEFAULT 'baseline' CHECK (experiment_role IN ('baseline','candidate','human_import'));
UPDATE transcripts SET experiment_role='human_import' WHERE provider='imported';
CREATE INDEX idx_transcripts_role ON transcripts(experiment_role);
