import json

from sqlalchemy.orm import Session

from app.models import SystemSettings

DEFAULT_TICKET_PRINT_SCALE_PERCENT = 94
MIN_TICKET_PRINT_SCALE_PERCENT = 50
MAX_TICKET_PRINT_SCALE_PERCENT = 150
DEFAULT_AUTO_CALL_DELAY_SECONDS = 60
MIN_AUTO_CALL_DELAY_SECONDS = 0
MAX_AUTO_CALL_DELAY_SECONDS = 600
DEFAULT_CALLED_TICKET_MIN_WAIT_SECONDS = 180
MIN_CALLED_TICKET_MIN_WAIT_SECONDS = 0
MAX_CALLED_TICKET_MIN_WAIT_SECONDS = 3600
DEFAULT_CANCELLED_TICKET_BOARD_MESSAGE_TEMPLATE = (
    "⚠ Талон <number>: вызов отменён — клиент не подошёл. "
    "Вернулись? Сообщите номер оператору."
)

DEFAULT_TICKET_NOTICE_PRINTED_TEXT = "Ваш номер: <number>"
DEFAULT_TICKET_NOTICE_UNPRINTED_TEXT = "Пожалуйста, запомните свой номер:\n<number>"
BOARD_TICKER_SEPARATOR = " | "
DEFAULT_CANCEL_REASON_OPTIONS = [
    {"text": "Клиент не явился", "enabled": True},
    {"text": "Отказался от услуги", "enabled": True},
    {"text": "Ошибочный талон", "enabled": True},
    {"text": "Нет нужного документа", "enabled": True},
    {"text": "Другое", "enabled": True},
]
DEFAULT_DEFER_REASON_OPTIONS = [
    {"text": "Заполняет документы", "enabled": True},
    {"text": "Оплачивает", "enabled": True},
    {"text": "Пошёл за документами", "enabled": True},
    {"text": "Нет нужного документа", "enabled": True},
    {"text": "Другое", "enabled": True},
]


def _str_to_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).lower() in {"1", "true", "yes", "on"}


def _bool_to_str(value: bool) -> str:
    return "true" if value else "false"


def _normalize_ticket_print_scale_percent(value: int | None) -> int:
    if value is None:
        return DEFAULT_TICKET_PRINT_SCALE_PERCENT
    return max(
        MIN_TICKET_PRINT_SCALE_PERCENT,
        min(MAX_TICKET_PRINT_SCALE_PERCENT, int(value)),
    )


def _normalize_auto_call_delay_seconds(value: int | None) -> int:
    if value is None:
        return DEFAULT_AUTO_CALL_DELAY_SECONDS
    return max(
        MIN_AUTO_CALL_DELAY_SECONDS,
        min(MAX_AUTO_CALL_DELAY_SECONDS, int(value)),
    )


def _normalize_called_ticket_min_wait_seconds(value: int | None) -> int:
    if value is None:
        return DEFAULT_CALLED_TICKET_MIN_WAIT_SECONDS
    return max(
        MIN_CALLED_TICKET_MIN_WAIT_SECONDS,
        min(MAX_CALLED_TICKET_MIN_WAIT_SECONDS, int(value)),
    )


def normalize_board_ticker_messages(messages, legacy_text: str | None = "") -> list[dict]:
    normalized = []
    if isinstance(messages, str) and messages.strip():
        try:
            messages = json.loads(messages)
        except json.JSONDecodeError:
            messages = []
    if not isinstance(messages, list):
        messages = []

    for item in messages:
        if isinstance(item, str):
            text = item.strip()
            enabled = True
        elif isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            enabled = item.get("enabled") is not False
        else:
            continue
        if text:
            normalized.append({"text": text[:500], "enabled": enabled})

    if not normalized and legacy_text:
        for line in str(legacy_text).splitlines():
            text = line.strip()
            if text:
                normalized.append({"text": text[:500], "enabled": True})

    return normalized


