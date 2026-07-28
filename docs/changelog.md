# Changelog

作成日時: 2026-07-28 11:59
更新日時: 2026-07-28 15:26

## 未リリース

### 2026-07-28 15:26 — 保存先フォルダの分離

- 生成結果(WAV と結果一覧)の保存先フォルダを UI から変更できるようにした(生成条件の上の折りたたみ行)。デフォルトは `data/`。
- 切替はフォルダの読み替えのみで、既存データの移動・削除は行わない。生成中は切替不可。
- ネイティブのフォルダ選択ダイアログと「エクスプローラーで開く」に対応(Electron IPC)。

### 2026-07-28 13:13 — persona 管理と Whisper 文字起こし(Phase 3)

- ボイスクローンの声(persona)をアプリ内で登録・編集・削除できる管理画面を追加(クローンタブの「⚙管理」から)。
- 参照音声のアップロード(WAV/MP3/WebM 等)と、Whisper(large-v3-turbo)による自動文字起こし+言語判定を追加。
- キャラ設定(話し方・口癖・NG表現など、今後の LLM セリフ生成用)の編集欄を追加。

### 2026-07-28 12:31 — CustomVoice / VoiceDesign 対応(Phase 4)

- プリセット話者方式(CustomVoice)とボイスデザイン方式(VoiceDesign)のモデルを導入し、3方式すべてで生成可能に。
- プリセット話者9名(aiden / dylan / eric / ono_anna / ryan / serena / sohee / uncle_fu / vivian)をモデル設定から自動取得し、選択式 UI で提供。

### 2026-07-28 11:59 — 初期実装(Phase 1 + 2)

- Electron + React + Vite + FastAPI の骨格を構築(sound-effect-generator ベース)。
- Qwen3-TTS による Voice Clone 生成の最小フローを実装。
  - 左サイドバーで方式(ボイスクローン/プリセット話者/ボイスデザイン)・声(persona)・テキスト・言語・モデルサイズを設定し、生成キューに追加。
  - 右側リストに生成結果カード(波形プレイヤー・ダウンロード・削除・フォームにコピー)。
  - 出力は WAV(24kHz PCM_16)、`data/` に保存。
- persona 3件(Shigeru/Shinjiro/Shinzo)と TTS/ASR モデルキャッシュを voice-persona から取り込み。
- LLM(Gemma4 12B GGUF)のロード/アンロードのトグルをヘッダーに実装(支援機能自体は未実装)。
- ポートは backend 8766 / Vite dev 5174(sound-effect-generator との同時起動に対応)。
