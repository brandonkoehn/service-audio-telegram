# Service Audio → Telegram — Project Reference

Personal reference for the Service Audio → Telegram deployment. Captures
architecture decisions, operational notes, and the school Mac Mini deployment
plan so future-you (or someone else) can pick this up cleanly.

**Repo:** <https://github.com/brandonkoehn/service-audio-telegram>

> **Retention note (updated May 2026):** Message expiry is **no longer handled
> by the bot**. It is now handled by Telegram's built-in chat-level auto-delete
> timer, set to **2 weeks**. See "How retention actually works" below for the
> full story on why the bot can't do it and why 2 weeks (not 10 days) is the
> setting. The bot's old per-message deletion logic still runs but its delete
> attempts fail harmlessly — that's expected now, not a bug.

-----

> **Live stream problems?** See `STREAM_TROUBLESHOOTING.md` (IceCast host,
> test commands, incident log — 2026-10-11 flapping traced to the church
> internet uplink).

-----

## What this does

Captures live audio from a church sound system via butt → IceCast for live
streaming, and saves a local MP3 copy on a Mac Mini. A Docker container
watches that local folder, waits for each recording to finish writing, then
uploads the MP3 to a Telegram supergroup. Old messages are removed
automatically by **Telegram's native auto-delete timer** on the chat (set to
2 weeks), not by the bot.

Built for two locations sharing the same Telegram chat:

- **SHMC (Church)** — runs every Sunday morning + Sunday evening
- **School** — runs ~4-5 times per year

Both locations post to the same Telegram chat, distinguished by a
`LOCATION_NAME` config value that tags filenames and captions.

-----

## How retention actually works (READ THIS)

This is the part the original design got wrong, discovered May 2026.

### The original (broken) assumption

The bot was built to upload each MP3, record a deletion time in `state.db`,
and later call Telegram's `deleteMessage` to remove it after
`MESSAGE_RETENTION_DAYS`. This **never actually worked past ~48 hours**, and
the symptom was MP3s piling up in the chat that never disappeared. The logs
showed:

```
[WARNING] uploader: Could not delete message_id=N: {'ok': False, 'error_code': 400,
'description': "Bad Request: message can't be deleted"}
```

### Why the bot can't do it

A Telegram **bot can only delete its own messages within 48 hours** of
sending them. The `can_delete_messages` admin right *does* extend a bot's
delete power — but in a **supergroup** that extension applies to **other
users'** messages of any age, **not to the bot's own old messages**. Our
audio files are the bot's own messages, so once they pass 48 hours the bot
gets "message can't be deleted" no matter what admin rights it holds.

The cruel irony: promoting the bot to admin (to try to get long retention) is
exactly what converted the group into a supergroup — and in a supergroup the
"delete any message" power narrows away from the bot's own messages. So the
step taken to enable long retention is what blocked it.

There is **no Bot API method to set the chat's auto-delete timer** either.
(`setChatMessageAutoDeleteTime` does not exist as a callable endpoint — calling
it returns `404 Not Found`. The timer shows up only as a *readable* property,
`message_auto_delete_time`, in `getChat`.) A user-account script (Telethon /
Pyrogram with an API ID/hash and a logged-in user session) could delete its
own old messages and hit an exact day count, but that's a full re-architecture
and a session credential to babysit — not worth it here.

### The fix: Telegram's native chat-level auto-delete timer

Telegram has a built-in per-chat auto-delete timer, enforced server-side,
completely independent of the bot's 48-hour `deleteMessage` limit. Since this
chat contains nothing but the bot's audio uploads, a chat-wide timer does
exactly what the bot's logic was trying to do — and it works on old messages.

**How to set it (must be done from the MOBILE app — desktop can't):**

1. Open the SHMC Service Audio group in the Telegram iOS/Android app.
2. Tap the group name at the top to open group info.
3. Tap **Auto-Delete Messages**.
4. Pick the duration.

It's a property of the **chat**, so setting it once (from a phone, or from any
admin) applies group-wide and shows on the Mac desktop too. The desktop client
can *display and honor* the timer but can only *set* the three fixed presets
(1 day / 1 week / 1 month), which is why this must be done from a phone.

### Why 2 weeks, not 10 days

