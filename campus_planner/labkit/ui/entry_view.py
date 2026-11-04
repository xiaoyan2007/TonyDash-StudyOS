"""词条渲染器：查询结果与单词本详情**共用一套**（改一处两边都变）。

只负责画，不负责查：数据由外部传 ``WordEntry``，用户的动作通过信号发出去：

* ``playRequested(accent)`` —— 要求播放英/美发音
* ``saveRequested()`` / ``removeRequested()`` —— 收藏 / 取消收藏
* ``suggestClicked(word)`` —— 点了「你是不是想查」

为什么要抽出来：词典查询页和单词本页要显示的东西完全一样（音标、释义、例句、
词形、标签），只是数据来源不同。写两遍必然走样。
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..wordbook import api as wapi
from ..wordbook import parser as P

#: Segoe Fluent Icons / Segoe MDL2 Assets 的码位（主程序的 ICON_CODES 里没有的）
GLYPH = {
    "volume": "\ue767",
    "play": "\ue768",
    "delete": "\ue74d",
    "edit": "\ue70f",
    "save": "\ue74e",
    "copy": "\ue8c8",
    "add": "\ue710",
    "clear": "\ue894",
    "sort": "\ue8cb",
    "sync": "\ue72c",
    "hourglass": "\ue823",
    "note": "\ue70b",
    "check": "\ue73e",
    "heart": "\ue735",
}


def glyph_label(theme, glyph: str, size: int = 13, color: str | None = None) -> QLabel:
    """图标字形用的标签（``Kit.icon_label`` 只认主程序 ICON_CODES 里的名字）。"""
    label = QLabel(glyph)
    label.setFont(theme.icon_font(size))
    label.setStyleSheet(f"color:{color or theme.C_SUB};background:transparent;")
    return label


def glyph_button(kit, theme, glyph: str, tooltip: str = "", *, kind: str = "ghost",
                 color: str | None = None, parent=None):
    """只有一个图标的小方按钮。

    **不能用 ``button.setText(glyph)``**：按钮的 QSS 里写着 ``font-family``，样式表
    的优先级高于 ``setFont()``，字形会被普通文字字体渲染成一个**空白方块**（肉眼看
    起来像「按钮没画图标」）。所以把字形放进按钮内部的一个 QLabel，字体由
    :func:`glyph_label` 直接设在 label 上——这也是主程序 ``AppButton`` 的做法。
    """
    button = kit.button("", None, kind, "icon", parent)
    button.setFixedSize(30, 30)
    label = glyph_label(theme, glyph, 14, color)
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay = QVBoxLayout(button)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(label)
    if tooltip:
        button.setToolTip(tooltip)
        label.setToolTip(tooltip)
    return button


class EntryView(QWidget):
    """把一个 ``WordEntry`` 画成一屏（音标 / 释义 / 词形 / 例句 / 短语 / 标签）。"""

    playRequested = Signal(str)
    saveRequested = Signal()
    removeRequested = Signal()
    suggestClicked = Signal(str)
    sentencePlayRequested = Signal(str)  # 例句音频（网址或 token）

    def __init__(self, kit, parent=None):
        super().__init__(parent)
        self.kit = kit
        self.theme = kit.theme
        self.entry = None
        self._saved = False
        self._sent_limit = 6
        self._build()

    # ------------------------------------------------------------------ 骨架
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._body = QWidget(self)
        self._lay = QVBoxLayout(self._body)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(10)
        outer.addWidget(self._body)

    def _clear(self) -> None:
        while self._lay.count():
            item = self._lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                self._drop_layout(item.layout())

    @staticmethod
    def _drop_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                EntryView._drop_layout(item.layout())

    # ------------------------------------------------------------------ 入口
    def clear(self) -> None:
        self.entry = None
        self._saved = False
        self._clear()

    def set_entry(self, entry, *, saved: bool = False, service=None) -> None:
        """``service`` 只用来判断「是不是没装本地词库」之类的展示细节，可为 None。"""
        self.entry = entry
        self._saved = bool(saved)
        self._sent_limit = 6
        self._clear()
        if entry is None:
            return
        self._render_head()
        if not entry.found:
            self._render_missing()
            return
        self._render_phonetics()
        self._render_trans()
        self._render_forms()
        self._render_sentences()
        self._render_phrases()
        self._render_synonyms()
        self._render_footer()

    # ------------------------------------------------------------------ 各段
    def _render_head(self) -> None:
        entry = self.entry
        head = QWidget()
        row = QHBoxLayout(head)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        word = self.kit.title(entry.word or entry.norm or "（未知）", 24)
        row.addWidget(word)
        if entry.offline:
            row.addWidget(self.kit.chip("离线释义", "amber", "info"))
        if entry.src == "youdao":
            row.addWidget(self.kit.chip("有道词典", "blue", "search"))
        if entry.raw_size:
            row.addWidget(self.kit.chip(f"{entry.raw_size / 1024:.1f} KB", "neutral"))
        row.addStretch(1)

        if entry.found:
            if self._saved:
                button = glyph_button(self.kit, self.theme, GLYPH["heart"], "从单词本移除", kind="soft")
                button.clicked.connect(self.removeRequested.emit)
                row.addWidget(button)
            else:
                button = self.kit.button("收藏到单词本", "star", "primary", "md")
                button.setToolTip("把释义、音标、例句和发音一起存到本地")
                button.clicked.connect(self.saveRequested.emit)
                row.addWidget(button)
        self._lay.addWidget(head)

    def _render_phonetics(self) -> None:
        entry = self.entry
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        any_phonetic = False
        for accent, name in (("uk", "英"), ("us", "美")):
            phonetic = entry.phonetic_uk if accent == "uk" else entry.phonetic_us
            if phonetic:
                any_phonetic = True
                text = self.kit.text(f"{name} [{phonetic}]", 13, self.theme.C_SUB)
                row.addWidget(text)
            if entry.voice_token(accent):
                button = glyph_button(
                    self.kit, self.theme, GLYPH["volume"], f"播放{name}式发音", kind="soft"
                )
                button.setProperty("accent", accent)
                button.clicked.connect(lambda _=False, a=accent: self.playRequested.emit(a))
                row.addWidget(button)

        if not any_phonetic and not entry.has_audio:
            # 短语、中文词没有音标字段，这是数据本身如此，不是错误
            hint = "该词条没有音标" + ("，但仍可发音" if entry.has_audio else "")
            row.addWidget(self.kit.text(hint, 11.5, self.theme.C_MUTED))
        row.addStretch(1)
        self._lay.addWidget(box)

    def _render_trans(self) -> None:
        entry = self.entry
        if not entry.trans:
            return
        self._lay.addWidget(self.kit.divider())
        self._lay.addWidget(self.kit.text("释义", 12, self.theme.C_MUTED))
        for sense in entry.trans:
            line = QLabel()
            line.setTextFormat(Qt.TextFormat.RichText)
            line.setWordWrap(True)
            line.setFont(self.theme.font(13))
            pos = (
                f'<span style="color:{self.theme.C_BLUE}">{html.escape(sense.pos)}</span> '
                if sense.pos
                else ""
            )
            line.setText(f'{pos}<span style="color:{self.theme.C_TEXT}">'
                         f"{html.escape(sense.definition)}</span>")
            line.setStyleSheet("background:transparent;")
            self._lay.addWidget(line)

    def _render_forms(self) -> None:
        entry = self.entry
        if not entry.forms:
            return
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(self.kit.text("词形", 12, self.theme.C_MUTED))
        for name, value in list(entry.forms.items())[:8]:
            row.addWidget(self.kit.chip(f"{name} {value}", "teal"))
        row.addStretch(1)
        self._lay.addWidget(box)

    def _render_sentences(self) -> None:
        entry = self.entry
        if not entry.sents:
            return
        self._lay.addWidget(self.kit.divider())
        head = QWidget()
        row = QHBoxLayout(head)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self.kit.text(f"例句（{len(entry.sents)}）", 12, self.theme.C_MUTED))
        row.addStretch(1)
        if len(entry.sents) > self._sent_limit:
            more = self.kit.button("显示全部", None, "ghost", "sm")
            more.clicked.connect(self._show_all_sentences)
            row.addWidget(more)
        self._lay.addWidget(head)

        for sentence in entry.sents[: self._sent_limit]:
            item = QWidget()
            col = QVBoxLayout(item)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(2)

            top = QWidget()
            line = QHBoxLayout(top)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(6)
            english = QLabel(P.strip_html(sentence.en))
            english.setWordWrap(True)
            english.setFont(self.theme.font(12.5))
            english.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            english.setStyleSheet(f"color:{self.theme.C_TEXT};background:transparent;")
            line.addWidget(english, 1)
            if sentence.audio:
                button = glyph_button(self.kit, self.theme, GLYPH["play"], "播放这句", kind="ghost")
                button.setFixedSize(24, 24)
                button.clicked.connect(
                    lambda _=False, a=sentence.audio: self.sentencePlayRequested.emit(a)
                )
                line.addWidget(button)
            col.addWidget(top)

            meta = " · ".join(x for x in (sentence.zh, sentence.source) if x)
            if meta:
                detail = self.kit.text(meta, 11.5, self.theme.C_MUTED, wrap=True)
                detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                col.addWidget(detail)
            self._lay.addWidget(item)

    def _show_all_sentences(self) -> None:
        self._sent_limit = len(self.entry.sents) if self.entry else 6
        self.set_entry(self.entry, saved=self._saved)

    def _render_phrases(self) -> None:
        entry = self.entry
        if not entry.phrases:
            return
        self._lay.addWidget(self.kit.divider())
        self._lay.addWidget(self.kit.text("短语", 12, self.theme.C_MUTED))
        for phrase in entry.phrases[:6]:
            label = self.kit.text(f"{phrase.pos}  {phrase.definition}", 12, self.theme.C_SUB, wrap=True)
            self._lay.addWidget(label)

    def _render_synonyms(self) -> None:
        entry = self.entry
        if not entry.synonyms:
            return
        self._lay.addWidget(self.kit.text("同近义词", 12, self.theme.C_MUTED))
        for item in entry.synonyms[:6]:
            self._lay.addWidget(
                self.kit.text(f"{item.pos}  {item.definition}", 12, self.theme.C_SUB, wrap=True)
            )

    def _render_footer(self) -> None:
        entry = self.entry
        if entry.etym:
            self._lay.addWidget(self.kit.divider())
            self._lay.addWidget(self.kit.text(f"词源：{entry.etym}", 11.5, self.theme.C_MUTED, wrap=True))
        if entry.tags:
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            for tag in entry.tags[:6]:
                row.addWidget(self.kit.chip(tag, "purple"))
            row.addStretch(1)
            self._lay.addWidget(box)
        if entry.note:
            self._lay.addWidget(self.kit.text(f"备注：{entry.note}", 11.5, self.theme.C_MUTED, wrap=True))
        self._lay.addWidget(self.kit.text(wapi.CREDIT, 10.5, self.theme.C_MUTED, wrap=True))

    def _render_missing(self) -> None:
        entry = self.entry
        reason = entry.note or "词典没有收录这个词"
        self._lay.addWidget(self.kit.text(reason, 13, self.theme.C_SUB, wrap=True))
        if entry.suggestions:
            self._lay.addWidget(self.kit.text("你是不是想查：", 12, self.theme.C_MUTED))
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            for word in entry.suggestions[:6]:
                button = self.kit.button(word, None, "soft", "sm")
                button.clicked.connect(lambda _=False, w=word: self.suggestClicked.emit(w))
                row.addWidget(button)
            row.addStretch(1)
            self._lay.addWidget(box)
        self._lay.addWidget(self.kit.text(wapi.CREDIT, 10.5, self.theme.C_MUTED, wrap=True))


__all__ = ["EntryView", "GLYPH", "glyph_button", "glyph_label"]
