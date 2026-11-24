import os
from pathlib import Path

MIN_PASSWORD_LENGTH = 10


def database_path() -> Path:
    return Path(os.getenv("STOCKFLOW_DB_PATH", "data/stockflow.db")).resolve()


def jwt_secret() -> str:
    value = os.getenv("STOCKFLOW_JWT_SECRET", "")
    if len(value) < 32:
        raise RuntimeError("STOCKFLOW_JWT_SECRET 必须至少 32 个字符")
    return value


def token_hours() -> int:
    try:
        value = int(os.getenv("STOCKFLOW_TOKEN_HOURS", "24"))
    except ValueError:
        raise RuntimeError("STOCKFLOW_TOKEN_HOURS 必须是整数") from None
    if value < 1 or value > 168:
        raise RuntimeError("STOCKFLOW_TOKEN_HOURS 必须在 1 到 168 之间")
    return value
