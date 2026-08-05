# rts-video-flow

スマホで撮った素材から、字幕・文字起こし・動画を作る軽量Vlogパイプラインです。

限界開発Vlogでは、YouTube運用を重労働にしないため、**短いインカメラ動画・短い画面収録・スクリーンショット・後入れ音声・自動字幕**を基本にします。

## 現在の位置づけ

通常の操作、素材管理、構成編集、軽い処理はOracle Cloud上のVlog Consoleで行います。

Oracleの能力不足で重い書き出しが完走できない場合だけ、Google Cloud Run Jobへ処理を逃がせる非常用オーバーフロー経路を用意しています。

Google Cloudは通常基盤ではありません。

- 自動では切り替えない
- 毎回Security Gateを通す
- Cost Gate直前に元ファイルを再読込し、サイズとSHA-256を再検証する
- 毎回料金と影響を表示する
- 毎回1回限りの明示承認を取る
- 同時実行1、再試行なしを基本とする
- Cloud workerの失敗でOracleのUIを停止させない

## 絶対ゲート

外部入力、クラウド処理、課金、外部変更を伴う処理は必ず次の順序を通します。

```text
Security Gate
→ Local Hash Revalidation
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

Cost GateはSecurity Passの期限、ポリシー、合計サイズを確認したうえで、各ローカル素材を再読込します。

- 元ファイル消失を拒否
- symlinkへの差し替えを拒否
- サイズ変更を拒否
- 同サイズの内容差し替えをSHA-256不一致で拒否

正常時は`local_hash_revalidated: true`を表示します。

`--approve`なしでは承認ファイルを発行しません。`--approve`付きでも、最後に`YES`を手入力しない限り止まります。

承認はSecurity fingerprint、入力ハッシュ、プロジェクト、リージョン、バケット、Job、CPU、メモリ、時間、タスク数、料金上限へ固定されます。

## ローカル安全経路の検証状況

Oracle上で合成テスト動画と拒否用サンプルを使い、次を確認済みです。

- 正常な1秒MP4からSecurity Passを生成
- 危険なファイル名を拒否
- allowlist外拡張子を拒否
- 壊れたMP4を拒否
- サイズ不一致、期限切れ、不正ポリシーを拒否
- 元ファイル消失、symlink、サイズ変更を拒否
- 同サイズの内容差し替えをSHA-256で拒否
- 実ファイル再ハッシュ後、承認手前で安全停止
- Security Gate＋Cost Gateの自動テスト：`14 passed`

この検証ではCloud Build、Cloud Run、GCS実行、課金処理は行っていません。

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
- 課金前に元ファイルの同一性をローカルで再確認する

## 運用方針

- 画面収録は機能デモや動作証拠に限り、短時間だけ使う
- 日常の作業記録はスクリーンショットを基本にする
- 通知、DM、メール、個人情報、APIキー、非公開URLを映さない
- 動画制作そのものではなく、開発記録から動画を作る
- YouTubeは限界開発の本体ではなく、ブランドと実在性を補強する出力先とする
- 自動投稿はせず、人間の公開前確認を残す
- 未検査素材をクラウド実行環境へ渡さない
- 課金・外部処理は毎回の明示承認なしに動かさない
- Build承認とRender承認を分離し、片方の承認をもう片方へ流用しない

## 仕様

- [Vlog MVP仕様書](docs/VLOG_MVP_SPEC.md)
- [後入れ音声仕様](docs/SCREENSHOT_NARRATION_SPEC.md)
- [Security / Cost / Approval Flow](docs/SECURITY_COST_APPROVAL_FLOW.md)
- [Cloud Render Cost Gate v1](docs/specs/VLOG_CLOUD_RENDER_COST_GATE_V1.md)
- [Current Status](docs/STATUS.md)

## 次の確認

1. Security Gate入りの新しいworker imageについて、タグ、buildコマンド、料金上限を表示する
2. Cloud Buildを1回だけ行う明示承認を取る
3. 新imageを確認し、Cloud Run Jobの参照imageだけ更新する
4. Jobを実行せず設定を確認する
5. 合成素材1件を隔離GCS領域へ準備する
6. 別途、最小renderの料金上限と影響を表示し、1回限りの承認を取る
7. 出力、ログ、SHA-256、実時間、実費、承認消費、重複実行拒否、一時ファイル削除を確認する
8. 実行結果を基準に仕様書、状態、変更履歴を最終更新する
