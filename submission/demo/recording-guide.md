# Recording guide

How to record the demo video described in `video-script.md` and `storyboard.md`.

## 1. Prepare a clean environment

Pick **one** way to run the app. Use the same one for every take.

### Option A: development servers

```bash
./scripts/dev.sh
```

Open http://127.0.0.1:5173. The lab APIs run on :8101 and :8102 and store data in
`./.ghostreplay/`.

For a completely clean store, stop the servers, then move the old store aside (do not delete
it if you may need it):

```bash
mv .ghostreplay ".ghostreplay.bak-$(date +%Y%m%d%H%M)"
```

Alternatively, in the dashboard open **Executions** in each lab and click **Clear**
(available outside the public profile).

### Option B: one container (what a hosted demo looks like)

```bash
docker compose up --build
```

Open http://127.0.0.1:8100. For a clean store:

```bash
docker compose down -v && docker compose up --build
```

(`-v` removes the `ghostreplay-data` volume, which holds only demo executions.)

### Warm-up run

Click both demo buttons once before recording ("Try the Duplicate Refund Demo" and
"Try the Unsafe AWS Operation Demo") so you know both stories finish with
"✓ bug reproduced" and "✓ fix proven". Then reload the page: the guided demo re-runs when it
is opened in a fresh page, so the recording shows real preparation.

The guided demo creates the recordings the later shots need (the healthy baseline for the
Failure Lab and the counterfactuals for Regression Results). Record the takes in script order.

### Terminal cut (optional)

Prepare a terminal with a large font (18 pt or more), a plain prompt and this command ready:

```bash
uv run pytest tests/regression -q
```

## 2. Browser and screen

- Use a fresh browser profile: no extensions, bookmarks bar hidden, no other tabs, no
  personal accounts visible.
- Window content size **1440 × 900** (or 1920 × 1080 on a large display). The header badges
  "offline · simulated backends" and "scripted models" only appear at 1280 px wide or more.
- Browser zoom 110 to 125 % if text looks small in a 1080p export.
- Turn on Do Not Disturb; hide the dock or taskbar; close chat apps.
- Do not show `.env`, terminal history with keys, or the Anthropic console. The default demo
  needs no API key; keep live AI mode off unless you deliberately show it, and then say so.

## 3. Tools

Any of these work; use what you know:

- Screen capture: OBS Studio (free), macOS Screenshot toolbar (`Shift`+`Cmd`+`5`), or
  ScreenFlow / Camtasia.
- Cursor highlight and click rings: built into ScreenFlow and Camtasia; in OBS use a cursor
  highlighter app.
- Editing: DaVinci Resolve (free), iMovie, ScreenFlow, Camtasia or Shotcut.
- Kiro segment: record the Kiro window the same way, only from real sessions.

## 4. Audio

- Use a USB or headset microphone, not the laptop microphone, in a quiet, soft-furnished room.
- Record narration separately from the screen capture, one section at a time, following the
  timestamps in `video-script.md`. Re-record a section rather than splicing words.
- Target loudness about -16 LUFS (common for web video); peaks below -1 dBFS.
- Apply light noise reduction and a high-pass filter around 80 Hz; avoid heavy compression.
- Optional background music very low (around -30 dB under the voice), licensed for public use.

## 5. Capture settings

| Setting | Value |
|---|---|
| Resolution | 1920 × 1080 (or 2560 × 1440 downscaled to 1080p) |
| Frame rate | 30 fps (60 fps if you show fast scrolling) |
| Capture format | the recorder's lossless or high-bitrate setting |

## 6. Edit

- Keep the total under **3:00** (aim for 2:50 to 2:57).
- Cut waiting time (the demo preparation takes a moment), but never cut in a way that changes
  what a result says. Do not edit numbers, verdicts or labels.
- Add zoom-ins on small text (invariants, metrics, badges).
- Add captions or subtitles; export an `.srt` from the editor or from the script.
- End card: project name, tagline, repository URL, `<DEPLOYED_URL>`.

## 7. Export

| Setting | Value |
|---|---|
| Container / codec | MP4, H.264 (High profile), AAC audio |
| Resolution | 1920 × 1080 |
| Frame rate | same as capture |
| Video bitrate | 10 to 16 Mbps (VBR) |
| Audio | AAC 48 kHz, 192 kbps or higher, stereo |

## 8. Upload

1. Upload to YouTube (or Vimeo) with a title such as
   "GhostReplay Lab: break AI agents safely, replay failures, prove the fix".
2. Visibility: public (or unlisted if the official rules allow it). Check the hackathon's
   rules for allowed platforms and visibility.
3. Description: tagline, repository URL, `<DEPLOYED_URL>`, and a note that the demo agents
   use scripted models and simulated tools.
4. Upload the `.srt` captions.
5. Open the video in a private browser window to confirm it plays without signing in.
6. Replace `<VIDEO_URL>` in `submission/devpost/description.md` and the README.
