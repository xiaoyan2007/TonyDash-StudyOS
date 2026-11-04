"""单词本页：本地收藏的单词，**离线可看可听**。

左边是列表（可搜索、可排序、可导出/导入），右边复用 :class:`EntryView` 显示详情 ——
释义、音标、例句和发音都在本地，断网照常使用。

导出格式就是 ``wordbook.json``（schema 带版本号），将来并进主程序时
``data.json`` 只存这个文件的路径指针，绝不动用户已收藏的生词。
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLineEdit, QScrollArea,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..common import paths
from ..wordbook import api as wapi
from .entry_view import EntryView
from .kit import Kit
from .media import AudioPlayback

COLUMNS = ("单词", "音标", "释义", "标签", "收藏时间")


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


class WordbookPage(QWidget):
    """本地单词本。"""

    def __init__(self, service, parent=None, kit: Kit | None = None):
        super().__init__(parent)
        self.kit = kit or Kit()
        self.theme = self.kit.theme
        self.service = service
        self.audio = AudioPlayback(service, self)
        self.entries: list = []
        self.current = None
        self._loading = False
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ 建界面
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_list_card())
        splitter.addWidget(self._build_detail_card())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([430, 560])
        root.addWidget(splitter)

    def _build_list_card(self) -> QWidget:
        card = self.kit.card(self)
        lay = self.kit.card_layout(card, margins=(16, 14, 16, 12), spacing=10)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        head.addWidget(self.kit.title("单词本", 15))
        head.addStretch(1)
        self.count_chip = self.kit.chip("0 词", "blue", "star")
        head.addWidget(self.count_chip)
        lay.addLayout(head)

        self.search = self.kit.search_box("搜索单词、释义、例句或备注", card)
        self.search.textChanged.connect(lambda _t: self.refresh())
        lay.addWidget(self.search)

        self.order = self.kit.select(card)
        self.order.addItems(["最近收藏", "字母 A→Z", "优先级"])
        self.order.currentIndexChanged.connect(lambda _i: self.refresh())
        self.btn_export = self.kit.button("导出", "download", "ghost", "sm", card)
        self.btn_export.clicked.connect(self.export)
        self.btn_import = self.kit.button("导入", "upload", "ghost", "sm", card)
        self.btn_import.clicked.connect(self.import_file)
        self.btn_refresh = self.kit.button("刷新", "refresh", "ghost", "sm", card)
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_clear = self.kit.button("清空", "delete", "ghost", "sm", card)
        self.btn_clear.clicked.connect(self.clear_all)
        lay.addWidget(Kit.row(self.order, self.btn_export, self.btn_import, self.btn_refresh,
                              self.btn_clear, None))

        self.table = QTableWidget(0, len(COLUMNS), card)
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setStyleSheet(self._table_qss())
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_select)
        lay.addWidget(self.table, 1)

        self.hint = self.kit.text(
            "单词本还是空的。\n\n去「词典查询」页查一个词，点「收藏到单词本」，"
            "音标、释义、例句和发音会一起存到本地。",
            11.5,
            self.theme.C_MUTED,
            wrap=True,
        )
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.hint)

        self.status = self.kit.text("", 11, self.theme.C_MUTED, wrap=True)
        lay.addWidget(self.status)
        return card

    def _table_qss(self) -> str:
        theme = self.theme
        return (
            "QTableWidget{background:transparent;border:none;}"
            f"QTableWidget::item{{padding:6px 4px;color:{theme.C_TEXT};}}"
            f"QTableWidget::item:selected{{background:rgba(10,132,255,30);color:{theme.C_TEXT};}}"
            f"QHeaderView::section{{background:transparent;border:none;color:{theme.C_MUTED};"
            "padding:6px 4px;font-weight:600;}"
        )

    def _build_detail_card(self) -> QWidget:
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
        self.view.removeRequested.connect(self.remove_current)
        self.view.sentencePlayRequested.connect(self.audio.play_sentence)
        holder_lay.addWidget(self.view)

        self.empty = self.kit.empty_state(
            "star", "选中左边的一个单词", "这里会显示它在本地保存的音标、释义和例句。", holder
        )
        holder_lay.addWidget(self.empty)
        holder_lay.addStretch(1)
        scroll.setWidget(holder)
        lay.addWidget(scroll, 1)

        note_row = QHBoxLayout()
        note_row.setContentsMargins(0, 0, 0, 0)
        note_row.setSpacing(8)
        self.note = QLineEdit(card)
        self.note.setPlaceholderText("给这个单词加一句备注（回车保存）")
        self.note.setFixedHeight(32)
        self.note.returnPressed.connect(self.save_note)
        self.note.setStyleSheet(
            f"QLineEdit{{border:1px solid {self.theme.C_BLUE};border-radius:8px;"
            f"padding:0 10px;color:{self.theme.C_TEXT};background:rgba(255,255,255,0.6);}}"
        )
        self.note.setEnabled(False)
        note_row.addWidget(self.note, 1)
        self.btn_note = self.kit.button("保存备注", "save", "soft", "md", card)
        self.btn_note.clicked.connect(self.save_note)
        self.btn_note.setEnabled(False)
        note_row.addWidget(self.btn_note)
        lay.addLayout(note_row)

        self.audio.failed.connect(lambda msg: self._set_status(msg, warn=True))
        return card

    # ------------------------------------------------------------------ 数据
    def _order_key(self) -> str:
        return {0: "time", 1: "alpha", 2: "priority"}.get(self.order.currentIndex(), "time")

    def refresh(self) -> None:
        keyword = self.search.text().strip()
        self.entries = (
            self.service.search_saved(keyword) if keyword else self.service.saved_entries(order=self._order_key())
        )
        self._loading = True
        self.table.setRowCount(len(self.entries))
        for row, entry in enumerate(self.entries):
            values = (
                entry.word or entry.norm,
                entry.phonetic_line() or "—",
                entry.summary(limit=2) or "—",
                "、".join(entry.tags[:2]) or "—",
                time.strftime("%Y-%m-%d", time.localtime(entry.fetched_at)) if entry.fetched_at else "—",
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col != 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                item.setToolTip(f"{entry.word}\n{entry.summary(limit=6)}")
                self.table.setItem(row, col, item)
        self._loading = False

        self.hint.setVisible(not self.entries)
        self.table.setVisible(bool(self.entries))
        self.count_chip.setText(f"{len(self.entries)} 词")
        self._set_status(self.service.status())

        if self.entries:
            keep = next((i for i, e in enumerate(self.entries) if e.norm == (self.current or "")), 0)
            self.table.selectRow(max(0, keep))
        else:
            self.current = None
            self.view.clear()
            self.empty.setVisible(True)
            self.note.clear()
            self.note.setEnabled(False)
            self.btn_note.setEnabled(False)

    def _on_select(self) -> None:
        if self._loading:
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self.entries):
            return
        entry = self.entries[row]
        self.current = entry.norm
        self.empty.setVisible(False)
        self.view.set_entry(entry, saved=True)
        self.note.setText(entry.note or "")
        self.note.setEnabled(True)
        self.btn_note.setEnabled(True)

    def _set_status(self, text: str, *, warn: bool = False) -> None:
        self.status.setText(text)
        color = self.theme.C_RED if warn else self.theme.C_MUTED
        self.status.setStyleSheet(f"color:{color};background:transparent;")

    # ------------------------------------------------------------------ 动作
    def save_note(self) -> None:
        if not self.current:
            return
        if self.service.update_note(self.current, self.note.text().strip()):
            self._set_status(f"已保存「{self.current}」的备注")
            self.refresh()
        else:
            self._set_status("备注保存失败", warn=True)

    def remove_current(self) -> None:
        if not self.current:
            return
        norm = self.current
        self.current = None
        self.service.remove(norm)
        self.view.clear()
        self.empty.setVisible(True)
        self.refresh()
        self._set_status(f"已移除「{norm}」（连带删掉本地发音）")

    def _play(self, accent: str) -> None:
        if self.current:
            self.audio.play(self.selected_entry(), accent)

    def selected_entry(self):
        return next((e for e in self.entries if e.norm == self.current), None)

    def export(self) -> None:
        target = paths.data_file(f"wordbook/单词本-{_stamp()}.json")
        try:
            path = self.service.export_wordbook(target)
        except Exception as exc:  # noqa: BLE001 - 导出失败只提示
            self._set_status(f"导出失败：{type(exc).__name__}: {exc}", warn=True)
            return
        self._set_status(f"已导出 {len(self.entries)} 个词条到 {path}")

    def import_file(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "选择单词本 JSON", str(paths.DATA_DIR), "JSON 文件 (*.json)"
        )
        if not path:
            return
        try:
            count = self.service.import_wordbook(path, merge=True)
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"导入失败：{type(exc).__name__}: {exc}", warn=True)
            return
        self.refresh()
        self._set_status(f"从 {Path(path).name} 合并了 {count} 个词条")

    def clear_all(self) -> None:
        if not self.entries:
            return
        if not self.kit.confirm(self, "清空单词本", f"确定要删除全部 {len(self.entries)} 个单词吗？此操作不可撤销。"):
            return
        removed = self.service.wordbook.clear()
        self.service.audio.clear()
        self.current = None
        self.view.clear()
        self.empty.setVisible(True)
        self.refresh()
        self._set_status(f"已清空单词本（{removed} 个词条）")

    # ------------------------------------------------------------------ 演示
    def load_demo(self) -> None:
        """离屏自检用：造两个词条塞进临时单词本，看界面（不联网）。"""
        from ..wordbook import parser as P

        demo = P.parse_entry(
            {
                "ec": {
                    "word": [
                        {
                            "ukphone": "həˈləʊ",
                            "usphone": "həˈloʊ",
                            "ukspeech": "hello&type=1",
                            "usspeech": "hello&type=2",
                            "trs": [{"tr": {"l": {"i": "int. 喂，你好"}}},
                                    {"tr": {"l": {"i": "n. 招呼，问候"}}}],
                            "wfs": [{"wf": {"name": "复数", "value": "hellos"}}],
                        }
                    ]
                },
                "blng_sents_part": {
                    "sentence-pair": [
                        {"sentence": "Hello, Trish.", "sentence-translation": "喂，特里什，你好吗？",
                         "source": "《牛津词典》"}
                    ]
                },
            },
            query="hello",
        )
        demo.note = "演示词条"
        self.service.wordbook.add(demo, replace=True)
        self.refresh()


__all__ = ["WordbookPage"]
