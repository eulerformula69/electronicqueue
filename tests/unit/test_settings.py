from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import SystemSettings, Window
from app.routers import admin as admin_router
from app.schemas import PublicSettingsResponse, SystemSettingsResponse, SystemSettingsUpdate
from app.services.settings import (
    _bool_to_str,
    _str_to_bool,
    build_board_ticker_text,
    normalize_ticket_reason,
    normalize_ticket_reason_options,
    normalize_board_ticker_messages,
    serialize_board_ticker_messages,
    serialize_ticket_reason_options,
)
from app.services.settings import get_system_settings_dict

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("off", False),
        ("", False),
    ],
)
def test_str_to_bool(value, expected):
    assert _str_to_bool(value) is expected


def test_str_to_bool_none_uses_default():
    assert _str_to_bool(None, default=True) is True
    assert _str_to_bool(None, default=False) is False


def test_bool_to_str():
    assert _bool_to_str(True) == "true"
    assert _bool_to_str(False) == "false"


def _schema_fields(schema):
    return getattr(schema, "model_fields", getattr(schema, "__fields__", {}))


def test_board_ticker_text_is_in_settings_schemas():
    for schema in (SystemSettingsUpdate, SystemSettingsResponse, PublicSettingsResponse):
        assert "board_ticker_text" in _schema_fields(schema)


def test_board_ticker_messages_are_in_admin_settings_schemas():
    for schema in (SystemSettingsUpdate, SystemSettingsResponse):
        assert "board_ticker_messages" in _schema_fields(schema)

    assert "board_ticker_messages" not in _schema_fields(PublicSettingsResponse)


def test_ticket_reason_options_are_in_settings_schemas():
    for schema in (SystemSettingsUpdate, SystemSettingsResponse, PublicSettingsResponse):
        assert "cancel_reason_options" in _schema_fields(schema)
        assert "defer_reason_options" in _schema_fields(schema)


def test_ticket_print_scale_percent_is_in_settings_schemas():
    for schema in (SystemSettingsUpdate, SystemSettingsResponse, PublicSettingsResponse):
        assert "ticket_print_scale_percent" in _schema_fields(schema)


def test_auto_call_settings_are_in_settings_schemas():
    for schema in (SystemSettingsUpdate, SystemSettingsResponse, PublicSettingsResponse):
        assert "auto_call_enabled" in _schema_fields(schema)
        assert "auto_call_delay_seconds" in _schema_fields(schema)


def test_redirect_status_settings_are_exposed_to_operator_ui():
    for schema in (SystemSettingsUpdate, SystemSettingsResponse, PublicSettingsResponse):
        assert "redirect_allow_break" in _schema_fields(schema)
        assert "redirect_allow_offline" in _schema_fields(schema)


def test_system_settings_dict_includes_board_ticker_text():
    engine = create_engine("sqlite:///:memory:")
    SystemSettings.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        settings = SystemSettings(
            id=1,
            board_ticker_messages=serialize_board_ticker_messages([
                {"text": "Прием документов до 18:00", "enabled": True},
                {"text": "Обед", "enabled": False},
                {"text": "Окно 3 работает", "enabled": True},
            ]),
        )
        db.add(settings)
        db.commit()

        assert get_system_settings_dict(db)["board_ticker_text"] == (
            "Прием документов до 18:00 | Окно 3 работает"
        )
    finally:
        db.close()


def test_system_settings_dict_includes_ticket_print_scale_percent():
    engine = create_engine("sqlite:///:memory:")
    SystemSettings.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        settings = SystemSettings(id=1, ticket_print_scale_percent=120)
        db.add(settings)
        db.commit()

        assert get_system_settings_dict(db)["ticket_print_scale_percent"] == 120
    finally:
        db.close()


def test_system_settings_dict_clamps_ticket_print_scale_percent():
    engine = create_engine("sqlite:///:memory:")
    SystemSettings.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        db.add(SystemSettings(id=1, ticket_print_scale_percent=300))
        db.commit()

        assert get_system_settings_dict(db)["ticket_print_scale_percent"] == 150
    finally:
        db.close()


def test_system_settings_dict_includes_auto_call_settings():
    engine = create_engine("sqlite:///:memory:")
    SystemSettings.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        db.add(SystemSettings(id=1, auto_call_enabled="true", auto_call_delay_seconds=30))
        db.commit()

        result = get_system_settings_dict(db)

        assert result["auto_call_enabled"] is True
        assert result["auto_call_delay_seconds"] == 30
    finally:
        db.close()


def test_system_settings_dict_clamps_auto_call_delay_seconds():
    engine = create_engine("sqlite:///:memory:")
    SystemSettings.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        db.add(SystemSettings(id=1, auto_call_delay_seconds=999))
        db.commit()

        assert get_system_settings_dict(db)["auto_call_delay_seconds"] == 600
    finally:
        db.close()


def test_system_settings_dict_defaults_empty_board_ticker_text():
    engine = create_engine("sqlite:///:memory:")
    SystemSettings.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        settings = SystemSettings(id=1, board_ticker_text=None)
        db.add(settings)
        db.commit()

        assert get_system_settings_dict(db)["board_ticker_text"] == ""
    finally:
        db.close()


