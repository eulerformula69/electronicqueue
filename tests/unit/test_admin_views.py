from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_operator_admin_table_shows_visible_id_and_keeps_internal_id():
    source = _read("queue/js/admin/views/operators.view.js")

    assert "<td>${operator.id}</td>" in source
    assert 'ctx.ui.sortHeader("ID", "id", sortState)' in source
    assert '["id", "name", "login", "window"].includes(parsed.key)' in source
    assert "id: operator.id" in source
    assert "operators.find(item => item.id === Number(button.dataset.id))" in source


def test_window_admin_table_shows_visible_id_and_keeps_internal_id():
    source = _read("queue/js/admin/views/windows.view.js")

    assert "<td>${windowItem.id}</td>" in source
    assert 'ctx.ui.sortHeader("ID", "id", sortState)' in source
    assert '["id", "name", "status", "services"].includes(parsed.key)' in source
    assert "id: windowItem.id" in source
    assert "windows.find(item => item.id === Number(button.dataset.id))" in source


def test_window_admin_loads_hidden_terminal_services_for_internal_assignment():
    modern_source = _read("queue/js/admin/views/windows.view.js")
    legacy_source = _read("queue/js/admin/windows.js")
    map_source = _read("queue/js/admin/map.js")

    assert 'ctx.api.request("/services/?include_hidden=true")' in modern_source
    assert "fetchJSON(`${API}/services/?include_hidden=true`)" in legacy_source
    assert "fetchJSON(`${API}/services/?limit=500&include_hidden=true`)" in map_source


def test_service_admin_list_hides_visible_id_but_keeps_data_id():
    source = _read("queue/js/admin/views/services.view.js")

    assert "admin-service-id" not in source
    assert 'data-service-id="${service.id}"' in source
    assert "draggedServiceId = Number(item.dataset.serviceId)" in source


def test_admin_views_use_click_sorting_with_direction_toggle():
    for path in [
        "queue/js/admin/views/operators.view.js",
        "queue/js/admin/views/windows.view.js",
    ]:
        source = _read(path)
        assert 'button.dataset.action === "sort"' in source
        assert 'sortState.key === key && sortState.direction === "asc" ? "desc" : "asc"' in source


def test_admin_views_persist_sort_state():
    for path, key in [
        ("queue/js/admin/views/operators.view.js", "admin.operators.sort"),
        ("queue/js/admin/views/windows.view.js", "admin.windows.sort"),
    ]:
        source = _read(path)
        assert f'const sortStorageKey = "{key}"' in source
        assert "sortState = loadSortState(sortState)" in source
        assert "saveSortState(sortState)" in source
        assert "localStorage.setItem(sortStorageKey, JSON.stringify(state))" in source


def test_table_helper_renders_sortable_headers():
    source = _read("queue/js/admin/ui.js")

    assert "export function sortHeader" in source
    assert "headers.map(renderTableHeader)" in source
    assert 'data-action="sort"' in source
    assert 'data-sort-key="${escapeHtml(header.sortKey)}"' in source


def test_sorting_layout_has_stable_column_widths():
    source = _read("queue/css/admin/shell.css") + _read("queue/css/admin/services.css")

    assert "table-layout: fixed;" in source
    assert "flex: 0 0 12px;" in source
    assert "grid-template-columns: 34px minmax(260px, 1fr) 120px 150px 120px 140px;" in source


def test_settings_view_renders_and_saves_board_ticker_text():
    source = _read("queue/js/admin/views/settings.view.js")

    assert "setting-board-ticker-text" in source
    assert "board_ticker_text" in source
    assert "board_ticker_messages" in source
    assert "collectBoardTickerMessages" in source
    assert "add-ticker-message" in source
    assert "delete-ticker-message" in source
    assert "data.board_ticker_text.trim()" in source


def test_settings_view_renders_and_saves_ticket_reason_options():
    modern_source = _read("queue/js/admin/views/settings.view.js")
    legacy_source = _read("queue/js/admin/settings.js")

    for source in (modern_source, legacy_source):
        assert "Причины отмены" in source
        assert "Причины отложения" in source
        assert "cancel_reason_options" in source
        assert "defer_reason_options" in source
        assert "collectReasonOptions" in source
        assert "deleteReasonOption" in source or "delete-reason-option" in source


def test_settings_view_renders_and_saves_ticket_print_scale_percent():
    source = _read("queue/js/admin/views/settings.view.js")
    terminal = _read("queue/js/terminal.js")
    terminal_html = _read("queue/terminal.html")

    assert "ticket_print_scale_percent" in source
    assert "validTicketPrintScale" in source
    assert "normalizeTicketPrintScalePercent" in terminal
    assert "--ticket-print-scale" in terminal
    assert "scale(var(--ticket-print-scale, 0.94))" in terminal_html


