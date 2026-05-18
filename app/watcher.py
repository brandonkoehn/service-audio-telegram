"""Watch a folder for new MP3 files and detect when they have finished writing."""
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)


class FolderWatcher:
    def __init__(self, folder: Path, stable_seconds: int, upload_delay_minutes: int):
        self.folder = folder
        self.stable_seconds = stable_seconds
        self.upload_delay_minutes = upload_delay_minutes
        # Track per-file: last seen size, timestamp of that observation
        self._observations = {}

    def find_ready_files(self) -> list:
        """Return list of Path objects for MP3 files that are stable AND past the upload delay.
        A file is 'ready' when:
          1. Its size has not changed for at least `stable_seconds`
          2. At least `upload_delay_minutes` have passed since it became stable
        """
        if not self.folder.exists():
            log.warning("Watch folder does not exist yet: %s", self.folder)
            return []

        now = time.time()
        ready = []
        current_files = set()

        for path in self.folder.glob("*.mp3"):
            if not path.is_file():
                continue
            current_files.add(str(path))
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            size = stat.st_size
            obs = self._observations.get(str(path))

            if obs is None:
                # First time seeing this file
                self._observations[str(path)] = {
                    "size": size,
                    "size_first_stable_at": None,
                    "last_check": now,
                }
                continue

            if size != obs["size"]:
                # Still being written
                obs["size"] = size
                obs["size_first_stable_at"] = None
                obs["last_check"] = now
                continue

            # Size unchanged since last check
            if obs["size_first_stable_at"] is None:
                obs["size_first_stable_at"] = now
                obs["last_check"] = now
                continue

            stable_for = now - obs["size_first_stable_at"]
            obs["last_check"] = now

            if stable_for >= self.stable_seconds:
                # File has been stable long enough. Check upload delay.
                stable_at = datetime.fromtimestamp(obs["size_first_stable_at"], tz=timezone.utc)
                ready_at = stable_at + timedelta(minutes=self.upload_delay_minutes)
                if datetime.now(timezone.utc) >= ready_at:
                    ready.append(path)

        # Prune observations for files that no longer exist
        stale = set(self._observations.keys()) - current_files
        for s in stale:
            del self._observations[s]

        return ready
