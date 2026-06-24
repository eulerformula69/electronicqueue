import asyncio
import json
import os
import secrets
import shutil
import subprocess
from datetime import datetime
from pathlib import Path as FilePath

from fastapi import HTTPException

from app.config import (
    ALLOWED_MEDIA_EXTENSIONS, BASE_DIR, FFMPEG_PATH, MEDIA_TRANSCODE_CRF,
    MEDIA_TRANSCODE_FPS, MEDIA_TRANSCODE_KEEP_AUDIO, MEDIA_TRANSCODE_MAX_WIDTH,
    MEDIA_TRANSCODE_PRESET,
)


MEDIA_DIR = BASE_DIR / "queue" / "media"
MEDIA_ORIGINALS_DIR = MEDIA_DIR / "originals"
MEDIA_PROCESSING_DIR = MEDIA_DIR / "processing"
MEDIA_JOBS_FILE = MEDIA_DIR / ".media_jobs.json"
MEDIA_TRANSCODE_MODES = {
    "normal": {
        "label": "Обычное качество",
        "crf": str(MEDIA_TRANSCODE_CRF),
        "preset": MEDIA_TRANSCODE_PRESET,
        "max_width": MEDIA_TRANSCODE_MAX_WIDTH,
        "fps": MEDIA_TRANSCODE_FPS,
    },
    "high": {
        "label": "Высокое качество",
        "crf": "20",
        "preset": MEDIA_TRANSCODE_PRESET,
        "max_width": 1920,
        "fps": 30,
    },
    "compact": {
        "label": "Максимальное сжатие",
        "crf": "26",
        "preset": MEDIA_TRANSCODE_PRESET,
        "max_width": 1280,
        "fps": 30,
    },
}

_jobs_lock = asyncio.Lock()
_media_queue: asyncio.Queue[str] | None = None
_worker_task: asyncio.Task | None = None


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _ensure_media_dirs() -> None:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_PROCESSING_DIR.mkdir(parents=True, exist_ok=True)


def _read_jobs_sync() -> dict:
    _ensure_media_dirs()
    if not MEDIA_JOBS_FILE.exists():
        return {}
    try:
        with MEDIA_JOBS_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_jobs_sync(jobs: dict) -> None:
    _ensure_media_dirs()
    temp_file = MEDIA_JOBS_FILE.with_name(
        f".{MEDIA_JOBS_FILE.name}.{secrets.token_hex(8)}.tmp"
    )
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(jobs, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temp_file, MEDIA_JOBS_FILE)


async def _load_jobs() -> dict:
    async with _jobs_lock:
        return _read_jobs_sync()


async def _save_job(job: dict) -> None:
    async with _jobs_lock:
        jobs = _read_jobs_sync()
        jobs[job["id"]] = job
        _write_jobs_sync(jobs)


def sanitize_media_filename(filename: str) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="Имя файла отсутствует")

    safe_name = os.path.basename(filename).strip()
    if safe_name in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Некорректное имя файла")

    ext = FilePath(safe_name).suffix.lower()
    if ext not in ALLOWED_MEDIA_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Недопустимое расширение файла")

    return safe_name


def build_media_file_path(filename: str) -> str:
    safe_filename = sanitize_media_filename(filename)
    _ensure_media_dirs()
    target_path = (MEDIA_DIR / safe_filename).resolve()
    media_dir = MEDIA_DIR.resolve()
    if os.path.commonpath([media_dir, target_path]) != str(media_dir):
        raise HTTPException(status_code=400, detail="Некорректный путь файла")
    return str(target_path)


def normalize_compression_mode(mode: str | None) -> str:
    if not mode:
        return "normal"
    normalized = mode.strip().lower()
    if normalized not in MEDIA_TRANSCODE_MODES:
        raise HTTPException(status_code=400, detail="Некорректный режим сжатия")
    return normalized


def _build_unique_output_filename(filename: str) -> str:
    safe_filename = sanitize_media_filename(filename)
    stem = FilePath(safe_filename).stem.strip() or "video"
    reserved_names = {
        job.get("filename")
        for job in _read_jobs_sync().values()
        if job.get("status") in {"pending", "processing"}
    }
    candidate = f"{stem}.mp4"
    counter = 2
    while (MEDIA_DIR / candidate).exists() or candidate in reserved_names:
        candidate = f"{stem}-{counter}.mp4"
        counter += 1
    return candidate


async def enqueue_media_processing(
    source_path: str,
    original_filename: str,
    compression_mode: str = "normal",
) -> dict:
    _ensure_media_dirs()
    safe_filename = sanitize_media_filename(original_filename)
    mode = normalize_compression_mode(compression_mode)
    job_id = secrets.token_hex(8)
    source = FilePath(source_path)
    output_filename = _build_unique_output_filename(safe_filename)

    job = {
        "id": job_id,
        "original_filename": safe_filename,
        "filename": output_filename,
        "status": "pending",
        "source_path": str(source),
        "output_path": str(MEDIA_DIR / output_filename),
        "compression_mode": mode,
        "compression_label": MEDIA_TRANSCODE_MODES[mode]["label"],
        "error": "",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }
    await _save_job(job)

    if _media_queue is not None:
        await _media_queue.put(job_id)

    return job


