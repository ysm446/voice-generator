# progress — 進捗と注意点

作成日時: 2026-07-28 10:17
更新日時: 2026-07-28 16:10

## 現在の状態

**Phase 1〜4 完了(3方式の生成 + persona 管理 + Whisper 文字起こし)。残りは Phase 5(LLM 支援)と Phase 6(磨き込み)。**

## 完了済み

- 2026-07-28: 流用元2リポジトリの調査完了(sound-effect-generator / voice-persona)。
- 2026-07-28: 基本方針を決定(ユーザー確認済み)。3方式対応 / LLM支援3機能 / 内蔵runtime / WAV保存。
- 2026-07-28: goals.md / plan.md / progress.md を作成。
- 2026-07-28: **Phase 1 完了** — スキャフォールド一式。
  - `runtime/python/`(Python 3.10.20)を sound-effect-generator からコピーし `.venv` 構築。
  - 依存導入済み: torch 2.10.0+cu130(CUDA動作確認済)/ qwen-tts 0.1.1 / qwen-asr / transformers 4.57.6 / llama-cpp-python 0.3.16(CUDA対応、pipキャッシュのローカルビルドwheelを再利用)/ fastapi / soundfile / PyYAML。
  - frontend(Electron + React + Vite)を移植し voice-generator 用に書き換え。
- 2026-07-28: **Phase 2 完了** — Voice Clone 最小フロー。
  - `backend/server.py`(FastAPI + 単一ワーカーのジョブキュー + jobs.json 永続化)。
  - `backend/tts_engine.py`(3方式のモデルレジストリ / 遅延ロード / 生成ディスパッチ)。
  - `backend/personas.py`(persona 一覧・読込)/ `backend/llm_engine.py`(Gemma4 load/unload のみ)。
  - モデルキャッシュ(TTS 1.7B-Base, ASR 1.7B)と persona 3件(Shigeru/Shinjiro/Shinzo)を voice-persona からコピー。
  - **動作確認済み**: 日本語テキスト → Voice Clone 生成(初回28秒、モデルロード込み)→ WAV 保存 → UI のカード表示・波形再生。UI スクリーンショット確認済み。
  - フォームは3方式のタブ切替を実装済み(custom/design は「未DL」表示で無効化)。

- 2026-07-28: **Phase 4 完了** — CustomVoice / VoiceDesign。
  - 両モデル(各約3.8GB)を `models/` にダウンロード。**Windows の symlink 権限問題(WinError 1314)のため、huggingface_hub の `are_symlinks_supported` を False に固定してコピー方式で取得**(再取得は `backend/download_models.py` を使うこと)。
  - プリセット話者9名を CustomVoice の config.json(`talker_config.spk_id`)から動的取得し、health の `modes.custom.speakers` で配信。フォームは選択式。
    - 話者: aiden / dylan(北京方言) / eric(四川方言) / ono_anna / ryan / serena / sohee / uncle_fu / vivian
  - 生成テスト済み: custom(ono_anna + instruct)5.8秒 / design(instruct のみ)6.6秒の日本語音声を確認。

- 2026-07-28: **Phase 3 完了** — persona 管理 + Whisper 文字起こし。
  - **仕様変更(ユーザー決定)**: ASR は Qwen3-ASR ではなく **Whisper(openai/whisper-large-v3-turbo)** を採用。
  - `backend/asr_engine.py`: transformers pipeline + `model.detect_language` による言語判定(パイプラインの `return_language` はチャンクの language が None になり使えなかった)。
  - persona CRUD API(GET/POST/DELETE `/api/voices`、`/api/voices/{name}/audio`、`POST /api/transcribe`)。multipart 用に python-multipart 追加。
  - アップロード音声は soundfile → torchaudio フォールバックで読み込み(WebM/MP3等も可)。
  - `PersonaManager.jsx`: モーダル UI(一覧・新規作成・参照音声アップロード・Whisper 文字起こしボタン・言語・キャラ設定折りたたみ・保存/削除)。クローンタブの「⚙管理」から開く。
  - テスト済み: 既存/アップロード音声の文字起こし(言語判定 Japanese 確認)、persona 新規作成→一覧反映→削除、モーダル UI 表示。
  - `server.py` 起動時に huggingface_hub の symlink 判定を無効化(実行時ダウンロードも安全に)。

