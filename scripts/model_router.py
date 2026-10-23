#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一模型路由：ExamSystem 里所有「用哪个模型 / 哪个 API」都从这里读。

事实来源：~/.hermes/model-router.json 的 active profile。
- 一个地方切换（前端「模型」页签 / 直接改 JSON），全系统跟随。
- 旧的按用途环境变量（ZILIAO_GEMINI_MODEL / DAILY_GEMINI_MODEL / CLIPROXY_PDF_MODEL
  / QUESTION_IMAGE_MODEL / QUESTION_IMAGE_REVIEW_MODEL / VOICE_TRANSCRIBE_MODEL / QUIZ_LITE_MODEL）
  仍保留：显式设置时优先（按用途覆盖），未设置时跟随 router 的 active 模型。

能力位（supports_vision / supports_audio / supports_image_output）用于门控：
- 切到不支持视觉的模型（如 DeepSeek）时，视觉任务（录屏复盘、图片生成/审核）明确报错，不静默跑。
- 切到不支持语音的模型时，语音输入在前端直接禁用。

用法：
    import model_router
    MODEL = model_router.resolve_model()          # 跟随 active
    MODEL = model_router.resolve_model("ziliao")  # 允许按用途 env 覆盖
    BASE  = model_router.resolve_base_url()
    KEY   = model_router.resolve_api_key()

CLI：
    python3 scripts/model_router.py --show                # 打印当前 active 与能力位
    python3 scripts/model_router.py --apply-config deepseek  # 把 active 同步进 ~/.hermes/config.yaml
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROUTER_PATH = Path(
    os.environ.get("HERMES_MODEL_ROUTER", "")
    or str(Path.home() / ".hermes" / "model-router.json")
)
HERMES_CONFIG = Path.home() / ".hermes" / "config.yaml"
DEFAULT_PROFILE = "gemini-cliproxy"
DEFAULT_MODEL = "gemini-3.8-flash-high"

# 按用途的旧环境变量覆盖（显式设置时优先于 router 的 active 模型）
_PURPOSE_ENVS = {
    "ziliao": "ZILIAO_GEMINI_MODEL",
    "daily": "DAILY_GEMINI_MODEL",
    "quiz_lite": "QUIZ_LITE_MODEL",
    "pdf": "CLIPROXY_PDF_MODEL",
    "image": "QUESTION_IMAGE_MODEL",
    "image_review": "QUESTION_IMAGE_REVIEW_MODEL",
    "voice": "VOICE_TRANSCRIBE_MODEL",
}


def _load() -> dict:
    """读 router JSON；缺失/损坏时回退到默认 profile（不阻塞脚本）。"""
    try:
        data = json.loads(ROUTER_PATH.read_text(encoding="utf-8"))
        profiles = data.get("profiles") or {}
        active = str(data.get("active") or "")
        if active not in profiles:
            active = DEFAULT_PROFILE if DEFAULT_PROFILE in profiles else (next(iter(profiles), ""))
        return {"active": active, "profiles": profiles}
    except Exception:
        return {"active": DEFAULT_PROFILE, "profiles": {}}


def active_profile_name() -> str:
    return _load()["active"]


def active_profile() -> dict:
    d = _load()
    return d["profiles"].get(d["active"]) or {}


def resolve_model(purpose: str | None = None) -> str:
    """当前生效的模型名。purpose 非空时允许按用途 env 覆盖。"""
    if purpose:
        env_name = _PURPOSE_ENVS.get(purpose)
        if env_name and os.environ.get(env_name, "").strip():
            return os.environ[env_name].strip()
    return active_profile().get("model") or DEFAULT_MODEL


def resolve_base_url() -> str:
    prof = active_profile()
    if prof.get("base_url"):
        return str(prof["base_url"]).rstrip("/")
    # 兼容：router 缺失时回退到 cliproxy
    return os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8889/v1").rstrip("/")


def resolve_api_key() -> str:
    """按 active profile 的 api_key_env 解析密钥：进程环境 → ~/.hermes/.env。"""
    prof = active_profile()
    env = str(prof.get("api_key_env") or "CLIPROXY_API_KEY")
    if val := os.environ.get(env, "").strip():
        return val
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.is_file():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith(f"{env}="):
                    return line.split("=", 1)[1].strip().strip("\"'")
        except Exception:
            pass
    raise RuntimeError(
        f"{env} not found（model-router active={active_profile_name()}）——请在 ~/.hermes/.env 填入"
    )


def resolve_api_key_env() -> str:
    return str(active_profile().get("api_key_env") or "CLIPROXY_API_KEY")


def resolve_api_mode() -> str:
    return str(active_profile().get("api_mode") or "chat_completions")


