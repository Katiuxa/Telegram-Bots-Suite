"""Estado MP3 por enlace: no reutilizar audio de otro vídeo."""

from pathlib import Path

from bot.services.mp3_meta import (
    bind_link_mp3_session,
    bump_link_mp3_generation,
    clear_stale_link_mp3_session,
    get_link_mp3_generation,
    get_link_mp3_ready_url,
    link_mp3_session_matches,
    reset_link_mp3_workflow,
    set_link_mp3_ready_url,
    set_pending_link_mp3_url,
)
from bot.services.session_audio import has_session_audio, store_session_audio_source


class _Ctx:
    def __init__(self) -> None:
        self.user_data: dict = {}


def test_reset_link_mp3_workflow_clears_session(tmp_path: Path) -> None:
    ctx = _Ctx()
    audio = tmp_path / "old.mp3"
    audio.write_bytes(b"fake")
    store_session_audio_source(ctx, 1, audio, None)
    bind_link_mp3_session(ctx, "https://youtu.be/old")
    set_pending_link_mp3_url(ctx, "https://youtu.be/old")
    set_link_mp3_ready_url(ctx, "https://youtu.be/old")
    ctx.user_data["link_mp3_dl_state"] = "done"

    reset_link_mp3_workflow(ctx)

    assert not has_session_audio(ctx)
    assert get_link_mp3_ready_url(ctx) is None
    assert ctx.user_data.get("link_mp3_dl_state") is None
    assert ctx.user_data.get("pending_link_mp3_url") is None
    assert get_link_mp3_generation(ctx) == 1


def test_ready_url_without_session_binding_is_not_reused(tmp_path: Path) -> None:
    ctx = _Ctx()
    audio = tmp_path / "old.mp3"
    audio.write_bytes(b"fake")
    store_session_audio_source(ctx, 1, audio, None)
    set_link_mp3_ready_url(ctx, "https://youtu.be/yNbtF-XASbY")

    assert not link_mp3_session_matches(ctx, "https://youtu.be/yNbtF-XASbY")


def test_session_requires_source_id_for_youtube(tmp_path: Path) -> None:
    ctx = _Ctx()
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"fake")
    url = "https://youtu.be/yNbtF-XASbY"
    store_session_audio_source(ctx, 1, audio, None)
    bind_link_mp3_session(ctx, url, source_id="yNbtF-XASbY")

    assert link_mp3_session_matches(ctx, url)
    assert link_mp3_session_matches(
        ctx, "https://www.youtube.com/watch?v=yNbtF-XASbY"
    )
    assert not link_mp3_session_matches(ctx, "https://youtu.be/7aGJYNkzAXI")


def test_clear_stale_keeps_matching_session(tmp_path: Path) -> None:
    ctx = _Ctx()
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"fake")
    url = "https://youtu.be/abc12345678"
    store_session_audio_source(ctx, 1, audio, None)
    bind_link_mp3_session(ctx, url, source_id="abc12345678")

    clear_stale_link_mp3_session(ctx, "https://www.youtube.com/watch?v=abc12345678")

    assert has_session_audio(ctx)
    assert link_mp3_session_matches(ctx, url)


def test_clear_stale_removes_wrong_session(tmp_path: Path) -> None:
    ctx = _Ctx()
    audio = tmp_path / "old.mp3"
    audio.write_bytes(b"fake")
    store_session_audio_source(ctx, 1, audio, None)
    bind_link_mp3_session(ctx, "https://youtu.be/old11111111", source_id="old11111111")

    clear_stale_link_mp3_session(ctx, "https://youtu.be/new22222222")

    assert not has_session_audio(ctx)
    assert get_link_mp3_ready_url(ctx) is None


def test_generation_bump_invalidates_stale_completion() -> None:
    ctx = _Ctx()
    gen = bump_link_mp3_generation(ctx)
    assert gen == 1
    bump_link_mp3_generation(ctx)
    assert get_link_mp3_generation(ctx) == 2
