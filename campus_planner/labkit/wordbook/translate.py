"""有道翻译 / 多语种词条 —— 词典页第二个选项卡与语言下拉框的后端。

接口（都用标准库 ``urllib``，与 :mod:`labkit.wordbook.client` 共用请求与重试）

* **翻译**：``https://aidemo.youdao.com/trans?q=..&from=..&to=..``
  返回 ``{"translation": ["译文"], "errorCode": "0"}``。
  实测覆盖中 / 英 / 法 / 日 / 韩 / 西 等；个别语言对（如 ru→zh、zh→fr）
  服务端返回 ``errorCode=411``（不支持的语言对），这里如实提示而不是假装失败。
* **多语种词条**：``dict.youdao.com/jsonapi`` 的 ``le`` 参数决定词典方向，
  语言下拉框选中后把它带上即可（英汉 / 法汉 / 日汉…）。

有道 ``from/to`` 用的语言代码与词典 ``le`` 不完全一样（``zh-CHS``、``en``…），
所以 :data:`LANGUAGES` 里同时给出 ``le`` 与 ``from``/``to`` 三个代码。
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Callable

from .client import YoudaoClient, YoudaoError

__all__ = [
    "LANGUAGES", "TRANSLATE_URL", "translate", "lang_label",
    "guess_lang_code", "lang_codes",
]

#: 语言下拉框：``(le 代码, 中文名, 翻译接口代码)``。
#: ``le`` 给词典 jsonapi 用，翻译代码给 aidemo/trans 的 ``from`` / ``to`` 用。
LANGUAGES: tuple[tuple[str, str, str], ...] = (
    ("auto", "自动检测", "Auto"),
    ("zh", "中文", "zh-CHS"),
    ("en", "英语", "en"),
    ("fr", "法语", "fr"),
    ("ja", "日语", "ja"),
    ("ko", "韩语", "ko"),
    ("es", "西班牙语", "es"),
    ("de", "德语", "de"),
    ("it", "意大利语", "it"),
    ("pt", "葡萄牙语", "pt"),
    ("ru", "俄语", "ru"),
)

#: 有道翻译接口（免鉴权，返回 JSON）。
TRANSLATE_URL = "https://aidemo.youdao.com/trans?q={q}&from={f}&to={t}"

_LABEL_MAP = {code: name for code, name, _ in LANGUAGES}
_TRANS_MAP = {code: trans for code, _, trans in LANGUAGES}


def lang_label(code: str) -> str:
    """语言代码 → 显示名（未知代码原样返回）。"""
    return _LABEL_MAP.get(str(code or "").strip().lower(), str(code or ""))


def lang_codes(code: str) -> tuple[str, str, str]:
    """返回 ``(le, 中文名, 翻译接口代码)``。"""
    code = str(code or "").strip().lower()
    for le, name, trans in LANGUAGES:
        if le == code:
            return le, name, trans
    return code, code, code


def guess_lang_code(text: str) -> str:
    """粗略判断源语言（仅用于下拉框默认值；真正判断交给服务端 ``Auto``）。"""
    text = str(text or "")
    if not text.strip():
        return "auto"
    if any("\u3040" <= ch <= "\u30ff" for ch in text):
        return "ja"
    if any("\uac00" <= ch <= "\ud7af" for ch in text):
        return "ko"
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        return "zh"
    if any("\u0400" <= ch <= "\u04ff" for ch in text):
        return "ru"
    return "en"


def translate(client: YoudaoClient, text: str, *, source: str = "auto",
              target: str = "zh",
              on_progress: Callable[[int, str], None] | None = None) -> dict:
    """调用有道翻译。

    返回 ``{"ok": bool, "text", "result", "source", "target", "error"}``。
    失败不抛异常，界面按 ``ok`` 决定提示方式。
    """
    raw_text = str(text or "").strip()
    if not raw_text:
        return {"ok": False, "text": "", "result": "", "source": source,
                "target": target, "error": "请输入要翻译的内容"}

    le_from, name_from, trans_from = lang_codes(source)
    le_to, name_to, trans_to = lang_codes(target)
    if le_from == le_to and le_from != "auto":
        return {"ok": False, "text": raw_text, "result": "", "source": source,
                "target": target, "error": "源语言与目标语言相同，换一个目标语言试试"}

    url = TRANSLATE_URL.format(
        q=urllib.parse.quote(raw_text), f=trans_from, t=trans_to)

    if on_progress is not None:
        try:
            on_progress(20, f"连接翻译服务…（{name_from} → {name_to}）")
        except Exception:  # noqa: BLE001 - 进度回调失败不该影响翻译
            pass

    try:
        body = client._request(url, accept="application/json", what="翻译",
                               on_progress=on_progress)
    except YoudaoError as exc:
        return {"ok": False, "text": raw_text, "result": "", "source": source,
                "target": target, "error": f"翻译失败：{exc}"}
    except Exception as exc:  # noqa: BLE001 - 任何网络异常都要变成可展示信息
        return {"ok": False, "text": raw_text, "result": "", "source": source,
                "target": target, "error": f"翻译失败：{type(exc).__name__}: {exc}"}

    try:
        payload = json.loads(body.decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError):
        return {"ok": False, "text": raw_text, "result": "", "source": source,
                "target": target, "error": "翻译服务返回的内容无法解析"}

    if on_progress is not None:
        try:
            on_progress(85, "整理译文…")
        except Exception:  # noqa: BLE001
            pass

    code = str(payload.get("errorCode") or "0")
    if code != "0":
        # 411 = 不支持该语言对，其余按服务端错误码如实提示
        if code == "411":
            msg = f"不支持「{name_from} → {name_to}」这个语言对，换个目标语言试试"
        else:
            msg = f"翻译服务返回错误码 {code}"
        return {"ok": False, "text": raw_text, "result": "", "source": source,
                "target": target, "error": msg}

    rows = payload.get("translation") or []
    result_text = "".join(str(row or "") for row in rows) if isinstance(rows, list) \
        else str(rows or "")
    result_text = result_text.strip()

    if on_progress is not None:
        try:
            on_progress(100, "翻译完成")
        except Exception:  # noqa: BLE001
            pass

    if not result_text:
        return {"ok": False, "text": raw_text, "result": "", "source": source,
                "target": target, "error": "没有拿到译文，请换个说法再试"}
    return {"ok": True, "text": raw_text, "result": result_text,
            "source": source, "target": target, "error": ""}
