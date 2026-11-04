"""lab 界面层：把主程序的外观与 lab 的功能拼在一起。

- :class:`~labkit.ui.kit.Kit`：控件适配层（有主程序就用主程序控件，没有就用内置兜底）
- :class:`~labkit.ui.media.AudioPlayer` / ``AudioPlayback`` / ``LookupWorker``：发音与后台任务
- :class:`~labkit.ui.entry_view.EntryView`：词条渲染（查询页与单词本页共用）
- :class:`~labkit.ui.import_page.ImportPage`：课表导入页
- :class:`~labkit.ui.word_page.WordPage`：词典查询页
- :class:`~labkit.ui.wordbook_page.WordbookPage`：本地单词本页
"""

from .entry_view import EntryView, glyph_button, glyph_label
from .import_page import ImportPage
from .kit import Kit
from .media import (
    AudioPlayback, AudioPlayer, AudioFetchWorker, LookupWorker, SaveWorker,
    TranslateWorker, media_available,
)
from .word_page import WordPage
from .wordbook_page import WordbookPage

__all__ = [
    "Kit",
    "ImportPage",
    "WordPage",
    "WordbookPage",
    "EntryView",
    "glyph_label",
    "glyph_button",
    "AudioPlayer",
    "AudioPlayback",
    "AudioFetchWorker",
    "LookupWorker",
    "SaveWorker",
    "TranslateWorker",
    "media_available",
]
