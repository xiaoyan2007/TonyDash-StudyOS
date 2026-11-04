"""词典查询页：两个选项卡 —— 查单词 / 翻译。

界面结构
--------
1. 顶部分段控件切「查单词」与「翻译」，右侧是语言下拉框；
2. 查单词：搜索框 + 查词/清空 + 状态行 + 百分比进度条，
   结果区复用 :class:`EntryView`（音标 / 释义 / 词形 / 例句 / 短语 / 标签）；
3. 翻译：目标语言下拉框 + 多行输入 + 翻译/清空/复制 + 译文区。

联网与下载都在后台线程（``LookupWorker`` / ``SaveWorker`` / ``TranslateWorker``），
界面不卡；所有颜色按当前主题取，切主题后调 :meth:`sync_theme` 就地重刷。
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QHBoxLayout, QProgressBar, QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget,
)

from ..wordbook import api as wapi
from ..wordbook import translate as T
from .entry_view import EntryView
from .kit import Kit
from .media import AudioPlayback, LookupWorker, SaveWorker, TranslateWorker

__all__ = ["WordPage"]

TAB_WORD = "word"
TAB_TRANSLATE = "translate"


class WordPage(QWidget):
    """词典查询页：查单词 / 翻译 两个选项卡。"""

    def __init__(self, service, parent=None, kit: Kit | None = None):
        super().__init__(parent)
        self.kit = kit or Kit()
        self.theme = self.kit.theme
        self.service = service
        self.audio = AudioPlayback(service, self)
        self.result = None
        self._worker = None
        self._save_worker = None
        self._trans_worker = None
        self._tab = TAB_WORD
        self._language = "auto"
        self._build()
        self._refresh_source_row()
        self.sync_theme()

    # ------------------------------------------------------------------ 建界面
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        root.addWidget(self._build_tab_card())
        root.addWidget(self._build_word_card())
        root.addWidget(self._build_result_card(), 1)
        root.addWidget(self._build_translate_card(), 1)
        self._switch_tab(TAB_WORD)

    def _build_tab_card(self) -> QWidget:
        card = self.kit.card(self)
        lay = self.kit.card_layout(card, margins=(16, 10, 16, 10), spacing=8)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.tabs = self.kit.segmented(
            [("word", "查单词"), ("translate", "翻译")], "word")
        self.tabs.changed.connect(self._switch_tab)
        row.addWidget(self.tabs, 1)
        row.addWidget(self.kit.text("语言", 11.5, self.theme.C_SUB))
        self.lang_select = self.kit.select(card)
        self.lang_select.setFixedWidth(132)
        for code, name, _trans in T.LANGUAGES:
            self.lang_select.addItem(name, code)
        self.lang_select.setCurrentIndex(0)
        self.lang_select.currentIndexChanged.connect(self._on_language)
        self.lang_select.setToolTip("选择词典 / 翻译的源语言（自动检测 = 交给有道判断）")
        row.addWidget(self.lang_select)
        lay.addLayout(row)
        return card

    def _build_word_card(self) -> QWidget:
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

        self.search = self.kit.search_box(
            "输入单词或短语，回车查询（例如 hello / take off）", card)
        self.search.returnPressed.connect(self.query)
        self.btn_query = self.kit.button("查词", "search", "primary", "md", card)
        self.btn_query.clicked.connect(self.query)
        self.btn_clear = self.kit.button("清空", "clear", "ghost", "md", card)
        self.btn_clear.clicked.connect(self.clear)
        lay.addWidget(Kit.row(self.search, self.btn_query, self.btn_clear, None))

        self.status = self.kit.text("", 11.5, self.theme.C_MUTED, wrap=True)
        lay.addWidget(self.status)

        bar_row = QHBoxLayout()
        bar_row.setContentsMargins(0, 0, 0, 0)
        bar_row.setSpacing(8)
        self.progress_bar = QProgressBar(card)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setVisible(False)
        self.progress_label = self.kit.text("", 10.5, self.theme.C_SUB)
        self.progress_label.setVisible(False)
        bar_row.addWidget(self.progress_bar, 1)
        bar_row.addWidget(self.progress_label)
        lay.addLayout(bar_row)
        self.word_card = card
        return card

    def _build_result_card(self) -> QWidget:
        card = self.kit.card(self)
        lay = self.kit.card_layout(card, margins=(16, 14, 16, 14), spacing=8)

        scroll = QScrollArea(card)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

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
        self.result_card = card
        return card

    def _build_translate_card(self) -> QWidget:
        card = self.kit.card(self)
        lay = self.kit.card_layout(card, margins=(16, 14, 16, 14), spacing=10)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        head.addWidget(self.kit.title("翻译", 15))
        head.addStretch(1)
        head.addWidget(self.kit.text("译为", 11.5, self.theme.C_SUB))
        self.to_select = self.kit.select(card)
        self.to_select.setFixedWidth(132)
        for code, name, _trans in T.LANGUAGES:
            if code == "auto":
                continue
            self.to_select.addItem(name, code)
        index = self.to_select.findData("zh")
        self.to_select.setCurrentIndex(index if index >= 0 else 0)
        self.to_select.setToolTip("目标语言")
        head.addWidget(self.to_select)
        lay.addLayout(head)

        self.trans_input = QPlainTextEdit(card)
        self.trans_input.setPlaceholderText(
            "粘贴或输入要翻译的内容，支持多语言"
            "（中 / 英 / 法 / 日 / 韩 / 西 / 德 / 意 / 葡 / 俄）")
        self.trans_input.setMinimumHeight(110)
        lay.addWidget(self.trans_input)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)
        self.btn_translate = self.kit.button("翻译", "search", "primary", "md", card)
        self.btn_translate.clicked.connect(self.do_translate)
        self.btn_trans_clear = self.kit.button("清空", "clear", "ghost", "md", card)
        self.btn_trans_clear.clicked.connect(self.clear_translate)
        self.btn_trans_copy = self.kit.button("复制译文", "copy", "ghost", "md", card)
        self.btn_trans_copy.clicked.connect(self.copy_translation)
        btn_row.addWidget(self.btn_translate)
        btn_row.addWidget(self.btn_trans_clear)
        btn_row.addWidget(self.btn_trans_copy)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.trans_status = self.kit.text("", 11.5, self.theme.C_MUTED, wrap=True)
        lay.addWidget(self.trans_status)

        tbar = QHBoxLayout()
        tbar.setContentsMargins(0, 0, 0, 0)
        tbar.setSpacing(8)
        self.trans_progress = QProgressBar(card)
        self.trans_progress.setRange(0, 100)
        self.trans_progress.setTextVisible(False)
        self.trans_progress.setFixedHeight(8)
        self.trans_progress.setVisible(False)
        self.trans_label = self.kit.text("", 10.5, self.theme.C_SUB)
        self.trans_label.setVisible(False)
        tbar.addWidget(self.trans_progress, 1)
        tbar.addWidget(self.trans_label)
        lay.addLayout(tbar)

        self.trans_out = QPlainTextEdit(card)
        self.trans_out.setReadOnly(True)
        self.trans_out.setPlaceholderText("译文会显示在这里")
        self.trans_out.setMinimumHeight(120)
        lay.addWidget(self.trans_out, 1)
        self.translate_card = card
        return card

    # ------------------------------------------------------------------ 选项卡
    def _switch_tab(self, key: str) -> None:
        key = key if key in (TAB_WORD, TAB_TRANSLATE) else TAB_WORD
        self._tab = key
        is_word = key == TAB_WORD
        self.word_card.setVisible(is_word)
        self.result_card.setVisible(is_word)
        self.translate_card.setVisible(not is_word)
        if hasattr(self, "tabs"):
            self.tabs.set_current(key, emit=False)

    def current_tab(self) -> str:
        return self._tab

    def _on_language(self, _index: int) -> None:
        self._language = str(self.lang_select.currentData() or "auto")

    def current_language(self) -> str:
        return self._language

    def target_language(self) -> str:
        return str(self.to_select.currentData() or "zh")

    # ------------------------------------------------------------------ 主题
    def sync_theme(self) -> None:
        """切主题后重刷所有写死过颜色的控件（进度条 / 多行框 / 文本 / 标签）。"""
        self.theme = self.kit.theme
        self._style_progress(self.progress_bar)
        self._style_progress(self.trans_progress)
        self._style_text_edit(self.trans_input)
        self._style_text_edit(self.trans_out)
        self._retint_labels()
        self._refresh_source_row()
        segmented = getattr(self.tabs, "sync_theme", None)
        if callable(segmented):
            segmented()
        entry = getattr(self.view, "entry", None)
        if entry is not None:
            saved = bool(entry.found and self.service.is_saved(entry.norm))
            self.view.set_entry(entry, saved=saved)

    def _style_progress(self, bar: QProgressBar) -> None:
        track = "rgba(255,255,255,30)" if self.theme.MODE == "dark" \
            else "rgba(255,255,255,170)"
        bar.setStyleSheet(
            f"QProgressBar{{background:{track};border:none;border-radius:4px;}}"
            f"QProgressBar::chunk{{background:{self.theme.C_BLUE};border-radius:4px;}}"
        )

    def _style_text_edit(self, edit: QPlainTextEdit) -> None:
        dark = self.theme.MODE == "dark"
        bg = "rgba(255,255,255,22)" if dark else "rgba(255,255,255,214)"
        border = "rgba(255,255,255,54)" if dark else "rgba(28,28,30,42)"
        focus = "rgba(255,255,255,36)" if dark else "rgba(255,255,255,242)"
        edit.setStyleSheet(
            f"QPlainTextEdit{{background:{bg};border:1px solid {border};"
            f"border-radius:10px;padding:8px 10px;color:{self.theme.C_TEXT};"
            f"selection-background-color:{self.theme.C_BLUE};selection-color:#FFFFFF;}}"
            f"QPlainTextEdit:focus{{border:1px solid {self.theme.C_BLUE};"
            f"background:{focus};}}"
        )

    def _retint_labels(self) -> None:
        for lab in (self.status, self.trans_status):
            lab.setStyleSheet(f"color:{self.theme.C_MUTED};background:transparent;")
        for lab in (self.progress_label, self.trans_label):
            lab.setStyleSheet(f"color:{self.theme.C_SUB};background:transparent;")

    def _refresh_source_row(self) -> None:
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

    # ------------------------------------------------------------------ 状态
    def _set_status(self, text: str, *, warn: bool = False) -> None:
        self.status.setText(text)
        color = self.theme.C_RED if warn else self.theme.C_MUTED
        self.status.setStyleSheet(f"color:{color};background:transparent;")

    def _set_trans_status(self, text: str, *, warn: bool = False) -> None:
        self.trans_status.setText(text)
        color = self.theme.C_RED if warn else self.theme.C_MUTED
        self.trans_status.setStyleSheet(f"color:{color};background:transparent;")

    def _busy(self, on: bool) -> None:
        self.btn_query.setEnabled(not on)
        self.search.setEnabled(not on)
        self.btn_query.setText("查询中…" if on else "查词")

    def _show_progress(self, percent: int, text: str) -> None:
        pct = max(0, min(100, int(percent)))
        self.progress_bar.setValue(pct)
        self.progress_label.setText(f"{pct}%　{text}" if text else f"{pct}%")
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)

    def _hide_progress(self) -> None:
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)

    def _show_trans_progress(self, percent: int, text: str) -> None:
        pct = max(0, min(100, int(percent)))
        self.trans_progress.setValue(pct)
        self.trans_label.setText(f"{pct}%　{text}" if text else f"{pct}%")
        self.trans_progress.setVisible(True)
        self.trans_label.setVisible(True)

    def _hide_trans_progress(self) -> None:
        self.trans_progress.setVisible(False)
        self.trans_label.setVisible(False)

    # ------------------------------------------------------------------ 查词
    def lookup_word(self, word: str) -> None:
        self._switch_tab(TAB_WORD)
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
        lang = self._language
        self._set_status(f"正在查询「{query}」…（{T.lang_label(lang)}）")
        self._show_progress(0, "准备中…")
        worker = LookupWorker(self.service, query, lang=lang, parent=self)
        worker.progress.connect(self._show_progress)
        worker.done.connect(self._on_result)
        worker.finished.connect(lambda w=worker: self._busy(False))
        self._worker = worker
        worker.start()

    def _on_result(self, result) -> None:
        self._hide_progress()
        self.result = result
        entry = result.entry
        self.empty.setVisible(not (entry and entry.found))
        saved = bool(entry and entry.found and self.service.is_saved(entry.norm))
        self.view.set_entry(entry, saved=saved)
        if not result.ok:
            self._set_status(result.error or "查询失败", warn=True)
            return
        if not result.found:
            self._set_status(
                f"未收录「{entry.word}」"
                + ("，可试试下面的联想词" if result.suggestions else ""),
                warn=True)
            return
        self._set_status(
            f"{result.describe()}；释义 {len(entry.trans)} 条，例句 {len(entry.sents)} 条"
            + ("；已在单词本" if saved else ""))

    def save(self) -> None:
        entry = getattr(self.view, "entry", None)
        if entry is None or not entry.found:
            return
        if self._save_worker is not None and self._save_worker.isRunning():
            return
        self._set_status("正在收藏（顺带把发音存到本地）…")
        self._show_progress(0, "准备中…")
        worker = SaveWorker(self.service, entry, want_audio=True, parent=self)
        worker.progress.connect(self._show_progress)
        worker.done.connect(self._on_saved)
        self._save_worker = worker
        worker.start()

    def _on_saved(self, is_new: bool, message: str) -> None:
        self._hide_progress()
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
        self._hide_progress()
        self.search.clear()
        self.view.clear()
        self.empty.setVisible(True)
        self._set_status("已清空")

    # ------------------------------------------------------------------ 翻译
    def do_translate(self) -> None:
        text = self.trans_input.toPlainText().strip()
        if not text:
            self._set_trans_status("请输入要翻译的内容", warn=True)
            return
        if self._trans_worker is not None and self._trans_worker.isRunning():
            return
        source = self._language
        target = self.target_language()
        if source == target and source != "auto":
            self._set_trans_status("源语言与目标语言相同，换一个目标语言试试", warn=True)
            return
        self.btn_translate.setEnabled(False)
        self.btn_translate.setText("翻译中…")
        self._set_trans_status(
            f"正在翻译…（{T.lang_label(source)} → {T.lang_label(target)}）")
        self._show_trans_progress(0, "准备中…")
        worker = TranslateWorker(self.service.client, text, source=source,
                                 target=target, parent=self)
        worker.progress.connect(self._show_trans_progress)
        worker.done.connect(self._on_translated)
        worker.finished.connect(self._trans_done_ui)
        self._trans_worker = worker
        worker.start()

    def _trans_done_ui(self) -> None:
        self.btn_translate.setEnabled(True)
        self.btn_translate.setText("翻译")

    def _on_translated(self, result) -> None:
        self._hide_trans_progress()
        result = result if isinstance(result, dict) else {}
        if not result.get("ok"):
            self._set_trans_status(str(result.get("error") or "翻译失败"), warn=True)
            self.trans_out.clear()
            return
        self.trans_out.setPlainText(str(result.get("result") or ""))
        self._set_trans_status(
            f"翻译完成（{T.lang_label(result.get('source') or 'auto')} → "
            f"{T.lang_label(result.get('target') or 'zh')}）")

    def clear_translate(self) -> None:
        self._hide_trans_progress()
        self.trans_input.clear()
        self.trans_out.clear()
        self._set_trans_status("已清空")

    def copy_translation(self) -> None:
        from PySide6.QtWidgets import QApplication

        text = self.trans_out.toPlainText().strip()
        if not text:
            self._set_trans_status("还没有译文可复制", warn=True)
            return
        QApplication.clipboard().setText(text)
        self._set_trans_status("译文已复制到剪贴板")

    # ------------------------------------------------------------------ 演示
    def load_demo(self) -> None:
        """离屏自检用：渲染一个**完整**词条，不联网。"""
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