def supports_vision() -> bool:
    return bool(active_profile().get("supports_vision", True))


def supports_audio() -> bool:
    return bool(active_profile().get("supports_audio", False))


def supports_image_output() -> bool:
    return bool(active_profile().get("supports_image_output", supports_vision()))


def context_length() -> int | None:
    v = active_profile().get("context_length")
    try:
        return int(v) if v else None
    except (TypeError, ValueError):
        return None


def profile_list() -> list[dict]:
    """给前端/调试用的 profile 摘要（不含密钥值）。"""
    out = []
    for name, p in _load()["profiles"].items():
        out.append({
            "id": name,
            "label": p.get("label", name),
            "model": p.get("model", ""),
            "base_url": p.get("base_url", ""),
            "api_key_env": p.get("api_key_env", ""),
            "api_mode": p.get("api_mode", ""),
            "supports_vision": bool(p.get("supports_vision", True)),
            "supports_audio": bool(p.get("supports_audio", False)),
            "supports_image_output": bool(p.get("supports_image_output", p.get("supports_vision", True))),
            "context_length": p.get("context_length"),
        })
    return out


# ───────────────────────── config.yaml 同步 ─────────────────────────
def apply_config(profile_name: str) -> dict:
    """把 router 的 active profile 写进 ~/.hermes/config.yaml。

    用 key_env 指针引用 .env（不在 config.yaml 里落明文密钥）。
    保留其他所有配置键；Hermes 会在下一个会话/轮次热重载。
    """
    import yaml

    d = _load()
    profiles = d["profiles"]
    if profile_name not in profiles:
        raise KeyError(f"profile 不存在: {profile_name}")
    prof = profiles[profile_name]

    cfg = {}
    if HERMES_CONFIG.is_file():
        cfg = yaml.safe_load(HERMES_CONFIG.read_text(encoding="utf-8")) or {}

    # model 主段
    model_cfg = {
        "provider": f"custom:{profile_name}",
        "default": prof.get("model", DEFAULT_MODEL),
        "base_url": prof.get("base_url", ""),
        "key_env": prof.get("api_key_env", ""),
        "api_mode": prof.get("api_mode", "chat_completions"),
    }
    cfg["model"] = model_cfg

    # providers 段：更新本 profile 的条目，保留其他（cliproxy/highway 等）
    providers = dict(cfg.get("providers") or {})
    providers[profile_name] = {
        "base_url": prof.get("base_url", ""),
        "key_env": prof.get("api_key_env", ""),
        "api_mode": prof.get("api_mode", "chat_completions"),
        "models": {
            prof.get("model", DEFAULT_MODEL): {
                "supports_vision": bool(prof.get("supports_vision", True)),
                "context_length": prof.get("context_length") or 1048576,
            }
        },
    }
    cfg["providers"] = providers

    # model_aliases.pdf-gemini（PDF/文档解析走主模型）
    aliases = dict(cfg.get("model_aliases") or {})
    aliases["pdf-gemini"] = {
        "model": prof.get("model", DEFAULT_MODEL),
        "provider": f"custom:{profile_name}",
        "base_url": prof.get("base_url", ""),
        "key_env": prof.get("api_key_env", ""),
    }
    cfg["model_aliases"] = aliases

    HERMES_CONFIG.write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return {"applied": profile_name, "model": prof.get("model", DEFAULT_MODEL), "config": str(HERMES_CONFIG)}


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="统一模型路由")
    ap.add_argument("--show", action="store_true", help="显示当前 active 与 profile 列表")
    ap.add_argument("--apply-config", metavar="PROFILE", help="把指定 profile 写进 ~/.hermes/config.yaml")
    args = ap.parse_args()

    if args.show:
        active = active_profile_name()
        prof = active_profile()
        print(f"active: {active}")
        print(f"  model: {prof.get('model')}")
        print(f"  base_url: {prof.get('base_url')}")
        print(f"  api_key_env: {prof.get('api_key_env')}")
        print(f"  api_mode: {prof.get('api_mode')}")
        print(f"  supports_vision: {supports_vision()}")
        print(f"  supports_audio: {supports_audio()}")
        print(f"  context_length: {context_length()}")
        print("profiles:")
        for p in profile_list():
            mark = " *" if p["id"] == active else "  "
            print(f"{mark} {p['id']}: {p['label']} ({p['model']}) vision={p['supports_vision']} audio={p['supports_audio']}")
        return 0

    if args.apply_config:
        try:
            result = apply_config(args.apply_config)
        except Exception as e:
            print(f"应用失败: {e}", file=sys.stderr)
            return 1
        print(f"已应用 → {result['model']}（{result['config']}）")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
