import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from deploy.update_from_git import (  # noqa: E402
    is_excluded,
    load_excludes,
    normalize_path,
)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("./queue/js/config.js", "queue/js/config.js"),
        ("queue\\media\\clip.mp4", "queue/media/clip.mp4"),
    ],
)
def test_normalize_path(path, expected):
    assert normalize_path(path) == expected


def test_load_excludes_includes_main_env():
    patterns = load_excludes(PROJECT_ROOT)
    assert "main.env" in patterns


@pytest.mark.parametrize(
    "relative_path",
    [
        "main.env",
        "queue/media/video.mp4",
        "queue/tts/cache/hash.wav",
        "__pycache__/module.pyc",
    ],
)
def test_is_excluded_local_files(relative_path):
    patterns = load_excludes(PROJECT_ROOT)
    assert is_excluded(relative_path, patterns)


@pytest.mark.parametrize(
    "relative_path",
    [
        "app/routers/tickets.py",
        "queue/js/terminal.js",
        "requirements.txt",
    ],
)
def test_is_excluded_allows_project_files(relative_path):
    patterns = load_excludes(PROJECT_ROOT)
    assert not is_excluded(relative_path, patterns)
