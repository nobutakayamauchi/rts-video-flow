# rts-video-flow

スマホで撮った素材から、字幕・文字起こし・動画を作る軽量Vlogパイプラインです。

限界開発Vlogでは、YouTube運用を重労働にしないため、**短いインカメラ動画・短い画面収録・スクリーンショット・自動字幕**を基本にします。

## 一番簡単な使い方：Vlog Console

素材を1つのフォルダへ入れて、対話形式で順番を指定します。

```bash
python3 scripts/vlog_console.py
```

コンソールで次を順番に選べます。

- プロジェクト名
- 素材フォルダ
- オープニング動画
- 画面収録
- 差し込むスクリーンショットと順番
- エンディング動画
- スクリーンショット1枚の表示秒数
- 字幕生成まで実行するか
- 最終動画を書き出すか

コンソールが素材を整理し、`vlog-plan.json`へ明示的なタイムラインを保存します。

```text
オープニング
↓
画面収録
↓
スクリーンショット
↓
エンディング
```

順番はコンソールで選んだ内容が優先されます。

### 素材の置き方

例えば、Oracle Cloud上に次のフォルダを作り、iPhoneから動画と画像を送ります。

```text
inbox/vlog-001/
├── opening.mov
├── screen.mov
├── ending.mov
├── screenshot-01.png
└── screenshot-02.png
```

その後、`python3 scripts/vlog_console.py`を実行するだけです。

## 初回セットアップ

```bash
bash scripts/setup.sh
```

## 手動で回す場合

```bash
bash scripts/process_vlog.sh projects/vlog-001
```

公開前チェック後に動画を書き出します。

```bash
bash scripts/render_vlog.sh vlog-001
```

完成動画：

```text
output/vlog-001/vlog.mp4
```

## 生成物

```text
output/vlog-001/
├── manifest.json
├── subtitles.srt
├── transcript.md
├── NEXT_STEPS.md
└── vlog.mp4
```

## 現在できること

- iPhoneのインカメラ・外カメラ動画を読み込む
- iPhone標準の画面収録を読み込む
- スクリーンショットの順番と表示時間を指定する
- オープニング・画面収録・画像・エンディングを明示的に並べる
- Whisperで日本語を文字起こしする
- 日本語字幕を読みやすい単位へ分割する
- YouTube用SRT字幕を出力する
- Remotionで1920×1080の動画を書き出す
- 公開前のプライバシー確認表を生成する

## 運用方針

- 画面収録は機能デモや動作証拠に限り、短時間だけ使う
- 日常の作業記録はスクリーンショットを基本にする
- 通知、DM、メール、個人情報、APIキー、非公開URLを映さない
- 動画制作そのものではなく、開発記録から動画を作る
- YouTubeは限界開発の本体ではなく、ブランドと実在性を補強する出力先とする
- 自動投稿はせず、人間の公開前確認を残す

## 仕様

- [Vlog MVP仕様書](docs/VLOG_MVP_SPEC.md)

## 次の確認

実際のiPhone素材をコンソールへ通し、次を確認します。

1. 3本の動画と画像を正しい順で結合できるか
2. 字幕の時間がオープニング以外の素材でもずれないか
3. 縦動画を横長フレームへ自然に配置できるか
4. Oracle CloudのCPU・メモリでレンダリング可能か
5. 操作手数が本当に少ないか
