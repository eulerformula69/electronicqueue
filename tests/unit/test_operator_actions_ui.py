from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_operator_uses_shared_feedback_instead_of_browser_dialogs():
    html = read_text("queue/operator.html")
    source = read_text("queue/js/operator.js")
    feedback = read_text("queue/js/operator-feedback.js")

    assert '<script src="/queue/js/operator-feedback.js"></script>' in html
    assert "OperatorFeedback.toast" in source
    assert "OperatorFeedback.confirm" in source
    assert "OperatorFeedback.input" in source
    assert "OperatorFeedback.acknowledge" in source
    assert "alert(" not in source
    assert "window.confirm(" not in source
    assert "prompt(" not in source
    assert "global.OperatorFeedback" in feedback


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
    assert "confirmReturnCurrentToQueue" in source


def test_redirect_limit_is_checked_before_modal_opens():
    source = read_text("queue/js/operator.js")
    show_modal = source.split("async function showRedirectModal()", 1)[1].split(
        "function renderRedirectModal()", 1
    )[0]

    assert "max_ticket_redirects: 3" in source
    assert "currentTicketRedirectCount" in show_modal
    assert "operatorSettings.max_ticket_redirects" in show_modal
    assert "Этот талон больше нельзя перенаправлять" in show_modal
    assert show_modal.index("Этот талон больше нельзя перенаправлять") < show_modal.index(
        "renderRedirectModal();"
    )


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
    assert "/tickets/${sourceSection}/${ticketId}/resume" in source
    assert 'selectedSection === "deferred" || selectedSection === "cancelled"' in Path(
        "queue/js/operator-queue-sections.js"
    ).read_text(encoding="utf-8")
    assert "/tickets/return-to-queue" in source
    assert "/tickets/recall" in source
    assert "/tickets/redirect" in source
    assert "/tickets/redirect-to-window" in source


def test_cancel_and_defer_keep_waiting_section_selected():
    source = Path("queue/js/operator.js").read_text(encoding="utf-8")

    cancel_action = source.split("async function cancelCurrent", 1)[1].split(
        "function showCancelReasonPopup", 1
    )[0]
    defer_action = source.split("async function deferCurrentTicket", 1)[1].split(
        "async function resumeTicket", 1
    )[0]

    assert 'OperatorQueueSections.select("waiting");' in cancel_action
    assert 'OperatorQueueSections.select("waiting");' in defer_action
    assert "selectDeferred" not in source


def test_idle_ticket_text_is_smaller_without_shifting_client_label():
    styles = Path("queue/css/operator.css").read_text(encoding="utf-8")

    ticket_number = styles.split("body.operator-page .ticket-number{", 1)[1].split("}", 1)[0]
    idle_ticket_number = styles.split(
        "body.operator-page .current-ticket-actions-inactive .ticket-number{", 1
    )[1].split("}", 1)[0]

    assert "min-height: 112px" in ticket_number
    assert "display: flex" in ticket_number
    assert "align-items: center" in ticket_number
    assert "font-size: 2rem" in idle_ticket_number


def test_operator_auto_call_uses_global_settings_without_local_toggle():
    html = read_text("queue/operator.html")
    source = read_text("queue/js/operator.js")
    display_zone = html.split('<section class="glass-card display-zone">', 1)[1]
    display_zone = display_zone.split('<section class="glass-card">', 1)[0]
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
    assert "body: JSON.stringify({ auto_call: options.autoCall === true })" in source
    assert "loadQueue({ checkNewTickets: false })" in source
    assert "Очередь пуста" in source
    assert "auto-call-info-block" in display_zone
    assert "auto-call-countdown" not in display_zone
    assert "auto-call-actions" not in display_zone


def test_operator_auto_call_schedules_after_workspace_freeing_actions():
    source = read_text("queue/js/operator.js")

    assert "function scheduleAutoCallAfterWorkspaceFreed()" in source
    assert source.count("scheduleAutoCallAfterWorkspaceFreed();") >= 5

    for marker in [
        "async function finishCurrent",
        "async function confirmRedirectFromModal",
        "async function cancelCurrent",
        "async function deferCurrentTicket",
        "async function confirmReturnCurrentToQueue",
    ]:
        section = source.split(marker, 1)[1].split("async function ", 1)[0]
        assert "scheduleAutoCallAfterWorkspaceFreed();" in section


def test_operator_auto_call_resumes_when_operator_goes_online():
    source = read_text("queue/js/operator.js")
    change_status_section = source.split("async function changeWindowStatus", 1)[1]
    change_status_section = change_status_section.split("function updateStatusButtons", 1)[0]

    assert 'result.status === "break" ? "Перерыв" : "Оператор офлайн"' in change_status_section
    assert "scheduleAutoCallAfterWorkspaceFreed();" in change_status_section
    assert "На паузе: оператор не в статусе Online" not in source


def test_operator_uses_one_direct_status_toggle():
    html = read_text("queue/operator.html")
    source = read_text("queue/js/operator.js")
    ui_state = read_text("queue/js/operator-ui-state.js")

    assert 'id="window-status-toggle"' in html
    assert 'type="checkbox"' in html
    assert 'onchange="toggleWindowStatus(this)"' in html
    assert 'class="window-status-switch-track"' in html
    assert 'id="btn-start"' not in html
    assert 'id="btn-stop"' not in html
    assert 'control.checked ? "online" : "break"' in source
    assert 'statusToggle.checked = currentWindowStatus === "online"' in source
    assert 'statusText.textContent = "Онлайн"' in source
    assert "На линии" not in source
    assert 'if (!changed) updateStatusButtons(currentWindowStatus)' in source
    assert 'statusToggle.disabled = busy' in ui_state


