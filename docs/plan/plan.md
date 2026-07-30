# plan — 実装方針と優先順位

作成日時: 2026-07-28 10:17
更新日時: 2026-07-30 09:25

## アーキテクチャ

```
Electron main (frontend/electron/main.cjs)
  ├─ .venv の python.exe で backend/server.py を spawn (127.0.0.1:8766)
  ├─ /api/health をポーリングして起動待ち
  └─ BrowserWindow (React UI)
        └─ fetch → FastAPI
              ├─ tts_engine.py   Qwen3-TTS (Base / CustomVoice / VoiceDesign)
              ├─ asr_engine.py   Whisper large-v3-turbo (参照音声の文字起こし)
              ├─ llm_engine.py   Gemma4 12B GGUF (llama-cpp-python)
              └─ personas.py     persona/<名前>/{ref.wav, info.yaml} の管理
```

### ディレクトリ構成(予定)

```
voice-generator/
├── backend/            server.py / tts_engine.py / asr_engine.py / llm_engine.py / personas.py
├── frontend/
│   ├── electron/       main.cjs / preload.cjs / launch.cjs (sound-effect-generator から流用)
│   └── src/            App.jsx / components/ / api.js / i18n.jsx / styles.css
├── persona/            話者データ (gitignore)
├── models/             HF_HOME + GGUF (gitignore) ※gemma-4-12B-it-GGUF は配置済み
├── runtime/python/     内蔵 Python (gitignore)
├── .venv/              (gitignore)
├── data/               jobs.json / <job_id>.wav / screenshot/ (gitignore)
└── docs/
```

## 流用元と流用方法

| 流用するもの | 流用元 | 備考 |
|---|---|---|
| Electron 起動3ファイル | sound-effect-generator `frontend/electron/` | ほぼ無改造。`launch.cjs` の ELECTRON_RUN_AS_NODE 対策も含めて |
| App.jsx のレイアウト・ポーリング | 同 `frontend/src/App.jsx` | grid 2カラム、1.5秒ポーリング |
| GenerateForm / ResultCard / AudioPlayer | 同 `frontend/src/components/` | フォーム項目を TTS 用に差し替え。AudioPlayer は無改造 |
| styles.css / i18n.jsx / api.js | 同 `frontend/src/` | CSS 変数のダークテーマ、en/ja 辞書 |
| ジョブキューの骨格 | 同 `backend/server.py` | Job dataclass / 単一ワーカー / jobs.json アトミック書き込み |
| TTS 推論コード | voice-persona `server.py` `_generate_tts` | `generate_voice_clone` 周辺。qwen-tts ライブラリ |
| HF_HOME 設定・persona 管理・ASR | voice-persona `server.py` | import 前の HF_HOME 設定、info.yaml スキーマ |
| LLM の SSE ストリーミング | voice-persona `server.py:317-377` | `<think>` フィルタは Gemma では不要だが構造は流用 |

## 設計方針: モデル世代交代への対応(ユーザー決定 2026-07-28)

将来、Qwen3-TTS の後継や別系統の TTS モデルが登場した場合、**アプリの基本機能は変えずに**、モデル依存部分だけを新モデルの仕様に沿って作り変えられる状態を保って開発する。

### 変えない部分(アプリの土台)

- Electron + React + FastAPI の構成と、「左で設定 → キューに追加 → 右のカードで再生」という UX。
- 保存先フォルダの仕組みとデータ形式(jobs.json + WAV + persona/)。過去の生成物は WAV として残るので、モデルが変わっても一覧・再生は影響を受けない。
- persona 管理、Whisper 文字起こし、ステータスバー、LLM 支援などの周辺機能。
- API の基本契約: 「テキスト + 声の指定を `/api/generate` に投げると WAV ができる」。

### モデル依存として隔離する部分(将来の作り変え対象)

- `backend/tts_engine.py` — モデルID・ロード・生成メソッド呼び出し・パラメータ変換をここに集約する。server.py のキュー処理やフロントにモデル固有 API を漏らさない。
- 生成フォームの入力項目 — 方式タブ・instruct・話者一覧などはモデル仕様に依存してよい。ただし選択肢(話者一覧、モデルの present 状態など)は `health.modes` のメタデータとしてサーバーから動的配信し、フロントに固定リストをハードコードしない(現状の CustomVoice 話者一覧が config.json から動的取得なのはこの方針の実例)。
- Job の `mode` / `model_size` 等のモデル依存フィールドは記録用として保持する(表示に使うだけなので、新モデルで意味が変わっても壊れない)。

### 運用

- 新モデル対応時は、まず `tts_engine.py` の差し替え(必要なら `engines/` へのファイル分割)で成立するかを検討し、UI の変更は生成フォームの入力項目の範囲に留める。
- 事前の過剰な抽象化はしない。実際に新モデルが出た時点で、その仕様に合わせてエンジン層を書き換える(現状も Base / CustomVoice / VoiceDesign の3モデルをこの形で吸収している)。

## ジョブモデル(方式共通)

```python
@dataclass
class Job:
    id, status(queued|running|done|error), message, created_at, started_at, finished_at
    mode: "clone" | "custom" | "design"
    text: str                 # セリフ本文
    language: str             # Auto / Japanese / ...
    voice_name: str | None    # clone: persona名 / custom: プリセット話者名
    instruct: str | None      # custom / design 用の指示文
    model_size: str           # 1.7B / 0.6B (clone のみ選択可)
    title: str | None         # LLM 自動生成
    filename: str | None      # data/<id>.wav
```

