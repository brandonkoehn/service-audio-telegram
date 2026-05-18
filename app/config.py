"""Load and validate configuration from config.txt."""
import os
from pathlib import Path


class Config:
    def __init__(self, config_path: str = "/config/config.txt"):
        self.config_path = config_path
        self._values = {}
        self._load()
        self._validate()

    def _load(self):
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(
                f"Config file not found at {self.config_path}. "
                f"Copy config.example.txt to config.txt and fill in your values."
            )
        with open(self.config_path, "r") as f:
            for line_num, raw in enumerate(f, 1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    raise ValueError(f"Invalid config line {line_num}: {line}")
                key, _, value = line.partition("=")
                self._values[key.strip()] = value.strip()

    def _validate(self):
        required = [
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CHAT_ID",
            "WATCH_FOLDER",
            "LOCATION_NAME",
        ]
        missing = [k for k in required if not self._values.get(k)]
        if missing:
            raise ValueError(f"Missing required config keys: {', '.join(missing)}")

    @property
    def bot_token(self) -> str:
        return self._values["TELEGRAM_BOT_TOKEN"]

    @property
    def chat_id(self) -> str:
        return self._values["TELEGRAM_CHAT_ID"]

    @property
    def watch_folder(self) -> Path:
        return Path(self._values["WATCH_FOLDER"])

    @property
    def location_name(self) -> str:
        return self._values["LOCATION_NAME"]

    @property
    def upload_delay_minutes(self) -> int:
        return int(self._values.get("UPLOAD_DELAY_MINUTES", "10"))

    @property
    def retention_days(self) -> int:
        return int(self._values.get("MESSAGE_RETENTION_DAYS", "7"))

    @property
    def file_stable_seconds(self) -> int:
        return int(self._values.get("FILE_STABLE_SECONDS", "60"))

    @property
    def poll_interval_seconds(self) -> int:
        return int(self._values.get("POLL_INTERVAL_SECONDS", "30"))

    @property
    def state_db_path(self) -> str:
        return self._values.get("STATE_DB_PATH", "/state/state.db")

    def summary(self) -> str:
        return (
            f"Location: {self.location_name}\n"
            f"Watch folder: {self.watch_folder}\n"
            f"Upload delay: {self.upload_delay_minutes} min after file stable\n"
            f"File stable threshold: {self.file_stable_seconds} sec\n"
            f"Message retention: {self.retention_days} days\n"
            f"State DB: {self.state_db_path}"
        )
