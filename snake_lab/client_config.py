"""Read-only configuration lookup for the telemetry client."""

import json
from pathlib import Path
from typing import Any

import pymysql

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
        credentials = json.loads(Path(self.credentials_file).read_text(encoding="utf-8"))
        connection = pymysql.connect(
            host=self.host, port=self.port,
            user=credentials.get("user", DSnakeLab.DB_USER),
            password=credentials["password"],
            database=credentials.get("database", DSnakeLab.DB_NAME),
            charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=3, read_timeout=3, write_timeout=3,
            autocommit=False,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute("START TRANSACTION READ ONLY")
                columns = ", ".join(name for name, _ in TUNED_FIELDS)
                cursor.execute(f"SELECT {columns} FROM configurations WHERE run_id = %s", (run_id,))
                return cursor.fetchone()
        finally:
            connection.close()