def test_services_view_uses_drag_order_without_click_sorting():
    source = _read("queue/js/admin/views/services.view.js")

    assert "admin.services.sort" not in source
    assert 'data-action="sort"' not in source
    assert "sortServices(" not in source
    assert "services.filter(service => service.service_group_id === group.id)" in source
    assert "persistDraggedOrder" in source


def test_settings_view_does_not_show_template_hint_caption():
    source = _read("queue/js/admin/views/settings.view.js")

    assert "В шаблонах должны остаться параметры" not in source


def test_board_status_moves_with_ticker_offset():
    board_css = _read("queue/css/board.css")
    media_css = _read("queue/css/board-media/main.css")
    lite_css = _read("queue/css/board-media/lite.css")

    assert "--board-ticker-offset: 0px;" in board_css
    assert "bottom: calc(10px + var(--board-ticker-offset));" in board_css
    assert "--board-ticker-offset: 0px;" in media_css
    assert "bottom: calc(10px + var(--board-ticker-offset));" in media_css
    assert "--lite-ticker-height: 76px;" in lite_css
    assert "--board-ticker-offset: var(--lite-ticker-height);" in lite_css


def test_lite_media_board_reserves_ticker_height():
    lite_css = _read("queue/css/board-media/lite.css")

    assert 'grid-template-areas:\n        "header"\n        "main"\n        "ticker";' in lite_css
    assert "grid-template-rows: var(--lite-header-height) minmax(0, 1fr) var(--lite-ticker-height);" in lite_css
    assert "position: fixed !important;" in lite_css
    assert "bottom: 0 !important;" in lite_css
    assert "grid-template-columns: minmax(0, 1fr) minmax(0, var(--lite-board-width)) !important;" in lite_css
    assert "grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) !important;" in lite_css
    assert "overflow: hidden;" in lite_css


def test_lite_media_pages_have_explicit_layout_zones_and_ticker():
    lite_source = _read("queue/board-media-lite.html")
    lite2_source = _read("queue/board-media-lite2.html")

    for source in (lite_source, lite2_source):
        assert '<header class="lite-header">' in source
        assert '<main class="board-wrapper">' in source
        assert '<div id="board-ticker" class="board-ticker" hidden>' in source
        assert '<video id="media-video" autoplay playsinline></video>' in source
        assert '<div class="waiting-board" id="waiting-board"></div>' in source
        assert '<div class="board" id="board"></div>' in source


def test_lite2_board_uses_smaller_page_sizes():
    source = _read("queue/board-media-lite2.html")

    assert '<body class="board-media-page lite-version lite2-version">' in source
    assert "calledPageSize: 8," in source
    assert "waitingPageSize: 8," in source


def test_global_credentials_move_with_ticker_offset():
    source = _read("queue/css/base.css")

    assert "body::after" in source
    assert "bottom: calc(12px + var(--board-ticker-offset, 0px));" in source
    assert "bottom: calc(10px + var(--board-ticker-offset, 0px));" in source


def test_board_ticker_uses_seamless_repeated_segment():
    script = _read("queue/js/board-ticker.js")
    board_css = _read("queue/css/board.css")
    media_css = _read("queue/css/board-media/main.css")

    assert "repeatCount = Math.max(2, Math.ceil(tickerWidth / setWidth) + 2)" in script
    assert "track.style.setProperty(\"--board-ticker-distance\"" in script
    assert "track.style.setProperty(\"--board-ticker-duration\"" in script
    assert "i < repeatCount * 2" in script
    assert "var(--board-ticker-distance" in board_css
    assert "translateX(-50%)" not in board_css
    assert "var(--board-ticker-distance" in media_css
    assert "translateX(-50%)" not in media_css


def test_board_ticker_splits_multiline_messages_with_separator():
    script = _read("queue/js/board-ticker.js")
    board_css = _read("queue/css/board.css")
    media_css = _read("queue/css/board-media/main.css")

    assert ".split(/\\s+\\|\\s+|\\r?\\n/)" in script
    assert ".filter(Boolean)" in script
    assert "tickerMessages = parseTickerMessages(value)" in script
    assert "appendMessageSet(track, messages" in script
    assert "board-ticker__text--segment-end" in script
    assert 'content: "|";' in board_css
    assert 'content: "";' not in board_css
    assert "margin-left: 72px;" in board_css
    assert 'content: "|";' in media_css
    assert 'content: "";' not in media_css
