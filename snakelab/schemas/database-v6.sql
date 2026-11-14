-- Sequence-model choice and EpsilonNice settings and episode measurements.
-- Historical runs used the RNN without EpsilonNice. Safe to reapply.
ALTER TABLE configurations
    ADD COLUMN IF NOT EXISTS model_type VARCHAR(16) NOT NULL DEFAULT 'rnn',
    ADD COLUMN IF NOT EXISTS model_heads INT UNSIGNED NOT NULL DEFAULT 4,
    ADD COLUMN IF NOT EXISTS epsilon_nice_probability DOUBLE NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS epsilon_nice_steps INT UNSIGNED NOT NULL DEFAULT 20;

ALTER TABLE simulation_episodes
    ADD COLUMN IF NOT EXISTS epsilon_nice_injections INT UNSIGNED NOT NULL DEFAULT 0;
