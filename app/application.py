import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, CORS_ORIGINS
from app.database import Base, engine
from app.migrations import (
    init_ticket_numbering, migrate_operator_choice_schema,
    migrate_operator_status_periods_schema, migrate_queue_mode_periods_schema,
    migrate_ticket_stages_schema,
)
from app.routers import admin, auth, operators, services, tickets, tts, websocket, windows
from app.services.operators import cleanup_sessions


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
    windows.router, auth.router, admin.router, tts.router,
):
    app.include_router(router)


@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)
    migrate_operator_choice_schema(engine)
    migrate_ticket_stages_schema(engine)
    migrate_operator_status_periods_schema(engine)
    migrate_queue_mode_periods_schema(engine)
    init_ticket_numbering(engine)
    asyncio.create_task(cleanup_sessions())
