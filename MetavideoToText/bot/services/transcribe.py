import logging
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable

import httpx

from bot.config import (
    GROQ_API_KEY,
    GROQ_API_KEYS,
    GROQ_WHISPER_MODEL,
    HF_API_TOKEN,
    TRANSCRIBE_GROQ_ONLY,
    TRANSCRIBE_PARALLEL_CHUNKS,
)
from bot.services.audio_chunks import cleanup_chunks, split_wav_for_transcription
from bot.i18n_progress import prog
from bot.services.transcript_lang import (
    hf_language,
    is_auto_detect,
    normalize_transcript_lang,
    whisper_language,
    whisper_prompt,
)

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
HF_URL = "https://api-inference.huggingface.co/models/openai/whisper-large-v3"


class TranscriptionError(Exception):
    pass


class JobCancelled(Exception):
    pass


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


def wav_duration_sec(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            rate = w.getframerate() or 16000
            return w.getnframes() / float(rate)
    except Exception:
        return 0.0


class TranscribeLiveProgress:
    """Avance efímero por tiempo de audio; se omite en archivos muy cortos."""

    MIN_DURATION_SEC = 7.0
    MIN_WAV_BYTES = 140_000
    MIN_UPDATE_GAP = 0.85
    CLOUD_PULSE_GAP = 1.4

    def __init__(
        self,
        callback: Callable[[int, str, str], None] | None,
        *,
        total_sec: float,
        wav_bytes: int,
        pct_start: int = 55,
        pct_end: int = 89,
        timeline_offset: float = 0.0,
        chunk_index: int = 0,
        chunk_count: int = 1,
        lang: str = "es",
    ) -> None:
        self._lang = normalize_transcript_lang(lang)
        self._cb = callback
        self.total_sec = max(total_sec, 0.1)
        self.pct_start = pct_start
        self.pct_end = pct_end
        self.timeline_offset = timeline_offset
        self.chunk_index = chunk_index
        self.chunk_count = max(chunk_count, 1)
        self.live = bool(
            callback
            and total_sec >= self.MIN_DURATION_SEC
            and wav_bytes >= self.MIN_WAV_BYTES
        )
        self._last_emit = 0.0
        self._segments_seen = 0

    def _emit(self, pct: int, label: str, sub: str) -> None:
        if self._cb:
            self._cb(pct, label, sub)

    def _pct_at(self, t: float) -> int:
        t = max(0.0, min(t, self.total_sec))
        if self.chunk_count > 1:
            frac = (self.chunk_index + t / self.total_sec) / self.chunk_count
        else:
            frac = t / self.total_sec
        return self.pct_start + int((self.pct_end - self.pct_start) * frac)

    def engine(self, name: str) -> None:
        del name
        if not self._cb:
            return
        self._emit(self.pct_start, prog("transcribing", self._lang), "")

    def segment(self, seg: TranscriptSegment) -> None:
        if not self.live:
            return
        now = time.monotonic()
        if now - self._last_emit < self.MIN_UPDATE_GAP:
            return
        self._last_emit = now
        self._segments_seen += 1
        self._emit(self._pct_at(seg.end), prog("transcribing", self._lang), "")

    def cloud_pulse(self, elapsed: float) -> None:
        if not self.live:
            return
        now = time.monotonic()
        if now - self._last_emit < self.CLOUD_PULSE_GAP:
            return
        self._last_emit = now
        estimate = max(self.total_sec * 0.45, 10.0)
        frac = min(0.9, elapsed / estimate)
        pct = self.pct_start + int((self.pct_end - self.pct_start - 10) * frac)
        self._emit(pct, prog("transcribing", self._lang), "")

    def flush_segments(self, segments: list[TranscriptSegment]) -> None:
        if not self._cb:
            return
        if not self.live:
            self._emit(self.pct_end - 4, prog("transcribing", self._lang), "")
            return
        for seg in segments:
            self.segment(seg)
        if segments:
            self._emit(self.pct_end - 3, prog("transcribing_almost", self._lang), "")


def _detected_from_payload(payload: dict, *, fallback: str = "") -> str:
    raw = (payload.get("language") or fallback or "").strip().lower()
    return raw[:2] if raw else ""


def _whisper_keys() -> list[str]:
    keys: list[str] = []
    for k in list(GROQ_API_KEYS or []) + ([GROQ_API_KEY] if GROQ_API_KEY else []):
        if k and k not in keys:
            keys.append(k)
    return keys


def _groq(
    wav_path: Path,
    live: TranscribeLiveProgress | None = None,
    *,
    language: str = "es",
) -> tuple[list[TranscriptSegment], str]:
    keys = _whisper_keys()
    if not keys:
        raise TranscriptionError(prog("transcription_service_unavailable", language))
    # None = auto-detect; "es"/"en"/"fr"/"ru" = idioma forzado por el usuario
    lang_code = whisper_language(language)
    forced = bool(lang_code)
    logger.info(
        "Whisper Groq: language=%s mode=%s file=%s keys=%s",
        lang_code or "auto",
        "forced" if forced else "detect",
        wav_path.name,
        len(keys),
    )
    data = {
        "model": GROQ_WHISPER_MODEL or "whisper-large-v3",
        "response_format": "verbose_json",
        "timestamp_granularities[]": "segment",
        "temperature": "0",
    }
    if lang_code:
        data["language"] = lang_code

    r = None
    last_status = 0
    key_i = 0
    for attempt in range(8):
        api_key = keys[key_i % len(keys)]
        headers = {"Authorization": f"Bearer {api_key}"}
        with wav_path.open("rb") as f:
            files = {"file": (wav_path.name, f, "audio/wav")}
            stop = threading.Event()

            def _pulse() -> None:
                if not live:
                    return
                t0 = time.monotonic()
                while not stop.wait(live.CLOUD_PULSE_GAP):
                    live.cloud_pulse(time.monotonic() - t0)

            waiter = threading.Thread(target=_pulse, daemon=True)
            waiter.start()
            try:
                r = httpx.post(
                    GROQ_URL, files=files, data=data, headers=headers, timeout=300.0
                )
            finally:
                stop.set()
                waiter.join(timeout=0.5)
        last_status = r.status_code
        if r.status_code == 200:
            break
        if r.status_code == 429:
            # Vídeos largos: rotar cuenta Groq antes de esperar
            if len(keys) > 1:
                key_i += 1
                logger.warning(
                    "Groq Whisper 429, otra clave (%s/%s) — %s",
                    (key_i % len(keys)) + 1,
                    len(keys),
                    wav_path.name,
                )
                time.sleep(0.4)
                continue
            wait = 8.0 * (attempt + 1)
            try:
                wait = float(r.headers.get("retry-after") or wait)
            except ValueError:
                pass
            wait = min(max(wait, 3.0), 60.0)
            logger.warning(
                "Groq Whisper 429 (intento %s/8), esperando %.1fs — %s",
                attempt + 1,
                wait,
                wav_path.name,
            )
            time.sleep(wait)
            continue
        break

    if r is None or r.status_code != 200:
        logger.error(
            "Groq Whisper falló status=%s file=%s body=%s",
            last_status,
            wav_path.name,
            (r.text[:240] if r is not None else ""),
        )
        raise TranscriptionError(prog("transcription_failed_audio", language))
    payload = r.json()
    segs = payload.get("segments") or []
    from bot.services.whisper_quality import filter_segment_dicts

    segs = filter_segment_dicts(segs, lang=language)
    out: list[TranscriptSegment] = []
    for s in segs:
        t = (s.get("text") or "").strip()
        if t:
            out.append(
                TranscriptSegment(
                    float(s.get("start", 0)),
                    float(s.get("end", 0)),
                    t,
                )
            )
    if not out:
        raw = (payload.get("text") or "").strip()
        if raw:
            from bot.services.whisper_quality import clean_segment_text

            cleaned = clean_segment_text(raw, language) or raw
            detected = lang_code or _detected_from_payload(payload, fallback="")
            return [TranscriptSegment(0.0, 0.0, cleaned)], detected
        raise TranscriptionError(prog("transcription_empty", language))
    if live:
        live.flush_segments(out)
    if lang_code:
        detected = lang_code
    else:
        detected = _detected_from_payload(payload, fallback="")
    return out, detected


def _huggingface(
    wav_path: Path,
    live: TranscribeLiveProgress | None = None,
    *,
    language: str = "es",
) -> tuple[list[TranscriptSegment], str]:
    headers = {}
    if HF_API_TOKEN:
        headers["Authorization"] = f"Bearer {HF_API_TOKEN}"
    stop = threading.Event()

    def _pulse() -> None:
        if not live:
            return
        t0 = time.monotonic()
        while not stop.wait(live.CLOUD_PULSE_GAP):
            live.cloud_pulse(time.monotonic() - t0)

    waiter = threading.Thread(target=_pulse, daemon=True)
    with wav_path.open("rb") as f:
        data = f.read()
    waiter.start()
    params: dict[str, str] = {"task": "transcribe"}
    hf_lang = hf_language(language)
    if hf_lang:
        params["language"] = hf_lang
    try:
        r = httpx.post(
            HF_URL,
            headers=headers,
            content=data,
            params=params,
            timeout=300.0,
        )
    finally:
        stop.set()
        waiter.join(timeout=0.5)
    if r.status_code == 503:
        raise TranscriptionError("Servicio ocupado, reintenta en un momento")
    if r.status_code != 200:
        raise TranscriptionError(prog("transcription_failed_audio", language))
    data = r.json()
    if isinstance(data, dict) and "error" in data:
        raise TranscriptionError(str(data["error"]))
    text = ""
    if isinstance(data, dict):
        text = (data.get("text") or "").strip()
    elif isinstance(data, list) and data:
        text = (data[0].get("text") or "").strip()
    if not text:
        raise TranscriptionError("El audio no tenía voz reconocible")
    out = [TranscriptSegment(0.0, 0.0, text)]
    if live:
        live.flush_segments(out)
    detected = hf_lang[:2] if hf_lang else ""
    return out, detected


_whisper_model = None


def _local_whisper(
    wav_path: Path,
    live: TranscribeLiveProgress | None = None,
    *,
    language: str = "es",
) -> tuple[list[TranscriptSegment], str]:
    global _whisper_model
    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        raise TranscriptionError(
            prog("transcription_unavailable", language)
        ) from e

    if _whisper_model is None:
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

    lang_param = whisper_language(language)
    segments, info = _whisper_model.transcribe(
        str(wav_path),
        language=lang_param,
        task="transcribe",
        temperature=0.0,
        condition_on_previous_text=False,
        vad_filter=False,
        compression_ratio_threshold=2.35,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.55,
        initial_prompt=whisper_prompt(language) or None,
    )
    out: list[TranscriptSegment] = []
    for s in segments:
        t = (s.text or "").strip()
        if t:
            seg = TranscriptSegment(float(s.start), float(s.end), t)
            out.append(seg)
            if live:
                live.segment(seg)
    from bot.services.whisper_quality import filter_transcript_segments

    out = filter_transcript_segments(out, lang=language)
    if not out:
        raise TranscriptionError(prog("transcription_empty_local", language))
    # Idioma forzado: no usar el que invente el modelo local
    if lang_param:
        detected = lang_param
    else:
        detected = (getattr(info, "language", None) or "")[:2]
    return out, detected


def _transcribe_file(
    wav_path: Path,
    live: TranscribeLiveProgress | None = None,
    *,
    language: str = "es",
) -> tuple[list[TranscriptSegment], str]:
    errors: list[str] = []
    engines: list[tuple[str, Callable[..., tuple[list[TranscriptSegment], str]]]] = []
    if _whisper_keys():
        engines.append(("remoto", _groq))
    if not TRANSCRIBE_GROQ_ONLY:
        engines.extend([("local", _local_whisper), ("respaldo", _huggingface)])

    for tag, fn in engines:
        try:
            if live:
                live.engine(tag)
            segs, detected = fn(wav_path, live, language=language)
            if not detected and not is_auto_detect(language):
                detected = whisper_language(language) or normalize_transcript_lang(language)
            return segs, detected
        except Exception as e:
            logger.warning("Transcripción %s falló: %s", tag, e)
            errors.append(str(e))

    raise TranscriptionError(prog("transcription_failed_audio", language))


def transcribe_audio(
    wav_path: Path,
    on_progress: Callable[[int, str, str], None] | None = None,
    cancel_event: threading.Event | None = None,
    *,
    language: str = "es",
) -> tuple[list[TranscriptSegment], str]:
    chunks = split_wav_for_transcription(wav_path)
    multi = len(chunks) > 1
    all_segments: list[TranscriptSegment] = []
    n = len(chunks)

    total_sec = wav_duration_sec(wav_path)
    wav_bytes = wav_path.stat().st_size if wav_path.exists() else 0

    parallel = (
        multi
        and GROQ_API_KEY
        and TRANSCRIBE_PARALLEL_CHUNKS > 1
        and n > 1
    )

    def _one_chunk(i: int, chunk_path: Path, offset: float) -> tuple[int, list[TranscriptSegment], str]:
        from bot.services.job_cancel import check_cancelled

        check_cancelled(cancel_event)
        chunk_sec = wav_duration_sec(chunk_path) if multi else total_sec
        chunk_bytes = chunk_path.stat().st_size if chunk_path.exists() else wav_bytes
        live = None if parallel else TranscribeLiveProgress(
            on_progress,
            total_sec=chunk_sec,
            wav_bytes=chunk_bytes,
            timeline_offset=offset,
            chunk_index=i,
            chunk_count=n,
            lang=language,
        )
        segs, detected = _transcribe_file(chunk_path, live, language=language)
        return i, segs, detected

    detected_lang = ""
    try:
        if parallel:
            workers = min(TRANSCRIBE_PARALLEL_CHUNKS, n)
            done = 0
            ordered: list[tuple[int, list[TranscriptSegment], str]] = []
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_one_chunk, i, cp, off): i
                    for i, (cp, off) in enumerate(chunks)
                }
                for fut in as_completed(futures):
                    from bot.services.job_cancel import check_cancelled

                    check_cancelled(cancel_event)
                    i, segs, detected = fut.result()
                    ordered.append((i, segs, detected))
                    if detected and not detected_lang:
                        detected_lang = detected
                    done += 1
                    if on_progress:
                        pct = 58 + int(30 * done / n)
                        on_progress(pct, prog("transcribing", language), "")
                    logger.info("Transcrito trozo %s/%s (paralelo)", done, n)
            for _i, segs, _det in sorted(ordered, key=lambda x: x[0]):
                off = chunks[_i][1]
                for s in segs:
                    all_segments.append(
                        TranscriptSegment(s.start + off, s.end + off, s.text)
                    )
        else:
            for i, (chunk_path, offset) in enumerate(chunks):
                _i, segs, detected = _one_chunk(i, chunk_path, offset)
                if detected and not detected_lang:
                    detected_lang = detected
                if on_progress:
                    pct = 58 + int(30 * (i + 1) / n) if multi else 60
                    on_progress(pct, prog("transcribing", language), "")
                for s in segs:
                    all_segments.append(
                        TranscriptSegment(s.start + offset, s.end + offset, s.text)
                    )
                if multi:
                    logger.info("Transcrito trozo %s/%s", i + 1, n)
    finally:
        cleanup_chunks(chunks, wav_path)

    if not all_segments:
        raise TranscriptionError(prog("transcription_empty", language))

    from bot.services.whisper_quality import filter_transcript_segments

    # Auto: filtrar con el idioma detectado. Forzado: con el que eligió el usuario.
    if is_auto_detect(language) and detected_lang:
        filter_lang = detected_lang
    else:
        filter_lang = language
    all_segments = filter_transcript_segments(all_segments, lang=filter_lang)
    if not all_segments:
        raise TranscriptionError(prog("transcription_empty", language))

    if not detected_lang and not is_auto_detect(language):
        detected_lang = whisper_language(language) or normalize_transcript_lang(language)

    return all_segments, detected_lang


def transcribe_spanish(
    wav_path: Path,
    on_progress: Callable[[int, str, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[list[TranscriptSegment], str]:
    """Compatibilidad: transcripción en español."""
    return transcribe_audio(
        wav_path, on_progress, cancel_event, language="es"
    )
