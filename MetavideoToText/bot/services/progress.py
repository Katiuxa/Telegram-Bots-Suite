import logging
import time
from collections.abc import Callable
from typing import Any

from telegram import Message

from bot.i18n_progress import (
    is_downloading_label,
    is_live_transcribe_label,
    is_transcribing_compact,
    prog,
)

logger = logging.getLogger(__name__)

BAR_LEN = 16

ProgressCallback = Callable[[int, str, str], None]


def _bar(percent: int) -> str:
    p = max(0, min(100, percent))
    filled = round(BAR_LEN * p / 100)
    return "█" * filled + "░" * (BAR_LEN - filled)


def format_bytes(num: int | float | None) -> str:
    if not num:
        return "0 B"
    n = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def format_speed(speed: float | None) -> str:
    if not speed or speed <= 0:
        return ""
    return f" · {format_bytes(speed)}/s"


class ProgressReporter:
    """Barra con porcentaje real (descarga, trozos, etc.)."""

    def __init__(
        self, message: Message, title: str, *, show_cancel: bool = False, lang: str = "es"
    ) -> None:
        self.message = message
        self.title = title
        self._lang = lang
        self.percent = 0
        self._label = prog("starting", lang)
        self._sub = ""
        self._last_edit = 0.0
        self._last_pct = -1
        self._last_sub_shown = ""
        self._show_cancel = show_cancel
        self._bot = message.get_bot()
        self._chat_id = message.chat_id

    def p(self, key: str, **kwargs) -> str:
        return prog(key, self._lang, **kwargs)

    @classmethod
    def audio(
        cls, message: Message, *, show_cancel: bool = True, lang: str = "es"
    ) -> "ProgressReporter":
        from bot.i18n import t

        return cls(message, t("progress_audio", lang), show_cancel=show_cancel, lang=lang)

    @classmethod
    def video(
        cls, message: Message, *, show_cancel: bool = True, lang: str = "es"
    ) -> "ProgressReporter":
        from bot.i18n import t

        return cls(message, t("progress_video", lang), show_cancel=show_cancel, lang=lang)

    @classmethod
    def link(
        cls, message: Message, *, youtube: bool = False, lang: str = "es"
    ) -> "ProgressReporter":
        from bot.i18n import t

        return cls(message, t("progress_link", lang), show_cancel=True, lang=lang)

    @classmethod
    def mp3_only(cls, message: Message, lang: str = "es") -> "ProgressReporter":
        from bot.i18n import t

        return cls(message, t("progress_mp3_only", lang), show_cancel=True, lang=lang)

    @classmethod
    def summary(cls, message: Message, lang: str = "es") -> "ProgressReporter":
        from bot.i18n import t

        return cls(message, t("progress_summary", lang), show_cancel=False, lang=lang)

    @classmethod
    def export(
        cls, message: Message, kind: str = "Archivo", lang: str = "es"
    ) -> "ProgressReporter":
        return cls(message, kind, show_cancel=False, lang=lang)

    def _reply_markup(self, *, finished: bool = False):
        if finished or not self._show_cancel:
            return None
        from bot.keyboards import cancel_job_keyboard

        return cancel_job_keyboard(self._lang)

    def _render(self) -> str:
        # Sin _cursiva_: si Markdown falla, el fallback dejaba "_Transcribiendo_" visible.
        if is_transcribing_compact(self._label, self._sub):
            return (
                f"⏳ *{self.title}*\n\n"
                f"{_bar(self.percent)}  *{self.percent}%*\n\n"
                f"📌 {self._label}"
            )
        lines = [
            f"⏳ *{self.title}*",
            "",
            f"{_bar(self.percent)}  *{self.percent}%*",
            "",
            f"📌 {self._label}",
        ]
        if self._sub:
            lines.append(f"↳ {self._sub}")
        return "\n".join(lines)

    @staticmethod
    def _plain_progress(text: str) -> str:
        """Quita marcas Markdown (*negrita*, _cursiva_) para reintento sin parse_mode."""
        return text.replace("*", "").replace("_", "")

    async def _show(self, *, force: bool = False) -> None:
        now = time.monotonic()
        pct_jump = abs(self.percent - self._last_pct) >= 2
        live = is_live_transcribe_label(self._label)
        compact = is_transcribing_compact(self._label, self._sub)
        downloading = is_downloading_label(self._label)
        sub_jump = self._sub != self._last_sub_shown
        if downloading:
            min_gap = 2.2
        elif compact:
            min_gap = 0.75
        elif live:
            min_gap = 1.0
        else:
            min_gap = 1.3
        if (
            not force
            and not pct_jump
            and not (live and sub_jump)
            and now - self._last_edit < min_gap
        ):
            return
        self._last_edit = now
        self._last_pct = self.percent
        self._last_sub_shown = self._sub
        text = self._render()
        markup = self._reply_markup()
        try:
            await self.message.edit_text(
                text, parse_mode="Markdown", reply_markup=markup
            )
        except Exception:
            try:
                await self.message.edit_text(
                    self._plain_progress(text), reply_markup=markup
                )
            except Exception as e:
                logger.debug("Progreso no editado: %s", e)

    async def set_real(
        self, percent: int, label: str, sub: str = "", *, force: bool = False
    ) -> None:
        self.percent = max(0, min(99 if percent < 100 else 100, int(percent)))
        self._label = label
        self._sub = sub
        await self._show(force=force)

    async def pulse(self, sub: str, *, force: bool = False) -> None:
        self._sub = sub
        await self._show(force=force)

    async def advance(self, detail: str | None = None, *, force: bool = False) -> None:
        self.percent = min(99, self.percent + 8)
        if detail:
            self._label = detail
        await self._show(force=force)

    async def update(self, detail: str, *, force: bool = False) -> None:
        await self.advance(detail, force=force)

    async def done(self, summary: str) -> None:
        self.percent = 100
        text = f"✅ *{self.title}*\n\n{_bar(100)}  *100%*\n\n{summary}"
        try:
            await self.message.edit_text(
                text, parse_mode="Markdown", reply_markup=self._reply_markup(finished=True)
            )
        except Exception:
            try:
                await self.message.edit_text(
                    f"✅ {self.title}\n\n100%\n\n{summary}",
                    reply_markup=None,
                )
            except Exception:
                pass

    async def fail(self, summary: str, detail: str = "", *, markdown: bool = True) -> None:
        text = f"❌ *{self.title}*\n\n{_bar(self.percent)}  {self.percent}%\n\n{summary}"
        if detail:
            text += f"\n\n{detail[:1200]}"
        markup = self._reply_markup(finished=True)
        if markdown:
            try:
                await self.message.edit_text(
                    text[:4000],
                    parse_mode="Markdown",
                    reply_markup=markup,
                )
                return
            except Exception:
                pass
        plain = text[:4000].replace("*", "")
        try:
            await self.message.edit_text(plain, reply_markup=markup)
        except Exception:
            logger.debug("Progreso fail no editado")

    async def cancelled(self) -> None:
        text = f"🛑 *{self.title}*\n\n{prog('cancelled_body', self._lang)}"
        try:
            await self.message.edit_text(
                text, parse_mode="Markdown", reply_markup=None
            )
        except Exception:
            try:
                await self.message.edit_text(text.replace("*", ""), reply_markup=None)
            except Exception:
                pass


