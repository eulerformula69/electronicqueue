import pytest
from fastapi import HTTPException

from app.services.media import (
    normalize_compression_mode,
    parse_custom_ffmpeg_command,
    sanitize_media_filename,
)


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


@pytest.mark.parametrize("mode", ["normal", "high", "compact", "custom", "HIGH"])
def test_normalize_compression_mode_valid(mode):
    assert normalize_compression_mode(mode) in {"normal", "high", "compact", "custom"}


def test_normalize_compression_mode_invalid():
    with pytest.raises(HTTPException) as exc:
        normalize_compression_mode("ultra")
    assert exc.value.status_code == 400


def test_parse_custom_ffmpeg_command_returns_safe_arguments():
    assert parse_custom_ffmpeg_command('ffmpeg -i "{input}" -c:v libx264 "{output}"') == [
        "-i", "{input}", "-c:v", "libx264", "{output}"
    ]


@pytest.mark.parametrize("command", [
    "rm -rf /",
    "ffmpeg -i file.mp4 {output}",
    "ffmpeg -i {input} result.mp4",
    "ffmpeg -i {input} -i second.mp4 {output}",
    "ffmpeg {output} -i {input}",
])
def test_parse_custom_ffmpeg_command_rejects_unsafe_templates(command):
    with pytest.raises(HTTPException) as exc:
        parse_custom_ffmpeg_command(command)
    assert exc.value.status_code == 400
