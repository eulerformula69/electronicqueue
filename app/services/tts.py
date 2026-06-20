import asyncio
import re
import subprocess

from fastapi import HTTPException

from app.config import (
    PIPER_MODEL,
    PIPER_PATH,
    TTS_LENGTH_SCALE,
    TTS_NOISE_SCALE,
    TTS_NOISE_W_SCALE,
)


tts_locks: dict[str, asyncio.Lock] = {}


def normalize_tts_input(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"\s+", " ", value)

    if not value:
        raise HTTPException(status_code=400, detail="Пустой текст для озвучки")

    if len(value) > 200:
        raise HTTPException(status_code=400, detail="Слишком длинный текст для озвучки")

    return value


def get_tts_lock(file_hash: str) -> asyncio.Lock:
    if file_hash not in tts_locks:
        tts_locks[file_hash] = asyncio.Lock()
    return tts_locks[file_hash]


def run_piper_sync(text: str, output_path: str):
    return subprocess.run(
        [
            PIPER_PATH,
            "--model", PIPER_MODEL,
            "--output_file", output_path,
            "--length-scale", TTS_LENGTH_SCALE,
            "--noise-scale", TTS_NOISE_SCALE,
            "--noise-w-scale", TTS_NOISE_W_SCALE,
        ],
        input=text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
