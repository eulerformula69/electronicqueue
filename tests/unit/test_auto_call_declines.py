from app.models import AutoCallDecline
from app.schemas import AutoCallDeclineCreate


def test_auto_call_decline_has_journal_model_and_validated_reason():
    decline = AutoCallDecline(operator_id=3, window_id=7, reason="documents")
    payload = AutoCallDeclineCreate(reason="documents")

    assert decline.operator_id == 3
    assert decline.window_id == 7
    assert decline.reason == payload.reason


def test_auto_call_decline_endpoint_is_registered():
    from app.application import app

    paths = {route.path for route in app.routes}
    assert "/operator/auto-call-declines" in paths
