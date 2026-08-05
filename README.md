# rts-video-flow

スマホで撮った素材から、字幕・文字起こし・動画を作る軽量Vlogパイプラインです。

限界開発Vlogでは、YouTube運用を重労働にしないため、**短いインカメラ動画・短い画面収録・スクリーンショット・後入れ音声・自動字幕**を基本にします。

## 現在の位置づけ

通常の操作、素材管理、構成編集、軽い処理はOracle Cloud上のVlog Consoleで行います。

Oracleの能力不足で重い書き出しが完走できない場合だけ、Google Cloud Run Jobへ処理を逃がせる非常用オーバーフロー経路を用意しています。

Google Cloudは通常基盤ではありません。

- 自動では切り替えない
- 毎回Security Gateを通す
- 毎回料金と影響を表示する
- 毎回1回限りの明示承認を取る
- 同時実行1、再試行なしを基本とする
- Cloud workerの失敗でOracleのUIを停止させない

## 絶対ゲート

外部入力、クラウド処理、課金、外部変更を伴う処理は必ず次の順序を通します。

```text
Security Gate
→ Cost / Consequence Gate
→ Explicit Single-Use Approval
→ Scoped Execution
→ Outcome Verification + Audit
```

Security Gate前の素材をCloud Run、外部AI、公開処理、実行コマンドへ渡してはいけません。

詳細：[`docs/SECURITY_COST_APPROVAL_FLOW.md`](docs/SECURITY_COST_APPROVAL_FLOW.md)

## Vlog Console

素材を追加し、スマートフォン画面から順番、役割、後入れ音声、表示時間、字幕、書き出しを操作します。

通常の構成画面はOracle上のWeb Consoleです。

ローカルCLIを使う場合：

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

## Security Gate

非常用クラウド処理へ入れる前に、ローカルで次を実行します。

```bash
python3 scripts/media_security_gate.py input-001.mp4 --output temp/security-pass.json
```

この処理は、許可形式、ファイル名、サイズ、構造、ストリーム、解像度、フレームレート、尺を確認し、入力SHA-256へ紐づく`SECURITY_PASS`を生成します。

- symlink拒否
- 安全でないファイル名拒否
- allowlist外の形式拒否
- 最大512MiB
- `ffprobe`タイムアウト30秒
- 添付・data・subtitle・不明ストリーム拒否
- 動画/画像ストリームは1つのみ
- 判定不能・プローブ失敗は拒否

ファイル名は検査前に内部生成ASCII IDへ変更します。

## Cost Gate

Security Gate合格後にだけ、クラウド処理の条件と料金上限を表示します。

```bash
python3 scripts/cloud_cost_gate.py \
  --security-pass temp/security-pass.json \
  --project rts-vlog-render \
  --region asia-northeast1 \
  --bucket rts-vlog-render-files-20260805 \
  --job rts-vlog-render \
  --input-bytes <SECURITY_PASS内の合計値> \
  --cpu 1 \
  --memory-gib 1 \
  --timeout-seconds 600 \
  --task-count 1 \
  --estimated-max-yen <上限額>
```

`--approve`なしでは承認ファイルを発行しません。`--approve`付きでも、最後に`YES`を手入力しない限り止まります。

承認はSecurity fingerprint、入力ハッシュ、プロジェクト、リージョン、バケット、Job、CPU、メモリ、時間、タスク数、料金上限へ固定されます。

## Cloud Run worker

Cloud workerはGCSから素材を落とした後、実行前にもう一度ハッシュと構造を確認します。

許可された境界：

```text
bucket: rts-vlog-render-files-20260805
manifests/
inputs/
outputs/
```

別バケット、別prefix、パストラバーサル、hash不一致、未承認stream、既存出力への上書きを拒否します。

FFmpegはshell経由ではなく引数配列で起動し、stdin無効、1 thread、10分timeout、metadata/chapter除去で実行します。

> 現在Artifact Registryにある`cost-gated-v1`はSecurity Gate強化前のイメージです。再ビルド・Job更新・最小テストが終わるまで実行対象にしません。

## 初回セットアップ

```bash
bash scripts/setup.sh
```

## 手動で回す場合

```bash
bash scripts/process_vlog.sh projects/vlog-001
```

公開前チェック後に通常環境で動画を書き出します。

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
- 映像を見ながら後入れ音声を録音する
- 元音声を切り、後入れ音声を映像尺へ合わせる
- Whisperで日本語を文字起こしする
- 日本語字幕を読みやすい単位へ分割する
- YouTube用SRT字幕を出力する
- Remotionで動画を書き出す
- 公開前のプライバシー確認表を生成する
- Security GateとCost Gateを通した非常用Cloud Run Jobを準備する

## 運用方針

- 画面収録は機能デモや動作証拠に限り、短時間だけ使う
- 日常の作業記録はスクリーンショットを基本にする
- 通知、DM、メール、個人情報、APIキー、非公開URLを映さない
- 動画制作そのものではなく、開発記録から動画を作る
- YouTubeは限界開発の本体ではなく、ブランドと実在性を補強する出力先とする
- 自動投稿はせず、人間の公開前確認を残す
- 未検査素材をクラウド実行環境へ渡さない
- 課金・外部処理は毎回の明示承認なしに動かさない

## 仕様

- [Vlog MVP仕様書](docs/VLOG_MVP_SPEC.md)
- [後入れ音声仕様](docs/SCREENSHOT_NARRATION_SPEC.md)
- [Security / Cost / Approval Flow](docs/SECURITY_COST_APPROVAL_FLOW.md)

## 次の確認

1. Security GateとCost Gateの全ローカルテストを通す
2. 小さな正常動画で`SECURITY_PASS`を生成する
3. 危険な名前、異常stream、hash差し替えを拒否する
4. 新しいworker imageを、改めて上限額を確認して1回だけbuildする
5. Cloud Run Jobを新imageへ更新するが実行しない
6. 最小素材1件について、上限額と影響を表示し、明示承認後に1回だけ実行する
7. 出力、ログ、実時間、実費、一時ファイル削除を確認する
8. 実行結果を基準に仕様書、状態、変更履歴を最終置換する
