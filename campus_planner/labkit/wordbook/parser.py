"""把有道 ``jsonapi`` 的原始响应解析成 :class:`WordEntry` —— **纯函数，不出网**。

实测过的坑（每条都在这里处理掉了）：

* ``ec.word[].trs[].tr[].l.i`` 是**字符串列表**（不是字符串），一词性一条；
* 中文词没有 ``ec``，释义在 ``ce.word[].trs[].tr[].l``，其中 ``i`` 还会混进
  ``{"#text": "China", "@action": "link"}`` 这样的跳转节点，必须递归取文本；
* ``oxford*`` / ``webster`` / ``senior`` 只有 ``encryptedData``，**不可用**，
  不要浪费时间解析；
* ``meta.isHasSimpleDict == "0"`` 或响应里只有 ``typos`` ⇒ 干净的「没查到这个词」，
  应当提示近似词而不是显示空页面；
* 空字符串会返回单词 ``null`` 的词条 ⇒ 必须在 :func:`normalize` 里先拒绝；
* 短语（``a piece of cake``）没有音标，只能靠 ``simple.speech`` 发音。
"""

from __future__ import annotations

import html
import re
import time
from typing import Any

from .models import SCHEMA, Sentence, Sense, WordEntry

#: 出了这些键就说明「词典里有货」，其余（``meta``/``lang``/``input``）只是元信息
SUBSTANTIVE_KEYS = (
    "ec",
    "ce",
    "newhh",
    "baike",
    "expand_ec",
    "ee",
    "collins_primary",
    "individual",
    "blng_sents_part",
    "media_sents_part",
    "auth_sents_part",
    "phrs",
    "syno",
    "wikipedia_digest",
    "etym",
    "pic_dict",
    "web_trans",
)

#: 这些只有加密数据，解析不了就别碰
DEAD_KEYS = ("oxford", "oxfordAdvance", "oxfordAdvanceHtml", "oxfordAdvanceTen", "webster", "senior")

_RE_TAG = re.compile(r"<[^>]+>")
_RE_WS = re.compile(r"[ \t\u00a0]+")
#: 全角 → 半角。**用映射表而不是两个等长字符串** —— 标点数量不一样，
#: ``str.maketrans`` 两串长度不等会直接 ValueError（踩过这个坑）。
_FULLWIDTH_MAP: dict[str, str] = {}
_FULLWIDTH_MAP.update({chr(0xFF10 + i): chr(0x30 + i) for i in range(10)})   # ０-９
_FULLWIDTH_MAP.update({chr(0xFF21 + i): chr(0x41 + i) for i in range(26)})   # Ａ-Ｚ
_FULLWIDTH_MAP.update({chr(0xFF41 + i): chr(0x61 + i) for i in range(26)})   # ａ-ｚ
_FULLWIDTH_MAP.update(
    {"（": "(", "）": ")", "：": ":", "；": ";", "，": ",", "。": ".", "！": "!", "？": "?", "、": ","}
)
_FULLWIDTH = str.maketrans(_FULLWIDTH_MAP)
_RE_CJK = re.compile(r"[\u4e00-\u9fff]")
_RE_MULTI_WS = re.compile(r"\s+")

#: 发音地址（``type=1`` 英音 / ``type=2`` 美音；``type=3`` 会 500）
VOICE_URL = "https://dict.youdao.com/dictvoice?audio={token}"
JSONAPI_URL = "https://dict.youdao.com/jsonapi?q={query}"
SUGGEST_URL = (
    "https://dict.youdao.com/suggest?num={num}&ver=3.0&doctype=json&cache=false&le=en&q={query}"
)


# --------------------------------------------------------------------------- 文本工具
def strip_html(text: str) -> str:
    """去掉 ``<b>`` 这类高亮标签并还原实体（有道例句里常见）。"""
    if not text:
        return ""
    return html.unescape(_RE_TAG.sub("", str(text))).strip()


