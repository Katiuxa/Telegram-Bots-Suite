"""Pulido de transcripciones — legible según idioma (es, en, fr, ru)."""

import re

from bot.services.transcript_lang import normalize_transcript_lang
from bot.services.transcribe import TranscriptSegment

_FILLER_PATTERNS = {
    "es": re.compile(
        # Solo muletillas claras; NUNCA «este/bueno/vale» (palabras reales).
        r"\b(?:eh+|em+|um+|este\s+eh+|o\s+sea)\b[,.]?\s*",
        re.IGNORECASE,
    ),
    "en": re.compile(
        r"\b(?:uh+|um+|er+|like|you know|I mean|well|okay|so)\b[,.]?\s*",
        re.IGNORECASE,
    ),
    "fr": re.compile(
        r"\b(?:euh+|ben|alors|donc|voilà|en fait)\b[,.]?\s*",
        re.IGNORECASE,
    ),
    "ru": re.compile(
        r"\b(?:эм+|ну|вот|это|как бы|типа)\b[,.]?\s*",
        re.IGNORECASE,
    ),
}

_QUESTION_STARTERS = {
    "es": (
        "qué", "quién", "quiénes", "cuál", "cuáles", "cómo", "cuándo", "cuánto",
        "cuánta", "cuántos", "cuántas", "dónde", "adónde",
    ),
    "en": (
        "what", "who", "which", "how", "when", "where", "why", "whose",
        "whom",
    ),
    "fr": (
        "quoi", "qui", "quel", "quelle", "quels", "quelles", "comment",
        "quand", "où", "pourquoi", "combien",
    ),
    "ru": (
        "что", "кто", "как", "когда", "где", "зачем", "почему", "сколько",
        "какой", "какая", "какие", "разве", "неужели",
    ),
}

# Prefijos SOLO si son claramente interrogativos (evitar «Hay un chisme?»).
_QUESTION_PREFIXES = {
    "es": ("por qué ", "para qué ", "a que no ", "verdad que ", "sabes si "),
    "en": ("is it ", "are you ", "do you ", "can you ", "could you ", "will you "),
    "fr": ("est-ce que ", "est-ce "),
    "ru": ("разве ",),
}

_CAP_AFTER_PUNCT = {
    "es": re.compile(r"([.!?…])\s*([a-záéíóúñ])"),
    "en": re.compile(r"([.!?…])\s*([a-z])"),
    "fr": re.compile(r"([.!?…])\s*([a-zàâäéèêëïîôùûüç])"),
    "ru": re.compile(r"([.!?…])\s*([а-яё])"),
}

_MULTI_SPACE = re.compile(r"\s+")
_REPEAT_WORD = re.compile(r"\b(\w{3,})\s+\1\b", re.IGNORECASE)


def _lang_code(lang: str | None) -> str:
    return normalize_transcript_lang(lang)


def _capitalize_sentence(text: str) -> str:
    text = _MULTI_SPACE.sub(" ", text.strip())
    if not text:
        return ""
    return text[0].upper() + text[1:] if len(text) > 1 else text.upper()


_PERIOD_ABBREVS = frozenset(
    {
        "sr",
        "sra",
        "srta",
        "dr",
        "dra",
        "prof",
        "etc",
        "pág",
        "pag",
        "núm",
        "num",
        "vol",
        "cap",
        "art",
        "arts",
        "ud",
        "uds",
        "excmo",
        "ilmo",
        "lic",
        "ing",
        "arq",
    }
)


def pair_spanish_inverted_punctuation(text: str) -> str:
    """Empareja ¿→? y ¡→! en TODO el texto.

    Corrige chapuzas del ASR/pulido: «¿Cómo… café.», «link ¿Cuánto… renta.»,
    y nunca deja ¿/¡ huérfanos con punto o sin cierre.
    """
    if not text or ("¿" not in text and "¡" not in text):
        return text
    # «Compárteme el link ¿Cuánto…» → punto antes de nueva pregunta/exclamación.
    t = re.sub(r"([a-záéíóúüñ0-9»”\'\"])\s+(¿)", r"\1. \2", text, flags=re.I)
    t = re.sub(r"([a-záéíóúüñ0-9»”\'\"])\s+(¡)", r"\1. \2", t, flags=re.I)
    t = _pair_opener_spans(t, "¿", "?")
    t = _pair_opener_spans(t, "¡", "!")
    return t


