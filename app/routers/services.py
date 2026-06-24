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
from app.models import Admin, Operator, Service, Ticket, Window, WindowService
from app.schemas import (
    ServiceCreate,
    ServiceOperatorChoiceUpdate,
    ServiceOrderUpdate,
    ServiceRename,
    ServiceStatusUpdate,
    ServiceTerminalVisibilityUpdate,
)
from app.security import get_password_hash, verify_password

router = APIRouter()


@router.post("/services/", tags=["Services"])
async def create_service(service: ServiceCreate, admin: Admin = Depends(verify_admin_session)):
    db = SessionLocal()
    try:
        next_order = db.query(func.coalesce(func.max(Service.display_order), -1)).scalar() + 1
        db_service = Service(
            name=service.name.strip(),
            display_order=next_order,
            operator_choice_enabled=1 if service.operator_choice_enabled else 0,
            visible_on_terminal=1 if service.visible_on_terminal else 1

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
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    include_hidden: bool = Query(False),
):
    db = SessionLocal()
    query = db.query(Service).filter(Service.is_archived == 0)

    if not include_hidden:
        query = query.filter(Service.visible_on_terminal == 1)

    services = (
        query
        .order_by(Service.display_order, Service.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    db.close()
    return services

@router.patch("/services/{service_id}/terminal-visibility", tags=["Services"])
async def update_service_terminal_visibility(
    service_id: int = Path(..., gt=0),
    data: ServiceTerminalVisibilityUpdate = ...,
    admin: Admin = Depends(verify_admin_session)
):
    db = SessionLocal()
    try:
        service = (
            db.query(Service)
            .filter(Service.id == service_id, Service.is_archived == 0)
            .first()
        )
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        service.visible_on_terminal = 1 if data.visible_on_terminal else 0
        db.commit()
        db.refresh(service)

        await manager.broadcast({"type": "services_updated"})

        return {
            "id": service.id,
            "visible_on_terminal": service.visible_on_terminal
        }
    finally:
        db.close()

@router.put("/services/order", tags=["Services"])
async def update_services_order(
    data: ServiceOrderUpdate,
    admin: Admin = Depends(verify_admin_session),
):
    db = SessionLocal()
    try:
        services = (
            db.query(Service)
            .filter(Service.is_archived == 0)
            .with_for_update()
            .all()
        )
        existing_ids = {service.id for service in services}

        if len(data.service_ids) != len(set(data.service_ids)):
            raise HTTPException(status_code=400, detail="Service IDs must be unique")
        if set(data.service_ids) != existing_ids:
            raise HTTPException(status_code=400, detail="The order must include all services")

        order_by_id = {
            service_id: position
            for position, service_id in enumerate(data.service_ids)
        }
        for service in services:
            service.display_order = order_by_id[service.id]

        db.commit()
        await manager.broadcast({"type": "services_updated"})
        return {"service_ids": data.service_ids}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.patch("/services/{service_id}", tags=["Services"])
async def rename_service(service_id: int, data: ServiceRename, admin: Admin = Depends(verify_admin_session)):
    db = SessionLocal()
    service = (
        db.query(Service)
        .filter(Service.id == service_id, Service.is_archived == 0)
        .first()
    )

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
        service = (
            db.query(Service)
            .filter(Service.id == service_id, Service.is_archived == 0)
            .first()
        )
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
        service = (
            db.query(Service)
            .filter(Service.id == service_id, Service.is_archived == 0)
            .first()
        )
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
        service = (
            db.query(Service)
            .filter(Service.id == service_id, Service.is_archived == 0)
            .first()
        )
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
async def delete_service(service_id: int, admin: Admin = Depends(verify_admin_session)):
    db = SessionLocal()
    try:
        service = (
            db.query(Service)
            .filter(Service.id == service_id, Service.is_archived == 0)
            .first()
        )
        if not service:
            raise HTTPException(status_code=404, detail="Услуга не найдена")

        ticket_count = db.query(Ticket).filter(Ticket.service_id == service_id).count()
        db.query(WindowService).filter(WindowService.service_id == service_id).delete(
            synchronize_session=False
        )

        if ticket_count:
            service.status = "inactive"
            service.is_archived = 1
            service.operator_choice_enabled = 0
            message = "Услуга архивирована, потому что по ней уже есть билеты"
            action = "archived"
        else:
            db.delete(service)
            message = "Услуга удалена"
            action = "deleted"

        db.commit()
        await manager.broadcast({"type": "services_updated"})
        return {"message": message, "action": action}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        print(f"Failed to delete service {service_id}: {exc!r}")
        raise HTTPException(
            status_code=500,
            detail="Не удалось удалить услугу из-за ошибки базы данных"
        ) from exc
    finally:
        db.close()