def thread_safe_callback(
    loop: Any,
    reporter: ProgressReporter,
    cancel_event: Any = None,
) -> ProgressCallback:
    def cb(percent: int, label: str, sub: str = "") -> None:
        if cancel_event is not None and cancel_event.is_set():
            return
        asyncio = __import__("asyncio")
        try:
            asyncio.run_coroutine_threadsafe(
                reporter.set_real(percent, label, sub), loop
            )
        except Exception as e:
            logger.debug("Callback progreso: %s", e)

    return cb


def make_ytdlp_progress_hook(
    callback: ProgressCallback | None,
    *,
    pct_start: int = 8,
    pct_end: int = 48,
    cancel_event: Any = None,
    lang: str = "es",
) -> Callable[[dict], None]:
    from yt_dlp.utils import DownloadCancelled

    def hook(data: dict) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise DownloadCancelled(prog("download_cancelled", lang))
        if not callback:
            return
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes") or 0
            speed = data.get("speed")
            if total > 0:
                inner = done / total
                pct = pct_start + int(inner * (pct_end - pct_start))
                sub = prog(
                    "download_sub_of",
                    lang,
                    done=format_bytes(done),
                    total=format_bytes(total),
                    speed=format_speed(speed),
                )
                callback(pct, prog("downloading", lang), sub)
            else:
                eta = data.get("eta")
                sub = prog(
                    "download_sub_partial",
                    lang,
                    done=format_bytes(done),
                    speed=format_speed(speed),
                )
                if eta is not None:
                    sub += prog("download_sub_eta", lang, eta=int(eta))
                callback(pct_start, prog("downloading", lang), sub)
        elif status in ("processing", "postprocessing"):
            callback(
                pct_end - 1,
                prog("converting_audio", lang),
                prog("converting_audio_sub", lang),
            )
        elif status == "finished":
            callback(pct_end, prog("download_ready", lang), "")

    return hook
