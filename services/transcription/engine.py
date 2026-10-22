"""
Model engine and cache for Faster Whisper.
Ensures models are loaded from the configured storage directory and cached in memory.
"""
import time
import logging
import threading
from typing import Dict, Optional
from faster_whisper import WhisperModel
from services.transcription.models import get_models_directory, get_model_repo_name
from config import DEVICE, COMPUTE_TYPE, MAX_TRANSCRIPTION_WORKERS

logger = logging.getLogger(__name__)


class CachedModel:
    """Wrapper holding a loaded WhisperModel instance and its metadata."""
    def __init__(self, model: WhisperModel, model_name: str, device: str, compute_type: str, load_time: float):
        self.model = model
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.load_time = load_time
        self.cached_at = time.time()
        self.last_accessed = time.time()
        self.access_count = 1


class ModelEngine:
    """Singleton model cache managing active WhisperModel instances."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self._cache: Dict[str, CachedModel] = {}
        self._cache_lock = threading.Lock()
        self._initialized = True
        logger.info("ModelEngine initialized")

    def get_model(self, model_name: str,
                  device: str | None = None,
                  compute_type: str | None = None,
                  cpu_threads: int | None = None) -> WhisperModel:
        """
        Retrieve a loaded WhisperModel from memory cache or load it from disk.
        """
        use_device = device or DEVICE
        use_compute = compute_type or COMPUTE_TYPE
        workers = cpu_threads or MAX_TRANSCRIPTION_WORKERS
        cache_key = f"{model_name}_{use_device}_{use_compute}"

        # Fast path
        with self._cache_lock:
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                cached.last_accessed = time.time()
                cached.access_count += 1
                logger.info("Using cached model: %s (access #%d)", cache_key, cached.access_count)
                return cached.model

        # Slow path: load under lock
        with self._cache_lock:
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                cached.last_accessed = time.time()
                cached.access_count += 1
                return cached.model

            repo = get_model_repo_name(model_name)
            download_dir = get_models_directory()
            logger.info("Loading model %s from %s on device=%s, compute_type=%s, workers=%d...",
                        repo, download_dir, use_device, use_compute, workers)
            start_time = time.time()

            model = WhisperModel(
                repo,
                device=use_device,
                compute_type=use_compute,
                download_root=download_dir,
                cpu_threads=workers,
                num_workers=workers
            )

            load_time = time.time() - start_time
            logger.info("Loaded model %s in %.2fs", cache_key, load_time)

            self._cache[cache_key] = CachedModel(
                model=model,
                model_name=model_name,
                device=use_device,
                compute_type=use_compute,
                load_time=load_time
            )
            return model

    def evict(self, model_name: str | None = None):
        """Evict a specific model or all models from cache."""
        with self._cache_lock:
            if model_name:
                keys = [k for k in self._cache if k.startswith(model_name)]
                for k in keys:
                    del self._cache[k]
                    logger.info("Evicted cached model: %s", k)
            else:
                self._cache.clear()
                logger.info("Evicted all cached models")


_engine = ModelEngine()


def get_cached_model(model_name: str,
                     device: str | None = None,
                     compute_type: str | None = None) -> WhisperModel:
    """Get model instance from the global engine."""
    return _engine.get_model(model_name, device, compute_type)


def evict_model(model_name: str | None = None):
    """Evict cached model instance."""
    _engine.evict(model_name)
