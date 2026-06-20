from sqlalchemy.orm import Session

from app.models import SystemSettings


def _str_to_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).lower() in {"1", "true", "yes", "on"}


def _bool_to_str(value: bool) -> str:
    return "true" if value else "false"


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
    return {
        "print_ticket": _str_to_bool(settings.print_ticket, default=True),
        "show_print_badge": _str_to_bool(settings.show_print_badge, default=True),
        "default_operator_status": settings.default_operator_status or "online",
        "active_ticket_on_operator_logout": settings.active_ticket_on_operator_logout or "return_to_queue",
        "hide_services_without_online_operators": _str_to_bool(
            settings.hide_services_without_online_operators, default=True
        ),
        "queue_mode": settings.queue_mode or "priority_fifo",
        "call_message_template": settings.call_message_template or "Талон <number> подойдите к окну <window>",
        "board_ticket_template": settings.board_ticket_template or "Билет <number> -> окно <window>",
    }
