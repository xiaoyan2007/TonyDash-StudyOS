"""发音 mp3 的本地缓存。

设计要点（对齐调研结论）：

* 命名统一走 ``norm.lower()``，路径 ``<lab/_data/audio>/<口音>/<安全化后的词>.mp3``；
* **收藏时就把 mp3 存到本地**，之后离线也能播（这是用户明确要求「收藏时保存发音」）；
* 命中即不再请求网络；下载失败只返回 ``None``，绝不因为「没声音」打断收藏流程。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from ..common import paths

if TYPE_CHECKING:  # pragma: no cover - 仅类型提示，避免循环导入
    from .client import YoudaoClient
    from .models import WordEntry

#: Windows 文件名禁用字符
_UNSAFE = re.compile(r'[\\/:*?"<>|\r\n\t]+')
_RE_WS = re.compile(r"\s+")
MAX_STEM = 80


def safe_stem(text: str) -> str:
    """把查询词变成安全的文件名主干。"""
    stem = _UNSAFE.sub("_", str(text or "")).strip(" .")
    stem = _RE_WS.sub(" ", stem)
    if len(stem) > MAX_STEM:
        stem = stem[:MAX_STEM].rstrip()
    return stem or "audio"


class AudioStore:
    """发音缓存目录的门面。"""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else paths.AUDIO_DIR

    # ------------------------------------------------------------------ 路径
    def path_for(self, norm: str, accent: str) -> Path:
        return self.root / (accent or "uk") / f"{safe_stem(norm)}.mp3"

    def rel_for(self, norm: str, accent: str) -> str:
        """相对 ``lab/_data/audio`` 的 POSIX 路径（写进单词本 JSON）。"""
        return f"{accent or 'uk'}/{safe_stem(norm)}.mp3"

    def resolve(self, rel: str) -> Path:
        """把单词本里记的相对路径还原成绝对路径。"""
        return self.root / rel.replace("\\", "/")

    # ------------------------------------------------------------------ 读写
    def has(self, norm: str, accent: str) -> bool:
        path = self.path_for(norm, accent)
        return path.is_file() and path.stat().st_size > 0

    def read(self, norm: str, accent: str) -> bytes | None:
        path = self.path_for(norm, accent)
        try:
            data = path.read_bytes()
        except OSError:
            return None
        return data or None

    def save(self, norm: str, accent: str, data: bytes) -> Path:
        path = self.path_for(norm, accent)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".mp3.part")
        tmp.write_bytes(data)
        tmp.replace(path)
        return path

    def remove(self, norm: str, accents: tuple[str, ...] = ("uk", "us")) -> int:
        removed = 0
        for accent in accents:
            path = self.path_for(norm, accent)
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
        return removed

    # ------------------------------------------------------------------ 下载
    def ensure(self, entry: WordEntry, client: YoudaoClient, accents: tuple[str, ...] = ("uk", "us")) -> dict[str, str]:
        """确保这个词的发音在本地；返回更新后的 ``audio_files`` 映射。

        * 已经有本地文件 → 直接记录路径，不发请求；
        * 某个口音失败 → 换下一个口音（实测覆盖不对称）；
        * 全都失败 → 返回原样（界面隐藏发音按钮即可）。
        """
        files = dict(entry.audio_files or {})
        norm = entry.norm or entry.word
        for accent in accents:
            if self.has(norm, accent):
                files[accent] = self.rel_for(norm, accent)
        missing = [a for a in accents if a not in files and entry.voice_token(a)]
        if missing and client is not None:
            got = client.fetch_voice_any(entry, accents=tuple(missing))
            if got:
                accent, data = got
                self.save(norm, accent, data)
                files[accent] = self.rel_for(norm, accent)
        return files

    # ------------------------------------------------------------------ 统计
    def size(self) -> int:
        total = 0
        for path in self.root.rglob("*.mp3"):
            try:
                total += path.stat().st_size
            except OSError:
                pass
        return total

    def count(self) -> int:
        return sum(1 for _ in self.root.rglob("*.mp3"))

    def clear(self) -> int:
        removed = 0
        for path in self.root.rglob("*.mp3"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
        return removed

    def describe(self) -> str:
        return f"{self.count()} 个发音文件，共 {self.size() / 1024:.0f} KB"
