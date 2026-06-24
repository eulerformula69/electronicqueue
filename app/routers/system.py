import hashlib
import subprocess

from fastapi import APIRouter

from app.config import BASE_DIR


router = APIRouter()


def _get_git_revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=BASE_DIR,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    revision = result.stdout.strip()
    return revision or None


def _get_files_revision() -> str:
    hasher = hashlib.sha256()
    for directory in (BASE_DIR / "app", BASE_DIR / "queue"):
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                stat = path.stat()
                hasher.update(str(path.relative_to(BASE_DIR)).encode("utf-8"))
                hasher.update(str(stat.st_mtime_ns).encode("utf-8"))
                hasher.update(str(stat.st_size).encode("utf-8"))
    return hasher.hexdigest()[:12]


@router.get("/system/version", tags=["System"])
async def get_system_version():
    return {"version": _get_git_revision() or _get_files_revision()}
