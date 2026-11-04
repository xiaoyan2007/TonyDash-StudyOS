"""离线词库兜底（可选，放文件就生效，不放也不影响）。

主程序是纯本地应用，用户可能在没有网络的环境里查词。这里支持两种本地词库：

* ``lab/_data/ecdict.db`` —— SQLite（**推荐**，查询瞬发）。
  ECDICT 官方提供了一个可直接用的 ``stardict.db``，表名 ``stardict``，
  字段 ``word / phonetic / definition / translation / pos / collins / oxford /
  tag / bnc / frq / exchange``；
* ``lab/_data/ecdict.csv`` —— 官方 CSV（76 万词条）。逐行扫一遍要 1~2 秒，
  所以只做兜底，命中结果会进内存小缓存。

**不自动下载**：ECDICT 完整包几十 MB，静默下载既慢又占空间；
需要离线能力时由用户把文件放进 ``lab/_data/``，界面上会显示「本地词库已就绪」。
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any

from ..common import paths
from .models import Sentence, Sense, WordEntry

#: exchange 码位 → 中文说明（对齐 ECDICT 的约定）
EXCHANGE_LABELS = {
    "p": "过去式",
    "d": "过去分词",
    "i": "现在分词",
    "3": "第三人称单数",
    "r": "比较级",
    "t": "最高级",
    "s": "复数",
    "0": "原形",
    "1": "原形变换",
}
#: 查词时值得顺带显示的词形
EXCHANGE_DISPLAY = ("p", "d", "i", "3", "s", "r", "t")


def parse_exchange(text: str) -> tuple[dict[str, str], str]:
    """解析 ECDICT 的 ``exchange`` 字段。

    返回 ``(词形变化, 原形)``。格式形如
    ``p:perceived/d:perceived/3:perceives/i:perceiving``。
    """
    forms: dict[str, str] = {}
    lemma = ""
    for chunk in str(text or "").split("/"):
        if ":" not in chunk:
            continue
        code, _, value = chunk.partition(":")
        code = code.strip()
        value = value.strip()
        if not value:
            continue
        if code == "0":
            lemma = value
        elif code in EXCHANGE_LABELS and code in EXCHANGE_DISPLAY:
            forms[EXCHANGE_LABELS[code]] = value
    return forms, lemma


def _lines(text: str) -> list[str]:
    return [line.strip() for line in str(text or "").replace("\\n", "\n").split("\n") if line.strip()]


class OfflineDict:
    """本地词库（SQLite 优先，CSV 兜底）。"""

    def __init__(self, root: str | Path | None = None) -> None:
        base = Path(root) if root else paths.DATA_DIR
        self.db_path = base / "ecdict.db"
        self.csv_path = base / "ecdict.csv"
        self._conn: sqlite3.Connection | None = None
        self._csv_cache: dict[str, WordEntry | None] = {}

    # ------------------------------------------------------------------ 可用性
    @property
    def kind(self) -> str:
        """``"sqlite"`` / ``"csv"`` / ``""``（没有本地词库）。"""
        if self.db_path.is_file():
            return "sqlite"
        if self.csv_path.is_file():
            return "csv"
        return ""

    def available(self) -> bool:
        return bool(self.kind)

    def describe(self) -> str:
        kind = self.kind
        if not kind:
            return "未安装本地词库（把 ECDICT 的 ecdict.db 或 ecdict.csv 放进 lab/_data/ 即可离线查词）"
        name = "SQLite" if kind == "sqlite" else "CSV"
        return f"本地词库已就绪（{name}）"

    # ------------------------------------------------------------------ 查询
    def lookup(self, word: str) -> WordEntry | None:
        """查本地词库；先按原词查，再按「词形变化 → 原形」反查。"""
        norm = (word or "").strip()
        if not norm:
            return None
        kind = self.kind
        if not kind:
            return None
        key = norm.lower()
        if kind == "csv" and key in self._csv_cache:
            return self._csv_cache[key]
        row = self._row(norm) if kind == "sqlite" else self._csv_row(norm)
        if row is None:
            row = self._lemma_row(norm, kind)
        entry = self._entry_from_row(row, norm) if row else None
        if kind == "csv":
            # CSV 是逐行扫描（1~2 秒），必须缓存；只留最近 200 条免得吃内存
            if len(self._csv_cache) > 200:
                self._csv_cache.clear()
            self._csv_cache[key] = entry
        return entry

    def _row(self, word: str) -> dict[str, Any] | None:
        try:
            if self._conn is None:
                self._conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
                self._conn.row_factory = sqlite3.Row
            cur = self._conn.execute(
                "SELECT word, phonetic, definition, translation, pos, tag, exchange "
                "FROM stardict WHERE word = ? COLLATE NOCASE LIMIT 1",
                (word,),
            )
            row = cur.fetchone()
        except sqlite3.Error:
            return None
        return dict(row) if row is not None else None

    def _lemma_row(self, word: str, kind: str) -> dict[str, Any] | None:
        """按 ``exchange`` 里的原形反查（``running`` → ``run``）。"""
        if kind == "sqlite":
            try:
                if self._conn is None:
                    self._conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
                    self._conn.row_factory = sqlite3.Row
                cur = self._conn.execute(
                    "SELECT word, phonetic, definition, translation, pos, tag, exchange "
                    "FROM stardict WHERE exchange LIKE ? LIMIT 1",
                    (f"%:{word.lower()}/%",),
                )
                row = cur.fetchone()
                return dict(row) if row is not None else None
            except sqlite3.Error:
                return None
        return None

    def _csv_row(self, word: str) -> dict[str, Any] | None:
        """官方 CSV 逐行扫（只用于兜底，命中结果由 :meth:`lookup` 缓存）。"""
        try:
            with self.csv_path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    if str(row.get("word", "")).strip().lower() == word.lower():
                        return row
        except (OSError, UnicodeDecodeError):
            return None
        return None

    def _entry_from_row(self, row: dict[str, Any], query: str) -> WordEntry:
        translation = _lines(row.get("translation", ""))
        definition = _lines(row.get("definition", ""))
        pos = str(row.get("pos", "") or "").strip()
        trans: list[Sense] = []
        for line in translation:
            head, _, rest = line.partition(". ")
            if rest and len(head) <= 8 and head.isascii():
                trans.append(Sense(pos=head + ".", definition=rest.strip()))
            else:
                trans.append(Sense(pos=pos, definition=line))
        if not trans:
            trans = [Sense(pos=pos, definition=d) for d in definition[:4]]
        forms, lemma = parse_exchange(str(row.get("exchange", "")))
        entry = WordEntry(
            word=str(row.get("word") or query),
            norm=(str(row.get("word") or query)).lower(),
            lang="en",
            phonetic_uk=str(row.get("phonetic", "") or ""),
            trans=trans,
            forms=forms,
            offline=True,
            src="ecdict",
            note="当前未联网，以上释义来自本地词库。",
        )
        if lemma and lemma.lower() != entry.norm:
            entry.note = f"当前未联网，以上释义来自本地词库（原形 {lemma}）。"
        tag = str(row.get("tag", "") or "").strip()
        if tag:
            entry.tags = [t for t in tag.split() if t]
        if definition and not translation:
            entry.sents = [Sentence(en=d, zh="", source="ECDICT 英英释义") for d in definition[:3]]
        return entry

    def __enter__(self) -> "OfflineDict":
        return self

    def __exit__(self, *_exc) -> bool:
        self.close()
        return False

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None