def _is_abbrev_period(s: str, body_start: int, dot_idx: int) -> bool:
    chunk = s[max(body_start, dot_idx - 24) : dot_idx + 1]
    m = re.search(r"([A-Za-zÁÉÍÓÚÜáéíóúüñÑ]+)\.$", chunk)
    if not m:
        return False
    return m.group(1).casefold() in _PERIOD_ABBREVS


def _span_end(s: str, body_start: int) -> tuple[int, bool]:
    """Índice del cierre de cláusula y si había signo terminal consumible."""
    j = body_start
    n = len(s)
    while j < n:
        c = s[j]
        if c in "\n¿¡":
            return j, False
        if c in "?!":
            return j, True
        if c in ".…":
            if c == "." and _is_abbrev_period(s, body_start, j):
                j += 1
                continue
            if (
                c == "."
                and j > 0
                and s[j - 1].isdigit()
                and j + 1 < n
                and s[j + 1].isdigit()
            ):
                j += 1
                continue
            rest = s[j + 1 :]
            # Fin de pregunta/exclamación ante nueva frase u opener.
            if re.match(r"\s*(?:$|[\n¿¡]|[A-ZÁÉÍÓÚÑÜ«\"'“])", rest):
                return j, True
            # Punto dudoso ante minúscula: seguir (no cortar la pregunta).
            if re.match(r"\s+[a-záéíóúüñ]", rest):
                j += 1
                continue
            return j, True
        j += 1
    return n, False


def _pair_opener_spans(s: str, opener: str, closer: str) -> str:
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] != opener:
            out.append(s[i])
            i += 1
            continue
        body_start = i + 1
        end_idx, had_punct = _span_end(s, body_start)
        body = s[body_start:end_idx].rstrip()
        if not body:
            out.append(opener)
            i = body_start
            continue
        out.append(f"{opener}{body}{closer}")
        i = end_idx + (1 if had_punct else 0)
    return "".join(out)


def _likely_question(text: str, lang: str) -> bool:
    """Solo marcar pregunta si hay indicios claros. Nunca inventar ¿? por duda."""
    raw = (text or "").strip()
    if not raw:
        return False
    # Ya viene con ¿ de apertura: pregunta real (p. ej. «¿Tienes link?»).
    # Evita dejar ¿ huérfano con punto final.
    if raw.startswith("¿"):
        return True
    # Un "?" final NO basta: Whisper/IA lo ponen en frases afirmativas.
    low = raw.lower().lstrip("¿¡¿").rstrip("?!….").strip()
    if len(low) < 10:
        return False
    letters = [c for c in low if c.isalpha()]
    if len(letters) < 8:
        return False
    tokens = low.split()
    if not tokens:
        return False
    starters = _QUESTION_STARTERS.get(lang, ())
    if tokens[0].rstrip(",.;:") in starters:
        return True
    if len(tokens) >= 2 and f"{tokens[0]} {tokens[1]}" in {
        "por qué",
        "para qué",
        "por que",
        "para que",
    }:
        return True
    prefixes = _QUESTION_PREFIXES.get(lang, ())
    if any(low.startswith(p) for p in prefixes):
        return True
    if lang == "es" and (
        low.endswith(", no") or low.endswith(", verdad") or low.endswith(" o qué")
    ):
        return True
    return False


