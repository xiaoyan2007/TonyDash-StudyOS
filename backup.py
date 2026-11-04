"""创建带时间戳的完整备份（源码 + 可运行程序）。

用法:
    py backup.py 说明标签
"""
from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKUP_ROOT = ROOT / "backup"
IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "_appdata*", "_gui_appdata", "_exe_appdata",
    "_tmp", "_run_tmp", "_shots", ".pytest_cache",
)


def _safe(label: str) -> str:
    keep = []
    for ch in label.strip():
        keep.append(ch if ch.isalnum() or ch in "-_." else "-")
    return "".join(keep)[:40] or "manual"


def main() -> int:
    label = _safe(sys.argv[1] if len(sys.argv) > 1 else "manual")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_ROOT / f"{stamp}-{label}"
    dest.mkdir(parents=True, exist_ok=False)

    (dest / "code").mkdir(parents=True)
    for name in ("campus_planner", "tests", "assets", "update log", "installer"):
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, dest / "code" / name, ignore=IGNORE)
    for name in ("main.py", "README.md", ".gitignore", "backup.py"):
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, dest / "code" / name)
    for spec in ROOT.glob("*.spec"):
        shutil.copy2(spec, dest / "code" / spec.name)

    app_dir = dest / "app"
    dist = ROOT / "dist"
    if dist.is_dir():
        for item in dist.iterdir():
            if item.is_dir():
                shutil.copytree(item, app_dir / item.name)
            elif item.suffix.lower() == ".exe":
                app_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, app_dir / item.name)

    setup = ROOT / "release" / "TonyDash学习终端-Beta1.2-Setup.exe"
    if setup.is_file():
        app_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(setup, app_dir / setup.name)

    files = [p for p in dest.rglob("*") if p.is_file()]
    size = sum(p.stat().st_size for p in files)
    version = "unknown"
    try:
        text = (ROOT / "campus_planner" / "core.py").read_text(encoding="utf-8")
        match = re.search(r"APP_VERSION\s*=\s*['\"]([^'\"]+)", text)
        if match:
            version = match.group(1)
    except OSError:
        pass

    (dest / "MANIFEST.txt").write_text(
        f"备份时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"版本: {version}\n"
        f"说明: {label}\n"
        f"源码: code/\n"
        f"程序: app/\n"
        f"文件数: {len(files)}\n"
        f"总大小: {size / 1024 / 1024:.1f} MB\n",
        encoding="utf-8",
    )
    print(f"备份完成: {dest}  ({len(files)} 个文件, {size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
