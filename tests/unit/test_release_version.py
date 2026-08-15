from pathlib import Path

from fastapi.testclient import TestClient

from app.application import app
from app.release_middleware import _version_html


ROOT = Path(__file__).resolve().parents[2]


def test_every_html_page_loads_version_checker():
    for html_path in (ROOT / "queue").glob("*.html"):
        source = html_path.read_text(encoding="utf-8")
        assert '/queue/js/app-version.js' in source, html_path.name


def test_version_checker_offers_one_click_reload():
    source = (ROOT / "queue" / "js" / "app-version.js").read_text(encoding="utf-8")

    assert 'button.textContent = "Обновить"' in source
    assert 'window.location.reload()' in source
    assert 'meta[name="app-version"]' in source
    assert 'cache: "no-store"' in source


def test_html_assets_receive_release_version():
    source = b'<head><link href="/queue/css/base.css"></head><script src="/queue/js/app.js"></script>'

    result = _version_html(source, "abc123")

    assert b'<meta name="app-version" content="abc123">' in result
    assert b'/queue/css/base.css?v=abc123' in result
    assert b'/queue/js/app.js?v=abc123' in result


def test_version_endpoint_and_html_are_not_cached():
    client = TestClient(app)

    version_response = client.get("/system/version")
    html_response = client.get("/queue/login.html")

    assert version_response.headers["cache-control"] == "no-store"
    assert html_response.headers["cache-control"] == "no-store"
    assert '<meta name="app-version"' in html_response.text
    assert '/queue/js/app-version.js?v=' in html_response.text
