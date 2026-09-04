from typing import Final


class DSnakeLab:

    DB_CREDENTIALS_FILE: Final[str] = "/opt/snake-lab/config/database.json"
    DB_HOST: Final[str] = "localhost"
    DB_NAME: Final[str] = "snakelab"
    DB_PORT: Final[int] = 3306
    DB_USER: Final[str] = "snakelab"
    PORT: Final[int] = 41970
    TELEMETRY_FRAME_RATE: Final[float] = 15.0
    TELEMETRY_PORT: Final[int] = 41971
    SERVER_LOG_FILE: Final[str] = "/opt/snake-lab/logs/server.log"
    VERSION: Final[str] = "0.8.0"
