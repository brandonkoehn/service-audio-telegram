"""Telegram Bot API client — uploads audio files and deletes messages."""
import logging
import requests
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


def _scrub(text: str, secret: str) -> str:
    """Replace the bot token in any string so it can't leak to logs."""
    if not secret:
        return text
    return text.replace(secret, "***BOT_TOKEN***")


class TelegramUploader:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def upload_audio(self, file_path: Path, display_filename: str, caption: str) -> int:
        """Upload an audio file. Returns the message_id of the posted message."""
        url = f"{self.base_url}/sendAudio"
        with open(file_path, "rb") as f:
            files = {"audio": (display_filename, f, "audio/mpeg")}
            data = {
                "chat_id": self.chat_id,
                "caption": caption,
                "title": display_filename.rsplit(".", 1)[0],
            }
            log.info("Posting %s to chat %s", display_filename, self.chat_id)
            resp = requests.post(url, data=data, files=files, timeout=600)
        if not resp.ok:
            raise RuntimeError(
                f"Telegram upload failed (HTTP {resp.status_code}): "
                f"{_scrub(resp.text, self.bot_token)}"
            )
        body = resp.json()
        if not body.get("ok"):
            raise RuntimeError(
                f"Telegram API error: {_scrub(str(body), self.bot_token)}"
            )
        message_id = body["result"]["message_id"]
        log.info("Uploaded successfully, message_id=%s", message_id)
        return message_id

    def delete_message(self, message_id: int) -> bool:
        url = f"{self.base_url}/deleteMessage"
        try:
            resp = requests.post(
                url,
                data={"chat_id": self.chat_id, "message_id": message_id},
                timeout=30,
            )
        except requests.RequestException as e:
            log.warning("Network error deleting message_id=%s: %s",
                        message_id, _scrub(str(e), self.bot_token))
            return False
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if body.get("ok"):
            log.info("Deleted message_id=%s", message_id)
            return True
        # If message is already gone or too old, Telegram returns an error.
        # Treat as "done" so we don't keep retrying forever.
        log.warning(
            "Could not delete message_id=%s: %s",
            message_id,
            _scrub(str(body or resp.text), self.bot_token),
        )
        return False


def build_display_filename(mtime: float, location_name: str) -> str:
    """Produce a sort-friendly filename like 2026-05-18_0930_Church.mp3"""
    dt = datetime.fromtimestamp(mtime)
    safe_location = location_name.replace(" ", "_")
    return f"{dt.strftime('%Y-%m-%d_%H%M')}_{safe_location}.mp3"


def build_caption(mtime: float, location_name: str) -> str:
    dt = datetime.fromtimestamp(mtime)
    return f"{location_name} — {dt.strftime('%A, %B %d %Y at %I:%M %p')}"
