"""Whisper ASR engine for transcribing voice-clone reference audio.

Uses transformers' whisper-large-v3-turbo: near large-v3 accuracy, ~1.6GB,
and runs on the already-installed transformers + torch cu130 stack (no
CTranslate2, whose Blackwell support is uncertain).
"""
from __future__ import annotations

import gc
import threading
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent

ASR_MODEL_ID = "openai/whisper-large-v3-turbo"
ASR_SAMPLE_RATE = 16000

DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
DTYPE = torch.float16 if torch.cuda.is_available() else torch.float32

# Whisper ISO codes -> Qwen3-TTS `language` values.
_LANG_MAP = {
    "japanese": "Japanese",
    "english": "English",
    "chinese": "Chinese",
    "korean": "Korean",
    "german": "German",
    "french": "French",
    "russian": "Russian",
    "portuguese": "Portuguese",
    "spanish": "Spanish",
    "italian": "Italian",
    "ja": "Japanese",
    "en": "English",
    "zh": "Chinese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "pt": "Portuguese",
    "es": "Spanish",
    "it": "Italian",
}

_pipe = None
_lock = threading.RLock()


def loaded() -> bool:
    return _pipe is not None


def load():
    global _pipe
    with _lock:
        if _pipe is not None:
            return _pipe
        from transformers import pipeline

        _pipe = pipeline(
            "automatic-speech-recognition",
            model=ASR_MODEL_ID,
            dtype=DTYPE,
            device=DEVICE,
        )
        return _pipe


def unload():
    global _pipe
    with _lock:
        _pipe = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def _resample(data: np.ndarray, sr: int) -> np.ndarray:
    if sr == ASR_SAMPLE_RATE:
        return data
    import torchaudio

    tensor = torch.from_numpy(data).unsqueeze(0)
    return torchaudio.functional.resample(tensor, sr, ASR_SAMPLE_RATE).squeeze(0).numpy()


def transcribe(data: np.ndarray, sr: int) -> dict:
    """Transcribe mono float32 audio. Returns {"text", "language"}."""
    data = np.asarray(data, dtype=np.float32)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = _resample(data, sr)

    with _lock:
        pipe = load()
        # The pipeline does not surface the detected language reliably, so
        # detect it explicitly on the first 30 seconds.
        language = "Auto"
        try:
            feats = pipe.feature_extractor(
                data[: 30 * ASR_SAMPLE_RATE],
                sampling_rate=ASR_SAMPLE_RATE,
                return_tensors="pt",
            )
            input_features = feats.input_features.to(
                pipe.model.device, dtype=pipe.model.dtype
            )
            lang_ids = pipe.model.detect_language(input_features=input_features)
            token = pipe.tokenizer.decode(lang_ids)  # e.g. "<|ja|>"
            language = _LANG_MAP.get(token.strip("<|>").lower(), "Auto")
        except Exception:
            pass
        result = pipe(
            data,
            chunk_length_s=30,
            generate_kwargs={"task": "transcribe"},
        )

    text = (result.get("text") or "").strip()
    return {"text": text, "language": language}
