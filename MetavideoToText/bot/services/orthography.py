"""Restaurar tildes, puntuación y legibilidad en transcripciones españolas."""

from __future__ import annotations

import logging
import re

import httpx

from bot.config import GROQ_API_KEY, GROQ_CHAT_URL, RESTORE_SPANISH_ORTHO
from bot.services.transcribe import TranscriptSegment
from bot.services.transcript_lang import normalize_source_lang

logger = logging.getLogger(__name__)

_ORTHO_MODEL = "openai/gpt-oss-120b"
_BATCH_LINES = 8
_BATCH_CHARS = 1800
_BLOCK_CHARS = 2400
_CHUNK_CHARS = 2000
_NUM_LINE = re.compile(r"^\s*(\d+)\.\s*(.*)$", re.DOTALL)

_PROMPT_LEAK = re.compile(
    r"(?i)\b(?:transcripci[oó]n en espa[nñ]ol|ortograf[ií]a correcta|"
    r"puntuaci[oó]n natural|signos de interrogaci[oó]n|"
    r"tildes?,?\s*e[nñ]es?|subt[ií]tulos en espa[nñ]ol)\b[,.]?\s*"
)

# Anotaciones de corrector IA: «"mal" no, "bien"» / «mal → bien» / «(en realidad bien)»
_AI_QUOTE_NO_QUOTE = re.compile(
    r'(?:["«“„])(?P<wrong>[^"«»”“„]+)(?:["»”])'
    r'\s*,?\s*no,?\s*'
    r'(?:["«“„])(?P<right>[^"«»”“„]+)(?:["»”])',
    re.IGNORECASE,
)
_AI_ARROW_FIX = re.compile(
    r'["«“]?(?P<left>[^"«»”“→\n]{1,60})["»”]?\s*(?:→|->|=>)\s*'
    r'["«“]?(?P<right>[^"«»”“\n]{1,60})["»”]?'
)
_AI_REALITY_PAREN = re.compile(
    r"(\S+)\s*\(\s*(?:en\s+realidad|corr(?:ecci[oó]n)?\.?|quiero\s+decir|"
    r"mejor|rectificaci[oó]n)\s*[:\-]?\s*([^)]+?)\s*\)",
    re.IGNORECASE,
)
_AI_EDITORIAL_NOTE = re.compile(
    r"(?i)\s*\[(?:nota|correcci[oó]n|ndr|sic|nota\s+del\s+corrector)[^\]]*\]"
)
_BROKEN_SPACE = re.compile(r"\b([a-záéíóúüñ]{1,3})\s+([a-záéíóúüñ]{2,})\b", re.I)