async def list_media_jobs() -> list[dict]:
    jobs = await _load_jobs()
    return sorted(
        jobs.values(),
        key=lambda item: item.get("created_at", ""),
        reverse=True,
    )


async def get_media_job_index() -> dict[str, dict]:
    jobs = await _load_jobs()
    return {
        job.get("filename"): job
        for job in jobs.values()
        if job.get("filename")
    }


async def retry_media_job(job_id: str) -> dict:
    if _media_queue is None:
        raise HTTPException(status_code=503, detail="Обработчик видео еще не запущен")

    jobs = await _load_jobs()
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача обработки не найдена")
    if job.get("status") not in {"error", "pending"}:
        raise HTTPException(status_code=400, detail="Эту задачу нельзя повторить")
    if not FilePath(job.get("source_path", "")).exists():
        raise HTTPException(status_code=400, detail="Исходный файл уже недоступен")

    job["status"] = "pending"
    job["error"] = ""
    job["updated_at"] = _utc_now()
    await _save_job(job)
    await _media_queue.put(job_id)
    return job


async def start_media_processor() -> None:
    global _media_queue, _worker_task

    if _worker_task and not _worker_task.done():
        return

    _ensure_media_dirs()
    _media_queue = asyncio.Queue()

    async with _jobs_lock:
        jobs = _read_jobs_sync()
        for job in jobs.values():
            if job.get("status") == "processing":
                job["status"] = "pending"
                job["updated_at"] = _utc_now()
            if (
                job.get("status") == "error"
                and not job.get("error")
                and FilePath(job.get("source_path", "")).exists()
            ):
                job["status"] = "pending"
                job["updated_at"] = _utc_now()
        _write_jobs_sync(jobs)
        pending_job_ids = [
            job_id for job_id, job in jobs.items()
            if job.get("status") == "pending"
        ]

    for job_id in pending_job_ids:
        await _media_queue.put(job_id)

    _worker_task = asyncio.create_task(_media_worker())


async def _media_worker() -> None:
    if _media_queue is None:
        return

    while True:
        job_id = await _media_queue.get()
        try:
            await _process_media_job(job_id)
        finally:
            _media_queue.task_done()


async def _process_media_job(job_id: str) -> None:
    jobs = await _load_jobs()
    job = jobs.get(job_id)
    if not job:
        return

    source_path = FilePath(job["source_path"])
    output_path = FilePath(job["output_path"])
    temp_output = MEDIA_PROCESSING_DIR / f"{job_id}.mp4"

    if not source_path.exists():
        job["status"] = "error"
        job["error"] = "Исходный файл не найден"
        job["updated_at"] = _utc_now()
        await _save_job(job)
        return

    job["status"] = "processing"
    job["error"] = ""
    job["updated_at"] = _utc_now()
    await _save_job(job)

    mode = normalize_compression_mode(job.get("compression_mode", "normal"))
    settings = MEDIA_TRANSCODE_MODES[mode]
    job["compression_mode"] = mode
    job["compression_label"] = settings["label"]
    scale_filter = f"scale='min({settings['max_width']},iw)':-2,fps={settings['fps']}"
    command = [
        FFMPEG_PATH, "-y",
        "-i", str(source_path),
        "-vf", scale_filter,
        "-c:v", "libx264",
        "-preset", settings["preset"],
        "-crf", settings["crf"],
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
    ]
    if MEDIA_TRANSCODE_KEEP_AUDIO:
        command.extend(["-c:a", "aac", "-b:a", "128k"])
    else:
        command.append("-an")
    command.append(str(temp_output))

    try:
        process = await asyncio.to_thread(
            subprocess.run,
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if process.returncode != 0:
            error = (process.stderr or process.stdout or "")[-1000:]
            raise RuntimeError(error or "ffmpeg завершился с ошибкой")

        os.replace(temp_output, output_path)
        try:
            source_path.unlink()
        except OSError:
            pass

        job["status"] = "ready"
        job["error"] = ""
        job["size_bytes"] = output_path.stat().st_size
        job["updated_at"] = _utc_now()
        await _save_job(job)
    except Exception as exc:
        if temp_output.exists():
            try:
                temp_output.unlink()
            except OSError:
                pass
        if isinstance(exc, FileNotFoundError):
            error_text = (
                f"ffmpeg не найден: {FFMPEG_PATH}. "
                "Укажите правильный FFMPEG_PATH в main.env или добавьте ffmpeg в PATH."
            )
        elif isinstance(exc, NotImplementedError):
            error_text = (
                "Windows не смог запустить ffmpeg через текущий режим asyncio. "
                "Обновите проект до версии с потоковым запуском ffmpeg и повторите обработку."
            )
        else:
            error_text = str(exc) or exc.__class__.__name__
        job["status"] = "error"
        job["error"] = error_text[-1000:]
        job["updated_at"] = _utc_now()
        await _save_job(job)


def save_upload_to_originals(file_obj, filename: str) -> str:
    _ensure_media_dirs()
    safe_filename = sanitize_media_filename(filename)
    ext = FilePath(safe_filename).suffix.lower()
    source_path = MEDIA_ORIGINALS_DIR / f"{secrets.token_hex(8)}{ext}"
    with source_path.open("wb") as buffer:
        shutil.copyfileobj(file_obj, buffer)
    return str(source_path)
