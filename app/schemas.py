from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel


class ServiceRename(BaseModel):
    name: str


class OperatorWindowUpdate(BaseModel):
    window_id: int | None


class OperatorLoginUpdate(BaseModel):
    login: str
    password: str


class ServiceStatusUpdate(BaseModel):
    status: str


class PriorityUpdate(BaseModel):
    window_id: int
    service_id: int
    priority: int


class LoginRequest(BaseModel):
    login: str
    password: str


class CallSpecificRequest(BaseModel):
    number: int


class PingRequest(BaseModel):
    session_id: str


class ServiceCreate(BaseModel):
    name: str
    operator_choice_enabled: bool = False


class ServiceOperatorChoiceUpdate(BaseModel):
    operator_choice_enabled: bool


class TicketCreate(BaseModel):
    service_id: int
    window_id: int | None = None


class TicketRead(BaseModel):
    id: int
    number: int
    service_id: int
    status: str
    completion_reason: Literal["completed", "redirected", "cancelled"] | None = None
    root_ticket_id: int | None = None
    window_id: int | None = None
    target_window_id: int | None = None
    created_at: datetime | None = None
    called_at: datetime | None = None
    finished_at: datetime | None = None

    class Config:
        from_attributes = True


class OperatorCreate(BaseModel):
    name: str
    login: str
    password: str
    window_id: int | None = None


class WindowCreate(BaseModel):
    name: str


class RedirectRequest(BaseModel):
    ticket_id: int
    new_service_id: int


class RedirectToWindowRequest(BaseModel):
    ticket_id: int
    window_id: int


class WindowServiceCreate(BaseModel):
    window_id: int
    service_id: int


class WindowServiceRead(BaseModel):
    window_id: int
    service_id: int
    class Config:
        from_attributes = True


class WindowStatusUpdateOp(BaseModel):
    window_id: int
    status: str


class WindowStatusUpdate(BaseModel):
    status: str


class ServicePriority(BaseModel):
    service_id: int
    priority: int


class WindowServiceItem(BaseModel):
    service_id: int
    priority: int


class WindowServicesUpdate(BaseModel):
    services: List[WindowServiceItem]


class PlaylistUpdate(BaseModel):
    path: str = None
    index: int = None
    action: str


class SystemSettingsUpdate(BaseModel):
    print_ticket: bool
    show_print_badge: bool
    default_operator_status: str
    active_ticket_on_operator_logout: str
    hide_services_without_online_operators: bool
    queue_mode: str
    call_message_template: str
    board_ticket_template: str


class SystemSettingsResponse(BaseModel):
    print_ticket: bool
    show_print_badge: bool
    default_operator_status: str
    active_ticket_on_operator_logout: str
    hide_services_without_online_operators: bool
    queue_mode: str
    call_message_template: str
    board_ticket_template: str


class PublicSettingsResponse(BaseModel):
    print_ticket: bool
    show_print_badge: bool
