"""整合门面：主程序将来只 import 这一个模块。

主程序侧的用法（三段式，和课表导入保持一致）::

    from labkit.wordbook import api

    svc = api.make_service()                      # 数据落在 lab/_data/
    res = api.lookup(svc, "hello")                # 查询（缓存 → 有道 → 本地词库）
    api.add(svc, res.entry)                       # 收藏（顺带把发音 mp3 存到本地）

界面上要的东西都在这里：``rows()`` 给表格、``to_payload()`` 给备份/导出、
``status_text()`` 给状态栏、``install_hint()`` 给「怎么并进主程序」的说明。
"""

from __future__ import annotations

from pathlib import Path

from . import parser
from .audio import AudioStore
from .models import Sentence, Sense, WordEntry
from .offline import OfflineDict
from .service import LookupResult, WordService
from .store import QueryCache, WordbookStore

#: 方便 ``api.P.normalize(...)`` 这样的简写
P = parser

#: 状态栏/界面用的免责声明（有道词典的内容版权归有道，仅供个人学习）
CREDIT = "释义与发音来自有道词典，仅供个人学习使用。"

#: 表格列（词典查询结果与单词本共用一套渲染器）
RESULT_COLUMNS = ("单词", "音标", "释义", "例句", "标签")


def make_service(root: str | Path | None = None, **kwargs) -> WordService:
    """建服务（参数透传给 :class:`WordService`，测试时可注入假客户端）。

    给了 ``root`` 就把单词本 / 缓存 / 发音 / 离线词库全放进这个目录 ——
    自检脚本、多套数据、将来主程序指定数据目录都靠它，默认全在 ``lab/_data/``。
    """
    if root is None:
        return WordService(**kwargs)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    kwargs.setdefault("wordbook", WordbookStore(root / "wordbook.json"))
    kwargs.setdefault("cache", QueryCache(root / "cache" / "queries.json"))
    kwargs.setdefault("audio", AudioStore(root / "audio"))
    kwargs.setdefault("offline", OfflineDict(root))
    return WordService(**kwargs)


def lookup(service: WordService, query: str, **kwargs) -> LookupResult:
    return service.lookup(query, **kwargs)


def add(service: WordService, entry: WordEntry, **kwargs) -> tuple[bool, str]:
    return service.add(entry, **kwargs)


def remove(service: WordService, query: str) -> bool:
    return service.remove(query)


def rows(entries: list[WordEntry]) -> list[dict]:
    """把词条列表变成界面表格用的行。"""
    out: list[dict] = []
    for entry in entries:
        out.append(
            {
                "word": entry.word or entry.norm,
                "norm": entry.norm,
                "phonetic": entry.phonetic_line(),
                "summary": entry.summary(),
                "sents": len(entry.sents),
                "tags": "、".join(entry.tags),
                "saved": bool(entry.audio_files) or not entry.has_audio,
                "offline": entry.offline,
                "note": entry.note,
                "entry": entry,
            }
        )
    return out


def to_payload(service: WordService) -> dict:
    """导出给主程序 ``AppData`` / 备份用的扁平结构。

    **只导出单词本内容本身**，不含缓存；``schema`` 独立于主程序 ``data.json``，
    将来合并时用 :func:`~labkit.wordbook.store.WordbookStore.import_from` 反向导入。
    """
    entries = service.saved_entries()
    return {
        "schema": 1,
        "kind": "wordbook",
        "count": len(entries),
        "credit": CREDIT,
        "entries": [e.to_dict() for e in entries],
        "status": service.status(),
    }


def save_payload(service: WordService, path: str | Path) -> Path:
    from ..common.storage import write_json

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json(target, to_payload(service))
    return target


def status_text(service: WordService) -> str:
    return service.status()


def install_hint() -> str:
    """给未来的自己看：怎么并进主程序。"""
    return (
        "整合步骤：① 把 lab/labkit/wordbook/ 整个目录复制进 campus_planner/（或作为子包）；"
        "② 新增 campus_planner/pages/wordbook.py（词典查询 + 单词本两个视图，直接复用 theme/widgets）；"
        "③ 在 campus_planner/main.py 的导航里加一项；"
        "④ 单词本文件保持独立（不要把 entries 塞进 data.json），"
        "只在 Settings 里记一个路径指针，避免主程序版本升级时清空用户生词。"
    )


__all__ = [
    "CREDIT",
    "P",
    "RESULT_COLUMNS",
    "LookupResult",
    "Sentence",
    "Sense",
    "WordEntry",
    "WordService",
    "add",
    "install_hint",
    "lookup",
    "make_service",
    "parser",
    "remove",
    "rows",
    "save_payload",
    "status_text",
    "to_payload",
]
