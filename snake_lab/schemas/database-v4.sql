-- One high-score board snapshot per simulation, rendered on demand.
-- NULL means no snapshot is available. Safe to reapply.
ALTER TABLE simulation_runs
    ADD COLUMN IF NOT EXISTS high_score_snapshot JSON NULL;
