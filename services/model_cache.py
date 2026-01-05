"""
Model Cache Service - Cache Faster Whisper models for performance
"""
import threading
import time
from typing import Optional, Dict
from faster_whisper import WhisperModel


class ModelCache:
    """
    Singleton cache for Whisper models
    Keeps models in memory to avoid reloading
    """
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
        if self._initialized:
            return
        
        self._cache: Dict[str, 'CachedModel'] = {}
        self._cache_lock = threading.Lock()
        self._initialized = True
        print("[ModelCache] Initialized")
    
    def get_model(self, model_name: str, device: str = "cpu", compute_type: str = "int8") -> WhisperModel:
        """
        Get model from cache or load if not cached
        Thread-safe with double-checked locking to prevent duplicate loads
        
        Args:
            model_name: Model name (tiny, base, small, medium, large)
            device: Device to use (cpu, cuda)
            compute_type: Compute type (int8, float16, float32)
            
        Returns:
            WhisperModel instance
        """
        cache_key = f"{model_name}_{device}_{compute_type}"
        
        # ✅ Map large to large-v3 for Hugging Face repository
        hf_model_name = 'large-v3' if model_name == 'large' else model_name
        
        # First check without lock (fast path for cache hits)
        if cache_key in self._cache:
            with self._cache_lock:
                # Double-check with lock to ensure model is still there
                if cache_key in self._cache:
                    cached = self._cache[cache_key]
                    cached.last_accessed = time.time()
                    cached.access_count += 1
                    print(f"[ModelCache] ✅ Using cached model: {cache_key} (access #{cached.access_count})")
                    return cached.model
        
        # Load model under lock (slow path)
        with self._cache_lock:
            # Double-check: another thread might have loaded it while we waited
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                cached.last_accessed = time.time()
                cached.access_count += 1
                print(f"[ModelCache] ✅ Using cached model: {cache_key} (access #{cached.access_count})")
                return cached.model
            
            # Actually load the model (no other thread will load it now)
            print(f"[ModelCache] 📥 Loading model: {cache_key}")
            start_time = time.time()
            
            # Use the mapped model name for Hugging Face
            model = WhisperModel(
                f"Systran/faster-whisper-{hf_model_name}",
                device=device,
                compute_type=compute_type
            )
            
            load_time = time.time() - start_time
            print(f"[ModelCache] ✅ Loaded {cache_key} in {load_time:.1f}s")
            
            # Cache it
            self._cache[cache_key] = CachedModel(
                model=model,
                model_name=model_name,
                device=device,
                compute_type=compute_type,
                load_time=load_time
            )
            
            return model
    
    def clear_cache(self, model_name: Optional[str] = None):
        """
        Clear cache for specific model or all models
        
        Args:
            model_name: Model name to clear, or None to clear all
        """
        with self._cache_lock:
            if model_name:
                # Clear specific model
                keys_to_remove = [k for k in self._cache.keys() if k.startswith(model_name)]
                for key in keys_to_remove:
                    del self._cache[key]
                    print(f"[ModelCache] 🗑️ Cleared: {key}")
            else:
                # Clear all
                self._cache.clear()
                print("[ModelCache] 🗑️ Cleared all cached models")
    
    def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        with self._cache_lock:
            stats = {
                'cached_models': len(self._cache),
                'models': {}
            }
            
            for key, cached in self._cache.items():
                stats['models'][key] = {
                    'access_count': cached.access_count,
                    'load_time': cached.load_time,
                    'cached_since': time.time() - cached.cached_at
                }
            
            return stats


class CachedModel:
    """Wrapper for cached model with metadata"""
    
    def __init__(self, model, model_name: str, device: str, compute_type: str, load_time: float):
        self.model = model
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.load_time = load_time
        self.cached_at = time.time()
        self.last_accessed = time.time()
        self.access_count = 1


# Global instance
_model_cache = ModelCache()


def get_cached_model(model_name: str, device: str = "cpu", compute_type: str = "int8") -> WhisperModel:
    """
    Get model from global cache
    
    Args:
        model_name: Model name
        device: Device (cpu/cuda)
        compute_type: Compute type
        
    Returns:
        WhisperModel instance
    """
    return _model_cache.get_model(model_name, device, compute_type)


def clear_model_cache(model_name: Optional[str] = None):
    """Clear model cache"""
    _model_cache.clear_cache(model_name)


def get_cache_stats() -> dict:
    """Get cache statistics"""
    return _model_cache.get_cache_stats()
