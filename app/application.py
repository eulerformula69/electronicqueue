import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, CORS_ORIGINS
from app.database import Base, engine
from app.migrations import (
    init_ticket_numbering, migrate_operator_choice_schema,
    migrate_operator_status_periods_schema,
    migrate_service_archive_schema, migrate_service_order_schema,
    migrate_board_ticker_settings_schema, migrate_ticket_notice_settings_schema,
    migrate_ticket_operator_schema, migrate_ticket_stages_schema,
    migrate_ticket_queue_entered_at_schema,
    migrate_ticket_return_count_schema,
    migrate_ticket_defer_schema,
    migrate_ticket_recall_schema,
    migrate_service_groups_schema,
    migrate_service_terminal_visibility_schema,
    migrate_operator_service_notifications_schema,
    migrate_ticket_reason_settings_schema, migrate_auto_call_settings_schema,
    migrate_operator_auto_call_schema,
    migrate_called_ticket_min_wait_schema,
)
from app.routers import admin, auth, operators, services, system, tickets, tts, websocket, windows
from app.services.media import start_media_processor
from app.services.operators import cleanup_sessions
from app.services.tickets import auto_cancel_returned_tickets_worker

TESTING = os.getenv("TESTING", "").lower() in {"1", "true", "yes", "on"}

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/queue", StaticFiles(directory=BASE_DIR / "queue"), name="queue")

for router in (
    websocket.router, services.router, tickets.router, operators.router,
    windows.router, auth.router, admin.router, tts.router, system.router,
):
    app.include_router(router)


@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)
    migrate_operator_choice_schema(engine)
    migrate_service_order_schema(engine)
    migrate_service_archive_schema(engine)
    migrate_ticket_stages_schema(engine)
    migrate_operator_status_periods_schema(engine)
    migrate_ticket_operator_schema(engine)
    migrate_ticket_queue_entered_at_schema(engine)
    migrate_ticket_return_count_schema(engine)
    migrate_ticket_defer_schema(engine)
    migrate_ticket_recall_schema(engine)
    migrate_ticket_notice_settings_schema(engine)
    migrate_board_ticker_settings_schema(engine)
    migrate_ticket_reason_settings_schema(engine)
    migrate_auto_call_settings_schema(engine)
    migrate_operator_auto_call_schema(engine)
    migrate_called_ticket_min_wait_schema(engine)
    init_ticket_numbering(engine)
    migrate_service_terminal_visibility_schema(engine)
    migrate_service_groups_schema(engine)
    migrate_operator_service_notifications_schema(engine)
    if not TESTING:
        await start_media_processor()
        asyncio.create_task(cleanup_sessions())
        asyncio.create_task(auto_cancel_returned_tickets_worker())
