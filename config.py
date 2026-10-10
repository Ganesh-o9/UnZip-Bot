"""
NovaUnzip - Central Configuration Module
Validates required credentials, sets quotas, and handles optional database connections.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

class Config:
    # Telegram API Credentials (from my.telegram.org)
    API_ID: int = int(os.getenv("API_ID", "0"))
    API_HASH: str = os.getenv("API_HASH", "").strip()
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

    # Bot Owner and Authorized User IDs
    OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))
    AUTH_USERS: list[int] = [
        int(u) for u in os.getenv("AUTH_USERS", "").split(",") if u.strip().isdigit()
    ]
    if OWNER_ID and OWNER_ID not in AUTH_USERS:
        AUTH_USERS.append(OWNER_ID)

    # Storage and Limits
    WORKDIR: Path = Path(os.getenv("WORKDIR", "./downloads")).resolve()
    MAX_EXTRACT_SIZE_GB: int = int(os.getenv("MAX_EXTRACT_SIZE_GB", "10"))
    SPLIT_CHUNK_SIZE_MB: int = int(os.getenv("SPLIT_CHUNK_SIZE_MB", "1950"))
    PROGRESS_UPDATE_INTERVAL: float = float(os.getenv("PROGRESS_UPDATE_INTERVAL", "3.5"))

    # Telegram Premium Userbot (Optional for 4GB uploads)
    USERBOT_SESSION: str = os.getenv("USERBOT_SESSION", "").strip()

    # Optional MongoDB for persistent user settings
    MONGO_URL: str = os.getenv("MONGO_URL", "").strip()

    @classmethod
    def validate(cls):
        missing = []
        if not cls.API_ID:
            missing.append("API_ID")
        if not cls.API_HASH:
            missing.append("API_HASH")
        if not cls.BOT_TOKEN:
            missing.append("BOT_TOKEN")
        if missing:
            raise ValueError(f"Missing mandatory environment variables: {', '.join(missing)}")
        cls.WORKDIR.mkdir(parents=True, exist_ok=True)

Config.validate()
