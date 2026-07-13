import time
from contextlib import asynccontextmanager

import psutil
import torch
from fastapi import FastAPI, HTTPException

from .config import MODEL_CHOICES, MODEL_SIZE_DEFAULT, SOCKET_PATH
from .models import LoadRequest, ModelStatus, SynthesizeRequest, SynthesizeResponse
from .tts_engine import TTSEngine

_engine: TTSEngine | None = None
_stats = {"requests_total": 0, "requests_failed": 0}


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


def _get_engine() -> TTSEngine:
    if _engine is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return _engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if _engine is not None:
        _engine.unload()


app = FastAPI(title="TTSCore", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/status", response_model=ModelStatus)
def status():
    if _engine is None:
        return ModelStatus(state="unloaded", gpu_memory_mb=_gpu_memory_mb(), **_stats)
    return ModelStatus(
        state=_engine.state,
        model_name=_engine.model_name,
        error_message=str(_engine._error) if _engine._error else None,
        gpu_memory_mb=_gpu_memory_mb(),
        **_stats,
    )


@app.post("/load")
def load(req: LoadRequest):
    global _engine
    if _engine is not None and _engine.model_name == req.model_name:
        if _engine.state == "error":
            _engine.unload()
        else:
            return {"state": _engine.state, "model_name": req.model_name}

    if _engine is not None:
        _engine.unload()

    if req.model_name not in MODEL_CHOICES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model '{req.model_name}'. Choices: {MODEL_CHOICES}",
        )

    _engine = TTSEngine(model_name=req.model_name)
    _engine.load()
    return {"state": _engine.state, "model_name": req.model_name}


@app.post("/unload")
def unload():
    global _engine
    if _engine is not None:
        _engine.unload()
        _engine = None
    return {"state": "unloaded"}


@app.post("/synthesize", response_model=SynthesizeResponse)
def synthesize(req: SynthesizeRequest):
    global _engine
    _stats["requests_total"] += 1

    try:
        requested = req.model_name
        if requested:
            if _engine is None or _engine.model_name != requested:
                load(LoadRequest(model_name=requested))
        elif _engine is None:
            load(LoadRequest(model_name=MODEL_SIZE_DEFAULT))

        engine = _get_engine()
        result = engine.synthesize(
            text=req.text,
            language=req.language,
            speaker=req.speaker,
            instruct=req.instruct,
        )
        return SynthesizeResponse(**result)
    except HTTPException:
        _stats["requests_failed"] += 1
        raise
    except Exception as e:
        _stats["requests_failed"] += 1
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
def stats():
    return {
        **_stats,
        "gpu_memory_mb": _gpu_system_mb(),
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": psutil.virtual_memory().percent,
    }
