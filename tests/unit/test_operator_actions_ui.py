from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_operator_defer_replaces_return_to_queue_in_primary_actions():
    source = read_text("queue/operator.html")

    primary_actions = source.split('<div class="button-group primary-actions">', 1)[1]
    primary_actions = primary_actions.split('<div class="button-group secondary-actions">', 1)[0]
    secondary_actions = source.split('<div class="button-group secondary-actions">', 1)[1]
    secondary_actions = secondary_actions.split('<div id="redirect-panel"', 1)[0]
    more_menu = secondary_actions.split('<div id="operator-more-menu"', 1)[1]
    before_more_menu = secondary_actions.split('<div id="operator-more-menu"', 1)[0]

    assert "ВЫЗВАТЬ ПО НОМЕРУ" not in before_more_menu
    assert "ВЕРНУТЬ ОБРАТНО В ОЧЕРЕДЬ" not in before_more_menu
    assert "ОТМЕНИТЬ ВЫЗОВ" not in primary_actions
    assert "return-to-queue-btn" not in primary_actions
    assert "defer-ticket-btn" in primary_actions
    assert "showDeferReasonPopup()" in primary_actions
    assert "ВЫЗВАТЬ ПО НОМЕРУ" in more_menu
    assert "ОТМЕНИТЬ ВЫЗОВ" in more_menu
    assert 'onclick="cancelCurrent()"' in more_menu


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


def test_operator_defer_requires_reason_options():
    source = read_text("queue/js/operator.js")
    queue_sections_source = read_text("queue/js/operator-queue-sections.js")

    assert "OperatorQueueSections.deferReasons" in source
    assert 'value: "fills_documents"' in queue_sections_source
    assert 'value: "pays"' in queue_sections_source
    assert 'value: "went_for_documents"' in queue_sections_source
    assert 'value: "missing_document"' in queue_sections_source
    assert 'value: "other"' in queue_sections_source
    assert "Выберите причину отложения" in source


def test_operator_cancel_requires_reason_options():
    source = read_text("queue/js/operator.js")
    queue_sections_source = read_text("queue/js/operator-queue-sections.js")

    assert "showCancelReasonPopup()" in source
    assert "OperatorQueueSections.cancelReasons" in source
    assert 'body: JSON.stringify({ reason: options.reason })' in source
    assert 'value: "no_show"' in queue_sections_source
    assert 'value: "refused_service"' in queue_sections_source
    assert 'value: "wrong_ticket"' in queue_sections_source
    assert 'value: "missing_document"' in queue_sections_source
    assert 'value: "other"' in queue_sections_source
