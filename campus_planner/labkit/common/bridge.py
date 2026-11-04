"""主程序桥接：把 `campus_planner/` 的主题与组件按「只读引用」的方式接进来。

为什么这样做
------------
新功能将来要并进主程序，界面必须和主程序**长得一模一样**。与其复制一份
`theme.py`（两处维护必然漂移），不如在开发期直接 import 主程序模块：

* 只 import，**从不写入** `campus_planner/`，满足「其余文件夹严禁改动」；
* 主程序不在旁边时自动退回内置精简主题，lab 仍能独立跑起来。

对外只有三个门面：:func:`theme` / :func:`widgets` / :func:`main_core`。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from . import paths


@dataclass
class MainProgram:
    """主程序源码的加载结果。"""

    ok: bool = False
    error: str = ""
    root: Path = field(default_factory=lambda: paths.WORKSPACE_ROOT)
    theme: ModuleType | None = None
    widgets: ModuleType | None = None
    core: ModuleType | None = None
    added_path: bool = False


_loaded: MainProgram | None = None


def _ensure_importable() -> bool:
    """把工作区根目录挂到 sys.path，让 `import campus_planner.*` 可用。"""
    root = str(paths.WORKSPACE_ROOT)
    if root in sys.path:
        return False
    sys.path.insert(0, root)
    return True


def load_main(force: bool = False) -> MainProgram:
    """加载主程序的 theme/widgets/core（只读）。结果缓存。"""
    global _loaded
    if _loaded is not None and not force:
        return _loaded

    result = MainProgram()
    if not paths.has_main_package():
        result.error = f"未找到主程序源码：{paths.MAIN_PACKAGE}"
        _loaded = result
        return result

    result.added_path = _ensure_importable()
    try:
        from campus_planner import theme as _theme  # noqa: WPS433

        result.theme = _theme
    except Exception as exc:  # pragma: no cover - 环境相关
        result.error = f"主程序主题加载失败：{exc}"

    for name, attr in (("widgets", "widgets"), ("core", "core")):
        try:
            module = __import__(f"campus_planner.{name}", fromlist=["*"])
            setattr(result, attr, module)
        except Exception:  # pragma: no cover - 组件缺失不应阻断运行
            pass

    result.ok = result.theme is not None
    _loaded = result
    return result


# --------------------------------------------------------------------- 门面
def theme():
    """返回主题模块（主程序的，或内置兜底）。"""
    main = load_main()
    return main.theme if main.theme is not None else _FALLBACK


def widgets():
    """返回主程序组件模块；不可用时返回 ``None``。"""
    return load_main().widgets


def main_core():
    """返回主程序数据模型模块；不可用时返回 ``None``。"""
    return load_main().core


def main_ok() -> bool:
    """主程序主题是否已接入（界面标题上显示用）。"""
    return load_main().ok


def main_info() -> MainProgram:
    """完整的主程序接入信息（含 error）。"""
    return load_main()


def needs_widget(mod_name: str):
    """便捷导入：``GlassCard = needs_widget("GlassCard")``。"""
    module = widgets()
    if module is None:
        raise RuntimeError("主程序组件不可用，无法复用 GlassCard 等控件")
    return getattr(module, mod_name)


# ----------------------------------------------------------------- 兜底主题
class _FallbackTheme:
    """主程序不在旁边时的精简主题：只覆盖 lab 界面真正用到的部分。

    数值与主程序 `theme.py` 的 LIGHT 方案保持一致，视觉上不会突然变样。
    """

    MODE = "light"
    LIGHT = {
        "text": "#18181B", "sub": "#5F5F66", "muted": "#85858C",
        "blue": "#0A84FF", "blue_hover": "#0A76E0", "blue_press": "#0768C8",
        "green": "#248A3D", "red": "#D70015", "amber": "#8A5200",
        "orange": "#C25E00", "purple": "#8944AB", "teal": "#0F7C8A",
        "white": "#FFFFFF",
    }
    C_TEXT = "#18181B"
    C_SUB = "#5F5F66"
    C_MUTED = "#85858C"
    C_BLUE = "#0A84FF"
    C_BLUE_HOVER = "#0A76E0"
    C_BLUE_PRESS = "#0768C8"
    C_BLUE_SOFT = "rgba(10, 132, 255, 38)"
    C_GREEN = "#248A3D"
    C_RED = "#D70015"
    C_AMBER = "#8A5200"
    C_ORANGE = "#C25E00"
    C_PURPLE = "#8944AB"
    C_TEAL = "#0F7C8A"
    C_WHITE = "#FFFFFF"
    FONT_FAMILY = "Microsoft YaHei UI"
    COURSE_COLORS = ["#0A84FF", "#5E5CE6", "#30B0C7", "#34C759",
                     "#FF9F0A", "#FF375F", "#BF5AF2", "#AC8E68"]
    ICON_CODES = {
        "calendar": 0xE787, "settings": 0xE713, "plus": 0xE710, "search": 0xE721,
        "left": 0xE76B, "right": 0xE76C, "trash": 0xE74D, "copy": 0xE8C8,
        "download": 0xE896, "upload": 0xE898, "close": 0xE711, "check": 0xE73E,
        "clock": 0xE823, "user": 0xE77B, "warning": 0xE7BA, "info": 0xE946,
        "edit": 0xE70F, "refresh": 0xE72C, "save": 0xE74E, "books": 0xE8F1,
        "list": 0xE8FD, "star": 0xE734, "star_fill": 0xE735, "tag": 0xE8EC,
        "folder": 0xE8B7, "doc": 0xE8A5, "shuffle": 0xE8B1, "external": 0xE8A7,
    }

    def __init__(self) -> None:
        self._icon_family: str | None = None

    # Qt 类型走惰性属性：命令行工具用不到 Qt 时不必为了一个常量导入 Qt，
    # 也避免 Qt 在 Windows 上接管控制台后把 Python 的 stdout 吞掉。
    @property
    def QFont(self):
        from PySide6.QtGui import QFont

        return QFont

    @property
    def QColor(self):
        from PySide6.QtGui import QColor

        return QColor

    @property
    def QIcon(self):
        from PySide6.QtGui import QIcon

        return QIcon

    @property
    def QPixmap(self):
        from PySide6.QtGui import QPixmap

        return QPixmap

    def tokens(self) -> dict:
        return self.LIGHT

    def load_fonts(self) -> None:
        import os

        from PySide6.QtGui import QFontDatabase
        windir = os.environ.get("WINDIR", r"C:\Windows")
        for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf",
                     "SegoeIcons.ttf", "segmdl2.ttf"):
            path = os.path.join(windir, "Fonts", name)
            if os.path.exists(path):
                QFontDatabase.addApplicationFont(path)

    def icon_family(self) -> str:
        from PySide6.QtGui import QFontDatabase

        if self._icon_family:
            return self._icon_family
        families = set(QFontDatabase.families())
        for name in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
            if name in families:
                self._icon_family = name
                return name
        self._icon_family = ""
        return ""

    def icon_char(self, name: str) -> str:
        code = self.ICON_CODES.get(name)
        return chr(code) if code else ""

    def icon_font(self, size: int = 12, weight=None):
        font = self.QFont(self.icon_family() or self.FONT_FAMILY)
        font.setPixelSize(size)
        if weight is not None:
            font.setWeight(weight)
        return font

    def font(self, size: float = 11, weight=None, family: str | None = None):
        font = self.QFont(family or self.FONT_FAMILY)
        font.setPixelSize(int(round(size * 1.34)))
        if weight is not None:
            font.setWeight(weight)
        return font

    def course_color(self, index: int):
        """与主程序一致：**索引从 1 开始**，第 0 门课也落在第 1 种颜色上。"""
        return self.color(self.COURSE_COLORS[(max(1, int(index)) - 1) % len(self.COURSE_COLORS)])

    def color(self, hex_or_color, alpha: int | None = None):
        cls = self.QColor
        value = cls(hex_or_color)
        if alpha is not None:
            value.setAlpha(max(0, min(255, int(alpha))))
        return value

    def mix(self, a, b, ratio: float = 0.5):
        """与主程序 theme.mix 逐字节一致（含 alpha，且用 int 截断而不是四舍五入）。"""
        cls = self.QColor
        ca = a if isinstance(a, cls) else cls(a)
        cb = b if isinstance(b, cls) else cls(b)
        r = max(0.0, min(1.0, float(ratio)))
        return cls(
            int(ca.red() + (cb.red() - ca.red()) * r),
            int(ca.green() + (cb.green() - ca.green()) * r),
            int(ca.blue() + (cb.blue() - ca.blue()) * r),
            int(ca.alpha() + (cb.alpha() - ca.alpha()) * r),
        )

    def set_theme(self, mode: str) -> str:
        self.MODE = "dark" if str(mode).lower().startswith("d") else "light"
        return self.MODE

    def app_font(self):
        return self.font(13)

    def global_qss(self) -> str:
        return (
            "QWidget { color: %s; font-family: '%s'; }"
            "QToolTip { background: #FFFFFF; color: %s; border: 1px solid #D8DEE9;"
            " padding: 4px 6px; border-radius: 6px; }"
            % (self.C_TEXT, self.FONT_FAMILY, self.C_TEXT)
        )

    def apply_global_qss(self, force: bool = False) -> None:
        """与主程序同名接口：把全局样式装到当前 QApplication 上。"""
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(self.global_qss())


_FALLBACK = _FallbackTheme()
