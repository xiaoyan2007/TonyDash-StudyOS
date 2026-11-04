"""持久化：原子写 JSON + 版本迁移 + 损坏自愈。

思路直接沿用主程序 `campus_planner/core.py` 的成熟做法：

* 先写同目录临时文件，再 ``os.replace`` 原子替换 —— 断电/异常退出不会写坏原文件；
* 读出来解析失败时，把坏文件另存为 ``*.bad-<时间戳>`` 再回落默认值，绝不静默丢数据；
* 每个文件带 ``schema`` 版本号，迁移函数按版本链式升级，**认不出的高版本只读不写**。
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

#: 迁移函数签名：吃一个旧 dict，吐一个新 dict
Migrator = Callable[[dict], dict]


class StoreError(RuntimeError):
    """存储层异常（读写失败、版本不认识）。"""


class VersionTooNewError(StoreError):
    """文件版本比当前程序还新 —— 只读展示，禁止覆盖。"""


def read_json(path: Path, default: Any = None) -> tuple[Any, str | None]:
    """读 JSON。

    返回 ``(数据, 错误说明)``：

    * 文件不存在 -> ``(default, None)``
    * 解析失败   -> ``(default, "原因")``，并把坏文件备份成 ``*.bad-<时间戳>``
    """
    if not path.exists():
        return default, None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return default, f"读取失败：{exc}"
    if not text.strip():
        return default, None
    try:
        return json.loads(text), None
    except (json.JSONDecodeError, ValueError) as exc:
        backup = path.with_name(f"{path.name}.bad-{time.strftime('%Y%m%d-%H%M%S')}")
        try:
            path.replace(backup)
            detail = f"文件损坏（{exc}），已备份为 {backup.name}"
        except OSError:
            detail = f"文件损坏（{exc}），且备份失败"
        return default, detail


def write_json(path: Path, data: Any, *, indent: int = 2) -> None:
    """原子写 JSON（临时文件 + ``os.replace``）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=indent)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


class JsonStore:
    """带 schema 版本与迁移链的小型 JSON 存储。

    典型用法::

        store = JsonStore(path, schema=2, default={"entries": []})
        store.register_migration(1, upgrade_v1_to_v2)
        data = store.load()      # 自动迁移并回写
    """

    def __init__(
        self,
        path: Path,
        *,
        schema: int,
        default: dict | None = None,
        label: str = "",
    ) -> None:
        self.path = Path(path)
        self.schema = int(schema)
        self.default = dict(default or {})
        self.label = label or self.path.name
        self._migrations: dict[int, Migrator] = {}
        self.last_error: str | None = None
        self.read_only = False

    # ------------------------------------------------------------------ 迁移
    def register_migration(self, from_version: int, fn: Migrator) -> None:
        """注册 ``from_version -> from_version + 1`` 的迁移。"""
        self._migrations[int(from_version)] = fn

    def _migrate(self, raw: dict) -> tuple[dict, list[str]]:
        notes: list[str] = []
        version = int(raw.get("schema", 0) or 0)
        if version > self.schema:
            raise VersionTooNewError(
                f"{self.label} 的版本 {version} 高于当前程序支持的 {self.schema}，"
                "已切换为只读模式以免覆盖数据。"
            )
        guard = 0
        while version < self.schema:
            fn = self._migrations.get(version)
            if fn is None:
                # 没有迁移函数：用默认值补齐缺失键，尽量不丢已有字段
                notes.append(f"{self.label}：缺少 v{version}→v{version + 1} 的迁移，已按默认值补齐。")
                merged = dict(self.default)
                merged.update(raw)
                merged["schema"] = version + 1
                raw = merged
            else:
                raw = fn(dict(raw))
                raw["schema"] = version + 1
                notes.append(f"{self.label}：已从 v{version} 升级到 v{version + 1}。")
            version += 1
            guard += 1
            if guard > 50:
                raise StoreError(f"{self.label} 迁移链异常（循环）")
        return raw, notes

    # ------------------------------------------------------------------ 读写
    def load(self) -> dict:
        """读数据；自动迁移、必要时回写。任何异常都回落默认值。"""
        self.last_error = None
        self.read_only = False
        raw, err = read_json(self.path, None)
        if err:
            self.last_error = err
        if not isinstance(raw, dict) or not raw:
            data = dict(self.default)
            data["schema"] = self.schema
            return data
        try:
            data, notes = self._migrate(raw)
        except VersionTooNewError as exc:
            self.last_error = str(exc)
            self.read_only = True
            return raw
        if notes and not self.read_only:
            self.last_error = "；".join(notes)
            try:
                self.save(data)
            except OSError:
                pass
        return data

    def save(self, data: dict) -> None:
        if self.read_only:
            raise StoreError(f"{self.label} 处于只读模式，拒绝写入。")
        payload = dict(data)
        payload["schema"] = self.schema
        payload.setdefault("updated_at", time.time())
        write_json(self.path, payload)

    def update(self, **changes: Any) -> dict:
        """读-改-写：把 ``changes`` 合并进现有数据后落盘。"""
        data = self.load()
        data.update(changes)
        self.save(data)
        return data


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