def ensure_end_punctuation(text: str, lang: str | None = None) -> str:
    code = _lang_code(lang)
    text = text.strip()
    if not text:
        return ""
    # Nunca producir «muy,.» / «comida,.»: limpiar cola defectuosa.
    text = re.sub(r"[,:;]+([.!?…]*)$", r"\1", text).rstrip()
    if not text:
        return ""
    if code == "es" and ("¿" in text or "¡" in text):
        text = pair_spanish_inverted_punctuation(text)
        if not text:
            return ""
    if text[-1] == "?":
        if _likely_question(text, code):
            return text
        # Quitar también ¿/¡ huérfanos al degradar a afirmación.
        return text.rstrip("?").rstrip().lstrip("¿¡") + "."
    if text[-1] in ".!…":
        # «¿Tienes link.» → emparejar cierre si ya había apertura.
        if text.startswith("¿") and text[-1] == ".":
            return text[:-1] + "?"
        if text.startswith("¡") and text[-1] == ".":
            return text[:-1] + "!"
        return text
    if _looks_garbled(text):
        return text.rstrip("¿¡") + "."
    if _likely_question(text, code):
        body = text.rstrip(".")
        if code == "es" and not body.startswith("¿"):
            return "¿" + body + "?"
        return body + "?"
    return text + "."


def _looks_garbled(text: str) -> bool:
    t = text.strip().lower()
    if not t:
        return True
    if re.search(r"\b(?:no\s+s\s+si|ning\s+gestor|soltadilla)\b", t):
        return True
    tokens = re.findall(r"[a-záéíóúüñ]+", t, flags=re.I)
    if len(tokens) >= 4:
        short = sum(1 for w in tokens if len(w) <= 2)
        if short / len(tokens) >= 0.55:
            return True
    return False


def polish_fragment(
    text: str,
    *,
    light_fillers: bool = True,
    lang: str | None = None,
    fast: bool = False,
) -> str:
    code = _lang_code(lang)
    t = _MULTI_SPACE.sub(" ", (text or "").strip())
    if not t:
        return ""
    if fast:
        return _capitalize_sentence(t)
    if light_fillers:
        filler = _FILLER_PATTERNS.get(code, _FILLER_PATTERNS["es"])
        t = filler.sub("", t)
        t = _MULTI_SPACE.sub(" ", t).strip(" ,.")
    for _ in range(3):
        t2 = _REPEAT_WORD.sub(r"\1", t)
        if t2 == t:
            break
        t = t2
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    cap_re = _CAP_AFTER_PUNCT.get(code, _CAP_AFTER_PUNCT["es"])
    t = cap_re.sub(lambda m: m.group(1) + " " + m.group(2).upper(), t)
    t = _capitalize_sentence(t)
    return t


def merge_segments(
    segments: list[TranscriptSegment],
    *,
    max_gap: float = 0.65,
    lang: str | None = None,
    fast: bool = False,
) -> list[TranscriptSegment]:
    if not segments:
        return []
    merged: list[TranscriptSegment] = []
    buf_text: list[str] = []
    start = segments[0].start
    end = segments[0].end

    def flush() -> None:
        nonlocal buf_text, start, end
        if not buf_text:
            return
        text = polish_fragment(" ".join(buf_text), lang=lang, fast=fast)
        if text:
            merged.append(TranscriptSegment(start, end, text))
        buf_text = []

    for seg in segments:
        raw = seg.text.strip()
        if not raw:
            end = max(end, seg.end)
            continue
        gap = seg.start - end if buf_text else 0.0
        if buf_text and gap > max_gap:
            flush()
            start = seg.start
        if not buf_text:
            start = seg.start
        buf_text.append(raw)
        end = seg.end

    flush()
    return merged


def split_sentences(
    text: str, lang: str | None = None, *, fast: bool = False
) -> list[str]:
    text = polish_fragment(text, light_fillers=False, lang=lang, fast=fast)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?…])\s+", text)
    out: list[str] = []
    buf = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if buf and not _ends(buf):
            buf += " " + p
            continue
        if buf:
            out.append(ensure_end_punctuation(_capitalize_sentence(buf), lang))
        buf = p
    if buf:
        out.append(ensure_end_punctuation(_capitalize_sentence(buf), lang))
    return [s for s in out if len(s) > 2]


