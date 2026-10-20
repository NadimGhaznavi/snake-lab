from typing import Final


class DSnakeLab:

    DB_CREDENTIALS_FILE: Final[str] = "/opt/prod/snakelab/config/database.json"
    DB_HOST: Final[str] = "localhost"
    DB_NAME: Final[str] = "snakelab"
    DB_PORT: Final[int] = 3306
    DB_USER: Final[str] = "snakelab"
    MAX_MOVE_DELAY_MS: Final[int] = 100
    MOVE_DELAY_STEP_MS: Final[int] = 20
    PYTORCH_NUM_THREADS: Final[int] = 5
    SERVER_LOG_FILE: Final[str] = "/opt/prod/snakelab/logs/server.log"
    NETWORK_CONFIG_FILE: Final[str] = "/opt/prod/snakelab/conf/snakelab.json"
    VERSION: Final[str] = "2.1.0"
    CMDB_SUBTYPE: Final[str] = "Simulation Server"
    CMDB_SUPPLIER: Final[str] = "Nadim-Daniel"
    CMDB_CODENAME: Final[str] = "Zond"
    CMDB_TYPE: Final[str] = "application"
    CMDB_DATABASES: Final[tuple[tuple[str, str], ...]] = (("Snake Lab", "snakelab"),)
    CMDB_COMPONENTS: Final[tuple[tuple[str, str], ...]] = (("Logs", "logs"),)
    CMDB_NETWORK: Final[tuple[tuple[str, str, int], ...]] = (
        ("control", "0.0.0.0", 41970),
        ("telemetry", "0.0.0.0", 41971),
        ("events", "0.0.0.0", 41972),
    )
