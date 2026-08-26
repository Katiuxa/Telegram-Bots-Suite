"""Reglas de metadatos MP3 (título / artista)."""

from bot.services.mp3_meta import (
    apply_mp3_direct_defaults,
    get_resolved_mp3_meta,
    try_handle_mp3_meta_text,
)


class _Ctx:
    def __init__(self) -> None:
        self.user_data: dict = {}


def test_empty_title_uses_video_default() -> None:
    ctx = _Ctx()
    ctx.user_data["mp3_default_title"] = "Video de TikTok"
    ctx.user_data["awaiting_mp3_title"] = True
    assert try_handle_mp3_meta_text(ctx, "") == "need_author"
    ctx.user_data["awaiting_mp3_author"] = True
    assert try_handle_mp3_meta_text(ctx, "") == "ready"
    title, author = get_resolved_mp3_meta(ctx)
    assert title == "Video de TikTok"
    assert author == ""


def test_user_title_empty_author() -> None:
    ctx = _Ctx()
    ctx.user_data["mp3_default_title"] = "Video de TikTok"
    ctx.user_data["awaiting_mp3_title"] = True
    assert try_handle_mp3_meta_text(ctx, "Mi pista") == "need_author"
    ctx.user_data["awaiting_mp3_author"] = True
    assert try_handle_mp3_meta_text(ctx, "") == "ready"
    title, author = get_resolved_mp3_meta(ctx)
    assert title == "Mi pista"
    assert author == ""


def test_user_title_and_author() -> None:
    ctx = _Ctx()
    ctx.user_data["awaiting_mp3_title"] = True
    try_handle_mp3_meta_text(ctx, "Mi pista")
    ctx.user_data["awaiting_mp3_author"] = True
    try_handle_mp3_meta_text(ctx, "Mi artista")
    title, author = get_resolved_mp3_meta(ctx)
    assert title == "Mi pista"
    assert author == "Mi artista"


def test_user_title_overrides_video_default() -> None:
    ctx = _Ctx()
    ctx.user_data["mp3_default_title"] = "Título del vídeo"
    ctx.user_data["awaiting_mp3_title"] = True
    try_handle_mp3_meta_text(ctx, "Otro nombre")
    ctx.user_data["awaiting_mp3_author"] = True
    try_handle_mp3_meta_text(ctx, "Artista X")
    title, author = get_resolved_mp3_meta(ctx)
    assert title == "Otro nombre"
    assert author == "Artista X"


def test_direct_download_uses_video_title_only() -> None:
    ctx = _Ctx()
    ctx.user_data["mp3_default_title"] = "Desde YouTube"
    ctx.user_data["mp3_meta_title"] = "Parcial"
    ctx.user_data["mp3_meta_author"] = "Parcial artista"
    apply_mp3_direct_defaults(ctx)
    title, author = get_resolved_mp3_meta(ctx)
    assert title == "Desde YouTube"
    assert author == ""
