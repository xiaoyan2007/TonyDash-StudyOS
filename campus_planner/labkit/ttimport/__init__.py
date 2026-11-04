"""课表导入：粘贴文本 / CSV / Excel / 截图 OCR → 结构化课程。

对外只用 :mod:`labkit.ttimport.api` 里的函数，其余是内部实现。
"""

from __future__ import annotations

__all__ = ["api", "models", "weeks", "fields", "cell_parser", "text_parser", "tabular", "ocr"]
