"""Read-only configuration lookup for the telemetry client."""

from typing import Any

from snake_lab.database.SnakeDb import SnakeDb

from constants.DSnakeLab import DSnakeLab

# The whole-config LLM searches these fields; seed, run length and schema
# constants are deliberately excluded. Paired values are displayed separately.
TUNED_FIELDS = (
    ("model_hidden_size", "Hidden size"),
    ("training_sequence_length", "Sequence length"),
    ("training_batch_size", "Batch size"),
    ("training_learning_rate", "Learning rate"),
    ("training_gamma", "Gamma"),
    ("epsilon_initial", "Epsilon initial"),
    ("epsilon_decay", "Epsilon decay"),
    ("game_rewards_closer_to_food", "Closer reward"),
    ("game_rewards_further_from_food", "Further reward"),
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