10 days would have been ideal, but the native timer only accepts quantized
steps: 1–6 days, then 1/2/3 weeks, then 1–6 months, then 1 year. **There is no
10-day option.** The realistic choices around 10 are **1 week (7 days)** or
**2 weeks (14 days)**.

We chose **2 weeks** because:

- Services post twice every Sunday (morning ~11 AM, evening ~7 PM).
- At 7 days, a file expires right as the next Sunday arrives — tight, and it
  can vanish *during* the following service. Miss two Sundays and it's gone.
- At 14 days there are always ~two Sundays' worth available, with comfortable
  overlap and no countdown race.
- The extra 4 days beyond the ideal 10 cost nothing in a private group.

To change it later, it's a two-tap edit in the mobile app. Drop to 1 week if
chat clutter ever becomes a concern.

### Important caveats of the native timer

- **Not retroactive.** It only governs messages sent *after* it's enabled.
  Files already in the chat when you set it are NOT swept up — clear those
  once, manually, in the app (select & delete, or Clear History).
- The countdown starts when each file is sent (so 14 days from upload).
- Pinned messages ignore the timer (not relevant here — we don't pin).

-----

## Architecture decisions and why

### Why Telegram instead of WhatsApp

WhatsApp Business API is heavyweight and not really designed for media
distribution. Telegram's Bot API is dead simple — POST a file to a chat
endpoint and it handles everything. The user base trade-off (more people
use WhatsApp) was accepted in exchange for a fully automated, no-human-in-
the-loop pipeline.

### Why Docker instead of a native script

- Self-contained, portable, reproducible
- Identical deployment between church and school Macs
- Auto-restart on crash via `restart: unless-stopped`
- Easy to move to a new Mac Mini if hardware is swapped — clone the repo,
  edit config, `docker compose up`
- Keeps the host OS clean (no Python venv, no homebrew weirdness)

### Why two independent containers instead of file sync

- No sync layer = no failure points around file syncing
- No Dropbox spinner-during-write issues
- Each location is fully self-contained — if one Mac is offline, the other
  still works
- Trade-off: maintain two Docker setups instead of one (acceptable)

### Bot admin status — no longer needed for retention

The bot was made admin with **Delete Messages** permission to try to enable
long retention. As explained above, that approach doesn't work for the bot's
own messages, so **admin status is no longer required** for retention now that
the native timer handles deletion.

You can leave the bot as admin (harmless) or demote it. Note that demoting it
will **not** convert the supergroup back to a regular group — the supergroup
state is permanent, which is why the chat ID stays in `-100…` format.

### Why we transcode large files

Telegram Bot API caps `sendAudio` at 50 MB. Long sermons at typical bitrates
exceed that. `ffmpeg` re-encodes any oversize file to 64 kbps mono before
upload (gives ~28 MB per hour, transparent fidelity for speech). The
**original file on disk is never modified** — only a temporary copy in /tmp
inside the container gets transcoded and uploaded, then deleted.

### Why we track state in SQLite

`state.db` remembers which files have already been uploaded, so they don't get
re-uploaded. (It also still records intended deletion times, but that half is
now vestigial — see "How retention actually works." The bot's delete attempts
fail harmlessly; Telegram's native timer does the real removal.)

A SQLite file mounted as a volume gives us this with no extra services.

### Why files are processed N minutes after the last write

butt writes the MP3 continuously while broadcasting. We can't upload mid-
write. The detection logic:

1. File size stable for `FILE_STABLE_SECONDS` (default 60s) = writing is done
1. Wait additional `UPLOAD_DELAY_MINUTES` (default 10) before uploading
1. Then transcode (if needed) and upload

This gives plenty of buffer for OS flushing, slow disks, anything weird.

### Why we use a tombstone for permanent failures

If an upload fails for a reason that won't fix itself (file too large after
transcode, malformed file, etc.), we record it in state.db with a
`message_id=0` sentinel meaning "tried and failed permanently." Without
this, the script would loop forever retrying every poll cycle. To force a
retry, either rename the file or delete its row from state.db.

-----

## Bot, group, and credentials

|Item            |Value                                    |
|----------------|-----------------------------------------|
|Bot handle      |`@shmc_audio_bot`                        |
|Bot display name|SHMC Service Audio                       |
|Group name      |SHMC Service Audio (supergroup)          |
|Chat ID         |`-1003838820206`                         |
|Bot permissions |Delete Messages (no longer needed; safe to leave)|
|Group type      |Private supergroup (invite-link only)    |
|Retention       |Native chat auto-delete timer = **2 weeks**|
|Bot token       |In `config.txt` on each Mac, never in git|

The bot token lives only in `config.txt` on each Mac Mini and never gets
committed to git (gitignored). If a token ever leaks:

1. Chat with `@BotFather` on Telegram
1. Send `/revoke`
1. Select the bot
1. Update `config.txt` with the new token
1. `docker compose restart`

-----

## Currently deployed instances

### SHMC (Church) Mac Mini — DEPLOYED ✅

- Docker Desktop installed, autostart enabled
- Recordings folder: `/Users/Shared/ServiceAudio/recordings/`
- butt configured to save there
- Repo cloned at `~/service-audio-telegram`
- Container `service-audio-telegram` running with `restart: unless-stopped`
- `LOCATION_NAME=Church`

### School Mac Mini — PENDING

See "School deployment steps" below.

-----

## Config reference

`config.txt` lives in the repo root on each Mac (gitignored). All current
production settings:

```
TELEGRAM_BOT_TOKEN=<from BotFather>
TELEGRAM_CHAT_ID=-1003838820206
WATCH_FOLDER=/recordings
LOCATION_NAME=Church          # or School on the school Mac

UPLOAD_DELAY_MINUTES=10
FILE_STABLE_SECONDS=60
POLL_INTERVAL_SECONDS=30
MESSAGE_RETENTION_DAYS=7       # INERT — see note below

TRANSCODE_BITRATE_KBPS=64
TRANSCODE_MONO=true
```

> **`MESSAGE_RETENTION_DAYS` is effectively inert.** Retention is now handled
> by Telegram's native timer, not the bot. This value still makes the bot
> *attempt* deletions (which fail with "message can't be deleted" and log a
> harmless WARNING). To quiet the log noise you can set it to something large
> like `3650` so deletions are scheduled far in the future and effectively
> never fire. Already-stranded rows whose delete time is in the past will keep
> logging until cleared — clear them from state.db if the noise bothers you, or
> just ignore it.

### How config changes propagate

- **`MESSAGE_RETENTION_DAYS`** — no longer drives real retention (the chat
  timer does). Only affects when the bot's harmless delete attempts get
  scheduled.
- **`UPLOAD_DELAY_MINUTES`, `FILE_STABLE_SECONDS`, `POLL_INTERVAL_SECONDS`**
  affect everything immediately after restart.
- **`TRANSCODE_BITRATE_KBPS`, `TRANSCODE_MONO`** affect only future uploads.
- **`LOCATION_NAME`** affects only future filenames/captions.
- **`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`** affect future uploads.

To apply any config change: `nano config.txt` then `docker compose restart`.
No rebuild needed — the config file is mounted into the container.

-----

## Day-to-day operations

### Watch the live log

```bash
cd ~/service-audio-telegram
docker compose logs -f
```

Ctrl+C to stop watching (container keeps running).

### See last 50 log lines without tailing

```bash
docker compose logs --tail=50
```

### Confirm the container is running

```bash
docker compose ps
```

### Restart after editing config

```bash
docker compose restart
```

### Stop everything

```bash
docker compose down
```

### Start everything

```bash
docker compose up -d
```

### Rebuild after pulling code changes

```bash
git pull
docker compose up -d --build
```

### Change the retention period

This is now a Telegram setting, not a config/code change. On a phone:
group info → **Auto-Delete Messages** → pick a preset (1–6 days, 1/2/3 weeks,
1–6 months, 1 year). Currently set to 2 weeks. Applies group-wide; not
retroactive.

### Force re-upload of a specific file

Either:

- Rename the source file (new path = treated as new file), OR
- Delete its row from state.db:

  ```bash
  docker compose exec service-audio-telegram sqlite3 /state/state.db \
    "DELETE FROM uploaded_files WHERE source_path='/recordings/FILENAME.mp3';"
  ```

### Wipe ALL state (re-upload everything in folder)

```bash
docker compose down
rm -rf state
docker compose up -d --build
```

⚠️ This causes EVERY MP3 still in the folder to be uploaded again.

-----

## Filesystem layout on each Mac Mini

```
/Users/Shared/ServiceAudio/recordings/    ← butt saves MP3s here (permanent archive)
~/service-audio-telegram/                 ← cloned git repo
├── config.txt                            ← gitignored, contains secrets
├── state/                                ← gitignored, SQLite state
│   └── state.db
├── docker-compose.yml
├── Dockerfile
└── app/...
```

The recordings folder is mounted **read-only** into the container, so the
script can never modify or delete originals. Recordings accumulate forever
unless manually pruned — natural local archive.

-----

## Filename and caption conventions

The script renames files at upload time based on the file's modification
time (mtime), not its original name from butt:

- **Uploaded filename:** `2026-05-17_0930_Church.mp3` (`YYYY-MM-DD_HHMM_Location.mp3`)
- **Caption text:** `Church — Sunday, May 17 2026 at 09:30 AM`

The original file on disk keeps butt's naming scheme
(`rec_20260517-095030.mp3` etc.) untouched.

Timezone is set via `TZ=America/Chicago` in `docker-compose.yml` so timestamps
match local time.

-----

## Telegram group settings

### Invite link (Option 2 — private)

Generated under group → Edit → Invite Links. Looks like `https://t.me/+...`
Can be revoked/regenerated anytime. Optional: set expiration, member cap,
require admin approval for joins.

### Content protection

Currently OFF. If enabled (group → Edit → Restrict Saving Content), it
disables forwarding, downloading, AND screenshots — all-or-nothing, no way
to allow share-to-one-friend but block share-to-large-group. Leaving off
because the content is meant to be shared with the community.

### Auto-delete (retention)

Handled by Telegram's **native chat auto-delete timer**, set to 2 weeks from
the mobile app (group info → Auto-Delete Messages). This replaced the bot's
old deletion logic, which could not delete the bot's own messages past 48
hours. Not retroactive; set once, applies group-wide.

-----

## School Mac Mini deployment steps (PENDING)

When ready to deploy, on the school Mac Mini:

### 1. Install Docker Desktop

- Download from <https://www.docker.com/products/docker-desktop>
- Pick Apple Silicon or Intel installer based on the Mac
- Settings → General → enable "Start Docker Desktop when you sign in"
- Settings → Resources → File Sharing → confirm `/Users` is in the list
- Verify with `docker run hello-world`

### 2. Create recordings folder

```bash
sudo mkdir -p /Users/Shared/ServiceAudio/recordings
sudo chmod 775 /Users/Shared/ServiceAudio/recordings
sudo chown -R $(whoami):staff /Users/Shared/ServiceAudio
```

The chown is the important one — without it butt can't write without a
password prompt.

### 3. Point butt at the new folder

Open butt → Preferences → Record → set save path to
`/Users/Shared/ServiceAudio/recordings/`

### 4. Clone the repo and configure

```bash
cd ~
git clone https://github.com/brandonkoehn/service-audio-telegram.git
cd service-audio-telegram
cp config.example.txt config.txt
nano config.txt
```

Fill in `config.txt` (use the SAME values as church, except LOCATION_NAME):

```
TELEGRAM_BOT_TOKEN=<same token as church Mac Mini>
TELEGRAM_CHAT_ID=-1003838820206
LOCATION_NAME=School
UPLOAD_DELAY_MINUTES=10
FILE_STABLE_SECONDS=60
POLL_INTERVAL_SECONDS=30
MESSAGE_RETENTION_DAYS=7
TRANSCODE_BITRATE_KBPS=64
TRANSCODE_MONO=true
```

> Retention does NOT need to be configured per machine. The chat's native
> auto-delete timer is already set (2 weeks) and applies group-wide, including
> to uploads from the school Mac. Nothing to do on this side for retention.

### 5. Build and start

```bash
docker compose up -d --build
docker compose logs -f
```

### 6. Test

Drop a test MP3 into `/Users/Shared/ServiceAudio/recordings/`. Within 2-3
minutes you should see it transcode (if over 50 MB) and upload. Verify the
message appears in the SHMC Service Audio Telegram chat with caption
starting "School — ".

-----

## Troubleshooting recipes

### "413 Request Entity Too Large"

File is over 50 MB and transcoding didn't fix it (very unusual). Lower
`TRANSCODE_BITRATE_KBPS` to 48 or 32 in config.txt and restart.

### "Bad Request: group chat was upgraded to a supergroup chat"

The chat ID in config is stale — you used the pre-admin-promotion ID. The
error message includes the new ID (look for `migrate_to_chat_id`). Update
`TELEGRAM_CHAT_ID` in config.txt and restart.

### "Bad Request: chat not found"

Bot was removed from the group, or chat ID is wrong. Verify bot is still a
member, re-check chat ID with `@getidsbot`.

### Logs show "Could not delete message_id=…" / "message can't be deleted"

**This is now EXPECTED and harmless.** The bot cannot delete its own messages
older than 48 hours, and retention is handled by Telegram's native timer
instead. These warnings are not a failure of retention. (Do NOT re-promote the
bot or change admin rights chasing this — it won't help; the limitation is on
the bot deleting its *own* old messages, not on permissions.) To silence the
noise, set `MESSAGE_RETENTION_DAYS` very high and/or clear the old pending rows
from state.db.

### Old MP3s aren't disappearing from the chat

Check that the **native auto-delete timer** is set: phone → group info →
Auto-Delete Messages → should read 2 weeks. Remember it's **not retroactive**
— files posted before the timer was enabled must be cleared manually once.

### Container won't start, "Configuration error: Missing required config keys"

You haven't created `config.txt` yet. `cp config.example.txt config.txt` and
fill in the required values.

### File sits in folder forever, never uploads

- Check `docker compose ps` — is the container actually running?
- Check `docker compose logs --tail=100` for errors
- Verify the folder is mounted: `docker compose exec service-audio-telegram ls /recordings/`
- If the file shows up in container but doesn't process, check that
  `FILE_STABLE_SECONDS` and `UPLOAD_DELAY_MINUTES` have actually elapsed
  since the file became size-stable

### Wrong timezone in filenames/captions

Verify `TZ=America/Chicago` is in `docker-compose.yml` under `environment:`.
After changing, `docker compose up -d --build` (not just restart — needs
rebuild since it's a compose-level setting).

### Bot token accidentally exposed in logs

Logs now scrub the token automatically, but if it ever does leak:

1. `@BotFather` → `/revoke` → select bot
1. Update `config.txt` with new token
1. `docker compose restart`

-----

## Future improvements / ideas

- **Retire the bot's dead deletion code.** Now that the native timer handles
  retention, the state.db deletion-scheduling and `deleteMessage` calls are
  dead weight that only generate harmless warnings. A code cleanup could drop
  that path entirely and stop tracking `delete_after`.
- **Exact-day retention via a userbot.** If an exact day count (e.g. 10 days)
  ever truly matters, a user-account script (Telethon/Pyrogram) can delete its
  own messages at any age. This is a bigger lift (API ID/hash + session
  credential) and probably not worth it versus the native 1/2-week presets.
- **Sync recordings to Nextcloud (VM 100)** for off-site backup. Would
  inherit the existing Proxmox backup story. Easiest via the Nextcloud
  desktop client on each Mac syncing `/Users/Shared/ServiceAudio/recordings`
  to a Nextcloud folder.
- **Webhook notifications** when an upload fails. Could ping a separate
  Telegram admin chat, or send to Gotify, etc.
- **Multiple chat destinations.** Currently one chat for everything. Could
  add per-location target chats if church/school audiences ever diverge.

-----

## Quick command cheat sheet

```bash
# Watch live
docker compose logs -f

# Recent logs only
docker compose logs --tail=50

# Status
docker compose ps

# Restart after config change
docker compose restart

# Stop / start
docker compose down
docker compose up -d

# Update from git
git pull && docker compose up -d --build

# Check inside container
docker compose exec service-audio-telegram bash
docker compose exec service-audio-telegram ls /recordings/

# Query state.db
docker compose exec service-audio-telegram sqlite3 /state/state.db \
  "SELECT source_path, uploaded_at, delete_after, deleted FROM uploaded_files;"
```

> **Retention is NOT in this cheat sheet** because it's no longer a
> command-line thing — it's the chat's native auto-delete timer (2 weeks),
> changed from the Telegram mobile app.
