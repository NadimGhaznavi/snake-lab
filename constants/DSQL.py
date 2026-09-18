"""SQL schema mappings shared by SnakeLab persistence components."""

from typing import Final


class DSQL:
    """Constants for mapping application configurations to SQL columns."""

    # Stable SQL column order, matching database-v3.sql.
    CONFIGURATION_PATHS: Final[tuple[str, ...]] = (
        "epochs",
        "seed",
        "game.board_width",
        "game.board_height",
        "game.initial_snake_length",
        "game.max_moves_multiplier",
        "game.rewards.food",
        "game.rewards.wall",
        "game.rewards.snake",
        "game.rewards.max_moves",
        "game.rewards.empty",
        "game.rewards.closer_to_food",
        "game.rewards.further_from_food",
        "model.hidden_size",
        "model.layers",
        "model.dropout",
        "training.sequence_length",
        "training.batch_size",
        "training.replay_max_frames",
        "training.learning_rate",
        "training.gamma",
        "training.tau",
        "training.max_gradient_norm",
        "epsilon.initial",
        "epsilon.minimum",
        "epsilon.decay",
    )
