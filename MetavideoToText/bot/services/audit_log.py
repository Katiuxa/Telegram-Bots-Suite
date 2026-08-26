"""Registro estructurado por usuario Telegram (tú vs otros)."""

from __future__ import annotations

import json
import logging
from typing import Any

from telegram import Update

from bot.config import is_admin

logger = logging.getLogger(__name__)

_MAX = 600


def _clip(text: str | None, limit: int = _MAX) -> str:
    s = (text or "").strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _who(uid: int | None) -> str:
    if uid is None:
        return "UNKNOWN"
    return "OWNER" if is_admin(uid) else "OTHER"


def _base(update: Update) -> dict[str, Any]:
    user = update.effective_user
    chat = update.effective_chat
    uid = user.id if user else None
    uname = ""
    if user:
        uname = user.username or user.first_name or str(uid)
    return {
        "who": _who(uid),
        "uid": uid,
        "user": uname,
        "chat": chat.id if chat else None,
    }


def audit(
    update: Update,
    *,
    phase: str,
    action: str,
    detail: str = "",
    response: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Una línea JSON en journalctl: [AUDIT] {...}"""
    payload = _base(update)
    payload["phase"] = phase  # in | out | err
    payload["action"] = action
    if detail:
        payload["in"] = _clip(detail)
    if response:
        payload["out"] = _clip(response)
    if extra:
        payload.update(extra)
    logger.info("[AUDIT] %s", json.dumps(payload, ensure_ascii=False))


def audit_command(update: Update, command: str) -> None:
    audit(update, phase="in", action="command", detail=command)


def audit_callback(update: Update, data: str) -> None:
    audit(update, phase="in", action="callback", detail=data)


def audit_message_in(update: Update) -> None:
    msg = update.message
    if not msg:
        return
    parts: list[str] = []
    if msg.text:
        parts.append(msg.text)
    elif msg.caption:
        parts.append(f"[caption] {msg.caption}")
    if msg.document:
        fn = msg.document.file_name or msg.document.mime_type or "document"
        parts.append(f"[doc {fn}]")
    if msg.audio:
        parts.append(f"[audio {msg.audio.file_name or 'audio'}]")
    if msg.voice:
        parts.append("[voice]")
    if msg.video:
        parts.append(f"[video {getattr(msg.video, 'file_name', '') or msg.video.file_unique_id}]")
    if msg.video_note:
        parts.append("[video_note]")
    audit(update, phase="in", action="message", detail=" ".join(parts) or "(vacío)")


def audit_out(update: Update | None, *, action: str, response: str, uid: int | None = None) -> None:
    if update is not None:
        audit(update, phase="out", action=action, response=response)
        return
    if uid is None:
        return
    payload = {
        "who": _who(uid),
        "uid": uid,
        "phase": "out",
        "action": action,
        "out": _clip(response),
    }
    logger.info("[AUDIT] %s", json.dumps(payload, ensure_ascii=False))


def audit_error(update: Update | None, *, action: str, error: str) -> None:
    if update is None:
        return
    audit(update, phase="err", action=action, response=_clip(error, 400))
