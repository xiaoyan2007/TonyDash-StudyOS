"""有道接口客户端 —— **整个功能里唯一出网的地方**。

只用标准库 ``urllib``（不引入 requests），理由：主程序是纯本地零依赖应用，
新功能也要能在没有第三方包的环境里跑起来；``urllib`` 默认读取系统代理环境变量，
VPN/代理场景不需要额外配置。

实测结论（都已体现在代码里）：

* 有道这一组接口**无鉴权、无风控门槛**：裸请求 / Chrome UA / 带不带 Referer
  返回的字节完全一样；只有 ``Accept-Encoding: gzip`` 能省传输量（52KB → 33KB）；
* ``dictvoice?type=3`` 会 500；``type=1`` 英音、``type=2`` 美音；
  同一次失败**换口音重试一次**是值得的（口音覆盖不对称）；
* 限速取保守值：≤2 次/秒、并发 ≤4（实测 20 连发也没被拦，但没必要试探）；
* 超时：连接/读取都按 10 秒算，失败按 0.5s / 1.5s / 4s 退避重试 ≤3 次。
"""

from __future__ import annotations

import gzip
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import parser as P
from .models import WordEntry

#: 有道对普通浏览器 UA 与裸请求一视同仁，这里给个正常的 UA 便于排查日志
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

#: 退避序列（秒）：第 1 次失败等 0.5s，第 2 次 1.5s，第 3 次 4s
BACKOFF = (0.5, 1.5, 4.0)


class YoudaoError(RuntimeError):
    """网络层异常（超时、HTTP 错误、JSON 解析失败）。"""

    def __init__(self, message: str, *, status: int = 0) -> None:
        super().__init__(message)
        self.status = int(status)


class YoudaoClient:
    """线程安全的轻量客户端（可以在 QThread 里直接用）。"""

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        retries: int = 3,
        min_interval: float = 0.5,
        user_agent: str = DEFAULT_UA,
    ) -> None:
        self.timeout = float(timeout)
        self.retries = max(0, int(retries))
        self.min_interval = max(0.0, float(min_interval))
        self.user_agent = user_agent
        self._lock = threading.Lock()
        self._last_call = 0.0
        self.stats = {"requests": 0, "errors": 0, "bytes": 0, "voice": 0}

    # ------------------------------------------------------------------ 底层
    def _throttle(self) -> None:
        """全局节流：两次请求之间至少间隔 ``min_interval`` 秒。"""
        if self.min_interval <= 0:
            return
        with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def _open(self, url: str, *, accept: str) -> tuple[bytes, int]:
        if not url.lower().startswith(("http://", "https://")):
            raise YoudaoError(f"不支持的地址：{url!r}")
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Referer": "https://dict.youdao.com/",
                "Accept": accept,
                "Accept-Encoding": "gzip",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = resp.read()
            if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
                try:
                    body = gzip.decompress(body)
                except OSError:
                    pass
            return body, int(getattr(resp, "status", 200) or 200)

    def _request(self, url: str, *, accept: str, what: str) -> bytes:
        """带节流 + 退避重试的 GET。"""
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            self._throttle()
            try:
                body, status = self._open(url, accept=accept)
                if status >= 400:
                    raise YoudaoError(f"{what} 返回 HTTP {status}", status=status)
                with self._lock:
                    self.stats["requests"] += 1
                    self.stats["bytes"] += len(body)
                return body
            except YoudaoError as exc:
                last = exc
                # 4xx（除了 429）重试没有意义
                if 400 <= exc.status < 500 and exc.status != 429:
                    break
            except urllib.error.HTTPError as exc:
                last = YoudaoError(f"{what} 返回 HTTP {exc.code}", status=int(exc.code))
                if 400 <= int(exc.code) < 500 and int(exc.code) != 429:
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = YoudaoError(f"{what} 连接失败：{exc}")
            if attempt < self.retries:
                time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
        with self._lock:
            self.stats["errors"] += 1
        raise last if last is not None else YoudaoError(f"{what} 失败")

    # ------------------------------------------------------------------ 查询
    def query_json(self, word: str) -> dict:
        """取原始 JSON（``jsonapi``）。

        **空查询在本地就拒绝**：有道对空串会返回单词 ``null`` 的完整词条。
        """
        norm = P.normalize(word)
        if not norm:
            raise YoudaoError("查询内容为空")
        url = P.JSONAPI_URL.format(query=urllib.parse.quote(norm))
        body = self._request(url, accept="application/json", what="查询")
        try:
            raw = json.loads(body.decode("utf-8", "replace"))
        except (json.JSONDecodeError, ValueError) as exc:
            raise YoudaoError(f"返回内容不是 JSON：{exc}") from exc
        if not isinstance(raw, dict):
            raise YoudaoError("返回内容格式异常")
        return raw

    def query(self, word: str, *, limit_sents: int = 12) -> WordEntry:
        """查询并解析成 :class:`WordEntry`。"""
        raw = self.query_json(word)
        entry = P.parse_entry(raw, query=word, limit_sents=limit_sents)
        entry.raw_size = len(json.dumps(raw, ensure_ascii=False))
        return entry

    def suggest(self, word: str, *, num: int = 5) -> list[tuple[str, str]]:
        """联想/纠错：``[(词, 解释)]``。失败时返回空列表（联想不该让人看到报错）。"""
        norm = P.normalize(word)
        if not norm:
            return []
        url = P.SUGGEST_URL.format(num=int(num), query=urllib.parse.quote(norm))
        try:
            body = self._request(url, accept="application/json", what="联想")
            raw = json.loads(body.decode("utf-8", "replace"))
        except (YoudaoError, ValueError):
            return []
        return P.parse_suggest(raw)

    # ------------------------------------------------------------------ 发音
    def fetch_voice(self, token: str, accent: str = "uk") -> bytes | None:
        """下载发音 mp3。

        某个口音 500 是**正常的**（覆盖不对称），所以调用方失败后应换口音再试一次；
        这里返回 ``None`` 而不是抛异常，方便「能播就播，不能播就隐藏按钮」。
        """
        url = P.build_voice_url(token, accent)
        if not url:
            return None
        try:
            body = self._request(url, accept="audio/mpeg,*/*", what="发音")
        except YoudaoError:
            return None
        if not body or len(body) < 256:
            return None
        with self._lock:
            self.stats["voice"] += 1
        return body

    def fetch_voice_any(self, entry: WordEntry, accents: tuple[str, ...] = ("uk", "us")) -> tuple[str, bytes] | None:
        """依次尝试多个口音，返回 ``(口音, mp3 字节)``。"""
        for accent in accents:
            token = entry.voice_token(accent)
            if not token:
                continue
            data = self.fetch_voice(token, accent)
            if data:
                return accent, data
        return None

    # ------------------------------------------------------------------ 收尾
    def close(self) -> None:
        """urllib 没有连接池，留个空实现方便以后换成 requests.Session。"""

    def describe(self) -> str:
        s = self.stats
        return f"请求 {s['requests']} 次（{s['bytes'] / 1024:.0f} KB），发音 {s['voice']} 个，失败 {s['errors']} 次"
