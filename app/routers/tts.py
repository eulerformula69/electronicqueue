import asyncio
import hashlib
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import (
    PIPER_MODEL,
    TTS_CACHE_DIR,
    TTS_LENGTH_SCALE,
    TTS_NOISE_SCALE,
    TTS_NOISE_W_SCALE,
    TTS_OUTPUT_SAMPLE_RATE,
)
from app.services.tts import (
    get_tts_lock,
    normalize_tts_input,
    resample_wav_to_sample_rate,
    run_piper_sync,
)


router = APIRouter()


@router.get("/tts/audio", tags=["TTS"])
async def get_tts_audio(text: str = Query(..., min_length=1, max_length=200)):
    text = normalize_tts_input(text)

    os.makedirs(TTS_CACHE_DIR, exist_ok=True)

    cache_key = "|".join([
        text,
        str(PIPER_MODEL),
        TTS_LENGTH_SCALE,
        TTS_NOISE_SCALE,
        TTS_NOISE_W_SCALE,
        str(TTS_OUTPUT_SAMPLE_RATE),
    ])
    file_hash = hashlib.md5(cache_key.encode("utf-8")).hexdigest()
    output_path = os.path.join(TTS_CACHE_DIR, f"{file_hash}.wav")
    raw_output_path = os.path.join(TTS_CACHE_DIR, f"{file_hash}.raw.wav")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return FileResponse(output_path, media_type="audio/wav", filename="tts.wav")

    async with get_tts_lock(file_hash):
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return FileResponse(output_path, media_type="audio/wav", filename="tts.wav")

        if os.path.exists(raw_output_path):
            os.remove(raw_output_path)

        try:
            result = await asyncio.to_thread(run_piper_sync, text, raw_output_path)
        except OSError as exc:
            if os.path.exists(raw_output_path):
                os.remove(raw_output_path)
            raise HTTPException(
                status_code=500,
                detail=f"Piper execution error: {exc}",
            ) from exc

        if result.returncode != 0:
            if os.path.exists(raw_output_path):
                os.remove(raw_output_path)
            raise HTTPException(
                status_code=500,
                detail=f"Piper error: {result.stderr}",
            )

        if not os.path.exists(raw_output_path) or os.path.getsize(raw_output_path) == 0:
            if os.path.exists(raw_output_path):
                os.remove(raw_output_path)
            raise HTTPException(
                status_code=500,
                detail="TTS file was not created or is empty",
            )

        try:
            await asyncio.to_thread(
                resample_wav_to_sample_rate,
                raw_output_path,
                output_path,
                TTS_OUTPUT_SAMPLE_RATE,
            )
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(
                status_code=500,
                detail=f"TTS resampling error: {exc}",
            ) from exc
        finally:
            if os.path.exists(raw_output_path):
                os.remove(raw_output_path)

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise HTTPException(
                status_code=500,
                detail="TTS file was not created or is empty after resampling",
            )

    return FileResponse(output_path, media_type="audio/wav", filename="tts.wav")
