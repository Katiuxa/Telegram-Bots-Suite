import re

from dataclasses import dataclass



from bot.config import MOMENT_BUCKET_SEC, SPEAKER_GAP_SEC

from bot.services.text_polish import (

    chapter_label as _chapter_label,

    ensure_end_punctuation,

    merge_segments,

    polish_fragment,

    split_sentences,

)

from bot.services.transcribe import TranscriptSegment



SECTION_SEP = "\n\n━━━\n\n"





@dataclass

class MomentBlock:

    index: int

    start: float

    end: float

    title: str

    bullets: list[str]

    body: str = ""





def format_timestamp(seconds: float) -> str:

    return _chapter_label(seconds)





def _subtitle_lines(segments: list[TranscriptSegment]) -> list[str]:
    """Una línea por frase, con el tiempo en que empieza (sin tramos largos)."""
    lines: list[str] = []
    for seg in segments:
        raw = (seg.text or "").strip()
        if not raw:
            continue
        text = polish_fragment(raw)
        if not text:
            continue
        sents = split_sentences(text) if len(text) > 55 else [ensure_end_punctuation(text)]
        if not sents:
            continue
        if len(sents) == 1:
            lines.append(f"[{format_timestamp(seg.start)}]  {sents[0]}")
            continue
        dur = max(seg.end - seg.start, 0.05)
        n = len(sents)
        for i, sent in enumerate(sents):
            if not sent.strip():
                continue
            t = seg.start + dur * (i / n)
            lines.append(f"[{format_timestamp(t)}]  {sent}")
    return lines


def format_subtitles(segments: list[TranscriptSegment]) -> str:
    if not segments:
        return ""
    # Trozos cortos de Whisper: no fusionar en bloques de 180 caracteres
    merged = merge_segments(segments, max_gap=0.35)
    lines = _subtitle_lines(merged)
    if not lines:
        lines = _subtitle_lines(segments)
    header = (
        "SUBTÍTULOS CON TIEMPOS\n"
        "(Una frase por línea; el [mm:ss] es cuando empieza esa frase.)\n\n"
    )
    return header + "\n".join(lines)





def _capitalize(text: str) -> str:

    return polish_fragment(text, light_fillers=False)





_FILLER_START = re.compile(
    r"^(?:eh|em|bueno|vale|pues|entonces|o sea|y |pero |a ver|mira)\b",
    re.I,
)


def _title_score(sentence: str) -> float:
    words = sentence.split()
    n = len(words)
    score = 0.0
    if 5 <= n <= 14:
        score += 2.5
    elif 4 <= n < 5:
        score += 1.0
    elif n < 4:
        score -= 3.0
    elif n > 16:
        score -= 1.5
    if _FILLER_START.search(sentence.strip()):
        score -= 4.0
    if sentence.strip().endswith("?"):
        score -= 0.5
    return score


def _moment_title(texts: list[str]) -> str:
    """Título breve del tramo (tema), no la primera palabra literal del audio."""
    if not texts:
        return "Parte"
    bullets = _moment_bullets(texts, max_items=3)
    if bullets:
        pick = max(bullets, key=_title_score)
        title = pick.rstrip(".!?…").strip()
    else:
        full = polish_fragment(" ".join(texts))
        sentences = split_sentences(full) if full else []
        if not sentences:
            title = _capitalize(texts[0])[:80]
        else:
            title = max(sentences, key=_title_score).rstrip(".!?…").strip()
    words = title.split()
    if len(words) > 10:
        title = " ".join(words[:10]) + "…"
    return title or "Parte"





def _moment_bullets(texts: list[str], *, max_items: int = 5) -> list[str]:

    sentences = split_sentences(" ".join(texts))

    if not sentences:

        combined = _capitalize(" ".join(texts))

        return [combined[:200] + ("…" if len(combined) > 200 else "")] if combined else []

    bullets: list[str] = []

    for s in sentences:

        if len(s) > 160:

            s = s[:157].rsplit(" ", 1)[0] + "…"

        if s not in bullets:

            bullets.append(s)

        if len(bullets) >= max_items:

            break

    return bullets





def _adaptive_bucket_sec(total_dur: float) -> float:
    """Capítulos por tema/duración, no cubos fijos de 55 s."""
    if total_dur <= 90:
        return 40.0
    if total_dur <= 600:
        return 72.0
    if total_dur <= 1800:
        return 115.0
    if total_dur <= 3600:
        return 155.0
    target_chapters = min(36, max(10, int(total_dur / 240)))
    return max(90.0, total_dur / target_chapters)


