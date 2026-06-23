#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_SOURCE = PROJECT_DIR / "data" / "statistics.json"
DASHBOARD_DESTINATION = Path("/var/lib/grafana/dashboards/queue-statistics.json")
OLD_DATASOURCE_UIDS = {"cffzz1xb8ay9sa", "bfjh7wvbqibcwd"}


def replace_datasource_uid(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "uid" and item in OLD_DATASOURCE_UIDS:
                value[key] = "queue-postgres"
            else:
                replace_datasource_uid(item)
    elif isinstance(value, list):
        for item in value:
            replace_datasource_uid(item)


def normalize_template_queries(dashboard):
    for variable in dashboard.get("templating", {}).get("list", []):
        query = variable.get("query")
        if variable.get("type") == "query" and isinstance(query, dict):
            sql = query.get("rawSql") or query.get("query") or variable.get("definition")
            if isinstance(sql, str) and sql.strip():
                variable["query"] = sql.strip()
                variable["definition"] = sql.strip()


def run_optional(command):
    executable = shutil.which(command[0])
    if not executable:
        return

    subprocess.run([executable, *command[1:]], check=False)


def main():
    if not DASHBOARD_SOURCE.exists():
        print(f"Dashboard source not found: {DASHBOARD_SOURCE}", file=sys.stderr)
        return 1

    with DASHBOARD_SOURCE.open(encoding="utf-8") as file:
        dashboard = json.load(file)

    replace_datasource_uid(dashboard)
    normalize_template_queries(dashboard)

    dashboard["id"] = None
    dashboard["uid"] = "queue-statistics"
    dashboard["title"] = "Queue statistics"

    DASHBOARD_DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    with DASHBOARD_DESTINATION.open("w", encoding="utf-8") as file:
        json.dump(dashboard, file, ensure_ascii=False, indent=2)

    run_optional(["chown", "grafana:grafana", str(DASHBOARD_DESTINATION)])
    run_optional(["systemctl", "restart", "grafana-server"])

    print(f"Grafana dashboard synced: {DASHBOARD_DESTINATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
