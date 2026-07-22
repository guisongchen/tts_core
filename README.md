# TTSCore

Shared TTS (Text-to-Speech) service for local Qwen3-TTS models.

## What it does

TTSCore owns the TTS model lifecycle and exposes an HTTP API over a Unix domain socket. Other applications send text to TTSCore and receive synthesized audio files.

## Quick start

```bash
cd /home/ccc/projects/tts_core
python3 -m venv .venv
uv pip install -e ".[server]"

# Start the daemon
python -m tts_core

# In another terminal
curl --noproxy '*' --unix-socket /tmp/tts_core.sock http://tts_core/status
curl --noproxy '*' --unix-socket /tmp/tts_core.sock -X POST -H "Content-Type: application/json" \
  -d '{"model_name":"Qwen3-TTS-12Hz-0.6B-CustomVoice"}' http://tts_core/load
```

## systemd

```bash
systemctl --user enable --now $PWD/services/tts-core.service
```

## API

| Endpoint | Method | Body | Description |
|----------|--------|------|-------------|
| `/health` | GET | — | Liveness check |
| `/status` | GET | — | Model state: `unloaded`, `loading`, `loaded`, `error` |
| `/load` | POST | `{"model_name":"Qwen3-TTS-12Hz-0.6B-CustomVoice"}` | Load a model by name |
| `/unload` | POST | — | Unload the current model |
| `/synthesize` | POST | `{"text":"Hello","language":"Chinese","speaker":"Vivian","instruct":"用开心的语气说"}` | Synthesize speech |
| `/stats` | GET | — | Request stats and GPU memory |

### Synthesize parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | string | required | Text to synthesize (max 5000 chars) |
| `model_name` | string | default model | Model name (loads on demand if different) |
| `language` | string | — | e.g. `Chinese`, `English`, `Japanese`, `Korean` |
| `speaker` | string | — | `Vivian`, `Serena`, or `Uncle_Fu` |
| `instruct` | string | — | Style instruction, e.g. `"用特别愤怒的语气说"` |

## Models

Models are loaded from the directory configured in `tts_core.toml`:

```toml
[models]
model_dir = "/home/ccc/models/tts"
```

Place model directories there:

```bash
mv /path/to/Qwen3-TTS-12Hz-0.6B-CustomVoice /home/ccc/models/tts/Qwen3-TTS-12Hz-0.6B-CustomVoice
```

If `tts_core.toml` is missing, the default model directory is `~/models/tts`.

Models are loaded exclusively from local directories. No network downloads are performed.

## Audio output

Synthesized audio is written to `/tmp/tts_core_audio/` as WAV files (24 kHz mono). Files older than 1 hour are automatically cleaned up on each synthesis request.
