import math
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _positive_int(name, default):
    value = os.getenv(name, default)
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a positive integer")

    if result <= 0:
        raise ValueError(f"{name} must be a positive integer")

    return result


def _risk_value():
    try:
        value = float(os.getenv("MAX_RISK_DEFAULT", "1.0"))
    except (TypeError, ValueError):
        raise ValueError("MAX_RISK_DEFAULT must be a number")

    if not math.isfinite(value) or not 0 < value <= 5:
        raise ValueError("MAX_RISK_DEFAULT must be greater than 0 and at most 5")

    return value


def _admin_chat_id():
    value = os.getenv("ADMIN_CHAT_ID", "").strip()

    if value:
        try:
            parsed = int(value)
        except ValueError:
            raise ValueError("ADMIN_CHAT_ID must be a valid integer")

        if parsed == 0:
            raise ValueError("ADMIN_CHAT_ID cannot be zero")

    return value


def _log_level():
    value = os.getenv("LOG_LEVEL", "INFO").upper()
    allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

    if value not in allowed:
        raise ValueError(
            "LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL"
        )

    return value


def _database_path():
    value = os.getenv("DATABASE_PATH", "nepse.db")

    if not value.strip():
        raise ValueError("DATABASE_PATH cannot be empty")

    return value


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    admin_chat_id: str = _admin_chat_id()
    database_path: str = _database_path()
    log_level: str = _log_level()
    data_cache_seconds: int = _positive_int("DATA_CACHE_SECONDS", "60")
    max_risk_default: float = _risk_value()


settings = Settings()
