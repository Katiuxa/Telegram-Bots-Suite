import logging
import time
from pathlib import Path

from bot.config import TEMP_CLEANUP_MINUTES, TEMP_DIR

logger = logging.getLogger(__name__)

_SKIP = {".gitkeep"}


def _is_active_work_file(path: Path) -> bool:
    """Trozos Whisper / WAV en curso: no borrar aunque superen la edad."""
    name = path.name.lower()
    return "_part_" in name or name.endswith("_16k.wav")


def cleanup_old_files(max_age_minutes: int | None = None) -> int:
    """Borra archivos en temp/ más viejos que max_age_minutes."""
    age = max_age_minutes if max_age_minutes is not None else TEMP_CLEANUP_MINUTES
    cutoff = time.time() - age * 60
    removed = 0
    if not TEMP_DIR.exists():
        return 0
    for path in TEMP_DIR.iterdir():
        if path.name in _SKIP or _is_active_work_file(path):
            continue
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError as e:
            logger.debug("No borré %s: %s", path, e)
    if removed:
        logger.info("Limpieza temp: %s archivos borrados (>%s min)", removed, age)
    return removed
