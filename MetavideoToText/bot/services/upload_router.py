"""Cuotas y enrutado inteligente de subidas externas."""

from __future__ import annotations

import random
import threading
import time
from collections import deque
from dataclasses import dataclass

from bot.config import (
    CATBOX_MAX_MB,
    GOFILE_MAX_UPLOADS_PER_HOUR,
    GOFILE_MIN_SIZE_MB,
    USER_MAX_EXTERNAL_PER_DAY,
    USER_MAX_EXTERNAL_PER_HOUR,
    is_admin,
)


class UserLimitError(Exception):
    pass


@dataclass(frozen=True)
class ServiceLimits:
    max_file_mb: int
    min_file_mb: int
    global_per_hour: int
    global_per_day: int
    user_per_hour: int
    user_per_day: int
    global_mb_per_hour: int


# Limites por servicio (ajustables via env en config para GoFile/global user)
SERVICE_LIMITS: dict[str, ServiceLimits] = {
    "litterbox": ServiceLimits(
        max_file_mb=CATBOX_MAX_MB,
        min_file_mb=0,
        global_per_hour=30,
        global_per_day=180,
        user_per_hour=2,
        user_per_day=8,
        global_mb_per_hour=4000,
    ),
    "catbox": ServiceLimits(
        max_file_mb=CATBOX_MAX_MB,
        min_file_mb=0,
        global_per_hour=30,
        global_per_day=180,
        user_per_hour=2,
        user_per_day=8,
        global_mb_per_hour=4000,
    ),
    "0x0": ServiceLimits(
        max_file_mb=512,
        min_file_mb=0,
        global_per_hour=15,
        global_per_day=80,
        user_per_hour=2,
        user_per_day=6,
        global_mb_per_hour=3000,
    ),
    "pixeldrain": ServiceLimits(
        max_file_mb=10240,
        min_file_mb=0,
        global_per_hour=10,
        global_per_day=50,
        user_per_hour=1,
        user_per_day=4,
        global_mb_per_hour=8000,
    ),
    "gofile": ServiceLimits(
        max_file_mb=2048,
        min_file_mb=GOFILE_MIN_SIZE_MB,
        global_per_hour=GOFILE_MAX_UPLOADS_PER_HOUR or 8,
        global_per_day=40,
        user_per_hour=2,
        user_per_day=5,
        global_mb_per_hour=12000,
    ),
}

_lock = threading.Lock()
_user_total: dict[int, deque[float]] = {}
_user_service: dict[tuple[int, str], deque[float]] = {}
_global_service: dict[str, deque[float]] = {pid: deque() for pid in SERVICE_LIMITS}
_global_service_mb: dict[str, deque[tuple[float, int]]] = {
    pid: deque() for pid in SERVICE_LIMITS
}
_rr_bias: dict[str, float] = {pid: random.random() for pid in SERVICE_LIMITS}


def _prune_times(times: deque[float], window_sec: float, *, now: float) -> None:
    while times and now - times[0] > window_sec:
        times.popleft()


def _prune_mb(events: deque[tuple[float, int]], window_sec: float, *, now: float) -> None:
    while events and now - events[0][0] > window_sec:
        events.popleft()


def _count(times: deque[float], window_sec: float, *, now: float) -> int:
    _prune_times(times, window_sec, now=now)
    return len(times)


def _sum_mb(events: deque[tuple[float, int]], window_sec: float, *, now: float) -> int:
    _prune_mb(events, window_sec, now=now)
    return sum(mb for _, mb in events)


def check_user_may_upload(user_id: int) -> None:
    if is_admin(user_id):
        return
    now = time.monotonic()
    with _lock:
        times = _user_total.setdefault(user_id, deque())
        _prune_times(times, 86400, now=now)
        hour_count = _count(times, 3600, now=now)
        if hour_count >= USER_MAX_EXTERNAL_PER_HOUR:
            raise UserLimitError(
                f"Limite personal: max {USER_MAX_EXTERNAL_PER_HOUR} videos grandes por hora."
            )
        if len(times) >= USER_MAX_EXTERNAL_PER_DAY:
            raise UserLimitError(
                f"Limite personal: max {USER_MAX_EXTERNAL_PER_DAY} videos grandes al dia."
            )


def _service_limits(provider_id: str) -> ServiceLimits | None:
    return SERVICE_LIMITS.get(provider_id)