_PHRASE_FIXES: tuple[tuple[str, str], ...] = (
    (r"\bpoco\s+mas\b", "poco más"),
    (r"\bmas\s+o\s+menos\b", "más o menos"),
    (r"\bno\s+mas\b", "no más"),
    # Whisper corta «más» a «m»: «es m grande», «se siente m grande»
    (r"\bm\s+(?=grande|pequeñ|mejor|peor|importante|rápid|rapid|clar|fuerte|débil|debil|alto|bajo|cerca|lejos|fácil|facil|difícil|dificil|tarde|temprano|largo|corto|nuevo|viejo|serio|lento)", "más "),
    (r"\bes\s+m\s+", "es más "),
    (r"\bcada\s+vez\s+m\s+", "cada vez más "),
    (r"\bsiente\s+m\s+", "siente más "),
    (r"\bsienten\s+m\s+", "sienten más "),
    (r"\bmucho\s+m\s+", "mucho más "),
    (r"\bEst\s+claro\b", "Está claro"),
    (r"\best\s+claro\b", "está claro"),
    (r"\best\s+pasando\b", "está pasando"),
    (r"\best\s+bien\b", "está bien"),
    # «la est habitando» / «est ocurriendo»
    (r"\best\s+(?=(?:[a-záéíóúüñ]+(?:ando|iendo|ándo|iéndo)|ocurriendo|habiendo|siendo)\b)", "está "),
    (r"\bEst\s+(?=(?:[A-Za-záéíóúüñ]+(?:ando|iendo))\b)", "Está "),
    (r"\btodav\s+no\b", "todavía no"),
    (r"\bT\s+has\b", "Te has"),
    (r"\bas\s+que\b", "así que"),
    (r"\bex\s+orales\b", "exámenes orales"),
    (r"\bquiz\s+no\b", "quizá no"),
    (r"\bquiz\s+tenga\b", "quizá tenga"),
    (r"\bquiz\s+sea\b", "quizá sea"),
    (r"\banquilia\b", "ancilla"),
    (r"\bsorprendio\b", "sorprendió"),
    (r"\bseccion\s+Est\s+claro\b", "sección. Está claro"),
    (r"\bseccion\s+Está\s+claro\b", "sección. Está claro"),
    (r"\bpasando\s+Te\s+has\b", "pasando. Te has"),
    (r"\bpasando\s+T\s+has\b", "pasando. Te has"),
    # Cortes típicos de Whisper en español (sobre todo con audio YT flojo)
    (r"(?i)\btambi\b", "también"),
    (r"(?i)\btambien\b", "también"),
    (r"(?i)\ba\s+s\s+mismos\b", "a sí mismos"),
    (r"(?i)\ba\s+s\s+mismo\b", "a sí mismo"),
    (r"(?i)\ba\s+trav\s+de\b", "a través de"),
    (r"(?i)\btrav\s+de\b", "través de"),
    (r"(?i)\btravs\s+de\b", "través de"),
    (r"(?i)\bespa\b(?=\s+(?:del|de|actual|moderno))", "español"),
    (r"(?i)\bning\b(?=\s+(?:idioma|sentido|persona|cosa|manera))", "ningún"),
    (r"(?i)\bqu\b(?=\s+no\b)", "que"),
    (r"(?i)\bten\b(?=\s+lengua\b)", "tiene"),
    (r"(?i)\bmuch\b(?=\s+(?:pero|y|de|más|mas)\b)", "mucho"),
    (r"(?i)\bmuchisim\b", "muchísimo"),
    (r"(?i)\bmuchismo\b", "muchísimo"),
    (r"(?i)\binsuficient\b", "insuficiente"),
    (r"(?i)\bmecanizad\b", "mecanizado"),
    (r"(?i)\bexperienci\b", "experiencia"),
    (r"(?i)\brealid\b", "realidad"),
    (r"(?i)\bsimplificad\b(?=\s|$|[.,;:!?])", "simplificado"),
    (r"(?i)\bsimplifican\b(?=\s|$|[.,;:!?¿])", "simplificando"),
    # Colas con tilde perdidas (chunk largo Whisper / PDF): parecía→parec, habrá→habr…
    (r"(?i)\bparec\b(?=\s)", "parecía"),
    (r"(?i)\bleg\b(?=\s+[A-ZÁÉÍÓÚÑ])", "llegó"),
    (r"(?i)\blleg\b(?=\s+[A-ZÁÉÍÓÚÑ])", "llegó"),
    (r"(?i)\bcont\b(?=\s*,?\s*hemos\b)", "conté"),
    (r"(?i)\bd\s+atr\b", "días atrás"),
    (r"(?i)\baqu\b(?=\s+(?:en|con|pone|para|está|estamos|hay|mismo)\b)", "aquí"),
    (r"(?i)\badem\b(?=\s|$|[.,;:!?…])", "además"),
    (r"(?i)\bacerc\b(?=\s+a\s+(?:nuestra|la|su)\b)", "acercándose"),
    (r"(?i)\bbelengenal\b", "berenjenal"),
    (r"(?i)\bbelenjenal\b", "berenjenal"),
    (r"(?i)\bte\s+dec\b(?=\s+primero\b)", "te dice"),
    (r"(?i)\bexplican\s+c\s+son\b", "explican cómo son"),
    (r"(?i)\ben\s+qu\s+momento\b", "en qué momento"),
    (r"(?i)\best\s+prohibido\b", "está prohibido"),
    (r"(?i)\bhabr\b(?=\s+(?:un|una|unos|unas|momento|uno|de|que)\b)", "habrá"),
    (r"(?i)\bse\s+producir\b(?=\s+el\b)", "se producirá"),
    (r"(?i)\bno\s+s\s+qu\b", "no sé qué"),
    (r"(?i)\bno\s+s\s+cu\b", "no sé cuánto"),
    (r"(?i)\bno\s+s\s+que\b", "no sé qué"),
    (r"(?i)\bse\s+podr\b(?=\s+(?:quitar|ver|hacer|ir|ser)\b)", "se podrá"),
    (r"(?i)\bpodr\b(?=\s+quitar\b)", "podrá"),
    (r"(?i)\bdel\s+a\s+que\s+viene\b", "del año que viene"),
    (r"(?i)\bsur\s+de\s+Espa\b", "sur de España"),
    (r"(?i)\bEspa\b(?=\s*[.,;:!?…]|$)", "España"),
    (r"(?i)\bSierra\s+Madrile\b", "Sierra Madrileña"),
    (r"(?i)\bsierra\s+madrile\b", "sierra madrileña"),
    (r"(?i)\bte\s+pon\s+estas\b", "te pones estas"),
    (r"(?i)\bque\s+est\s+desaloj", "que están desaloj"),
    (r"(?i)\bpod\s+contempl", "podemos contempl"),
    (r"(?i)\bsi\s+sonar\b(?=\s+clon\b)", "si sonará"),
)