def test_system_settings_dict_migrates_legacy_board_ticker_text_to_messages():
    engine = create_engine("sqlite:///:memory:")
    SystemSettings.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        settings = SystemSettings(id=1, board_ticker_text="Первое\nВторое")
        db.add(settings)
        db.commit()

        result = get_system_settings_dict(db)

        assert result["board_ticker_text"] == "Первое | Второе"
        assert result["board_ticker_messages"] == [
            {"text": "Первое", "enabled": True},
            {"text": "Второе", "enabled": True},
        ]
    finally:
        db.close()


def test_board_ticker_text_uses_only_enabled_messages():
    messages = normalize_board_ticker_messages([
        {"text": "Первое", "enabled": True},
        {"text": "Второе", "enabled": False},
        {"text": "Третье", "enabled": True},
    ])

    assert build_board_ticker_text(messages) == "Первое | Третье"


def test_ticket_reason_options_normalize_and_serialize():
    options = normalize_ticket_reason_options([
        {"text": "  Клиент ушёл  ", "enabled": True},
        {"text": "Скрытая", "enabled": False},
        "",
        {"text": "x" * 140, "enabled": True},
    ])

    assert options == [
        {"text": "Клиент ушёл", "enabled": True},
        {"text": "Скрытая", "enabled": False},
        {"text": "x" * 120, "enabled": True},
    ]
    assert serialize_ticket_reason_options(options) == (
        '[{"text":"Клиент ушёл","enabled":true},'
        '{"text":"Скрытая","enabled":false},'
        f'{{"text":"{"x" * 120}","enabled":true}}]'
    )


def test_normalize_ticket_reason_formats_other_comment():
    assert normalize_ticket_reason("other") == "Другое"
    assert normalize_ticket_reason("other: клиент ушёл") == "Другое: клиент ушёл"
    assert normalize_ticket_reason("Другое:  клиент ушёл  ") == "Другое: клиент ушёл"
    assert normalize_ticket_reason("Другое:   ") == "Другое"


def test_admin_routes_expose_board_ticker_text_in_public_settings():
    source = (ROOT / "app" / "routers" / "admin.py").read_text(encoding="utf-8")

    assert "settings.board_ticker_messages = serialize_board_ticker_messages(board_ticker_messages)" in source
    assert "settings.board_ticker_text = build_board_ticker_text(board_ticker_messages)" in source
    assert "settings.ticket_print_scale_percent = data.ticket_print_scale_percent" in source
    assert '"ticket_print_scale_percent": settings["ticket_print_scale_percent"]' in source
    assert '"board_ticker_text": settings["board_ticker_text"]' in source
    assert '"auto_call_enabled": settings["auto_call_enabled"]' in source
    assert '"auto_call_delay_seconds": settings["auto_call_delay_seconds"]' in source
    assert '"cancel_reason_options": [' in source
    assert '"defer_reason_options": [' in source


@pytest.mark.asyncio
async def test_admin_settings_saves_ticket_reason_options(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    SystemSettings.__table__.create(engine)
    Window.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    broadcasts = []
    board_updates = []

    async def fake_broadcast(message):
        broadcasts.append(message)

    async def fake_broadcast_board():
        board_updates.append(True)

    monkeypatch.setattr(admin_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(admin_router.manager, "broadcast", fake_broadcast)
    monkeypatch.setattr(admin_router, "broadcast_board", fake_broadcast_board)
    monkeypatch.setattr(admin_router, "update_services_status_for_window", lambda db, window_id: None)

    payload = SystemSettingsUpdate(
        print_ticket=True,
        show_print_badge=True,
        ticket_print_scale_percent=94,
        ticket_notice_duration_printed_seconds=7,
        ticket_notice_duration_unprinted_seconds=45,
        ticket_notice_printed_text="Ваш номер: <number>",
        ticket_notice_unprinted_text="Пожалуйста, запомните номер: <number>",
        default_operator_status="online",
        active_ticket_on_operator_logout="return_to_queue",
        hide_services_without_online_operators=True,
        call_message_template="Талон <number> окно <window>",
        board_ticket_template="Билет <number> окно <window>",
        board_ticker_text="",
        board_ticker_messages=[],
        cancel_reason_options=[
            {"text": "Клиент ушёл", "enabled": True},
            {"text": "Ошибка", "enabled": False},
        ],
        defer_reason_options=[
            {"text": "Ждёт документы", "enabled": True},
        ],
        auto_call_enabled=True,
        auto_call_delay_seconds=15,
    )

    try:
        result = await admin_router.update_admin_settings(payload, admin=object())

        assert result["cancel_reason_options"] == [
            {"text": "Клиент ушёл", "enabled": True},
            {"text": "Ошибка", "enabled": False},
        ]
        assert result["defer_reason_options"] == [
            {"text": "Ждёт документы", "enabled": True},
        ]
        assert result["auto_call_enabled"] is True
        assert result["auto_call_delay_seconds"] == 15
        settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
        assert "Клиент ушёл" in settings.cancel_reason_options
        assert "Ждёт документы" in settings.defer_reason_options
        assert settings.auto_call_enabled == "true"
        assert settings.auto_call_delay_seconds == 15
        assert {"type": "settings_updated"} in broadcasts
        assert board_updates == [True]
    finally:
        db.close()
