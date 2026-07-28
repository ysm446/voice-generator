# HF_HOME must point into the project BEFORE transformers/qwen_tts are
# imported (directly or transitively), or models land in ~/.cache/huggingface.
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("HF_HOME", str(ROOT / "models"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# Windows without Developer Mode cannot create symlinks (WinError 1314) and
# huggingface_hub's probe misdetects it here — force the copy path so
# runtime downloads work.
import huggingface_hub.file_download as _fd

_fd.are_symlinks_supported = lambda *a, **k: False

import argparse
import io
import json
import queue
import shutil
import tempfile
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass

import numpy as np
import soundfile as sf
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import asr_engine
import llm_engine
import personas
import tts_engine

DEFAULT_DATA_DIR = ROOT / "data"

# ---------------------------------------------------------------- app config
# Records *where* the data folder is (plus future app-level settings), so it
# lives next to the code — never inside the data folder it points at.
APP_CONFIG_FILE = ROOT / "app-config.json"
_CONFIG_LOCK = threading.Lock()


def _read_json_dict(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


APP_CONFIG = _read_json_dict(APP_CONFIG_FILE)


def save_app_config():
    with _CONFIG_LOCK:
        tmp = APP_CONFIG_FILE.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(APP_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, APP_CONFIG_FILE)


def resolve_data_dir(raw: str | None) -> Path:
    """Turn a configured/requested path into an absolute data folder path."""
    if not raw or not str(raw).strip():
        return DEFAULT_DATA_DIR
    p = Path(str(raw).strip()).expanduser()
    if not p.is_absolute():
        p = ROOT / p
    return Path(os.path.normpath(p))


def _init_data_dir() -> Path:
    """Use the configured folder, falling back to data/ if unusable.

    The configured folder can live on a drive that is not present right now,
    so a failure here must not stop the server from starting.
    """
    configured = resolve_data_dir(APP_CONFIG.get("data_dir"))
    try:
        configured.mkdir(parents=True, exist_ok=True)
        return configured
    except OSError as exc:
        print(f"[data] cannot use {configured} ({exc}); falling back to default")
        DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
        return DEFAULT_DATA_DIR


DATA_DIR = _init_data_dir()


def jobs_file() -> Path:
    # Follows the (switchable) data folder, hence a function.
    return DATA_DIR / "jobs.json"


# Personas live inside the (switchable) data folder; late-bound so a data
# folder switch is picked up immediately.
personas.configure(lambda: DATA_DIR)

# One-time layout migration: personas used to live at <project>/persona.
# They belong to the data, so move them into the default data folder.
_LEGACY_PERSONA_DIR = ROOT / "persona"
if _LEGACY_PERSONA_DIR.is_dir() and not (DEFAULT_DATA_DIR / "persona").exists():
    try:
        DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(_LEGACY_PERSONA_DIR), str(DEFAULT_DATA_DIR / "persona"))
        print(f"[personas] moved {_LEGACY_PERSONA_DIR} -> {DEFAULT_DATA_DIR / 'persona'}")
    except OSError as exc:
        print(f"[personas] legacy migration failed: {exc}")


app = FastAPI(title="voice-generator backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # localhost-only app
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- job store

@dataclass
class Job:
    id: str
    mode: str  # clone | custom | design
    text: str
    language: str
    voice_name: str | None
    instruct: str | None
    model_size: str
    title: str | None = None
    status: str = "queued"  # queued | running | done | error
    message: str = ""
    created_at: float = 0.0
    started_at: float | None = None
    finished_at: float | None = None
    filename: str | None = None


JOBS: dict[str, Job] = {}
JOBS_LOCK = threading.Lock()
WORK_QUEUE: "queue.Queue[str]" = queue.Queue()
_SAVE_LOCK = threading.Lock()


def save_jobs():
    """Atomic snapshot of all jobs. Call OUTSIDE JOBS_LOCK."""
    with JOBS_LOCK:
        payload = [asdict(j) for j in JOBS.values()]
    with _SAVE_LOCK:
        target = jobs_file()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        os.replace(tmp, target)


def load_jobs():
    """Replace the in-memory job list with the one in the data folder."""
    src = jobs_file()
    payload = []
    if src.exists():
        try:
            with open(src, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            payload = []
    if not isinstance(payload, list):
        payload = []
    restored: dict[str, Job] = {}
    for item in payload:
        try:
            job = Job(**item)
        except TypeError:
            continue
        if job.status == "done":
            # Drop orphaned metadata whose audio file is gone.
            if not job.filename or not (DATA_DIR / job.filename).exists():
                continue
        elif job.status in ("queued", "running"):
            job.status = "error"
            job.message = "Interrupted by app shutdown"
        restored[job.id] = job
    with JOBS_LOCK:
        JOBS.clear()
        JOBS.update(restored)


# ---------------------------------------------------------------- worker

def _worker():
    while True:
        job_id = WORK_QUEUE.get()
        with JOBS_LOCK:
            job = JOBS.get(job_id)
        if job is None:  # deleted while queued
            continue
        job.status = "running"
        job.started_at = time.time()
        job.message = "starting..."
        save_jobs()

        def progress(msg: str):
            job.message = msg

        out_path = DATA_DIR / f"{job.id}.wav"
        try:
            audio, sr = tts_engine.generate(
                mode=job.mode,
                text=job.text,
                language=job.language,
                voice_name=job.voice_name,
                instruct=job.instruct,
                model_size=job.model_size,
                progress=progress,
            )
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tts_engine.save_wav(audio, sr, str(out_path))
            job.filename = out_path.name
            job.status = "done"
            job.message = ""
            job.finished_at = time.time()
        except Exception as e:
            traceback.print_exc()
            job.status = "error"
            job.message = str(e) or type(e).__name__
            job.finished_at = time.time()
        finally:
            with JOBS_LOCK:
                deleted = job.id not in JOBS
            if deleted and out_path.exists():
                try:
                    out_path.unlink()
                except OSError:
                    pass
            save_jobs()


threading.Thread(target=_worker, daemon=True).start()


# ---------------------------------------------------------------- engines

ENGINE_LOADING = {"tts": False, "llm": False}


def _engine_load_async(name: str):
    def run():
        try:
            if name == "tts":
                tts_engine.load("clone", "1.7B")
            else:
                llm_engine.load()
        except Exception:
            traceback.print_exc()
        finally:
            ENGINE_LOADING[name] = False

    ENGINE_LOADING[name] = True
    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------- API

class GenerateRequest(BaseModel):
    mode: str = Field(pattern="^(clone|custom|design)$")
    text: str = Field(min_length=1, max_length=4000)
    language: str = "Auto"
    voice_name: str | None = None
    instruct: str | None = None
    model_size: str = "1.7B"


class EngineRequest(BaseModel):
    action: str = Field(pattern="^(load|unload)$")


@app.get("/api/health")
def health():
    import torch

    return {
        "status": "ok",
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "modes": tts_engine.modes_summary(),
        "tts_present": tts_engine.any_present(),
        "tts_loaded": tts_engine.loaded_any(),
        "tts_loading": ENGINE_LOADING["tts"],
        "llm_present": llm_engine.present(),
        "llm_loaded": llm_engine.loaded(),
        "llm_loading": ENGINE_LOADING["llm"],
        "queue_size": WORK_QUEUE.qsize(),
        "data_dir": str(DATA_DIR),
    }


def _data_dir_state() -> dict:
    return {
        "path": str(DATA_DIR),
        "default": str(DEFAULT_DATA_DIR),
        "is_default": DATA_DIR == DEFAULT_DATA_DIR,
    }


class DataDirRequest(BaseModel):
    # Empty/None means "go back to the default data/ folder".
    path: str | None = None


@app.get("/api/datadir")
def get_data_dir():
    return _data_dir_state()


@app.post("/api/datadir")
def set_data_dir(req: DataDirRequest):
    """Point the app at another data folder.

    Nothing is moved or copied: the new folder is read as-is (its own
    jobs.json + WAVs become the visible result list), and the old one is
    left untouched.
    """
    global DATA_DIR
    new_dir = resolve_data_dir(req.path)
    if new_dir == DATA_DIR:
        return _data_dir_state()

    # Switching under a running/queued job would orphan its WAV in the old
    # folder, so require an idle queue.
    with JOBS_LOCK:
        busy = any(j.status in ("queued", "running") for j in JOBS.values())
    if busy:
        raise HTTPException(409, "jobs_in_progress")

    try:
        new_dir.mkdir(parents=True, exist_ok=True)
        probe = new_dir / ".write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise HTTPException(400, f"{type(exc).__name__}: {exc}")

    DATA_DIR = new_dir
    APP_CONFIG["data_dir"] = "" if new_dir == DEFAULT_DATA_DIR else str(new_dir)
    save_app_config()
    load_jobs()  # show whatever the new folder already holds
    return _data_dir_state()


def _read_audio_upload(file_bytes: bytes) -> tuple[np.ndarray, int]:
    """Read uploaded audio bytes, return (mono float32, sample_rate)."""
    try:
        data, sr = sf.read(io.BytesIO(file_bytes), always_2d=False)
        return np.asarray(data, dtype=np.float32), sr
    except Exception:
        pass
    # Fallback via torchaudio (handles WebM/Opus, MP3, M4A, ...).
    import torchaudio

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(file_bytes)
        tmp_path = f.name
    try:
        waveform, sr = torchaudio.load(tmp_path)
        return waveform.mean(0).numpy().astype(np.float32), sr
    finally:
        os.unlink(tmp_path)


@app.get("/api/voices")
def list_voices():
    return {"voices": personas.list_voices()}


@app.get("/api/voices/{name}")
def get_voice(name: str):
    try:
        return personas.get(name)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/api/voices")
async def save_voice(
    name: str = Form(...),
    new_name: str | None = Form(None),
    transcript: str | None = Form(None),
    language: str | None = Form(None),
    speech_style: str | None = Form(None),
    phrase_bank: str | None = Form(None),
    speech_habits: str | None = Form(None),
    ng_phrases: str | None = Form(None),
    sample_lines: str | None = Form(None),
    audio: UploadFile | None = File(None),
):
    audio_data = None
    if audio is not None:
        raw = await audio.read()
        if raw:
            try:
                audio_data = _read_audio_upload(raw)
            except Exception as e:
                raise HTTPException(422, f"could not read audio file: {e}")
    fields = {
        "transcript": transcript,
        "language": language,
        "speech_style": speech_style,
        "phrase_bank": phrase_bank,
        "speech_habits": speech_habits,
        "ng_phrases": ng_phrases,
        "sample_lines": sample_lines,
    }
    try:
        if new_name and new_name.strip() and new_name.strip() != name:
            name = personas.rename(name, new_name.strip())
        saved = personas.save(name, fields, audio_data)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not saved["has_audio"]:
        raise HTTPException(422, "reference audio (ref.wav) is required for a new persona")
    return saved


@app.delete("/api/voices/{name}")
def delete_voice(name: str):
    try:
        personas.delete(name)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}


@app.get("/api/voices/{name}/audio")
def get_voice_audio(name: str):
    try:
        path = personas.ref_audio_path(name)
    except ValueError as e:
        raise HTTPException(404, str(e))
    if not path.exists():
        raise HTTPException(404, "ref.wav not found")
    return FileResponse(path, media_type="audio/wav")


@app.post("/api/transcribe")
async def transcribe(
    audio: UploadFile | None = File(None),
    voice_name: str | None = Form(None),
):
    """Whisper-transcribe an uploaded file, or a persona's existing ref.wav."""
    if audio is not None:
        raw = await audio.read()
        if not raw:
            raise HTTPException(422, "empty audio upload")
        try:
            data, sr = _read_audio_upload(raw)
        except Exception as e:
            raise HTTPException(422, f"could not read audio file: {e}")
    elif voice_name:
        try:
            path = personas.ref_audio_path(voice_name)
        except ValueError as e:
            raise HTTPException(404, str(e))
        if not path.exists():
            raise HTTPException(404, "ref.wav not found")
        data, sr = sf.read(str(path), always_2d=False)
        data = np.asarray(data, dtype=np.float32)
    else:
        raise HTTPException(422, "audio file or voice_name is required")
    try:
        return asr_engine.transcribe(data, sr)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"transcription failed: {e}")


@app.post("/api/engine/{name}")
def set_engine(name: str, req: EngineRequest):
    if name not in ("tts", "llm"):
        raise HTTPException(404, "unknown engine")
    if ENGINE_LOADING[name]:
        raise HTTPException(409, "engine is loading")
    if req.action == "load":
        _engine_load_async(name)
    else:
        (tts_engine.unload_all if name == "tts" else llm_engine.unload)()
    return {"ok": True}


@app.post("/api/generate")
def generate(req: GenerateRequest):
    if req.mode == "clone" and not req.voice_name:
        raise HTTPException(422, "voice_name is required for clone mode")
    if req.mode == "design" and not (req.instruct or "").strip():
        raise HTTPException(422, "instruct is required for design mode")
    if req.mode == "custom" and not (req.voice_name or "").strip():
        raise HTTPException(422, "voice_name (speaker) is required for custom mode")
    model_id = tts_engine.resolve_model_id(req.mode, req.model_size)
    if not tts_engine.model_present(model_id):
        raise HTTPException(409, f"model not downloaded: {model_id}")

    job = Job(
        id=uuid.uuid4().hex[:12],
        mode=req.mode,
        text=req.text.strip(),
        language=req.language,
        voice_name=req.voice_name,
        instruct=(req.instruct or "").strip() or None,
        model_size=req.model_size,
        created_at=time.time(),
    )
    with JOBS_LOCK:
        JOBS[job.id] = job
    save_jobs()
    WORK_QUEUE.put(job.id)
    return asdict(job)


@app.get("/api/jobs")
def list_jobs():
    with JOBS_LOCK:
        jobs = sorted(JOBS.values(), key=lambda j: j.created_at, reverse=True)
        return [asdict(j) for j in jobs]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return asdict(job)


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.pop(job_id, None)
    if job is None:
        raise HTTPException(404, "job not found")
    for name in filter(None, {job.filename, f"{job_id}.wav"}):
        p = DATA_DIR / name
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    save_jobs()
    return {"ok": True}


@app.get("/api/audio/{job_id}")
def get_audio(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None or not job.filename:
        raise HTTPException(404, "audio not found")
    path = DATA_DIR / job.filename
    if not path.exists():
        raise HTTPException(404, "audio file missing")
    return FileResponse(path, media_type="audio/wav")


# ---------------------------------------------------------------- entrypoint

load_jobs()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
