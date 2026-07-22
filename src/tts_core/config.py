import logging
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

logger = logging.getLogger("tts_core")

SOCKET_PATH = "/tmp/tts_core.sock"
HOST = "127.0.0.1"
PORT = 8125

SAMPLE_RATE = 24000

MODEL_READY_TIMEOUT = 120

# Resolve project root robustly: try tts_core.toml next to the package first,
# then fall back to the src-layout parent directory.
_PACKAGE_DIR = Path(__file__).resolve().parent


def _find_project_root() -> Path:
    """Locate the project root by searching for tts_core.toml."""
    # Editable / src-layout install: src/tts_core/config.py -> ../../
    candidate = _PACKAGE_DIR.parent.parent
    if (candidate / "tts_core.toml").is_file():
        return candidate
    # Normal install: fall back to package dir parent
    return _PACKAGE_DIR.parent


PROJECT_ROOT = _find_project_root()

_MODEL_DEFAULTS = {
    "model_dir": str(Path.home() / "models" / "tts"),
    "default_model": "Qwen3-TTS-12Hz-0.6B-CustomVoice",
    "allowed_models": ["Qwen3-TTS-12Hz-0.6B-CustomVoice"],
}


def _load_config() -> dict:
    config_path = PROJECT_ROOT / "tts_core.toml"
    if not config_path.is_file():
        logger.debug("No tts_core.toml found at %s, using defaults", config_path)
        return {}
    try:
        with config_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        logger.warning("Failed to parse %s: %s", config_path, exc)
        return {}
    return data.get("models", {})


_config = _load_config()

MODEL_DIR = Path(_config.get("model_dir", _MODEL_DEFAULTS["model_dir"]))
MODEL_SIZE_DEFAULT = _config.get("default_model", _MODEL_DEFAULTS["default_model"])
MODEL_CHOICES = _config.get("allowed_models", _MODEL_DEFAULTS["allowed_models"])

# Audio output settings
AUDIO_OUTPUT_DIR = "/tmp/tts_core_audio"
AUDIO_MAX_AGE_SECONDS = 3600  # 1 hour
