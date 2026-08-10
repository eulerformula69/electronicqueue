import hashlib
import os
import re
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import BASE_DIR


DOCS_ROOT = BASE_DIR / "data" / "docs"
SCOPES = {"admin", "operator"}
MAX_DOCUMENT_BYTES = 1_000_000
MAX_IMAGE_BYTES = 8_000_000
IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def ensure_docs() -> None:
    defaults = {
        "admin": "# Инструкция администратора\n\nЗдесь можно описать работу с системой.\n",
        "operator": "# Инструкция оператора\n\nЗдесь можно описать рабочий процесс оператора.\n",
    }
    for scope, content in defaults.items():
        directory = DOCS_ROOT / scope
        (directory / "images").mkdir(parents=True, exist_ok=True)
        index = directory / "index.md"
        if not index.exists():
            _atomic_write(index, content.encode("utf-8"))


def _scope_root(scope: str) -> Path:
    if scope not in SCOPES:
        raise HTTPException(status_code=404, detail="Раздел документации не найден")
    ensure_docs()
    return (DOCS_ROOT / scope).resolve()


def resolve_path(scope: str, relative_path: str, extensions: set[str]) -> Path:
    root = _scope_root(scope)
    normalized = str(relative_path or "").replace("\\", "/").strip("/")
    if not normalized or "\x00" in normalized or ":" in normalized:
        raise HTTPException(status_code=400, detail="Некорректный путь")
    target = (root / normalized).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Некорректный путь") from error
    if target.suffix.lower() not in extensions:
        raise HTTPException(status_code=400, detail="Недопустимый тип файла")
    return target


def list_documents(scope: str) -> list[dict]:
    root = _scope_root(scope)
    return [
        {"path": path.relative_to(root).as_posix(), "title": _document_title(path)}
        for path in sorted(root.rglob("*.md"), key=lambda item: item.as_posix().lower())
        if path.is_file()
    ]


def read_document(scope: str, relative_path: str) -> dict:
    path = resolve_path(scope, relative_path, {".md"})
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Документ не найден")
    raw = path.read_bytes()
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Документ слишком большой")
    return {
        "path": path.relative_to(_scope_root(scope)).as_posix(),
        "content": raw.decode("utf-8"),
        "revision": hashlib.sha256(raw).hexdigest(),
    }


def save_document(scope: str, relative_path: str, content: str, revision: str | None) -> dict:
    raw = content.encode("utf-8")
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Документ слишком большой")
    path = resolve_path(scope, relative_path, {".md"})
    if path.exists() and revision:
        current = hashlib.sha256(path.read_bytes()).hexdigest()
        if current != revision:
            raise HTTPException(status_code=409, detail="Документ уже изменён в другой вкладке")
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, raw)
    return read_document(scope, relative_path)


def create_document(scope: str, relative_path: str) -> dict:
    path = resolve_path(scope, relative_path, {".md"})
    if path.exists():
        raise HTTPException(status_code=409, detail="Такой документ уже существует")
    path.parent.mkdir(parents=True, exist_ok=True)
    title = re.sub(r"[-_]", " ", path.stem).strip().capitalize() or "Новый документ"
    _atomic_write(path, f"# {title}\n\n".encode("utf-8"))
    return read_document(scope, relative_path)


def rename_document(scope: str, old_path: str, new_path: str) -> dict:
    source = resolve_path(scope, old_path, {".md"})
    target = resolve_path(scope, new_path, {".md"})
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Документ не найден")
    if target.exists():
        raise HTTPException(status_code=409, detail="Такой документ уже существует")
    target.parent.mkdir(parents=True, exist_ok=True)
    source.replace(target)
    return read_document(scope, new_path)


def delete_document(scope: str, relative_path: str) -> None:
    path = resolve_path(scope, relative_path, {".md"})
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Документ не найден")
    if len(list_documents(scope)) <= 1:
        raise HTTPException(status_code=400, detail="Нельзя удалить последний документ раздела")
    path.unlink()


async def save_image(scope: str, upload: UploadFile) -> dict:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Поддерживаются PNG, JPG, GIF и WebP")
    stem = re.sub(r"[^a-zA-Z0-9а-яА-Я_-]+", "-", Path(upload.filename or "image").stem).strip("-") or "image"
    data = await upload.read(MAX_IMAGE_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Изображение пустое")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Изображение больше 8 МБ")
    image_dir = _scope_root(scope) / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    target = image_dir / f"{stem}{suffix}"
    counter = 2
    while target.exists():
        target = image_dir / f"{stem}-{counter}{suffix}"
        counter += 1
    _atomic_write(target, data)
    return {"path": target.relative_to(_scope_root(scope)).as_posix(), "markdown": f"![{stem}]({target.relative_to(_scope_root(scope)).as_posix()})"}


def get_asset(scope: str, relative_path: str) -> tuple[Path, str]:
    path = resolve_path(scope, relative_path, set(IMAGE_TYPES))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Изображение не найдено")
    return path, IMAGE_TYPES[path.suffix.lower()]


def _document_title(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip() or path.stem
    except (OSError, UnicodeError):
        pass
    return path.stem.replace("-", " ").capitalize()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