# Terminaciones ASR truncadas: «partici»→partición, «frecuenci»→frecuencia
_TRUNCATION_FIXES: tuple[tuple[str, str], ...] = (
    (r"(?i)\b([a-záéíóúüñ]{3,})enci\b", r"\1encia"),
    (r"(?i)\b([a-záéíóúüñ]{3,})anci\b", r"\1ancia"),
    (r"(?i)\b([a-záéíóúüñ]{3,})sion\b", r"\1sión"),
    (r"(?i)\b([a-záéíóúüñ]{3,})cion\b", r"\1ción"),
    (r"(?i)\bpartici\b", "partición"),
    (r"(?i)\bdisociaci\b", "disociación"),
    (r"(?i)\bparticipaci\b", "participación"),
    (r"(?i)\bvibraci\b", "vibración"),
    (r"(?i)\bactivaci\b", "activación"),
    (r"(?i)\binformaci\b", "información"),
    (r"(?i)\bcomunicaci\b", "comunicación"),
    (r"(?i)\bmeditaci\b", "meditación"),
    (r"(?i)\bintenci\b", "intención"),
    (r"(?i)\batenci\b", "atención"),
    (r"(?i)\bconcienci\b", "conciencia"),
    (r"(?i)\bfrecuenci\b", "frecuencia"),
    (r"(?i)\bignoranci\b", "ignorancia"),
    (r"(?i)\bimportanci\b", "importancia"),
)

_CI_TRUNC_EXCLUDE = frozenset(
    {
        "casi",
        "asi",
        "así",
        "taxi",
        "merci",
        "naci",
        "hice",
        "dice",
        "hace",
        "voce",
        "luce",
        "doce",
        "trece",
        "catorce",
        "quince",
    }
)