- 2026-07-28: **保存先フォルダの分離** — sound-effect-generator の同機能(abfb2df / 1ffdede)を移植。
  - `/api/datadir` GET/POST。設定は `app-config.json`(コード側・gitignore 済)に保存。デフォルトは `data/`。
  - 切替は読み替えのみ(移動・コピー・削除なし)。ジョブ実行中は 409 で拒否。起動時に設定先が使えなければ `data/` にフォールバック。
  - UI は生成条件の上の折りたたみ行(DataDirField)。Electron IPC(`__DESKTOP__`)でネイティブフォルダ選択とエクスプローラー表示。F12/AUTO_SCREENSHOT のスクリーンショットも保存先に追従。
  - `E:\sample files\voice-generator\sample` で確認済み: 切替→既存 jobs.json 読込(5件)→音声配信→新規生成が同フォルダに保存→既定へ復帰、すべて成功。

- 2026-07-28: **persona を保存先フォルダ直下に移動(ユーザー決定)**。
  - `personas.py` の場所解決を動的化(`persona_dir()` = `<保存先>/persona`。server が `personas.configure()` で注入)。
  - 旧配置(プロジェクト直下 `persona/`)は server 起動時に `data/persona/` へ一度だけ自動移行(`shutil.move`)。
  - フォルダ切替時に選択中の persona が無くなった場合はフォームの選択を先頭にリセット。
  - `start.bat` は毎回 UI をビルドするように変更(古い dist が使われる事故の防止)。
  - 検証済み: 切替で persona 一覧が追従、sample 側での clone 生成、既定復帰。

- 2026-07-28: **persona 管理画面の改善** — 名前のリネーム(`personas.rename` + `POST /api/voices` の `new_name`)、参照音声のドラッグ&ドロップ対応。リネーム API・重複名拒否・UI 表示を確認済み。
- 2026-07-28: **音声の言語を記憶** — 生成フォームの言語選択を localStorage(`speechLang`)に保存し起動時に復元。不正値は Auto にフォールバック。

## 未完了(次にやること)

- Phase 5: Gemma4 支援機能(セリフ生成 SSE / テキスト整形 / タイトル自動生成)← **次はここから**。llm_engine の load/unload だけ実装済み。
- Phase 6: 磨き込み(キャンセル・VRAM 管理・配布)
- メモ: qwen-asr パッケージと Qwen3-ASR モデルキャッシュ(`models/hub/models--Qwen--Qwen3-ASR-1.7B`, 約4GB)は不要になったので削除してよい。

## 環境メモ(このマシン固有)

- GPU: NVIDIA RTX PRO 5000 Blackwell(compute capability 12.0)。torch は cu130 ビルド必須。
- **ポート**: backend **8766** / Vite dev **5174**(sound-effect-generator が 8765/5173 を使用中のため衝突回避)。
- 起動: `dev.bat`(開発・ホットリロード)/ `start.bat`(ビルド版)。
- `AUTO_SCREENSHOT=1` を設定して起動すると、ウィンドウ表示5秒後に `data/screenshot/` へ自動でスクリーンショットを保存(エージェントの UI 確認用。手動は F12)。

## 注意点

- 技術的なハマりどころは [plan.md](plan.md) 末尾に集約。実装時に必ず参照すること。
- **pip の依存解決**: qwen-tts(transformers==4.57.3 ピン)と qwen-asr(==4.57.6 ピン)は同時インストール不可。qwen-tts → qwen-asr の順に段階インストールする(backend/requirements.txt 冒頭に手順記載)。
- llama-cpp-python の CUDA 対応 wheel は PyPI に無い。pip キャッシュのローカルビルド wheel(cp310)を再利用した。再構築時は `CMAKE_ARGS="-DGGML_CUDA=on"` でビルドが必要。
- persona の language が設定されている場合、フォームで「Auto」を選ぶと persona 側の言語設定を優先する仕様(tts_engine.generate)。
- qwen-tts のモデルは方式(Base/CustomVoice/VoiceDesign)ごとに生成メソッドが排他。ロード済みモデルは `_models` dict に共存できる(VRAM 48GB 級のため当面問題なし)。
