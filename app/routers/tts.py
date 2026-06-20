import asyncio
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path as FilePath
from typing import List

import bcrypt
from fastapi import (
    APIRouter, Body, Depends, File, Header, HTTPException, Query, UploadFile,
    WebSocket, WebSocketDisconnect, status,
)
from fastapi.params import Path
from fastapi.responses import FileResponse
from sqlalchemy import and_, asc, func, literal, text
from sqlalchemy.orm import Session

from app.config import (
    ALLOWED_MEDIA_EXTENSIONS, BASE_DIR, DEFAULT_PAGE_LIMIT, MAX_FILE_SIZE,
    MAX_PAGE_LIMIT, PIPER_MODEL, PIPER_PATH, SESSION_TIMEOUT_SECONDS,
    TTS_CACHE_DIR, TTS_LENGTH_SCALE,
    TTS_NOISE_SCALE, TTS_NOISE_W_SCALE,
)
from app.connections import manager, operatorManager
from app.database import SessionLocal
from app.dependencies import (
    get_current_terminal, get_operator_by_session, verify_admin_session,
    verify_session,
)
from app.security import get_password_hash, verify_password
from app.services.tts import get_tts_lock, normalize_tts_input, run_piper_sync

router = APIRouter()
@router.get("/tts/audio", tags=["TTS"])
async def get_tts_audio(text: str = Query(..., min_length=1, max_length=200)):
    text = normalize_tts_input(text)

    os.makedirs(TTS_CACHE_DIR, exist_ok=True)

    file_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
    output_path = os.path.join(TTS_CACHE_DIR, f"{file_hash}.wav")

    # Если файл уже есть — сразу отдаём
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return FileResponse(
            output_path,
            media_type="audio/wav",
            filename="tts.wav"
        )

    async with get_tts_lock(file_hash):
        # Повторная проверка после ожидания lock
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return FileResponse(
                output_path,
                media_type="audio/wav",
                filename="tts.wav"
            )

        result = await asyncio.to_thread(run_piper_sync, text, output_path)

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Piper error: {result.stderr}"
            )

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise HTTPException(
                status_code=500,
                detail="TTS файл не создан или пустой"
            )

    return FileResponse(
        output_path,
        media_type="audio/wav",
        filename="tts.wav"
    )
