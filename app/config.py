import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "main.env", override=True)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/postgres")
raw_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost,http://127.0.0.1")
CORS_ORIGINS = [origin.strip() for origin in raw_cors_origins.split(",") if origin.strip()]
SESSION_TIMEOUT_SECONDS = int(os.getenv("SESSION_TIMEOUT_SECONDS", "30"))
OPERATOR_SESSION_AUTO_CLEANUP_ENABLED = os.getenv(
    "OPERATOR_SESSION_AUTO_CLEANUP_ENABLED", "true"
).lower() in {"1", "true", "yes", "on"}
CLOSE_DAY_WS_URL = os.getenv(
    "CLOSE_DAY_WS_URL", "ws://127.0.0.1:8000/ws/terminal"
)

MAX_FILE_SIZE = 50 * 1024 * 1024
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 500
ALLOWED_MEDIA_EXTENSIONS = {".mp4", ".webm"}

PIPER_PATH = os.getenv("PIPER_PATH", "piper")
PIPER_MODEL = Path(os.getenv(
    "PIPER_MODEL", BASE_DIR / "queue" / "tts" / "ru_RU-irina-medium.onnx"
))
if not PIPER_MODEL.is_absolute():
    PIPER_MODEL = BASE_DIR / PIPER_MODEL

TTS_CACHE_DIR = Path(os.getenv(
    "TTS_CACHE_DIR", BASE_DIR / "queue" / "tts" / "cache"
))
if not TTS_CACHE_DIR.is_absolute():
    TTS_CACHE_DIR = BASE_DIR / TTS_CACHE_DIR

TTS_LENGTH_SCALE = os.getenv("TTS_LENGTH_SCALE", "1.25")
TTS_NOISE_SCALE = os.getenv("TTS_NOISE_SCALE", "0.65")
TTS_NOISE_W_SCALE = os.getenv("TTS_NOISE_W_SCALE", "0.75")
TTS_OUTPUT_SAMPLE_RATE = int(os.getenv("TTS_OUTPUT_SAMPLE_RATE", "48000"))
