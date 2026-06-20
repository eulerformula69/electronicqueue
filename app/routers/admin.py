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
from app.models import Admin, Service, Window
from app.schemas import (
    PlaylistUpdate, PublicSettingsResponse, SystemSettingsResponse,
    SystemSettingsUpdate,
)
from app.security import get_password_hash, verify_password
from app.services.media import build_media_file_path, sanitize_media_filename
from app.services.operators import update_services_status_for_window
from app.services.settings import (
    _bool_to_str, get_or_create_system_settings, get_system_settings_dict,
)
from app.services.tickets import broadcast_board

router = APIRouter()


@router.post("/admin/media/upload", tags=["Admin"])
async def upload_media(
    file: UploadFile = File(...), 
    admin: Admin = Depends(verify_admin_session)
    ):
    safe_filename = sanitize_media_filename(file.filename)

    # 1. Size Limit Check
    # Spool to check size without reading everything into memory at once
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Файл слишком большой. Максимум 50MB.")

    file_path = build_media_file_path(safe_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
            
    return {"status": "success", "filename": safe_filename}


@router.delete("/admin/media/file/{filename}", tags=["Admin"])
async def delete_media_file(filename: str, admin: Admin = Depends(verify_admin_session)):
    safe_filename = sanitize_media_filename(filename)
    file_path = build_media_file_path(safe_filename)
    
    # 1. Remove from physical storage
    if os.path.exists(file_path):
        os.remove(file_path)
    
    # 2. Remove from playlist.json if it exists there
    playlist_path = os.path.abspath("queue/media/playlist.json")
    if os.path.exists(playlist_path):
        with open(playlist_path, "r", encoding="utf-8") as f:
            playlist = json.load(f)
        
        web_path = f"/queue/media/{safe_filename}"
        if web_path in playlist:
            playlist.remove(web_path)
            with open(playlist_path, "w", encoding="utf-8") as f:
                json.dump(playlist, f, ensure_ascii=False, indent=4)
    
    await manager.broadcast({"type": "playlist_updated"})
    return {"status": "deleted"}


@router.post("/admin/media/playlist", tags=["Admin"])
async def update_playlist(data: PlaylistUpdate, admin: Admin = Depends(verify_admin_session)):
    playlist_path = os.path.abspath("queue/media/playlist.json")
    os.makedirs(os.path.dirname(playlist_path), exist_ok=True)
    
    # Load current playlist
    playlist = []
    if os.path.exists(playlist_path):
        with open(playlist_path, "r", encoding="utf-8") as f:
            try:
                playlist = json.load(f)
                if not isinstance(playlist, list): # Safety check
                    playlist = []
            except:
                playlist = []

    if data.action == "add":
        if not data.path or not data.path.startswith("/queue/media/"):
            raise HTTPException(status_code=400, detail="Некорректный путь в плейлисте")
        sanitize_media_filename(data.path.rsplit("/", 1)[-1])
        if data.path not in playlist:
            playlist.append(data.path)
    elif data.action == "delete":
        playlist = [item for item in playlist if item != data.path]

    with open(playlist_path, "w", encoding="utf-8") as f:
        json.dump(playlist, f, ensure_ascii=False, indent=4)
            
    # BROADCAST UPDATE
    await manager.broadcast({"type": "playlist_updated"})
    
    return {"status": "success"}


@router.get("/admin/media/files", tags=["Admin"])
async def list_media_files(admin: Admin = Depends(verify_admin_session)):
    media_dir = os.path.abspath("queue/media")
    if not os.path.exists(media_dir):
        os.makedirs(media_dir)
    
    # List physical files on disk
    physical_files = [
        f for f in os.listdir(media_dir)
        if FilePath(f).suffix.lower() in ALLOWED_MEDIA_EXTENSIONS
    ]
    
    # Get current playlist
    playlist_path = os.path.join(media_dir, "playlist.json")
    playlist = []
    if os.path.exists(playlist_path):
        try:
            with open(playlist_path, "r", encoding="utf-8") as f:
                playlist = json.load(f)
        except:
            playlist = []
            
    return {
        "files": physical_files,
        "playlist": playlist
    }


@router.get("/admin/settings", response_model=SystemSettingsResponse, tags=["Admin"])
async def get_admin_settings(admin: Admin = Depends(verify_admin_session)):
    db = SessionLocal()
    try:
        return get_system_settings_dict(db)
    finally:
        await manager.broadcast({"type": "services_updated"})
        await manager.broadcast({"type": "settings_updated"})
        await manager.broadcast({"type": "queue_updated"})
        db.close()


@router.put("/admin/settings", response_model=SystemSettingsResponse, tags=["Admin"])
async def update_admin_settings(
    data: SystemSettingsUpdate,
    admin: Admin = Depends(verify_admin_session)
    ):
    if data.default_operator_status not in {"online", "break", "offline"}:
        raise HTTPException(status_code=400, detail="Некорректный default_operator_status")

    if data.active_ticket_on_operator_logout not in {"return_to_queue", "keep_with_operator"}:
        raise HTTPException(status_code=400, detail="Некорректный active_ticket_on_operator_logout")

    if data.queue_mode not in {"priority_fifo", "dynamic_operator_distribution"}:
        raise HTTPException(status_code=400, detail="Некорректный queue_mode")
        
    if "<number>" not in data.call_message_template or "<window>" not in data.call_message_template:
        raise HTTPException(
            status_code=400,
            detail="Шаблон сообщения должен содержать <number> и <window>"
        )

    if "<number>" not in data.board_ticket_template or "<window>" not in data.board_ticket_template:
        raise HTTPException(
            status_code=400,
            detail="Шаблон табло должен содержать <number> и <window>"
        )        

    db = SessionLocal()
    try:
        settings = get_or_create_system_settings(db)
        settings.print_ticket = _bool_to_str(data.print_ticket)
        settings.show_print_badge = _bool_to_str(data.show_print_badge)
        settings.default_operator_status = data.default_operator_status
        settings.active_ticket_on_operator_logout = data.active_ticket_on_operator_logout
        settings.hide_services_without_online_operators = _bool_to_str(
            data.hide_services_without_online_operators
        )
        settings.queue_mode = data.queue_mode
        settings.call_message_template = data.call_message_template
        settings.board_ticket_template = data.board_ticket_template        
        db.commit()

        if data.hide_services_without_online_operators:
            all_window_ids = [row[0] for row in db.query(Window.id).all()]
            for window_id in all_window_ids:
                update_services_status_for_window(db, window_id)
        else:
            db.query(Service).update({Service.status: "active"})
            db.commit()

        await manager.broadcast({"type": "services_updated"})
        await manager.broadcast({"type": "settings_updated"})
        await broadcast_board()
        await manager.broadcast({"type": "queue_updated"})        
        return get_system_settings_dict(db)
    finally:
        db.close()


@router.get("/settings/public", response_model=PublicSettingsResponse, tags=["Settings"])
async def get_public_settings():
    db = SessionLocal()
    try:
        settings = get_system_settings_dict(db)
        return {
            "print_ticket": settings["print_ticket"],
            "show_print_badge": settings["show_print_badge"]
        }
    finally:
        db.close()
