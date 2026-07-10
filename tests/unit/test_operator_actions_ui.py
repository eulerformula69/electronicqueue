from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_operator_defer_replaces_return_to_queue_in_primary_actions():
    source = read_text("queue/operator.html")

    primary_actions = source.split('<div class="button-group primary-actions">', 1)[1]
    primary_actions = primary_actions.split('<div class="button-group secondary-actions', 1)[0]
    actions_area = source.split('<div class="button-group secondary-actions', 1)[1]
    actions_area = actions_area.split('<div class="bottom-controls">', 1)[0]
    before_more_menu = actions_area.split('<div id="operator-more-menu"', 1)[0]

    assert "ВЕРНУТЬ ОБРАТНО В ОЧЕРЕДЬ" not in before_more_menu
    assert "ОТМЕНИТЬ ВЫЗОВ" not in primary_actions
    assert "return-to-queue-btn" not in primary_actions
    assert "defer-ticket-btn" in actions_area
    assert "showDeferReasonPopup()" in actions_area
    assert "ВЫЗВАТЬ ПО НОМЕРУ" in actions_area
    assert 'onclick="cancelCurrent()"' in actions_area


def test_operator_has_four_clickable_queue_columns():
    source = read_text("queue/operator.html")

    assert 'data-section="waiting"' in source
    assert 'data-section="deferred"' in source
    assert 'data-section="cancelled"' in source
    assert 'data-section="served"' in source
    assert "selectQueueSection('waiting')" in source
    assert "selectQueueSection('deferred')" in source
    assert "selectQueueSection('cancelled')" in source
    assert "selectQueueSection('served')" in source


def test_operator_return_to_queue_is_not_primary_but_legacy_function_stays():
    source = read_text("queue/js/operator.js")

    assert "returnCurrentToQueue" in source
    assert "showRepeatedReturnWarning()" in source
    assert "confirmReturnCurrentToQueue" in source


def test_operator_finish_warning_can_route_to_cancel_or_finish():
    source = read_text("queue/js/operator.js")

    assert "SHORT_SERVICE_WARNING_MS = 5 * 60 * 1000" in source
    assert "RECALL_FINISH_WARNING_COUNT = 2" in source
    assert "showFinishWarningPopup()" in source
    assert 'text: "Завершить"' in source
    assert 'text: "Клиент не явился"' in source
    assert "finishCurrent({ skipWarning: true })" in source
    assert 'cancelCurrent({ reason: "no_show" })' in source


def test_operator_actions_keep_existing_ticket_endpoints():
    source = read_text("queue/js/operator.js")

    assert "/tickets/finish" in source
    assert "/tickets/cancel" in source
    assert "/tickets/defer" in source
    assert "/tickets/deferred/${ticketId}/resume" in source
    assert "/tickets/return-to-queue" in source
    assert "/tickets/recall" in source
    assert "/tickets/redirect" in source
    assert "/tickets/redirect-to-window" in source


def test_operator_auto_call_uses_global_settings_without_local_toggle():
    html = read_text("queue/operator.html")
    source = read_text("queue/js/operator.js")

    assert 'id="auto-call-toggle"' not in html
    assert "autoCallActive" not in source
    assert "localStorage.getItem('autoCallActive')" not in source
    assert "localStorage.setItem('autoCallActive'" not in source
    assert "operatorSettings" in source
    assert "auto_call_enabled" in source
    assert "auto_call_delay_seconds" in source
    assert "startAutoCallAfterFinish();" in source
    assert "runAutoCallNow" in source
    assert "await callNext({ autoCall: true });" in source
    assert "loadQueue({ checkNewTickets: false })" in source
    assert "Очередь пуста" in source
    assert "auto-call-info-block" in html


def test_operator_redirect_loads_services_hidden_on_terminal():
    source = read_text("queue/js/operator.js")

    assert "`${CONFIG.API_URL}/services/?include_hidden=true`" in source