def _ends(text: str) -> bool:
    return bool(text) and text[-1] in ".!?…"


# Inicios típicos de frase en español (NO nombres propios / marcas).
_ES_SENTENCE_STARTERS = frozenset(
    {
        "entonces",
        "pero",
        "aunque",
        "porque",
        "luego",
        "también",
        "tambien",
        "además",
        "ademas",
        "ahora",
        "cuando",
        "donde",
        "mientras",
        "después",
        "despues",
        "antes",
        "finalmente",
        "primero",
        "segundo",
        "sin",
        "no",
        "sí",
        "si",
        "y",
        "o",
        "yo",
        "él",
        "ella",
        "nosotros",
        "nosotras",
        "ellos",
        "ellas",
        "esto",
        "esta",
        "este",
        "estos",
        "estas",
        "ese",
        "esa",
        "esos",
        "esas",
        "hay",
        "es",
        "son",
        "soy",
        "estoy",
        "está",
        "estan",
        "están",
        "estamos",
        "fue",
        "era",
        "tengo",
        "tiene",
        "tenemos",
        "puedo",
        "puede",
        "quiero",
        "voy",
        "va",
        "vas",
        "vamos",
        "van",
        "dice",
        "dices",
        "dijeron",
        "ojalá",
        "ojala",
        "quizá",
        "quizas",
        "quizás",
        "bueno",
        "vale",
        "mira",
        "fíjate",
        "obviamente",
        "claramente",
        "realmente",
        "básicamente",
        "personalmente",
        "por",
        "para",
        "en",
        "con",
        "de",
        "al",
        "del",
        "la",
        "el",
        "los",
        "las",
        "un",
        "una",
        "me",
        "te",
        "se",
        "nos",
        "qué",
        "que",
        "quién",
        "quien",
        "cuál",
        "cual",
        "cómo",
        "como",
        "cuándo",
        "dónde",
        "cuánto",
        "así",
        "asi",
        "tu",
        "tú",
        "su",
        "nuestro",
        "nuestra",
        "nuestros",
        "nuestras",
        "vuestro",
        "vuestra",
        "cada",
        "toda",
        "todo",
        "todas",
        "todos",
        "muchas",
        "muchos",
        "gracias",
        "hola",
        "ok",
        "okay",
    }
)

# Conectores FUERTES al inicio de frase (mayúscula). Sin IGNORECASE:
# si no, «Sonríe para mí» → «Sonríe. para mí».
_ES_DISCOURSE_INJECT = re.compile(
    r"([a-záéíóúüñ])\s+("
    r"Si\s+uno|Y\s+si|Entonces,|Por\s+eso|"
    r"Para\s+mí|Y\s+están|Y\s+yo|Ojalá|"
    r"Sin\s+embargo|No\s+obstante|"
    r"En\s+cambio|De\s+hecho|Al\s+final|"
    r"Ahora\s+bien|En\s+resumen|"
    r"En\s+conclusión|Dicho\s+esto|"
    r"Es\s+más,|Así\s+que|O\s+sea"
    r")\b"
)

# Palabra que NO cierra frase + punto + mayúscula → corte falso típico del ASR.
_WEAK_LEFT_BEFORE_PERIOD = re.compile(
    r"(?i)\b("
    r"[a-záéíóúüñ]+mente|"
    r"también|tambien|además|ademas|tampoco|"
    r"siempre|nunca|aún|aun|así|asi|solo|sólo|"
    r"ya|aquí|aqui|allí|alli|ahora|después|despues|antes|luego|"
    r"que|y|o|pero|porque|aunque|como|cuando|donde|"
    r"muy|más|mas|menos|tan|tanto|poco|mucho|todo|toda|todos|todas|"
    r"este|esta|estos|estas|ese|esa|esos|esas|aquel|aquella|"
    r"un|una|unos|unas|el|la|los|las|mi|tu|su|me|te|se|nos|"
    r"con|sin|por|para|de|del|al|en|entre|sobre|desde|hasta|"
    r"es|son|era|fue|ser|estar|está|están|estan|hay|"
    r"tiene|tienen|puede|pueden|debe|deben|quiere|quieren|"
    r"hace|hacen|dice|dices|digo|vamos|van|voy|va"
    r")\.[ \t]+([¿¡]?[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚáéíóúüñ’'-]*)"
)

