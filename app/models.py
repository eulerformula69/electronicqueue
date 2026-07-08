from datetime import datetime

from sqlalchemy import (
    BigInteger, CheckConstraint, Column, ForeignKey, Index, Integer, String,
    TIMESTAMP, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Session, relationship

from app.database import Base


class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    display_order = Column(Integer, nullable=False, default=0, server_default=text("0"))
    service_group_id = Column(Integer, ForeignKey("service_groups.id", ondelete="SET NULL"), nullable=True)
    status = Column(String, default="inactive")
    is_archived = Column(Integer, nullable=False, default=0, server_default=text("0"))
    last_window_id = Column(Integer, ForeignKey("windows.id"), nullable=True)
    operator_choice_enabled = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    visible_on_terminal = Column(
    Integer, nullable=False, default=1, server_default=text("1")
    )


class ServiceGroup(Base):
    __tablename__ = "service_groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    display_order = Column(Integer, nullable=False, default=0, server_default=text("0"))


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "completion_reason IS NULL OR completion_reason IN "
            "('completed', 'redirected', 'cancelled')",
            name="ck_tickets_completion_reason",
        ),
        Index("ix_tickets_root_ticket_id", "root_ticket_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    number = Column(Integer, nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"))
    status = Column(String, default="waiting")
    completion_reason = Column(String(16), nullable=True)
    root_ticket_id = Column(
        Integer,
        ForeignKey("tickets.id", name="fk_tickets_root_ticket_id"),
        nullable=True,
    )
    operator_id = Column(Integer, ForeignKey("operators.id"), nullable=True)
    window_id = Column(Integer, nullable=True)
    target_window_id = Column(Integer, ForeignKey("windows.id"), nullable=True)
    created_at = Column(
        TIMESTAMP,
        server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Irkutsk')"),
    )
    queue_entered_at = Column(
        TIMESTAMP,
        server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Irkutsk')"),
    )
    returned_to_queue_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    defer_reason = Column(String(255), nullable=True)
    deferred_at = Column(TIMESTAMP, nullable=True)
    cancel_reason = Column(String(255), nullable=True)
    called_at = Column(TIMESTAMP, nullable=True)
    finished_at = Column(TIMESTAMP, nullable=True)

    service = relationship("Service")


class Operator(Base):
    __tablename__ = "operators"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    login = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    window_id = Column(Integer, ForeignKey("windows.id"), unique=True)


