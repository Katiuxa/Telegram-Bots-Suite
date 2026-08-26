"""Subida externa con varios servidores, rotacion y enfriamiento si fallan."""



from __future__ import annotations



import logging
import random
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path



import httpx
import requests



from bot.config import (
    CATBOX_MAX_BYTES,
    CATBOX_MAX_MB,
    EXTERNAL_LINK_TTL,
    GOFILE_MIN_SIZE_MB,
    GOFILE_TTL_HOURS,
    MAX_EXTERNAL_BYTES,
    MAX_EXTERNAL_FILE_MB,
    MAX_TELEGRAM_BYTES,
    UPLOAD_PROVIDER_COOLDOWN_SEC,
    UPLOAD_PROVIDERS,
    ZEROX0_TTL_HOURS,
)



from bot.services.upload_router import check_user_may_upload, _quota_block_reason, record_upload



logger = logging.getLogger(__name__)



LITTERBOX_API = "https://litterbox.catbox.moe/resources/internals/api.php"

CATBOX_API = "https://catbox.moe/user/api.php"

PIXELDRAIN_API = "https://pixeldrain.com/api/file"

ZEROX0_API = "https://0x0.st"

UPLOAD_TIMEOUT = httpx.Timeout(900.0, connect=60.0)

HTTP_HEADERS = {"User-Agent": "MetavideoToText_bot/1.0"}



LITTERBOX_MAX_MB = CATBOX_MAX_MB

ZEROX0_MAX_MB = 512

GOFILE_MAX_MB = 2048

PIXELDRAIN_MAX_MB = 10240

CATBOX_PERMANENT_TTL_HOURS = 168



_lock = threading.Lock()
_upload_ctx = threading.local()







class UploadError(Exception):

    pass





@dataclass(frozen=True)
class ExternalLink:
    url: str
    provider: str
    expires_minutes: int
    max_mb: int



    @property

    def expiry_text(self) -> str:

        m = self.expires_minutes

        if m < 60:

            return f"{m} minutos"

        if m % 60 == 0:

            h = m // 60

            return f"{h} hora" if h == 1 else f"{h} horas"

        return f"{m // 60} h {m % 60} min"





@dataclass

class _ProviderState:

    failures: int = 0

    cooldown_until: float = 0.0

    disabled: bool = False





@dataclass(frozen=True)

class UploadProvider:

    id: str

    label: str

    max_bytes: int

    max_mb: int

    expires_minutes: int

    upload: Callable[[Path], ExternalLink]

    reserve_for_large: bool = False





def _check_response_url(text: str, provider: str) -> str:

    url = (text or "").strip()

    if url.startswith("http://") or url.startswith("https://"):

        return url

    raise UploadError(f"{provider}: {url[:300] or 'respuesta vacia'}")





def _temp_ttl_minutes() -> int:

    return {"1h": 60, "24h": 24 * 60, "72h": 72 * 60}.get(EXTERNAL_LINK_TTL, 60)


# Timeouts de subida (segundos): fallar rapido y rotar al siguiente proveedor
UPLOAD_TIMEOUT_CATBOX_MIN = 25
UPLOAD_TIMEOUT_CATBOX_MAX = 55
UPLOAD_TIMEOUT_CATBOX_PER_MB = 0.35
UPLOAD_TIMEOUT_GOFILE_MIN = 60
UPLOAD_TIMEOUT_GOFILE_MAX = 240
UPLOAD_TIMEOUT_GOFILE_PER_MB = 1.2
UPLOAD_TIMEOUT_PIXELDRAIN_MAX = 900


def _upload_timeout_sec(
    path: Path,
    *,
    min_sec: float = UPLOAD_TIMEOUT_CATBOX_MIN,
    max_sec: float = UPLOAD_TIMEOUT_CATBOX_MAX,
    sec_per_mb: float = UPLOAD_TIMEOUT_CATBOX_PER_MB,
) -> float:
    size_mb = path.stat().st_size / (1024 * 1024)
    return max(min_sec, min(max_sec, size_mb * sec_per_mb))