def serialize_board_ticker_messages(messages) -> str:
    return json.dumps(
        normalize_board_ticker_messages(messages),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def build_board_ticker_text(messages) -> str:
    return BOARD_TICKER_SEPARATOR.join(
        item["text"] for item in normalize_board_ticker_messages(messages)
        if item["enabled"]
    )[:500]


def normalize_ticket_reason_options(options, defaults: list[dict] | None = None) -> list[dict]:
    normalized = []
    provided = False
    if isinstance(options, str) and options.strip():
        provided = True
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = []
    elif isinstance(options, list):
        provided = True
    else:
        options = []

    for item in options:
        if isinstance(item, str):
            text = item.strip()
            enabled = True
        elif isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            enabled = item.get("enabled") is not False
        else:
            continue
        if text:
            normalized.append({"text": text[:120], "enabled": enabled})

    if normalized or provided:
        return normalized
    return list(defaults or [])


def serialize_ticket_reason_options(options, defaults: list[dict] | None = None) -> str:
    return json.dumps(
        normalize_ticket_reason_options(options, defaults),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def enabled_ticket_reason_options(options) -> list[dict]:
    enabled = [
        item for item in normalize_ticket_reason_options(options)
        if item["enabled"]
    ]
    if not any(item["text"] == "Другое" for item in enabled):
        enabled.append({"text": "Другое", "enabled": True})
    return enabled


def normalize_ticket_reason(value: str | None) -> str:
    reason = str(value or "").strip()
    if not reason:
        return ""
    if reason == "other":
        return "Другое"
    if reason.startswith("other:"):
        comment = reason.split(":", 1)[1].strip()
        return f"Другое: {comment}" if comment else "Другое"
    if reason.startswith("Другое:"):
        comment = reason.split(":", 1)[1].strip()
        return f"Другое: {comment}" if comment else "Другое"
    return reason[:255]


def get_or_create_system_settings(db: Session) -> SystemSettings:
    settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    if settings:
        return settings

    settings = SystemSettings(id=1)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def get_system_settings_dict(db: Session) -> dict:
    settings = get_or_create_system_settings(db)
    board_ticker_messages = normalize_board_ticker_messages(
        settings.board_ticker_messages,
        settings.board_ticker_text,
    )
    cancel_reason_options = normalize_ticket_reason_options(
        settings.cancel_reason_options,
        DEFAULT_CANCEL_REASON_OPTIONS,
    )
    defer_reason_options = normalize_ticket_reason_options(
        settings.defer_reason_options,
        DEFAULT_DEFER_REASON_OPTIONS,
    )
    return {
        "print_ticket": _str_to_bool(settings.print_ticket, default=True),
        "show_print_badge": _str_to_bool(settings.show_print_badge, default=True),
        "ticket_print_scale_percent": _normalize_ticket_print_scale_percent(
            settings.ticket_print_scale_percent
        ),
        "ticket_notice_duration_printed_seconds": settings.ticket_notice_duration_printed_seconds or 7,
        "ticket_notice_duration_unprinted_seconds": settings.ticket_notice_duration_unprinted_seconds or 45,
        "ticket_notice_printed_text": settings.ticket_notice_printed_text or DEFAULT_TICKET_NOTICE_PRINTED_TEXT,
        "ticket_notice_unprinted_text": settings.ticket_notice_unprinted_text or DEFAULT_TICKET_NOTICE_UNPRINTED_TEXT,
        "default_operator_status": settings.default_operator_status or "online",
        "active_ticket_on_operator_logout": settings.active_ticket_on_operator_logout or "return_to_queue",
        "hide_services_without_online_operators": _str_to_bool(
            settings.hide_services_without_online_operators, default=True
        ),
        "redirect_allow_break": _str_to_bool(settings.redirect_allow_break, default=True),
        "redirect_allow_offline": _str_to_bool(settings.redirect_allow_offline, default=False),
        "call_message_template": settings.call_message_template or "Талон <number> подойдите к окну <window>",
        "board_ticket_template": settings.board_ticket_template or "Билет <number> -> окно <window>",
        "board_ticker_text": build_board_ticker_text(board_ticker_messages),
        "board_ticker_messages": board_ticker_messages,
        "cancel_reason_options": cancel_reason_options,
        "defer_reason_options": defer_reason_options,
        "auto_call_enabled": _str_to_bool(settings.auto_call_enabled, default=False),
        "auto_call_delay_seconds": _normalize_auto_call_delay_seconds(
            settings.auto_call_delay_seconds
        ),
        "called_ticket_min_wait_seconds": _normalize_called_ticket_min_wait_seconds(
            settings.called_ticket_min_wait_seconds
        ),
        "auto_call_balance_enabled": _str_to_bool(
            settings.auto_call_balance_enabled, default=True
        ),
        "auto_call_balance_queue_threshold": max(
            1, min(100, int(settings.auto_call_balance_queue_threshold or 3))
        ),
        "auto_call_balance_min_free_operators": max(
            2, min(100, int(settings.auto_call_balance_min_free_operators or 2))
        ),
        "cancelled_ticket_board_display_seconds": max(
            0, min(3600, int(
                settings.cancelled_ticket_board_display_seconds
                if settings.cancelled_ticket_board_display_seconds is not None
                else 60
            ))
        ),
        "cancelled_ticket_board_message_template": (
            settings.cancelled_ticket_board_message_template
            or DEFAULT_CANCELLED_TICKET_BOARD_MESSAGE_TEMPLATE
        ),
    }
