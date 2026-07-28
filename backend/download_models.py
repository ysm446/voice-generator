"""Download the Qwen3-TTS models into the project HF cache (models/).

Usage:  .venv\\Scripts\\python.exe backend\\download_models.py [clone|custom|design ...]
        (no args = all modes)

Windows without Developer Mode cannot create symlinks (WinError 1314), and
huggingface_hub's support probe can misdetect it, so the copy path is forced.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("HF_HOME", str(ROOT / "models"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import huggingface_hub.file_download as fd

fd.are_symlinks_supported = lambda *a, **k: False

from huggingface_hub import snapshot_download

from asr_engine import ASR_MODEL_ID
from tts_engine import TTS_MODELS

targets = sys.argv[1:] or list(TTS_MODELS.keys()) + ["asr"]
for target in targets:
    if target == "asr":
        print(f"[asr] {ASR_MODEL_ID}", flush=True)
        path = snapshot_download(ASR_MODEL_ID)
        print(f"  -> {path}", flush=True)
        continue
    for size, repo in TTS_MODELS[target].items():
        print(f"[{target} {size}] {repo}", flush=True)
        path = snapshot_download(repo)
        print(f"  -> {path}", flush=True)