def _gofile_upload_timeout_sec(path: Path) -> float:
    size_mb = path.stat().st_size / (1024 * 1024)
    return max(
        UPLOAD_TIMEOUT_GOFILE_MIN,
        min(UPLOAD_TIMEOUT_GOFILE_MAX, size_mb * UPLOAD_TIMEOUT_GOFILE_PER_MB),
    )


def _pixeldrain_upload_timeout_sec(path: Path) -> float:
    size_mb = path.stat().st_size / (1024 * 1024)
    return max(120, min(UPLOAD_TIMEOUT_PIXELDRAIN_MAX, size_mb * 2.0))


def _format_elapsed(seconds: int) -> str:
    mins, secs = divmod(max(0, seconds), 60)
    if mins:
        return f"{mins}m {secs}s"
    return f"{secs}s"


def _report_upload_status(provider_label: str, size_mb: int, *, elapsed_sec: int = 0) -> None:
    """Progreso honesto: tiempo transcurrido, sin % falso (el buffer local engaña)."""
    on_progress = getattr(_upload_ctx, "on_progress", None)
    if not on_progress:
        return
    if elapsed_sec <= 0:
        text = f"Subiendo a {provider_label} ({size_mb} MB)…"
    else:
        text = f"Subiendo a {provider_label} ({size_mb} MB)… {_format_elapsed(elapsed_sec)}"
    on_progress(92, text)


@contextmanager
def _upload_status_heartbeat(provider_label: str, size_mb: int) -> Iterator[None]:
    stop = threading.Event()
    start = time.monotonic()
    _report_upload_status(provider_label, size_mb)

    def _tick() -> None:
        while not stop.wait(15):
            elapsed = int(time.monotonic() - start)
            _report_upload_status(provider_label, size_mb, elapsed_sec=elapsed)

    thread = threading.Thread(target=_tick, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)


def _post_multipart(
    url: str,
    *,
    data: dict,
    path: Path,
    provider_label: str = "",
    retries: int = 1,
) -> requests.Response:
    """Subida con reintento puntual (SSL) y mensaje de tiempo real."""
    timeout = _upload_timeout_sec(path)
    last_err: Exception | None = None
    label = provider_label or "servidor"
    size_mb = path.stat().st_size // (1024 * 1024)

    for attempt in range(1, retries + 1):
        try:
            logger.info(
                "%s intento %s/%s (timeout %.0fs)...",
                label,
                attempt,
                retries,
                timeout,
            )
            with _upload_status_heartbeat(label, size_mb):
                with path.open("rb") as fh:
                    resp = requests.post(
                        url,
                        data=data,
                        files={"fileToUpload": (path.name, fh, "application/octet-stream")},
                        headers=HTTP_HEADERS,
                        timeout=timeout,
                    )
            return resp
        except (
            requests.exceptions.SSLError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError,
        ) as e:
            last_err = e
            logger.warning("%s intento %s/%s fallo: %s", label, attempt, retries, e)
            if attempt < retries:
                time.sleep(min(5 * attempt, 10))
    raise UploadError(str(last_err or "subida fallida"))





def _upload_litterbox(path: Path) -> ExternalLink:

    size_mb = path.stat().st_size // (1024 * 1024)
    logger.info("Litterbox subiendo %s MB...", size_mb)
    resp = _post_multipart(
        LITTERBOX_API,
        data={"reqtype": "fileupload", "time": EXTERNAL_LINK_TTL},
        path=path,
        provider_label="Litterbox",
    )

    if resp.status_code >= 400:

        raise UploadError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    if "uploads disabled" in resp.text.lower():

        raise UploadError("subidas deshabilitadas en el servidor")

    link = _check_response_url(resp.text, "Litterbox")

    return ExternalLink(

        url=link,

        provider="Litterbox",

        expires_minutes=_temp_ttl_minutes(),

        max_mb=LITTERBOX_MAX_MB,

    )





def _upload_catbox(path: Path) -> ExternalLink:

    size_mb = path.stat().st_size // (1024 * 1024)
    logger.info("Catbox subiendo %s MB...", size_mb)
    resp = _post_multipart(
        CATBOX_API,
        data={"reqtype": "fileupload"},
        path=path,
        provider_label="Catbox",
    )

    if resp.status_code >= 400:

        raise UploadError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    link = _check_response_url(resp.text, "Catbox")

    return ExternalLink(

        url=link,

        provider="Catbox",

        expires_minutes=CATBOX_PERMANENT_TTL_HOURS * 60,

        max_mb=CATBOX_MAX_MB,

    )





