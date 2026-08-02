#!/usr/bin/env python3
"""Interactive console wizard for assembling an iPhone Vlog project.

The wizard scans an inbox folder, lets the operator assign each asset a role
and order, writes projects/<name>/vlog-plan.json, copies assets into the
project, and can optionally run the processing and rendering scripts.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    marker = "Y/n" if default else "y/N"
    value = input(f"{prompt} ({marker}): ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "はい", "h"}


def scan_assets(inbox: Path) -> list[Path]:
    allowed = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS
    return sorted(
        [p for p in inbox.iterdir() if p.is_file() and p.suffix.lower() in allowed],
        key=lambda p: p.name.lower(),
    )


def choose_asset(assets: list[Path], label: str, optional: bool = False) -> Path | None:
    print(f"\n{label}")
    if optional:
        print("  0. 使わない")
    for i, path in enumerate(assets, start=1):
        print(f"  {i}. {path.name}")

    while True:
        raw = ask("番号を選択", "0" if optional else "1")
        try:
            number = int(raw)
        except ValueError:
            print("数字で入力してください。")
            continue
        if optional and number == 0:
            return None
        if 1 <= number <= len(assets):
            return assets[number - 1]
        print("範囲内の番号を選んでください。")


def choose_many(assets: list[Path], label: str) -> list[Path]:
    print(f"\n{label}")
    print("  0. 使わない")
    for i, path in enumerate(assets, start=1):
        print(f"  {i}. {path.name}")
    raw = ask("番号をカンマ区切りで入力（並び順になります）", "0")
    if raw == "0":
        return []
    selected: list[Path] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            idx = int(chunk)
        except ValueError:
            print(f"無効な番号を無視しました: {chunk}")
            continue
        if 1 <= idx <= len(assets):
            selected.append(assets[idx - 1])
    return selected


def copy_asset(source: Path, project: Path, role: str, index: int) -> str:
    if source.suffix.lower() in IMAGE_EXTENSIONS:
        folder = project / "screenshots"
    elif role in {"opening", "ending", "camera"}:
        folder = project / "camera"
    else:
        folder = project / "screen"
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"{index:02d}_{role}{source.suffix.lower()}"
    shutil.copy2(source, destination)
    return str(destination.relative_to(project))


def main() -> None:
    print("=== RTS Vlog Console ===")
    print("素材を選び、順番を決め、処理と動画生成まで進めます。\n")

    project_name = ask("プロジェクト名", "vlog-001")
    inbox_value = ask("素材フォルダ", str(ROOT / "inbox" / project_name))
    inbox = Path(inbox_value).expanduser().resolve()
    if not inbox.is_dir():
        print(f"[ERROR] 素材フォルダがありません: {inbox}", file=sys.stderr)
        raise SystemExit(1)

    assets = scan_assets(inbox)
    if not assets:
        print(f"[ERROR] 動画・画像が見つかりません: {inbox}", file=sys.stderr)
        raise SystemExit(1)

    videos = [p for p in assets if p.suffix.lower() in VIDEO_EXTENSIONS]
    images = [p for p in assets if p.suffix.lower() in IMAGE_EXTENSIONS]
    if not videos:
        print("[ERROR] 最低1本の動画が必要です。", file=sys.stderr)
        raise SystemExit(1)

    opening = choose_asset(videos, "オープニング動画を選ぶ")
    screen = choose_asset(videos, "画面収録を選ぶ", optional=True)
    screenshots = choose_many(images, "差し込むスクリーンショットを選ぶ") if images else []
    ending = choose_asset(videos, "エンディング動画を選ぶ", optional=True)

    project = ROOT / "projects" / project_name
    if project.exists() and any(project.iterdir()):
        if not ask_yes_no(f"既存プロジェクト {project_name} を作り直しますか？"):
            print("中止しました。")
            return
        shutil.rmtree(project)
    project.mkdir(parents=True, exist_ok=True)

    timeline: list[dict[str, object]] = []
    order = 1

    opening_path = copy_asset(opening, project, "opening", order)
    timeline.append({"type": "video", "source": opening_path, "role": "opening"})
    order += 1

    if screen:
        screen_path = copy_asset(screen, project, "screen-demo", order)
        timeline.append({"type": "video", "source": screen_path, "role": "screen-demo"})
        order += 1

    image_seconds = float(ask("スクリーンショット1枚の表示秒数", "5"))
    for image in screenshots:
        image_path = copy_asset(image, project, "screenshot", order)
        timeline.append(
            {
                "type": "image",
                "source": image_path,
                "role": "screenshot",
                "durationSeconds": image_seconds,
                "motion": "slow-pan",
            }
        )
        order += 1

    if ending:
        ending_path = copy_asset(ending, project, "ending", order)
        timeline.append({"type": "video", "source": ending_path, "role": "ending"})

    plan = {
        "version": 1,
        "project": project_name,
        "policy": {
            "screenRecording": "short-demo-only",
            "defaultEvidence": "screenshots",
            "privacyReviewRequired": True,
        },
        "timeline": timeline,
    }
    plan_path = project / "vlog-plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 作成した順番 ===")
    for i, item in enumerate(timeline, start=1):
        print(f"{i}. {item['role']} -> {item['source']}")
    print(f"\n保存: {plan_path}")

    if ask_yes_no("文字起こし・字幕生成まで実行しますか？", default=True):
        subprocess.run(["bash", str(ROOT / "scripts" / "process_vlog.sh"), str(project)], check=True)
        if ask_yes_no("公開前チェック後、動画を書き出しますか？"):
            subprocess.run(["bash", str(ROOT / "scripts" / "render_vlog.sh"), project_name], check=True)
            print(f"完成動画: {ROOT / 'output' / project_name / 'vlog.mp4'}")
        else:
            print(f"確認ファイル: {ROOT / 'output' / project_name / 'NEXT_STEPS.md'}")


if __name__ == "__main__":
    main()