def build_moment_blocks(
    segments: list[TranscriptSegment],
    *,
    smart_titles: bool = True,
    lang: str | None = None,
) -> list[MomentBlock]:
    from bot.services.transcript_lang import normalize_transcript_lang

    code = normalize_transcript_lang(lang)
    merged = merge_segments(segments, lang=code)

    if not merged:

        return []

    total_dur = merged[-1].end - merged[0].start
    bucket_sec = _adaptive_bucket_sec(max(total_dur, 1.0))

    raw_buckets: list[dict] = []

    bucket_start = merged[0].start

    texts: list[str] = []

    prev_end = merged[0].end



    for seg in merged:

        t = seg.text.strip()

        if not t:

            continue

        gap = seg.start - prev_end if texts else 0.0

        span = seg.start - bucket_start

        if texts and (span >= bucket_sec or gap >= SPEAKER_GAP_SEC):

            raw_buckets.append({"start": bucket_start, "end": prev_end, "texts": texts})

            bucket_start = seg.start

            texts = []

        texts.append(t)

        prev_end = seg.end



    if texts:

        raw_buckets.append({"start": bucket_start, "end": prev_end, "texts": texts})



    blocks: list[MomentBlock] = []
    for i, b in enumerate(raw_buckets, 1):
        raw_text = " ".join(b["texts"])
        body = polish_fragment(raw_text, lang=code)
        if code == "es":
            from bot.services.orthography import (
                apply_asr_accent_rules,
                needs_extra_ortho,
                polish_spanish_readability,
            )
            from bot.services.text_polish import group_paragraphs, infer_sentences

            body = apply_asr_accent_rules(body)
            sentences = infer_sentences(body, lang=code)
            paras = group_paragraphs(sentences, max_sentences=3, max_chars=300)
            body = "\n\n".join(paras) if paras else body
            if needs_extra_ortho(body):
                body = polish_spanish_readability(
                    body.replace("\n\n", " "), code, paragraphs=True
                )
        if len(body) > 3200:
            body = body[:3180].rsplit(" ", 1)[0] + "…"
        bullets = _moment_bullets(b["texts"])
        if code == "es" and bullets:
            from bot.services.orthography import restore_spanish_orthography

            bullets = [restore_spanish_orthography(x) for x in bullets]
        blocks.append(
            MomentBlock(
                index=i,
                start=b["start"],
                end=b["end"],
                title="…",
                bullets=bullets,
                body=body,
            )
        )
    if smart_titles and blocks:
        from bot.services.index_titles import assign_intelligent_titles

        assign_intelligent_titles(blocks, lang=code)
    elif blocks:
        from bot.services.index_titles import editorial_fallback_title

        for b in blocks:
            b.title = editorial_fallback_title(b.body, b.bullets)
    return blocks





def format_moments_markdown(blocks: list[MomentBlock]) -> str:

    if not blocks:

        return ""

    sections: list[str] = []

    for b in blocks:

        ts0 = format_timestamp(b.start)

        ts1 = format_timestamp(b.end)

        lines = [f"*{b.index}. {b.title}*", f"`{ts0}` – `{ts1}`", ""]

        for bullet in b.bullets:

            lines.append(f"• {bullet}")

        sections.append("\n".join(lines).rstrip())

    return SECTION_SEP.join(sections)





def format_moments_plain(blocks: list[MomentBlock]) -> str:

    if not blocks:

        return ""

    lines = [
        "ÍNDICE INTELIGENTE",
        "Capítulos del vídeo con título de tema y tiempo aproximado.",
        "",
    ]

    for b in blocks:

        lines.append(f"{b.index}. {b.title}")

        lines.append(f"   Tiempo: {format_timestamp(b.start)} – {format_timestamp(b.end)}")

        lines.append("")

        for bullet in b.bullets:

            lines.append(f"   • {bullet}")

        lines.append("")

    return "\n".join(lines).strip()





def format_moments(segments: list[TranscriptSegment]) -> str:

    blocks = build_moment_blocks(segments)

    if not blocks:

        return ""

    header = (

        "📑 *Índice por partes*\n"

        "_Tramos del vídeo con tiempos; abre el enlace de lectura si aparece._\n"

    )

    return header + SECTION_SEP + format_moments_markdown(blocks)





def moments_to_telegraph_nodes(blocks: list[MomentBlock]) -> list[dict]:

    nodes: list[dict] = [

        {

            "tag": "p",

            "children": ["Índice por capítulos. Usa los tiempos para saltar en el vídeo."],

        },

        {"tag": "hr"},

    ]

    for b in blocks:

        ts0 = format_timestamp(b.start)

        ts1 = format_timestamp(b.end)

        nodes.append({"tag": "h4", "children": [f"{b.index}. {b.title}"]})

        nodes.append(

            {

                "tag": "p",

                "children": [{"tag": "strong", "children": [f"⏱ {ts0} – {ts1}"]}],

            }

        )

        if b.bullets:

            nodes.append(

                {

                    "tag": "ul",

                    "children": [{"tag": "li", "children": [line]} for line in b.bullets],

                }

            )

        nodes.append({"tag": "hr"})

    if nodes and nodes[-1].get("tag") == "hr":

        nodes.pop()

    return nodes





def segments_from_stored(raw: list) -> list[TranscriptSegment]:

    out: list[TranscriptSegment] = []

    for item in raw or []:

        if isinstance(item, dict):

            out.append(

                TranscriptSegment(

                    float(item.get("s", 0)),

                    float(item.get("e", 0)),

                    str(item.get("t", "")),

                )

            )

    return out





def store_segments(segments: list[TranscriptSegment]) -> list[dict]:

    return [{"s": s.start, "e": s.end, "t": s.text} for s in segments]


