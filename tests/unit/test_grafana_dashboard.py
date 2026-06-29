import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = PROJECT_ROOT / "data" / "statistics.json"


def _find_panel(panels, title):
    for panel in panels:
        if panel.get("title") == title:
            return panel
        nested_panel = _find_panel(panel.get("panels", []), title)
        if nested_panel:
            return nested_panel
    return None


def test_suspicious_operator_completions_panel():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    panel = _find_panel(dashboard["panels"], "Подозрительные завершения операторов")

    assert panel is not None
    assert panel["type"] == "table"

    raw_sql = panel["targets"][0]["rawSql"]
    expected_columns = [
        "operator_id",
        "operator_name",
        "window_id",
        "window_name",
        "suspicious_count",
        "avg_duration_seconds",
        "min_duration_seconds",
        "max_duration_seconds",
    ]
    for column in expected_columns:
        assert f" AS {column}" in raw_sql

    assert "t.status = 'finished'" in raw_sql
    assert "t.completion_reason = 'completed'" in raw_sql
    assert "t.called_at IS NOT NULL" in raw_sql
    assert "t.finished_at IS NOT NULL" in raw_sql
    assert "$__timeFrom()" in raw_sql
    assert "$__timeTo()" in raw_sql
    assert "(t.finished_at - t.called_at) < INTERVAL '5 minutes'" in raw_sql
    assert "GROUP BY t.operator_id, o.name, t.window_id, w.name" in raw_sql
    assert "ORDER BY suspicious_count DESC, avg_duration_seconds ASC" in raw_sql