_WORD_FIXES: tuple[tuple[str, str], ...] = (
    (r"\btambien\b", "también"),
    (r"\btodavia\b", "todavía"),
    (r"\bquizas\b", "quizás"),
    (r"\bojala\b", "ojalá"),
    (r"\basi\b", "así"),
    (r"\bmetodo\b", "método"),
    (r"\bmetodologia\b", "metodología"),
    (r"\bautonomia\b", "autonomía"),
    (r"\bpedagogia\b", "pedagogía"),
    (r"\bnosologia\b", "nosología"),
    (r"\bexamenes\b", "exámenes"),
    (r"\bestan\b", "están"),
    # NUNCA estas→estás: «estas cosas» es demostrativo correcto.
    (r"\bestamos\b", "estamos"),
    (r"\bhabiamos\b", "habíamos"),
    (r"\bteniamos\b", "teníamos"),
    (r"\bestaban\b", "estaban"),
    (r"\bfilosofia\b", "filosofía"),
    (r"\bpolitica\b", "política"),
    (r"\bseccion\b", "sección"),
    (r"\bteorica\b", "teórica"),
    (r"\bpractica\b", "práctica"),
    (r"\bjustificacion\b", "justificación"),
    (r"\bepistemologia\b", "epistemología"),
    (r"\bespecializadas\b", "especializadas"),
    (r"\bdivulgacion\b", "divulgación"),
    (r"\bconstruccion\b", "construcción"),
    (r"\bevaluacion\b", "evaluación"),
    (r"\bparticipacion\b", "participación"),
    (r"\bparticion\b", "partición"),
    (r"\bdisociacion\b", "disociación"),
    (r"\bvibracion\b", "vibración"),
    (r"\bactivacion\b", "activación"),
    (r"\binformacion\b", "información"),
    (r"\bcomunicacion\b", "comunicación"),
    (r"\bmeditacion\b", "meditación"),
    (r"\bintencion\b", "intención"),
    (r"\batencion\b", "atención"),
    (r"\bfrecuencia\b", "frecuencia"),
    (r"\bconciencia\b", "conciencia"),
    (r"\bprohibido\b", "prohibido"),
    (r"\bordenador\b", "ordenador"),
    (r"\buniversidad\b", "universidad"),
    # «mas» → «más» (conjunción arcaica es rarísima en hablado)
    (r"\bmas\b", "más"),
)


