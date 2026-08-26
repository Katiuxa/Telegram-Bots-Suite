"""Regresión: no meter puntos falsos ante nombres propios / marcas."""

import re

from bot.services.text_polish import (
    heal_false_sentence_breaks,
    infer_sentences,
    polish_fragment,
)
from bot.services.orthography import polish_spanish_readability


def test_heal_google_cloud_and_names():
    raw = (
        "Soy un developer advocate en Google. Cloud. "
        "Mi nombre. Soy Iván. Nardini. "
        "Trabajo con Anthropic. Coding. Agents en Cloud. Code."
    )
    fixed = heal_false_sentence_breaks(raw, "es")
    assert "Google Cloud" in fixed
    assert "Iván Nardini" in fixed
    assert "Anthropic Coding Agents" in fixed or "Anthropic Coding" in fixed
    assert "Cloud Code" in fixed
    assert "Google. Cloud" not in fixed
    assert "Iván. Nardini" not in fixed


def test_heal_keeps_real_sentence_breaks():
    raw = "Hola a todos. Estoy muy emocionado. Hay mucha gente."
    fixed = heal_false_sentence_breaks(raw, "es")
    assert "todos. Estoy" in fixed
    assert "emocionado. Hay" in fixed


def test_infer_sentences_does_not_split_proper_names():
    text = (
        "Para empezar me voy a presentar mi nombre soy Iván Nardini "
        "soy un developer advocate en Google Cloud trabajando con Anthropic"
    )
    sents = infer_sentences(text, "es")
    joined = " ".join(sents)
    assert "Iván. Nardini" not in joined
    assert "Google. Cloud" not in joined
    # Debe conservar los nombres juntos en alguna forma
    assert "Iván Nardini" in joined or "ivan nardini" in joined.casefold()
    assert "Google Cloud" in joined or "google cloud" in joined.casefold()


def test_polish_fragment_no_false_caps():
    t = polish_fragment("uso Google Cloud con Anthropic", lang="es", fast=False)
    assert "Google. Cloud" not in t


def test_infer_sentences_adds_periods_to_spoken_runon():
    text = (
        "aquí, del Caloco, y desde allí contemplar el eclipse, pero luego nos "
        "dimos cuenta que los árboles y la posición de la ermita haría muy "
        "difícil que desde ahí se contemplara. Escuchamos que en la piscina "
        "del pueblo y en las pistas de pádel que hay allí al lado, pues allí "
        "se iba a juntar la gente para verlo, pero decidimos arriesgarnos y "
        "intentar verlo desde nuestra terraza, aunque un monte, una loma, "
        "pues cuando llega el atardecer el sol se oculta y hay un momento en "
        "el que ya el atardecer o el ocultamiento final del sol cada día "
        "apenas se ve o dependiendo del momento del año hay momentos en los "
        "que sí se ve pero ahora en verano apenas se ve la maravillosa luz "
        "que estoy viendo yo ahora, de color anaranjado, de color violeta, "
        "y como en el cielo, el sol ocultándose pinta cuadros de rosco pero "
        "el caso es que yo le dije a Manuel, le digo, estoy convencido que "
        "desde nuestra casa vamos a"
    )
    sents = infer_sentences(text, "es")
    joined = " ".join(sents)
    assert joined.count(".") >= 5
    assert "contemplara." in joined
    assert re.search(r"\bPero decidimos\b", joined)
    assert re.search(r"\bAunque un monte\b", joined)
    assert "el caso es que" in joined.casefold()


def test_polish_spanish_readability_local_path_no_groq_needed(monkeypatch):
    monkeypatch.setattr("bot.services.orthography.GROQ_API_KEY", "")
    text = (
        "mi nombre soy Iván Nardini y trabajo en Google Cloud "
        "con Anthropic y Cloud Code en la presentación de hoy"
    )
    out = polish_spanish_readability(text, "es", paragraphs=True)
    assert "Iván. Nardini" not in out
    assert "Google. Cloud" not in out
    assert "Cloud. Code" not in out