def normalize(query: str) -> str | None:
    """查询词归一化：全角转半角、压缩空白、转小写。

    **空串返回 ``None``** —— 有道对空串会返回单词 ``null`` 的完整词条，
    必须在本地就拦住（这是实测出来的坑）。
    中文查询不去空格（词内空格有意义）。
    """
    if query is None:
        return None
    text = str(query).translate(_FULLWIDTH)
    text = _RE_WS.sub(" ", text).strip()
    if not text:
        return None
    if _RE_CJK.search(text):
        return text
    return text.lower()


def has_chinese(text: str) -> bool:
    return bool(_RE_CJK.search(text or ""))


def guess_lang(query: str) -> str:
    """粗判语言：含汉字算中文，否则算英文。"""
    return "zh" if has_chinese(query) else "en"


def _as_list(node: Any) -> list:
    """有道响应里同一个键时而是列表、时而是单个对象（``phrs`` 的 ``tr`` 就是单个对象）。

    统一包成列表再迭代 —— 直接 ``for x in dict`` 会迭代出键名，静默丢数据。
    """
    if node is None:
        return []
    if isinstance(node, (list, tuple)):
        return list(node)
    return [node]


def text_of(node: Any) -> str:
    """递归把有道那种「str / list / {``#text``}」混合结构取成一段文本。"""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, (int, float)):
        return str(node)
    if isinstance(node, (list, tuple)):
        return "".join(text_of(x) for x in node)
    if isinstance(node, dict):
        for key in ("#text", "i", "value", "l", "tr", "#tran", "tran", "word", "def"):
            if key in node:
                got = text_of(node[key])
                if got.strip():
                    return got
        return ""
    return ""


def _clean(text: str) -> str:
    return _RE_MULTI_WS.sub(" ", strip_html(text)).strip()


# --------------------------------------------------------------------------- 结果判定
def is_empty_result(raw: Any) -> bool:
    """响应里是不是「查无此词」。"""
    if not raw or not isinstance(raw, dict):
        return True
    meta = raw.get("meta") or {}
    if str(meta.get("isHasSimpleDict", "1")) == "0":
        return True
    return not any(raw.get(k) for k in SUBSTANTIVE_KEYS)


def parse_typos(raw: Any) -> list[str]:
    """拼错的候选词（``typos.typo[].correct`` 或 ``.word``）。"""
    out: list[str] = []
    if not isinstance(raw, dict):
        return out
    typos = (raw.get("typos") or {}).get("typo") or []
    for item in typos:
        if not isinstance(item, dict):
            continue
        for key in ("correct", "word", "text"):
            value = _clean(str(item.get(key, "")))
            if value and value.lower() not in [x.lower() for x in out]:
                out.append(value)
                break
        if len(out) >= 5:
            break
    return out


def parse_suggest(raw: Any) -> list[tuple[str, str]]:
    """``suggest`` 接口的联想结果：``[(词, 解释)]``。"""
    out: list[tuple[str, str]] = []
    if not isinstance(raw, dict):
        return out
    data = raw.get("data") or raw
    for item in data.get("entries") or []:
        if not isinstance(item, dict):
            continue
        entry = _clean(str(item.get("entry", "")))
        explain = _clean(str(item.get("explain", "")))
        if entry:
            out.append((entry, explain))
    return out


# --------------------------------------------------------------------------- 音标 / 发音
def extract_phonetics(raw: Any) -> tuple[str, str]:
    """返回 ``(英音标, 美音标)``；按 ``ec → simple → ee`` 退化。"""
    if not isinstance(raw, dict):
        return "", ""
    for key in ("ec", "simple", "ee", "ce"):
        block = raw.get(key) or {}
        words = block.get("word") or []
        for word in words:
            if not isinstance(word, dict):
                continue
            uk = _clean(str(word.get("ukphone") or ""))
            us = _clean(str(word.get("usphone") or ""))
            if uk or us:
                return uk, us
    return "", ""


def extract_voice_tokens(raw: Any) -> tuple[str, str]:
    """返回 ``(英音 token, 美音 token)``，如 ``hello&type=1``。"""
    if not isinstance(raw, dict):
        return "", ""
    for key in ("ec", "simple", "ee"):
        block = raw.get(key) or {}
        for word in block.get("word") or []:
            if not isinstance(word, dict):
                continue
            uk = str(word.get("ukspeech") or "").strip()
            us = str(word.get("usspeech") or "").strip()
            speech = str(word.get("speech") or "").strip()
            if not uk and not us and speech:
                # 短语没有 ukspeech/usspeech，只有 speech（原词）
                uk = speech
            if uk or us:
                return uk, us
    return "", ""


