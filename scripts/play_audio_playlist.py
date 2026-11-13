#!/usr/bin/env python3
"""按照 playlist.json 的顺序使用 pygame.mixer 播放音频。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import pygame
    PygameError = pygame.error
except ImportError:
    pygame = None

    class PygameError(Exception):
        """Placeholder used when pygame is not installed."""

"""
python3 scripts/play_audio_playlist.py \
  --playlist /home/cuenca/Downloads/audio_datasets/intent_300_v1_mp3/playlist.json \
  --volume 0.8
"""

PLAYBACK_WAIT_SECONDS = 1


@dataclass(frozen=True)
class PlaylistItem:
    filename: str
    filepath: Path
    category: str
    is_to_robot: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按照 JSON 清单中的顺序播放音频。")
    parser.add_argument("--playlist", type=Path, required=True, help="播放清单 JSON")
    parser.add_argument("--volume", type=float, default=1.0, help="播放音量，范围 0.0～1.0")
    return parser.parse_args()


def parse_playlist_item(value: Any, index: int, playlist_directory: Path) -> PlaylistItem:
    if not isinstance(value, dict):
        raise ValueError(f"清单第 {index} 项必须是 JSON 对象")

    filename = value.get("filename")
    filepath = value.get("filepath")
    category = value.get("category")
    is_to_robot = value.get("is_to_robot")

    if not isinstance(filename, str) or not filename:
        raise ValueError(f"清单第 {index} 项的 filename 必须是非空字符串")
    if Path(filename).name != filename:
        raise ValueError(f"清单第 {index} 项的 filename 只能包含文件名: {filename!r}")
    if not isinstance(filepath, str) or not filepath:
        raise ValueError(f"清单第 {index} 项的 filepath 必须是非空字符串")

    audio_path = Path(filepath)
    if not audio_path.is_absolute():
        raise ValueError(f"清单第 {index} 项的 filepath 必须是绝对路径: {filepath!r}")
    if audio_path.name != filename:
        raise ValueError(
            f"清单第 {index} 项的 filename 与 filepath 文件名不一致: "
            f"{filename!r} != {audio_path.name!r}"
        )
    if not isinstance(category, str) or not category:
        raise ValueError(f"清单第 {index} 项的 category 必须是非空字符串")
    if not isinstance(is_to_robot, bool):
        raise ValueError(f"清单第 {index} 项的 is_to_robot 必须是布尔值")
    if not audio_path.is_file():
        nearby_path = playlist_directory / filename
        if nearby_path.is_file():
            audio_path = nearby_path
        else:
            raise FileNotFoundError(
                f"清单第 {index} 项的音频不存在: {audio_path}；"
                f"清单同目录也没有找到: {nearby_path}"
            )

    return PlaylistItem(filename, audio_path, category, is_to_robot)


def load_playlist(path: Path) -> list[PlaylistItem]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"播放清单不是有效 JSON: {path}: {exc}") from exc
    if not isinstance(value, list):
        raise ValueError("播放清单必须是 JSON 数组")
    if not value:
        raise ValueError("播放清单不能为空")
    playlist_directory = path.resolve().parent
    return [parse_playlist_item(item, index, playlist_directory)
            for index, item in enumerate(value, 1)]


def play(items: list[PlaylistItem], volume: float) -> None:
    if pygame is None:
        raise RuntimeError("未安装 pygame，请执行 python -m pip install -r requirements.txt")
    pygame.mixer.init()
    pygame.mixer.music.set_volume(volume)
    clock = pygame.time.Clock()

    for index, item in enumerate(items, 1):
        print(f"[{index}/{len(items)}] [{item.category}] 播放: {item.filename}")
        pygame.mixer.music.load(str(item.filepath))
        playback_started = time.monotonic()
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            clock.tick(20)
        playback_seconds = time.monotonic() - playback_started
        pygame.mixer.music.unload()
        print(f"播放完成，语音耗时 {playback_seconds:.3f} 秒；等待 {PLAYBACK_WAIT_SECONDS} 秒……")
        time.sleep(PLAYBACK_WAIT_SECONDS)


def main() -> int:
    args = parse_args()
    try:
        if not 0.0 <= args.volume <= 1.0:
            raise ValueError("--volume 必须在 0.0～1.0 之间")
        play(load_playlist(args.playlist), args.volume)
        return 0
    except KeyboardInterrupt:
        print("\n播放已停止。")
        return 130
    except PygameError as exc:
        print(f"pygame 播放失败: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    finally:
        if pygame is not None and pygame.mixer.get_init():
            pygame.mixer.music.stop()
            pygame.mixer.quit()


if __name__ == "__main__":
    raise SystemExit(main())
