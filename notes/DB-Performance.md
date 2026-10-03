# DB Performance Idea

## Overview

| Priority | Proposed change | Expected benefit |
|---|---|---|
| **1** | Add `total_steps BIGINT UNSIGNED` to `simulation_runs`, maintained alongside `episode_count` | Avoids summing every episode’s steps on each page load. The current plan scans the episode table and uses a temporary table and sort. |
| **2** | Store the simulation-to-conversation association and completed LLM timing summary in Ax3l | Avoids repeatedly extracting run IDs from message JSON and reconstructing prompt/response timing. Keep these records in Ax3l, which owns the conversations. |
| **3** | If episode aggregation remains, benchmark a covering index on `simulation_episodes (run_id, steps)` | Could make the aggregation scan narrower. It still reads every relevant episode and adds storage and insert overhead. |
| **4** | Benchmark `simulation_runs (status, id)` | Matches completed-run filtering and simulation order. Likely modest benefit when almost all runs are completed—as they are here. |