def build_voice_url(token: str, accent: str = "uk") -> str:
    """把发音 token 拼成可下载的 mp3 地址。

    token 里一般已经带了 ``&type=1``；没有就按口音补上。
    **空格必须编码成 ``+``**（有道接受 ``+`` 或 ``%20``）。
    """
    token = (token or "").strip()
    if not token:
        return ""
    if "&type=" not in token:
        kind = "1" if accent == "uk" else "2"
        token = f"{token}&type={kind}"
    token = token.replace(" ", "+")
    return VOICE_URL.format(token=token)


# --------------------------------------------------------------------------- 释义
def _senses_from_ec(raw: dict) -> list[Sense]:
    """英汉释义（主力）。

    ``ec`` 的 ``trs[].tr[].l`` 里**没有独立的 pos 字段** —— 词性混在正文开头
    （``"int. 喂，你好（…）"``），这里把开头的词性摘出来单独放，界面才能分列显示。
    """
    out: list[Sense] = []
    for word in ((raw.get("ec") or {}).get("word") or []):
        for trs in (word.get("trs") or []) if isinstance(word, dict) else []:
            for tr in (trs.get("tr") or []) if isinstance(trs, dict) else []:
                if not isinstance(tr, dict):
                    continue
                l = tr.get("l") or {}
                pos = _clean(str(l.get("pos", "")))
                text = _clean(text_of(l.get("i")))
                if not text:
                    continue
                if not pos:
                    pos, text = _split_pos_head(text)
                out.append(Sense(pos=pos, definition=text))
    return out


#: ``int.`` / ``n.`` / ``adj.`` / ``vt. & vi.`` 这类开头的词性
_RE_POS_HEAD = re.compile(r"^([A-Za-z]{1,6}\.\s*(?:&\s*[A-Za-z]{1,6}\.)*)\s+(.+)$", re.S)


def _split_pos_head(text: str) -> tuple[str, str]:
    """把 ``"int. 喂，你好"`` 拆成 ``("int.", "喂，你好")``。"""
    match = _RE_POS_HEAD.match(text)
    if not match:
        return "", text
    pos = _RE_MULTI_WS.sub(" ", match.group(1)).strip()
    body = match.group(2).strip()
    if not body:
        return "", text
    return pos, body


def _senses_from_ce(raw: dict) -> list[Sense]:
    """中文词条：``ce.word[].trs[].tr[].l``（``i`` 里会混跳转节点）。"""
    out: list[Sense] = []
    for block_key in ("ce", "ce_new"):
        for word in ((raw.get(block_key) or {}).get("word") or []):
            if not isinstance(word, dict):
                continue
            for trs in word.get("trs") or []:
                for tr in (trs.get("tr") or []) if isinstance(trs, dict) else []:
                    if not isinstance(tr, dict):
                        continue
                    l = tr.get("l") or {}
                    pos = _clean(str(l.get("pos", "")))
                    body = _clean(text_of(l.get("i")))
                    tran = _clean(text_of(l.get("#tran")))
                    text = body or tran
                    if text:
                        out.append(Sense(pos=pos, definition=text))
    return out


def _senses_from_expand(raw: dict) -> list[Sense]:
    out: list[Sense] = []
    for word in ((raw.get("expand_ec") or {}).get("word") or []):
        if not isinstance(word, dict):
            continue
        for trs in word.get("transList") or []:
            if not isinstance(trs, dict):
                continue
            text = _clean(text_of(trs.get("trans")))
            pos = _clean(str(((trs.get("content") or {}) or {}).get("detailPos", "")))
            if text:
                out.append(Sense(pos=pos or _clean(str(word.get("pos", ""))), definition=text))
    return out


