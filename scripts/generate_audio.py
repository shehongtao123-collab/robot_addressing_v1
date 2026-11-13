#!/usr/bin/env python3
"""Use CosyVoice 3.5 Plus to synthesize JSONL text into local audio files."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

"""
python3 scripts/generate_audio.py \
  --model qwen-audio-3.1-tts-plus \
  --input datasets/intent_300_v1.jsonl \
  --output-dir /home/cuenca/Downloads/audio_datasets/intent_300_v1 \
  --voice-map config/voices_qwen_3_1_plus.json \
  --format mp3
"""

MODELS = (
    "cosyvoice-v3.5-plus",
    "qwen-audio-3.1-tts-plus",
    "qwen-audio-3.0-tts-flash",
)
FORMATS = ("mp3", "wav", "pcm", "opus")
SAMPLE_RATES = (8000, 12000, 16000, 22050, 24000, 44100, 48000)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按 JSONL 顺序调用百炼 TTS 生成音频和播放清单。"
    )
    parser.add_argument("--input", type=Path, required=True, help="输入 JSONL 文件")
    parser.add_argument("--output-dir", type=Path, required=True, help="音频保存目录")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "model_profiles.json",
        help="模型配置文件；默认 config/model_profiles.json",
    )
    parser.add_argument("--profile", default="bailian", help="读取的模型配置名称；默认 bailian")
    parser.add_argument(
        "--model",
        choices=MODELS,
        default="qwen-audio-3.0-tts-flash",
        help="语音合成模型；默认 qwen-audio-3.0-tts-flash",
    )
    parser.add_argument("--workspace-id", default=os.getenv("DASHSCOPE_WORKSPACE_ID"),
                        help="百炼业务空间 ID；默认读取 DASHSCOPE_WORKSPACE_ID")
    parser.add_argument("--api-key-env", default="DASHSCOPE_API_KEY",
                        help="保存百炼 API Key 的环境变量名")
    parser.add_argument("--voice-map", type=Path, required=True,
                        help='音色映射 JSON，例如 {"H1":"voice-id-1"}')
    parser.add_argument("--text-field", default="text", help="作为合成文本的字段，默认 text")
    parser.add_argument("--speaker-field", default="speaker_id", help="用于选择音色的字段")
    parser.add_argument("--id-field", default="id", help="用于文件名和筛选的 ID 字段")
    parser.add_argument("--ids", help="只生成指定 ID，多个 ID 用英文逗号分隔")
    parser.add_argument("--format", choices=FORMATS, default="mp3", help="输出音频格式")
    parser.add_argument("--sample-rate", type=int, choices=SAMPLE_RATES, default=22050)
    parser.add_argument("--rate", type=float, default=1.0, help="语速，范围 0.5～2.0")
    parser.add_argument("--pitch", type=float, default=1.0, help="音调，范围 0.5～2.0")
    parser.add_argument("--volume", type=int, default=50, help="音量，范围 0～100")
    parser.add_argument("--language", default="zh", help="语言提示，默认 zh")
    parser.add_argument("--instruction", help="可选的语气、情感、方言或角色指令")
    parser.add_argument("--playlist", default="playlist.json", help="播放清单文件名")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的音频")
    parser.add_argument("--continue-on-error", action="store_true", help="单条失败后继续生成")
    parser.add_argument("--dry-run", action="store_true", help="只生成清单，不请求接口")
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} 不是有效 JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} 必须是 JSON 对象")
            rows.append(value)
    return rows


def load_voice_map(path: Path) -> dict[str, str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not value:
        raise ValueError("--voice-map 必须是非空 JSON 对象")
    result = {str(key): str(voice) for key, voice in value.items() if str(voice).strip()}
    if not result:
        raise ValueError("音色映射中没有有效的音色 ID")
    return result


def safe_name(value: Any) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", str(value)).strip("._")
    return cleaned or "item"


def addressing_label(row: dict[str, Any]) -> tuple[bool, str]:
    """Return a stable addressing flag and its Chinese report label."""
    value = row.get("is_to_robot")
    if isinstance(value, bool):
        is_to_robot = value
    else:
        intent = str(row.get("policy_intent") or row.get("intent") or "").lower()
        is_to_robot = intent in {"addressing", "to_robot", "robot"}
    return is_to_robot, "对机器人说的话" if is_to_robot else "闲聊"


def load_profile(path: Path, name: str) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"模型配置文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"模型配置文件不是有效 JSON: {path}: {exc}") from exc
    models = config.get("models", []) if isinstance(config, dict) else []
    profile = next(
        (item for item in models if isinstance(item, dict) and item.get("name") == name), None
    )
    if profile is None:
        raise ValueError(f"{path} 中找不到模型配置 {name!r}")
    return profile


def workspace_from_profile(profile: dict[str, Any]) -> str:
    explicit = str(profile.get("workspace_id", "")).strip()
    if explicit:
        return explicit
    hostname = urlparse(str(profile.get("base_url", ""))).hostname or ""
    candidate = hostname.split(".", 1)[0]
    return candidate if candidate.startswith("ws-") else ""


def resolve_credentials(args: argparse.Namespace) -> tuple[str, str]:
    profile = load_profile(args.config, args.profile)
    workspace_id = (
        str(args.workspace_id or "").strip()
        or os.getenv("DASHSCOPE_WORKSPACE_ID", "").strip()
        or workspace_from_profile(profile)
    )
    env_name = args.api_key_env or str(profile.get("api_key_env", "")).strip()
    api_key = (os.getenv(env_name, "") if env_name else "") or str(profile.get("api_key", ""))
    if not workspace_id:
        raise ValueError(
            f"无法从配置 {args.profile!r} 的 workspace_id/base_url 获取业务空间 ID"
        )
    if not api_key.strip():
        raise ValueError(f"配置 {args.profile!r} 中没有可用的 API Key")
    return workspace_id, api_key.strip()


def request_audio(args: argparse.Namespace, api_key: str, text: str, voice: str) -> bytes:
    endpoint = (
        f"https://{args.workspace_id}.cn-beijing.maas.aliyuncs.com"
        "/api/v1/services/audio/tts/SpeechSynthesizer"
    )
    body = {
        "model": args.model,
        "input": {
            "text": text,
            "voice": voice,
            "format": args.format,
            "sample_rate": args.sample_rate,
            "volume": args.volume,
            "rate": args.rate,
            "pitch": args.pitch,
            "language_hints": [args.language],
        },
    }
    if args.instruction:
        body["input"]["instruction"] = args.instruction
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    result: Any = None
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
        audio_url = result["output"]["audio"]["url"]
        with urllib.request.urlopen(audio_url, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"百炼接口返回 HTTP {exc.code}: {detail}") from exc
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"百炼接口返回结构异常: {result!r}") from exc


def validate_args(args: argparse.Namespace) -> None:
    if not 0.5 <= args.rate <= 2.0:
        raise ValueError("--rate 必须在 0.5～2.0 之间")
    if not 0.5 <= args.pitch <= 2.0:
        raise ValueError("--pitch 必须在 0.5～2.0 之间")
    if not 0 <= args.volume <= 100:
        raise ValueError("--volume 必须在 0～100 之间")
    if Path(args.playlist).name != args.playlist:
        raise ValueError("--playlist 只能是文件名，不能包含上层路径")
    if not args.dry_run and not args.workspace_id:
        raise ValueError("请传入 --workspace-id 或设置 DASHSCOPE_WORKSPACE_ID")


def main() -> int:
    args = parse_args()
    try:
        validate_args(args)
        rows = read_jsonl(args.input)
        voices = load_voice_map(args.voice_map)
        selected_ids = {item.strip() for item in args.ids.split(",") if item.strip()} if args.ids else None
        if args.dry_run:
            api_key = ""
        else:
            args.workspace_id, api_key = resolve_credentials(args)

        args.output_dir.mkdir(parents=True, exist_ok=True)
        playlist: list[str] = []
        failures = 0
        print(f"模型: {args.model}")

        for index, row in enumerate(rows, 1):
            item_id = str(row.get(args.id_field, index))
            if selected_ids is not None and item_id not in selected_ids:
                continue
            text = row.get(args.text_field)
            speaker = str(row.get(args.speaker_field, ""))
            if not isinstance(text, str) or not text.strip():
                print(f"跳过 {item_id}: 字段 {args.text_field!r} 没有文本", file=sys.stderr)
                continue
            if speaker not in voices:
                print(f"跳过 {item_id}: 没有为 {speaker!r} 配置音色", file=sys.stderr)
                continue

            filename = f"{index:04d}_{safe_name(item_id)}_{safe_name(speaker)}.{args.format}"
            target = args.output_dir / filename
            is_to_robot, category = addressing_label(row)
            playlist.append(
                {
                    "filename": filename,
                    "filepath": str(target.resolve()),
                    "category": category,
                    "is_to_robot": is_to_robot,
                }
            )
            if target.exists() and not args.overwrite:
                print(f"[{index}/{len(rows)}] 已存在，跳过请求: {filename}")
                continue
            if args.dry_run:
                print(f"[{index}/{len(rows)}] 预览: {filename} <- {text}")
                continue
            try:
                audio = request_audio(args, api_key, text, voices[speaker])
                target.write_bytes(audio)
                print(f"[{index}/{len(rows)}] 已保存: {target}")
                time.sleep(0.05)
            except Exception as exc:  # keep the case ID in user-facing errors
                failures += 1
                playlist.pop()
                print(f"[{index}/{len(rows)}] {item_id} 生成失败: {exc}", file=sys.stderr)
                if not args.continue_on_error:
                    raise

        playlist_path = args.output_dir / args.playlist
        playlist_path.write_text(
            json.dumps(playlist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"播放清单: {playlist_path}（{len(playlist)} 个音频）")
        return 1 if failures else 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
