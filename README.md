# rts-video-flow

スマホで撮った素材から、字幕・文字起こし・動画用データを作る軽量パイプラインです。

限界開発Vlogでは、YouTube運用を重労働にしないため、**スクリーンショット中心・短い画面収録・自動字幕**を基本にします。

## 現在できること

- iPhoneの外カメラ動画を素材として受け取る
- iPhone標準の短い画面収録を受け取る
- スクリーンショットをファイル名順で収集する
- Whisperで日本語を文字起こしする
- 日本語字幕を読みやすい単位へ分割する
- YouTubeへ登録できるSRT字幕を出力する
- Vlog素材のmanifest.jsonを生成する
- 公開前のプライバシー確認表を生成する
- 既存の無音カット・Remotion準備処理を利用する

## Vlog MVPの使い方

### 1. 初回セットアップ

```bash
./scripts/setup.sh
```

### 2. プロジェクトを作る

`projects/vlog-template`を参考に、次の構成で素材を置きます。

```text
projects/vlog-001/
├── camera/       # iPhone外カメラ動画
├── screen/       # 短い画面収録。省略可
└── screenshots/  # 通常の作業記録
```

例:

```text
camera/01-opening.mov
screenshots/01-spec.png
screenshots/02-github.png
screenshots/03-test.png
screen/01-short-demo.mov
```

### 3. 一括処理

```bash
./scripts/process_vlog.sh projects/vlog-001
```

生成物:

```text
output/vlog-001/
├── manifest.json
├── subtitles.srt
├── transcript.md
└── NEXT_STEPS.md
```

最初のMVPは、誤公開を防ぐため**自動投稿の直前で止まります**。`NEXT_STEPS.md`を確認してから、レンダリング・投稿へ進みます。

## 運用方針

- 画面収録は機能デモや動作証拠に限り、短時間だけ使う
- 日常の作業記録はスクリーンショットを基本にする
- 通知、DM、メール、個人情報、APIキー、非公開URLを映さない
- 動画制作そのものではなく、開発記録から動画を作る
- YouTubeは限界開発の本体ではなく、ブランドと実在性を補強する出力先とする

## 既存の個別処理

### 無音カット

```bash
./venv/bin/python3 scripts/jumpcut.py
```

### 文字起こし

```bash
./venv/bin/python3 scripts/transcribe.py \
  --input temp/voice_audio.wav \
  --output temp/whisper_result.json
```

### 字幕分割

```bash
./venv/bin/python3 scripts/segment_subtitles.py \
  --input temp/whisper_result.json \
  --output temp/subtitles.json
```

### SRT出力

```bash
./venv/bin/python3 scripts/subtitles_to_srt.py \
  --input temp/subtitles.json \
  --output output/subtitles.srt
```

### Remotion準備

```bash
./venv/bin/python3 scripts/prepare_remotion.py
```

## 仕様

- [Vlog MVP仕様書](docs/VLOG_MVP_SPEC.md)

## 次の実装

1. manifest.jsonを直接読むRemotion Vlogテンプレート
2. 外カメラ → スクショ → 短い画面収録 → 締め動画の自動結合
3. スクショの軽いパン・ズーム
4. タイトル・概要欄・note下書き生成
5. 実素材を使った第1回ドッグフーディング
