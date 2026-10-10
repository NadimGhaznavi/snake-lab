-- Complete winning game, including frame 0 and the terminal move.
-- Safe to reapply. Older runs have no captured frames.
CREATE TABLE IF NOT EXISTS simulation_high_score_frames (
    run_id CHAR(36) NOT NULL,
    step INT UNSIGNED NOT NULL,
    episode INT UNSIGNED NOT NULL,
    frame JSON NOT NULL,

    PRIMARY KEY (run_id, step),
    CONSTRAINT fk_high_score_frame_run
        FOREIGN KEY (run_id)
        REFERENCES simulation_runs(run_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
