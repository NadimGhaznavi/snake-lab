"""Read-only configuration lookup for the telemetry client."""

from typing import Any

from snakelab.database.SnakeDb import SnakeDb

from snakelab.constants.DSnakeLab import DSnakeLab

# Match Ax3l's web configuration checklist, including seed. Paired values are
# displayed separately; fixed settings and run length are excluded.
TUNED_FIELDS = (
    ("model_hidden_size", "Hidden Size"),
    ("model_layers", "Encoder Layers"),
    ("model_dropout", "Dropout"),
    ("training_sequence_length", "Sequence Length"),
    ("training_batch_size", "Batch Size"),
    ("training_learning_rate", "Learning Rate"),
    ("training_gamma", "Gamma"),
    ("epsilon_initial", "Epsilon: initial"),
    ("epsilon_decay", "Epsilon: decay"),
    ("game_rewards_closer_to_food", "Food Reward: closer"),
    ("game_rewards_further_from_food", "Food Reward: further"),
    ("epsilon_nice_probability", "EpsilonNice: probability"),
    ("epsilon_nice_steps", "EpsilonNice: steps"),
    ("seed", "Random Seed"),
)


class ConfigurationReader:
    def __init__(self, *, host: str = DSnakeLab.DB_HOST,
                 port: int = DSnakeLab.DB_PORT,
                 credentials_file: str = DSnakeLab.DB_CREDENTIALS_FILE) -> None:
        self.host = host
        self.port = port
        self.credentials_file = credentials_file

    def read(self, run_id: str) -> dict[str, Any] | None:
        database = SnakeDb.connect(
            self.credentials_file, host=self.host, port=self.port,
        )
        try:
            return database.get_configuration(run_id)
        finally:
            database.close()
