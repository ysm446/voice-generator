// Thin client for the Python FastAPI backend.
// The backend host/port can be overridden by the Electron main process via a
// global injected on window; otherwise we default to localhost:8765.
const API_BASE =
  (typeof window !== "undefined" && window.__API_BASE__) ||
  "http://127.0.0.1:8766";

async function jsonOrThrow(res) {
  if (!res.ok) {
    let detail;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text();
    }
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail?.detail ?? detail)
    );
  }
  return res.json();
}

export const api = {
  base: API_BASE,

  health() {
    return fetch(`${API_BASE}/api/health`).then(jsonOrThrow);
  },

  listVoices() {
    return fetch(`${API_BASE}/api/voices`).then(jsonOrThrow);
  },

  getVoice(name) {
    return fetch(`${API_BASE}/api/voices/${encodeURIComponent(name)}`).then(
      jsonOrThrow
    );
  },

  // formData: name + info fields + optional `audio` file.
  saveVoice(formData) {
    return fetch(`${API_BASE}/api/voices`, {
      method: "POST",
      body: formData,
    }).then(jsonOrThrow);
  },

  deleteVoice(name) {
    return fetch(`${API_BASE}/api/voices/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }).then(jsonOrThrow);
  },

  voiceAudioUrl(name) {
    return `${API_BASE}/api/voices/${encodeURIComponent(name)}/audio`;
  },

  // formData: `audio` file, or `voice_name` for an existing persona.
  transcribe(formData) {
    return fetch(`${API_BASE}/api/transcribe`, {
      method: "POST",
      body: formData,
    }).then(jsonOrThrow);
  },

  getDataDir() {
    return fetch(`${API_BASE}/api/datadir`).then(jsonOrThrow);
  },

  // path = null/"" resets to the default data/ folder.
  setDataDir(path) {
    return fetch(`${API_BASE}/api/datadir`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    }).then(jsonOrThrow);
  },

  setEngine(name, action) {
    return fetch(`${API_BASE}/api/engine/${name}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    }).then(jsonOrThrow);
  },

  suggest(idea) {
    return fetch(`${API_BASE}/api/suggest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idea }),
    }).then(jsonOrThrow);
  },

  createJob(params) {
    return fetch(`${API_BASE}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    }).then(jsonOrThrow);
  },

  listJobs() {
    return fetch(`${API_BASE}/api/jobs`).then(jsonOrThrow);
  },

  deleteJob(id) {
    return fetch(`${API_BASE}/api/jobs/${id}`, { method: "DELETE" }).then(
      jsonOrThrow
    );
  },

  audioUrl(id) {
    return `${API_BASE}/api/audio/${id}`;
  },
};
