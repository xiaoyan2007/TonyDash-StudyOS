"""路径解析：定位 labkit 子包、主程序源码、运行期数据目录。

设计要点
--------
* 本包已整合进主程序（``campus_planner/labkit/``），路径锚点随之上移：
  ``campus_planner/labkit/common/paths.py`` -> ``parents[2]`` = ``campus_planner/``；
* **运行期数据绝不写进 git 仓库**：一律落在 ``campus_planner/_data/``，
  该目录已在 ``.gitignore`` 中排除；
* 样例文件随源码放在 ``campus_planner/samples/``，保证首次运行开箱可用；
* 主程序源码目录（``campus_planner/``）在本模块里只读引用，用于复用主题。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: `campus_planner/labkit/common/paths.py` -> `campus_planner/`
PACKAGE_ROOT = Path(__file__).resolve().parents[2]

#: 样例文件随源码 / 随程序分发，只读
SAMPLE_DIR = PACKAGE_ROOT / "samples"

if getattr(sys, "frozen", False):
    # 打包运行：数据绝不能放安装目录或临时解包目录（前者卸载会被删、
    # 后者每次启动都清空），与主程序同源：%APPDATA%\CampusPlanner 下的子目录。
    _base = os.environ.get("APPDATA") or str(Path.home())
    DATA_DIR = Path(_base) / "CampusPlanner" / "labkit"
else:
    #: 开发期数据目录（导入历史、缓存、发音），已 gitignore
    DATA_DIR = PACKAGE_ROOT / "_data"

CACHE_DIR = DATA_DIR / "cache"
AUDIO_DIR = DATA_DIR / "audio"

#: 工作区根目录（主程序包与 lab 工具都在这一层）
WORKSPACE_ROOT = PACKAGE_ROOT.parent
MAIN_PACKAGE = PACKAGE_ROOT


def ensure_dir(path: Path) -> Path:
    """创建目录并返回它。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_file(name: str) -> Path:
    """`campus_planner/_data/<name>`，自动建目录。"""
    ensure_dir(DATA_DIR)
    return DATA_DIR / name


def cache_file(name: str) -> Path:
    ensure_dir(CACHE_DIR)
    return CACHE_DIR / name


def audio_dir(accent: str = "") -> Path:
    """发音缓存目录；给定口音时返回其子目录。"""
    base = ensure_dir(AUDIO_DIR)
    if accent:
        return ensure_dir(base / accent)
    return base


def has_main_package() -> bool:
    """主程序源码是否就在旁边（旁边就能复用它的主题和组件）。"""
    return (MAIN_PACKAGE / "theme.py").is_file()


def describe() -> dict:
    """自检用：打印当前解析到的关键路径。"""
    return {
        "package_root": str(PACKAGE_ROOT),
        "data_dir": str(DATA_DIR),
        "sample_dir": str(SAMPLE_DIR),
        "workspace_root": str(WORKSPACE_ROOT),
        "main_package": str(MAIN_PACKAGE),
        "main_package_found": has_main_package(),
        "frozen": bool(getattr(__import__("sys"), "_MEIPASS", None)),
        "pid": os.getpid(),
    }
