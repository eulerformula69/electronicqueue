import asyncio
import re
import subprocess
import wave

from fastapi import HTTPException

try:
    import audioop
except ImportError:
    audioop = None

from app.config import (
    PIPER_MODEL,
    PIPER_PATH,
    TTS_LENGTH_SCALE,
    TTS_NOISE_SCALE,
    TTS_NOISE_W_SCALE,
)


tts_locks: dict[str, asyncio.Lock] = {}


def normalize_tts_input(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"\s+", " ", value)

    if not value:
        raise HTTPException(status_code=400, detail="Пустой текст для озвучки")

    if len(value) > 200:
        raise HTTPException(status_code=400, detail="Слишком длинный текст для озвучки")

    return value


def get_tts_lock(file_hash: str) -> asyncio.Lock:
    if file_hash not in tts_locks:
        tts_locks[file_hash] = asyncio.Lock()
    return tts_locks[file_hash]


def run_piper_sync(text: str, output_path: str):
    return subprocess.run(
        [
            PIPER_PATH,
            "-m", PIPER_MODEL,
            "-f", output_path,
            "--length-scale", TTS_LENGTH_SCALE,
            "--noise-scale", TTS_NOISE_SCALE,
            "--noise-w-scale", TTS_NOISE_W_SCALE,
        ],
        input=text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def resample_wav_to_sample_rate(input_path: str, output_path: str, sample_rate: int):
    with wave.open(input_path, "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        source_rate = source.getframerate()
        frames = source.readframes(source.getnframes())
        params = source.getparams()

    if source_rate == sample_rate:
        if input_path != output_path:
            with wave.open(output_path, "wb") as target:
                target.setparams(params)
                target.writeframes(frames)
        return

    if audioop is not None:
        converted, _ = audioop.ratecv(
            frames,
            sample_width,
            channels,
            source_rate,
            sample_rate,
            None,
        )
    else:
        converted = resample_pcm_linear(
            frames,
            sample_width,
            channels,
            source_rate,
            sample_rate,
        )

    with wave.open(output_path, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(sample_width)
        target.setframerate(sample_rate)
        target.writeframes(converted)


def resample_pcm_linear(
    frames: bytes,
    sample_width: int,
    channels: int,
    source_rate: int,
    target_rate: int,
) -> bytes:
    if sample_width != 2:
        raise HTTPException(
            status_code=500,
            detail="TTS resampling supports only 16-bit PCM WAV without audioop",
        )

    frame_width = sample_width * channels
    frame_count = len(frames) // frame_width
    if frame_count == 0:
        return frames

    samples = [
        int.from_bytes(
            frames[offset:offset + sample_width],
            byteorder="little",
            signed=True,
        )
        for offset in range(0, frame_count * frame_width, sample_width)
    ]

    target_frame_count = max(1, round(frame_count * target_rate / source_rate))
    ratio = source_rate / target_rate
    output = bytearray(target_frame_count * frame_width)

    for target_index in range(target_frame_count):
        source_pos = target_index * ratio
        left_index = int(source_pos)
        right_index = min(left_index + 1, frame_count - 1)
        fraction = source_pos - left_index

        for channel in range(channels):
            left = samples[left_index * channels + channel]
            right = samples[right_index * channels + channel]
            value = round(left + (right - left) * fraction)
            offset = target_index * frame_width + channel * sample_width
            output[offset:offset + sample_width] = int(value).to_bytes(
                sample_width,
                byteorder="little",
                signed=True,
            )

    return bytes(output)