def strip_whisper_artifacts(text: str) -> str:
    if not text:
        return text
    t = _PROMPT_LEAK.sub("", text)
    t = strip_ai_correction_notes(t)
    t = strip_bogus_question_marks(t)
    # No aplastar párrafos (\n\n): solo espacios/tabs en la misma línea.
    t = re.sub(r"[^\S\n]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip(" ,.")


def strip_bogus_question_marks(text: str) -> str:
    """Quita ¿? vacías y ? falsos en afirmaciones. No rompe párrafos multi-pregunta."""
    if not text:
        return text
    t = text
    # Vacías / cutres: «¿?», «, ¿?», «tierra,?»
    t = re.sub(r",\s*¿\s*\?", ".", t)
    t = re.sub(r",\s*\?", ".", t)
    t = re.sub(r"¿\s*\?", "", t)
    # NUNCA tumbar «¿no?», «¿sí?», «¿ya?», «¿qué?» — solo basura tipo «¿Uf?».
    def _strip_noise_short_q(m: re.Match[str]) -> str:
        word = m.group(1)
        if word.casefold() in {
            "uf",
            "um",
            "em",
            "hm",
            "mm",
            "ah",
            "oh",
            "eh",
            "puf",
            "uff",
            "sal",
            "pum",
        }:
            return word
        return m.group(0)

    t = re.sub(
        r"¿\s*([A-Za-zÁÉÍÓÚÜáéíóúüñÑ]{1,3})\s*\?",
        _strip_noise_short_q,
        t,
    )
    t = re.sub(r"¿\s*(?=[.!,;…]|$)", "", t)
    t = re.sub(r"\?{2,}", "?", t)

    def _demote_false(m: re.Match[str]) -> str:
        # Solo una cláusula (no cruza .!…): evita tumbar «¿A? ¿B?».
        whole = m.group(0)
        if "¿" in whole:
            return whole
        body = whole[:-1].rstrip()
        if _looks_like_real_question(whole) or _looks_like_real_question(body):
            return whole
        return body + "."

    # Importante: [^.!?\n] — el patrón viejo [^\n?] cruzaba puntos y destrozaba
    # «… link ¿Cuánto…?» al mirar desde el inicio del párrafo.
    t = re.sub(r"[^.!?\n]+?\?", _demote_false, t)

    from bot.services.text_polish import pair_spanish_inverted_punctuation

    return pair_spanish_inverted_punctuation(t)


def _looks_like_real_question(text: str) -> bool:
    """True solo con interrogativo claro (no basta un ? final)."""
    raw = (text or "").strip()
    # Apertura ¿ = pregunta en español (incl. «¿Tienes link?» sin qué/cómo).
    if raw.startswith("¿"):
        return True
    low = raw.lower().lstrip("¿¡").rstrip("?!….").strip()
    if len(low) < 8:
        return False
    tokens = low.split()
    if not tokens:
        return False
    first = tokens[0].rstrip(",.;:")
    if first in {
        "qué",
        "quien",
        "quién",
        "quiénes",
        "cual",
        "cuál",
        "cuáles",
        "cómo",
        "como",
        "cuándo",
        "cuando",
        "cuánto",
        "cuánta",
        "cuántos",
        "cuántas",
        "dónde",
        "donde",
        "adónde",
    }:
        return True
    if len(tokens) >= 2 and f"{tokens[0]} {tokens[1]}" in {
        "por qué",
        "para qué",
        "por que",
        "para que",
        "a que",
    }:
        return True
    if low.startswith(("verdad que ", "sabes si ", "a que no ")):
        return True
    if low.endswith((", no", ", verdad", " o qué", " o no")):
        return True
    return False


def apply_asr_accent_rules(text: str) -> str:
    t = text or ""
    for pattern, repl in _PHRASE_FIXES:
        t = re.sub(pattern, repl, t, flags=re.IGNORECASE)
    for pattern, repl in _TRUNCATION_FIXES:
        t = re.sub(pattern, repl, t)
    # «partici» genérico residual → partición (excluye casi/así/…)
    def _cion(m: re.Match[str]) -> str:
        w = m.group(0)
        if w.casefold() in _CI_TRUNC_EXCLUDE:
            return w
        if w.casefold().endswith(("encia", "ancia", "ción", "sión")):
            return w
        # Ya corregido por TRUNCATION_FIXES (enci/anci); resto *ci → *ción
        if len(w) >= 5 and w.casefold().endswith("ci"):
            return w + "ón"
        return w

    t = re.sub(r"(?i)\b[a-záéíóúüñ]{4,}ci\b", _cion, t)
    for pattern, repl in _WORD_FIXES:
        t = re.sub(pattern, repl, t, flags=re.IGNORECASE)
    return t


def strip_ai_correction_notes(text: str) -> str:
    """Quita marcas de corrector («"mal" no, "bien"») y deja solo el texto final."""
    if not text:
        return text
    t = text
    # "El idioma" no, "El idiota" → "El idiota"
    t = _AI_QUOTE_NO_QUOTE.sub(r'"\g<right>"', t)

    def _arrow(m: re.Match[str]) -> str:
        left, right = m.group("left").strip(), m.group("right").strip()
        if not left or not right:
            return m.group(0)
        if abs(len(left) - len(right)) > 40:
            return m.group(0)
        return right

    t = _AI_ARROW_FIX.sub(_arrow, t)
    t = _AI_REALITY_PAREN.sub(r"\2", t)
    t = _AI_EDITORIAL_NOTE.sub("", t)
    # Títulos sin comillas: El idioma no, El idiota
    t = re.sub(
        r"(?i)\b((?:El|La|Los|Las|Un|Una)\s+"
        r"[A-ZÁÉÍÓÚÑa-záéíóúüñ][\wÁÉÍÓÚáéíóúüñ'’-]{1,40})"
        r"\s+no,\s+"
        r"((?:El|La|Los|Las|Un|Una)\s+"
        r"[A-ZÁÉÍÓÚÑa-záéíóúüñ][\wÁÉÍÓÚáéíóúüñ'’-]{1,40})\b",
        r"\2",
        t,
    )
    return t


def _light_cleanup(text: str, lang: str | None) -> str:
    from bot.services.transcript_lang import is_supported_source

    t = strip_whisper_artifacts(text)
    if is_supported_source(lang):
        return apply_asr_accent_rules(t)
    return t


def _split_for_ortho(text: str, max_len: int = _CHUNK_CHARS) -> list[str]:
    text = text.strip()
    if len(text) <= max_len:
        return [text]
    parts = re.split(r"(?<=[.!?…])\s+", text)
    if len(parts) <= 1:
        parts = re.split(
            r"\s+(?=(?:Entonces|Pero|Aunque|Porque|Luego|Y\s+[A-ZÁÉÍÓÚÑ]|"
            r"Si\s+[a-záéíóúñ]|No,|Sí,|Hay\s+que)\b)",
            text,
            flags=re.I,
        )
    chunks: list[str] = []
    buf = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if buf and len(buf) + len(part) + 1 > max_len:
            chunks.append(buf.strip())
            buf = part
        else:
            buf = f"{buf} {part}".strip() if buf else part
    if buf:
        chunks.append(buf.strip())
    return chunks or [text]


def _groq_fix_long_text(text: str) -> str:
    chunks = _split_for_ortho(text)
    fixed: list[str] = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        result = _groq_fix_lines([chunk])
        fixed.append(result[0] if result else chunk)
    return " ".join(fixed).strip()


def polish_spanish_readability(
    text: str,
    lang: str | None = None,
    *,
    paragraphs: bool = True,
) -> str:
    """Reglas locales de tildes/puntuación. NUNCA llama a un LLM (inventaba texto)."""
    code = normalize_source_lang(lang)
    if code != "es" or not text.strip():
        return text

    from bot.services.text_polish import (
        group_paragraphs,
        heal_false_sentence_breaks,
        infer_sentences,
        pair_spanish_inverted_punctuation,
        repair_broken_paragraphs,
    )

    t = apply_asr_accent_rules(strip_whisper_artifacts(text))
    t = strip_bogus_question_marks(strip_ai_correction_notes(t))
    t = heal_false_sentence_breaks(t, code)
    t = pair_spanish_inverted_punctuation(t)

    if not paragraphs or len(t) < 60:
        return t

    sentences = infer_sentences(t, lang=code)
    paras = group_paragraphs(sentences, max_sentences=4, max_chars=420)
    joined = "\n\n".join(paras) if paras else t
    joined = heal_false_sentence_breaks(joined, code)
    return pair_spanish_inverted_punctuation(
        repair_broken_paragraphs(joined, code)
    )


def needs_extra_ortho(text: str) -> bool:
    t = (text or "").replace("\n", " ")
    if len(t) < 120:
        return False
    if len(t) > 180 and sum(1 for c in t if c in ".!?…") == 0:
        return True
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 40:
        return False
    accented = sum(1 for c in t if c in "áéíóúüñÁÉÍÓÚÜÑ")
    suspicious = len(
        re.findall(
            r"\b(?:mas|est\s|estan|asi|tambien|todavia|quizas|todav|ex\s+orales)\b",
            t,
            re.I,
        )
    )
    return suspicious >= 2 or (
        len(letters) >= 80 and accented / len(letters) < 0.018
    )


def restore_spanish_orthography(text: str) -> str:
    return polish_spanish_readability(text, "es", paragraphs=False)


def restore_segments_orthography(
    segments: list[TranscriptSegment],
    lang: str | None,
) -> list[TranscriptSegment]:
    """Solo limpieza local por segmento. Sin LLM: no inventa frases."""
    return [
        TranscriptSegment(
            s.start,
            s.end,
            _light_cleanup(s.text, lang),
        )
        for s in segments
    ]


def restore_formatted_orthography(text: str, lang: str | None) -> str:
    """Sin LLM: solo limpieza local. Nunca reescribe ni inventa contenido."""
    code = normalize_source_lang(lang)
    if not text.strip():
        return text
    text = strip_whisper_artifacts(text)
    if code == "es":
        from bot.services.text_polish import pair_spanish_inverted_punctuation

        text = apply_asr_accent_rules(text)
        text = strip_bogus_question_marks(strip_ai_correction_notes(text))
        text = pair_spanish_inverted_punctuation(text)
    # Aunque RESTORE_SPANISH_ORTHO=1, NO usamos LLM aquí: inventaba charlas enteras.
    return text


def _fix_block(block: str, *, paragraphs: bool = True) -> str:
    block = block.strip()
    if not block:
        return block
    # Solo reglas locales (tildes). Sin Groq.
    return polish_spanish_readability(block, "es", paragraphs=paragraphs)


def _groq_fix_lines(lines: list[str]) -> list[str]:
    if not lines:
        return []
    prepped = [apply_asr_accent_rules(ln) for ln in lines]
    numbered = "\n".join(f"{j + 1}. {ln}" for j, ln in enumerate(prepped))
    system = (
        "Corrector experto de transcripciones de audio en español (ASR/Whisper). "
        "Para cada línea numerada devuelve SOLO el texto final ya corregido.\n"
        "REGLA DE ORO: el usuario debe leer una transcripción limpia. "
        "NUNCA muestres el proceso de corrección ni anotes el error.\n"
        "PROHIBIDO escribir cosas como: «\"El idioma\" no, \"El idiota\"», "
        "«mal → bien», «(en realidad …)», «[corrección]», «quiero decir …». "
        "Si el ASR dijo mal un título o palabra, SUSTITÚYELO en silencio "
        "(ej. salida correcta: Estaba leyendo \"El idiota\" de Dostoyevsky).\n"
        "- Tildes y eñes obligatorias: más (NUNCA «mas» ni «m» suelta), está "
        "(NUNCA «est» delante de gerundio), así, todavía, quizá, también, "
        "exámenes, metodología, pedagogía, autonomía, habíamos, sorprendió.\n"
        "- Completa palabras cortadas por el ASR: partici→partición, "
        "disociaci→disociación, frecuenci→frecuencia, concienci→conciencia, "
        "y en general terminaciones -ción/-sión/-encia/-ancia.\n"
        "- Puntuación natural entre frases completas; coma donde haga falta.\n"
        "- Si una frase nueva empieza con mayúscula tras minúscula sin punto "
        "(«…grande Por tanto», «…Tierra Que es», «…holograma Vas a»), "
        "pon punto y seguido.\n"
        "- NUNCA inventes signos de interrogación. PROHIBIDO «¿?», «palabra,?», "
        "o ? al final de afirmaciones. Solo ¿? con interrogativo real "
        "(qué, cómo, cuándo, dónde, por qué, …, no?).\n"
        "- NUNCA pongas punto y seguido a mitad de cláusula delante de "
        "también, además, hay que, y, pero, no, adverbios en -mente, etc.\n"
        "- NUNCA partas nombres propios ni marcas (Iván Nardini, Google Cloud).\n"
        "- Corrige pegados del ASR en silencio (Te has, está claro, todavía no, así que).\n"
        "- En filosofía, usa ancilla (siervo) si el ASR escribió anquilia.\n"
        "- PROHIBIDO inventar contenido, nombres o ideas nuevas.\n"
        "- Si la línea es basura, otro idioma transliterado o ininteligible, "
        "devuélvela IGUAL (no la reescribas en español coherente).\n"
        "- Mantén el mismo orden y longitud aproximada.\n"
        "Responde SOLO líneas numeradas: 1. …  2. …"
    )
    payload = {
        "model": _ORTHO_MODEL,
        "temperature": 0.1,
        "max_tokens": min(8192, max(900, len(numbered) + 500)),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": numbered},
        ],
    }
    try:
        r = httpx.post(
            GROQ_CHAT_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
            timeout=120.0,
        )
        if r.status_code != 200:
            logger.warning("Ortografía Groq %s: %s", r.status_code, r.text[:180])
            return prepped
        raw = (
            r.json()
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        parsed = _parse_numbered_lines(raw, len(prepped))
        if parsed and len(parsed) == len(prepped):
            return [
                apply_asr_accent_rules(
                    strip_bogus_question_marks(strip_ai_correction_notes(p))
                )
                for p in parsed
            ]
    except Exception as e:
        logger.warning("Ortografía falló: %s", e)
    return prepped


def _parse_numbered_lines(raw: str, expected: int) -> list[str] | None:
    by_num: dict[int, str] = {}
    for line in raw.splitlines():
        m = _NUM_LINE.match(line.strip())
        if m:
            by_num[int(m.group(1))] = m.group(2).strip()
    if len(by_num) >= expected:
        return [by_num.get(j + 1, "") for j in range(expected)]
    if expected == 1 and raw.strip():
        return [raw.strip()]
    return None
