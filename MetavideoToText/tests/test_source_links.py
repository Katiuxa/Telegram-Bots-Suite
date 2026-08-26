"""Comparación de enlaces al mismo vídeo."""

from bot.services.source_links import same_media_url


def test_same_youtube_urls_different_hosts() -> None:
    a = "https://youtu.be/yNbtF-XASbY?is=3pwMT9P3pKnlHDGO"
    b = "https://www.youtube.com/watch?v=yNbtF-XASbY"
    assert same_media_url(a, b)


def test_different_youtube_urls() -> None:
    a = "https://youtu.be/yNbtF-XASbY"
    b = "https://youtu.be/abcdefghijk"
    assert not same_media_url(a, b)


def test_same_media_url_empty() -> None:
    assert not same_media_url("", "https://youtu.be/yNbtF-XASbY")
    assert not same_media_url("https://youtu.be/yNbtF-XASbY", None)
