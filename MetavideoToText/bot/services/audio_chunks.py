import subprocess
from pathlib import Path

from bot.config import AUDIO_CHUNK_SEC, FFMPEG_THREADS, GROQ_MAX_WAV_MB, TEMP_DIR


def wav_needs_chunking(wav_path: Path) -> bool:
    limit = GROQ_MAX_WAV_MB * 1024 * 1024
    return wav_path.stat().st_size > limit


def split_wav_for_transcription(wav_path: Path) -> list[tuple[Path, float]]:
    """
    Divide WAV largos en trozos (~10 min) para Groq y motores con límite de tamaño.
    Devuelve [(archivo, offset_segundos), ...]
    """
    if not wav_needs_chunking(wav_path):
        return [(wav_path, 0.0)]

    pattern = str(TEMP_DIR / f"{wav_path.stem}_part_%03d.wav")
    cmd = [
        "ffmpeg",
        "-y",
        "-threads",
        str(max(1, FFMPEG_THREADS)),
        "-i",
        str(wav_path),
        "-f",
        "segment",
        "-segment_time",
        str(AUDIO_CHUNK_SEC),
        "-reset_timestamps",
        "1",
        "-acodec",
        "pcm_s16le",
        pattern,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return [(wav_path, 0.0)]

    parts = sorted(TEMP_DIR.glob(f"{wav_path.stem}_part_*.wav"))
    if not parts:
        return [(wav_path, 0.0)]

    out: list[tuple[Path, float]] = []
    for i, p in enumerate(parts):
        out.append((p, float(i * AUDIO_CHUNK_SEC)))
    return out


def cleanup_chunks(chunks: list[tuple[Path, float]], original: Path) -> None:
    for p, _ in chunks:
        if p != original:
            try:
                p.unlink()
            except OSError:
                pass
