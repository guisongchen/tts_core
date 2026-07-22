import gc
import logging
import os
import threading
import time

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

from .config import (
    AUDIO_OUTPUT_DIR,
    MODEL_DIR,
    MODEL_READY_TIMEOUT,
    MODEL_SIZE_DEFAULT,
)

logger = logging.getLogger("tts_core")


class TTSEngine:
    """Qwen3-TTS model wrapper with async loading and lifecycle management."""

    def __init__(self, model_name: str = None):
        self.model_name = model_name or MODEL_SIZE_DEFAULT
        self._model = None
        self._ready = threading.Event()
        self._error: Exception | None = None
        self._lock = threading.Lock()
        self._load_thread: threading.Thread | None = None
        self._synth_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def error(self) -> Exception | None:
        """Last loading error, if any."""
        return self._error

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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load(self):
        """Start loading the model in a background thread."""
        with self._lock:
            if self._load_thread is not None and self._load_thread.is_alive():
                return
            self._ready.clear()
            self._error = None
            self._load_thread = threading.Thread(
                target=self._load, daemon=True, name="tts-model-load"
            )
            self._load_thread.start()

    def _load(self):
        try:
            local_path = MODEL_DIR / self.model_name
            if not local_path.is_dir():
                raise FileNotFoundError(
                    f"Model directory not found: {local_path}. "
                    f"Place the model in {MODEL_DIR}/"
                )

            logger.info("Loading model from %s ...", local_path)
            self._model = Qwen3TTSModel.from_pretrained(
                str(local_path),
                device_map="cuda:0",
                dtype=torch.bfloat16,
                local_files_only=True,
            )
            logger.info("Model '%s' loaded successfully", self.model_name)
        except Exception as e:
            logger.error("Failed to load model '%s': %s", self.model_name, e)
            self._error = e
        finally:
            self._ready.set()

    def unload(self):
        """Unload the model and free GPU memory."""
        with self._lock:
            if self._model is not None:
                logger.info("Unloading model '%s'", self.model_name)
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
        """Block until the model is loaded or timeout is reached."""
        if not self._ready.wait(timeout=timeout):
            raise RuntimeError(f"Model loading timed out after {timeout}s")
        if self._error:
            raise self._error
        return self._model

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def synthesize(
        self,
        text: str,
        language: str = None,
        speaker: str = None,
        instruct: str = None,
        output_dir: str = None,
    ) -> dict:
        """Synthesize speech. Thread-safe: serializes concurrent calls."""
        model = self.wait_for_ready()
        output_dir = output_dir or AUDIO_OUTPUT_DIR

        kwargs: dict = {"text": text}
        if language:
            kwargs["language"] = language
        if speaker:
            kwargs["speaker"] = speaker
        if instruct:
            kwargs["instruct"] = instruct

        with self._synth_lock:
            start = time.monotonic()
            wavs, sr = model.generate_custom_voice(**kwargs)
            duration = time.monotonic() - start

        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"tts_{int(time.time() * 1000)}.wav")
        sf.write(output_path, wavs[0], sr)

        logger.info(
            "Synthesized %d chars -> %s (%.2fs)", len(text), output_path, duration
        )
        return {
            "audio_path": output_path,
            "duration_seconds": duration,
            "sample_rate": sr,
        }
