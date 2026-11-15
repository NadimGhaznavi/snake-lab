-- Episode reinforcement and exploration diagnostics. Safe to reapply.
ALTER TABLE simulation_episodes
    ADD COLUMN IF NOT EXISTS reward DOUBLE NULL,
    ADD COLUMN IF NOT EXISTS outcome VARCHAR(16) NULL,
    ADD COLUMN IF NOT EXISTS epsilon_injections INT UNSIGNED NULL;