class OperatorServiceNotification(Base):
    __tablename__ = "operator_service_notifications"
    __table_args__ = (
        UniqueConstraint("operator_id", "service_id", name="uq_operator_service_notifications"),
    )

    id = Column(Integer, primary_key=True, index=True)
    operator_id = Column(Integer, ForeignKey("operators.id", ondelete="CASCADE"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id", ondelete="CASCADE"), nullable=False)
    enabled = Column(Integer, nullable=False, default=1, server_default=text("1"))


class Window(Base):
    __tablename__ = "windows"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    status = Column(String, default="offline")


class UserSession(Base):
    __tablename__ = "sessions"
    session_id = Column(String, primary_key=True) 
    operator_id = Column(Integer, ForeignKey("operators.id"))
    created_at = Column(TIMESTAMP, server_default=text("NOW()"), nullable=False)
    last_seen = Column(TIMESTAMP, server_default=text("NOW()"), nullable=False)
    is_expirable = Column(Integer, default=1)


class OperatorStatusPeriod(Base):
    __tablename__ = "operator_status_periods"
    __table_args__ = (
        CheckConstraint(
            "status IN ('online', 'break', 'offline')",
            name="ck_operator_status_periods_status",
        ),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="ck_operator_status_periods_dates",
        ),
        Index("ix_operator_status_period", "operator_id", "started_at"),
        Index(
            "uq_operator_current_status",
            "operator_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    operator_id = Column(Integer, ForeignKey("operators.id", ondelete="CASCADE"), nullable=False)
    window_id = Column(Integer, ForeignKey("windows.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(16), nullable=False)
    started_at = Column(
        TIMESTAMP(timezone=False),
        nullable=False,
        server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Irkutsk')"),
    )
    ended_at = Column(TIMESTAMP(timezone=False), nullable=True)


def record_operator_status(
    db: Session,
    operator_id: int,
    window_id: int | None,
    new_status: str,
):
    """Close the current status period and open a new one when state changes."""
    normalized_status = new_status.lower()
    if normalized_status not in {"online", "break", "offline"}:
        raise ValueError(f"Unsupported operator status: {new_status}")

    # Serialize transitions for one operator, including the first inserted row.
    db.execute(
        text("SELECT pg_advisory_xact_lock(:operator_id)"),
        {"operator_id": operator_id},
    )
    current_period = (
        db.query(OperatorStatusPeriod)
        .filter(
            OperatorStatusPeriod.operator_id == operator_id,
            OperatorStatusPeriod.ended_at.is_(None),
        )
        .with_for_update()
        .first()
    )

    if (
        current_period
        and current_period.status == normalized_status
        and current_period.window_id == window_id
    ):
        return current_period

    if current_period:
        current_period.ended_at = func.timezone("Asia/Irkutsk", func.current_timestamp())

    new_period = OperatorStatusPeriod(
        operator_id=operator_id,
        window_id=window_id,
        status=normalized_status,
        started_at=func.timezone("Asia/Irkutsk", func.current_timestamp()),
    )
    db.add(new_period)
    db.flush()
    return new_period


class Admin(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True, index=True)
    login = Column(String, unique=True, index=True)
    password = Column(String)
    status = Column(String)


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    session_id = Column(String, primary_key=True) 
    admin_id = Column(Integer, ForeignKey("admins.id"), unique=True, index=True) 
    created_at = Column(TIMESTAMP, default=datetime.now)
    last_seen = Column(TIMESTAMP, default=datetime.now)
    is_expirable = Column(Integer, default=1)


class WindowService(Base):
    __tablename__ = "window_services"
    window_id = Column(Integer, ForeignKey("windows.id"), primary_key=True)
    service_id = Column(Integer, ForeignKey("services.id"), primary_key=True)
    priority = Column(Integer, default=1)


class SystemSettings(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True, default=1)
    print_ticket = Column(String, default="true")
    show_print_badge = Column(String, default="false")
    ticket_print_scale_percent = Column(Integer, default=94)
    ticket_notice_duration_printed_seconds = Column(Integer, default=7)
    ticket_notice_duration_unprinted_seconds = Column(Integer, default=45)
    ticket_notice_printed_text = Column(String, default="Ваш номер: <number>")
    ticket_notice_unprinted_text = Column(String, default="Пожалуйста, запомните свой номер:\n<number>")
    default_operator_status = Column(String, default="online")
    active_ticket_on_operator_logout = Column(String, default="return_to_queue")
    hide_services_without_online_operators = Column(String, default="true")
    queue_mode = Column(String, default="priority_fifo")

    call_message_template = Column(
        String,
        default="Талон <number> подойдите к окну <window>"
    )
    board_ticket_template = Column(
        String,
        default="Билет <number> -> Окно <window>"
    )
    board_ticker_text = Column(String(500), default="")
    board_ticker_messages = Column(String(4000), default="")
    cancel_reason_options = Column(String(4000), default="")
    defer_reason_options = Column(String(4000), default="")


class QueueModePeriod(Base):
    __tablename__ = "queue_mode_periods"
    __table_args__ = (
        CheckConstraint(
            "queue_mode IN ('priority_fifo', 'dynamic_operator_distribution')",
            name="ck_queue_mode_periods_mode",
        ),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="ck_queue_mode_periods_dates",
        ),
        Index("ix_queue_mode_periods_started_at", "started_at"),
        Index(
            "uq_queue_mode_current_period",
            "current_period_key",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    queue_mode = Column(String(40), nullable=False)
    started_at = Column(
        TIMESTAMP(timezone=False),
        nullable=False,
        server_default=text("(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Irkutsk')"),
    )
    ended_at = Column(TIMESTAMP(timezone=False), nullable=True)
    current_period_key = Column(Integer, nullable=False, default=1, server_default=text("1"))


def record_queue_mode(db: Session, new_mode: str):
    """Close the current queue-mode period and open one when the mode changes."""
    if new_mode not in {"priority_fifo", "dynamic_operator_distribution"}:
        raise ValueError(f"Unsupported queue mode: {new_mode}")

    db.execute(text("SELECT pg_advisory_xact_lock(71756575655)"))
    current_period = (
        db.query(QueueModePeriod)
        .filter(QueueModePeriod.ended_at.is_(None))
        .with_for_update()
        .first()
    )
    if current_period and current_period.queue_mode == new_mode:
        return current_period

    now = func.timezone("Asia/Irkutsk", func.current_timestamp())
    if current_period:
        current_period.ended_at = now

    new_period = QueueModePeriod(queue_mode=new_mode, started_at=now)
    db.add(new_period)
    db.flush()
    return new_period