def test_operator_redirect_uses_single_modal_button():
    html = read_text("queue/operator.html")
    js = read_text("queue/js/operator.js")
    css = read_text("queue/css/operator.css")

    assert 'id="redirect-btn"' in html
    assert 'onclick="showRedirectModal()"' in html
    assert "ПЕРЕНАПРАВИТЬ НА УСЛУГУ" not in html
    assert "ПЕРЕНАПРАВИТЬ НА РАБОЧЕЕ МЕСТО" not in html
    assert 'id="redirect-panel"' not in html
    assert 'id="redirect-to-window-panel"' not in html

    assert "function showRedirectModal" in js
    assert "redirect-modal-overlay" in js
    assert "Поиск услуги" in js
    assert "Кому" in js
    assert "Любому доступному оператору" in js
    assert "Конкретному оператору" not in js
    assert "Поиск оператора или окна" not in js
    assert "На услугу" not in js
    assert "К оператору/окну" not in js
    assert "new_service_id: Number(redirectState.serviceId)" in js
    assert "modal.appendChild(createRedirectRecipientSection());" in js
    assert 'redirectState.mode' not in js
    assert "createRedirectWindowSection" not in js
    assert "DEFAULT_REDIRECT_RECIPIENT_LABEL" in js
    assert 'service.status !== "active"' in js
    assert 'windowItem.status !== "online"' in js
    assert "redirectWindowSupportsService(windowItem, redirectState.serviceId)" in js
    assert "? \"/tickets/redirect-to-window\"" in js
    assert ": \"/tickets/redirect\"" in js
    assert "payload.window_id = Number(redirectState.windowId);" in js
    assert 'confirmButton.textContent = redirectState.isSubmitting ? "Перенаправляем..." : "Перенаправить";' in js
    assert 'confirmButton.className = "btn-primary redirect-confirm-button";' in js
    assert "serviceList.replaceWith(nextServiceList)" in js
    assert "windowList.replaceWith(nextWindowList)" in js
    assert "width: min(950px, 100%)" in css
    assert ".redirect-confirm-button" in css
    assert ".redirect-mode-group" not in css
    assert "width: 100%" in css


def test_operator_redirect_by_service_does_not_require_window():
    js = read_text("queue/js/operator.js")

    assert "if (!redirectState.windowId) return true;" in js
    assert "const endpoint = redirectState.windowId" in js
    assert "? \"/tickets/redirect-to-window\"" in js
    assert ": \"/tickets/redirect\"" in js
    assert "if (redirectState.windowId) {" in js
    assert "payload.window_id = Number(redirectState.windowId);" in js


def test_operator_redirect_to_window_requires_compatible_service():
    js = read_text("queue/js/operator.js")

    assert "const windowItem = getRedirectWindow(redirectState.windowId);" in js
    assert "return Boolean(windowItem && redirectWindowSupportsService(windowItem, redirectState.serviceId));" in js
    assert "redirectState.serviceId &&" in js
    assert "!redirectWindowSupportsService(windowItem, redirectState.serviceId)" in js
    assert "redirectState.serviceId = null;" in js


def test_operator_redirect_services_filter_by_selected_online_window():
    js = read_text("queue/js/operator.js")

    assert "const selectedWindow = getRedirectWindow(redirectState.windowId);" in js
    assert 'selectedWindow.status === "online"' in js
    assert "? selectedWindow.services" in js
    assert ": allServices" in js
    assert "if (Number(service.is_archived) === 1) return false;" in js
    assert 'if (service.status !== "active") return false;' in js
    assert "redirectState.serviceId &&" in js
    assert "!redirectWindowSupportsService(windowItem, redirectState.serviceId)" in js


def test_operator_redirect_recipient_search_replaces_mode_buttons():
    js = read_text("queue/js/operator.js")

    assert 'input.placeholder = DEFAULT_REDIRECT_RECIPIENT_LABEL;' in js
    assert "redirectState.windowQuery || DEFAULT_REDIRECT_RECIPIENT_LABEL" in js
    assert "redirectWindowMatchesQuery(getRedirectWindow(redirectState.windowId), redirectState.windowQuery)" in js
    assert "if (!query && !redirectState.windowId) return [];" in js
    assert "redirectState.windowQuery = getRedirectWindowTitle(windowItem);" in js
    assert "getRedirectWindowActiveServices(windowItem)" in js


def test_operator_defer_requires_reason_options():
    source = read_text("queue/js/operator.js")
    queue_sections_source = read_text("queue/js/operator-queue-sections.js")

    assert "OperatorQueueSections.deferReasons" in source
    assert "loadOperatorReasonSettings" in source
    assert "setReasonOptions" in queue_sections_source
    assert 'value: "Заполняет документы"' in queue_sections_source
    assert 'value: "Оплачивает"' in queue_sections_source
    assert 'value: "Пошёл за документами"' in queue_sections_source
    assert 'value: "Нет нужного документа"' in queue_sections_source
    assert 'value: "Другое"' in queue_sections_source
    assert "withOtherComment(reason.value)" in source
    assert "Выберите причину отложения" in source


def test_operator_cancel_requires_reason_options():
    source = read_text("queue/js/operator.js")
    queue_sections_source = read_text("queue/js/operator-queue-sections.js")

    assert "showCancelReasonPopup()" in source
    assert "OperatorQueueSections.cancelReasons" in source
    assert 'body: JSON.stringify({ reason: options.reason })' in source
    assert 'value: "Клиент не явился"' in queue_sections_source
    assert 'value: "Отказался от услуги"' in queue_sections_source
    assert 'value: "Ошибочный талон"' in queue_sections_source
    assert 'value: "Нет нужного документа"' in queue_sections_source
    assert 'value: "Другое"' in queue_sections_source
    assert "withOtherComment(reason.value)" in source
