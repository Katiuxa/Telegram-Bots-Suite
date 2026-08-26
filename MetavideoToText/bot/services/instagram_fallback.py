"""Descarga Reels de Instagram (fallback si yt-dlp falla)."""
from __future__ import annotations

import logging
import re
import subprocess
import time
from pathlib import Path

import httpx

from bot.config import ROOT, TEMP_DIR

logger = logging.getLogger(__name__)

_SHORTCODE_RE = re.compile(r"/(?:reel|reels|p)/([A-Za-z0-9_-]+)")
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def instagram_shortcode(url: str) -> str | None:
    m = _SHORTCODE_RE.search(url)
    return m.group(1) if m else None


def shortcode_to_media_id(shortcode: str) -> str:
    n = 0
    for ch in shortcode:
        n = n * 64 + _ALPHABET.index(ch)
    return str(n)


def _cookies_path() -> Path | None:
    p = ROOT / "cookies.txt"
    return p if p.is_file() and p.stat().st_size > 50 else None


def _sessionid_from_cookies() -> str | None:
    path = _cookies_path()
    if not path:
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 7 and parts[5] == "sessionid":
            return parts[6].strip()
    return None


def _mobile_headers(*, sessionid: str | None = None) -> dict[str, str]:
    h = {
        "User-Agent": (
            "Instagram 351.0.0.0.0 Android "
            "(29/10; 420dpi; 1080x2134; samsung; SM-G973F; beyond1; exynos9820; en_US)"
        ),
        "Accept-Language": "en-US",
        "X-IG-App-ID": "567067343352427",
    }
    if sessionid:
        h["Cookie"] = f"sessionid={sessionid}"
    return h


def _pick_video_url(data: dict) -> str | None:
    items = data.get("items") or []
    if not items:
        return None
    item = items[0]
    if item.get("video_versions"):
        return item["video_versions"][0].get("url")
    carousel = item.get("carousel_media") or []
    for slide in carousel:
        if slide.get("video_versions"):
            return slide["video_versions"][0].get("url")
    return None


def fetch_reel_video_url(url: str) -> tuple[str, str]:
    """Devuelve (video_url, title). Lanza RuntimeError si no puede."""
    # Desactivado: no usar sessionid/cookies de cuenta (riesgo de flag de automatización).
    raise RuntimeError(
        "Descarga con sesión de Instagram desactivada. Solo Reels públicos vía yt-dlp."
    )
    shortcode = instagram_shortcode(url)
    if not shortcode:
        raise RuntimeError("Enlace de Instagram no válido.")
    media_id = shortcode_to_media_id(shortcode)
    sessionid = None
    api = f"https://i.instagram.com/api/v1/media/{media_id}/info/"
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        r = client.get(api, headers=_mobile_headers(sessionid=sessionid))
        if r.status_code == 404:
            raise RuntimeError("Reel no encontrado o eliminado.")
        if r.status_code in (401, 403):
            raise RuntimeError(
                "Instagram bloqueó el acceso. Falta cookies.txt con sesión iniciada."
            )
        if r.status_code != 200:
            raise RuntimeError(f"Instagram API respondió {r.status_code}.")
        data = r.json()
    video_url = _pick_video_url(data)
    if not video_url:
        raise RuntimeError(
            "Instagram no devolvió el vídeo. Prueba con cookies.txt (sesión iniciada)."
        )
    title = ""
    items = data.get("items") or []
    if items:
        cap = items[0].get("caption") or {}
        title = (cap.get("text") or "").strip()[:200]
    return video_url, title or shortcode


def download_reel_to_temp(url: str, *, since: float | None = None) -> Path:
    """Descarga el reel a temp/ y devuelve la ruta."""
    video_url, _ = fetch_reel_video_url(url)
    shortcode = instagram_shortcode(url) or "ig"
    out = TEMP_DIR / f"{shortcode}.mp4"
    since = since or time.time()
    proc = subprocess.run(
        [
            "curl",
            "-L",
            "-f",
            "--max-time",
            "300",
            "-A",
            "Mozilla/5.0",
            "-o",
            str(out),
            video_url,
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not out.is_file():
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"No pude bajar el vídeo del Reel: {err[:200]}")
    if out.stat().st_mtime < since - 5:
        out.unlink(missing_ok=True)
        raise RuntimeError("Archivo de descarga inválido.")
    return out
