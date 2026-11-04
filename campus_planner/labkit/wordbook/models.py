"""单词条目的数据模型（纯数据，不碰网络、不碰 Qt）。

字段划分照着「收藏时要在本地保存发音、音标、释义、例句」这条硬需求来：

* 音标：``phonetic_uk`` / ``phonetic_us``
* 发音：``voice_uk`` / ``voice_us``（有道发音 token，可重新拼出 mp3 地址）
        以及 ``audio_files``（口音 → 本地缓存文件相对路径，收藏后离线可播）
* 释义：``trans``（词性 + 释义）
* 例句：``sents``（英文 + 中文 + 出处）

其余字段（词形变化、短语、同近义、考试标签、词源）属于「有就展示」的加分项。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

#: 单词本/查询缓存里的 schema 版本（与文件里的 ``schema`` 字段对应）
SCHEMA = 1


@dataclass
class Sense:
    """一条释义：词性 + 中文解释。"""

    pos: str = ""
    definition: str = ""

    def to_dict(self) -> dict:
        return {"pos": self.pos, "def": self.definition}

    @classmethod
    def from_dict(cls, data: dict) -> "Sense":
        return cls(pos=str(data.get("pos", "")), definition=str(data.get("def", "")))

    def label(self) -> str:
        """给界面用的一行文本，如 ``int. 喂，你好``。"""
        if self.pos and self.definition:
            return f"{self.pos} {self.definition}"
        return self.pos or self.definition


@dataclass
class Sentence:
    """一条例句。``audio`` 只有媒体例句才有（也可为空）。"""

    en: str = ""
    zh: str = ""
    source: str = ""
    audio: str = ""

    def to_dict(self) -> dict:
        data = {"en": self.en, "zh": self.zh}
        if self.source:
            data["src"] = self.source
        if self.audio:
            data["audio"] = self.audio
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Sentence":
        return cls(
            en=str(data.get("en", "")),
            zh=str(data.get("zh", "")),
            source=str(data.get("src", "")),
            audio=str(data.get("audio", "")),
        )

    def label(self) -> str:
        if self.zh:
            return f"{self.en}\n{self.zh}"
        return self.en


@dataclass
class WordEntry:
    """一个词的完整词条。

    ``found=False`` 表示「查到了响应但词典没有这个词」（拼错了或不是词），
    这时候 ``suggestions`` 里会有近似词，界面显示「你是不是想查：…」。
    """

    word: str = ""
    norm: str = ""
    lang: str = "en"
    phonetic_uk: str = ""
    phonetic_us: str = ""
    voice_uk: str = ""
    voice_us: str = ""
    trans: list[Sense] = field(default_factory=list)
    sents: list[Sentence] = field(default_factory=list)
    forms: dict[str, str] = field(default_factory=dict)
    phrases: list[Sense] = field(default_factory=list)
    synonyms: list[Sense] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    etym: str = ""
    note: str = ""
    src: str = "youdao"
    fetched_at: int = 0
    found: bool = True
    offline: bool = False
    suggestions: list[str] = field(default_factory=list)
    #: 口音 -> 本地 mp3 相对路径（相对 lab/_data/audio），收藏后离线可播
    audio_files: dict[str, str] = field(default_factory=dict)
    #: 原始响应的字节数，仅用于自检/调试
    raw_size: int = 0

    # ------------------------------------------------------------------ 便捷属性
    @property
    def phonetic(self) -> str:
        """界面顶部显示：优先英音，退美音。"""
        return self.phonetic_uk or self.phonetic_us

    @property
    def has_audio(self) -> bool:
        return bool(self.voice_uk or self.voice_us)

    @property
    def is_chinese(self) -> bool:
        return self.lang == "zh"

    def phonetic_line(self, accent: str = "uk") -> str:
        """``英 [həˈləʊ]  美 [həˈloʊ]`` 这样的双语对照行。"""
        parts = []
        if self.phonetic_uk:
            parts.append(f"英 [{self.phonetic_uk}]")
        if self.phonetic_us:
            parts.append(f"美 [{self.phonetic_us}]")
        return "  ".join(parts)

    def voice_token(self, accent: str) -> str:
        """取某口音的发音 token（``hello&type=1``）。"""
        return self.voice_uk if accent == "uk" else self.voice_us

    def local_audio(self, accent: str) -> str:
        return self.audio_files.get(accent, "")

    def summary(self, limit: int = 3) -> str:
        """一行摘要，用于列表/表格。"""
        if not self.found:
            return "（未收录）"
        texts = [s.label() for s in self.trans[:limit]]
        return "；".join(texts) if texts else "（无释义）"

    # ------------------------------------------------------------------ 序列化
    def to_dict(self) -> dict:
        data: dict[str, Any] = {
            "word": self.word,
            "norm": self.norm or self.word,
            "lang": self.lang,
            "schema": SCHEMA,
            "trans": [s.to_dict() for s in self.trans],
        }
        if self.phonetic_uk or self.phonetic_us:
            data["phonetic"] = {"uk": self.phonetic_uk, "us": self.phonetic_us}
        if self.voice_uk or self.voice_us:
            data["voice"] = {"uk": self.voice_uk, "us": self.voice_us}
        if self.sents:
            data["sents"] = [s.to_dict() for s in self.sents]
        if self.forms:
            data["forms"] = dict(self.forms)
        if self.phrases:
            data["phrs"] = [s.to_dict() for s in self.phrases]
        if self.synonyms:
            data["syno"] = [s.to_dict() for s in self.synonyms]
        if self.tags:
            data["tags"] = list(self.tags)
        if self.etym:
            data["etym"] = self.etym
        if self.note:
            data["note"] = self.note
        if self.audio_files:
            data["audio"] = dict(self.audio_files)
        data["src"] = self.src
        data["fetched_at"] = self.fetched_at
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "WordEntry":
        phones = data.get("phonetic") or {}
        voices = data.get("voice") or {}
        entry = cls(
            word=str(data.get("word", "")),
            norm=str(data.get("norm", "") or data.get("word", "")),
            lang=str(data.get("lang", "en")),
            phonetic_uk=str(phones.get("uk", "")),
            phonetic_us=str(phones.get("us", "")),
            voice_uk=str(voices.get("uk", "")),
            voice_us=str(voices.get("us", "")),
            trans=[Sense.from_dict(x) for x in (data.get("trans") or []) if isinstance(x, dict)],
            sents=[Sentence.from_dict(x) for x in (data.get("sents") or []) if isinstance(x, dict)],
            forms={str(k): str(v) for k, v in (data.get("forms") or {}).items()},
            phrases=[Sense.from_dict(x) for x in (data.get("phrs") or []) if isinstance(x, dict)],
            synonyms=[Sense.from_dict(x) for x in (data.get("syno") or []) if isinstance(x, dict)],
            tags=[str(t) for t in (data.get("tags") or [])],
            etym=str(data.get("etym", "")),
            note=str(data.get("note", "")),
            src=str(data.get("src", "youdao")),
            fetched_at=int(data.get("fetched_at", 0) or 0),
            audio_files={str(k): str(v) for k, v in (data.get("audio") or {}).items()},
        )
        return entry


def diff_fields(old: WordEntry | None, new: WordEntry) -> list[str]:
    """新词条相比旧词条多了什么（用于「重新查询后更新」的提示）。"""
    if old is None:
        return ["新增"]
    changed: list[str] = []
    if (old.phonetic_uk, old.phonetic_us) != (new.phonetic_uk, new.phonetic_us):
        changed.append("音标")
    if [s.label() for s in old.trans] != [s.label() for s in new.trans]:
        changed.append("释义")
    if len(new.sents) > len(old.sents):
        changed.append(f"例句 +{len(new.sents) - len(old.sents)}")
    if new.forms != old.forms:
        changed.append("词形")
    return changed


def sort_entries(entries: Iterable[WordEntry], key: str = "added") -> list[WordEntry]:
    """单词本排序：``added``（添加时间，倒序）/ ``alpha`` / ``seen``。"""
    items = list(entries)
    if key == "alpha":
        return sorted(items, key=lambda e: (e.norm or e.word).lower())
    if key == "seen":
        return sorted(items, key=lambda e: e.fetched_at, reverse=True)
    return sorted(items, key=lambda e: e.fetched_at, reverse=True)
