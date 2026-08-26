"""Idioma de transcripción (Whisper) y modo detección automática."""

from __future__ import annotations

from telegram.ext import ContextTypes

from bot.i18n import DEFAULT_LANG, LANG_MENU, SUPPORTED, normalize_lang

AUTO_LANG = "auto"

# Códigos ISO para Groq / faster-whisper (modo fijo)
WHISPER_CODE = {
    "es": "es",
    "en": "en",
    "fr": "fr",
    "ru": "ru",
    "pt": "pt",
    "de": "de",
    "it": "it",
    "ar": "ar",
    "hi": "hi",
    "zh": "zh",
    "ja": "ja",
    "ko": "ko",
    "tr": "tr",
    "pl": "pl",
    "nl": "nl",
    "uk": "uk",
    "sv": "sv",
    "id": "id",
    "vi": "vi",
    "th": "th",
    "ca": "ca",
    "gl": "gl",
    "ro": "ro",
    "cs": "cs",
    "el": "el",
    "he": "he",
    "fa": "fa",
    "bn": "bn",
    "ta": "ta",
    "ur": "ur",
}

# Parámetro language en Hugging Face Inference
HF_LANGUAGE = {
    "es": "spanish",
    "en": "english",
    "fr": "french",
    "ru": "russian",
    "pt": "portuguese",
    "de": "german",
    "it": "italian",
    "ar": "arabic",
    "hi": "hindi",
    "zh": "chinese",
    "ja": "japanese",
    "ko": "korean",
    "tr": "turkish",
    "pl": "polish",
    "nl": "dutch",
    "uk": "ukrainian",
}

SPEAKER_LABEL = {
    "es": "Voz",
    "en": "Voice",
    "fr": "Voix",
    "ru": "Голос",
    "pt": "Voz",
    "de": "Stimme",
    "it": "Voce",
}

# Selector visible de idioma del audio (solo estos)
AUDIO_LANG_MENU: dict[str, str] = {
    "es": LANG_MENU.get("es", "🇪🇸 Español"),
    "en": LANG_MENU.get("en", "🇬🇧 English"),
    "fr": LANG_MENU.get("fr", "🇫🇷 Français"),
    "ru": LANG_MENU.get("ru", "🇷🇺 Русский"),
    "auto": LANG_MENU.get("auto", "🌐 Detección"),
}

# Nombres legibles para idiomas detectados fuera de ES/EN/FR/RU
WHISPER_LANG_NAMES: dict[str, str] = {
    "hi": "Hindi",
    "ur": "Urdu",
    "pa": "Punjabi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "ar": "Arabic",
    "tr": "Turkish",
    "id": "Indonesian",
    "pt": "Portuguese",
    "de": "German",
    "it": "Italian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "vi": "Vietnamese",
    "th": "Thai",
    "pl": "Polish",
    "nl": "Dutch",
    "sv": "Swedish",
    "uk": "Ukrainian",
    "ca": "Catalan",
    "gl": "Galician",
    "ro": "Romanian",
    "cs": "Czech",
    "el": "Greek",
    "he": "Hebrew",
    "fa": "Persian",
}

# Solo si WHISPER_USE_PROMPT=1. Palabras sueltas sesgan a Whisper hacia temas inventados.
WHISPER_PROMPT = {
    "es": "Transcripción literal en español.",
    "en": "Literal English transcription.",
    "fr": "Transcription littérale en français.",
    "ru": "Дословная транскрипция на русском.",
    "pt": "Transcrição literal em português.",
    "de": "Wörtliche Transkription auf Deutsch.",
    "it": "Trascrizione letterale in italiano.",
}



def is_auto_detect(lang: str | None) -> bool:
    return normalize_transcript_lang(lang) == AUTO_LANG


def normalize_transcript_lang(lang: str | None) -> str:
    """Modo de transcripción: auto o cualquier código ISO-639-1 que Whisper acepte."""
    if not lang:
        return DEFAULT_LANG
    raw = lang.strip().lower()
    if raw == AUTO_LANG or raw.startswith("auto"):
        return AUTO_LANG
    code = raw[:2]
    if not code.isalpha() or len(code) != 2:
        return DEFAULT_LANG
    # No degradar a español idiomas válidos fuera de ES/EN/FR/RU
    if (
        code in SUPPORTED
        or code in AUDIO_LANG_MENU
        or code in WHISPER_CODE
        or code in WHISPER_LANG_NAMES
    ):
        return code
    return code


