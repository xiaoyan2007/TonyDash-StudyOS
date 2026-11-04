"""鸣谢名单：设置页底部，感谢参与测试与反馈的同学。

学校徽标优先使用 assets/credits/<缩写>.png（可自行替换为官方校徽）；
没有图片时统一绘制圆角渐变徽标，保证任何环境下观感一致。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from . import theme, widgets


@dataclass
class School:
    name: str
    pinyin: str
    abbr: str
    color: str
    people: list[str]


# 按学校拼音排序：澳门 < 宁波 < 云南 < 浙江财经 < 浙江工商
SCHOOLS: list[School] = [
    School("澳门大学", "aomen", "UM", "#12557F", ["xy"]),
    School("宁波诺丁汉大学", "ningbo", "UNNC", "#8C1D40", ["ymz"]),
    School("云南大学", "yunnan", "YNU", "#6A4C93", ["wjx"]),
    School("浙江财经大学", "zhejiang caijing", "ZUFE", "#2A7D4F", ["lmd"]),
    School("浙江工商大学", "zhejiang gongshang", "ZJGSU", "#C0392B",
           ["yyx", "fqy", "zkh", "wyy", "ljc"]),
]


def _logo_pixmap(path: str, size: int) -> QPixmap | None:
    if not path or not os.path.exists(path):
        return None
    pm = QPixmap(path)
    if pm.isNull():
        return None
    return pm.scaled(size, size,
                     Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)


def _round_clip(size: int) -> QPainterPath:
    shape = QPainterPath()
    shape.addRoundedRect(QRectF(0, 0, size, size), size * 0.24, size * 0.24)
    return shape


def _badge_pixmap(school: School, size: int = 48) -> QPixmap:
    """优先显示 assets/credits/<缩写>.png，否则绘制圆角渐变徽标。"""
    logo = _logo_pixmap(theme.asset_path(f"credits/{school.abbr}.png"), size)
    if logo is not None:
        # 官方校徽优先原样显示（圆形已去白底、诺丁汉保留原图形状）
        return logo

    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    base = QColor(school.color)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, base.lighter(135))
    grad.setColorAt(1, base)
    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), size * 0.24, size * 0.24)
    p.setPen(QPen(QColor(255, 255, 255, 90), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(4.5, 4.5, size - 9, size - 9), size * 0.20, size * 0.20)
    p.setPen(QColor(255, 255, 255))
    p.setFont(theme.font(size * 0.30, theme.QFont.Weight.DemiBold))
    p.drawText(out.rect(), Qt.AlignmentFlag.AlignCenter, school.abbr)
    p.end()
    return out


class CreditsCard(widgets.GlassCard):
    """鸣谢名单卡片：校徽 + 学校名 + 参与同学名单。"""

    def __init__(self, parent=None):
        super().__init__(parent, radius=16, alpha=180)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 15, 18, 17)
        lay.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(9)
        head.addWidget(widgets.IconBadge("heart", 30))
        box = QVBoxLayout()
        box.setSpacing(0)
        t = QLabel("鸣谢名单", self)
        t.setFont(theme.font(13.5, theme.QFont.Weight.DemiBold))
        t.setStyleSheet("background: transparent;")
        s = QLabel("感谢每一位参与测试与反馈的同学", self)
        s.setFont(theme.font(11.5))
        s.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        box.addWidget(t)
        box.addWidget(s)
        head.addLayout(box, 1)
        lay.addLayout(head)

        intro = QLabel(
            "感谢你们把课表、考试和待办真正用起来的每一次反馈："
            "一个报错、一句「这里看不清」、一次顺手的提醒，都在让这块玻璃变得更好用。"
            "名单按学校拼音排序，昵称由同学本人确认。",
            self,
        )
        intro.setWordWrap(True)
        intro.setFont(theme.font(12))
        intro.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
        lay.addWidget(intro)

        for index, school in enumerate(SCHOOLS):
            if index:
                line = QLabel("", self)
                line.setFixedHeight(6)
                line.setStyleSheet("background: transparent;")
                lay.addWidget(line)
            row = QHBoxLayout()
            row.setSpacing(12)
            badge = QLabel(self)
            badge.setPixmap(_badge_pixmap(school, 48))
            badge.setFixedSize(48, 48)
            row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

            col = QVBoxLayout()
            col.setSpacing(3)
            name = QLabel(school.name, self)
            name.setFont(theme.font(12, theme.QFont.Weight.DemiBold))
            name.setStyleSheet(f"color: {theme.C_TEXT}; background: transparent;")
            col.addWidget(name)
            people = QLabel(" · ".join(school.people), self)
            people.setFont(theme.font(12))
            people.setStyleSheet(f"color: {theme.C_SUB}; background: transparent;")
            col.addWidget(people)
            row.addLayout(col, 1)

            count = QLabel(f"{len(school.people)} 位同学", self)
            count.setFont(theme.font(11.5))
            count.setStyleSheet(f"color: {theme.C_MUTED}; background: transparent;")
            row.addWidget(count, 0, Qt.AlignmentFlag.AlignTop)
            lay.addLayout(row)

        tail = QLabel("愿每一次登录，都能少一点焦虑、多一点方向。", self)
        tail.setFont(theme.font(12, theme.QFont.Weight.DemiBold))
        tail.setStyleSheet(f"color: {theme.C_BLUE}; background: transparent;")
        lay.addWidget(tail)
