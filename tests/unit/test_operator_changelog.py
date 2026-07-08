import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_operator_page_loads_operator_changelog_only():
    operator_html = read_text("queue/operator.html")

    assert '<script src="/queue/js/operator-changelog.js"></script>' in operator_html

    other_pages = [
        "queue/board.html",
        "queue/board-media.html",
        "queue/terminal.html",
        "queue/admin.html",
    ]
    for page in other_pages:
        assert "operator-changelog.js" not in read_text(page)


def test_operator_changelog_is_independent_from_system_version():
    source = read_text("queue/js/operator-changelog.js")

    assert 'CHANGELOG_URL = "/queue/changelog/operator.json"' in source
    assert 'STORAGE_KEY = "operatorChangelogVersion"' in source
    assert "/system/version" not in source
    assert "operatorAppVersion" not in source
    assert 'cache: "no-store"' in source
    assert "localStorage.setItem(STORAGE_KEY, version)" in source
    assert "localStorage.getItem(STORAGE_KEY) === version" in source


def test_operator_changelog_fails_silent_on_bad_or_missing_file():
    source = read_text("queue/js/operator-changelog.js")

    assert "if (!response.ok) return;" in source
    assert "if (!isValidChangelog(data)) return;" in source
    assert "console.debug(\"Operator changelog load error:\", error)" in source


def test_operator_changelog_popup_is_centered_over_dimmed_operator_page():
    source = read_text("queue/css/operator.css")

    assert "body.operator-page .operator-changelog-overlay" in source
    assert "background: rgba(0, 0, 0, 0.62);" in source
    assert "body.operator-page .operator-changelog-modal" in source
    assert "text-align: center;" in source
    assert "justify-content: center;" in source


def test_operator_changelog_json_has_operator_facing_russian_text():
    data = json.loads(read_text("queue/changelog/operator.json"))

    assert isinstance(data["version"], str)
    assert data["version"].strip()
    assert data["title"] == "Что изменилось для оператора"
    assert data["changes"]
    assert all(isinstance(item, str) and item.strip() for item in data["changes"])
    assert any("оператор" in item.lower() for item in data["changes"])


def test_operator_changelog_policy_exists():
    policy = read_text("CHANGELOG_POLICY.md")

    assert "`queue/changelog/operator.json` обновляется только" in policy
    assert "Не обновлять operator changelog для изменений табло, терминала, админки, статистики" in policy
    assert "увеличить `version`" in policy
    assert "Писать только то, что важно оператору" in policy