def normalize_source_lang(lang: str | None) -> str:
    """Idioma real del audio (detectado o fijo); conserva códigos ISO arbitrarios."""
    if not lang:
        return DEFAULT_LANG
    raw = lang.strip().lower()
    if raw == AUTO_LANG:
        return AUTO_LANG
    return raw[:2] or DEFAULT_LANG


def get_ui_lang(context: ContextTypes.DEFAULT_TYPE | None) -> str:
    if context is None:
        return DEFAULT_LANG
    return normalize_lang(context.user_data.get("ui_lang"))


def set_ui_lang(context: ContextTypes.DEFAULT_TYPE, lang: str) -> str:
    """Solo idioma de la app (menú). No cambia el idioma del audio."""
    code = normalize_lang(lang)
    context.user_data["ui_lang"] = code
    if not context.user_data.get("transcript_lang"):
        context.user_data["transcript_lang"] = code
    return code


def get_transcript_lang(context: ContextTypes.DEFAULT_TYPE | None) -> str:
    if context is None:
        return DEFAULT_LANG
    raw = context.user_data.get("transcript_lang") or context.user_data.get("ui_lang")
    return normalize_transcript_lang(raw)


def set_transcript_lang(context: ContextTypes.DEFAULT_TYPE, lang: str) -> str:
    """Fija idioma del audio / Whisper. No toca ui_lang."""
    code = normalize_transcript_lang(lang)
    if code == AUTO_LANG:
        return set_auto_detect_mode(context)
    context.user_data["transcript_lang"] = code
    return code


def set_auto_detect_mode(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Modo detección: transcribe en idioma original; menú no cambia."""
    context.user_data["transcript_lang"] = AUTO_LANG
    if not context.user_data.get("ui_lang"):
        context.user_data["ui_lang"] = DEFAULT_LANG
    return AUTO_LANG


def detected_language_label(code: str | None, ui_lang: str | None = None) -> str:
    """Etiqueta humana del idioma detectado (p. ej. Hindi, Urdu)."""
    c = normalize_source_lang(code)
    if c == AUTO_LANG:
        return AUDIO_LANG_MENU.get(AUTO_LANG) or LANG_MENU.get(AUTO_LANG, "🌐 Auto")
    if c in AUDIO_LANG_MENU:
        return AUDIO_LANG_MENU[c]
    if c in LANG_MENU:
        return LANG_MENU[c]
    return WHISPER_LANG_NAMES.get(c, c.upper())


def polish_lang(lang: str | None) -> str:
    """Idioma para formato/puntuación (solo ES/EN/FR/RU tienen reglas)."""
    c = normalize_source_lang(lang)
    return c if c in SUPPORTED else "en"


def whisper_language(lang: str | None) -> str | None:
    """Código para Whisper/Groq. None = detección automática.

    Nunca fuerza español si el usuario eligió otro idioma.
    """
    if is_auto_detect(lang):
        return None
    code = normalize_transcript_lang(lang)
    if code == AUTO_LANG:
        return None
    if code in WHISPER_CODE:
        return WHISPER_CODE[code]
    if len(code) == 2 and code.isalpha():
        return code
    return None


def hf_language(lang: str | None) -> str | None:
    if is_auto_detect(lang):
        return None
    code = normalize_transcript_lang(lang)
    if code == AUTO_LANG:
        return None
    return HF_LANGUAGE.get(code)


def speaker_label(lang: str | None, number: int = 1) -> str:
    code = polish_lang(lang)
    return f"{SPEAKER_LABEL.get(code, 'Voice')} {number}"


def whisper_prompt(lang: str | None) -> str:
    from bot.config import WHISPER_USE_PROMPT

    # Nunca mandar anclas tipo "Español.": Whisper las repite como alucinación.
    if not WHISPER_USE_PROMPT or is_auto_detect(lang):
        return ""
    code = normalize_transcript_lang(lang)
    return WHISPER_PROMPT.get(code, "")


def is_supported_source(lang: str | None) -> bool:
    return normalize_source_lang(lang) in SUPPORTED


def same_language(a: str | None, b: str | None) -> bool:
    return normalize_source_lang(a) == normalize_source_lang(b)


def should_auto_translate(
    detected: str,
    source_lang: str,
    ui_lang: str,
) -> bool:
    """En modo auto: traducir salvo que el detectado coincida con el idioma de menú."""
    if not detected:
        return True
    if same_language(source_lang, ui_lang):
        return False
    return True
