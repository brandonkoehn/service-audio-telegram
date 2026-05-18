# Service Audio → Telegram

Watches a folder for new MP3 recordings and automatically uploads them to a
Telegram chat. Designed for unattended use on a Mac Mini (or any Linux/macOS
host running Docker) that captures live audio from a sound system.

Originally built for posting church service recordings, but works for any
"record audio → publish a file" workflow.

## What it does

1. Monitors a local folder for new `.mp3` files.
2. Detects when a recording has finished writing (file size stable for N seconds).
3. Waits a configurable delay after the file is stable.
4. Uploads the file to a Telegram chat with a sortable filename like
   `2026-05-18_0930_Church.mp3` and a human-readable caption.
5. After a configurable number of days, deletes the message from the chat.

State is kept in SQLite so restarts don't lose pending deletions or
re-upload files that were already posted.

## Requirements

- Docker (Docker Desktop on Mac, or Docker Engine on Linux).
- A Telegram bot token (free, from [@BotFather](https://t.me/BotFather)).
- A Telegram group chat where the bot has been added as a **group administrator**
  with "Delete messages" permission. Without admin rights, the bot can only
  delete messages younger than 48 hours.

## Initial Telegram setup (one-time)

### Create the bot

1. Open Telegram and start a chat with [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts:
   - Display name (e.g. `Moremangin Service Audio`)
   - Username — must end in `bot` (e.g. `moremangin_audio_bot`)
3. BotFather replies with an HTTP API token. **Save it somewhere safe** —
   it's effectively your bot's password.

### Create the group and add the bot

1. Create a new Telegram group and add your bot as a member.
2. Open group settings → Administrators → Add Administrator → select your bot.
3. Grant **only** the "Delete messages" permission. Leave everything else off.
4. Adding any admin automatically converts the group to a supergroup. This is
   expected and required for the 48-hour delete limit to be lifted.

### Get the chat ID

1. Temporarily add [@getidsbot](https://t.me/getidsbot) (or
   [@RawDataBot](https://t.me/RawDataBot)) to the group.
2. It will post the group's chat ID — a negative number like `-1001234567890`.
3. Remove the helper bot from the group.

## Host setup

### macOS

1. Install Docker Desktop from <https://www.docker.com/products/docker-desktop>.
2. Create the recordings folder:
   ```bash
   sudo mkdir -p /Users/Shared/ServiceAudio/recordings
   sudo chmod 775 /Users/Shared/ServiceAudio/recordings
   ```
3. Configure your recording application (e.g. `butt`) to save MP3s to
   `/Users/Shared/ServiceAudio/recordings`.

### Linux

Use `/opt/service-audio/recordings` (or any path you prefer) and update
`docker-compose.yml` accordingly.

## Deploying

1. Clone this repo onto the host:
   ```bash
   git clone https://github.com/YOUR-USERNAME/service-audio-telegram.git
   cd service-audio-telegram
   ```

2. Create your config:
   ```bash
   cp config.example.txt config.txt
   ```
   Edit `config.txt` and fill in `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and
   `LOCATION_NAME`. The other values have sensible defaults.

3. Build and start the container:
   ```bash
   docker compose up -d --build
   ```

4. Check the logs:
   ```bash
   docker compose logs -f
   ```
   You should see the startup banner and the configuration summary.

5. To stop:
   ```bash
   docker compose down
   ```

The container restarts automatically on reboot or crash (`restart: unless-stopped`).

## Configuration reference

See `config.example.txt` for all options. The most important ones:

| Key | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From BotFather. |
| `TELEGRAM_CHAT_ID` | Target group, usually a negative number. |
| `LOCATION_NAME` | Appears in captions and filenames (e.g. `Church`, `School`). |
| `UPLOAD_DELAY_MINUTES` | Wait this long after the file stops growing before uploading. |
| `FILE_STABLE_SECONDS` | How long the file size must be unchanged to count as "done." |
| `MESSAGE_RETENTION_DAYS` | When to auto-delete the message. |

To change any value, edit `config.txt` and restart the container:
```bash
docker compose restart
```

No image rebuild is needed for config changes — the file is mounted from the host.

## Running multiple instances

To deploy to a second location (e.g. a second Mac Mini at a different building):

1. Install Docker on the new host.
2. Clone the repo: `git clone ...`
3. Copy `config.example.txt` to `config.txt` and edit — typically only
   `LOCATION_NAME` changes if both instances post to the same Telegram chat.
4. `docker compose up -d --build`

Both instances can safely upload to the same chat. The `LOCATION_NAME` tag in
filenames and captions distinguishes them.

## Troubleshooting

**Files aren't being uploaded.**
Check `docker compose logs -f`. The container scans every
`POLL_INTERVAL_SECONDS` (default 30). New files won't upload until they have
been size-stable for `FILE_STABLE_SECONDS` AND `UPLOAD_DELAY_MINUTES` has
elapsed past the stability point.

**The container can't see the recordings folder.**
Verify the host path in `docker-compose.yml` matches your actual recording
folder. On Docker Desktop for Mac, the path must be inside the directories
Docker has permission to share (Docker Desktop → Settings → Resources →
File Sharing).

**Messages aren't being deleted.**
The bot must be a group administrator with "Delete messages" permission, AND
the group must be a supergroup. If you set `MESSAGE_RETENTION_DAYS=7` but the
bot isn't admin, delete calls older than 48h fail silently. Check logs for
`Could not delete message_id=...` warnings.

**"Bad Request: chat not found" on first upload.**
Make sure you added the bot to the group and that `TELEGRAM_CHAT_ID` is
correct (groups are negative numbers).

## Project layout

```
.
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── config.example.txt    ← template, committed
├── config.txt            ← your real config, gitignored
├── .gitignore
├── .dockerignore
├── state/                ← SQLite state, gitignored, persists across rebuilds
└── app/
    ├── main.py           ← entry point, main loop
    ├── config.py         ← config.txt parser
    ├── watcher.py        ← folder monitoring + write-completion detection
    ├── uploader.py       ← Telegram API client
    └── state.py          ← SQLite-backed upload/deletion tracking
```

## License

MIT.
