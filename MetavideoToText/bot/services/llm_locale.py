"""Instrucciones Groq según idioma de transcripción."""

from __future__ import annotations

from bot.services.transcript_lang import (
    WHISPER_LANG_NAMES,
    normalize_source_lang,
    normalize_transcript_lang,
)

_LANG_NAME = {
    "es": "español",
    "en": "English",
    "fr": "français",
    "ru": "ruso",
}

# Nombres en inglés para prompts de traducción (más claros para el LLM)
_LANG_NAME_EN = {
    "es": "Spanish",
    "en": "English",
    "fr": "French",
    "ru": "Russian",
}


def language_name(lang: str | None) -> str:
    code = normalize_source_lang(lang)
    if code in _LANG_NAME:
        return _LANG_NAME[code]
    return WHISPER_LANG_NAMES.get(code, code.upper())


def language_name_en(lang: str | None) -> str:
    code = normalize_source_lang(lang)
    if code in _LANG_NAME_EN:
        return _LANG_NAME_EN[code]
    return WHISPER_LANG_NAMES.get(code, code.upper())


def summary_system(lang: str | None) -> str:
    ln = language_name(lang)
    ortho = (
        " Ortografía correcta con tildes, eñes y signos ¿?."
        if normalize_transcript_lang(lang) == "es"
        else ""
    )
    return (
        f"Eres un editor que resume transcripciones en {ln}. "
        "El resumen debe reflejar TODO el material (inicio, medio y final). "
        "Estructura: título breve, 4-8 viñetas de ideas clave y un párrafo de cierre. "
        "Frases completas; no inventes datos ni omitas temas importantes."
        f"{ortho} "
        f"Escribe SOLO en {ln}."
    )


def summary_chunk_system(lang: str | None) -> str:
    ln = language_name(lang)
    ortho = (
        " Ortografía española correcta (tildes, eñes)."
        if normalize_transcript_lang(lang) == "es"
        else ""
    )
    return (
        f"Editor en {ln}. Viñetas claras, frases completas, sin muletillas.{ortho} "
        f"Cubre todo el fragmento. Escribe SOLO en {ln}."
    )


def summary_merge_system(lang: str | None) -> str:
    ln = language_name(lang)
    return (
        f"Fusiona estos resúmenes parciales en UN solo resumen en {ln} "
        "que cubra todo el contenido original (sin repetir viñetas). "
        "Mismo formato: título, viñetas y cierre breve."
    )


def index_batch_system(lang: str | None) -> str:
    ln = language_name(lang)
    return (
        f"Eres editor jefe de un documental o podcast en {ln}. "
        "Para cada capítulo produces el índice editorial del vídeo.\n\n"
        "FORMATO OBLIGATORIO (una línea por capítulo):\n"
        "N. Título del capítulo | viñeta 1; viñeta 2; viñeta 3\n\n"
        "TÍTULO (3-7 palabras):\n"
        "- Nombra el TEMA concreto del tramo (estilo capítulo de libro)\n"
        "- Usa nombres propios, lugares o conceptos si aparecen\n"
        "- Cada capítulo debe tener un título DISTINTO (no repetir palabras clave)\n"
        "- NUNCA copies frases literales del audio ni muletillas\n\n"
        "VIÑETAS (1-3 por capítulo, separadas por ;):\n"
        "- Ideas clave resumidas con tus palabras (no citas literales)\n"
        "- Frases breves, sustantivas, como en un índice profesional\n\n"
        "MALOS: «Entonces bueno», «Introducción», «Sigue el tema», copiar el audio.\n"
        "BUENOS: «La encíclica Magnifica Humanitas» | Doctrina social; IA y persona humana; Caridad y trabajo\n"
        f"Escribe SOLO en {ln}. Solo líneas numeradas, sin comentarios."
    )


