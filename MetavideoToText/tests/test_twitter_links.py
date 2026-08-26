"""Detección y comparación de enlaces X/Twitter."""

from bot.services.media import (
    extract_social_url,
    is_twitter_url,
    looks_like_social_link,
    twitter_status_id,
)
from bot.services.source_links import media_source_kind, same_media_url


def test_looks_like_x_status_url() -> None:
    url = "https://x.com/elonmusk/status/1234567890123456789"
    assert looks_like_social_link(url)
    assert is_twitter_url(url)
    assert extract_social_url(f"Mira esto {url}") == url
    assert media_source_kind(url) == "twitter"
    assert twitter_status_id(url) == "1234567890123456789"


def test_looks_like_twitter_status_url() -> None:
    url = "https://twitter.com/user/status/9876543210"
    assert looks_like_social_link(url)
    assert is_twitter_url(url)
    assert twitter_status_id(url) == "9876543210"


def test_looks_like_twitter_i_status_url() -> None:
    url = "https://mobile.twitter.com/i/status/111222333444"
    assert looks_like_social_link(url)
    assert twitter_status_id(url) == "111222333444"


def test_looks_like_t_co_short_url() -> None:
    url = "https://t.co/abc123XYZ"
    assert looks_like_social_link(url)
    assert is_twitter_url(url)


def test_same_twitter_status_different_hosts() -> None:
    a = "https://twitter.com/foo/status/1234567890"
    b = "https://x.com/foo/status/1234567890"
    assert same_media_url(a, b)


def test_different_twitter_status_ids() -> None:
    a = "https://x.com/foo/status/111"
    b = "https://x.com/foo/status/222"
    assert not same_media_url(a, b)
