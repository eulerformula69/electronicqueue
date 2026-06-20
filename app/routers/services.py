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
from app.models import Admin, Operator, Service, Window, WindowService
from app.schemas import (
    ServiceCreate, ServiceOperatorChoiceUpdate, ServiceRename,
    ServiceStatusUpdate,
)
from app.security import get_password_hash, verify_password

router = APIRouter()


@router.post("/services/", tags=["Services"])
async def create_service(service: ServiceCreate, admin: Admin = Depends(verify_admin_session)):
    db = SessionLocal()
    try:
        db_service = Service(
            name=service.name.strip(),
            operator_choice_enabled=1 if service.operator_choice_enabled else 0
        )
        db.add(db_service)
        db.commit()
        db.refresh(db_service)

        await manager.broadcast({"type": "services_updated"})
        return db_service
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        print(f"Failed to create service: {exc!r}")
        raise HTTPException(
            status_code=500,
            detail="Не удалось создать услугу из-за ошибки базы данных"
        ) from exc
    finally:
        db.close()


@router.get("/services/", tags=["Services"])
def list_services(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
    ):
    db = SessionLocal()
    services = db.query(Service).order_by(Service.id).offset(skip).limit(limit).all()
    db.close()
    return services


@router.patch("/services/{service_id}", tags=["Services"])
async def rename_service(service_id: int, data: ServiceRename, admin: Admin = Depends(verify_admin_session)):
    db = SessionLocal()
    service = db.query(Service).filter(Service.id == service_id).first()

    if not service:
        db.close()
        raise HTTPException(status_code=404, detail="Service not found")

    service.name = data.name
    db.commit()
    
    await manager.broadcast({
        "type": "services_updated"
    })    
    
    db.refresh(service)
    db.close()

    return service


@router.patch("/services/{service_id}/status", tags=["Services"])
async def update_service_status(
    service_id: int = Path(..., gt=0),
    data: ServiceStatusUpdate = ...,
    admin: Admin = Depends(verify_admin_session)
    ):
    db = SessionLocal()
    try:
        service = db.query(Service).filter(Service.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        if data.status not in ["active", "inactive"]:
            raise HTTPException(status_code=400, detail="Invalid status")

        service.status = data.status
        db.commit()
        db.refresh(service)
        await manager.broadcast({"type": "services_updated"})

        return {"id": service.id, "status": service.status}
    finally:
        db.close()


@router.patch("/services/{service_id}/operator-choice", tags=["Services"])
async def update_service_operator_choice(
    service_id: int = Path(..., gt=0),
    data: ServiceOperatorChoiceUpdate = ...,
    admin: Admin = Depends(verify_admin_session)
    ):
    db = SessionLocal()
    try:
        service = db.query(Service).filter(Service.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        service.operator_choice_enabled = 1 if data.operator_choice_enabled else 0
        db.commit()
        db.refresh(service)
        await manager.broadcast({"type": "services_updated"})

        return {
            "id": service.id,
            "operator_choice_enabled": service.operator_choice_enabled
        }
    finally:
        db.close()


@router.get("/services/{service_id}/operators", tags=["Services"])
def list_service_operators(
    service_id: int = Path(..., gt=0),
    _auth = Depends(get_current_terminal)
    ):
    db = SessionLocal()
    try:
        service = db.query(Service).filter(Service.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Услуга не найдена")

        rows = (
            db.query(Operator, Window)
            .join(Window, Operator.window_id == Window.id)
            .join(WindowService, Window.id == WindowService.window_id)
            .filter(
                WindowService.service_id == service_id,
                Window.status == "online"
            )
            .order_by(Operator.name.asc())
            .all()
        )

        return [
            {
                "operator_id": operator.id,
                "operator_name": operator.name,
                "window_id": window.id,
                "window_name": window.name
            }
            for operator, window in rows
        ]
    finally:
        db.close()


@router.delete("/services/{service_id}", tags=["Services"])
async def delete_service(service_id: int, admin: Admin = Depends(verify_admin_session)): # Добавили проверку
    db = SessionLocal()
    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        db.close()
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    
    db.delete(service)

    await manager.broadcast({
        "type": "services_updated"
    })

    db.commit()
    db.close()

    return {"message": "Service deleted"}
