"""Descarga Reels de Instagram (fallback si yt-dlp falla)."""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

import httpx

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


def resolve_cookies_file(root: Path) -> Path | None:
    """Desactivado: no usar cookies/sesión de cuenta Instagram."""
    return None


def _sessionid_from_cookies(cookies: Path | None) -> str | None:
    if not cookies:
        return None
    for line in cookies.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 7 and parts[5] == "sessionid":
            return parts[6].strip()
    return None


def _cookie_header_from_file(cookies: Path | None) -> str | None:
    if not cookies:
        return None
    pairs: list[str] = []
    for line in cookies.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 7 and "instagram.com" in parts[0]:
            pairs.append(f"{parts[5]}={parts[6].strip()}")
    return "; ".join(pairs) if pairs else None


def _mobile_headers(*, cookies: Path | None = None, sessionid: str | None = None) -> dict[str, str]:
    h = {
        "User-Agent": (
            "Instagram 351.0.0.0.0 Android "
            "(29/10; 420dpi; 1080x2134; samsung; SM-G973F; beyond1; exynos9820; en_US)"
        ),
        "Accept-Language": "en-US",
        "X-IG-App-ID": "567067343352427",
    }
    header = _cookie_header_from_file(cookies)
    if header:
        h["Cookie"] = header
    elif sessionid:
        h["Cookie"] = f"sessionid={sessionid}"
    return h


def _pick_video_url(data: dict) -> str | None:
    items = data.get("items") or []
    if not items:
        return None
    item = items[0]
    if item.get("video_versions"):
        return item["video_versions"][0].get("url")
    for slide in item.get("carousel_media") or []:
        if slide.get("video_versions"):
            return slide["video_versions"][0].get("url")
    return None


def download_reel(url: str, out_dir: Path, *, cookies: Path | None) -> Path:
    raise RuntimeError(
        "Descarga con sesión de Instagram desactivada. Solo Reels públicos vía yt-dlp."
    )
    shortcode = instagram_shortcode(url)
    if not shortcode:
        raise RuntimeError("Enlace de Instagram no válido.")
    media_id = shortcode_to_media_id(shortcode)
    sessionid = None
    if not sessionid:
        raise RuntimeError(
            "Instagram necesita cookies.txt (exporta desde Chrome o envía el archivo al bot)."
        )
    api = f"https://i.instagram.com/api/v1/media/{media_id}/info/"
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        r = client.get(api, headers=_mobile_headers(cookies=cookies, sessionid=sessionid))
        if r.status_code in (401, 403):
            body = (r.text or "").lower()
            if "login_required" in body or "logged out" in body:
                raise RuntimeError(
                    "Instagram ha cerrado la sesión (login_required). "
                    "Actualiza cookies.txt con sesión iniciada."
                )
            raise RuntimeError(
                "Instagram bloqueó el acceso. Actualiza cookies.txt."
            )
        if r.status_code != 200:
            raise RuntimeError(f"Instagram API respondió {r.status_code}.")
        data = r.json()
    video_url = _pick_video_url(data)
    if not video_url:
        raise RuntimeError("Instagram no devolvió el vídeo.")
    out = out_dir / f"{shortcode}.mp4"
    since = time.time()
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
        raise RuntimeError(f"No pude bajar el Reel: {err[:200]}")
    if out.stat().st_mtime < since - 5:
        out.unlink(missing_ok=True)
        raise RuntimeError("Descarga del Reel inválida.")
    return out
