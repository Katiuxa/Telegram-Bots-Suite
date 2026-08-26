"""Tests del modo detección de idioma."""

from bot.services.transcript_lang import (
    AUTO_LANG,
    detected_language_label,
    is_auto_detect,
    normalize_source_lang,
    normalize_transcript_lang,
    polish_lang,
    same_language,
    set_auto_detect_mode,
    whisper_language,
)


class _Ctx:
    user_data: dict

    def __init__(self) -> None:
        self.user_data = {}


def test_auto_detect_mode():
    ctx = _Ctx()
    ctx.user_data["ui_lang"] = "es"
    code = set_auto_detect_mode(ctx)  # type: ignore[arg-type]
    assert code == AUTO_LANG
    assert ctx.user_data["transcript_lang"] == AUTO_LANG
    assert ctx.user_data["ui_lang"] == "es"
    assert is_auto_detect(AUTO_LANG)
    assert whisper_language(AUTO_LANG) is None


def test_detected_language_labels():
    assert detected_language_label("hi") == "Hindi"
    assert detected_language_label("ur") == "Urdu"
    assert detected_language_label("es") == "🇪🇸 Español"
    assert normalize_source_lang("hindi") == "hi"
    assert polish_lang("hi") == "en"
    assert same_language("hi", "hi")
    assert not same_language("hi", "es")


def test_should_auto_translate():
    from bot.services.transcript_lang import should_auto_translate

    assert should_auto_translate("", "hi", "es") is True
    assert should_auto_translate("hi", "hi", "es") is True
    assert should_auto_translate("es", "es", "es") is False
    assert should_auto_translate("en", "en", "en") is False
