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
    assert "(t.finished_at - t.called_at) < INTERVAL '1.5 minutes'" in raw_sql
    assert "operator_aliases AS" not in raw_sql
    assert "COALESCE(NULLIF(btrim(o.name), ''), 'Неизвестно')" in raw_sql
    assert "GROUP BY COALESCE(NULLIF(btrim(o.name), ''), 'Неизвестно')" in raw_sql
    assert "ORDER BY suspicious_count DESC, avg_duration_seconds ASC" in raw_sql


def test_redirected_stages_are_not_problematic_unfinished():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    panel = _find_panel(dashboard["panels"], "Проблемные незавершения")

    assert panel is not None
    assert panel["type"] == "stat"

    raw_sql = panel["targets"][0]["rawSql"]
    assert "t.completion_reason IS DISTINCT FROM 'redirected'" in raw_sql
    assert "t.completion_reason = 'redirected'" not in raw_sql


def test_redirected_stages_are_reported_as_operator_outcome():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    panel = _find_panel(dashboard["panels"], "Итог вызовов к операторам")

    assert panel is not None
    assert panel["type"] == "table"

    raw_sql = panel["targets"][0]["rawSql"]
    assert "t.completion_reason = 'redirected'" in raw_sql
    assert "Этап перенаправлен" in raw_sql
    assert 'count(*) AS "Этапов"' in raw_sql


def test_operator_efficiency_is_stage_based():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    panel = _find_panel(dashboard["panels"], "Закрытие этапов, %")

    assert panel is not None
    assert panel["type"] == "stat"

    raw_sql = panel["targets"][0]["rawSql"]
    assert "closed_stage_percent" in raw_sql
    assert "t.completion_reason IN ('completed', 'redirected')" in raw_sql
    assert "NULLIF(count(*), 0)" in raw_sql


def test_operator_day_status_timeline_panel():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    panel = _find_panel(dashboard["panels"], "Статусы сотрудников за рабочий день")

    assert panel is not None
    assert panel["type"] == "state-timeline"
    assert panel["targets"][0]["format"] == "time_series"

    raw_sql = panel["targets"][0]["rawSql"]
    assert "operator_status_periods osp" in raw_sql
    assert "workdays AS" in raw_sql
    assert "day::timestamp + time '08:00'" in raw_sql
    assert "day::timestamp + time '17:00'" in raw_sql
    assert "GREATEST(osp.started_at, workdays.day_start)" in raw_sql
    assert "LEAST(COALESCE(osp.ended_at, workdays.day_end), workdays.day_end)" in raw_sql
    assert "osp.started_at < workdays.day_end" in raw_sql
    assert "COALESCE(osp.ended_at, workdays.day_end) > workdays.day_start" in raw_sql
    assert "osp.operator_id::text IN (${operator_id:sqlstring})" in raw_sql
    assert "event_time AT TIME ZONE 'Asia/Irkutsk' AS \"time\"" in raw_sql
    assert "WHEN 'offline' THEN 0" in raw_sql
    assert "WHEN 'online' THEN 1" in raw_sql
    assert "WHEN 'break' THEN 2" in raw_sql


def test_dashboard_percentile_and_operator_filter_are_variable_based():
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    variables = {item["name"]: item for item in dashboard["templating"]["list"]}

    assert "percentile" in variables
    assert variables["operator_id"]["query"].startswith(
        "SELECT COALESCE(NULLIF(btrim(name), ''), 'Неизвестно') AS __text"
    )

    raw_sql_values = []

    def collect_raw_sql(panels):
        for panel in panels:
            raw_sql_values.extend(
                target["rawSql"]
                for target in panel.get("targets", [])
                if "rawSql" in target
            )
            collect_raw_sql(panel.get("panels", []))

    collect_raw_sql(dashboard["panels"])
    raw_sql = "\n".join(raw_sql_values)

    assert "percentile_cont(0.9)" not in raw_sql
    assert "percentile_cont((${percentile:raw}::numeric / 100.0))" in raw_sql
    assert "${operator_name:sqlstring}" not in raw_sql
    assert "o.name IN" not in raw_sql
    assert "o.id::text IN (${operator_id:sqlstring})" in raw_sql
    assert "operator_aliases AS" not in raw_sql
    assert "'Сотрудник ' || row_number()" not in raw_sql
