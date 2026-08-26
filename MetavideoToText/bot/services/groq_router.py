"""Cascada inteligente de modelos Groq (cuotas por modelo, sin esperas largas)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Calidad de traducción (mayor = mejor). Cuotas free son independientes por modelo.
# Orden base: calidad alta primero; si uno se satura, saltar al siguiente al instante.
_MODEL_CATALOG: tuple[tuple[str, int, int], ...] = (
    # name, quality (0-100), daily_headroom_hint
    # Groq retira llama-3.1-8b-instant y llama-3.3-70b-versatile el 2026-08-16.
    ("openai/gpt-oss-120b", 96, 40),
    ("meta-llama/llama-4-scout-17b-16e-instruct", 90, 55),
    ("qwen/qwen3-32b", 86, 50),
    ("openai/gpt-oss-20b", 80, 80),
)

_MAX_SWITCH_SLEEP = 0.35
_MAX_LAST_RETRY_SLEEP = 1.2
_COOLDOWN_PAD = 0.15


@dataclass
class _Slot:
    name: str
    quality: int
    headroom: int
    cool_until: float = 0.0
    unavailable: bool = False
    ok_count: int = 0
    fail_429: int = 0


@dataclass
class GroqRouter:
    """Elige el mejor modelo disponible según calidad + estado de cuota reciente."""

    _slots: dict[str, _Slot] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _last_ok: str | None = None

    def ensure(self, models: list[str]) -> None:
        with self._lock:
            catalog = {n: (q, h) for n, q, h in _MODEL_CATALOG}
            for name in models:
                if name in self._slots:
                    continue
                q, h = catalog.get(name, (70, 40))
                self._slots[name] = _Slot(name=name, quality=q, headroom=h)

    def mark_rate_limited(self, model: str, reset_sec: float) -> None:
        """Marca el modelo en enfriamiento; el siguiente pick lo saltará."""
        wait = max(0.5, min(float(reset_sec or 1.0), 90.0))
        self.ensure([model])
        with self._lock:
            slot = self._slots.get(model)
            if not slot:
                return
            slot.fail_429 += 1
            slot.cool_until = time.monotonic() + wait + _COOLDOWN_PAD
            logger.info(
                "Groq %s en cooldown %.1fs (429 #%s)",
                model.split("/")[-1],
                wait,
                slot.fail_429,
            )

    def mark_ok(self, model: str) -> None:
        self.ensure([model])
        with self._lock:
            slot = self._slots.get(model)
            if not slot:
                return
            slot.ok_count += 1
            slot.cool_until = 0.0
            slot.unavailable = False
            self._last_ok = model

    def mark_unavailable(self, model: str) -> None:
        self.ensure([model])
        with self._lock:
            slot = self._slots.get(model)
            if slot:
                slot.unavailable = True
                logger.info("Groq modelo no disponible en cuenta: %s", model)

    def ordered_models(self, candidates: list[str]) -> list[str]:
        """Mejor primero entre los que no están en cooldown / unavailable."""
        self.ensure(candidates)
        now = time.monotonic()
        with self._lock:
            scored: list[tuple[float, str]] = []
            cooling: list[tuple[float, str]] = []
            for name in candidates:
                slot = self._slots.get(name)
                if not slot or slot.unavailable:
                    continue
                # Preferir el último que funcionó (afinidad de sesión) si está fresco
                sticky = 8.0 if name == self._last_ok else 0.0
                # Penalizar 429 recientes
                penalty = min(25.0, slot.fail_429 * 4.0)
                score = slot.quality + slot.headroom * 0.15 + sticky - penalty
                if slot.cool_until > now:
                    cooling.append((slot.cool_until, name))
                    continue
                scored.append((score, name))
            scored.sort(key=lambda x: (-x[0], x[1]))
            ready = [n for _, n in scored]
            if ready:
                return ready
            # Todos en cooldown: si el más cercano tarda >1.5s, mejor MT ahora.
            cooling.sort(key=lambda x: x[0])
            if not cooling:
                return []
            soonest = cooling[0][0] - now
            if soonest > 1.5:
                logger.info(
                    "Todos los modelos Groq en cooldown (mín %.1fs) → ceder a MT",
                    soonest,
                )
                return []
            return [n for _, n in cooling]

    def sleep_before_retry(
        self,
        *,
        model: str,
        reset_sec: float,
        has_alternative: bool,
    ) -> float:
        """Espera mínima. Si hay otro modelo/clave, casi no espera."""
        if has_alternative:
            wait = min(_MAX_SWITCH_SLEEP, max(0.05, min(reset_sec, _MAX_SWITCH_SLEEP)))
        else:
            wait = min(_MAX_LAST_RETRY_SLEEP, max(0.2, min(reset_sec, _MAX_LAST_RETRY_SLEEP)))
        if wait > 0:
            time.sleep(wait)
        return wait


_ROUTER = GroqRouter()


def get_router() -> GroqRouter:
    return _ROUTER


def default_translate_cascade() -> list[str]:
    """Cascada free-tier: calidad → headroom → instant."""
    return [name for name, _, _ in _MODEL_CATALOG]


def parse_retry_after_seconds(response, attempt: int = 0) -> float:
    raw = (getattr(response, "headers", {}) or {}).get("retry-after") or ""
    raw = str(raw).strip()
    if raw:
        try:
            return max(0.2, float(raw))
        except ValueError:
            pass
    headers = getattr(response, "headers", {}) or {}
    reset = (
        headers.get("x-ratelimit-reset-tokens")
        or headers.get("x-ratelimit-reset-requests")
        or ""
    ).strip()
    if reset:
        try:
            val = float(reset)
            if val > 1e9:
                val = max(0.0, val - time.time())
            return max(0.2, val)
        except ValueError:
            pass
    return min(2.0, 0.4 * (2**attempt))