# «que no. Hay que» / «y no. También» — no/sí solos no se unen a cualquier frase.
_NO_SI_FALSE_BREAK = re.compile(
    r"(?i)\b((?:que\s+)?(?:no|sí|si))"
    r"\.[ \t]+"
    r"(Hay|También|Tambien|Además|Ademas|Es|Está|Esta|Están|Estan|"
    r"Puede|Pueden|Debe|Tiene|Hace|Va|Van|Vamos)\b"
)

# Minúscula + mayúscula de arranque de oración sin punto (falta punto y seguido).
# No incluir El/La/Los/Un: destroza títulos («en La Tierra»).
_MISSING_PERIOD_BEFORE_START = re.compile(
    r"([a-záéíóúüñ])[ \t]+("
    r"(?:Solo|Sólo|Este|Esta|Estos|Estas|"
    r"Eso|Esa|Ese|Esos|Esas|Yo|Él|Ella|Nosotros|Nosotras|"
    r"Tu|Tú|Usted|Ustedes|"
    r"Entonces|Pero|Aunque|Además|También|Por\s+eso|Por\s+tanto|"
    r"Sin\s+embargo|No\s+obstante|En\s+cambio|De\s+hecho|Después|Antes|"
    r"Finalmente|Primero|Segundo|Ojalá|Hay\s+que|Si\s+uno|"
    r"Así\s+que|Es\s+más|Enhorabuena|Usa|Usad|Mirad|Mira|Mire|Miren|"
    r"Sonríe|Sonrie|Sonreíd|Escucha|Escuche|Escuchen|Oye|Oiga|"
    r"Ven|Venga|Vengan|Dame|Dime|Dile|Haz|Hazme|Espera|Espere|"
    r"Fíjate|Fijate|Cállate|Callate|"
    r"Vale|Bueno|Ok|Okay|Gracias|Hola|"
    r"Vas|Vamos|Van|Voy|Que|Qué|Ya|Ahora|Cada|Toda|Todo|"
    r"Todas|Todos|Muchas|Muchos|"
    r"Si(?=\s+[a-záéíóúñ]))"
    r")\b"
)

# «…ahí Sonríe» / «…aquí Mira»: locativo + mayúscula = frase nueva.
_LOCATIVE_CAP_START = re.compile(
    r"(?i)\b(ahí|aqui|aquí|allí|alli|entonces|luego|después|despues|ahora)"
    r"[ \t]+([A-ZÁÉÍÓÚÑ][A-Za-záéíóúüñ]{2,})\b"
)

# "Tampoco O al menos" / "fuego Y el" — conjunción suelta en mayúsculas (ASR).
_LONE_CAP_CONJ = re.compile(
    r"(?<=[a-záéíóúüñ])[ \t]+([OYA])[ \t]+(?=[a-záéíóúüñ])"
)

# "Google. Cloud" / "Iván. Nardini" / "Anthropic. Coding"
# Solo espacios en la misma línea: \s incluiría \n\n y aplastaría párrafos.
_FALSE_NAME_BREAK = re.compile(
    r"\b([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚáéíóúüñ’'-]{0,40})"
    r"\.[ \t]+"
    r"([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚáéíóúüñ’'-]{0,40})\b"
)


