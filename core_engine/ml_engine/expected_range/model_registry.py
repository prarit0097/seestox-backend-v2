# core_engine/ml_engine/expected_range/model_registry.py
# ER-4.2 — MODEL REGISTRY (SINGLE SOURCE OF TRUTH)

from typing import Dict, Optional
from core_engine.ml_engine.expected_range.model_persistence import (
    load_all_models,
    load_model_meta,
)

# ==================================================
# INTERNAL CACHE (SAFE)
# ==================================================

_MODEL_CACHE: Optional[Dict] = None
_META_CACHE: Optional[Dict] = None


# ==================================================
# LOADERS
# ==================================================

def _ensure_loaded():
    global _MODEL_CACHE, _META_CACHE

    if _MODEL_CACHE is None:
        _MODEL_CACHE = load_all_models()

    if _META_CACHE is None:
        _META_CACHE = load_model_meta()


# ==================================================
# PUBLIC API
# ==================================================

def get_all_models() -> Dict:
    """
    Returns all loaded Expected Range models.
    """
    _ensure_loaded()
    return _MODEL_CACHE.copy()


def get_model(model_name: str):
    """
    Returns a single model by name.
    """
    _ensure_loaded()
    return _MODEL_CACHE.get(model_name)


def get_registry_meta() -> Dict:
    """
    Returns training meta information.
    """
    _ensure_loaded()
    return _META_CACHE.copy()


def refresh_registry() -> dict:
    """
    Force reload models + meta (after retraining).
    """
    global _MODEL_CACHE, _META_CACHE

    _MODEL_CACHE = load_all_models()
    _META_CACHE = load_model_meta()

    return {
        "status": "REFRESHED",
        "model_count": len(_MODEL_CACHE),
    }


# ==================================================
# SIMPLE HEALTH CHECK
# ==================================================

def registry_health() -> dict:
    _ensure_loaded()

    if not _MODEL_CACHE:
        return {
            "status": "EMPTY",
            "note": "No Expected Range models loaded",
        }

    return {
        "status": "READY",
        "models": list(_MODEL_CACHE.keys()),
        "count": len(_MODEL_CACHE),
    }
