import { createContext, useContext, useState, useEffect } from "react";

// Selectable UI languages. Backend-originated text (generation progress,
// error messages from the server) is left as-is.
export const LANGS = [
  { code: "en", label: "English" },
  { code: "ja", label: "日本語" },
];

const STRINGS = {
  en: {
    subtitle: "Qwen3-TTS · Local generation",
    language: "Language",
    notDownloaded: " (not downloaded)",
    device: "Device",
    notLoaded: "not loaded",
    backendOffline: "Backend offline",
    engineLoadHint: "Off — click to load into memory",
    engineUnloadHint: "Loaded — click to unload",
    engineLoading: "Loading…",
    engineMissing: "Model files not available",
    missingFiles: "Missing model files:",
    genSettings: "Generation settings",
    empty: 'No generations yet. Set the options on the left and click "Add to queue".',
    connectError: "Cannot connect to the backend. Check that the server is running.",

    modeLabel: "Method",
    modeClone: "Voice Clone",
    modeCustom: "Preset speaker",
    modeDesign: "Voice Design",
    modeMissing: "The model for this method is not downloaded yet.",

    text: "Text",
    textPh: "Text to speak (e.g. こんにちは、今日はいい天気ですね)",
    voice: "Voice (persona)",
    noVoices: "No personas registered",
    speaker: "Speaker",
    instruct: "Voice / style instruction",
    instructPh: "e.g. A deep, husky middle-aged male voice, speaking slowly",
    speechLang: "Speech language",
    modelSize: "Model size",

    addToQueue: "+ Add to queue",
    notReady: "Model not ready, generation unavailable.",

    personaManage: "Manage",
    personaTitle: "Personas",
    personaNew: "+ New persona",
    personaName: "Name",
    refAudio: "Reference audio",
    refAudioHint: "5-20s of clean speech recommended",
    transcribeBtn: "Transcribe (Whisper)",
    transcribing: "Transcribing…",
    transcript: "Transcript (ref text)",
    charProfile: "Character profile (for LLM, optional)",
    speechStyle: "Speaking style",
    phraseBank: "Phrase bank",
    speechHabits: "Speech habits",
    ngPhrases: "NG phrases",
    sampleLines: "Sample lines",
    save: "Save",
    saving: "Saving…",
    confirmDelete: "Delete this persona? Its reference audio will be removed.",
    close: "Close",
    newPersonaNeedsAudio: "A reference audio file is required for a new persona.",

    statusQueued: "Queued",
    statusRunning: "Generating",
    statusDone: "Done",
    statusError: "Error",
    menu: "Menu",
    copyToForm: "Copy to form",
    download: "Download",
    delete: "Delete",

    play: "Play",
    pause: "Pause",
    seek: "Click / drag to seek",
    mute: "Mute",
    unmute: "Unmute",
    volume: "Volume",
    loop: "Loop",
  },
  ja: {
    subtitle: "Qwen3-TTS · ローカル生成",
    language: "言語",
    notDownloaded: "（未DL）",
    device: "デバイス",
    notLoaded: "未ロード",
    backendOffline: "バックエンド停止中",
    engineLoadHint: "オフ — クリックでメモリに読み込み",
    engineUnloadHint: "読み込み済み — クリックで解放",
    engineLoading: "読み込み中…",
    engineMissing: "モデルファイルがありません",
    missingFiles: "モデルファイルが不足しています:",
    genSettings: "生成条件",
    empty: "まだ生成タスクがありません。左で条件を設定して「生成キューに追加」してください。",
    connectError: "バックエンドに接続できません。サーバーが起動しているか確認してください。",

    modeLabel: "生成方式",
    modeClone: "ボイスクローン",
    modeCustom: "プリセット話者",
    modeDesign: "ボイスデザイン",
    modeMissing: "この方式のモデルは未ダウンロードです。",

    text: "テキスト",
    textPh: "話させたいテキスト（例: こんにちは、今日はいい天気ですね）",
    voice: "声（persona）",
    noVoices: "persona が登録されていません",
    speaker: "話者",
    instruct: "声・話し方の指示",
    instructPh: "例: 低くて渋い中年男性の声で、ゆっくり落ち着いて話す",
    speechLang: "音声の言語",
    modelSize: "モデルサイズ",

    addToQueue: "＋ 生成キューに追加",
    notReady: "モデル未準備のため生成できません。",

    personaManage: "管理",
    personaTitle: "Persona 管理",
    personaNew: "＋ 新規作成",
    personaName: "名前",
    refAudio: "参照音声",
    refAudioHint: "5〜20秒のクリアな音声を推奨",
    transcribeBtn: "文字起こし (Whisper)",
    transcribing: "文字起こし中…",
    transcript: "文字起こし（参照テキスト）",
    charProfile: "キャラ設定（LLM用・任意）",
    speechStyle: "話し方プロファイル",
    phraseBank: "言い回し集",
    speechHabits: "口癖",
    ngPhrases: "NG表現",
    sampleLines: "サンプル台詞",
    save: "保存",
    saving: "保存中…",
    confirmDelete: "この persona を削除しますか？参照音声も削除されます。",
    close: "閉じる",
    newPersonaNeedsAudio: "新規作成には参照音声ファイルが必要です。",

    statusQueued: "待機中",
    statusRunning: "生成中",
    statusDone: "完了",
    statusError: "エラー",
    menu: "メニュー",
    copyToForm: "フォームにコピー",
    download: "ダウンロード",
    delete: "削除",

    play: "再生",
    pause: "一時停止",
    seek: "クリック/ドラッグでシーク",
    mute: "ミュート",
    unmute: "ミュート解除",
    volume: "音量",
    loop: "ループ再生",
  },
};

const I18nContext = createContext(null);

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(() => {
    const saved = localStorage.getItem("lang");
    return STRINGS[saved] ? saved : "ja";
  });

  useEffect(() => {
    localStorage.setItem("lang", lang);
    document.documentElement.lang = lang;
  }, [lang]);

  // Look up a key in the current language, falling back to English, then the
  // key itself (so a missing translation is visible rather than blank).
  const t = (key) => STRINGS[lang]?.[key] ?? STRINGS.en[key] ?? key;

  return (
    <I18nContext.Provider value={{ lang, setLang, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
