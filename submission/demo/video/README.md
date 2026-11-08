# Submission video

`out/ghostreplay-demo.mp4`: 2:44, 1920×1080, H.264 + AAC, about 17 MB. Captions are in
`out/ghostreplay-demo.srt`. The `out/` folder is git-ignored; regenerate it with the commands
below.

- **Picture.** A real browser session on https://ghostreplay.hayaix.tech, driven by
  Playwright. Every click triggers real requests: re-executions against the live server's
  SQLite database, HTTP services and instance lab, strict offline replays and regression runs.
  Nothing on screen is staged or edited. The numbers are whatever that run produced.
- **Voice.** A synthetic male voice (macOS `say`, voice "Daniel", 148 words per minute),
  generated from `narration.json`.
- **Sync.** Each voice segment is placed at the moment its screen segment actually started
  (`out/marks.json`).

## Regenerate

```bash
python3 submission/demo/video/make_video.py voice      # narration.json -> out/audio/*.wav
node apps/dashboard/scripts/record-demo-video.mjs      # live site -> out/screen.webm (~2:45)
python3 submission/demo/video/make_video.py mix        # -> out/ghostreplay-demo.mp4 + .srt
```

Needs macOS (`say`), ffmpeg, and the dashboard's Playwright install. To record against a
local server, add its URL to the `node` command (for example `http://127.0.0.1:8100`).

## Upload

Upload the MP4 to YouTube (unlisted or public) and add `out/ghostreplay-demo.srt` as English
subtitles. Then paste the link into the Devpost form and replace `<VIDEO_URL>` in
`submission/devpost/description.md`. Use `upload-description.md` as the video description.
