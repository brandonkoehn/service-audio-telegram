# Live Stream (butt → IceCast) — Troubleshooting Reference

Companion to `Telegram_PROJECT_REFERENCE.md`, which covers the MP3 → Telegram
side. This file covers the **live stream** side and logs incidents.

Last updated: 2026-10-11

---

## Stream setup

| Item | Value |
|---|---|
| Source app | butt on the SHMC church Mac mini (user `shmc`) |
| Server | `icecast.aleph-com.net:8000` (hosted; resolves to `us-az-phoenix-17.listentochurch.com`, 172.83.127.56) |
| Mount | `/8131738` |
| Login | user `source`, password in butt (also in Brandon's `~/.buttrc` and Dropbox/butt settings backups) |
| Codec | MP3, 128 kbps, mono, 44.1 kHz (consider 64 kbps — see below) |
| Audio in | USB Audio Device (Core Audio) |
| Recording | separate, 192 kbps MP3 to `/Users/Shared/ServiceAudio/recordings`, independent of the stream |
| Mac network | Wi-Fi (`en1`), 192.168.103.107, router 192.168.103.1 |
| Remote access | Jump Desktop only (no Tailscale, no SSH) |
| Status page | `http://icecast.aleph-com.net:8000/status-json.xsl` — hides sources (private), so test the mount directly |

The stream and the recording are independent. If the stream flaps, the
recording keeps going and the Telegram upload is unaffected. butt's config
has "stop recording when disconnected" OFF.

---

## Tests

### From anywhere (Brandon's Mac) — is the server OK and is the mount live?

```bash
H=icecast.aleph-com.net
ping -c 5 $H | tail -2
nc -vz -w 5 $H 8000
# Live mount returns 200 + audio/mpeg + icy-br header; ~64 KB per 4 s at 128 kbps
curl -s -m 8 -v -o /dev/null http://$H:8000/8131738 2>&1 | grep -E "^< (HTTP|icy|ice)"
# Watch for flapping: should print 200 and ~64000 bytes every line
for i in $(seq 1 9); do echo "$(date +%T) $(curl -s -m 4 -o /dev/null -w '%{http_code} %{size_download}' http://$H:8000/8131738)"; sleep 6; done
```

### On the Mac mini (via Jump Desktop → Terminal) — where is the loss?

```bash
GW=$(route -n get default | awk '/gateway/{print $2}'); IF=$(route -n get default | awk '/interface/{print $2}')
echo "== link: $IF via $GW"; ifconfig $IF | grep -E "status|media|inet "
networksetup -listallhardwareports | grep -B1 "$IF"
echo "== ping router"; ping -c 20 -i 0.5 $GW | tail -2
echo "== ping internet"; ping -c 20 -i 0.5 8.8.8.8 | tail -2
echo "== ping icecast"; ping -c 20 -i 0.5 icecast.aleph-com.net | tail -2
echo "== tcp 8000"; nc -vz -w 5 icecast.aleph-com.net 8000
echo "== mtu / drops"; netstat -i | grep -E "Name|$IF"
```

Reading it:
- Router lossy → Wi-Fi problem (move to Ethernet).
- Router clean, internet lossy → church uplink/modem/ISP.
- Both clean, IceCast lossy → routing between ISP and host.

### On the Mac mini — what is using the upload?

```bash
nettop -P -J bytes_out -d -x -l 2 -s 10 2>/dev/null | awk '/^time/{n++; next} n==2 && $NF>50000 {printf "%8.1f KB/s  %s\n", $NF/10240, $2}' | sort -rn | head
```

butt at 128 kbps should show ~16 KB/s. Jump Desktop shows up whenever
you're connected (~10 KB/s). Anything else large is competing for the uplink.

### On the Mac mini — modem vs ISP, and real upload speed (run when no service is on; saturates the line ~15 s)

```bash
H2=$(traceroute -n -m 3 -q 1 -w 2 8.8.8.8 2>/dev/null | awk 'NR==3{print $2}'); echo "== first ISP hop: $H2"
ping -c 20 -i 0.5 $H2 | tail -2
echo "== networkQuality"; networkQuality -v 2>&1 | grep -E "Upload|Download|Responsiveness|Idle"
```

### butt log

Main window → the log pane under the meters. `ERROR: Connection lost` +
`reconnecting...` = TCP session died mid-stream (packet loss). `refused` /
`401` = server/credential problem.

---

## Changing the stream bitrate

butt → Settings → **Audio** tab → streaming Bitrate → 64 (speech, mono, is
fine at 64; 48 as a last resort). Leave the recording bitrate alone. Then
stop (square) and start (play) the stream — takes effect on the next connect.
Recording keeps running.

---

## Incident log

### 2026-10-11 (Sunday AM service) — stream flapping, unresolved

**Symptom:** butt log showed `ERROR: Connection lost / reconnecting...` about
once a minute (11:10, 11:11 …), reconnecting successfully each time. Stream
time kept resetting. Recording kept going.

**Findings:**

| Test | Result |
|---|---|
| Server from Brandon's Mac | 0% loss, 86 ms, port 8000 open, mount live at 128 kbps, test listener fed steadily for 90 s |
| Mini → router (Wi-Fi) | 0% loss, avg 11 ms, max 71 ms |
| Mini → 8.8.8.8 | **55% loss** |
| Mini → icecast.aleph-com.net | **65% loss** |
| Interface errors | 0 Ierrs / 0 Oerrs |
| Upload users on the mini | JumpConnect 9.7 KB/s, butt 5.1 KB/s (butt should be ~16 → it was stalled most of the time), nothing else |
| Dropbox on the mini | idle |
| On-site modem/router power-cycle | **did not help** |

**Conclusion:** Mac mini, Wi-Fi hop, and IceCast server all clean. Loss is
between the church router and the internet: the ISP line itself, or another
device on the church LAN saturating the uplink. Could not change butt's
bitrate because Jump Desktop was too laggy on the same line. Left as-is;
recording/Telegram unaffected.

**Follow-ups (not done yet):**
1. Run the ISP-hop + `networkQuality` test on a quiet day; quote the numbers to the ISP.
2. Check what else is on the church network during services (phones backing up, cloud cameras, etc.). Router admin page per-client traffic if available.
3. Put the mini on Ethernet if a cable can reach.
4. Set butt stream bitrate to 64 kbps during a stable session.
5. Consider installing Tailscale on the mini so this can be checked without Jump Desktop (which itself eats upload).