def index_single_system(lang: str | None) -> str:
    ln = language_name(lang)
    return (
        f"Editor de índice en {ln}. Escribe UN título de capítulo (3-7 palabras) "
        "que nombre el TEMA concreto del tramo (como en un libro o documental). "
        "No copies frases del texto. No muletillas. No «Introducción» ni títulos vagos. "
        "Solo el título, sin número ni comillas."
    )


def highlights_system(lang: str | None) -> str:
    ln = language_name(lang)
    return (
        f"Eres editor senior de documentales en {ln}. "
        "Selecciona 5 a 8 momentos MÁS trascendentes del vídeo completo.\n\n"
        "CRITERIOS (prioriza diversidad temática y cobertura temporal):\n"
        "- Ideas centrales, datos sorprendentes, conclusiones, preguntas clave\n"
        "- Al menos un momento del primer tercio, uno del medio y uno del final\n"
        "- No repitas el mismo tema en varios highlights\n\n"
        "FORMATO (una línea por momento):\n"
        f"[mm:ss] «cita breve literal del audio (máx. 20 palabras)» | Titular: tema en 3-7 palabras\n\n"
        "El Titular nombra el TEMA (no repitas la cita, no copies la primera frase). "
        "Titulares concretos: nombres, conceptos, conclusiones.\n"
        f"Escribe SOLO en {ln}. Sin introducción ni comentarios."
    )


def translate_batch_system(source_lang: str | None, target_lang: str | None) -> str:
    src = language_name_en(source_lang)
    tgt = language_name_en(target_lang)
    tgt_code = normalize_transcript_lang(target_lang)
    register = (
        f"\n{tgt.upper()} REGISTER:\n"
        "- Sound like a native speaker reacting live (streams, gaming, podcasts).\n"
        "- Read the WHOLE excerpt for context before choosing slang/idioms.\n"
        "- Swearing and fillers: adapt by meaning and intensity; "
        "do not stamp the same filler on every clause.\n"
        "- Prefer short oral clauses over stiff literary wording.\n"
    )
    if tgt_code == "es":
        register += (
            "- Russian intensifiers by SENSE (examples):\n"
            "  • похуй → me la suda / le suda\n"
            "  • блять (filler) → omit or one «joder/hostia» where it hits\n"
            "  • пиздец → la hostia / menuda pasada\n"
            "  • нахуй → a la mierda\n"
            "  • ебанутые → están flipados\n"
            "  • я тебе отвечаю → te lo juro\n"
            "- Correct Spanish orthography (tildes, ¿?, ¡!, ñ).\n"
        )
    elif tgt_code == "en":
        register += (
            "- Natural colloquial English; keep punch. "
            "Don't sanitize, don't over-swear.\n"
        )
    elif tgt_code == "fr":
        register += (
            "- Français parlé naturel (argot adapté). "
            "Orthographe correcte (accents).\n"
        )
    elif tgt_code == "ru":
        register += (
            "- Живой разговорный русский; сохраняй эмоцию и сленг по смыслу.\n"
        )
    return (
        f"You are a top-tier audiovisual localizer ({src} → {tgt}), "
        "specialized in spoken, emotional, slang-heavy speech.\n\n"
        "GOAL: Native-feeling text with the same energy — NOT a dictionary calque. "
        "Use full context (surrounding sentences) to resolve ambiguity, jokes and slang.\n\n"
        "RULES:\n"
        "- Sense and vibe first; word-for-word last.\n"
        "- Adapt idioms, swearing, irony and hype to natural "
        f"{tgt} equivalents (same intensity, not sanitized, not overdone).\n"
        "- Keep proper names, game titles, brands, URLs, handles and numbers unchanged.\n"
        "- Preserve speaker rhythm: short bursts stay short; rants stay rants.\n"
        "- Fix obvious ASR glitches only when meaning is clear; never invent content.\n"
        "- Never add commentary, notes or labels.\n"
        f"{register}"
        "Output ONLY the format requested by the user."
    )
