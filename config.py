import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    admin_chat_id: str = os.getenv("ADMIN_CHAT_ID", "")
    database_path: str = os.getenv("DATABASE_PATH", "nepse.db")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    data_cache_seconds: int = int(os.getenv("DATA_CACHE_SECONDS", "60"))
    max_risk_default: float = float(os.getenv("MAX_RISK_DEFAULT", "1.0"))

settings = Settings()
