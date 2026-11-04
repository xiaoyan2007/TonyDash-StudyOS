"""发音播放与后台线程。

两件事：

* :class:`AudioPlayer` —— 包一层 ``QMediaPlayer``，能播本地 mp3，也能直接流播网址；
  没有 QtMultimedia 时**优雅降级**（``available()`` 为假，界面隐藏播放按钮，不报错）。
* :class:`LookupWorker` / :class:`AudioFetchWorker` —— 把「联网查词」「下载发音」
  放到后台线程，界面不卡（网络抖动时尤其明显）。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, QUrl, Signal


def media_available() -> tuple[bool, str]:
    """``(能否播放, 说明)``。"""
    try:
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer  # noqa: F401
    except Exception as exc:  # noqa: BLE001 - 任何导入失败都算不可用
        return False, f"当前环境没有 QtMultimedia（{type(exc).__name__}），发音播放不可用"
    return True, ""


class AudioPlayer(QObject):
    """播放发音。**懒惰导入 QtMultimedia**，没装也 import 得动。"""

    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ok, self._why = media_available()
        self._player = None
        self._output = None

    def available(self) -> bool:
        return self._ok

    def reason(self) -> str:
        return self._why

    def _ensure(self) -> bool:
        if not self._ok:
            return False
        if self._player is None:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

            self._player = QMediaPlayer(self)
            self._output = QAudioOutput(self)
            self._player.setAudioOutput(self._output)
            self._player.setVolume(0.9)
            self._player.errorOccurred.connect(self._on_error)
        return True

    def _on_error(self, *_args) -> None:
        message = self._player.errorString() if self._player is not None else ""
        self.failed.emit(message or "发音播放失败")

    def play_file(self, path: str | Path) -> bool:
        path = Path(path)
        if not path.exists():
            self.failed.emit(f"找不到发音文件：{path}")
            return False
        return self._play(QUrl.fromLocalFile(str(path.resolve())))

    def play_url(self, url: str) -> bool:
        if not url:
            return False
        return self._play(QUrl(url))

    def _play(self, url: QUrl) -> bool:
        if not self._ensure():
            self.failed.emit(self._why)
            return False
        self._player.stop()
        self._player.setSource(url)
        self._player.play()
        return True

    def stop(self) -> None:
        if self._player is not None:
            self._player.stop()


class LookupWorker(QThread):
    """后台查词：``done`` 一定带一个 ``LookupResult``（异常也包成结果，界面不用 try）。

    ``progress(int 百分比, str 说明)`` 从后台线程发出，主线程排队接收后刷新进度条，
    网络抖动时界面也能看到进度在走，而不是卡在一句静态文案上。
    """

    done = Signal(object)
    progress = Signal(int, str)

    def __init__(self, service, query: str, *, use_cache: bool = True, parent=None):
        super().__init__(parent)
        self.service = service
        self.query = query
        self.use_cache = use_cache

    def run(self) -> None:  # noqa: D102 - QThread 入口
        from ..wordbook.service import LookupResult

        def report(pct, text):
            self.progress.emit(int(pct), str(text))

        try:
            result = self.service.lookup(self.query, use_cache=self.use_cache,
                                         on_progress=report)
        except Exception as exc:  # noqa: BLE001 - 兜底：绝不让线程异常冒到 Qt 层
            result = LookupResult(error=f"查询出错：{type(exc).__name__}: {exc}")
        self.done.emit(result)


class AudioFetchWorker(QThread):
    """后台把某个口音的发音落到本地，然后回报绝对路径（拿不到就回报空串）。"""

    done = Signal(str, str)  # (accent, 本地绝对路径 或 "")
    progress = Signal(int, str)

    def __init__(self, service, entry, accent: str, parent=None):
        super().__init__(parent)
        self.service = service
        self.entry = entry
        self.accent = accent

    def run(self) -> None:  # noqa: D102 - QThread 入口
        rel = ""

        def report(pct, text):
            self.progress.emit(int(pct), str(text))

        try:
            files = self.service.ensure_audio(self.entry, accents=(self.accent,),
                                              on_progress=report)
            rel = (files or {}).get(self.accent, "")
            if not rel:
                kind, value = self.service.audio_source(self.entry, self.accent)
                self.done.emit(self.accent, "" if kind != "file" else value)
                return
            path = self.service.audio.resolve(rel)
            self.done.emit(self.accent, str(path) if path else "")
        except Exception:  # noqa: BLE001 - 下载失败不是致命错误，静默降级
            self.done.emit(self.accent, "")


class SaveWorker(QThread):
    """后台收藏（顺带下载发音）。"""

    done = Signal(bool, str)
    progress = Signal(int, str)

    def __init__(self, service, entry, *, want_audio: bool = True, parent=None):
        super().__init__(parent)
        self.service = service
        self.entry = entry
        self.want_audio = want_audio

    def run(self) -> None:  # noqa: D102 - QThread 入口
        def report(pct, text):
            self.progress.emit(int(pct), str(text))

        try:
            is_new, message = self.service.add(self.entry, want_audio=self.want_audio,
                                               on_progress=report)
        except Exception as exc:  # noqa: BLE001
            is_new, message = False, f"收藏失败：{type(exc).__name__}: {exc}"
        self.done.emit(is_new, message)


class AudioPlayback(QObject):
    """「点一下喇叭就出声」的完整链路：本地有就播本地，没有就后台下载再播。

    两个页面共用：查询页拿到的是没收藏的词（本地没 mp3），单词本页拿到的是收藏过的
    词（本地已经有）。无论哪种，用户看到的行为都一样。
    """

    failed = Signal(str)
    played = Signal(str)  # accent

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.player = AudioPlayer(self)
        self.player.failed.connect(self.failed.emit)
        self._workers: list[QThread] = []

    def local_path(self, entry, accent: str) -> str:
        rel = (getattr(entry, "audio_files", None) or {}).get(accent, "")
        if not rel:
            return ""
        path = self.service.audio.resolve(rel)
        return str(path) if path and Path(path).exists() else ""

    def play(self, entry, accent: str = "uk") -> None:
        if entry is None:
            return
        path = self.local_path(entry, accent)
        if path:
            if self.player.play_file(path):
                self.played.emit(accent)
            return
        if not entry.voice_token(accent):
            self.failed.emit("这个词条没有该口音的发音")
            return
        worker = AudioFetchWorker(self.service, entry, accent, self)
        worker.done.connect(self._on_fetched)
        worker.finished.connect(lambda w=worker: self._forget(w))
        self._workers.append(worker)
        worker.start()

    def _on_fetched(self, accent: str, path: str) -> None:
        if path:
            if self.player.play_file(path):
                self.played.emit(accent)
        else:
            self.failed.emit("发音下载失败（检查网络或稍后再试）")

    def _forget(self, worker: QThread) -> None:
        if worker in self._workers:
            self._workers.remove(worker)

    def play_sentence(self, audio: str) -> None:
        """例句音频：网址直放，``token`` 拼成 dictvoice 网址。"""
        from ..wordbook import parser as P

        if not audio:
            return
        url = audio if audio.startswith("http") else P.build_voice_url(audio, "uk")
        if not self.player.play_url(url):
            self.failed.emit("这句例句没有可播放的音频")

    def stop(self) -> None:
        self.player.stop()


__all__ = [
    "AudioFetchWorker",
    "AudioPlayback",
    "AudioPlayer",
    "LookupWorker",
    "SaveWorker",
    "media_available",
]
