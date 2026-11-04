"""单词本与查询缓存的持久化。

**两个文件、两套 schema、互不干扰**：

* ``lab/_data/wordbook.json`` —— 用户收藏的单词（发音/音标/释义/例句都在这儿）；
* ``lab/_data/cache/queries.json`` —— 查询缓存（只存解析后的扁平模型，
  不缓存 52KB 原始响应包），容量上限 + LRU 淘汰 + TTL 过期。

为什么不塞进主程序的 ``data.json``：将来合并时只要搬文件 + 迁移版本号，
主程序永远不会因为「读不懂生词本」而清空用户收藏。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterable

from ..common import paths
from ..common.storage import JsonStore, VersionTooNewError
from .models import SCHEMA, WordEntry

#: 查询缓存的默认容量与有效期
DEFAULT_CAPACITY = 5000
DEFAULT_TTL_DAYS = 30


def _now() -> int:
    return int(time.time())


class WordbookStore:
    """本地单词本（JSON，原子写 + 版本保护）。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else paths.data_file("wordbook.json")
        self.store = JsonStore(
            self.path,
            schema=SCHEMA,
            default={"schema": SCHEMA, "updated_at": 0, "entries": []},
            label="单词本",
        )
        self.data: dict = self.store.load()
        if not isinstance(self.data.get("entries"), list):
            self.data["entries"] = []

    # ------------------------------------------------------------------ 基础
    @property
    def read_only(self) -> bool:
        return bool(self.store.read_only)

    @property
    def last_error(self) -> str | None:
        return self.store.last_error

    def _raw_entries(self) -> list[dict]:
        """返回**文件里那个列表本身**（就地清理脏项）。

        注意：不能返回列表推导式的结果 —— 调用方会往里 ``append``，
        那样写进的是副本，文件永远不更新（这个坑踩过一次）。
        """
        items = self.data.get("entries")
        if not isinstance(items, list):
            items = []
            self.data["entries"] = items
        if any(not isinstance(x, dict) for x in items):
            items[:] = [x for x in items if isinstance(x, dict)]
        return items

    def save(self) -> None:
        if self.read_only:
            return
        self.data["schema"] = SCHEMA
        self.data["updated_at"] = _now()
        self.store.save(self.data)

    def reload(self) -> None:
        self.data = self.store.load()
        if not isinstance(self.data.get("entries"), list):
            self.data["entries"] = []

    # ------------------------------------------------------------------ 查询
    def entries(self) -> list[WordEntry]:
        return [WordEntry.from_dict(x) for x in self._raw_entries()]

    def count(self) -> int:
        return len(self._raw_entries())

    def has(self, norm: str) -> bool:
        key = (norm or "").strip().lower()
        return any(str(x.get("norm", "")).lower() == key for x in self._raw_entries())

    def get(self, norm: str) -> WordEntry | None:
        key = (norm or "").strip().lower()
        for item in self._raw_entries():
            if str(item.get("norm", "")).lower() == key:
                return WordEntry.from_dict(item)
        return None

    def search(self, keyword: str) -> list[WordEntry]:
        """按词形/释义/例句模糊搜索（界面上的搜索框用）。"""
        key = (keyword or "").strip().lower()
        if not key:
            return self.entries()
        out: list[WordEntry] = []
        for entry in self.entries():
            haystack = [entry.word, entry.norm]
            haystack += [s.label() for s in entry.trans]
            haystack += [s.en for s in entry.sents[:3]]
            haystack += [entry.note, " ".join(entry.tags)]
            if any(key in str(h).lower() for h in haystack if h):
                out.append(entry)
        return out

    # ------------------------------------------------------------------ 写入
    def add(self, entry: WordEntry, *, replace: bool = True) -> bool:
        """加入单词本；返回 ``True`` 表示这是新词。

        ``replace=True`` 时已存在的词会被新词条覆盖（音标/释义/例句可能变多了），
        但保留用户自己写的笔记。
        """
        if self.read_only:
            return False
        key = (entry.norm or entry.word or "").strip().lower()
        if not key:
            return False
        items = self._raw_entries()
        payload = entry.to_dict()
        for index, item in enumerate(items):
            if str(item.get("norm", "")).lower() == key:
                if not replace:
                    return False
                if item.get("note"):
                    payload["note"] = item["note"]
                # 已缓存的本地发音路径要保留，别因为重新查询把 mp3 记录抹掉
                merged_audio = dict(item.get("audio") or {})
                merged_audio.update(payload.get("audio") or {})
                if merged_audio:
                    payload["audio"] = merged_audio
                items[index] = payload
                self.save()
                return False
        items.append(payload)
        self.save()
        return True

    def remove(self, norm: str) -> bool:
        if self.read_only:
            return False
        key = (norm or "").strip().lower()
        items = self._raw_entries()
        kept = [x for x in items if str(x.get("norm", "")).lower() != key]
        if len(kept) == len(items):
            return False
        self.data["entries"] = kept
        self.save()
        return True

    def update_fields(self, norm: str, **changes: Any) -> bool:
        """改笔记 / 优先级 / 本地发音路径等单个字段。"""
        if self.read_only:
            return False
        key = (norm or "").strip().lower()
        for item in self._raw_entries():
            if str(item.get("norm", "")).lower() == key:
                for field, value in changes.items():
                    if value is None:
                        item.pop(field, None)
                    else:
                        item[field] = value
                self.save()
                return True
        return False

    def set_note(self, norm: str, note: str) -> bool:
        return self.update_fields(norm, note=note)

    def set_priority(self, norm: str, priority: int) -> bool:
        return self.update_fields(norm, priority=int(priority))

    def clear(self) -> int:
        if self.read_only:
            return 0
        count = self.count()
        self.data["entries"] = []
        self.save()
        return count

    # ------------------------------------------------------------------ 导入导出
    def export_to(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        from ..common.storage import write_json

        write_json(
            target,
            {"schema": SCHEMA, "updated_at": _now(), "entries": self._raw_entries()},
        )
        return target

    def import_from(self, path: str | Path, *, merge: bool = True) -> int:
        """导入另一个单词本文件，返回导入条数。"""
        from ..common.storage import read_json

        raw, err = read_json(Path(path), None)
        if err or not isinstance(raw, dict):
            return 0
        items = [x for x in (raw.get("entries") or []) if isinstance(x, dict)]
        if not items:
            return 0
        if not merge:
            self.data["entries"] = []
        added = 0
        for item in items:
            entry = WordEntry.from_dict(item)
            if self.add(entry):
                added += 1
        return added

    def describe(self) -> str:
        note = ""
        if self.read_only:
            note = "（只读：文件版本比程序新）"
        elif self.last_error:
            note = f"（{self.last_error}）"
        return f"{self.count()} 个单词{note}"


class QueryCache:
    """查询缓存：容量上限 + LRU + TTL。"""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        capacity: int = DEFAULT_CAPACITY,
        ttl_days: int = DEFAULT_TTL_DAYS,
    ) -> None:
        self.path = Path(path) if path else paths.cache_file("queries.json")
        self.capacity = max(100, int(capacity))
        self.ttl = max(0, int(ttl_days)) * 86400
        self.store = JsonStore(
            self.path,
            schema=SCHEMA,
            default={"schema": SCHEMA, "updated_at": 0, "entries": {}},
            label="查询缓存",
        )
        self.data: dict = self.store.load()
        if not isinstance(self.data.get("entries"), dict):
            self.data["entries"] = {}
        self.hits = 0
        self.misses = 0

    # ------------------------------------------------------------------ 读写
    def get(self, norm: str) -> WordEntry | None:
        key = (norm or "").strip().lower()
        if not key:
            return None
        item = self.data["entries"].get(key)
        if not isinstance(item, dict):
            self.misses += 1
            return None
        fetched = int(item.get("fetched_at", 0) or 0)
        if self.ttl and fetched and (_now() - fetched) > self.ttl:
            self.data["entries"].pop(key, None)
            self.misses += 1
            return None
        self.hits += 1
        # LRU：命中就刷新时间戳会让「重新查询」失去意义，
        # 这里只记录访问次数，淘汰仍按 fetched_at（避免老词条永远不过期）
        item["seen"] = int(item.get("seen", 0) or 0) + 1
        return WordEntry.from_dict(item)

    def put(self, entry: WordEntry, *, key: str | None = None) -> None:
        """写入缓存。``key`` 可显式指定（多语种查询要带语言后缀，
        否则「bonjour 的法汉结果」会被「bonjour 的英汉查询」命中）。"""
        key = ((key if key is not None else (entry.norm or entry.word)) or "").strip().lower()
        if not key:
            return
        if not entry.fetched_at:
            entry.fetched_at = _now()
        self.data["entries"][key] = entry.to_dict()
        self.prune()

    def prune(self, *, force_save: bool = False) -> int:
        """清理过期条目 + 超容量时按时间淘汰最旧的。"""
        entries: dict[str, Any] = self.data["entries"]
        removed = 0
        if self.ttl:
            now = _now()
            for key in [k for k, v in entries.items() if isinstance(v, dict) and (now - int(v.get("fetched_at", 0) or 0)) > self.ttl]:
                entries.pop(key, None)
                removed += 1
        if len(entries) > self.capacity:
            ordered = sorted(
                entries.items(),
                key=lambda kv: int((kv[1] or {}).get("fetched_at", 0) or 0),
            )
            for key, _ in ordered[: len(entries) - self.capacity]:
                entries.pop(key, None)
                removed += 1
        if removed or force_save:
            self.save()
        return removed

    def save(self) -> None:
        if self.store.read_only:
            return
        self.data["schema"] = SCHEMA
        self.data["updated_at"] = _now()
        self.store.save(self.data)

    def clear(self) -> int:
        if self.store.read_only:
            return 0
        count = len(self.data.get("entries") or {})
        self.data["entries"] = {}
        self.save()
        return count

    # ------------------------------------------------------------------ 统计
    @property
    def read_only(self) -> bool:
        return bool(self.store.read_only)

    @property
    def last_error(self) -> str | None:
        return self.store.last_error

    def count(self) -> int:
        return len(self.data.get("entries") or {})

    def stats(self) -> dict:
        return {"count": self.count(), "capacity": self.capacity, "hits": self.hits, "misses": self.misses}

    def describe(self) -> str:
        note = "（只读）" if self.read_only else ""
        return f"缓存 {self.count()}/{self.capacity} 条{note}"


def sort_entries(entries: Iterable[WordEntry], key: str = "time") -> list[WordEntry]:
    """列表排序：``time``（最近查询）/ ``alpha``（字母）/ ``added``。"""
    items = list(entries)
    if key == "alpha":
        return sorted(items, key=lambda e: (e.norm or e.word).lower())
    return sorted(items, key=lambda e: e.fetched_at, reverse=True)


__all__ = [
    "DEFAULT_CAPACITY",
    "DEFAULT_TTL_DAYS",
    "QueryCache",
    "VersionTooNewError",
    "WordbookStore",
    "sort_entries",
]
