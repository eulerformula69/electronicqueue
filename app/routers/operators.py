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
from app.models import (
    Admin, Operator, Service, Window, WindowService, record_operator_status,
)
from app.schemas import OperatorCreate, OperatorLoginUpdate
from app.security import get_password_hash, verify_password
from app.services.operators import get_operator_state

router = APIRouter()


@router.get("/operator/windows", tags=["Operators"])
def get_operator_windows(operator: Operator = Depends(verify_session)):
    db = SessionLocal()
    try:
        windows = db.query(Window).order_by(Window.id.asc()).all()
        result = []

        for w in windows:
            assigned_operator = (
                db.query(Operator)
                .filter(Operator.window_id == w.id)
                .first()
            )

            services = (
                db.query(Service)
                .join(WindowService, WindowService.service_id == Service.id)
                .filter(WindowService.window_id == w.id)
                .order_by(WindowService.priority.asc(), Service.name.asc())
                .all()
            )

            result.append({
                "id": w.id,
                "name": w.name,
                "status": w.status,
                "operator_id": assigned_operator.id if assigned_operator else None,
                "operator_name": assigned_operator.name if assigned_operator else None,
                "operator_login": assigned_operator.login if assigned_operator else None,
                "services": [
                    {"id": service.id, "name": service.name, "status": service.status}
                    for service in services
                ],
                "service_names": [service.name for service in services]
            })

        return result
    finally:
        db.close()


@router.post("/operators/", tags=["Operators"])
def create_operator(
    operator: OperatorCreate, admin: Admin = Depends(verify_admin_session)
    ):
    db = SessionLocal()
    try:
        # 1. Хэшируем пароль перед сохранением в базу
        hashed_password = get_password_hash(operator.password)

        # 2. Создаем объект оператора с хэшированным паролем
        db_operator = Operator(
            name=operator.name,
            login=operator.login,
            password=hashed_password,
            window_id=operator.window_id,
        )

        db.add(db_operator)
        db.commit()
        db.refresh(db_operator)

        # 3. Возвращаем созданного оператора, но вместо хэша отдаем точки
        return {
            "id": db_operator.id,
            "name": db_operator.name,
            "login": db_operator.login,
            "window_id": db_operator.window_id,
            "password": "••••••",  # Админ видит это на экране вместо хэша
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()


@router.get("/operators/", tags=["Operators"])
async def list_operators(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    admin: Admin = Depends(verify_admin_session)
    ):
    db = SessionLocal()
    try:
        # Получаем всех операторов из базы
        operators = db.query(Operator).order_by(Operator.id).offset(skip).limit(limit).all()
        
        # Создаем новый список, где вместо хэшей паролей будут точки
        safe_operators = []
        for op in operators:
            safe_operators.append({
                "id": op.id,
                "name": op.name,
                "login": op.login,
                "window_id": op.window_id,
                "password": "••••••"  # Прячем хэш от фронтенда
            })
            
        return safe_operators
    finally:
        # Блок finally гарантирует, что база закроется даже при ошибке
        db.close()


@router.delete("/operators/{operator_id}", tags=["Operators"])
async def delete_operator(operator_id: int, admin: Admin = Depends(verify_admin_session)): # Добавили Depends
    db = SessionLocal()
    op = db.query(Operator).filter(Operator.id == operator_id).first()
    if not op:
        db.close()
        raise HTTPException(status_code=404, detail="Оператор не найден")
    db.delete(op)
    db.commit()
    db.close()
    return {"status": "ok"}


@router.patch("/operators/{operator_id}", tags=["Operators"])
async def update_operator(operator_id: int, data: dict, admin: Admin = Depends(verify_admin_session)):

    db = SessionLocal()

    op = db.query(Operator).filter(Operator.id == operator_id).first()

    if not op:
        db.close()
        raise HTTPException(status_code=404, detail="Operator not found")

    if "name" in data:
        op.name = data["name"]

    if "window_id" in data:

        new_window = data["window_id"]
        old_window_id = op.window_id
        new_window_status = "offline"

        if new_window is not None:

            window = db.query(Window).filter(Window.id == new_window).first()
            if not window:
                db.close()
                raise HTTPException(status_code=404, detail="Window not found")

            new_window_status = window.status

            existing = db.query(Operator).filter(
                Operator.window_id == new_window,
                Operator.id != operator_id
            ).first()

            if existing:
                db.close()
                raise HTTPException(
                    status_code=400,
                    detail="Это окно уже занято другим оператором"
                )

        op.window_id = new_window

        if old_window_id != new_window:
            record_operator_status(
                db, op.id, new_window, new_window_status
            )


    await manager.broadcast({"type": "services_updated"})
    db.commit()
    db.refresh(op)
    db.close()

    return op


@router.put("/operators/{operator_id}/login", tags=["Operators"])
def update_operator_login(
    operator_id: int = Path(..., gt=0), 
    data: OperatorLoginUpdate = Body(...), 
    admin: Admin = Depends(verify_admin_session)
 ):
    db: Session = SessionLocal()
    try:
        operator = db.query(Operator).filter(Operator.id == operator_id).first()
        if not operator:
            raise HTTPException(status_code=404, detail="Operator not found")

        # Обновляем логин
        operator.login = data.login
        
        # ХЭШИРУЕМ новый пароль перед сохранением
        operator.password = get_password_hash(data.password)
        
        db.commit()
        db.refresh(operator)
        
        # Возвращаем ответ без самого пароля (даже хэшированного)
        return {
            "message": "Login and password updated", 
            "operator_id": operator.id,
            "login": operator.login
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при обновлении: {str(e)}")
    finally:
        db.close()


@router.get("/operator/dashboard", tags=["Operators"])
def get_dashboard_data(operator: Operator = Depends(verify_session)):
    return get_operator_state(operator.id)


@router.get("/operators/details", tags=["Operators"])
async def get_my_details(operator: Operator = Depends(verify_session)):
    db = SessionLocal()
    try:
        window = None
        if operator.window_id:
            window = db.query(Window).filter(Window.id == operator.window_id).first()
        
        services_with_priority = []
        if operator.window_id:
            # Получаем и название услуги, и её приоритет из связующей таблицы
            results = (
                db.query(Service.name, WindowService.priority)
                .join(WindowService, Service.id == WindowService.service_id)
                .filter(WindowService.window_id == operator.window_id)
                .order_by(WindowService.priority.desc()) # Сортируем по важности
                .all()
            )
            
            # Формируем список словарей для фронтенда
            services_with_priority = [
                {"name": name, "priority": priority} 
                for name, priority in results
            ]

        return {
            "operator_name": operator.name,
            "window_id": operator.window_id,
            "window_name": window.name if window else "Не назначено",
            "window_status": window.status if window else "offline",
            "services": services_with_priority # Теперь это список объектов
        }
    finally:
        db.close()
