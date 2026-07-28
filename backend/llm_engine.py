"""Gemma4 (GGUF via llama-cpp-python) engine.

Phase 1 only covers resident load/unload for the top-bar toggle; the actual
assist features (dialogue writing, text normalization, titles) come later.
"""
from __future__ import annotations

import gc
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GGUF_PATH = ROOT / "models" / "gemma-4-12B-it-GGUF" / "gemma-4-12B-it-Q4_K_M.gguf"

_llm = None
_lock = threading.RLock()


def present() -> bool:
    return GGUF_PATH.exists()


def loaded() -> bool:
    return _llm is not None


def load():
    global _llm
    with _lock:
        if _llm is not None:
            return _llm
        from llama_cpp import Llama

        _llm = Llama(
            model_path=str(GGUF_PATH),
            n_gpu_layers=-1,
            n_ctx=8192,
            verbose=False,
        )
        return _llm


def unload():
    global _llm
    with _lock:
        _llm = None
        gc.collect()
