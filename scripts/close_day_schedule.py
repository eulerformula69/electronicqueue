"""One-time scheduling support for the close-day command."""

from __future__ import annotations

import os
import re
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
WINDOWS_DATE_TOKENS = re.compile(r"yyyy|yy|MM|M|dd|d")


@dataclass(frozen=True)
class ScheduledCloseDay:
    run_at: datetime
    job_output: str


def build_close_day_command(
    python_executable: str,
    script_path: str | Path,
    *,
    platform: str = os.name,
) -> str:
    """Build a shell-safe command that reruns this script immediately."""
    python_path = Path(python_executable).resolve()
    close_day_path = Path(script_path).resolve()
    arguments = [str(python_path), str(close_day_path), "--run-now"]
    if platform == "nt":
        return subprocess.list2cmdline(arguments)
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


def get_windows_short_date_pattern() -> str:
    """Read the current user's date format used by Windows Task Scheduler."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\International") as key:
            pattern, _ = winreg.QueryValueEx(key, "sShortDate")
    except (ImportError, OSError) as error:
        raise RuntimeError(
            "не удалось определить региональный формат даты Windows"
        ) from error
    return pattern


def format_windows_start_date(run_at: datetime, pattern: str) -> str:
    """Format a date according to the current Windows short-date pattern."""
    values = {
        "yyyy": f"{run_at.year:04d}",
        "yy": f"{run_at.year % 100:02d}",
        "MM": f"{run_at.month:02d}",
        "M": str(run_at.month),
        "dd": f"{run_at.day:02d}",
        "d": str(run_at.day),
    }
    return WINDOWS_DATE_TOKENS.sub(lambda match: values[match.group()], pattern)


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
    platform: str = os.name,
    windows_date_pattern: str | None = None,
) -> list[ScheduledCloseDay]:
    """Create persistent one-time jobs through the operating-system scheduler."""
    scheduler = "schtasks.exe" if platform == "nt" else "at"
    if shutil.which(scheduler) is None:
        if platform == "nt":
            raise RuntimeError("Планировщик заданий Windows (schtasks.exe) недоступен")
        raise RuntimeError(
            "служба одноразовых заданий не установлена; повторно запустите deploy/install.sh"
        )

    run_times = [parse_run_at(value, now=now) for value in values]
    if platform == "nt" and windows_date_pattern is None:
        windows_date_pattern = get_windows_short_date_pattern()
    environment = os.environ.copy()
    environment["TZ"] = "Asia/Irkutsk"
    scheduled: list[ScheduledCloseDay] = []
    for index, run_at in enumerate(run_times, start=1):
        if platform == "nt":
            task_name = (
                f"Qronion-CloseDay-{run_at:%Y%m%d-%H%M}-{index}"
            )
            process = subprocess.run(
                [
                    "schtasks.exe",
                    "/Create",
                    "/TN",
                    task_name,
                    "/TR",
                    command,
                    "/SC",
                    "ONCE",
                    "/SD",
                    format_windows_start_date(run_at, windows_date_pattern),
                    "/ST",
                    run_at.strftime("%H:%M"),
                    "/Z",
                    "/F",
                ],
                text=True,
                encoding="oem",
                errors="replace",
                capture_output=True,
                check=False,
            )
        else:
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
