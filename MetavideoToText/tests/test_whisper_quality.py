from bot.services.whisper_quality import filter_segment_dicts, segment_likely_hallucination


def test_music_borderline_nsp_kept_when_logprob_ok():
    """Regresión: nsp≈0.56 no debe borrar letra real (caso Instagram/rap)."""
    seg = {
        "text": "Rien qu'on se croirait dans un film",
        "no_speech_prob": 0.5576172,
        "compression_ratio": 1.8085107,
        "avg_logprob": -0.19517738,
    }
    assert segment_likely_hallucination(seg) is False


def test_hard_no_speech_still_dropped():
    seg = {
        "text": "mmm",
        "no_speech_prob": 0.92,
        "compression_ratio": 1.2,
        "avg_logprob": -0.2,
    }
    assert segment_likely_hallucination(seg) is True


def test_filter_keeps_full_music_clip():
    segments = [
        {
            "start": 0.0,
            "end": 4.1,
            "text": " Rien qu'on se croirait dans un film",
            "no_speech_prob": 0.5576172,
            "compression_ratio": 1.8085107,
            "avg_logprob": -0.19517738,
        },
        {
            "start": 28.3,
            "end": 31.2,
            "text": " Mais tout a commencé par un jeu de regard",
            "no_speech_prob": 0.2692871,
            "compression_ratio": 1.1318681,
            "avg_logprob": -0.19614895,
        },
    ]
    kept = filter_segment_dicts(segments)
    assert len(kept) == 2
