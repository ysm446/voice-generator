import { useState, useRef, useEffect } from "react";
import { useI18n } from "../i18n.jsx";

// Values accepted by Qwen3-TTS's `language` argument.
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

const MODES = [
  { key: "clone", labelKey: "modeClone" },
  { key: "custom", labelKey: "modeCustom" },
  { key: "design", labelKey: "modeDesign" },
];

const DEFAULTS = {
  mode: "clone",
  text: "",
  language: "Auto",
  voice_name: "",
  speaker: "",
  instruct: "",
  model_size: "1.7B",
};

export default function GenerateForm({
  onSubmit,
  modes,
  online,
  voices,
  onWidthHint,
  applyValues,
  onManageVoices,
}) {
  const { t } = useI18n();
  // The speech language is a sticky preference: restore the last-used value.
  const [form, setForm] = useState(() => {
    const saved = localStorage.getItem("speechLang");
    return {
      ...DEFAULTS,
      language: SPEECH_LANGS.includes(saved) ? saved : DEFAULTS.language,
    };
  });
  const taRef = useRef(null);

  useEffect(() => {
    localStorage.setItem("speechLang", form.language);
  }, [form.language]);

  // Default the persona selection to the first available voice; also reset it
  // when the list no longer contains it (e.g. after a data folder switch).
  useEffect(() => {
    if (voices.length === 0) return;
    if (!form.voice_name || !voices.some((v) => v.name === form.voice_name)) {
      setForm((f) => ({ ...f, voice_name: voices[0].name }));
    }
  }, [voices, form.voice_name]);

  // Same for the preset speaker list (CustomVoice).
  const speakers = modes?.custom?.speakers ?? [];
  useEffect(() => {
    if (!form.speaker && speakers.length > 0) {
      setForm((f) => (f.speaker ? f : { ...f, speaker: speakers[0] }));
    }
  }, [speakers, form.speaker]);

  // Load a card's settings into the form (triggered from a result card menu).
  useEffect(() => {
    if (!applyValues) return;
    setForm((f) => ({
      ...f,
      mode: applyValues.mode ?? f.mode,
      text: applyValues.text ?? f.text,
      language: applyValues.language ?? f.language,
      voice_name:
        (applyValues.mode === "custom"
          ? f.voice_name
          : applyValues.voice_name) ?? f.voice_name,
      speaker:
        (applyValues.mode === "custom" ? applyValues.voice_name : f.speaker) ??
        f.speaker,
      instruct: applyValues.instruct ?? f.instruct,
      model_size: applyValues.model_size ?? f.model_size,
    }));
  }, [applyValues]);

  // Auto-grow the text box to fit its content, and ask the parent to widen
  // the sidebar as the number of (wrapped) lines increases.
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${ta.scrollHeight}px`;
    const rows = Math.round(ta.scrollHeight / 22);
    const width = Math.min(560, Math.max(380, 380 + (rows - 3) * 26));
    onWidthHint?.(width);
  }, [form.text, onWidthHint]);

  const update = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }));
  };

  const modeInfo = modes?.[form.mode];
  const modeReady = !!modeInfo?.present;
  const needsVoice = form.mode === "clone" && !form.voice_name;
  const needsSpeaker = form.mode === "custom" && !form.speaker.trim();
  const needsInstruct = form.mode === "design" && !form.instruct.trim();
  const disabled = !online || !modeReady;

  const submit = (e) => {
    e.preventDefault();
    if (!form.text.trim() || needsVoice || needsSpeaker || needsInstruct) return;
    onSubmit({
      mode: form.mode,
      text: form.text.trim(),
      language: form.language,
      voice_name:
        form.mode === "clone"
          ? form.voice_name
          : form.mode === "custom"
          ? form.speaker.trim()
          : null,
      instruct: form.mode === "clone" ? null : form.instruct.trim() || null,
      model_size: form.model_size,
    });
  };

  return (
    <form onSubmit={submit} className="gen-form">
      <div className="mode-tabs" role="tablist">
        {MODES.map((m) => (
          <button
            key={m.key}
            type="button"
            role="tab"
            aria-selected={form.mode === m.key}
            className={`mode-tab${form.mode === m.key ? " active" : ""}`}
            onClick={() => setForm((f) => ({ ...f, mode: m.key }))}
          >
            {t(m.labelKey)}
            {modes && !modes[m.key]?.present ? t("notDownloaded") : ""}
          </button>
        ))}
      </div>

      {form.mode === "clone" && (
        <label>
          <span className="label-row">
            {t("voice")}
            <button
              type="button"
              className="suggest-btn"
              onClick={onManageVoices}
            >
              ⚙ {t("personaManage")}
            </button>
          </span>
          <select
            className="model-select"
            value={form.voice_name}
            onChange={update("voice_name")}
          >
            {voices.length === 0 && <option value="">{t("noVoices")}</option>}
            {voices.map((v) => (
              <option key={v.name} value={v.name}>
                {v.name}
              </option>
            ))}
          </select>
        </label>
      )}

      {form.mode === "custom" && (
        <label>
          {t("speaker")}
          <select
            className="model-select"
            value={form.speaker}
            onChange={update("speaker")}
          >
            {!form.speaker && <option value="" />}
            {(modes?.custom?.speakers ?? []).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      )}

      {(form.mode === "custom" || form.mode === "design") && (
        <label>
          {t("instruct")}
          <textarea
            rows={2}
            value={form.instruct}
            onChange={update("instruct")}
            placeholder={t("instructPh")}
            required={form.mode === "design"}
          />
        </label>
      )}

      <label>
        {t("text")}
        <textarea
          ref={taRef}
          rows={3}
          value={form.text}
          onChange={update("text")}
          placeholder={t("textPh")}
          required
        />
      </label>

      <label>
        {t("speechLang")}
        <select
          className="model-select"
          value={form.language}
          onChange={update("language")}
        >
          {SPEECH_LANGS.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
      </label>

      {form.mode === "clone" && (
        <label>
          {t("modelSize")}
          <select
            className="model-select"
            value={form.model_size}
            onChange={update("model_size")}
          >
            <option value="1.7B">1.7B</option>
            <option value="0.6B">0.6B</option>
          </select>
        </label>
      )}

      <button type="submit" className="primary" disabled={disabled}>
        {t("addToQueue")}
      </button>
      {online && !modeReady && <p className="hint">{t("modeMissing")}</p>}
      {!online && <p className="hint">{t("notReady")}</p>}
    </form>
  );
}
