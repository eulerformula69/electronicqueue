"""Normalization helpers for portable Grafana dashboard exports."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path


DASHBOARD_UID = "queue-statistics"
DASHBOARD_TITLE = "Статистика очереди"
DATASOURCE_UID = "queue-postgres"
DATASOURCE_TYPE = "grafana-postgresql-datasource"

_POSTGRES_TYPES = {"postgres", DATASOURCE_TYPE}
_PROJECT_DATASOURCE_NAMES = {"queue postgresql", "queue postgres", DATASOURCE_UID}
_LEGACY_DATASOURCE_UIDS = {"cffzz1xb8ay9sa", "bfjh7wvbqibcwd"}
_SPECIAL_DATASOURCES = {"-- grafana --", "grafana", "mixed", "dashboard"}
_UNSTABLE_FIELDS = {"iteration", "meta", "folderId", "folderUid", "overwrite"}


def _looks_like_postgres_name(value: str) -> bool:
    normalized = value.strip().lower()
    return "postgresql" in normalized or "postgres" in normalized


def _discover_postgres_uids(value, discovered):
    if isinstance(value, dict):
        datasource = value.get("datasource")
        if isinstance(datasource, dict):
            datasource_type = str(datasource.get("type", "")).strip().lower()
            name = str(datasource.get("name", ""))
            if datasource_type in _POSTGRES_TYPES or _looks_like_postgres_name(name):
                uid = datasource.get("uid")
                if isinstance(uid, str) and uid:
                    discovered.add(uid)
        for item in value.values():
            _discover_postgres_uids(item, discovered)
    elif isinstance(value, list):
        for item in value:
            _discover_postgres_uids(item, discovered)


def _normalized_datasource(value, postgres_uids):
    if isinstance(value, str):
        identifier = value.strip().lower()
        if identifier in _SPECIAL_DATASOURCES:
            return value
        if (
            identifier in _PROJECT_DATASOURCE_NAMES
            or value in _LEGACY_DATASOURCE_UIDS
            or value in postgres_uids
            or _looks_like_postgres_name(value)
        ):
            return {"type": DATASOURCE_TYPE, "uid": DATASOURCE_UID}
        return value

    if not isinstance(value, dict):
        return value

    datasource_type = str(value.get("type", "")).strip().lower()
    uid = str(value.get("uid", "")).strip()
    name = str(value.get("name", "")).strip().lower()
    if datasource_type in _SPECIAL_DATASOURCES or uid.lower() in _SPECIAL_DATASOURCES:
        return value
    if (
        datasource_type in _POSTGRES_TYPES
        or uid in _LEGACY_DATASOURCE_UIDS
        or uid in postgres_uids
        or uid == DATASOURCE_UID
        or name in _PROJECT_DATASOURCE_NAMES
    ):
        return {"type": DATASOURCE_TYPE, "uid": DATASOURCE_UID}
    return value


def _normalize_nested(value, postgres_uids):
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key == "datasource":
                value[key] = _normalized_datasource(item, postgres_uids)
            else:
                _normalize_nested(item, postgres_uids)
    elif isinstance(value, list):
        for item in value:
            _normalize_nested(item, postgres_uids)


def _normalize_template_queries(dashboard):
    templating = dashboard.get("templating")
    if not isinstance(templating, dict):
        return
    variables = templating.get("list")
    if not isinstance(variables, list):
        return
    for variable in variables:
        if not isinstance(variable, dict) or variable.get("type") != "query":
            continue
        query = variable.get("query")
        if not isinstance(query, dict):
            continue
        sql = query.get("rawSql") or query.get("query")
        if isinstance(sql, str):
            variable["query"] = sql
            variable["definition"] = sql


def normalize_dashboard_export(payload: dict) -> dict:
    """Return a portable dashboard without mutating the supplied export."""
    if not isinstance(payload, dict):
        raise TypeError("Экспорт Grafana должен быть JSON-объектом")

    wrapped_dashboard = payload.get("dashboard")
    source = wrapped_dashboard if isinstance(wrapped_dashboard, dict) else payload
    dashboard = copy.deepcopy(source)

    for field in _UNSTABLE_FIELDS:
        dashboard.pop(field, None)
    dashboard["id"] = None
    dashboard["uid"] = DASHBOARD_UID
    dashboard["title"] = DASHBOARD_TITLE
    dashboard["version"] = 1

    postgres_uids = set(_LEGACY_DATASOURCE_UIDS)
    _discover_postgres_uids(dashboard, postgres_uids)
    _normalize_nested(dashboard, postgres_uids)
    _normalize_template_queries(dashboard)
    return dashboard


def write_dashboard_json(path: Path, payload: dict) -> None:
    """Atomically write a normalized dashboard as stable UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
