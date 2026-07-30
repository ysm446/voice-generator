"""Qwen3-TTS engine: model registry, lazy loading, and generation dispatch.

Model type and generation method are 1:1 (library raises otherwise):
  -Base        -> generate_voice_clone   (mode "clone")
  -CustomVoice -> generate_custom_voice  (mode "custom")
  -VoiceDesign -> generate_voice_design  (mode "design")
"""
from __future__ import annotations

import gc
import json
import os
import threading
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

import personas

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"

DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
DTYPE = torch.bfloat16 if torch.cuda.is_available() else torch.float32

# mode -> size -> HF model id. custom/design only ship in 1.7B here; requests
# for other sizes fall back to the mode's only entry.
TTS_MODELS = {
    "clone": {
        "1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        "0.6B": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    },
    "custom": {"1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"},
    "design": {"1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"},
}

_models: dict[str, object] = {}
_lock = threading.RLock()

# Voice-clone prompts (reference codes + speaker embedding) reused across
# consecutive generations with the same persona. Keyed on the reference audio's
# mtime/size and the transcript, so editing the persona invalidates it.
_prompt_cache: dict[tuple, object] = {}
_PROMPT_CACHE_MAX = 8


def resolve_model_id(mode: str, size: str) -> str:
    sizes = TTS_MODELS[mode]
    return sizes.get(size) or sizes["1.7B"]


def _cache_dir(model_id: str) -> Path:
    return MODELS_DIR / "hub" / ("models--" + model_id.replace("/", "--"))


def model_present(model_id: str) -> bool:
    """True if the HF cache holds a snapshot with a config.json."""
    snapshots = _cache_dir(model_id) / "snapshots"
    if not snapshots.exists():
        return False
    return any(p.is_dir() and (p / "config.json").exists() for p in snapshots.iterdir())


def _snapshot_config(model_id: str) -> dict | None:
    snapshots = _cache_dir(model_id) / "snapshots"
    if not snapshots.exists():
        return None
    for p in snapshots.iterdir():
        cfg = p / "config.json"
        if cfg.exists():
            try:
                with open(cfg, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
    return None


def custom_speakers() -> list[str]:
    """Preset speaker names of the CustomVoice model (empty if absent)."""
    cfg = _snapshot_config(TTS_MODELS["custom"]["1.7B"])
    if not cfg:
        return []
    spk = (cfg.get("talker_config") or {}).get("spk_id") or {}
    return sorted(spk.keys())


def modes_summary() -> dict:
    """Per-mode availability for /api/health."""
    out = {}
    for mode, sizes in TTS_MODELS.items():
        models = {
            size: {"id": mid, "present": model_present(mid)}
            for size, mid in sizes.items()
        }
        out[mode] = {
            "present": any(m["present"] for m in models.values()),
            "models": models,
        }
    out["custom"]["speakers"] = custom_speakers()
    return out


def any_present() -> bool:
    return any(info["present"] for info in modes_summary().values())


def loaded_any() -> bool:
    return bool(_models)


def load(mode: str, size: str, progress=None):
    model_id = resolve_model_id(mode, size)
    with _lock:
        if model_id in _models:
            return _models[model_id]
        if progress:
            progress(f"loading {model_id.split('/')[-1]}...")
        from qwen_tts import Qwen3TTSModel

        kwargs = {"device_map": DEVICE, "dtype": DTYPE}
        try:
            import flash_attn  # noqa: F401

            kwargs["attn_implementation"] = "flash_attention_2"
        except ImportError:
            pass
        model = Qwen3TTSModel.from_pretrained(model_id, **kwargs)
        _models[model_id] = model
        return model


def unload_all():
    with _lock:
        _models.clear()
        # The cached prompts hold small CUDA tensors; drop them with the models.
        _prompt_cache.clear()
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def _load_ref_audio(path: str) -> tuple[np.ndarray, int]:
    data, sr = sf.read(path)
    data = np.asarray(data, dtype=np.float32)
    if data.ndim > 1:
        data = data.mean(axis=1)
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > 1.0:
        data = data / peak
    return data, sr


def _prompt_key(model_id: str, name: str, persona: dict) -> tuple | None:
    """Cache key for a persona's voice-clone prompt (None if ref.wav is gone)."""
    try:
        st = os.stat(persona["ref_path"])
    except OSError:
        return None
    return (
        model_id,
        name,
        persona["ref_path"],
        st.st_mtime_ns,
        st.st_size,
        persona["transcript"],
    )


def _voice_clone_prompt(model, model_id: str, name: str, persona: dict, progress=None):
    """Reference prompt for `name`, built once and reused while unchanged."""
    key = _prompt_key(model_id, name, persona)
    if key is not None and key in _prompt_cache:
        # Refresh insertion order so eviction drops the least recently used.
        _prompt_cache[key] = _prompt_cache.pop(key)
        return _prompt_cache[key]

    if progress:
        progress("encoding reference audio...")
    items = model.create_voice_clone_prompt(
        ref_audio=_load_ref_audio(persona["ref_path"]),
        ref_text=persona["transcript"],
    )
    if key is not None:
        _prompt_cache[key] = items
        while len(_prompt_cache) > _PROMPT_CACHE_MAX:
            _prompt_cache.pop(next(iter(_prompt_cache)))
    return items


def generate(
    mode: str,
    text: str,
    language: str,
    voice_name: str | None,
    instruct: str | None,
    model_size: str,
    progress=None,
) -> tuple[np.ndarray, int]:
    """Run TTS and return (mono float audio, sample_rate)."""
    with _lock:
        if mode == "clone":
            persona = personas.load(voice_name)
            # An explicit language wins; "Auto" defers to the persona's setting.
            if language == "Auto" and persona["language"] != "Auto":
                language = persona["language"]
            model = load(mode, model_size, progress)
            prompt = _voice_clone_prompt(
                model, resolve_model_id(mode, model_size), voice_name, persona, progress
            )
            if progress:
                progress("generating...")
            wavs, sr = model.generate_voice_clone(
                text=text,
                language=language,
                voice_clone_prompt=prompt,
            )
        elif mode == "custom":
            model = load(mode, model_size, progress)
            if progress:
                progress("generating...")
            wavs, sr = model.generate_custom_voice(
                text=text,
                speaker=voice_name,
                language=language,
                instruct=instruct or None,
            )
        elif mode == "design":
            model = load(mode, model_size, progress)
            if progress:
                progress("generating...")
            wavs, sr = model.generate_voice_design(
                text=text,
                instruct=instruct,
                language=language,
            )
        else:
            raise ValueError(f"unknown mode: {mode}")

    audio = np.asarray(wavs[0], dtype=np.float32)
    return audio, sr


def save_wav(audio: np.ndarray, sr: int, path: str):
    audio = np.clip(audio, -1.0, 1.0)
    sf.write(path, audio, sr, subtype="PCM_16")
