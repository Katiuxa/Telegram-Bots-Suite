import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
# Varias cuentas Groq (claves separadas por coma). Misma org = misma cuota;
# cuentas distintas sí suman límite. También se acepta GROQ_API_KEY.
_GROQ_KEYS_RAW = os.getenv("GROQ_API_KEYS", "").strip()
GROQ_API_KEYS: list[str] = []
for _k in ((GROQ_API_KEY,) + tuple(p.strip() for p in _GROQ_KEYS_RAW.split(",") if p.strip())):
    if _k and _k not in GROQ_API_KEYS:
        GROQ_API_KEYS.append(_k)
if not GROQ_API_KEY and GROQ_API_KEYS:
    GROQ_API_KEY = GROQ_API_KEYS[0]
GROQ_CHAT_URL = os.getenv(
    "GROQ_CHAT_URL", "https://api.groq.com/openai/v1/chat/completions"
).strip()
# 0 = solo reglas locales (tildes). El LLM inventaba español falso sobre basura ASR.
RESTORE_SPANISH_ORTHO = os.getenv("RESTORE_SPANISH_ORTHO", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
# Prompt inicial a Whisper: sesga y puede provocar alucinaciones → desactivado por defecto.
WHISPER_USE_PROMPT = os.getenv("WHISPER_USE_PROMPT", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
HF_API_TOKEN = os.getenv("HF_API_TOKEN", "").strip()
# Desactivado: no leer cookies del navegador (riesgo de flags Instagram/cuenta).
YTDLP_BROWSER = ""
TELEGRAPH_ACCESS_TOKEN = os.getenv("TELEGRAPH_ACCESS_TOKEN", "").strip()

TEMP_DIR = ROOT / "temp"
TEMP_DIR.mkdir(exist_ok=True)

MAX_TELEGRAM_FILE_MB = int(os.getenv("MAX_TELEGRAM_FILE_MB", "20") or "20")
# Audio: no rechazar antes de descargar (Telegram suele limitar ~20 MB al bot)
MAX_TELEGRAM_AUDIO_MB = int(os.getenv("MAX_TELEGRAM_AUDIO_MB", "20") or "20")
MAX_AUDIO_PARTS = int(os.getenv("MAX_AUDIO_PARTS", "30") or "30")
MAX_AUDIO_PARTS_TOTAL_MB = int(os.getenv("MAX_AUDIO_PARTS_TOTAL_MB", "500") or "500")
MAX_LINK_DURATION_SEC = 600
# YouTube: hasta ~5 h (solo audio)
MAX_YOUTUBE_DURATION_SEC = int(os.getenv("MAX_YOUTUBE_DURATION_SEC", "18000") or "18000")
MAX_VIDEO_DURATION_SEC = 600
# YouTube: solo audio; ~280 MB cubre ~5 h a 128 kbps sin bajar vídeo
MAX_YOUTUBE_DOWNLOAD_MB = int(os.getenv("MAX_YOUTUBE_DOWNLOAD_MB", "280") or "280")
YTDLP_SOCKET_TIMEOUT = int(os.getenv("YTDLP_SOCKET_TIMEOUT", "60") or "60")
# Tiempo mínimo por descarga (vídeos largos en Pi necesitan margen amplio)
YTDLP_JOB_TIMEOUT_SEC = int(os.getenv("YTDLP_JOB_TIMEOUT_SEC", "3600") or "3600")

# Telegram permite 4096; margen pequeño por Markdown y edición
TELEGRAM_MESSAGE_LIMIT = 4096
TELEGRAM_SAFE_CHARS = 4000
# Cuerpo por pantalla en el visor de transcripción (sin contar cabecera)
TRANSCRIPT_BODY_MAX = 4010
TRANSCRIPT_BODY_MAX_FIRST = 3820
# Si el texto partido supera esto, se usa navegación por pantallas
TRANSCRIPT_INLINE_MAX_PARTS = 3
TRANSCRIPT_PAGE_MAX_CHARS = TRANSCRIPT_BODY_MAX
MOMENT_BODY_MAX_CHARS = 3400
HIGHLIGHT_QUOTE_MAX_CHARS = 3400
# Muestra repartida en el tiempo para highlights con Groq (no solo el inicio)
HIGHLIGHTS_LLM_CHARS = 24_000
HIGHLIGHT_LABEL_WORDS_MAX = 7
HIGHLIGHT_LABEL_MAX_CHARS = 52

# Títulos del índice (Groq + validación anti-copia)
INDEX_TITLE_EXCERPT_CHARS = 960
INDEX_TITLE_WORDS_MAX = 7
INDEX_TITLES_BATCH_SIZE = 5
INDEX_LLM_MODEL = os.getenv(
    "INDEX_LLM_MODEL", "openai/gpt-oss-120b"
).strip() or "openai/gpt-oss-120b"
TELEGRAM_AUDIO_MAX_MB = int(os.getenv("TELEGRAM_AUDIO_MAX_MB", "48") or "48")
SUMMARY_INPUT_CHARS = 18_000
# Resumen en chat: una ventana editable con pantallas (no mensajes sueltos)
SUMMARY_BODY_MAX_FIRST = 3600
SUMMARY_BODY_MAX = 3920
SUMMARY_LLM_CHUNK_CHARS = 14_000
# Trozos cortos = menos tokens/minuto (plan gratis Groq)
TRANSLATE_LLM_CHUNK_CHARS = int(os.getenv("TRANSLATE_LLM_CHUNK_CHARS", "2200") or "2200")
# Preferir calidad; el router baja a gpt-oss-20b si los grandes están en cooldown.
# Groq retira llama-3.1-8b-instant y llama-3.3-70b-versatile el 2026-08-16.
TRANSLATE_LLM_MODEL = os.getenv(
    "TRANSLATE_LLM_MODEL", "openai/gpt-oss-120b"
).strip() or "openai/gpt-oss-120b"
TRANSLATE_LLM_FALLBACK = os.getenv(
    "TRANSLATE_LLM_FALLBACK", "openai/gpt-oss-20b"
).strip() or "openai/gpt-oss-20b"
# Cascada traducción: calidad primero; cada modelo tiene cuota free aparte.
# Si uno satura, el router salta al siguiente al instante (sin esperas largas).
_translate_models_env = os.getenv("TRANSLATE_LLM_MODELS", "").strip()
if _translate_models_env:
    TRANSLATE_LLM_MODELS = [
        m.strip() for m in _translate_models_env.split(",") if m.strip()
    ]
else:
    TRANSLATE_LLM_MODELS = []
    for m in (
        TRANSLATE_LLM_MODEL,
        "openai/gpt-oss-120b",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "qwen/qwen3-32b",
        "openai/gpt-oss-20b",
        TRANSLATE_LLM_FALLBACK,
    ):
        name = (m or "").strip()
        if name and name not in TRANSLATE_LLM_MODELS:
            TRANSLATE_LLM_MODELS.append(name)
TRANSLATE_CHUNK_PAUSE_SEC = float(
    os.getenv("TRANSLATE_CHUNK_PAUSE_SEC", "0.8") or "0.8"
)

# Saltos de línea y cambio de hablante (segundos)
PARAGRAPH_GAP_SEC = 0.9
SPEAKER_GAP_SEC = 2.0
MOMENT_BUCKET_SEC = 55
CHAPTER_INTERVAL_SEC = 240

# Borrar descargas y temporales (minutos). 3 h: un YouTube largo no se borra a media transcripción.
TEMP_CLEANUP_MINUTES = int(os.getenv("TEMP_CLEANUP_MINUTES", "180") or "180")

GROQ_MAX_WAV_MB = 22
# Trozos ~8 min: pocos requests Groq (vídeos largos) sin saturar cuota 429.
# Trozos >~2 min degradan el español en Groq Whisper (habrá→habr, está→est, qué→qu).
AUDIO_CHUNK_SEC = int(os.getenv("AUDIO_CHUNK_SEC", "90") or "90")

# Calidad máxima Whisper (turbo es más rápido pero peor / más alucinaciones)
GROQ_WHISPER_MODEL = (
    os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3").strip() or "whisper-large-v3"
)
# Parallelismo bajo: evita 429 en plan free con vídeos largos.
TRANSCRIBE_PARALLEL_CHUNKS = int(os.getenv("TRANSCRIBE_PARALLEL_CHUNKS", "2") or "2")
FFMPEG_THREADS = int(os.getenv("FFMPEG_THREADS", "2") or "2")
TRANSCRIBE_GROQ_ONLY = os.getenv("TRANSCRIBE_GROQ_ONLY", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Por defecto calidad (pulido completo). FAST_POLISH=1 solo si quieres velocidad.
_fast_polish = os.getenv("FAST_POLISH", "0").strip().lower()
if _fast_polish in ("0", "false", "no", "off", ""):
    FAST_POLISH = False
elif _fast_polish in ("1", "true", "yes", "on"):
    FAST_POLISH = True
else:
    FAST_POLISH = False

_cf = os.getenv("YTDLP_CONCURRENT_FRAGMENTS", "").strip()
if _cf:
    YTDLP_CONCURRENT_FRAGMENTS = max(0, int(_cf or "0"))
elif FAST_POLISH:
    YTDLP_CONCURRENT_FRAGMENTS = 4
else:
    # En PC los fragmentos paralelos aceleran mucho YouTube (solo audio).
    YTDLP_CONCURRENT_FRAGMENTS = 4 if sys.platform == "win32" else 0

LINK_PATTERNS = (
    r"(https?://)?(www\.)?(tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)",
    r"(https?://)?(www\.)?(instagram\.com/(reel|reels|p)/|instagr\.am)",
    r"(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)",
    r"(https?://)?(www\.|mobile\.)?(twitter\.com|x\.com)/([\w]+/status/|i/status/)",
    r"(https?://)?(www\.)?t\.co/\w+",
)

YOUTUBE_PATTERNS = (
    r"youtube\.com",
    r"youtu\.be",
    r"music\.youtube\.com",
)

TWITTER_PATTERNS = (
    r"(?:^|/)(?:twitter\.com|x\.com)/",
    r"(?:^|/)(?:www\.|mobile\.)?(?:twitter\.com|x\.com)/",
    r"t\.co/",
)

DOCUMENT_TITLE_DEFAULT = os.getenv("DOCUMENT_TITLE", "Transcripción").strip() or "Transcripción"
METADATA_ENABLED = os.getenv("METADATA_ENABLED", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
METADATA_DESCRIPTION_MAX = int(os.getenv("METADATA_DESCRIPTION_MAX", "320") or "320")
METADATA_MIN_PLAIN_CHARS = int(os.getenv("METADATA_MIN_PLAIN_CHARS", "80") or "80")

# Post-transcripción: PDF automático si el texto cabe en un mensaje corto
MAX_CHARS_FOR_TELEGRAM = int(os.getenv("MAX_CHARS_FOR_TELEGRAM", "4000") or "4000")
AUTO_PDF = os.getenv("AUTO_PDF", "0").strip().lower() in ("1", "true", "yes", "on")
EXPORT_TOC = os.getenv("EXPORT_TOC", "1").strip().lower() in ("1", "true", "yes", "on")
CLEANUP_TEMP = os.getenv("CLEANUP_TEMP", "1").strip().lower() in ("1", "true", "yes", "on")

# Subida externa (misma lógica que VideoDownloader_bot / X Downloader)
EXTERNAL_UPLOAD_ENABLED = os.getenv("EXTERNAL_UPLOAD_ENABLED", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
CATBOX_MAX_MB = int(os.getenv("CATBOX_MAX_MB", "200") or "200")
MAX_EXTERNAL_FILE_MB = int(os.getenv("MAX_EXTERNAL_FILE_MB", "2048") or "2048")
_link_ttl = os.getenv("EXTERNAL_LINK_TTL", "1h").strip().lower()
EXTERNAL_LINK_TTL = _link_ttl if _link_ttl in {"1h", "24h", "72h"} else "1h"
GOFILE_TTL_HOURS = int(os.getenv("GOFILE_TTL_HOURS", "24") or "24")
ZEROX0_TTL_HOURS = int(os.getenv("ZEROX0_TTL_HOURS", "24") or "24")
UPLOAD_PROVIDER_COOLDOWN_SEC = int(os.getenv("UPLOAD_PROVIDER_COOLDOWN_SEC", "300") or "300")
GOFILE_MIN_SIZE_MB = int(os.getenv("GOFILE_MIN_SIZE_MB", "200") or "200")
GOFILE_MAX_UPLOADS_PER_HOUR = int(os.getenv("GOFILE_MAX_UPLOADS_PER_HOUR", "8") or "8")
USER_MAX_EXTERNAL_PER_HOUR = int(os.getenv("USER_MAX_EXTERNAL_PER_HOUR", "4") or "4")
USER_MAX_EXTERNAL_PER_DAY = int(os.getenv("USER_MAX_EXTERNAL_PER_DAY", "20") or "20")
_VALID_UPLOAD_PROVIDERS = frozenset({"litterbox", "catbox", "0x0", "pixeldrain", "gofile"})
_raw_providers = os.getenv(
    "UPLOAD_PROVIDERS", "litterbox,catbox,gofile,pixeldrain"
).strip().lower()
UPLOAD_PROVIDERS = tuple(
    p.strip() for p in _raw_providers.split(",") if p.strip() in _VALID_UPLOAD_PROVIDERS
) or ("litterbox", "catbox", "gofile")
OWNER_ADMIN_IDS: frozenset[int] = frozenset({39624065})
_raw_admin = (os.getenv("ADMIN_ID") or "").strip()
_extra_admin = int(_raw_admin) if _raw_admin.isdigit() and int(_raw_admin) > 0 else 0
ADMIN_ID = next(iter(OWNER_ADMIN_IDS)) if not _extra_admin else _extra_admin

MAX_TELEGRAM_BYTES = TELEGRAM_AUDIO_MAX_MB * 1024 * 1024
CATBOX_MAX_BYTES = CATBOX_MAX_MB * 1024 * 1024
MAX_EXTERNAL_BYTES = MAX_EXTERNAL_FILE_MB * 1024 * 1024
# MP3 a 128 kbps sin comprimir agresivamente si va a host externo
MP3_FAST_ENCODE_KBPS = int(os.getenv("MP3_FAST_ENCODE_KBPS", "128") or "128")


def is_admin(user_id: int) -> bool:
    if user_id in OWNER_ADMIN_IDS:
        return True
    if _extra_admin and user_id == _extra_admin:
        return True
    return False
