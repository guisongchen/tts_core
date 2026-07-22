import logging
import os
import threading
import time
from contextlib import asynccontextmanager

import psutil
import torch
from fastapi import FastAPI, HTTPException

from .config import (
    AUDIO_MAX_AGE_SECONDS,
    AUDIO_OUTPUT_DIR,
    MODEL_CHOICES,
    MODEL_SIZE_DEFAULT,
)
from .models import LoadRequest, ModelStatus, SynthesizeRequest, SynthesizeResponse
from .tts_engine import TTSEngine

logger = logging.getLogger("tts_core")

_engine: TTSEngine | None = None
_engine_lock = threading.Lock()
_stats_lock = threading.Lock()
_stats = {"requests_total": 0, "requests_failed": 0}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _gpu_memory_mb() -> float | None:
    try:
        return torch.cuda.memory_allocated() / 1024 / 1024
    except Exception:
        return None


def _gpu_system_mb() -> float | None:
    try:
        free, total = torch.cuda.mem_get_info()
        return (total - free) / 1024 / 1024
    except Exception:
        return None


def _cleanup_old_audio():
    """Remove audio files older than AUDIO_MAX_AGE_SECONDS."""
    try:
        if not os.path.isdir(AUDIO_OUTPUT_DIR):
            return
        cutoff = time.time() - AUDIO_MAX_AGE_SECONDS
        for fname in os.listdir(AUDIO_OUTPUT_DIR):
            fpath = os.path.join(AUDIO_OUTPUT_DIR, fname)
            try:
                if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                    os.unlink(fpath)
                    logger.debug("Cleaned up old audio file: %s", fpath)
            except OSError:
                pass
    except Exception as exc:
        logger.warning("Audio cleanup error: %s", exc)


# ------------------------------------------------------------------
# App lifecycle
# ------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    with _engine_lock:
        if _engine is not None:
            _engine.unload()


app = FastAPI(title="TTSCore", lifespan=lifespan)


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/status", response_model=ModelStatus)
def status():
    with _engine_lock:
        engine = _engine
    with _stats_lock:
        stats_snapshot = dict(_stats)
    if engine is None:
        return ModelStatus(state="unloaded", gpu_memory_mb=_gpu_memory_mb(), **stats_snapshot)
    return ModelStatus(
        state=engine.state,
        model_name=engine.model_name,
        error_message=str(engine.error) if engine.error else None,
        gpu_memory_mb=_gpu_memory_mb(),
        **stats_snapshot,
    )


@app.post("/load")
def load(req: LoadRequest):
    global _engine

    if req.model_name not in MODEL_CHOICES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model '{req.model_name}'. Choices: {MODEL_CHOICES}",
        )

    with _engine_lock:
        if _engine is not None and _engine.model_name == req.model_name:
            if _engine.state == "error":
                _engine.unload()
            else:
                return {"state": _engine.state, "model_name": req.model_name}

        if _engine is not None:
            _engine.unload()

        _engine = TTSEngine(model_name=req.model_name)
        _engine.load()
        return {"state": _engine.state, "model_name": req.model_name}


@app.post("/unload")
def unload():
    global _engine
    with _engine_lock:
        if _engine is not None:
            _engine.unload()
            _engine = None
    return {"state": "unloaded"}


@app.post("/synthesize", response_model=SynthesizeResponse)
def synthesize(req: SynthesizeRequest):
    global _engine

    with _stats_lock:
        _stats["requests_total"] += 1

    # Periodic cleanup of old audio files
    _cleanup_old_audio()

    try:
        requested = req.model_name or MODEL_SIZE_DEFAULT

        # Grab a reference to the current engine under the lock.
        with _engine_lock:
            engine = _engine

        # If no engine or wrong model, load the requested one.
        if engine is None or engine.model_name != requested:
            load(LoadRequest(model_name=requested))
            with _engine_lock:
                engine = _engine
            if engine is None:
                raise HTTPException(status_code=503, detail="Model not loaded")

        # Run inference outside _engine_lock so /status, /load, /unload
        # remain responsive.  TTSEngine.synthesize has its own _synth_lock
        # to serialize concurrent GPU calls.
        result = engine.synthesize(
            text=req.text,
            language=req.language,
            speaker=req.speaker,
            instruct=req.instruct,
        )
        return SynthesizeResponse(**result)

    except HTTPException:
        with _stats_lock:
            _stats["requests_failed"] += 1
        raise
    except Exception as e:
        with _stats_lock:
            _stats["requests_failed"] += 1
        logger.exception("Synthesis failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
def stats():
    with _stats_lock:
        stats_snapshot = dict(_stats)
    return {
        **stats_snapshot,
        "gpu_memory_mb": _gpu_system_mb(),
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_percent": psutil.virtual_memory().percent,
    }