def _inject_sentence_periods(text: str, lang: str) -> str:
    """Punto delante de conectores fuertes; nunca ante cualquier mayúscula."""
    if lang != "es" or not text:
        return text
    t = _ES_DISCOURSE_INJECT.sub(r"\1. \2", text)
    t = _MISSING_PERIOD_BEFORE_START.sub(r"\1. \2", t)

    def _loc(m: re.Match[str]) -> str:
        right = m.group(2)
        if right.casefold() in {
            "el",
            "la",
            "los",
            "las",
            "un",
            "una",
            "su",
            "sus",
            "de",
            "del",
            "al",
            "en",
            "con",
            "por",
            "para",
        }:
            return m.group(0)
        return f"{m.group(1)}. {right}"

    t = _LOCATIVE_CAP_START.sub(_loc, t)
    return t


# Tras un falso «palabra. También» se une; tras «…más. Por tanto» se conserva.
_KEEP_PERIOD_BEFORE = frozenset(
    {
        "por",
        "entonces",
        "pero",
        "aunque",
        "que",
        "qué",
        "vas",
        "vamos",
        "voy",
        "van",
        "va",
        "si",
        "ya",
        "ahora",
        "cada",
        "toda",
        "todo",
        "todas",
        "todos",
        "así",
        "asi",
        "gracias",
        "hola",
        "tu",
        "tú",
        "yo",
        "él",
        "ella",
        "nosotros",
        "nosotras",
        "después",
        "despues",
        "antes",
        "finalmente",
        "primero",
        "segundo",
        "ok",
        "okay",
        "vale",
        "bueno",
        "estoy",
        "estamos",
        "están",
        "estan",
        "hay",
    }
)


def _heal_weak_false_breaks(text: str) -> str:
    """Quita punto y seguido falso: «técnicamente. También» → «técnicamente también»."""

    def _join(m: re.Match[str]) -> str:
        left, right = m.group(1), m.group(2)
        if right.startswith(("¿", "¡")):
            return m.group(0)
        right_tok = right.casefold()
        if right_tok in _KEEP_PERIOD_BEFORE or right_tok.startswith("por "):
            return m.group(0)
        lowered = right[0].lower() + right[1:] if right else right
        return f"{left} {lowered}"

    t = text
    for _ in range(6):
        nxt = _WEAK_LEFT_BEFORE_PERIOD.sub(_join, t)
        nxt = _NO_SI_FALSE_BREAK.sub(_join, nxt)
        if nxt == t:
            break
        t = nxt
    return t


# «utiliza. El mismo» / «propias. Toallas» / «Putin no. Es»
_MID_CLAUSE_BREAK = re.compile(
    r"(?i)\b([a-záéíóúüñ]{2,})\.\s+("
    r"El|La|Los|Las|Un|Una|Su|Sus|Es|Esta|Este|Estos|Estas|"
    r"Porque|Que|Y|"
    r"Toallas|Todo|Todos|Todas|Eso|Esa|Ese"
    r")\b"
)

# Cola «muy,.» / «comida,.»
_COMMA_PERIOD = re.compile(r",\s*\.")


def _heal_mid_clause_breaks(text: str) -> str:
    def _join(m: re.Match[str]) -> str:
        left, right = m.group(1), m.group(2)
        left_l = left.casefold()
        right_l = right.casefold()
        # «mono. Es genial» es frase nueva; «no. Es el único» se une.
        if right_l == "es" and left_l not in {"no", "sí", "si", "bueno", "vale", "claro"}:
            return m.group(0)
        if left_l in {
            "años",
            "días",
            "meses",
            "siglo",
            "país",
            "pais",
            "mundo",
            "vez",
            "veces",
            "hombre",
            "mujer",
            "gente",
            "equipo",
            "investigación",
            "investigacion",
            "mono",
            "genial",
        }:
            return m.group(0)
        if len(left) >= 8 and left_l.endswith(
            ("ción", "sión", "cion", "sion", "dad", "tad", "umbre", "encia", "ancia")
        ):
            return m.group(0)
        lowered = right[0].lower() + right[1:] if right else right
        return f"{left} {lowered}"

    t = text
    for _ in range(4):
        nxt = _MID_CLAUSE_BREAK.sub(_join, t)
        if nxt == t:
            break
        t = nxt
    return t


