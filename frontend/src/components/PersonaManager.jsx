import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useI18n } from "../i18n.jsx";

const SPEECH_LANGS = [
  "Auto",
  "Japanese",
  "English",
  "Chinese",
  "Korean",
  "German",
  "French",
  "Russian",
  "Portuguese",
  "Spanish",
  "Italian",
];

const EMPTY = {
  name: "",
  transcript: "",
  language: "Auto",
  speech_style: "",
  phrase_bank: "",
  speech_habits: "",
  ng_phrases: "",
  sample_lines: "",
};

// Modal for creating/editing personas (reference audio + transcript +
// character profile). Mounted by App while open.
export default function PersonaManager({ voices, onClose, onChanged }) {
  const { t } = useI18n();
  const [selected, setSelected] = useState(null); // persona name, null = new
  const [form, setForm] = useState(EMPTY);
  const [audioFile, setAudioFile] = useState(null);
  const [busy, setBusy] = useState(null); // "saving" | "transcribing" | null
  const [error, setError] = useState(null);
  // Bumped after save so the <audio> src cache-busts.
  const [audioRev, setAudioRev] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef(null);

  // While the modal is open, keep a stray drop (outside the drop zone) from
  // making the window navigate to the file.
  useEffect(() => {
    const prevent = (e) => e.preventDefault();
    window.addEventListener("dragover", prevent);
    window.addEventListener("drop", prevent);
    return () => {
      window.removeEventListener("dragover", prevent);
      window.removeEventListener("drop", prevent);
    };
  }, []);

  const selectPersona = async (name) => {
    setError(null);
    setAudioFile(null);
    if (fileRef.current) fileRef.current.value = "";
    if (!name) {
      setSelected(null);
      setForm(EMPTY);
      return;
    }
    try {
      const info = await api.getVoice(name);
      setSelected(name);
      setForm({ ...EMPTY, ...info });
    } catch (e) {
      setError(e.message);
    }
  };

  // Close on Escape.
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const update = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }));
  };

  const handleTranscribe = async () => {
    setError(null);
    const fd = new FormData();
    if (audioFile) {
      fd.append("audio", audioFile);
    } else if (selected) {
      fd.append("voice_name", selected);
    } else {
      return;
    }
    setBusy("transcribing");
    try {
      const { text, language } = await api.transcribe(fd);
      setForm((f) => ({
        ...f,
        transcript: text || f.transcript,
        language: language !== "Auto" ? language : f.language,
      }));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  const handleSave = async () => {
    setError(null);
    const newName = form.name.trim();
    if (!newName) return;
    if (!selected && !audioFile) {
      setError(t("newPersonaNeedsAudio"));
      return;
    }
    const fd = new FormData();
    // For an existing persona `name` is the current directory; a differing
    // edited name goes in `new_name` and renames it on the server.
    fd.append("name", selected || newName);
    if (selected && newName !== selected) fd.append("new_name", newName);
    for (const [key, value] of Object.entries(form)) {
      if (key === "name") continue;
      fd.append(key, value ?? "");
    }
    if (audioFile) fd.append("audio", audioFile);
    setBusy("saving");
    try {
      const saved = await api.saveVoice(fd);
      setAudioRev((r) => r + 1);
      setAudioFile(null);
      if (fileRef.current) fileRef.current.value = "";
      setSelected(saved.name);
      onChanged?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  const handleDelete = async () => {
    if (!selected) return;
    if (!window.confirm(t("confirmDelete"))) return;
    setError(null);
    try {
      await api.deleteVoice(selected);
      onChanged?.();
      selectPersona(null);
    } catch (e) {
      setError(e.message);
    }
  };

  const canTranscribe = (audioFile || selected) && !busy;

  return (
    <div className="modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-head">
          <h2>{t("personaTitle")}</h2>
          <button type="button" className="modal-close" onClick={onClose} title={t("close")}>
            ✕
          </button>
        </div>

        <div className="persona-layout">
          <div className="persona-list">
            <button
              type="button"
              className={`persona-item${selected === null ? " active" : ""}`}
              onClick={() => selectPersona(null)}
            >
              {t("personaNew")}
            </button>
            {voices.map((v) => (
              <button
                key={v.name}
                type="button"
                className={`persona-item${selected === v.name ? " active" : ""}`}
                onClick={() => selectPersona(v.name)}
              >
                {v.name}
              </button>
            ))}
          </div>

          <div className="persona-editor gen-form">
            <label>
              {t("personaName")}
              <input
                type="text"
                value={form.name}
                onChange={update("name")}
                placeholder="e.g. Hanako"
              />
            </label>

            <label>
              <span className="label-row">
                {t("refAudio")}
                <span className="hint-inline">{t("refAudioHint")}</span>
              </span>
            </label>
            <div
              className={`drop-zone${dragOver ? " over" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                const f = e.dataTransfer.files?.[0];
                if (f) setAudioFile(f);
              }}
              onClick={() => fileRef.current?.click()}
              role="button"
              tabIndex={0}
            >
              {audioFile ? `🎵 ${audioFile.name}` : t("dropHint")}
              <input
                ref={fileRef}
                type="file"
                accept="audio/*"
                style={{ display: "none" }}
                onChange={(e) => setAudioFile(e.target.files?.[0] ?? null)}
              />
            </div>
            {selected && !audioFile && (
              <audio
                controls
                className="persona-audio"
                src={`${api.voiceAudioUrl(selected)}?rev=${audioRev}`}
              />
            )}
            {selected &&
              form.ref_path &&
              typeof window !== "undefined" &&
              window.__DESKTOP__ && (
                <div className="persona-audio-actions">
                  <button
                    type="button"
                    className="mini-btn"
                    onClick={() => window.__DESKTOP__.showItem(form.ref_path)}
                    title={form.ref_path}
                  >
                    📂 {t("openFileLocation")}
                  </button>
                </div>
              )}

            <label>
              <span className="label-row">
                {t("transcript")}
                <button
                  type="button"
                  className="suggest-btn"
                  onClick={handleTranscribe}
                  disabled={!canTranscribe}
                >
                  {busy === "transcribing" ? t("transcribing") : `🎙 ${t("transcribeBtn")}`}
                </button>
              </span>
              <textarea rows={3} value={form.transcript} onChange={update("transcript")} />
            </label>

            <label>
              {t("speechLang")}
              <select className="model-select" value={form.language} onChange={update("language")}>
                {SPEECH_LANGS.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </label>

            <details className="persona-profile">
              <summary>{t("charProfile")}</summary>
              {[
                ["speech_style", "speechStyle"],
                ["phrase_bank", "phraseBank"],
                ["speech_habits", "speechHabits"],
                ["ng_phrases", "ngPhrases"],
                ["sample_lines", "sampleLines"],
              ].map(([key, labelKey]) => (
                <label key={key}>
                  {t(labelKey)}
                  <textarea rows={2} value={form[key]} onChange={update(key)} />
                </label>
              ))}
            </details>

            {error && <p className="card-error">{error}</p>}

            <div className="persona-actions">
              <button
                type="button"
                className="primary"
                onClick={handleSave}
                disabled={!form.name.trim() || busy}
              >
                {busy === "saving" ? t("saving") : t("save")}
              </button>
              {selected && (
                <button type="button" className="btn-danger" onClick={handleDelete} disabled={!!busy}>
                  {t("delete")}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