def _quota_block_reason(
    user_id: int | None,
    provider_id: str,
    size_bytes: int,
    *,
    now: float,
    soft_min: bool,
) -> str | None:
    limits = _service_limits(provider_id)
    if limits is None:
        return "sin configuracion"

    size_mb = size_bytes / (1024 * 1024)
    if size_mb > limits.max_file_mb:
        return f"archivo > {limits.max_file_mb} MB"

    if user_id is not None and is_admin(user_id):
        return None

    if soft_min and size_mb < limits.min_file_mb:
        return f"reservado para >={limits.min_file_mb} MB"

    if user_id is not None:
        key = (user_id, provider_id)
        user_times = _user_service.setdefault(key, deque())
        _prune_times(user_times, 86400, now=now)
        if _count(user_times, 3600, now=now) >= limits.user_per_hour:
            return f"tu limite horario en {provider_id}"
        if len(user_times) >= limits.user_per_day:
            return f"tu limite diario en {provider_id}"

    g_times = _global_service.setdefault(provider_id, deque())
    _prune_times(g_times, 86400, now=now)
    if limits.global_per_hour and _count(g_times, 3600, now=now) >= limits.global_per_hour:
        return f"{provider_id} saturado (hora)"
    if limits.global_per_day and len(g_times) >= limits.global_per_day:
        return f"{provider_id} saturado (dia)"

    if limits.global_mb_per_hour:
        g_mb = _global_service_mb.setdefault(provider_id, deque())
        mb_hour = _sum_mb(g_mb, 3600, now=now)
        if mb_hour + size_mb > limits.global_mb_per_hour:
            return f"{provider_id} ancho de banda horario"

    return None


def _load_score(user_id: int | None, provider_id: str, size_bytes: int, *, now: float) -> float:
    limits = _service_limits(provider_id)
    if limits is None:
        return 999.0

    size_mb = size_bytes / (1024 * 1024)
    scores: list[float] = []

    g_times = _global_service.setdefault(provider_id, deque())
    if limits.global_per_hour:
        used = _count(g_times, 3600, now=now)
        scores.append(used / limits.global_per_hour)
    if limits.global_per_day:
        used = len(g_times)
        _prune_times(g_times, 86400, now=now)
        used = len(g_times)
        scores.append(used / limits.global_per_day)

    if limits.global_mb_per_hour:
        g_mb = _global_service_mb.setdefault(provider_id, deque())
        used_mb = _sum_mb(g_mb, 3600, now=now)
        scores.append(used_mb / limits.global_mb_per_hour)

    if user_id is not None and not is_admin(user_id):
        user_times = _user_service.setdefault((user_id, provider_id), deque())
        if limits.user_per_hour:
            scores.append(_count(user_times, 3600, now=now) / limits.user_per_hour)
        if limits.user_per_day:
            _prune_times(user_times, 86400, now=now)
            scores.append(len(user_times) / limits.user_per_day)

    load = max(scores) if scores else 0.0

    # Preferir servidores adecuados al tamano
    if provider_id in {"litterbox", "catbox"} and size_mb <= limits.max_file_mb * 0.95:
        load -= 0.35
    if provider_id == "pixeldrain" and size_mb >= GOFILE_MIN_SIZE_MB:
        load -= 0.45
    if provider_id == "gofile" and size_mb >= limits.min_file_mb:
        load -= 0.2
    if provider_id == "gofile" and size_mb < limits.min_file_mb:
        load += 0.8

    load += _rr_bias.get(provider_id, 0.0) * 0.05
    return load


def rank_providers(
    provider_ids: list[str],
    size_bytes: int,
    user_id: int | None,
) -> tuple[list[str], list[str]]:
    """Devuelve (orden de intento, motivos de exclusion)."""
    now = time.monotonic()
    primary: list[tuple[float, str]] = []
    fallback: list[tuple[float, str]] = []
    blocked: list[str] = []

    for pid in provider_ids:
        if _service_limits(pid) is None:
            continue
        reason = _quota_block_reason(user_id, pid, size_bytes, now=now, soft_min=True)
        if reason is None:
            primary.append((_load_score(user_id, pid, size_bytes, now=now), pid))
            continue
        if "reservado para" in reason:
            reason_hard = _quota_block_reason(
                user_id, pid, size_bytes, now=now, soft_min=False
            )
            if reason_hard is None:
                fallback.append(
                    (_load_score(user_id, pid, size_bytes, now=now) + 0.5, pid)
                )
                continue
            blocked.append(f"{pid}: {reason_hard}")
        else:
            blocked.append(f"{pid}: {reason}")

    primary.sort(key=lambda item: item[0])
    fallback.sort(key=lambda item: item[0])
    ordered = [pid for _, pid in primary] + [pid for _, pid in fallback]
    # Litterbox primero (mas fiable); Catbox como respaldo.
    priority = {"litterbox": 0, "catbox": 1, "pixeldrain": 2, "gofile": 3, "0x0": 4}
    ordered.sort(key=lambda pid: priority.get(pid, 50))
    return ordered, blocked


def record_upload(user_id: int | None, provider_id: str, size_bytes: int) -> None:
    now = time.monotonic()
    size_mb = int(size_bytes / (1024 * 1024)) or 1
    with _lock:
        g_times = _global_service.setdefault(provider_id, deque())
        g_times.append(now)
        g_mb = _global_service_mb.setdefault(provider_id, deque())
        g_mb.append((now, size_mb))

        if user_id is None or is_admin(user_id):
            return

        _user_total.setdefault(user_id, deque()).append(now)
        _user_service.setdefault((user_id, provider_id), deque()).append(now)

        # Rotacion: quien acaba de usarse sube un poco su bias para repartir
        for pid in _rr_bias:
            _rr_bias[pid] = random.random() * 0.3
        _rr_bias[provider_id] = 1.0


# Compat con codigo anterior
check_user_can_upload = check_user_may_upload
record_user_upload = lambda user_id: None  # sustituido por record_upload con provider