def _upload_0x0(path: Path) -> ExternalLink:

    with path.open("rb") as fh:

        files = {"file": (path.name, fh, "application/octet-stream")}

        with httpx.Client(timeout=UPLOAD_TIMEOUT, headers=HTTP_HEADERS) as client:

            resp = client.post(ZEROX0_API, files=files)

    if resp.status_code >= 400:

        body = resp.text[:200]

        if resp.status_code == 503 or "uploads disabled" in body.lower():

            _disable_provider("0x0", "subidas deshabilitadas en 0x0.st")

        raise UploadError(f"HTTP {resp.status_code}: {body}")

    link = _check_response_url(resp.text, "0x0.st")

    return ExternalLink(

        url=link,

        provider="0x0.st",

        expires_minutes=ZEROX0_TTL_HOURS * 60,

        max_mb=ZEROX0_MAX_MB,

    )





def _upload_pixeldrain(path: Path) -> ExternalLink:
    size_mb = path.stat().st_size // (1024 * 1024)
    upload_timeout = int(_pixeldrain_upload_timeout_sec(path))
    logger.info("Pixeldrain subiendo %s MB...", size_mb)
    with _upload_status_heartbeat("Pixeldrain", size_mb):
        with path.open("rb") as fh:
            resp = requests.post(
                PIXELDRAIN_API,
                data={"anonymous": "true"},
                files={"file": (path.name, fh, "application/octet-stream")},
                headers=HTTP_HEADERS,
                timeout=upload_timeout,
            )

    if resp.status_code >= 400:

        raise UploadError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    try:

        body = resp.json()

    except Exception as e:

        raise UploadError(f"respuesta invalida ({resp.text[:120]})") from e

    file_id = body.get("id") or ""

    if not file_id:

        raise UploadError("no devolvio id de archivo")

    link = f"https://pixeldrain.com/api/file/{file_id}"

    return ExternalLink(

        url=link,

        provider="Pixeldrain",

        expires_minutes=60 * 24 * 60,

        max_mb=PIXELDRAIN_MAX_MB,

    )




GOFILE_WEBSITE_TOKEN = "4fd6sg89d7s6"
GOFILE_UPLOAD_URL = "https://upload.gofile.io/uploadfile"
GOFILE_SERVERS_FALLBACK = (
    "store-eu-par-4",
    "store-na-phx-5",
    "store4",
    "store3",
    "store10",
)
_gofile_guest_token: str | None = None
_gofile_token_lock = threading.Lock()


