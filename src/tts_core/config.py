import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

SOCKET_PATH = "/tmp/tts_core.sock"
HOST = "127.0.0.1"
PORT = 8125

DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 8126

SAMPLE_RATE = 24000

MODEL_READY_TIMEOUT = 120

PROJECT_ROOT = Path(__file__).parent.parent.parent

_MODEL_DEFAULTS = {
    "model_dir": "/home/ccc/models/tts",
    "default_model": "Qwen3-TTS-12Hz-0.6B-CustomVoice",
    "allowed_models": ["Qwen3-TTS-12Hz-0.6B-CustomVoice"],
}


def _load_config() -> dict:
    config_path = PROJECT_ROOT / "tts_core.toml"
    if not config_path.is_file():
        return {}
    try:
        with config_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return {}
    return data.get("models", {})


_config = _load_config()

MODEL_DIR = Path(_config.get("model_dir", _MODEL_DEFAULTS["model_dir"]))
MODEL_SIZE_DEFAULT = _config.get("default_model", _MODEL_DEFAULTS["default_model"])
MODEL_CHOICES = _config.get("allowed_models", _MODEL_DEFAULTS["allowed_models"])
