# CLAUDE.md

This file provides guidance to Claude Code when working in the `tts_core` repository.

## Project Overview

`tts_core` is a shared local TTS (Text-to-Speech) service that owns the Qwen3-TTS model lifecycle. It exposes an HTTP API over a Unix domain socket and provides a Python client library.

## Architecture

```
tts_core/
├── src/tts_core/
│   ├── server.py      # Uvicorn + FastAPI daemon entry point
│   ├── api.py         # FastAPI routes: /health, /status, /load, /unload, /synthesize, /stats
│   ├── models.py      # Pydantic request/response models
│   ├── client.py      # TTSCoreClient — Python client over Unix socket
│   ├── tts_engine.py  # TTSEngine — wraps qwen_tts.Qwen3TTSModel
│   ├── config.py      # Paths, defaults, and tts_core.toml loader
│   └── dashboard/     # Web dashboard (FastAPI + Jinja2 + HTMX)
│       ├── app.py     # Dashboard routes and API
│       ├── systemd.py # Systemd service manager wrapper
│       ├── static/    # HTMX, CSS, favicon
│       └── templates/ # Jinja2 templates with HTMX partials
├── services/
│   └── tts-core.service
├── tts_core.toml      # Runtime model configuration
└── models/            # local model directories or symlinks (gitignored)
```

## Environment

```bash
cd /home/ccc/projects/tts_core
python3 -m venv .venv
uv pip install -e ".[server]"
```

For client-only projects, install the base package without GPU/server dependencies:

```bash
uv pip install -e /home/ccc/projects/tts_core
```

The project expects Python 3.10+ and a CUDA-capable GPU for model inference.

## Running the service

### Manually

```bash
.venv/bin/python3 -m tts_core
```

### Via systemd

```bash
systemctl --user enable --now $PWD/services/tts-core.service
```

### Dashboard

```bash
.venv/bin/python3 -m tts_core.dashboard
# http://127.0.0.1:8126
```

Socket path: `/tmp/tts_core.sock`
Dashboard: `http://127.0.0.1:8126`

## API

| Endpoint | Method | Body | Description |
|----------|--------|------|-------------|
| `/health` | GET | — | Liveness |
| `/status` | GET | — | Model state |
| `/load` | POST | `{"model_name":"Qwen3-TTS-12Hz-0.6B-CustomVoice"}` | Load model |
| `/unload` | POST | — | Unload model, free GPU |
| `/synthesize` | POST | `{"text":"Hello", "language":"Chinese", "speaker":"Vivian"}` | Synthesize speech |
| `/stats` | GET | — | Request stats + GPU memory |

### Supported speakers

`Qwen3-TTS-12Hz-0.6B-CustomVoice` supports:

| Speaker | Description | Native Language |
| --- | --- | --- |
| Vivian | Bright young female voice | Chinese |
| Serena | Warm, gentle young female voice | Chinese |
| Uncle_Fu | Seasoned male voice, mellow timbre | Chinese |

More speakers may be available from the full model config.

### Synthesize parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | string (required) | Text to synthesize |
| `model_name` | string | Override model (loads on demand) |
| `language` | string | `Chinese`, `English`, `Japanese`, `Korean`, `German`, `French`, `Russian`, `Portuguese`, `Spanish`, `Italian` |
| `speaker` | string | `Vivian`, `Serena`, `Uncle_Fu` |
| `instruct` | string | Style instruction, e.g. `"用特别愤怒的语气说"` |

## Model resolution

When loading a model, `TTSEngine` resolves the path in this order:

1. `<model_dir>/<model_name>` if it exists, where `model_dir` is read from `tts_core.toml`
2. Fallback HF identifier `Qwen/<model_name>` (only if not in offline mode)

Configure the model directory in `tts_core.toml`:

```toml
[models]
model_dir = "/home/ccc/models/tts"
```

If the config file is missing, `model_dir` defaults to `/home/ccc/models/tts`.

Place model directories there:

```bash
mv /path/to/Qwen3-TTS-12Hz-0.6B-CustomVoice /home/ccc/models/tts/Qwen3-TTS-12Hz-0.6B-CustomVoice
```

## Client usage

```python
from tts_core.client import TTSCoreClient

with TTSCoreClient() as client:
    client.load_model("Qwen3-TTS-12Hz-0.6B-CustomVoice")
    result = client.synthesize(
        "你好世界",
        language="Chinese",
        speaker="Vivian",
        instruct="用开心的语气说",
    )
    print(result["audio_path"])  # path to generated WAV file
```

`TTSCoreClient` auto-starts the daemon if `/tmp/tts_core.sock` is missing (configurable).

## Important notes

- Model weights are configured via `tts_core.toml`; do not commit model weights.
- The service uses `local_files_only=True` when loading models, so models must be present locally.
- Only one model is loaded at a time; loading a different model unloads the previous one.
- If the daemon hits `CUDA out of memory`, stop other GPU processes or unload the current model first.
- The TTS engine depends on `qwen-tts` (not `transformers.AutoModel`), using `Qwen3TTSModel.from_pretrained()` and `generate_custom_voice()`.
- Audio output is 24000 Hz mono WAV, written to `/tmp/tts_<timestamp>.wav` by default.
