from operator import eq

from app.models import Operator, Service, Ticket, Window, WindowService
from app.schemas import CallNextRequest
from app.services.operators import resolve_operator_auto_call_enabled
from app.services.tickets import claim_next_ticket


class ClaimQuery:
    def __init__(self, db, model, rows):
        self.db = db
        self.model = model
        self.rows = list(rows)
        self.allowed_service_ids = None

    def join(self, *args):
        return self

    def filter(self, *conditions):
        for condition in conditions:
            field = condition.left.name
            value = getattr(condition.right, "value", None)
            owner = {
                "tickets": Ticket,
                "windows": Window,
                "window_services": WindowService,
            }[condition.left.table.name]
            if owner is WindowService and field == "window_id":
                self.allowed_service_ids = {
                    item.service_id
                    for item in self.db.window_services
                    if item.window_id == value
                }
                continue
            if owner is not self.model:
                continue
            if condition.operator is eq:
                self.rows = [row for row in self.rows if getattr(row, field) == value]
            elif condition.operator.__name__ == "is_":
                self.rows = [row for row in self.rows if getattr(row, field) is value]
            else:
                raise AssertionError(f"Unsupported condition: {condition.operator}")
        return self

    def order_by(self, *args):
        if self.model is Ticket:
            priorities = {
                item.service_id: item.priority for item in self.db.window_services
            }
            self.rows.sort(
                key=lambda item: (
                    priorities.get(item.service_id, 999),
                    item.queue_entered_at or item.created_at,
                    item.id,
                )
            )
        return self

    def with_for_update(self, **kwargs):
        self.db.locks.append(kwargs)
        return self

    def first(self):
        rows = self.rows
        if self.allowed_service_ids is not None:
            rows = [row for row in rows if row.service_id in self.allowed_service_ids]
        return rows[0] if rows else None


class ClaimDb:
    def __init__(self, *, tickets, windows, window_services):
        self.tickets = tickets
        self.windows = windows
        self.window_services = window_services
        self.locks = []
        self.flush_count = 0

    def query(self, model):
        rows = {
            Ticket: self.tickets,
            Window: self.windows,
        }[model]
        return ClaimQuery(self, model, rows)

    def flush(self):
        self.flush_count += 1


def make_db(ticket_services=(1, 1), window_services=((10, 1), (20, 1))):
    tickets = [
        Ticket(id=index, number=index, service_id=service_id, status="waiting")
        for index, service_id in enumerate(ticket_services, start=1)
    ]
    windows = [Window(id=10, name="10", status="online"), Window(id=20, name="20", status="online")]
    services = [
        WindowService(window_id=window_id, service_id=service_id, priority=1)
        for window_id, service_id in window_services
    ]
    return ClaimDb(tickets=tickets, windows=windows, window_services=services)


def claim(db, operator):
    return claim_next_ticket(
        db,
        operator=operator,
        queue_mode="priority_fifo",
        require_online=True,
    )


def test_two_auto_call_operators_claim_different_tickets():
    db = make_db()

    first, first_claimed = claim(db, Operator(id=1, window_id=10))
    second, second_claimed = claim(db, Operator(id=2, window_id=20))

    assert first_claimed and second_claimed
    assert first.id != second.id
    assert (first.operator_id, first.window_id) == (1, 10)
    assert (second.operator_id, second.window_id) == (2, 20)
    assert {ticket.status for ticket in db.tickets} == {"called"}


def test_one_ticket_is_claimed_by_only_one_operator_and_leaves_queue():
    db = make_db(ticket_services=(1,))

    first, first_claimed = claim(db, Operator(id=1, window_id=10))
    second, second_claimed = claim(db, Operator(id=2, window_id=20))

    assert first_claimed is True
    assert first.status == "called"
    assert second is None
    assert second_claimed is False
    assert not [ticket for ticket in db.tickets if ticket.status == "waiting"]


def test_auto_call_respects_workplace_services():
    db = make_db(ticket_services=(2, 1), window_services=((10, 1),))

    ticket, claimed = claim(db, Operator(id=1, window_id=10))

    assert claimed is True
    assert ticket.service_id == 1
    assert db.tickets[0].status == "waiting"


def test_claim_uses_postgresql_skip_locked_and_flushes_before_commit():
    db = make_db(ticket_services=(1,))

    ticket, claimed = claim(db, Operator(id=1, window_id=10))

    assert claimed and ticket
    assert {"skip_locked": True, "of": Ticket} in db.locks
    assert db.flush_count == 1


def test_empty_queue_returns_once_without_creating_a_ticket():
    db = make_db(ticket_services=())

    ticket, claimed = claim(db, Operator(id=1, window_id=10))

    assert ticket is None
    assert claimed is False
    assert db.flush_count == 0
    assert len(db.locks) == 3


def test_offline_operator_cannot_auto_claim():
    db = make_db(ticket_services=(1,))
    db.windows[0].status = "offline"

    ticket, claimed = claim(db, Operator(id=1, window_id=10))

    assert ticket is None
    assert claimed is False
    assert db.tickets[0].status == "waiting"


def test_operator_auto_call_mode_overrides_global_default():
    assert resolve_operator_auto_call_enabled(
        Operator(auto_call_mode="enabled"), False
    ) is True
    assert resolve_operator_auto_call_enabled(
        Operator(auto_call_mode="disabled"), True
    ) is False
    assert resolve_operator_auto_call_enabled(
        Operator(auto_call_mode="default"), True
    ) is True


def test_call_next_request_distinguishes_manual_and_auto_call():
    assert CallNextRequest().auto_call is False
    assert CallNextRequest(auto_call=True).auto_call is True
