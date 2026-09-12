#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Hermes 语音口述转成文字，并收成专项出题参数。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scheduler_common import DB, local_today
from spoken_quiz_intent import parse_spoken_intent


MODEL = os.environ.get("VOICE_TRANSCRIBE_MODEL", os.environ.get("DAILY_GEMINI_MODEL", "gemini-3.8-flash-high"))
BASE_URL = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I | re.M)


def api_key() -> str:
    if key := os.environ.get("CLIPROXY_API_KEY", "").strip():
        return key
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("CLIPROXY_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    raise RuntimeError("CLIPROXY_API_KEY not found")


def taken_batch_ids(db_path: Path) -> set[str]:
    if not db_path.is_file():
        return set()
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        rows = conn.execute(
            "SELECT DISTINCT batch_id FROM questions WHERE batch_id LIKE ?",
            (f"{local_today():%Y%m%d}_hermes_%",),
        ).fetchall()
    finally:
        conn.close()
    return {str(row[0]) for row in rows if row and row[0]}


def decode_data_url(raw: str) -> tuple[bytes, str]:
    text = (raw or "").strip()
    if text.startswith("data:") and "," in text:
        header, payload = text.split(",", 1)
        mime = "audio/webm"
        if ":" in header:
            mime = header.split(":", 1)[1].split(";", 1)[0] or mime
        return __import__("base64").b64decode(payload), mime
    return __import__("base64").b64decode(text), "audio/webm"


def write_source(path: Path, data: bytes, mime: str) -> Path:
    ext = {
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/aac": ".aac",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
    }.get(mime.split(";")[0], ".bin")
    dest = path.with_suffix(ext)
    dest.write_bytes(data)
    return dest


def to_wav(src: Path) -> Path:
    dest = src.with_suffix(".wav")
    if src.suffix.lower() == ".wav":
        return src
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", str(dest)],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return src
    return dest if dest.is_file() and dest.stat().st_size > 0 else src


def transcribe_file(path: Path) -> str:
    raw = path.read_bytes()
    if len(raw) < 200:
        raise ValueError("录音太短")
    fmt = path.suffix.lower().lstrip(".") or "wav"
    if fmt == "wave":
        fmt = "wav"
    payload = json.dumps(
        {
            "model": MODEL,
            "max_tokens": 1024,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "只转写这段中文口语。不要解释，不要翻译，不要补全没说的词。听不清就按近音写。",
                        },
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": __import__("base64").b64encode(raw).decode("ascii"),
                                "format": fmt,
                            },
                        },
                    ],
                }
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key()}",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8"))
    text = str((data.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()
    text = FENCE.sub("", text).strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
            text = str(parsed.get("text") or parsed.get("transcript") or text).strip()
        except json.JSONDecodeError:
            pass
    if not text:
        raise RuntimeError("转写为空")
    return text


def run(file: Path | None, data_url: str, db_path: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="voice-") as tmp:
        folder = Path(tmp)
        if file:
            src = file
            wav = to_wav(src)
        else:
            data, mime = decode_data_url(data_url)
            src = write_source(folder / "voice", data, mime)
            wav = to_wav(src)
        text = transcribe_file(wav)
    intent = parse_spoken_intent(text, taken_batch_ids=taken_batch_ids(db_path))
    intent["status"] = "success"
    return intent


def main() -> int:
    parser = argparse.ArgumentParser(description="语音转写 + 出题意图")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--data-url-file", type=Path)
    parser.add_argument("--db", type=Path, default=DB)
    args = parser.parse_args()
    if not args.file and not args.data_url_file:
        raise SystemExit("需要 --file 或 --data-url-file")
    data_url = args.data_url_file.read_text(encoding="utf-8") if args.data_url_file else ""
    try:
        result = run(args.file, data_url, args.db)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "text": "", "message": str(exc)[:500]}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
