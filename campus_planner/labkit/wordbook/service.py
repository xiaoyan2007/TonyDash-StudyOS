"""``WordService`` —— 查询编排层（UI 只跟它打交道，不直接碰网络和文件）。

一次查询的完整顺序：

1. **本地就拒绝空输入**（有道对空串会返回单词 ``null`` 的词条）；
2. 查缓存（TTL 内直接返回，``from_cache=True``，不发请求）；
3. 联网查询（``YoudaoClient``）；成功且找到了就写进缓存；
4. 联网失败或查无此词时依次退化：**已收藏的词条 → 本地词库（ECDICT）**；
5. 仍然没有就返回一条带错误说明的 ``LookupResult``，界面据此提示。

收藏（``add``）时会把**发音 mp3 落到本地**，之后离线也能播 —— 这是需求里
「收藏时在本地保存单词的发音、音标、释义和例句」的落点。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import parser as P
from .audio import AudioStore
from .client import YoudaoClient, YoudaoError
from .models import WordEntry
from .offline import OfflineDict
from .store import QueryCache, WordbookStore, sort_entries


@dataclass
class LookupResult:
    """一次查询的结果（成功与否都返回它，界面不用 try/except）。"""

    entry: WordEntry
    from_cache: bool = False
    from_offline: bool = False
    error: str = ""
    elapsed_ms: int = 0
    suggestions: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def found(self) -> bool:
        return self.entry.found

    def describe(self) -> str:
        if self.error:
            return self.error
        if not self.entry.found:
            return "词典没有收录这个词"
        where = "缓存" if self.from_cache else ("本地词库" if self.from_offline else "有道词典")
        return f"{self.entry.word}（{where}，{self.elapsed_ms} ms）"


class WordService:
    """查词 + 单词本 + 发音缓存的门面。"""

    def __init__(
        self,
        *,
        client: YoudaoClient | None = None,
        wordbook: WordbookStore | None = None,
        cache: QueryCache | None = None,
        audio: AudioStore | None = None,
        offline: OfflineDict | None = None,
    ) -> None:
        self.client = client or YoudaoClient()
        self.wordbook = wordbook if wordbook is not None else WordbookStore()
        self.cache = cache if cache is not None else QueryCache()
        self.audio = audio if audio is not None else AudioStore()
        self.offline = offline if offline is not None else OfflineDict()
        #: 本次进程内已经查过的词（避免同一个词连续点两次都打网络）
        self._recent: dict[str, WordEntry] = {}

    # ------------------------------------------------------------------ 查询
    def lookup(self, query: str, *, use_cache: bool = True, want_voice: bool = False,
               lang: str = "en",
               on_progress: Callable[[int, str], None] | None = None) -> LookupResult:
        started = time.perf_counter()

        def emit(pct: int, text: str) -> None:
            """进度回调：界面在等网络时能看到百分比在动（失败静默）。"""
            if on_progress is None:
                return
            try:
                on_progress(int(pct), text)
            except Exception:  # noqa: BLE001 - 回调异常不该影响查询
                pass

        emit(5, "开始查询…")
        norm = P.normalize(query)
        if not norm:
            return LookupResult(
                entry=P.make_missing(str(query or "")),
                error="请输入要查询的单词或短语",
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
        le = str(lang or "en").strip().lower() or "en"

        # 1) 缓存（键带语言：法汉词典命中不能拿去回答英汉查询）
        ck = norm if le == "en" else f"{norm}::{le}"
        if use_cache:
            hit = self.cache.get(ck)
            if hit is not None:
                emit(100, "缓存命中")
                return LookupResult(
                    entry=hit,
                    from_cache=True,
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                )

        # 2) 联网
        error = ""
        if self.client is not None:
            emit(20, "连接有道词典…")
            try:
                entry = self.client.query(norm, lang=le, on_progress=on_progress)
                if entry.found:
                    emit(80, "整理释义…")
                    self.cache.put(entry, key=ck)
                    self._recent[ck] = entry
                    emit(100, "查询完成")
                    return LookupResult(
                        entry=entry,
                        elapsed_ms=int((time.perf_counter() - started) * 1000),
                    )
                # 查无此词：给联想建议（拼错时这一步最有用）。
                # 优先用 suggest 接口（带解释），失败再退回响应里的 typos 候选词。
                emit(70, "准备联想词…")
                suggestions = self.suggest(norm)
                if not suggestions and entry.suggestions:
                    suggestions = [(word, "") for word in entry.suggestions]
                emit(100, "词典没有收录这个词")
                return LookupResult(
                    entry=entry,
                    suggestions=suggestions,
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                )
            except YoudaoError as exc:
                error = str(exc)
            except Exception as exc:  # 兜底：网络层再奇怪也不该让界面崩
                error = f"查询失败：{exc}"

        # 3) 已收藏的词条
        emit(60, "尝试本地收藏…")
        saved = self.wordbook.get(norm)
        if saved is not None and saved.found:
            emit(100, "显示本地收藏的词条")
            return LookupResult(
                entry=saved,
                from_offline=True,
                error="" if not error else f"{error}（显示已收藏的词条）",
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )

        # 4) 本地词库
        emit(75, "查本地词库…")
        local = self.offline.lookup(norm) if self.offline is not None else None
        if local is not None:
            emit(100, "显示本地词库释义")
            return LookupResult(
                entry=local,
                from_offline=True,
                error="" if not error else f"{error}（显示本地词库释义）",
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )

        # 5) 什么都没有
        message = error or "词典没有收录这个词，也没有本地词库可兜底"
        if not self.offline.available():
            message += f"；{self.offline.describe()}"
        emit(100, "查询失败")
        return LookupResult(
            entry=P.make_missing(norm),
            error=message,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

    def suggest(self, query: str, *, num: int = 5) -> list[tuple[str, str]]:
        """联想词（失败静默返回空，联想不是主功能）。"""
        if self.client is None:
            return []
        try:
            return self.client.suggest(query, num=num)
        except Exception:
            return []

    # ------------------------------------------------------------------ 单词本
    def is_saved(self, query: str) -> bool:
        norm = P.normalize(query)
        return bool(norm) and self.wordbook.has(norm)

    def saved_entries(self, *, order: str = "time") -> list[WordEntry]:
        return sort_entries(self.wordbook.entries(), order)

    def search_saved(self, keyword: str) -> list[WordEntry]:
        return self.wordbook.search(keyword)

    def add(self, entry: WordEntry, *, want_audio: bool = True,
            on_progress: Callable[[int, str], None] | None = None) -> tuple[bool, str]:
        """收藏一个词条（含发音落盘）；返回 ``(是否新词, 提示文本)``。

        收藏失败的唯一情况是「词典没收录」——那没有可保存的内容。
        """
        if not entry or not entry.found:
            return False, "这个词还没有释义，无法收藏（可以先联网查询）"
        norm = entry.norm or P.normalize(entry.word) or ""
        if not norm:
            return False, "词条内容异常，无法收藏"
        messages: list[str] = []
        if want_audio and entry.has_audio:
            if on_progress is not None:
                try:
                    on_progress(10, "下载发音…")
                except Exception:  # noqa: BLE001
                    pass
            before = dict(entry.audio_files or {})
            entry.audio_files = self.audio.ensure(entry, self.client, on_progress=on_progress)
            if entry.audio_files and entry.audio_files != before:
                messages.append("发音已保存到本地")
            elif not entry.audio_files:
                messages.append("发音下载失败，已保存文字内容")
        if entry.fetched_at == 0:
            entry.fetched_at = int(time.time())
        if on_progress is not None:
            try:
                on_progress(95, "写入单词本…")
            except Exception:  # noqa: BLE001
                pass
        is_new = self.wordbook.add(entry)
        if on_progress is not None:
            try:
                on_progress(100, "已加入单词本")
            except Exception:  # noqa: BLE001
                pass
        return is_new, "，".join(messages)

    def remove(self, query: str) -> bool:
        """移出单词本（连带删除本地发音文件）。"""
        norm = P.normalize(query)
        if not norm:
            return False
        removed = self.wordbook.remove(norm)
        if removed:
            self.audio.remove(norm)
        return removed

    def update_note(self, query: str, note: str) -> bool:
        norm = P.normalize(query)
        return bool(norm) and self.wordbook.set_note(norm, note)

    def update_priority(self, query: str, priority: int) -> bool:
        norm = P.normalize(query)
        return bool(norm) and self.wordbook.set_priority(norm, priority)

    # ------------------------------------------------------------------ 发音
    def audio_source(self, entry: WordEntry, accent: str = "uk") -> tuple[str, str]:
        """返回 ``(类型, 路径或地址)``：``("file", 绝对路径)`` 或 ``("url", 网址)``。"""
        norm = entry.norm or entry.word
        rel = entry.local_audio(accent)
        if rel:
            path = self.audio.resolve(rel)
            if path.is_file():
                return "file", str(path)
        if self.audio.has(norm, accent):
            return "file", str(self.audio.path_for(norm, accent))
        url = P.build_voice_url(entry.voice_token(accent), accent)
        return ("url", url) if url else ("", "")

    def cached_audio_path(self, entry: WordEntry, accent: str = "uk") -> Path | None:
        norm = entry.norm or entry.word
        if self.audio.has(norm, accent):
            return self.audio.path_for(norm, accent)
        rel = entry.local_audio(accent)
        if rel:
            path = self.audio.resolve(rel)
            if path.is_file():
                return path
        return None

    def ensure_audio(self, entry: WordEntry, accents: tuple[str, ...] = ("uk", "us"),
                     on_progress: Callable[[int, str], None] | None = None) -> dict[str, str]:
        entry.audio_files = self.audio.ensure(entry, self.client, accents,
                                              on_progress=on_progress)
        return entry.audio_files

    # ------------------------------------------------------------------ 状态
    def status(self) -> str:
        return (
            f"单词本 {self.wordbook.describe()}；"
            f"{self.cache.describe()}；"
            f"发音 {self.audio.describe()}；"
            f"{self.offline.describe()}"
        )

    def clear_cache(self) -> int:
        return self.cache.clear()

    def export_wordbook(self, path: str | Path) -> Path:
        return self.wordbook.export_to(path)

    def import_wordbook(self, path: str | Path, *, merge: bool = True) -> int:
        return self.wordbook.import_from(path, merge=merge)

    # ------------------------------------------------------------------ 收尾
    def close(self) -> None:
        """放掉网络连接与本地词库的 sqlite 句柄（退出/换数据目录时调用）。"""
        try:
            self.client.close()
        except Exception:  # noqa: BLE001 - 关闭失败不该影响退出
            pass
        self.offline.close()

    def __enter__(self) -> "WordService":
        return self

    def __exit__(self, *_exc) -> bool:
        self.close()
        return False


__all__ = ["LookupResult", "WordService"]
