"""Build the submission video: male voiceover + a real recording of the live site.

    python3 submission/demo/video/make_video.py voice      # 1. narration.json -> out/audio/*.wav
    node apps/dashboard/scripts/record-demo-video.mjs      # 2. drive the live site -> out/screen.webm
    python3 submission/demo/video/make_video.py mix        # 3. -> out/ghostreplay-demo.mp4 + .srt

Each voice segment is placed at the moment its screen segment really started (out/marks.json),
so picture and voice stay in sync even when a live request is slower than planned.
Needs macOS `say` and ffmpeg.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"


def run(*cmd: str) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def duration(path: Path) -> float:
    return float(
        run(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        )
    )


def voice() -> None:
    d = json.loads((HERE / "narration.json").read_text())
    (OUT / "audio").mkdir(parents=True, exist_ok=True)
    durs = {}
    for s in d["segments"]:
        aiff, wav = OUT / "audio" / f"{s['id']}.aiff", OUT / "audio" / f"{s['id']}.wav"
        run("say", "-v", d["voice"], "-r", str(d["rate"]), "-o", str(aiff), s["say"])
        run(
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(aiff),
            "-ar",
            "48000",
            "-ac",
            "2",
            str(wav),
        )
        durs[s["id"]] = round(duration(wav), 3)
    (OUT / "durations.json").write_text(json.dumps(durs, indent=1))
    print(durs, "total", round(sum(durs.values()), 1), "s")


def srt_time(t: float) -> str:
    ms = round(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def captions(segments: list[dict], marks: dict, durs: dict) -> str:
    """One caption per sentence, timed proportionally to its word count within the segment."""
    cues, n = [], 1
    for s in segments:
        sentences = [x.strip() for x in re.split(r"(?<=[.!?:])\s+", s["caption"]) if x.strip()]
        words = [len(x.split()) for x in sentences]
        total, t = sum(words), marks[s["id"]]
        for text, w in zip(sentences, words, strict=True):
            span = durs[s["id"]] * w / total
            cues.append(f"{n}\n{srt_time(t)} --> {srt_time(t + span)}\n{text}\n")
            t += span
            n += 1
    return "\n".join(cues)


def mix() -> None:
    d = json.loads((HERE / "narration.json").read_text())
    marks = json.loads((OUT / "marks.json").read_text())
    durs = json.loads((OUT / "durations.json").read_text())
    screen = OUT / "screen.webm"
    length = duration(screen)
    inputs: list[str] = ["-i", str(screen)]
    parts = []
    for i, s in enumerate(d["segments"], start=1):
        inputs += ["-i", str(OUT / "audio" / f"{s['id']}.wav")]
        delay = int(marks[s["id"]] * 1000)
        parts.append(f"[{i}:a]adelay={delay}|{delay}[a{i}]")
    n = len(d["segments"])
    graph = ";".join(parts) + ";" + "".join(f"[a{i}]" for i in range(1, n + 1))
    graph += (
        f"amix=inputs={n}:normalize=0,apad,atrim=0:{length:.3f},loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
    )
    mp4 = OUT / "ghostreplay-demo.mp4"
    run(
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        *inputs,
        "-filter_complex",
        graph,
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(mp4),
    )
    (OUT / "ghostreplay-demo.srt").write_text(
        captions(d["segments"], marks, durs), encoding="utf-8"
    )
    print(f"{mp4}  {duration(mp4):.1f}s  {mp4.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    {"voice": voice, "mix": mix}[sys.argv[1] if len(sys.argv) > 1 else "mix"]()