def test_operator_auto_call_starts_when_admin_enables_it_for_free_workspace():
    source = read_text("queue/js/operator.js")
    settings_section = source.split("async function loadOperatorReasonSettings", 1)[1]
    settings_section = settings_section.split("function withOtherComment", 1)[0]

    assert "let autoCallSettingsLoaded = false;" in source
    assert "const wasAutoCallEnabled = operatorSettings.auto_call_enabled;" in settings_section
    assert "autoCallSettingsLoaded &&" in settings_section
    assert "!wasAutoCallEnabled &&" in settings_section
    assert "operatorSettings.auto_call_enabled" in settings_section
    assert "autoCallWasJustEnabled || hadActiveAutoCallTimer" in settings_section
    assert "scheduleAutoCallAfterWorkspaceFreed();" in settings_section


def test_operator_auto_call_stops_for_empty_queue_and_resumes_on_queue_update():
    source = read_text("queue/js/operator.js")
    websocket_section = source.split("function initWebSocket", 1)[1]
    websocket_section = websocket_section.split("function startOperatorPolling", 1)[0]
    refresh_section = source.split("async function refreshQueueAndAutoCall", 1)[1]
    refresh_section = refresh_section.split("function showToast", 1)[0]
    start_section = source.split("function startAutoCallAfterFinish", 1)[1]
    start_section = start_section.split("function scheduleAutoCallAfterWorkspaceFreed", 1)[0]

    assert "let queueHasCallableTickets = null;" in source
    assert "queueHasCallableTickets = Array.isArray(tickets) && tickets.length > 0;" in source
    assert "refreshQueueAndAutoCall();" in websocket_section
    assert 'stopAutoCall("Очередь пуста");' in refresh_section
    assert 'autoCallState === "empty"' in refresh_section
    assert "scheduleAutoCallAfterWorkspaceFreed();" in refresh_section
    assert "if (queueHasCallableTickets === false)" in start_section
    assert 'stopAutoCall("Очередь пуста");' in start_section


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
    assert 'windowItem.status === "break"' in js
    assert 'operatorSettings.redirect_allow_offline' in js
    assert 'selectedWindow?.status === "offline"' in js
    assert "if (!isRedirectWindowAvailable(windowItem)) return false;" in js
    assert "redirectWindowSupportsService(windowItem, redirectState.serviceId)" in js
    assert "? \"/tickets/redirect-to-window\"" in js
    assert ": \"/tickets/redirect\"" in js
    assert "payload.window_id = Number(redirectState.windowId);" in js
    assert 'confirmButton.textContent = redirectState.isSubmitting ? "Перенаправляем..." : "Перенаправить";' in js
    assert 'const confirmUnavailable = !canConfirmRedirect() || redirectState.isSubmitting;' in js
    assert 'confirmUnavailable ? "current-ticket-action-inactive" : ""' in js
    assert "confirmButton.disabled = confirmUnavailable;" in js
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


def test_operator_redirect_services_filter_by_selected_available_window():
    js = read_text("queue/js/operator.js")

    assert "const selectedWindow = getRedirectWindow(redirectState.windowId);" in js
    assert "isRedirectWindowAvailable(selectedWindow)" in js
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


def test_operator_ui_uses_one_state_refresh_for_action_availability():
    html = read_text("queue/operator.html")
    source = read_text("queue/js/operator-ui-state.js")
    css = read_text("queue/css/operator.css")

    assert "function refreshOperatorUiState()" in source
    assert '<script src="/queue/js/operator-ui-state.js"></script>' in html
    assert 'document.querySelectorAll("[data-call-action]")' in source
    assert 'document.querySelectorAll("[data-current-ticket-action]")' in source
    assert "button.disabled = !online || hasTicket || busy" in source
    assert "button.disabled = !online || !hasTicket || busy" in source
    assert 'displayZone.classList.toggle("operator-work-disabled", !online)' in source
    assert "data-call-action" in html
    assert "data-current-ticket-action" in html
    assert ".current-ticket-actions-inactive [data-current-ticket-action]" in css


def test_operator_mutations_share_double_click_guard():
    source = read_text("queue/js/operator.js")
    ui_state = read_text("queue/js/operator-ui-state.js")

    assert "const activeOperatorRequests = new Set();" in ui_state
    assert "function beginOperatorRequest(key)" in ui_state
    assert "if (activeOperatorRequests.size > 0) return false;" in ui_state
    for key in (
        "call-next", "call-specific", "finish", "cancel", "defer",
        "redirect", "return-to-queue", "recall", "resume-deferred",
    ):
        assert f'beginOperatorRequest("{key}")' in source
        assert f'endOperatorRequest("{key}")' in source


def test_operator_page_keeps_simple_auto_call_status_without_prompt_two_controls():
    html = read_text("queue/operator.html")
    source = read_text("queue/js/operator.js")

    assert "auto-call-info-block" in html
    assert "auto-call-status" in html
    assert "auto-call-hint" not in html
    assert "auto-call-countdown" not in html
    assert "auto-call-actions" not in html
    assert "showAutoCallDeclinePopup" not in source
    assert "/operator/auto-call-declines" not in source


def test_auto_call_uses_distinct_break_and_offline_reasons():
    source = read_text("queue/js/operator.js")

    assert 'return isOperatorOnBreak() ? "Перерыв" : "Оператор офлайн";' in source
    assert "Рабочее место занято текущим талоном" in source
    assert "Очередь пуста" in source
    assert "Отключён администратором" in source
    assert 'statusDisplay.textContent = "Включён";' in source
    assert "Автоочередь" not in source
    assert "Отсчёт начнётся после завершения текущего клиента" not in source
    assert "normalizeAutoCallDelay(operatorSettings.auto_call_delay_seconds)" in source
