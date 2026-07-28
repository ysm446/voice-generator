"""Persona (voice profile) management.

A persona is a directory under persona/<name>/ containing:
  ref.wav    - reference audio for voice cloning
  info.yaml  - transcript / language / speech-style profile (see voice-persona)
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

ROOT = Path(__file__).resolve().parent.parent
PERSONA_DIR = ROOT / "persona"

# transcript/language drive TTS; the rest feed the LLM dialogue writer.
INFO_FIELDS = (
    "transcript",
    "language",
    "speech_style",
    "phrase_bank",
    "speech_habits",
    "ng_phrases",
    "sample_lines",
)

_NAME_RE = re.compile(r"^[^\\/:*?\"<>|.][^\\/:*?\"<>|]{0,63}$")


class _BlockDumper(yaml.SafeDumper):
    """Dump multiline strings in readable block style (|-)."""


def _str_representer(dumper, value):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_BlockDumper.add_representer(str, _str_representer)


def _validate_name(name: str) -> str:
    name = (name or "").strip()
    if not _NAME_RE.match(name):
        raise ValueError(f"invalid persona name: {name!r}")
    return name


def _read_info(name: str) -> dict:
    info_path = PERSONA_DIR / name / "info.yaml"
    if not info_path.exists():
        return {}
    try:
        with open(info_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def list_voices() -> list[dict]:
    """Personas that have a reference audio, sorted by name."""
    if not PERSONA_DIR.exists():
        return []
    voices = []
    for d in sorted(PERSONA_DIR.iterdir()):
        if not d.is_dir() or not (d / "ref.wav").exists():
            continue
        info = _read_info(d.name)
        voices.append({"name": d.name, "language": info.get("language", "Auto")})
    return voices


def get(name: str) -> dict:
    """Full persona info for the editor UI."""
    name = _validate_name(name)
    d = PERSONA_DIR / name
    if not d.is_dir():
        raise ValueError(f"persona '{name}' not found")
    info = _read_info(name)
    out = {"name": name, "has_audio": (d / "ref.wav").exists()}
    for field in INFO_FIELDS:
        out[field] = info.get(field) or ""
    out["language"] = info.get("language") or "Auto"
    return out


def save(name: str, fields: dict, audio: tuple[np.ndarray, int] | None = None) -> dict:
    """Create or update a persona. `audio` replaces ref.wav when given."""
    name = _validate_name(name)
    d = PERSONA_DIR / name
    d.mkdir(parents=True, exist_ok=True)

    if audio is not None:
        data, sr = audio
        data = np.asarray(data, dtype=np.float32)
        if data.ndim > 1:
            data = data.mean(axis=1)
        sf.write(str(d / "ref.wav"), data, sr)

    info = _read_info(name)
    for field in INFO_FIELDS:
        if field in fields and fields[field] is not None:
            info[field] = fields[field]
    with open(d / "info.yaml", "w", encoding="utf-8") as f:
        yaml.dump(info, f, Dumper=_BlockDumper, allow_unicode=True, sort_keys=False)
    return get(name)


def delete(name: str):
    name = _validate_name(name)
    d = PERSONA_DIR / name
    if not d.is_dir():
        raise ValueError(f"persona '{name}' not found")
    shutil.rmtree(d)


def ref_audio_path(name: str) -> Path:
    name = _validate_name(name)
    return PERSONA_DIR / name / "ref.wav"


def load(name: str) -> dict:
    """Full persona data for generation. Raises ValueError if unusable."""
    ref_path = PERSONA_DIR / name / "ref.wav"
    if not ref_path.exists():
        raise ValueError(f"persona '{name}' not found (no ref.wav)")
    info = _read_info(name)
    transcript = (info.get("transcript") or "").strip()
    if not transcript:
        raise ValueError(f"persona '{name}' has no transcript in info.yaml")
    return {
        "ref_path": str(ref_path),
        "transcript": transcript,
        "language": info.get("language", "Auto"),
    }