## 実装フェーズと優先順位

### Phase 1 — スキャフォールド(最優先)
- Electron + React + Vite の骨格を sound-effect-generator から移植し、空の FastAPI と health チェックで起動確認。
- 内蔵 runtime のセットアップ手順(python-build-standalone → .venv → pip install)を `setup.bat` 等に整備。
- torch は CUDA ホイール(cu130 系、Blackwell 対応)を明示インストール。qwen-tts / qwen-asr / llama-cpp-python / fastapi / soundfile。
- `.gitignore`(models / runtime / .venv / data / persona)。

### Phase 2 — Voice Clone 生成の最小フロー
- `tts_engine.py`: HF_HOME 設定 → `Qwen3TTSModel.from_pretrained` の遅延ロード → `generate_voice_clone` → `soundfile.write` で WAV 保存。
- モデルは voice-persona のキャッシュ(`models/hub/models--Qwen--Qwen3-TTS-12Hz-1.7B-Base`)をコピーして再ダウンロードを回避。
- ジョブキュー(単一ワーカー)+ `POST /api/generate` + 1.5秒ポーリング + ResultCard 表示 + AudioPlayer 再生。
- persona は最初は voice-persona からコピーした固定データで動作確認。

### Phase 3 — persona 管理
- persona 一覧・登録・更新・削除 API と UI(ref.wav アップロード、info.yaml 編集)。
- ASR による参照音声の自動文字起こし + 言語判定。
  - **仕様変更(ユーザー決定)**: Qwen3-ASR ではなく **Whisper(openai/whisper-large-v3-turbo, transformers 版)** を使う。日本語精度と頑健性、既存スタック(transformers + torch cu130)でネイティブ依存なしに動く点が理由。faster-whisper(CTranslate2)は Blackwell 対応が不確実なため不採用。

### Phase 4 — CustomVoice / VoiceDesign 方式の追加
- `-CustomVoice` / `-VoiceDesign` モデルのダウンロード(各約4.3GB、初回のみ)。
- モデルレジストリ(present フラグ付き)と未ダウンロード時のバナー表示(sound-effect-generator 方式)。
- サイドバーの方式切替 UI(clone / custom / design でフォーム項目が変わる)。
- `generate_custom_voice(text, speaker, language, instruct)` / `generate_voice_design(text, instruct, language)` の実装。

### Phase 5 — Gemma4 支援機能
- `llm_engine.py`: llama-cpp-python で `gemma-4-12B-it-Q4_K_M.gguf` をロード(`n_gpu_layers=-1`)。
- セリフ生成支援: persona の口調プロファイル + シーン指示 → SSE ストリーミングでフォームに流し込み。
- テキスト整形・読み修正: 入力テキストを TTS 向けに変換するボタン。
- タイトル自動生成: ワーカー内で best-effort 実行(失敗しても生成は止めない)。

### Phase 6 — 磨き込み
- キャンセル機構(生成中ジョブの中断)、進捗表示の改善。
- 長文対応: 文・段落単位の自動分割 → 連続生成 → 連結 WAV(検討記録は docs/design/voice-guide.md の 3.7 参照。Phase 5 の LLM 整形と組み合わせると効果大)。
- VRAM 管理: TTS(bf16 約5GB)+ Gemma4 Q4_K_M(約8GB)+ ASR の同時常駐は VRAM を圧迫するため、エンジン単位の load/unload UI(sound-effect-generator の EngineToggle 方式)を整備。
- ~~同一話者の連続生成高速化(`voice_clone_prompt` の再利用)~~ → 実装済み(2026-07-30)。計測の結果、削減できたのは1件あたり 60〜100ms 程度で、生成時間の大半は talker の自己回帰ループだった(progress.md 参照)。
- i18n(en/ja)、F12 スクリーンショット、配布方式の検討。

## 技術的な注意点(調査で判明済みのハマりどころ)

1. **HF_HOME は qwen_tts / transformers の import より前に設定する**(遅れると `~/.cache/huggingface` に落ちる)。
2. **`ref_audio` は `(ndarray, sample_rate)` の順**。逆にすると壊れる(Gradio は逆順で渡してくる)。
3. **モデル型とメソッドは 1:1**。`-Base` は `generate_voice_clone` のみ。型が違うと ValueError。
4. **Voice Clone は `ref_text`(参照音声の文字起こし)が実質必須**。省略するなら `x_vector_only_mode=True`。
5. **TTS 出力は 24kHz モノラル float の ndarray**。WAV 保存は soundfile(Windows の torchaudio は WAV 保存不可)。
6. **qwen-tts 0.1.1 は transformers==4.57.3 をピン**しているが、4.57.6 でも動作実績あり(voice-persona)。
7. **Flask/FastAPI とも GPU 推論は直列化必須**(単一ワーカー + Lock)。
8. **ELECTRON_RUN_AS_NODE 問題**: VS Code 統合ターミナルから起動すると Electron が素の Node になる → `launch.cjs` で対策。
9. **jobs.json は tmp ファイル + `os.replace()` でアトミック書き込み**。
10. Blackwell GPU(sm_120)では torch の CUDA ビルド指定(cu128 以上)が必須。