def _senses_from_ee(raw: dict) -> list[Sense]:
    """英文释义（维基/英英），质量参差，只在前面的都没有时才用。"""
    out: list[Sense] = []
    for word in ((raw.get("ee") or {}).get("word") or []):
        if not isinstance(word, dict):
            continue
        for trs in word.get("trs") or []:
            pos = _clean(str((trs or {}).get("pos", ""))) if isinstance(trs, dict) else ""
            for tr in (trs.get("tr") or []) if isinstance(trs, dict) else []:
                text = _clean(text_of((tr or {}).get("l"))) if isinstance(tr, dict) else ""
                if text:
                    out.append(Sense(pos=pos, definition=text))
    return out


def _senses_from_newhh(raw: dict) -> list[Sense]:
    """现代汉语规范词典（中文词的兜底）。"""
    out: list[Sense] = []
    for item in ((raw.get("newhh") or {}).get("dataList") or []):
        if not isinstance(item, dict):
            continue
        for sense in item.get("sense") or []:
            if not isinstance(sense, dict):
                continue
            cat = _clean(str(sense.get("cat", "")))
            for definition in sense.get("def") or []:
                text = _clean(text_of(definition))
                if text:
                    out.append(Sense(pos=cat, definition=text))
    return out


def _senses_from_web(raw: dict) -> list[Sense]:
    """网络释义（论坛噪声多，仅兜底，调用方应加提醒）。"""
    out: list[Sense] = []
    for item in ((raw.get("web_trans") or {}).get("web-translation") or []):
        if not isinstance(item, dict):
            continue
        key = _clean(str(item.get("key", "")))
        values = []
        for tr in item.get("trans") or []:
            if isinstance(tr, dict):
                value = _clean(text_of(tr.get("value")))
                if value:
                    values.append(value)
        if values:
            out.append(Sense(pos=key, definition="；".join(values[:3])))
    return out[:3]


def parse_senses(raw: Any) -> list[Sense]:
    """按质量顺序取释义：``ec → ce → expand_ec → newhh → ee → web_trans``。"""
    if not isinstance(raw, dict):
        return []
    for fn in (_senses_from_ec, _senses_from_ce, _senses_from_expand, _senses_from_newhh, _senses_from_ee, _senses_from_web):
        got = fn(raw)
        if got:
            return got
    return []


def senses_are_web_only(raw: Any) -> bool:
    """释义是不是只来自网络释义（界面要标注「网络释义，仅供参考」）。"""
    if not isinstance(raw, dict):
        return False
    if _senses_from_ec(raw) or _senses_from_ce(raw) or _senses_from_expand(raw) or _senses_from_newhh(raw) or _senses_from_ee(raw):
        return False
    return bool(_senses_from_web(raw))


# --------------------------------------------------------------------------- 例句
def _media_audio(item: dict) -> str:
    snippets = ((item.get("snippets") or {}).get("snippet") or []) if isinstance(item, dict) else []
    for snip in snippets:
        if isinstance(snip, dict):
            url = str(snip.get("streamUrl") or snip.get("win8") or "").strip()
            if url:
                return url
    return ""


