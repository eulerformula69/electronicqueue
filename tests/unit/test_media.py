import pytest
from fastapi import HTTPException

from app.services.media import normalize_compression_mode, sanitize_media_filename


def test_sanitize_media_filename_valid():
    assert sanitize_media_filename("clip.mp4") == "clip.mp4"


def test_sanitize_media_filename_strips_path():
    assert sanitize_media_filename("/tmp/evil/../video.webm") == "video.webm"


@pytest.mark.parametrize("filename", ["", ".", "..", None])
def test_sanitize_media_filename_invalid(filename):
    with pytest.raises(HTTPException) as exc:
        sanitize_media_filename(filename)
    assert exc.value.status_code == 400


def test_sanitize_media_filename_bad_extension():
    with pytest.raises(HTTPException) as exc:
        sanitize_media_filename("file.exe")
    assert exc.value.status_code == 400


def test_normalize_compression_mode_defaults_to_normal():
    assert normalize_compression_mode(None) == "normal"
    assert normalize_compression_mode("") == "normal"


@pytest.mark.parametrize("mode", ["normal", "high", "compact", "HIGH"])
def test_normalize_compression_mode_valid(mode):
    assert normalize_compression_mode(mode) in {"normal", "high", "compact"}


def test_normalize_compression_mode_invalid():
    with pytest.raises(HTTPException) as exc:
        normalize_compression_mode("ultra")
    assert exc.value.status_code == 400
