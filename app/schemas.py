from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, Field


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


class CallNextRequest(BaseModel):
    auto_call: bool = False


class DeferTicketRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=255)


class CancelTicketRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=255)


class PingRequest(BaseModel):
    session_id: str


class ServiceCreate(BaseModel):
    name: str
    operator_choice_enabled: bool = False
    operator_choice_allow_break: bool = True
    operator_choice_allow_offline: bool = False
    visible_on_terminal: bool = True
    service_group_id: int | None = None


class ServiceOperatorChoiceUpdate(BaseModel):
    operator_choice_enabled: bool
    operator_choice_allow_break: bool = True
    operator_choice_allow_offline: bool = False


class ServiceGroupCreate(BaseModel):
    name: str


class ServiceGroupUpdate(BaseModel):
    name: str


class ServiceGroupOrderUpdate(BaseModel):
    group_ids: List[int]


class ServiceGroupAssignUpdate(BaseModel):
    service_group_id: int | None = None


class ServiceOrderUpdate(BaseModel):
    service_ids: List[int]


class TicketCreate(BaseModel):
    service_id: int
    window_id: int | None = None

class ServiceTerminalVisibilityUpdate(BaseModel):
    visible_on_terminal: bool


class OperatorServiceNotificationUpdate(BaseModel):
    enabled: bool


class OperatorServiceNotificationRead(BaseModel):
    service_id: int
    service_name: str
    priority: int
    enabled: bool


class TicketRead(BaseModel):
    id: int
    number: int
    service_id: int
    status: str
    completion_reason: Literal["completed", "redirected", "cancelled"] | None = None
    root_ticket_id: int | None = None
    operator_id: int | None = None
    window_id: int | None = None
    target_window_id: int | None = None
    created_at: datetime | None = None
    queue_entered_at: datetime | None = None
    defer_reason: str | None = None
    deferred_at: datetime | None = None
    cancel_reason: str | None = None
    called_at: datetime | None = None
    finished_at: datetime | None = None

    class Config:
        from_attributes = True


class TicketReprintResponse(BaseModel):
    id: int
    number: int
    service_name: str
    waiting_before: int
    date: str


class OperatorCreate(BaseModel):
    name: str
    login: str
    password: str
    window_id: int | None = None
    auto_call_mode: str = "default"


class WindowCreate(BaseModel):
    name: str


class WindowOperatorUpdate(BaseModel):
    operator_id: int | None = None


class RedirectRequest(BaseModel):
    ticket_id: int
    new_service_id: int


class RedirectToWindowRequest(BaseModel):
    ticket_id: int
    window_id: int
    new_service_id: int


class WindowServiceCreate(BaseModel):
    window_id: int
    service_id: int


class WindowServiceRead(BaseModel):
    window_id: int
    service_id: int
    priority: int = 1
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


class MapObject(BaseModel):
    id: str
    type: Literal["room", "workplace", "wall", "door", "label", "zone"]
    x: int
    y: int
    width: int
    height: int
    label: str = ""
    window_id: int | None = None


class OfficeMap(BaseModel):
    version: int = 1
    width: int = 1200
    height: int = 700
    objects: List[MapObject] = Field(default_factory=list)


class BoardTickerMessage(BaseModel):
    text: str = Field(default="", max_length=500)
    enabled: bool = True


class TicketReasonOption(BaseModel):
    text: str = Field(default="", max_length=120)
    enabled: bool = True


class SystemSettingsUpdate(BaseModel):
    print_ticket: bool
    show_print_badge: bool
    ticket_print_scale_percent: int = Field(default=94, ge=50, le=150)
    ticket_notice_duration_printed_seconds: int = Field(ge=1, le=300)
    ticket_notice_duration_unprinted_seconds: int = Field(ge=1, le=300)
    ticket_notice_printed_text: str = Field(default="Ваш номер: <number>", min_length=1, max_length=500)
    ticket_notice_unprinted_text: str = Field(default="Пожалуйста, запомните свой номер:\n<number>", min_length=1, max_length=500)
    default_operator_status: str
    active_ticket_on_operator_logout: str
    hide_services_without_online_operators: bool
    redirect_allow_break: bool = True
    redirect_allow_offline: bool = False
    call_message_template: str
    board_ticket_template: str
    board_ticker_text: str = Field(default="", max_length=500)
    board_ticker_messages: List[BoardTickerMessage] = Field(default_factory=list)
    cancel_reason_options: List[TicketReasonOption] = Field(default_factory=list)
    defer_reason_options: List[TicketReasonOption] = Field(default_factory=list)
    auto_call_enabled: bool = False
    auto_call_delay_seconds: int = Field(default=60, ge=0, le=600)
    called_ticket_min_wait_seconds: int = Field(default=180, ge=0, le=3600)


class SystemSettingsResponse(BaseModel):
    print_ticket: bool
    show_print_badge: bool
    ticket_print_scale_percent: int
    ticket_notice_duration_printed_seconds: int
    ticket_notice_duration_unprinted_seconds: int
    ticket_notice_printed_text: str
    ticket_notice_unprinted_text: str
    default_operator_status: str
    active_ticket_on_operator_logout: str
    hide_services_without_online_operators: bool
    redirect_allow_break: bool
    redirect_allow_offline: bool
    call_message_template: str
    board_ticket_template: str
    board_ticker_text: str
    board_ticker_messages: List[BoardTickerMessage] = Field(default_factory=list)
    cancel_reason_options: List[TicketReasonOption] = Field(default_factory=list)
    defer_reason_options: List[TicketReasonOption] = Field(default_factory=list)
    auto_call_enabled: bool
    auto_call_delay_seconds: int
    called_ticket_min_wait_seconds: int


class PublicSettingsResponse(BaseModel):
    print_ticket: bool
    show_print_badge: bool
    ticket_print_scale_percent: int
    ticket_notice_duration_printed_seconds: int
    ticket_notice_duration_unprinted_seconds: int
    ticket_notice_printed_text: str
    ticket_notice_unprinted_text: str
    redirect_allow_break: bool
    redirect_allow_offline: bool
    board_ticket_template: str
    board_ticker_text: str
    cancel_reason_options: List[TicketReasonOption] = Field(default_factory=list)
    defer_reason_options: List[TicketReasonOption] = Field(default_factory=list)
    auto_call_enabled: bool
    auto_call_delay_seconds: int
    called_ticket_min_wait_seconds: int
