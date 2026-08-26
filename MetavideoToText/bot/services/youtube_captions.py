"""Subtítulos de YouTube → segmentos.

Solo MANUALES de calidad en el camino principal (como TikTok/Reels → Whisper).
Los automáticos puntúan mal, cortan el final y parten frases: solo se usan
como último recurso si Whisper falla en un vídeo largo (no Shorts).
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from pathlib import Path

from bot.config import TEMP_DIR
from bot.services.transcribe import TranscriptSegment
from bot.services.transcript_lang import is_auto_detect, normalize_transcript_lang

logger = logging.getLogger(__name__)

_TS = re.compile(
    r"(?P<h1>\d{2}):(?P<m1>\d{2}):(?P<s1>\d{2})\.(?P<ms1>\d{3})\s*-->\s*"
    r"(?P<h2>\d{2}):(?P<m2>\d{2}):(?P<s2>\d{2})\.(?P<ms2>\d{3})"
)
_TAG = re.compile(r"<[^>]+>")
_VTT_META = re.compile(r"^(WEBVTT|NOTE|STYLE|REGION)\b", re.I)


def _sec(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _clean_vtt_line(line: str) -> str:
    t = _TAG.sub("", line)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    t = t.replace("\u200b", "").replace("\ufeff", "")
    return re.sub(r"\s+", " ", t).strip()


def _collect_cues(text: str) -> list[tuple[float, float, str]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[tuple[float, float, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or _VTT_META.match(line) or line.isdigit():
            continue
        m = _TS.match(line)
        if not m:
            continue
        start = _sec(m["h1"], m["m1"], m["s1"], m["ms1"])
        end = _sec(m["h2"], m["m2"], m["s2"], m["ms2"])
        buf: list[str] = []
        while i < len(lines) and lines[i].strip() and not _TS.match(lines[i].strip()):
            piece = _clean_vtt_line(lines[i])
            i += 1
            if piece:
                buf.append(piece)
        body = " ".join(buf).strip()
        if body:
            cues.append((start, end, body))
    return cues


def parse_vtt(text: str) -> list[TranscriptSegment]:
    """Parsea WEBVTT sin duplicar el formato rolling de auto-subs de YouTube."""
    cues = _collect_cues(text)
    if not cues:
        return []

    # Auto YouTube: cues «commit» de ~10 ms con la frase ya cerrada.
    short = [(a, b, t) for a, b, t in cues if (b - a) <= 0.05 and t]
    if len(short) >= max(3, int(len(cues) * 0.12)):
        out: list[TranscriptSegment] = []
        prev = ""
        for start, end, body in short:
            if body == prev:
                continue
            out.append(TranscriptSegment(start, end, body))
            prev = body
        return out

    out: list[TranscriptSegment] = []
    prev_text = ""
    for start, end, body in cues:
        if not body or body == prev_text:
            continue
        if prev_text and body.startswith(prev_text) and len(body) > len(prev_text) + 2:
            extra = body[len(prev_text) :].strip()
            if extra:
                out.append(TranscriptSegment(start, end, extra))
                prev_text = body
            continue
        out.append(TranscriptSegment(start, end, body))
        prev_text = body
    return out


def _sub_lang_args(lang: str) -> str:
    if is_auto_detect(lang):
        return "es.*,en.*,fr.*,ru.*"
    code = normalize_transcript_lang(lang)
    return f"{code}.*,{code}"


def _is_likely_auto_vtt(path: Path, raw: str) -> bool:
    name = path.name.lower()
    if re.search(r"\.a\d+\.vtt$", name):
        return True
    if "kind: captions" in raw[:800].lower() and "<c>" in raw:
        return True
    cues = _collect_cues(raw)
    if len(cues) >= 8:
        short_n = sum(1 for a, b, _ in cues if (b - a) <= 0.05)
        if short_n / len(cues) >= 0.25:
            return True
    return False


def _pick_lang_vtts(folder: Path, lang: str) -> list[Path]:
    files = sorted(folder.glob("*.vtt"))
    if not files:
        return []
    code = "es" if is_auto_detect(lang) else normalize_transcript_lang(lang)
    matched = [
        p
        for p in files
        if re.search(rf"\.{re.escape(code)}(?:-[A-Za-z]+)?\.vtt$", p.name, re.I)
    ]
    orig = [p for p in matched if "-orig" in p.name.lower()]
    other = [p for p in matched if p not in orig]
    rest = [p for p in files if p not in matched]
    # Original del vídeo primero (es-orig), luego el idioma pedido, luego el resto
    return orig + other + rest


def _pick_manual_vtts(folder: Path, lang: str) -> list[Path]:
    """Compat: mismos candidatos que _pick_lang_vtts."""
    return _pick_lang_vtts(folder, lang)


def _detect_lang_from_filename(path: Path, fallback: str) -> str:
    m = re.search(r"\.([a-z]{2})(?:-[A-Za-z]+)?\.vtt$", path.name, re.I)
    if m:
        return m.group(1).lower()
    if is_auto_detect(fallback):
        return "es"
    return normalize_transcript_lang(fallback)


def _duplication_ratio(texts: list[str]) -> float:
    if len(texts) < 4:
        return 0.0
    dup = 0
    total = 0
    prev = ""
    for t in texts:
        toks = t.lower().split()
        total += len(toks)
        if prev and (t.lower().startswith(prev) or prev.startswith(t.lower())):
            dup += len(toks)
        prev = t.lower()
    return dup / total if total else 0.0


def _quality_ok(
    segs: list[TranscriptSegment], lang: str, *, raw: str, path: Path
) -> bool:
    if len(segs) < 3:
        logger.info("YouTube caps: VTT demasiado corto (%s cues)", len(segs))
        return False

    if _is_likely_auto_vtt(path, raw):
        logger.info("YouTube caps: auto-ASR detectado (%s) → Whisper", path.name)
        return False

    sample = " ".join(s.text for s in segs[:80]).lower()
    if any(
        bad in sample
        for bad in (
            "don quixote",
            "servantes",
            "serfano",
            "quixote de",
            "[música] [música]",
            "[applause] [applause]",
        )
    ):
        logger.info("YouTube caps: calidad dudosa → Whisper")
        return False

    texts = [s.text for s in segs]
    if _duplication_ratio(texts) >= 0.35:
        logger.info("YouTube caps: demasiada duplicación rolling → Whisper")
        return False

    chars = sum(len(t) for t in texts)
    if chars < max(40, len(segs) * 8):
        logger.info("YouTube caps: texto insuficiente → Whisper")
        return False

    code = (
        normalize_transcript_lang(lang)
        if not is_auto_detect(lang)
        else _detect_lang_from_filename(path, lang)
    )
    if code == "es":
        es_hits = sum(
            1
            for w in ("el", "la", "de", "que", "en", "los", "una", "es", "se", "por")
            if f" {w} " in f" {sample} "
        )
        if es_hits < 3:
            logger.info("YouTube caps: poco español detectable → Whisper")
            return False
    return True


def _auto_quality_ok(segs: list[TranscriptSegment], *, raw: str, path: Path) -> bool:
    """Automáticos: acepta si cubren el vídeo con texto real (no solo [música])."""
    if len(segs) < 8:
        logger.info("YouTube auto-caps: demasiado cortos (%s cues) %s", len(segs), path.name)
        return False
    texts = [s.text for s in segs]
    chars = sum(len(t) for t in texts)
    if chars < max(80, len(segs) * 5):
        logger.info("YouTube auto-caps: poco texto (%s chars) %s", chars, path.name)
        return False
    last_end = max((s.end for s in segs), default=0.0)
    if last_end < 20:
        logger.info("YouTube auto-caps: cobertura %ss insuficiente %s", last_end, path.name)
        return False
    sample = " ".join(texts[:120]).lower()
    music_hits = sum(sample.count(tag) for tag in ("[música]", "[music]", "[applause]"))
    if music_hits >= 12 and chars < 400:
        logger.info("YouTube auto-caps: casi solo marcas de música %s", path.name)
        return False
    return True


def _read_vtt_segments(path: Path) -> tuple[str, list[TranscriptSegment]] | None:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.warning("YouTube caps: no se pudo leer %s: %s", path, e)
        return None
    return raw, parse_vtt(raw)


def try_fetch_youtube_captions(
    url: str,
    lang: str = "es",
    *,
    allow_auto: bool = False,
) -> tuple[list[TranscriptSegment], str] | None:
    """
    Subtítulos MANUALES de calidad.
    allow_auto=True solo como fallback si Whisper falló en un vídeo largo.
    """
    from bot.services.media import is_youtube_shorts_url

    if is_youtube_shorts_url(url):
        logger.info("YouTube Shorts: sin caps (Whisper) %s", url)
        return None
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    out_dir = TEMP_DIR / f"ytcaps_{abs(hash(url)) % 10_000_000}"
    if out_dir.exists():
        for old in out_dir.glob("*"):
            try:
                old.unlink()
            except OSError:
                pass
    else:
        out_dir.mkdir(parents=True, exist_ok=True)

    outtmpl = str(out_dir / "%(id)s")
    lang_arg = _sub_lang_args(lang)
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--skip-download",
        "--write-subs",
        "--sub-langs",
        lang_arg,
        "--sub-format",
        "vtt/best",
        "--convert-subs",
        "vtt",
        "--no-playlist",
        "-o",
        outtmpl,
        url,
    ]
    if allow_auto:
        cmd.insert(cmd.index("--write-subs") + 1, "--write-auto-subs")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(TEMP_DIR),
        )
    except Exception as e:
        logger.warning("YouTube caps: fallo yt-dlp: %s", e)
        return None

    if proc.returncode != 0:
        logger.info(
            "YouTube caps: yt-dlp code=%s stderr=%s",
            proc.returncode,
            (proc.stderr or "")[-400:],
        )

    vtts = _pick_lang_vtts(out_dir, lang)
    if not vtts:
        logger.info("YouTube caps: sin VTT para %s lang=%s", url, lang)
        return None

    vtts.sort(key=lambda p: (p.stat().st_size < 80, -p.stat().st_size))

    for chosen in vtts:
        parsed = _read_vtt_segments(chosen)
        if not parsed:
            continue
        raw, segs = parsed
        if _is_likely_auto_vtt(chosen, raw):
            continue
        if not _quality_ok(segs, lang, raw=raw, path=chosen):
            continue
        detected = _detect_lang_from_filename(chosen, lang)
        logger.info(
            "YouTube caps: OK manual file=%s segs=%s lang=%s",
            chosen.name,
            len(segs),
            detected,
        )
        return segs, detected

    if not allow_auto:
        logger.info("YouTube caps: sin manuales → Whisper para %s", url)
        return None

    for chosen in vtts:
        parsed = _read_vtt_segments(chosen)
        if not parsed:
            continue
        raw, segs = parsed
        if not _auto_quality_ok(segs, raw=raw, path=chosen):
            continue
        detected = _detect_lang_from_filename(chosen, lang)
        logger.info(
            "YouTube caps: OK auto file=%s segs=%s lang=%s last=%.0fs",
            chosen.name,
            len(segs),
            detected,
            max((s.end for s in segs), default=0.0),
        )
        return segs, detected

    logger.info("YouTube caps: ninguno usable → Whisper para %s", url)
    return None
