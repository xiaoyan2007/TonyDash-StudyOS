"""有道词典查询 + 本地单词本（Lab 新功能 B）。

分层（**每一层都能单独测，网络只出现在 client 层**）::

    UI(词典页/单词本页)
      └── service.WordService      编排：缓存 → 联网 → 离线兜底
            ├── client.YoudaoClient 唯一出网的地方（jsonapi / suggest / 发音）
            ├── parser              纯函数：原始 JSON → WordEntry
            ├── audio.AudioStore    发音 mp3 落盘缓存
            └── store.WordbookStore 单词本 + 查询缓存（JSON，带 schema 版本）

整合到主程序时只需要 ``api`` 这一层：``WordService`` 负责数据，
``build_wordbook()`` 负责把本地单词本交给主程序的 ``AppData``。
"""

from __future__ import annotations

__all__ = ["api", "audio", "client", "models", "parser", "service", "store"]
