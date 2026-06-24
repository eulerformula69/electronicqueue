import pytest
from fastapi import HTTPException

from app.services.tts import normalize_tts_input, resample_pcm_linear


def test_normalize_tts_input_strips_and_collapses_whitespace():
    assert normalize_tts_input("  Талон   42  ") == "Талон 42"


def test_normalize_tts_input_empty_raises():
    with pytest.raises(HTTPException) as exc:
        normalize_tts_input("   ")
    assert exc.value.status_code == 400


def test_normalize_tts_input_too_long_raises():
    with pytest.raises(HTTPException) as exc:
        normalize_tts_input("а" * 201)
    assert exc.value.status_code == 400


def test_resample_pcm_linear_downsamples():
    # 16-bit mono: two samples 0 and 1000 at 48000 -> 24000 Hz
    frames = (0).to_bytes(2, "little", signed=True) + (1000).to_bytes(
        2, "little", signed=True
    )
    result = resample_pcm_linear(frames, 2, 1, 48000, 24000)
    assert len(result) == 2  # one output sample


def test_resample_pcm_linear_same_rate_returns_input():
    frames = b"\x00\x00\xff\x7f"
    assert resample_pcm_linear(frames, 2, 1, 48000, 48000) == frames


def test_resample_pcm_linear_unsupported_width_raises():
    with pytest.raises(HTTPException) as exc:
        resample_pcm_linear(b"\x00", 1, 1, 48000, 24000)
    assert exc.value.status_code == 500
