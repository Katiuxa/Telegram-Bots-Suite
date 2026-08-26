"""Descarga por enlace: no reutilizar archivos temp de otro vídeo."""

from pathlib import Path

from bot.services.media import _find_downloaded_file, _validate_download_path


def test_find_downloaded_file_requires_exact_youtube_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("bot.services.media.TEMP_DIR", tmp_path)
    old = tmp_path / "7aGJYNkzAXI.m4a"
    new = tmp_path / "yNbtF-XASbY.m4a"
    old.write_bytes(b"old")
    new.write_bytes(b"new")

    since = new.stat().st_mtime + 1
    found = _find_downloaded_file(
        {"id": "yNbtF-XASbY"},
        since,
        expected_id="yNbtF-XASbY",
    )
    assert found == new
    assert found != old

    missing = _find_downloaded_file(
        {"id": "yNbtF-XASbY"},
        since,
        expected_id="yNbtF-XASbY",
    )
    assert missing == new

    wrong = _find_downloaded_file(
        {"id": "missingid12"},
        since,
        expected_id="missingid12",
    )
    assert wrong is None


def test_validate_download_path_rejects_wrong_file(tmp_path: Path) -> None:
    path = tmp_path / "7aGJYNkzAXI.m4a"
    path.write_bytes(b"x")
    url = "https://youtu.be/yNbtF-XASbY"
    meta = {"id": "yNbtF-XASbY"}
    try:
        _validate_download_path(path, url, meta)
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass


def test_two_hour_youtube_is_allowed() -> None:
    from bot.config import MAX_YOUTUBE_DOWNLOAD_MB, MAX_YOUTUBE_DURATION_SEC
    from bot.services.media import (
        _check_download_size,
        _check_duration,
        _is_audio_only_format,
    )

    url = "https://www.youtube.com/watch?v=VjBEuNnRPXE"
    # El vídeo real dura 7584 s (~2 h 6 min) y el audio ~106 MB
    assert 7584 < MAX_YOUTUBE_DURATION_SEC
    _check_duration({"duration": 7584}, url)
    _check_download_size(
        {"filesize": 111_465_787, "duration": 7584, "vcodec": "none"},
        url,
        "es",
    )
    assert 111_465_787 < MAX_YOUTUBE_DOWNLOAD_MB * 1024 * 1024
    assert _is_audio_only_format({"vcodec": "none", "acodec": "opus", "ext": "webm"})
    assert _is_audio_only_format({"vcodec": None, "acodec": "mp4a.40.2", "ext": "m4a"})
    assert not _is_audio_only_format(
        {"vcodec": "avc1.640028", "acodec": "mp4a.40.2", "ext": "mp4", "width": 1280}
    )


def test_youtube_shorts_url_detected() -> None:
    from bot.services.media import is_youtube_shorts_url, is_youtube_url
    from bot.services.youtube_captions import try_fetch_youtube_captions

    short = "https://www.youtube.com/shorts/l_pYmDnjCGs"
    assert is_youtube_url(short)
    assert is_youtube_shorts_url(short)
    assert not is_youtube_shorts_url("https://www.youtube.com/watch?v=VjBEuNnRPXE")
    assert try_fetch_youtube_captions(short, "es") is None
    assert try_fetch_youtube_captions(short, "es", allow_auto=True) is None