def parse_sentences(raw: Any, *, limit: int = 12) -> list[Sentence]:
    """收集例句，按「柯林斯 → 双语例句 → 媒体例句 → 真题例句 → 权威例句」的顺序。"""
    if not isinstance(raw, dict):
        return []
    out: list[Sentence] = []
    seen: set[str] = set()

    def add(en: str, zh: str = "", source: str = "", audio: str = "") -> None:
        en = _clean(en)
        if not en:
            return
        key = _RE_MULTI_WS.sub(" ", strip_html(en)).lower()
        if key in seen:
            return
        seen.add(key)
        out.append(Sentence(en=en, zh=_clean(zh), source=source, audio=audio))

    # 1) 柯林斯例句（英文例句 + 词条释义可当参考，这里只取例句原文）
    collins = (raw.get("collins_primary") or {}).get("words") or {}
    if isinstance(collins, dict):
        for cat in collins.get("gramcat") or []:
            if not isinstance(cat, dict):
                continue
            for sense in cat.get("senses") or []:
                if not isinstance(sense, dict):
                    continue
                for example in sense.get("examples") or []:
                    if isinstance(example, dict):
                        add(example.get("example", ""), "", "柯林斯")

    # 2) 双语例句（有中文翻译，质量最高）
    for pair in ((raw.get("blng_sents_part") or {}).get("sentence-pair") or []):
        if not isinstance(pair, dict):
            continue
        add(pair.get("sentence") or pair.get("sentence-eng", ""), pair.get("sentence-translation", ""), _clean(str(pair.get("source", ""))))

    # 3) 媒体例句（带原声音频）
    for item in ((raw.get("media_sents_part") or {}).get("sent") or []):
        if isinstance(item, dict):
            add(item.get("eng", ""), "", "原声", _media_audio(item))

    # 4) 真题例句（``individual.pastExamSents``）
    for item in ((raw.get("individual") or {}).get("pastExamSents") or []):
        if isinstance(item, dict):
            add(item.get("en", ""), item.get("zh", ""), _clean(str(item.get("source", ""))) or "真题")

    # 5) 权威例句（只有英文原文）
    for item in ((raw.get("auth_sents_part") or {}).get("sent") or []):
        if isinstance(item, dict):
            add(item.get("foreign", ""), "", _clean(str(item.get("source", ""))) or "权威例句")

    if limit and len(out) > limit:
        # 优先保留带中文翻译的
        out.sort(key=lambda s: 0 if s.zh else 1)
        out = out[:limit]
    return out


# --------------------------------------------------------------------------- 其他加分项
def parse_word_forms(raw: Any) -> dict[str, str]:
    """词形变化：``ec.word[].wfs[].wf{name, value}``。"""
    forms: dict[str, str] = {}
    if not isinstance(raw, dict):
        return forms
    for word in ((raw.get("ec") or {}).get("word") or []):
        if not isinstance(word, dict):
            continue
        for item in word.get("wfs") or []:
            wf = (item or {}).get("wf") if isinstance(item, dict) else None
            if isinstance(wf, dict):
                name = _clean(str(wf.get("name", "")))
                value = _clean(str(wf.get("value", "")))
                if name and value:
                    forms[name] = value
    return forms


def parse_phrases(raw: Any) -> list[Sense]:
    """短语：``phrs.phrs[].phr{headword, trs}``。

    坑：``ec`` 里 ``trs[].tr`` 是**列表**，而 ``phrs`` 里 ``tr`` 是**单个对象**，
    所以一律走 ``_as_list`` 包一层，不要假设某一侧的形状。
    """
    out: list[Sense] = []
    for item in _as_list((raw.get("phrs") or {}).get("phrs") if isinstance(raw, dict) else None):
        phr = item.get("phr") if isinstance(item, dict) else None
        if not isinstance(phr, dict):
            continue
        head = _clean(text_of((phr.get("headword") or {}).get("l")))
        for trs in _as_list(phr.get("trs")):
            for tr in _as_list(trs.get("tr") if isinstance(trs, dict) else None):
                body = _clean(text_of(tr.get("l"))) if isinstance(tr, dict) else ""
                if head and body:
                    out.append(Sense(pos=head, definition=body))
    return out[:12]


def parse_synonyms(raw: Any) -> list[Sense]:
    """同近义词：``syno.synos[].syno{pos, ws[].w, tran}``。"""
    out: list[Sense] = []
    for item in ((raw.get("syno") or {}).get("synos") or []):
        syno = (item or {}).get("syno") if isinstance(item, dict) else None
        if not isinstance(syno, dict):
            continue
        words = [_clean(text_of(w.get("w"))) for w in syno.get("ws") or [] if isinstance(w, dict)]
        words = [w for w in words if w]
        if not words:
            continue
        tran = _clean(text_of(syno.get("tran")))
        definition = "、".join(words)
        if tran:
            definition = f"{definition} —— {tran}"
        out.append(Sense(pos=_clean(str(syno.get("pos", ""))), definition=definition))
    return out[:8]


