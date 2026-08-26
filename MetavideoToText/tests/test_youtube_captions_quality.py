"""YouTube captions: manuales primero; auto-ASR usable en vídeos largos."""

from pathlib import Path

from bot.services.youtube_captions import (
    _auto_quality_ok,
    _is_likely_auto_vtt,
    _quality_ok,
    parse_vtt,
)


FIXTURE = Path(__file__).resolve().parents[1] / "temp" / "caps_probe" / "cMGtFpXZuyI.es-orig.vtt"

_AUTO_VTT = """WEBVTT
Kind: captions
Language: es

00:00:01.000 --> 00:00:03.500
el sentido de la vida es el tema de hoy

00:00:03.500 --> 00:00:06.000
y vamos a hablar de la existencia de dios

00:00:06.000 --> 00:00:09.000
descubrir quién eres no es un lujo

00:00:09.000 --> 00:00:12.000
es la pregunta que nos hacemos todos

00:00:12.000 --> 00:00:15.000
en este camino filosófico largo

00:00:15.000 --> 00:00:18.000
con argumentos y no solo opiniones

00:00:18.000 --> 00:00:22.000
gracias por acompañarme en esta charla

00:00:22.000 --> 00:00:26.000
seguimos con la pregunta de quién eres
"""


def test_parse_youtube_rolling_uses_short_cues():
    if not FIXTURE.exists():
        return  # skip if probe not downloaded
    raw = FIXTURE.read_text(encoding="utf-8")
    segs = parse_vtt(raw)
    texts = [s.text for s in segs]
    # No debe concatenar la misma frase dos veces seguidas
    joined = " ".join(texts[:6])
    assert joined.count("la verdad está en el profeta de kalil") <= 1
    assert any("Gibrán" in t or "Gibran" in t for t in texts)


def test_auto_vtt_rejected_as_manual():
    if not FIXTURE.exists():
        return
    raw = FIXTURE.read_text(encoding="utf-8")
    assert _is_likely_auto_vtt(FIXTURE, raw) is True
    segs = parse_vtt(raw)
    assert _quality_ok(segs, "es", raw=raw, path=FIXTURE) is False


def test_auto_vtt_accepted_only_as_long_video_fallback():
    segs = parse_vtt(_AUTO_VTT)
    assert len(segs) >= 8
    assert _auto_quality_ok(segs, raw=_AUTO_VTT, path=Path("talk.es.vtt")) is True


def test_estas_not_converted_to_estas_accent():
    from bot.services.orthography import apply_asr_accent_rules

    assert apply_asr_accent_rules("estas cosas estan mal") == "estas cosas están mal"
