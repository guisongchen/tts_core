import gc
import os
import threading
import time

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

from .config import (
    MODEL_DIR,
    MODEL_READY_TIMEOUT,
    MODEL_SIZE_DEFAULT,
)


class TTSEngine:
    """Qwen3-TTS model wrapper with async loading and lifecycle management."""

    def __init__(self, model_name: str = None):
        self.model_name = model_name or MODEL_SIZE_DEFAULT
        self._model = None
        self._ready = threading.Event()
        self._error = None
        self._lock = threading.Lock()
        self._load_thread = None

    def load(self):
        with self._lock:
            if self._load_thread is not None and self._load_thread.is_alive():
                return
            self._ready.clear()
            self._error = None
            self._load_thread = threading.Thread(target=self._load, daemon=True)
            self._load_thread.start()

    def _load(self):
        try:
            local_path = MODEL_DIR / self.model_name
            if local_path.is_dir():
                model_id = str(local_path)
            else:
                model_id = f"Qwen/{self.model_name}"

            self._model = Qwen3TTSModel.from_pretrained(
                model_id,
                device_map="cuda:0",
                dtype=torch.bfloat16,
                local_files_only=True,
            )
        except Exception as e:
            self._error = e
        finally:
            self._ready.set()

    def unload(self):
        with self._lock:
            if self._model is not None:
                del self._model
                self._model = None
            self._ready.clear()
            self._error = None
            self._load_thread = None

        gc.collect()

        try:
            torch.cuda.empty_cache()
        except Exception:
            pass

    def wait_for_ready(self, timeout: float = MODEL_READY_TIMEOUT):
        if not self._ready.wait(timeout=timeout):
            raise RuntimeError(f"Model loading timed out after {timeout}s")
        if self._error:
            raise self._error
        return self._model

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set() and self._error is None and self._model is not None

    @property
    def state(self) -> str:
        if self._error:
            return "error"
        if self.is_ready:
            return "loaded"
        if self._load_thread is not None and self._load_thread.is_alive():
            return "loading"
        return "unloaded"

    def synthesize(
        self,
        text: str,
        language: str = None,
        speaker: str = None,
        instruct: str = None,
        output_dir: str = "/tmp",
    ) -> dict:
        model = self.wait_for_ready()

        start = time.monotonic()

        kwargs = {"text": text}
        if language:
            kwargs["language"] = language
        if speaker:
            kwargs["speaker"] = speaker
        if instruct:
            kwargs["instruct"] = instruct

        wavs, sr = model.generate_custom_voice(**kwargs)
        duration = time.monotonic() - start

        os.makedirs(output_dir, exist_ok=True)
        output_path = f"{output_dir}/tts_{int(time.time() * 1000)}.wav"
        sf.write(output_path, wavs[0], sr)

        return {
            "audio_path": output_path,
            "duration_seconds": duration,
            "sample_rate": sr,
        }
