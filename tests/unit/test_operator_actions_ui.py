from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_operator_return_to_queue_and_cancel_are_swapped():
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
    assert "ВЕРНУТЬ ОБРАТНО В ОЧЕРЕДЬ" in primary_actions
    assert "ВЫЗВАТЬ ПО НОМЕРУ" in more_menu
    assert "ОТМЕНИТЬ ВЫЗОВ" in more_menu
    assert 'onclick="returnCurrentToQueue()"' in primary_actions
    assert 'onclick="cancelCurrent()"' in more_menu


def test_operator_return_to_queue_warns_only_after_first_return():
    source = read_text("queue/js/operator.js")

    assert "operatorReturnedTicketIds" not in source
    assert "rememberReturnedTicket" not in source
    assert "wasTicketReturnedToQueue" not in source
    assert "data.was_returned_before" not in source
    assert "currentTicketReturnedToQueueCount" in source
    assert "const returnedToQueueCount = await getCurrentTicketReturnedToQueueCount();" in source
    assert "if (returnedToQueueCount > 0)" in source
    assert "showRepeatedReturnWarning()" in source
    assert "showOperatorPopup({" in source
    assert 'title: "Вернуть в очередь?"' in source
    assert "Похоже, вы возвращаете в очередь не в первый раз" in source
    assert "Если нужно отменить вызов, перейдите в «Дополнительно» → «Отменить вызов»." in source
    assert 'text: "Вернуть в очередь"' in source
    assert "onClick: confirmReturnCurrentToQueue" in source
    assert 'text: "Отмена"' in source


def test_operator_finish_warning_can_route_to_cancel_or_finish():
    source = read_text("queue/js/operator.js")

    assert "SHORT_SERVICE_WARNING_MS = 5 * 60 * 1000" in source
    assert "RECALL_FINISH_WARNING_COUNT = 2" in source
    assert "showFinishWarningPopup()" in source
    assert 'text: "Завершить"' in source
    assert 'text: "Клиент не явился"' in source
    assert "finishCurrent({ skipWarning: true })" in source
    assert "cancelCurrent({ skipConfirm: true })" in source


def test_operator_actions_keep_existing_ticket_endpoints():
    source = read_text("queue/js/operator.js")

    assert "/tickets/finish" in source
    assert "/tickets/cancel" in source
    assert "/tickets/return-to-queue" in source
    assert "/tickets/recall" in source
    assert "/tickets/redirect" in source
    assert "/tickets/redirect-to-window" in source