def parse_tags(raw: Any) -> list[str]:
    """考试标签：``ec.exam_type`` / ``individual.level``。"""
    tags: list[str] = []
    if not isinstance(raw, dict):
        return tags
    for word in ((raw.get("ec") or {}).get("word") or []):
        if isinstance(word, dict):
            for item in word.get("exam_type") or []:
                value = _clean(str(item))
                if value and value not in tags:
                    tags.append(value)
    level = _clean(str((raw.get("individual") or {}).get("level", "")))
    if level and level not in tags:
        tags.append(level)
    return tags


def parse_etym(raw: Any) -> str:
    """词源：``etym.etyms.zh[].value``。"""
    if not isinstance(raw, dict):
        return ""
    for item in ((raw.get("etym") or {}).get("etyms") or {}).get("zh") or []:
        if isinstance(item, dict):
            value = _clean(text_of(item.get("value")))
            if value:
                return value
    return ""


# --------------------------------------------------------------------------- 总装
def parse_entry(raw: Any, *, query: str = "", limit_sents: int = 12) -> WordEntry:
    """把原始响应装成 :class:`WordEntry`（``found=False`` 表示查无此词）。"""
    norm = normalize(query) or ""
    word = query.strip() if query else ""
    entry = WordEntry(word=word or norm, norm=norm, lang=guess_lang(word or norm))
    entry.src = "youdao"

    if not isinstance(raw, dict):
        entry.found = False
        return entry

    meta = raw.get("meta") or {}
    input_word = _clean(str(meta.get("input", "")))
    if input_word and not word:
        entry.word = input_word
        entry.norm = normalize(input_word) or ""
        entry.lang = guess_lang(input_word)

    entry.trans = parse_senses(raw)
    if not entry.trans and is_empty_result(raw):
        entry.found = False
        entry.suggestions = parse_typos(raw)
        return entry

    entry.phonetic_uk, entry.phonetic_us = extract_phonetics(raw)
    entry.voice_uk, entry.voice_us = extract_voice_tokens(raw)
    entry.sents = parse_sentences(raw, limit=limit_sents)
    entry.forms = parse_word_forms(raw)
    entry.phrases = parse_phrases(raw)
    entry.synonyms = parse_synonyms(raw)
    entry.tags = parse_tags(raw)
    entry.etym = parse_etym(raw)
    entry.fetched_at = int(time.time())
    if senses_are_web_only(raw):
        entry.note = "以上为网络释义，仅供参考。"
    return entry


def entry_from_dict(data: dict) -> WordEntry:
    """缓存/单词本回读（薄封装，便于测试替换）。"""
    return WordEntry.from_dict(data)


def make_missing(query: str, suggestions: list[str] | None = None) -> WordEntry:
    """构造「没收录」的词条（离线兜底和拼错时都用它）。"""
    norm = normalize(query) or ""
    entry = WordEntry(word=query.strip(), norm=norm, lang=guess_lang(query))
    entry.found = False
    entry.suggestions = list(suggestions or [])
    return entry


def make_offline(query: str, trans: list[Sense] | None = None, *, phonetic: str = "") -> WordEntry:
    """构造「离线释义」词条（ECDICT 兜底时用）。"""
    norm = normalize(query) or ""
    entry = WordEntry(word=query.strip(), norm=norm, lang=guess_lang(query))
    entry.offline = True
    entry.src = "ecdict"
    entry.trans = list(trans or [])
    entry.phonetic_uk = phonetic
    entry.note = "当前未联网，以上释义来自本地词库。"
    entry.fetched_at = int(time.time())
    return entry


__all__ = [
    "DEAD_KEYS",
    "JSONAPI_URL",
    "SCHEMA",
    "SUBSTANTIVE_KEYS",
    "SUGGEST_URL",
    "VOICE_URL",
    "build_voice_url",
    "entry_from_dict",
    "extract_phonetics",
    "extract_voice_tokens",
    "guess_lang",
    "has_chinese",
    "is_empty_result",
    "make_missing",
    "make_offline",
    "normalize",
    "parse_entry",
    "parse_etym",
    "parse_phrases",
    "parse_senses",
    "parse_sentences",
    "parse_suggest",
    "parse_synonyms",
    "parse_tags",
    "parse_typos",
    "parse_word_forms",
    "senses_are_web_only",
    "strip_html",
    "text_of",
]
