import pytest

from app.services.settings import _bool_to_str, _str_to_bool


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
