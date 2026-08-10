from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services import documentation


@pytest.fixture()
def docs_root(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    monkeypatch.setattr(documentation, "DOCS_ROOT", root)
    return root


def test_default_documents_are_created_for_both_roles(docs_root):
    assert documentation.list_documents("admin")[0]["path"] == "index.md"
    assert documentation.list_documents("operator")[0]["path"] == "index.md"


def test_document_lifecycle_and_revision_conflict(docs_root):
    created = documentation.create_document("admin", "setup/start.md")
    saved = documentation.save_document("admin", created["path"], "# Начало\n\nТекст", created["revision"])

    assert documentation.read_document("admin", "setup/start.md")["content"] == "# Начало\n\nТекст"
    with pytest.raises(HTTPException) as error:
        documentation.save_document("admin", "setup/start.md", "Старая версия", created["revision"])
    assert error.value.status_code == 409

    renamed = documentation.rename_document("admin", saved["path"], "setup/intro.md")
    assert renamed["path"] == "setup/intro.md"
    documentation.delete_document("admin", "setup/intro.md")
    assert not (docs_root / "admin" / "setup" / "intro.md").exists()


@pytest.mark.parametrize("path", ["../secret.md", "folder/../../secret.md", "C:/secret.md"])
def test_document_paths_cannot_escape_scope(docs_root, path):
    with pytest.raises(HTTPException) as error:
        documentation.create_document("admin", path)
    assert error.value.status_code == 400


def test_only_markdown_documents_are_allowed(docs_root):
    with pytest.raises(HTTPException) as error:
        documentation.create_document("admin", "payload.html")
    assert error.value.status_code == 400


def test_operator_and_admin_documents_are_isolated(docs_root):
    documentation.save_document("operator", "index.md", "# Только оператор", None)
    admin = documentation.read_document("admin", "index.md")
    operator = documentation.read_document("operator", "index.md")
    assert admin["content"] != operator["content"]


def test_frontend_exposes_editor_only_to_admin():
    root = Path(__file__).resolve().parents[2]
    admin_source = (root / "queue/js/admin/views/docs.view.js").read_text(encoding="utf-8")
    operator_source = (root / "queue/js/operator-docs.js").read_text(encoding="utf-8")
    assert 'method: "PUT"' in admin_source
    assert 'method: "PUT"' not in operator_source
    assert "openOperatorDocumentation" in operator_source