def heal_false_sentence_breaks(text: str, lang: str | None = None) -> str:
    """Reúne cortes falsos (nombres/marcas y punto antes de mayúscula indebida)."""
    if not text:
        return text
    code = _lang_code(lang)
    if code != "es":
        return text

    t = _COMMA_PERIOD.sub(".", text)
    t = _LONE_CAP_CONJ.sub(lambda m: f" {m.group(1).lower()} ", t)
    t = _heal_weak_false_breaks(t)
    t = _heal_mid_clause_breaks(t)

    def _join_name(m: re.Match[str]) -> str:
        left, right = m.group(1), m.group(2)
        if right.casefold() in _ES_SENTENCE_STARTERS:
            return m.group(0)
        if len(left) <= 2 and right.casefold() in _ES_SENTENCE_STARTERS:
            return m.group(0)
        return f"{left} {right}"

    for _ in range(4):
        nxt = _FALSE_NAME_BREAK.sub(_join_name, t)
        if nxt == t:
            break
        t = nxt
    t = re.sub(r"([.!?…])[^\S\n]{2,}", r"\1 ", t)
    t = re.sub(r"[^\S\n]{2,}", " ", t)
    t = _COMMA_PERIOD.sub(".", t)
    return t


def repair_broken_paragraphs(text: str, lang: str | None = None) -> str:
    """Une párrafos partidos a mitad de frase (saltos raros / sin punto)."""
    if not text or "\n\n" not in text:
        return _COMMA_PERIOD.sub(".", text or "")
    code = _lang_code(lang)
    parts = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if len(parts) <= 1:
        return _COMMA_PERIOD.sub(".", text)

    def _merge(a: str, b: str) -> str:
        a = re.sub(r"[,:;]+\s*$", "", a.rstrip())
        if _should_strip_period(a, b):
            a = re.sub(r"\.\s*$", "", a.rstrip())
        b0 = b[0].lower() + b[1:] if b and b[0].isupper() and code == "es" else b
        return f"{a} {b0}".strip()

    out: list[str] = []
    buf = parts[0]
    for nxt in parts[1:]:
        if _should_merge_paragraphs(buf, nxt, code):
            buf = _merge(buf, nxt)
        else:
            out.append(buf)
            buf = nxt
    out.append(buf)
    return "\n\n".join(_COMMA_PERIOD.sub(".", p) for p in out)


def _should_strip_period(prev: str, nxt: str) -> bool:
    if not prev.endswith("."):
        return False
    return bool(
        re.match(
            r"^(El|La|Los|Las|Un|Una|Su|Sus|Es|Pero|Porque|Que|Y|Toallas|Todo)\b",
            nxt,
        )
    )


def _should_merge_paragraphs(prev: str, nxt: str, lang: str) -> bool:
    prev = prev.rstrip()
    nxt = nxt.strip()
    if not prev or not nxt:
        return True
    if prev.endswith((",", ";", ":")) or re.search(r",\s*\.$", prev):
        return True
    if prev[-1] not in ".!?…»\"')":
        return True
    if lang != "es" or not prev.endswith("."):
        return False
    if not re.match(
        r"^(El|La|Los|Las|Un|Una|Su|Sus|Es|Pero|Porque|Que|Y|Toallas|Todo|Todos)\b",
        nxt,
    ):
        return False
    last = prev[:-1].rstrip().split()[-1].casefold() if prev[:-1].strip() else ""
    if last in {
        "muy",
        "tan",
        "más",
        "mas",
        "no",
        "sí",
        "si",
        "propias",
        "propia",
        "propio",
        "propios",
        "utiliza",
        "tiene",
        "tienen",
        "son",
        "es",
        "era",
        "fue",
        "mismo",
        "misma",
    }:
        return True
    if last.endswith(("ar", "er", "ir", "ado", "ido", "ando", "endo", "izas", "iza")):
        return True
    return False


