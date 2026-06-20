import os
from pathlib import Path as FilePath

from fastapi import HTTPException

from app.config import ALLOWED_MEDIA_EXTENSIONS


def sanitize_media_filename(filename: str) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="Имя файла отсутствует")

    # Strip directory parts and normalize extension.
    safe_name = os.path.basename(filename).strip()
    if safe_name in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Некорректное имя файла")

    ext = FilePath(safe_name).suffix.lower()
    if ext not in ALLOWED_MEDIA_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Недопустимое расширение файла")

    return safe_name


def build_media_file_path(filename: str) -> str:
    media_dir = os.path.abspath("queue/media")
    os.makedirs(media_dir, exist_ok=True)
    target_path = os.path.abspath(os.path.join(media_dir, filename))
    if os.path.commonpath([media_dir, target_path]) != media_dir:
        raise HTTPException(status_code=400, detail="Некорректный путь файла")
    return target_path
