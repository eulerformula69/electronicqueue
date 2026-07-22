"""One-time scheduling support for the close-day command."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


LOCAL_TIMEZONE = ZoneInfo("Asia/Irkutsk")
INPUT_FORMAT = "%d.%m.%Y %H:%M"
AT_FORMAT = "%Y%m%d%H%M"


@dataclass(frozen=True)
class ScheduledCloseDay:
    run_at: datetime
    job_output: str


def build_close_day_command(
    python_executable: str, script_path: str | Path
) -> str:
    """Build a shell-safe command that reruns this script immediately."""
    python_path = Path(python_executable).resolve()
    close_day_path = Path(script_path).resolve()
    return (
        f"{shlex.quote(str(python_path))} "
        f"{shlex.quote(str(close_day_path))} --run-now"
    )


def parse_run_at(value: str, *, now: datetime | None = None) -> datetime:
    """Parse a local date and time and reject moments that have already passed."""
    try:
        run_at = datetime.strptime(value.strip(), INPUT_FORMAT).replace(
            tzinfo=LOCAL_TIMEZONE
        )
    except ValueError as error:
        raise ValueError(
            "используйте формат ДД.ММ.ГГГГ ЧЧ:ММ, например 24.07.2026 18:00"
        ) from error

    current_time = now or datetime.now(LOCAL_TIMEZONE)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=LOCAL_TIMEZONE)
    if run_at <= current_time.astimezone(LOCAL_TIMEZONE):
        raise ValueError("дата и время должны быть в будущем")
    return run_at


def collect_interactive_schedule(input_func=input) -> list[str]:
    """Read one or more dates until the user submits an empty line."""
    print("Введите даты закрытия по одной строке в формате ДД.ММ.ГГГГ ЧЧ:ММ.")
    print("Пустая строка завершит ввод.")
    values: list[str] = []
    while True:
        value = input_func(f"Закрытие #{len(values) + 1}: ").strip()
        if not value:
            break
        values.append(value)
    if not values:
        raise ValueError("не указано ни одной даты закрытия")
    return values


def schedule_close_days(
    values: list[str],
    *,
    command: str,
    now: datetime | None = None,
) -> list[ScheduledCloseDay]:
    """Create persistent one-time jobs through the system `at` service."""
    if shutil.which("at") is None:
        raise RuntimeError(
            "служба одноразовых заданий не установлена; повторно запустите deploy/install.sh"
        )

    run_times = [parse_run_at(value, now=now) for value in values]
    environment = os.environ.copy()
    environment["TZ"] = "Asia/Irkutsk"
    scheduled: list[ScheduledCloseDay] = []
    for run_at in run_times:
        process = subprocess.run(
            ["at", "-t", run_at.strftime(AT_FORMAT)],
            input=f"{command}\n",
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        if process.returncode != 0:
            details = (process.stderr or process.stdout).strip()
            raise RuntimeError(details or "не удалось создать одноразовое задание")
        scheduled.append(
            ScheduledCloseDay(
                run_at=run_at,
                job_output=(process.stderr or process.stdout).strip(),
            )
        )
    return scheduled
