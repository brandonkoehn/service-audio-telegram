"""Re-encode an MP3 to a target bitrate using ffmpeg so the result fits
within Telegram's 50 MB bot upload limit."""
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

# Telegram bot API limit for sendAudio is 50 MB.
TELEGRAM_MAX_BYTES = 50 * 1024 * 1024


def transcode_if_needed(source: Path, bitrate_kbps: int, mono: bool) -> Path:
    """Return a path to a file that is safe to upload.

    If the source is already under the Telegram limit, it is returned unchanged.
    Otherwise, ffmpeg re-encodes it to the configured bitrate and the new file
    path is returned. The caller is responsible for cleanup of the new file
    (use cleanup_transcoded() once the upload is complete).
    """
    size = source.stat().st_size
    if size <= TELEGRAM_MAX_BYTES:
        log.info("File %s is %.1f MB, no re-encode needed", source.name, size / 1024 / 1024)
        return source

    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "File is over Telegram's 50 MB limit and ffmpeg is not installed. "
            "Cannot re-encode."
        )

    # Output to /tmp so we don't pollute the read-only recordings mount.
    tmp_dir = Path(tempfile.mkdtemp(prefix="transcode_"))
    output = tmp_dir / source.name

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(source),
        "-vn",                              # drop any video/cover-art streams
        "-c:a", "libmp3lame",
        "-b:a", f"{bitrate_kbps}k",
        "-ac", "1" if mono else "2",
        str(output),
    ]
    log.info(
        "Re-encoding %s (%.1f MB) at %d kbps %s",
        source.name,
        size / 1024 / 1024,
        bitrate_kbps,
        "mono" if mono else "stereo",
    )
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()}")

    new_size = output.stat().st_size
    log.info(
        "Re-encoded to %.1f MB (%.0f%% of original)",
        new_size / 1024 / 1024,
        100 * new_size / size,
    )
    if new_size > TELEGRAM_MAX_BYTES:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError(
            f"Re-encoded file is still {new_size / 1024 / 1024:.1f} MB, over "
            f"Telegram's 50 MB limit. Try a lower TRANSCODE_BITRATE_KBPS."
        )
    return output


def cleanup_transcoded(transcoded_path: Path, original_path: Path):
    """Remove the transcoded temp file and its directory, if it isn't the original."""
    if transcoded_path == original_path:
        return
    try:
        shutil.rmtree(transcoded_path.parent, ignore_errors=True)
    except Exception as e:
        log.warning("Failed to clean up %s: %s", transcoded_path.parent, e)