def _gofile_auth_headers() -> dict[str, str]:
    global _gofile_guest_token
    headers = {
        **HTTP_HEADERS,
        "X-Website-Token": GOFILE_WEBSITE_TOKEN,
    }
    with _gofile_token_lock:
        if not _gofile_guest_token:
            resp = requests.post(
                "https://api.gofile.io/accounts",
                headers=headers,
                timeout=60,
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("status") != "ok":
                raise UploadError(f"GoFile cuenta invitado: {body.get('status', body)}")
            _gofile_guest_token = (body.get("data") or {}).get("token") or ""
            if not _gofile_guest_token:
                raise UploadError("GoFile no devolvio token de invitado")
        headers["Authorization"] = f"Bearer {_gofile_guest_token}"
    return headers


def _gofile_upload_urls() -> list[str]:
    urls = [GOFILE_UPLOAD_URL]
    try:
        resp = requests.get(
            "https://api.gofile.io/servers",
            headers=_gofile_auth_headers(),
            timeout=60,
        )
        if resp.ok:
            data = resp.json().get("data") or {}
            raw = data.get("servers") or data.get("serversAllZone") or []
            for item in raw:
                name = item.get("name", item) if isinstance(item, dict) else item
                if name:
                    urls.append(f"https://{name}.gofile.io/uploadFile")
    except Exception as e:
        logger.warning("GoFile API servers: %s", e)
    for server in GOFILE_SERVERS_FALLBACK:
        url = f"https://{server}.gofile.io/uploadFile"
        if url not in urls:
            urls.append(url)
    return urls


def _gofile_download_url(data: dict) -> str:
    """Pagina gofile.io/d/ (la que funciona). No enlaces store-* en el mensaje."""
    guest = (data.get("guestToken") or "").strip()
    code = data.get("parentFolderCode") or data.get("code") or ""
    page = (data.get("downloadPage") or "").strip()
    if not page and code:
        page = f"https://gofile.io/d/{code}"
    if page and guest and "token=" not in page:
        page = f"{page}{'&' if '?' in page else '?'}token={guest}"
    if page.startswith("http"):
        return page
    raise UploadError("GoFile no devolvio enlace de descarga")


def _upload_gofile(path: Path) -> ExternalLink:
    size_bytes = path.stat().st_size
    if size_bytes > GOFILE_MAX_MB * 1024 * 1024:
        raise UploadError(
            f"Archivo demasiado grande para GoFile ({size_bytes // (1024 * 1024)} MB, "
            f"max {GOFILE_MAX_MB} MB)."
        )
    size_mb = size_bytes // (1024 * 1024)
    upload_timeout = int(_gofile_upload_timeout_sec(path))
    errors: list[str] = []
    urls = _gofile_upload_urls()
    random.shuffle(urls[1:6])
    for upload_url in urls[:6]:
        label = upload_url.split("//", 1)[-1].split("/", 1)[0]
        try:
            logger.info(
                "GoFile subiendo a %s (%s MB, timeout %ss)...",
                label,
                size_mb,
                upload_timeout,
            )
            headers = _gofile_auth_headers()
            with _upload_status_heartbeat("GoFile", size_mb):
                with path.open("rb") as fh:
                    resp = requests.post(
                        upload_url,
                        files={"file": (path.name, fh, "application/octet-stream")},
                        headers=headers,
                        timeout=upload_timeout,
                    )
            if resp.status_code >= 400:
                raise UploadError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            body = resp.json()
            if body.get("status") != "ok":
                raise UploadError(str(body.get("status", body)))
            data = body.get("data") or {}
            url = _gofile_download_url(data)
            logger.info("OK GoFile via %s: %s", label, url)
            on_progress = getattr(_upload_ctx, "on_progress", None)
            if on_progress:
                on_progress(99, "Enlace listo, enviando…")
            return ExternalLink(
                url=url,
                provider="GoFile",
                expires_minutes=GOFILE_TTL_HOURS * 60,
                max_mb=GOFILE_MAX_MB,
            )
        except Exception as e:
            errors.append(f"{label}: {e}")
            logger.warning("Fallo GoFile %s", errors[-1])
    raise UploadError("GoFile agotado: " + "; ".join(errors[:4]))




_ALL_PROVIDERS: dict[str, UploadProvider] = {

    "litterbox": UploadProvider(

        id="litterbox",

        label="Litterbox",

        max_bytes=CATBOX_MAX_BYTES,

        max_mb=LITTERBOX_MAX_MB,

        expires_minutes=_temp_ttl_minutes(),

        upload=_upload_litterbox,

    ),

    "catbox": UploadProvider(

        id="catbox",

        label="Catbox",

        max_bytes=CATBOX_MAX_BYTES,

        max_mb=CATBOX_MAX_MB,

        expires_minutes=CATBOX_PERMANENT_TTL_HOURS * 60,

        upload=_upload_catbox,

    ),

    "0x0": UploadProvider(

        id="0x0",

        label="0x0.st",

        max_bytes=ZEROX0_MAX_MB * 1024 * 1024,

        max_mb=ZEROX0_MAX_MB,

        expires_minutes=ZEROX0_TTL_HOURS * 60,

        upload=_upload_0x0,

    ),

    "pixeldrain": UploadProvider(

        id="pixeldrain",

        label="Pixeldrain",

        max_bytes=PIXELDRAIN_MAX_MB * 1024 * 1024,

        max_mb=PIXELDRAIN_MAX_MB,

        expires_minutes=60 * 24 * 60,

        upload=_upload_pixeldrain,

    ),

    "gofile": UploadProvider(
        id="gofile",
        label="GoFile",
        max_bytes=GOFILE_MAX_MB * 1024 * 1024,
        max_mb=GOFILE_MAX_MB,
        expires_minutes=GOFILE_TTL_HOURS * 60,
        upload=_upload_gofile,
        reserve_for_large=True,
    ),

}



_provider_state: dict[str, _ProviderState] = {pid: _ProviderState() for pid in _ALL_PROVIDERS}



def _disable_provider(provider_id: str, reason: str) -> None:

    st = _provider_state[provider_id]

    st.disabled = True

    st.cooldown_until = time.monotonic() + 24 * 3600

    logger.warning("Proveedor %s deshabilitado: %s", provider_id, reason)




def _enabled_providers() -> list[UploadProvider]:

    out: list[UploadProvider] = []

    for pid in UPLOAD_PROVIDERS:

        p = _ALL_PROVIDERS.get(pid)

        if p is not None:

            out.append(p)

    if not out:

        out = [
            _ALL_PROVIDERS["litterbox"],
            _ALL_PROVIDERS["catbox"],
            _ALL_PROVIDERS["gofile"],
        ]

    return out





def _provider_available(provider: UploadProvider, *, now: float) -> bool:

    st = _provider_state[provider.id]

    if st.disabled:

        return False

    if st.cooldown_until > now:

        return False

    return True




def _mark_success(provider_id: str) -> None:

    st = _provider_state[provider_id]

    st.failures = 0

    st.cooldown_until = 0.0





def _mark_failure(provider_id: str) -> None:

    st = _provider_state[provider_id]

    st.failures += 1

    if st.failures >= 2:

        st.cooldown_until = time.monotonic() + UPLOAD_PROVIDER_COOLDOWN_SEC

        logger.warning(

            "Proveedor %s en pausa %ss tras %s fallos",

            provider_id,

            UPLOAD_PROVIDER_COOLDOWN_SEC,

            st.failures,

        )





def _try_providers(path: Path, pool: list[UploadProvider]) -> tuple[ExternalLink | None, list[str]]:
    """Un intento por proveedor; timeout corto y pasa al siguiente."""
    size = path.stat().st_size
    size_mb = size // (1024 * 1024)
    errors: list[str] = []

    for idx, provider in enumerate(pool):
        if idx > 0:
            on_progress = getattr(_upload_ctx, "on_progress", None)
            if on_progress:
                prev = pool[idx - 1].label
                on_progress(
                    91,
                    f"{prev} no respondio a tiempo. Probando {provider.label} ({size_mb} MB)…",
                )
        try:
            logger.info(
                "Subiendo %s MB a %s (intento %s/%s)",
                size_mb,
                provider.label,
                idx + 1,
                len(pool),
            )
            link = provider.upload(path)
            _mark_success(provider.id)
            logger.info("OK %s: %s", provider.label, link.url)
            return link, errors
        except Exception as e:
            _mark_failure(provider.id)
            msg = f"{provider.label}: {e}"
            errors.append(msg)
            logger.warning("Fallo %s", msg)

    return None, errors





def _build_upload_pool(size: int, user_id: int | None) -> tuple[list[UploadProvider], list[str]]:
    """<=200 MB: Litterbox/Catbox. >200 MB: GoFile. Sin mezclar mal los servicios."""
    now = time.monotonic()
    size_mb = size / (1024 * 1024)
    blocked: list[str] = []
    by_id = {p.id: p for p in _enabled_providers()}

    if size_mb <= CATBOX_MAX_MB:
        order = ("litterbox", "catbox", "gofile")
    else:
        order = ("gofile", "pixeldrain")

    pool: list[UploadProvider] = []
    for pid in order:
        p = by_id.get(pid)
        if p is None or size > p.max_bytes or not _provider_available(p, now=now):
            continue
        soft_min = pid == "gofile" and size_mb < GOFILE_MIN_SIZE_MB
        reason = _quota_block_reason(user_id, pid, size, now=now, soft_min=soft_min)
        if reason:
            if soft_min and "reservado" in reason and pid == "gofile":
                reason = _quota_block_reason(user_id, pid, size, now=now, soft_min=False)
            if reason:
                blocked.append(f"{pid}: {reason}")
                continue
        pool.append(p)

    return pool, blocked


def current_max_deliverable_bytes(user_id: int | None) -> int:
    """Max MB de un solo archivo que algun alojamiento libre acepta ahora."""
    now = time.monotonic()
    best = MAX_TELEGRAM_BYTES
    candidates_mb = (
        CATBOX_MAX_MB,
        GOFILE_MIN_SIZE_MB,
        GOFILE_MAX_MB,
        PIXELDRAIN_MAX_MB,
        ZEROX0_MAX_MB,
        MAX_EXTERNAL_FILE_MB,
    )
    seen: set[int] = set()
    for mb in sorted(candidates_mb, reverse=True):
        if mb in seen or mb <= 0:
            continue
        seen.add(mb)
        size = min(mb * 1024 * 1024, MAX_EXTERNAL_BYTES)
        if size <= MAX_TELEGRAM_BYTES:
            pool, _ = _build_upload_pool(size, user_id)
            if pool:
                best = max(best, size)
            continue
        pool, _ = _build_upload_pool(size, user_id)
        if pool:
            return size
    for p in _enabled_providers():
        if not _provider_available(p, now=now):
            continue
        cap = min(p.max_bytes, MAX_EXTERNAL_BYTES)
        pool, _ = _build_upload_pool(cap, user_id)
        if pool:
            best = max(best, cap)
    return best


def preflight_delivery_ok(
    size_bytes: int,
    user_id: int | None,
) -> tuple[bool, str | None]:
    """True si el tamano cabe en Telegram o en algun alojamiento disponible ahora."""
    if size_bytes <= 0:
        return True, None
    if size_bytes > MAX_EXTERNAL_BYTES:
        max_mb = current_max_deliverable_bytes(user_id) // (1024 * 1024)
        return False, (
            f"Supera el tope absoluto ({MAX_EXTERNAL_FILE_MB} MB). "
            f"Ahora puedo entregar hasta ~{max_mb} MB por archivo."
        )
    if size_bytes <= MAX_TELEGRAM_BYTES:
        return True, None
    pool, blocked = _build_upload_pool(size_bytes, user_id)
    if pool:
        return True, None
    max_mb = current_max_deliverable_bytes(user_id) // (1024 * 1024)
    hint = blocked[0] if blocked else "todos los alojamientos ocupados o saturados"
    return False, (
        f"Ningun alojamiento libre acepta ese tamano ahora "
        f"(disponible hasta ~{max_mb} MB). {hint}"
    )


def upload_video_external(
    path: Path,
    user_id: int | None = None,
    *,
    on_progress: Callable[[int, str], None] | None = None,
) -> ExternalLink:

    """Enrutado inteligente: cuotas por usuario y por servicio."""

    _upload_ctx.on_progress = on_progress
    try:
        return _upload_video_external_impl(path, user_id)
    finally:
        _upload_ctx.on_progress = None


def _upload_video_external_impl(path: Path, user_id: int | None) -> ExternalLink:

    if user_id is not None:

        check_user_may_upload(user_id)

    size = path.stat().st_size

    if size > MAX_EXTERNAL_BYTES:

        raise UploadError(

            f"Archivo demasiado grande ({size // (1024 * 1024)} MB). "

            f"Limite: {MAX_EXTERNAL_FILE_MB} MB."

        )

    pool, blocked = _build_upload_pool(size, user_id)

    if not pool:

        hint = "\n".join(blocked) if blocked else "sin servidores disponibles"

        raise UploadError(

            f"No hay servidor libre ahora ({size // (1024 * 1024)} MB).\n{hint}"

        )

    link, errors = _try_providers(path, pool)

    if link is not None:

        pid = next(

            (p.id for p in _ALL_PROVIDERS.values() if p.label == link.provider),

            link.provider.lower(),

        )

        record_upload(user_id, pid, size)

        return link

    detail = "\n".join(errors + blocked) if (errors or blocked) else "sin proveedores"

    raise UploadError(

        f"No pude subir el archivo ({size // (1024 * 1024)} MB).\n{detail}"

    )


