"""词典查询页：输入单词 → 一键查有道 → 收藏到本地单词本（连发音一起存）。

界面结构（从上到下）：

1. 查询卡：搜索框 + 查词/清空按钮 + 状态行（数据源、缓存、耗时、错误）
2. 结果卡：:class:`EntryView`（音标 / 释义 / 词形 / 例句 / 短语 / 标签）
3. 未收录时：显示联想词（可点击直查）

联网与下载都在后台线程，界面不卡（``LookupWorker`` / ``SaveWorker``）。
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ..wordbook import api as wapi
from .entry_view import EntryView
from .kit import Kit
from .media import AudioPlayback, LookupWorker, SaveWorker


class WordPage(QWidget):
    """词典查询页。"""

    def __init__(self, service, parent=None, kit: Kit | None = None):
        super().__init__(parent)
        self.kit = kit or Kit()
        self.theme = self.kit.theme
        self.service = service
        self.audio = AudioPlayback(service, self)
        self.result = None
        self._worker = None
        self._save_worker = None
        self._build()
        self._refresh_chips()

    # ------------------------------------------------------------------ 建界面
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        root.addWidget(self._build_search_card())
        root.addWidget(self._build_result_card(), 1)

    def _build_search_card(self) -> QWidget:
        card = self.kit.card(self)
        lay = self.kit.card_layout(card, margins=(16, 14, 16, 12), spacing=10)

        head = QWidget()
        head_lay = QHBoxLayout(head)
        head_lay.setContentsMargins(0, 0, 0, 0)
        head_lay.setSpacing(8)
        head_lay.addWidget(self.kit.title("词典查询", 15))
        head_lay.addStretch(1)
        self._source_row = QHBoxLayout()
        self._source_row.setContentsMargins(0, 0, 0, 0)
        self._source_row.setSpacing(6)
        head_lay.addLayout(self._source_row)
        lay.addWidget(head)

        self.search = self.kit.search_box("输入单词或短语，回车查询（例如 hello / take off）", card)
        self.search.returnPressed.connect(self.query)
        self.btn_query = self.kit.button("查词", "search", "primary", "md", card)
        self.btn_query.clicked.connect(self.query)
        self.btn_clear = self.kit.button("清空", "clear", "ghost", "md", card)
        self.btn_clear.clicked.connect(self.clear)
        lay.addWidget(Kit.row(self.search, self.btn_query, self.btn_clear, None))

        self.status = self.kit.text("", 11.5, self.theme.C_MUTED, wrap=True)
        lay.addWidget(self.status)
        return card

    def _build_result_card(self) -> QWidget:
        card = self.kit.card(self)
        lay = self.kit.card_layout(card, margins=(16, 14, 16, 14), spacing=8)

        scroll = QScrollArea(card)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")

        holder = QWidget()
        holder.setStyleSheet("background:transparent;")
        holder_lay = QVBoxLayout(holder)
        holder_lay.setContentsMargins(0, 0, 6, 0)
        holder_lay.setSpacing(10)

        self.view = EntryView(self.kit, holder)
        self.view.playRequested.connect(self._play)
        self.view.saveRequested.connect(self.save)
        self.view.removeRequested.connect(self.remove)
        self.view.suggestClicked.connect(self.lookup_word)
        self.view.sentencePlayRequested.connect(self.audio.play_sentence)
        holder_lay.addWidget(self.view)

        self.empty = self.kit.empty_state(
            "search",
            "还没有查询结果",
            "输入单词或短语后回车。\n\n收藏时会自动把音标、释义、例句和发音一起存到本地，离线也能看。",
            holder,
        )
        holder_lay.addWidget(self.empty)
        holder_lay.addStretch(1)

        scroll.setWidget(holder)
        lay.addWidget(scroll, 1)
        self.audio.failed.connect(lambda msg: self._set_status(msg, warn=True))
        return card

    # ------------------------------------------------------------------ 状态
    def _refresh_chips(self) -> None:
        row = self._source_row
        while row.count():
            item = row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        row.addWidget(self.kit.chip("有道词典", "blue", "search"))
        offline = getattr(self.service, "offline", None)
        if offline is not None and offline.available():
            row.addWidget(self.kit.chip(f"本地词库 {offline.kind.upper()}", "green", "download"))
        else:
            row.addWidget(self.kit.chip("未装本地词库", "neutral", "info"))
        if not self.audio.player.available():
            row.addWidget(self.kit.chip("发音不可用", "amber", "warning"))

    def _set_status(self, text: str, *, warn: bool = False) -> None:
        self.status.setText(text)
        color = self.theme.C_RED if warn else self.theme.C_MUTED
        self.status.setStyleSheet(f"color:{color};background:transparent;")

    def _busy(self, on: bool) -> None:
        self.btn_query.setEnabled(not on)
        self.search.setEnabled(not on)
        if on:
            self.btn_query.setText("查询中…")
        else:
            self.btn_query.setText("查词")

    # ------------------------------------------------------------------ 行为
    def lookup_word(self, word: str) -> None:
        self.search.setText(word)
        self.query()

    def query(self) -> None:
        query = self.search.text().strip()
        if not query:
            self._set_status("请输入要查询的单词或短语", warn=True)
            return
        if self._worker is not None and self._worker.isRunning():
            return
        self._busy(True)
        self._set_status(f"正在查询「{query}」…")
        worker = LookupWorker(self.service, query, parent=self)
        worker.done.connect(self._on_result)
        worker.finished.connect(lambda w=worker: self._busy(False))
        self._worker = worker
        worker.start()

    def _on_result(self, result) -> None:
        self.result = result
        entry = result.entry
        self.empty.setVisible(not (entry and entry.found))
        saved = bool(entry and entry.found and self.service.is_saved(entry.norm))
        self.view.set_entry(entry, saved=saved)
        if not result.ok:
            self._set_status(result.error or "查询失败", warn=True)
            return
        if not result.found:
            self._set_status(f"未收录「{entry.word}」" + ("，可试试下面的联想词" if result.suggestions else ""),
                             warn=True)
            return
        self._set_status(
            f"{result.describe()}；释义 {len(entry.trans)} 条，例句 {len(entry.sents)} 条"
            + ("；已在单词本" if saved else "")
        )

    def save(self) -> None:
        entry = getattr(self.view, "entry", None)
        if entry is None or not entry.found:
            return
        if self._save_worker is not None and self._save_worker.isRunning():
            return
        self._set_status("正在收藏（顺带把发音存到本地）…")
        worker = SaveWorker(self.service, entry, want_audio=True, parent=self)
        worker.done.connect(self._on_saved)
        self._save_worker = worker
        worker.start()

    def _on_saved(self, is_new: bool, message: str) -> None:
        entry = getattr(self.view, "entry", None)
        saved = bool(entry is not None and self.service.is_saved(entry.norm))
        if entry is not None:
            self.view.set_entry(entry, saved=saved)
        if saved:
            self._set_status(message or ("已加入单词本" if is_new else "已更新单词本里的词条"))
        else:
            self._set_status(message or "收藏失败", warn=True)

    def remove(self) -> None:
        entry = getattr(self.view, "entry", None)
        if entry is None:
            return
        self.service.remove(entry.norm)
        self.view.set_entry(entry, saved=False)
        self._set_status(f"已从单词本移除「{entry.norm}」")

    def _play(self, accent: str) -> None:
        entry = getattr(self.view, "entry", None)
        if entry is None:
            return
        self.audio.play(entry, accent)

    def clear(self) -> None:
        self.search.clear()
        self.view.clear()
        self.empty.setVisible(True)
        self._set_status("已清空")

    # ------------------------------------------------------------------ 演示
    def load_demo(self) -> None:
        """离屏自检用：渲染一个**完整**词条，不联网。

        特意读 ``lab/tests/data/youdao_hello.json``（从真实 jsonapi 响应裁剪而来）：
        自检要能看到音标、词性、词形、例句的真实排版；只画一个「未收录」的占位词条
        看不出释义串行、例句丢失这类问题。
        """
        from ..wordbook import parser as P

        fixture = Path(__file__).resolve().parents[2] / "tests" / "data" / "youdao_hello.json"
        entry = None
        if fixture.exists():
            try:
                raw = json.loads(fixture.read_text(encoding="utf-8"))
                entry = P.parse_entry(raw, query=str(raw.get("input") or "hello"))
            except Exception as exc:  # noqa: BLE001 - 演示失败就退回占位词条
                print(f"[demo] 测试夹具解析失败：{type(exc).__name__}: {exc}")
        if entry is None or not entry.found:
            entry = P.make_missing("hello", ["hello"])
            self._set_status("演示：没有找到测试夹具，显示未收录占位词条")
        else:
            entry.note = "演示数据（离线读取测试夹具，不发网络请求）"
            self._set_status(
                f"演示：{entry.word}　音标 {entry.phonetic_line() or '无'}　"
                f"释义 {len(entry.trans)} 条　例句 {len(entry.sents)} 条　词形 {len(entry.forms)} 条"
            )
        self.empty.setVisible(False)
        self.view.set_entry(entry, saved=self.service.is_saved(entry.norm))


__all__ = ["WordPage"]
