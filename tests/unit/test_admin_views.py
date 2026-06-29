from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_operator_admin_table_hides_visible_id_but_keeps_internal_id():
    source = _read("queue/js/admin/views/operators.view.js")

    assert "<td>${operator.id}</td>" not in source
    assert '"ID"' not in source
    assert "id: operator.id" in source
    assert "operators.find(item => item.id === Number(button.dataset.id))" in source


def test_window_admin_table_hides_visible_id_but_keeps_internal_id():
    source = _read("queue/js/admin/views/windows.view.js")

    assert "<td>${windowItem.id}</td>" not in source
    assert '"ID"' not in source
    assert "id: windowItem.id" in source
    assert "windows.find(item => item.id === Number(button.dataset.id))" in source


def test_service_admin_list_hides_visible_id_but_keeps_data_id():
    source = _read("queue/js/admin/views/services.view.js")

    assert "admin-service-id" not in source
    assert 'data-service-id="${service.id}"' in source
    assert "draggedServiceId = Number(item.dataset.serviceId)" in source


def test_admin_views_use_click_sorting_with_direction_toggle():
    for path in [
        "queue/js/admin/views/services.view.js",
        "queue/js/admin/views/operators.view.js",
        "queue/js/admin/views/windows.view.js",
    ]:
        source = _read(path)
        assert 'button.dataset.action === "sort"' in source
        assert 'sortState.key === key && sortState.direction === "asc" ? "desc" : "asc"' in source


def test_table_helper_renders_sortable_headers():
    source = _read("queue/js/admin/ui.js")

    assert "export function sortHeader" in source
    assert "headers.map(renderTableHeader)" in source
    assert 'data-action="sort"' in source
    assert 'data-sort-key="${escapeHtml(header.sortKey)}"' in source
