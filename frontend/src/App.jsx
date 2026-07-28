import { useEffect, useState, useCallback } from "react";
import { api } from "./api.js";
import GenerateForm from "./components/GenerateForm.jsx";
import PersonaManager from "./components/PersonaManager.jsx";
import ResultCard from "./components/ResultCard.jsx";
import { useI18n, LANGS } from "./i18n.jsx";

export default function App() {
  const { t, lang, setLang } = useI18n();
  const [health, setHealth] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [voices, setVoices] = useState([]);
  const [error, setError] = useState(null);
  // Sidebar width grows as the text gets longer (set by GenerateForm).
  const [formWidth, setFormWidth] = useState(380);
  // A request to load a card's settings back into the form.
  const [copyRequest, setCopyRequest] = useState(null);
  const [showPersonas, setShowPersonas] = useState(false);
  // Where generated results are stored ({path, default, is_default}).
  const [dataDir, setDataDir] = useState(null);

  // Load/unload a resident model from the top-bar toggles. We flip health
  // optimistically so the pill reacts immediately; the next poll reconciles.
  const handleEngineToggle = useCallback(async (name, loaded) => {
    const action = loaded ? "unload" : "load";
    setHealth((h) =>
      h ? { ...h, [`${name}_loading`]: action === "load" } : h
    );
    try {
      await api.setEngine(name, action);
      api.health().then(setHealth).catch(() => {});
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const handleCopyToForm = useCallback((job) => {
    setCopyRequest({
      mode: job.mode,
      text: job.text,
      language: job.language,
      voice_name: job.voice_name,
      instruct: job.instruct,
      model_size: job.model_size,
      _ts: Date.now(), // ensure the effect re-runs even for identical values
    });
  }, []);

  const refreshJobs = useCallback(async () => {
    try {
      const list = await api.listJobs();
      setJobs(list);
      setError(null);
    } catch (e) {
      // Stored as a key so it follows the current language at render time.
      setError("connectError");
    }
  }, []);

  const refreshVoices = useCallback(async () => {
    try {
      const { voices: list } = await api.listVoices();
      setVoices(list);
    } catch {
      /* backend down; ignore */
    }
  }, []);

  const refreshDataDir = useCallback(async () => {
    try {
      setDataDir(await api.getDataDir());
    } catch {
      /* backend down; ignore */
    }
  }, []);

  // Switch the data folder, then reload the result list from the new location.
  const handleDataDirChange = useCallback(
    async (path) => {
      try {
        setDataDir(await api.setDataDir(path));
        setError(null);
        await refreshJobs();
      } catch (e) {
        // Stored as a key so it follows the current language at render time.
        setError(
          e.message?.includes("jobs_in_progress") ? "dataDirBusy" : e.message
        );
      }
    },
    [refreshJobs]
  );

  // Initial health check + polling loop for live job updates.
  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    refreshJobs();
    refreshVoices();
    refreshDataDir();
    const timer = setInterval(() => {
      refreshJobs();
      refreshVoices();
      api.health().then(setHealth).catch(() => {});
    }, 1500);
    return () => clearInterval(timer);
  }, [refreshJobs, refreshVoices, refreshDataDir]);

  const handleSubmit = async (params) => {
    try {
      await api.createJob(params);
      await refreshJobs();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleDelete = async (id) => {
    try {
      await api.deleteJob(id);
      setJobs((prev) => prev.filter((j) => j.id !== id));
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Voice Generator</h1>
          <p className="subtitle">{t("subtitle")}</p>
        </div>
        <div className="status">
          <select
            className="lang-select"
            value={lang}
            onChange={(e) => setLang(e.target.value)}
            title={t("language")}
          >
            {LANGS.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>
          <EngineToggle
            label="LLM"
            loaded={!!health?.llm_loaded}
            loading={!!health?.llm_loading}
            present={health?.llm_present ?? false}
            online={!!health}
            onToggle={() => handleEngineToggle("llm", health?.llm_loaded)}
          />
          <EngineToggle
            label="TTS"
            loaded={!!health?.tts_loaded}
            loading={!!health?.tts_loading}
            present={health?.tts_present ?? false}
            online={!!health}
            onToggle={() => handleEngineToggle("tts", health?.tts_loaded)}
          />
        </div>
      </header>

      {error && (
        <div className="banner error">
          {["connectError", "dataDirBusy"].includes(error) ? t(error) : error}
        </div>
      )}

      <main
        className="layout"
        style={{ gridTemplateColumns: `${formWidth}px 1fr` }}
      >
        <section className="panel form-panel">
          <h2>{t("genSettings")}</h2>
          <DataDirField info={dataDir} onChange={handleDataDirChange} />
          <GenerateForm
            onSubmit={handleSubmit}
            modes={health?.modes}
            online={!!health}
            voices={voices}
            onWidthHint={setFormWidth}
            applyValues={copyRequest}
            onManageVoices={() => setShowPersonas(true)}
          />
        </section>

        <section className="panel results-panel">
          {jobs.length === 0 ? (
            <p className="empty">{t("empty")}</p>
          ) : (
            <div className="card-list">
              {jobs.map((job) => (
                <ResultCard
                  key={job.id}
                  job={job}
                  onDelete={handleDelete}
                  onCopyToForm={handleCopyToForm}
                />
              ))}
            </div>
          )}
        </section>
      </main>

      {showPersonas && (
        <PersonaManager
          voices={voices}
          onClose={() => setShowPersonas(false)}
          onChanged={refreshVoices}
        />
      )}
    </div>
  );
}

// Shows where generated results are stored and lets the user point the app at
// another folder (keeping data separate from the app itself). The native picker
// comes from Electron; in a plain browser we fall back to typing a path.
// Collapsed by default (it is a set-once setting) — the folder name stays
// visible in the header so the current location is readable at a glance.
function DataDirField({ info, onChange }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(
    () => localStorage.getItem("dataDirOpen") === "1"
  );

  useEffect(() => {
    localStorage.setItem("dataDirOpen", open ? "1" : "0");
  }, [open]);

  if (!info) return null;

  const desktop = typeof window !== "undefined" ? window.__DESKTOP__ : null;
  const folderName =
    info.path.split(/[\\/]/).filter(Boolean).pop() || info.path;

  const pick = async () => {
    const picked = desktop
      ? await desktop.pickFolder(info.path)
      : window.prompt(t("dataDir"), info.path);
    if (picked && picked !== info.path) onChange(picked);
  };

  return (
    <div className="model-field data-dir-field">
      <button
        type="button"
        className="collapse-head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        title={t("dataDirHelp")}
      >
        <span className={`chevron ${open ? "open" : ""}`}>▸</span>
        <span>{t("dataDir")}</span>
        {!open && (
          <span className="collapse-preview" title={info.path}>
            {folderName}
          </span>
        )}
      </button>
      {open && (
        <>
          <input
            className="path-box"
            readOnly
            value={info.path}
            title={info.path}
          />
          <div className="data-dir-actions">
            <button type="button" className="mini-btn" onClick={pick}>
              {t("browse")}
            </button>
            {desktop && (
              <button
                type="button"
                className="mini-btn"
                onClick={() => desktop.openPath(info.path)}
              >
                {t("openFolder")}
              </button>
            )}
            {!info.is_default && (
              <button
                type="button"
                className="mini-btn"
                onClick={() => onChange("")}
                title={info.default}
              >
                {t("useDefault")}
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// A compact on/off pill for a resident model (LLM / TTS). Green dot =
// loaded, grey = off, pulsing amber = loading. Click toggles load/unload.
function EngineToggle({ label, loaded, loading, present, online, onToggle }) {
  const { t } = useI18n();
  const disabled = !online || !present || loading;
  const cls = loading ? "loading" : loaded ? "on" : "off";
  const title = !online
    ? t("backendOffline")
    : !present
    ? t("engineMissing")
    : loading
    ? t("engineLoading")
    : loaded
    ? t("engineUnloadHint")
    : t("engineLoadHint");
  return (
    <button
      type="button"
      className={`engine-toggle ${cls}`}
      onClick={onToggle}
      disabled={disabled}
      title={title}
      aria-pressed={loaded}
    >
      <span className="et-dot" />
      {label}
    </button>
  );
}
