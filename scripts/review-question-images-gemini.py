#!/usr/bin/env python3
"""Review question figures with isolated Gemini Flash vision calls."""

from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.request
from pathlib import Path


BASE_URL = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")
MODEL = os.environ.get("QUESTION_IMAGE_REVIEW_MODEL", "gemini-3-flash")

SYSTEM_PROMPTS = {
    "candidate": """You are a blind civil-service exam candidate reviewing actual figures.
You must not use or infer any hidden answer key. Read only the supplied question booklet and
images, solve every question independently, and report unreadable text, ambiguous geometry,
unclear connectors, conflicting conditions, or multiple defensible answers. End with exactly:
ANSWERS: <one A-D letter per question>
CANDIDATE_VERDICT: PASS or REJECT
Use REJECT if any figure is unclear or any answer is not unique.""",
    "setter": """You are a strict civil-service exam figure quality reviewer. Independently
verify every supplied figure against the full setter specification: objects, counts, geometry,
labels, dimensions, connections, arrow directions, answer uniqueness, explanation consistency,
readability when reduced, and leakage of any target deduction or answer. Reject the whole set
if any single figure is wrong. End with exactly:
SETTER_VERDICT: PASS or REJECT""",
}


def api_key() -> str:
    if key := os.environ.get("CLIPROXY_API_KEY", "").strip():
        return key
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("CLIPROXY_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("CLIPROXY_API_KEY not found")


def image_part(path: Path) -> dict:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}


def response_text(payload: dict) -> str:
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, str):
        return content
    return "\n".join(
        part.get("text", "") for part in content if isinstance(part, dict)
    ).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=SYSTEM_PROMPTS, required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--image", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    parts: list[dict] = [{
        "type": "text",
        "text": args.prompt_file.read_text(encoding="utf-8").strip()
        + "\nThe attached images are in question order.",
    }]
    for index, image in enumerate(args.image, 1):
        parts.extend(({"type": "text", "text": f"IMAGE {index}"}, image_part(image)))

    payload = {
        "model": MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPTS[args.mode]},
            {"role": "user", "content": parts},
        ],
    }
    request = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key()}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        result = json.loads(response.read().decode("utf-8"))
    text = response_text(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
