"""labkit —— 托尼Dash学习终端「实验室」功能包。

本包是**独立开发、独立运行**的新功能集合，与主程序 `campus_planner/` 完全解耦：

* 只依赖标准库 + Qt（可选复用主程序主题）；
* 每个子包都能单独启动（见工作区根目录 `run_tt_import.py` / `run_wordbook.py`）；
* 对外只暴露 `api.py` 里的少数函数，方便日后整体平移进主程序。

子包：
    ``labkit.common``    主题桥接、存储、通用 UI 组件
    ``labkit.ttimport``  课表导入（粘贴文本 / CSV / Excel / 截图 OCR）
    ``labkit.wordbook``  有道词典查询与本地单词本
"""

from __future__ import annotations

__all__ = ["common", "ttimport", "wordbook"]

__version__ = "0.1.0"
