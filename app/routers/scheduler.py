from fastapi import APIRouter, Depends

from app.database import SessionLocal
from app.dependencies import verify_admin_session
from app.models import Admin
from app.schemas import CloseDayScheduleResponse, CloseDayScheduleUpdate
from app.services.close_day_scheduler import get_or_create_schedule, serialize_schedule


router = APIRouter()


@router.get("/admin/close-day-schedule", response_model=CloseDayScheduleResponse, tags=["Admin"])
def get_close_day_schedule(admin: Admin = Depends(verify_admin_session)):
    db = SessionLocal()
    try:
        return serialize_schedule(get_or_create_schedule(db))
    finally:
        db.close()


@router.put("/admin/close-day-schedule", response_model=CloseDayScheduleResponse, tags=["Admin"])
def update_close_day_schedule(data: CloseDayScheduleUpdate, admin: Admin = Depends(verify_admin_session)):
    db = SessionLocal()
    try:
        schedule = get_or_create_schedule(db)
        schedule.enabled = int(data.enabled)
        schedule.weekdays = ",".join(str(day) for day in sorted(set(data.weekdays)))
        schedule.run_time = data.run_time
        schedule.operator_action = data.operator_action
        schedule.ticket_action = data.ticket_action
        db.commit()
        db.refresh(schedule)
        return serialize_schedule(schedule)
    finally:
        db.close()
