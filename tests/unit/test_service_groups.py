from types import SimpleNamespace

from app.routers.services import build_terminal_service_groups


def test_build_terminal_service_groups_splits_grouped_and_ungrouped_services():
    groups = [
        SimpleNamespace(id=2, name="Second", display_order=0),
        SimpleNamespace(id=1, name="First", display_order=1),
        SimpleNamespace(id=3, name="Empty", display_order=2),
    ]
    services = [
        SimpleNamespace(
            id=10,
            name="Grouped",
            display_order=0,
            service_group_id=2,
            status="active",
            is_archived=0,
            last_window_id=None,
            operator_choice_enabled=0,
            visible_on_terminal=1,
        ),
        SimpleNamespace(
            id=11,
            name="Ungrouped",
            display_order=1,
            service_group_id=None,
            status="active",
            is_archived=0,
            last_window_id=None,
            operator_choice_enabled=1,
            visible_on_terminal=1,
        ),
        SimpleNamespace(
            id=12,
            name="Missing group",
            display_order=2,
            service_group_id=99,
            status="inactive",
            is_archived=0,
            last_window_id=None,
            operator_choice_enabled=0,
            visible_on_terminal=1,
        ),
    ]

    result = build_terminal_service_groups(groups, services)

    assert [group["id"] for group in result["groups"]] == [2]
    assert result["groups"][0]["services"][0]["id"] == 10
    assert [service["id"] for service in result["ungrouped_services"]] == [11, 12]
