from app.models import WindowService
from app.routers import windows as windows_router


class FakeWindowServiceQuery:
    def __init__(self, rows):
        self.rows = rows

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.closed = False

    def query(self, model):
        assert model is WindowService
        return FakeWindowServiceQuery(self.rows)

    def close(self):
        self.closed = True


def test_get_window_services_returns_serializable_dto_and_closes_session(monkeypatch):
    db = FakeDb(
        [
            WindowService(window_id=6, service_id=1, priority=None),
            WindowService(window_id=6, service_id=2, priority=3),
        ]
    )
    monkeypatch.setattr(windows_router, "SessionLocal", lambda: db)

    result = windows_router.get_window_services(6, admin=object())

    assert [item.dict() for item in result] == [
        {"window_id": 6, "service_id": 1, "priority": 1},
        {"window_id": 6, "service_id": 2, "priority": 3},
    ]
    assert db.closed
