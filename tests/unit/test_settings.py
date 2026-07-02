from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import SystemSettings
from app.schemas import PublicSettingsResponse, SystemSettingsResponse, SystemSettingsUpdate
from app.services.settings import (
    _bool_to_str,
    _str_to_bool,
    build_board_ticker_text,
    normalize_board_ticker_messages,
    serialize_board_ticker_messages,
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


def test_ticket_print_scale_percent_is_in_settings_schemas():
    for schema in (SystemSettingsUpdate, SystemSettingsResponse, PublicSettingsResponse):
        assert "ticket_print_scale_percent" in _schema_fields(schema)


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


def test_admin_routes_expose_board_ticker_text_in_public_settings():
    source = (ROOT / "app" / "routers" / "admin.py").read_text(encoding="utf-8")

    assert "settings.board_ticker_messages = serialize_board_ticker_messages(board_ticker_messages)" in source
    assert "settings.board_ticker_text = build_board_ticker_text(board_ticker_messages)" in source
    assert "settings.ticket_print_scale_percent = data.ticket_print_scale_percent" in source
    assert '"ticket_print_scale_percent": settings["ticket_print_scale_percent"]' in source
    assert '"board_ticker_text": settings["board_ticker_text"]' in source
