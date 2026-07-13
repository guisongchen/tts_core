from typing import Literal, Optional

from pydantic import BaseModel, Field


class ModelStatus(BaseModel):
    state: Literal["unloaded", "loading", "loaded", "error"] = "unloaded"
    model_name: Optional[str] = None
    error_message: Optional[str] = None
    gpu_memory_mb: Optional[float] = None
    requests_total: int = 0
    requests_failed: int = 0


class LoadRequest(BaseModel):
    model_name: str = Field(default="Qwen3-TTS-12Hz-0.6B-CustomVoice")


class SynthesizeRequest(BaseModel):
    text: str
    model_name: Optional[str] = None
    language: Optional[str] = None
    speaker: Optional[str] = "Serena"
    instruct: Optional[str] = None


class SynthesizeResponse(BaseModel):
    audio_path: str
    duration_seconds: Optional[float] = None
    sample_rate: int = 24000


class ServiceStatus(BaseModel):
    name: str
    active: bool
    status: str
    uptime: Optional[str] = None
