"""Service Audio → Telegram uploader.

Watches a folder for MP3 recordings, waits until each file is fully written,
then uploads to a Telegram chat. Scheduled-deletes the message after a
configurable retention period.
"""
import logging
import signal
import sys
import time
from datetime import datetime, timedelta, timezone

from config import Config
from state import State
from transcode import transcode_if_needed, cleanup_transcoded
from uploader import TelegramUploader, build_display_filename, build_caption
from watcher import FolderWatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("main")

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    log.info("Received signal %s, shutting down...", signum)
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def process_ready_files(watcher, uploader, state, config):
    for path in watcher.find_ready_files():
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue

        if state.has_been_uploaded(str(path), stat.st_size, stat.st_mtime):
            continue

        display_name = build_display_filename(stat.st_mtime, config.location_name)
        caption = build_caption(stat.st_mtime, config.location_name)

        transcoded = None
        try:
            transcoded = transcode_if_needed(
                path,
                bitrate_kbps=config.transcode_bitrate_kbps,
                mono=config.transcode_mono,
            )
            message_id = uploader.upload_audio(transcoded, display_name, caption)
        except Exception as e:
            log.exception("Upload failed for %s: %s", path, e)
            # Record a "tombstone" so we don't retry this file forever.
            # message_id=0 is a sentinel meaning "never actually uploaded."
            state.record_upload(
                str(path),
                stat.st_size,
                stat.st_mtime,
                message_id=0,
                delete_after=datetime.now(timezone.utc),
            )
            log.warning(
                "Marking %s as permanently failed; will not retry. "
                "Fix the underlying issue and either rename the file or "
                "clear state.db to retry.",
                path.name,
            )
            continue
        finally:
            if transcoded is not None:
                cleanup_transcoded(transcoded, path)

        delete_after = datetime.now(timezone.utc) + timedelta(days=config.retention_days)
        state.record_upload(str(path), stat.st_size, stat.st_mtime, message_id, delete_after)
        log.info("Scheduled deletion for %s at %s", display_name, delete_after.isoformat())


def process_pending_deletions(uploader, state):
    for source_path, message_id in state.pending_deletions():
        if message_id == 0:
            # Tombstone for a failed upload; nothing to delete.
            state.mark_deleted(source_path)
            continue
        try:
            uploader.delete_message(message_id)
        except Exception as e:
            log.exception("Delete failed for message_id=%s: %s", message_id, e)
            continue
        # Mark as deleted whether Telegram accepted it or not — if the message
        # is already gone or too old to delete, no point in keep retrying.
        state.mark_deleted(source_path)


def main():
    try:
        config = Config()
    except (FileNotFoundError, ValueError) as e:
        log.error("Configuration error: %s", e)
        sys.exit(1)

    log.info("Starting up.\n%s", config.summary())

    state = State(config.state_db_path)
    uploader = TelegramUploader(config.bot_token, config.chat_id)
    watcher = FolderWatcher(
        folder=config.watch_folder,
        stable_seconds=config.file_stable_seconds,
        upload_delay_minutes=config.upload_delay_minutes,
    )

    while not _shutdown:
        try:
            process_ready_files(watcher, uploader, state, config)
            process_pending_deletions(uploader, state)
        except Exception as e:
            log.exception("Unexpected error in main loop: %s", e)

        # Sleep in short chunks so SIGTERM is responsive
        for _ in range(config.poll_interval_seconds):
            if _shutdown:
                break
            time.sleep(1)

    log.info("Shutdown complete.")


if __name__ == "__main__":
    main()
