import pytest

from app.services.tickets import render_ticket_template


def test_render_ticket_template_replaces_placeholders():
    result = render_ticket_template(
        "Талон <number> подойдите к окну <window>",
        42,
        "Окно 3",
    )
    assert result == "Талон 42 подойдите к окну Окно 3"


def test_render_ticket_template_none_template():
    assert render_ticket_template(None, 1, "A") == ""


def test_render_ticket_template_empty_string():
    assert render_ticket_template("", 7, "W") == ""


def test_render_ticket_template_multiline():
    template = "Пожалуйста, запомните свой номер:\n<number>"
    assert render_ticket_template(template, 99, "X") == (
        "Пожалуйста, запомните свой номер:\n99"
    )