def _finish_es_sentence(part: str, lang: str | None) -> str:
    part = part.strip().rstrip(" ,;")
    if not part:
        return ""
    code = _lang_code(lang)
    return heal_false_sentence_breaks(
        ensure_end_punctuation(_capitalize_sentence(part), lang),
        code,
    )


# Cortes de oralidad: Whisper deja un bloque con comas y sin punto y seguido.
_RUNON_MARKER = re.compile(
    r"(?i)\s+(?=("
    r"pero\s+(?!que\b)|"
    r"aunque\s+|"
    r"el caso es que\b|"
    r"la verdad es que\b|"
    r"yo le (?:dije|digo)\b|"
    r"le digo\b|"
    r"le dije\b|"
    r"y hay un momento\b|"
    r"o dependiendo\b"
    r"))"
)


def _split_runon_sentence(sent: str) -> list[str]:
    """Parte parrafadas orales largas; no toca frases cortas ni nombres."""
    sent = sent.strip()
    if len(sent) < 140:
        return [sent]
    cuts = [0]
    for m in _RUNON_MARKER.finditer(sent):
        left = sent[cuts[-1] : m.start()].strip()
        if len(left) >= 48:
            cuts.append(m.start())
    cuts.append(len(sent))
    parts = [sent[cuts[i] : cuts[i + 1]].strip() for i in range(len(cuts) - 1)]
    return [p for p in parts if p] or [sent]


def infer_sentences(
    text: str, lang: str | None = None, *, fast: bool = False
) -> list[str]:
    """Parte frases aunque Whisper no haya puesto puntos."""
    code = _lang_code(lang)
    t = polish_fragment(text, light_fillers=False, lang=lang, fast=fast)
    if not t:
        return []
    t = _inject_sentence_periods(t, code)
    t = heal_false_sentence_breaks(t, code)
    existing = split_sentences(t, lang, fast=fast)
    if not existing:
        existing = [t]

    boundary = re.compile(
        r"\s+(?=(?:Entonces|Pero|Aunque|Porque|Luego|"
        r"Sin embargo|No obstante|En cambio|De hecho|Al final|"
        r"Ahora bien|Yo |Ella |Él |Nosotros|Si uno|Y si|Y no|"
        r"Para mí|Es el|Es claro|Ojalá|Y están|"
        r"¿Qué|¿qué|Y yo|Entonces,|Por eso|Así que|Es más|"
        r"En resumen|En conclusión|Dicho esto)\b)",
        re.I,
    )

    out: list[str] = []
    for sent in existing:
        chunks = _split_runon_sentence(sent) if code == "es" else [sent]
        if (
            code == "es"
            and len(chunks) == 1
            and len(sent) >= 90
        ):
            more = [p.strip() for p in boundary.split(sent) if p.strip()]
            if len(more) > 1:
                chunks = more
        for part in chunks:
            finished = _finish_es_sentence(part, lang) if code == "es" else part
            if finished:
                out.append(finished)

    if out:
        return out
    return [ensure_end_punctuation(t, lang)]


def sentences_from_segments(
    segs: list[TranscriptSegment], lang: str | None = None
) -> list[str]:
    combined = " ".join(
        polish_fragment(s.text, lang=lang) for s in segs if s.text.strip()
    )
    return infer_sentences(combined, lang) if combined else []


def group_paragraphs(
    sentences: list[str],
    *,
    max_sentences: int = 4,
    max_chars: int = 400,
) -> list[str]:
    if not sentences:
        return []
    paras: list[str] = []
    chunk: list[str] = []
    chunk_len = 0

    for sent in sentences:
        slen = len(sent)
        if chunk and (
            len(chunk) >= max_sentences or chunk_len + slen > max_chars
        ):
            paras.append(" ".join(chunk))
            chunk = []
            chunk_len = 0
        chunk.append(sent)
        chunk_len += slen + 1

    if chunk:
        paras.append(" ".join(chunk))
    return paras


def chapter_label(seconds: float) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"
