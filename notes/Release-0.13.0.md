# Pre-Release v0.13.0 Spec

## Overview

This release will have no protocol or user interface changes. Existing simulation history will be cleared as a one-time release operation.

The purpose of this change is to expose simulation configurations in a way that can be easily queried using SQL. This will allow an intelligent search of the configuration search space i.e. which hyperparameters have been searched and which have not. This data will be consumed by external applications.

A new table, `configurations`, will be created based on the project's `simulation-config-v1.schema`.

This table will house a simulation's runtime configuration. This configuration is currently stored as a JSON blob in the `config` column of the `simulation_runs` table.

Start this release with an empty database using uninstall, an explicit database drop, and install. The uninstaller preserves MariaDB data, so the database must be dropped separately while the service is stopped. Historical configurations will not be migrated; no reset logic is included in the schema.

See `CHANGELOG.md` for the one-time commands.

Additionally, when a valid configuration is received by the service the values from the configuration will be stored in the database table. This will be a new part of the normal operation.

## Remove

Confirm that the `"x-snakelab-sweepable"` key is unused and remove it from the JSON schema.

## List of Configuration Elements

In addition to this list, a `run_id` column will be added to link the configuration to a simulation run.

- epochs
- seed
- game.board_height
- game.board_width
- game.initial_snake_length
- game.max_moves_multiplier
- game.rewards.food
- game.rewards.wall
- game.rewards.snake
- game.rewards.max_moves
- game.rewards.empty
- game.rewards.closer_to_food
- game.rewards.further_from_food
- model.hidden_size
- model.layers
- model.dropout
- training.sequence_length
- training.batch_size
- training.replay_max_frames
- training.learning_rate
- training.gamma
- training.tau
- training.max_gradient_norm
- epsilon.initial
- epsilon.minimum
- epsilon.decay





