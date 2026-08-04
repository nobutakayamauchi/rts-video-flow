# Vlog Composition, Output, and Trash UI v1

Date: 2026-08-04

Status: USER_DIRECTION_APPROVED / IMPLEMENTATION_DRAFT / HUMAN_REVIEW_REQUIRED

## 1. Purpose

Replace the current flat material-management screen with a mobile-first Vlog editing structure that matches the actual narrative flow:

1. opening
2. body content
3. ending
4. output and review

The UI must clearly separate:

- source materials;
- editing settings;
- generated cuts and final videos;
- recoverable trash;
- permanent deletion.

The user must be able to record or attach narration, review it, apply the changes, render a preview or final video, delete generated output by cut or in bulk, and restore accidentally deleted items.

## 2. Safety and product boundaries

This specification does not authorize:

- automatic upload or publishing;
- platform automation;
- unattended background media processing;
- storing credentials or private links;
- permanent deletion without explicit confirmation;
- treating an old final video as current after a source or edit change.

All rendered media remains a local review artifact until a human explicitly reviews it.

## 3. Core information architecture

The primary navigation is:

```text
1. 構成
2. 音声
3. 字幕
4. 書き出し
```

The main editing structure is:

```text
Vlog project
├─ オープニング
├─ 本編
│  ├─ 素材カード 1
│  ├─ 素材カード 2
│  └─ 素材カード N
├─ エンディング
└─ 書き出し・生成物
```

The UI has two editing levels:

1. **Composition overview** — shows the entire Vlog structure and output state.
2. **Material detail** — edits one source material without overloading the overview.

## 4. Screen A: Composition overview

### 4.1 Header

The header shows:

- project name;
- current step;
- unsaved or stale-output warning;
- link to trash;
- link to output management.

### 4.2 Opening section

Opening is displayed as one primary card.

The card shows:

- thumbnail or video preview;
- source file name;
- current audio mode;
- narration state;
- subtitle state;
- output freshness;
- `編集する`;
- `素材を差し替える`;
- `構成から削除`.

### 4.3 Body section

Body materials are displayed as repeatable ordered cards.

Each body card shows:

- sequence number;
- material type;
- preview;
- file name;
- description;
- source / narration / mute state;
- range narration count;
- subtitle state;
- generated-cut state;
- move up / move down controls;
- `編集する`;
- `構成から削除`.

### 4.4 Ending section

Ending uses the same single-card model as opening.

### 4.5 Global action bar

The composition overview always provides a clear global action area:

```text
変更を反映
プレビューを書き出す
最終版を書き出す
完成動画を開く
```

`変更を反映` persists editing settings. It does not publish content.

A render action must not be hidden only inside the first-run wizard. It must remain reachable from the material-management flow.

## 5. Screen B: Material detail

The material detail screen contains only controls relevant to one material.

Common controls:

- source preview;
- source replacement;
- current audio mode;
- whole-material narration recording;
- narration file selection fallback;
- narration playback before save;
- subtitle mode and review state;
- save / apply;
- return to composition overview.

Video-only controls:

- source / narration / mute selection;
- start and end seconds for range narration;
- range narration recording or file selection;
- list of registered narration ranges;
- range deletion;
- original-audio recovery outside each replaced range.

Image-only controls:

- display duration;
- narration;
- motion mode such as pan or zoom;
- subtitle mode.

BGM and volume controls may be added later, but must remain separate from destructive delete operations.

## 6. Screen C: Output management

The output-management screen is responsible only for generated artifacts. It does not delete sources or editing settings unless the user enters a separate source-deletion flow.

### 6.1 Render controls

```text
プレビューを書き出す
最終版を書き出す
現在の書き出し状況
完成動画を開く
```

The screen shows:

- render mode;
- start time;
- current stage;
- completion or failure state;
- log summary;
- output size;
- whether the output is current or stale.

### 6.2 Generated cuts

Generated cut rows show:

- cut number;
- source material reference;
- preview;
- generated timestamp;
- size;
- freshness state;
- `再生成`;
- `このカットの生成物だけ削除`.

Deleting a generated cut must not delete:

- the source material;
- narration recordings;
- subtitles or edit settings;
- its timeline position.

After a generated cut is deleted, the final output becomes `要再書き出し`.

### 6.3 Delete all generated output

The screen provides:

```text
生成物をすべて削除
```

The confirmation dialog shows the deletion inventory before execution:

```text
完成動画: N件
カット動画: N件
プレビュー: N件
一時ファイル: N件
書き出しログ: N件
合計容量: N MB / GB
```

Bulk generated-output deletion may move the following to trash:

- final videos;
- preview videos;
- generated cut videos;
- temporary render assets;
- generated manifests, subtitles, transcripts, and logs that belong to the deleted render generation.

It must not delete:

- original videos or images;
- narration recordings;
- BGM source files;
- timeline order;
- editing settings;
- manually edited subtitle source data;
- the project itself.

## 7. Deletion vocabulary

The UI must use distinct labels for distinct destructive actions.

```text
構成から削除
素材ファイルをゴミ箱へ移動
このカットの生成物だけ削除
生成物をすべて削除
ゴミ箱から完全に削除
```

The generic label `削除` alone must not be used where the affected data is ambiguous.

## 8. Soft-delete rule

Normal deletion is always soft deletion.

```text
通常削除 = project-scoped trashへ移動
完全削除 = explicit permanent purge
```

Default retention:

- 30 days; or
- until the user explicitly empties the trash.

Automatic retention expiry is not required in the first implementation slice. If expiry is later automated, it requires a separate decision because unattended deletion is higher risk.

## 9. Immediate undo

After a normal delete action, show a mobile snackbar for 60 seconds:

```text
カット3の生成物をゴミ箱へ移動しました
[元に戻す]
```

The undo action restores the exact deletion group when possible.

If the browser closes before undo, the item remains available in the trash screen.

## 10. Screen D: Trash

The trash screen lists deletion groups, not only individual files.

Examples:

- one source material and its attached narration files;
- one generated cut;
- one bulk generated-output deletion;
- one final video;
- one range narration recording.

Each group shows:

- trash ID;
- type;
- display name;
- deletion date and time;
- affected files;
- total size;
- original location;
- retention state;
- `元に戻す`;
- `完全に削除`.

Global actions:

```text
すべて元に戻す
ゴミ箱を空にする
```

`ゴミ箱を空にする` requires a second confirmation and clearly states that recovery will become impossible.

## 11. Restore behavior

### 11.1 Normal restore

Restore returns files and metadata to their recorded original locations.

### 11.2 Conflict handling

If a new file or object already exists at the original location, the system must not overwrite it silently.

The user chooses:

```text
新しい方を残す
削除した方を別名で戻す
キャンセル
```

The safe default is `削除した方を別名で戻す`.

Example restored name:

```text
cut-003-restored-20260804T182000.mp4
```

### 11.3 State after restore

Restoring a source, edit setting, narration, subtitle, or generated cut may invalidate the current final video.

The project is then marked:

```text
復元済み
完成動画は要再書き出し
```

A restored old final video must not automatically become `最新` unless its recorded input fingerprint matches the current project state.

## 12. Output freshness model

Each generated artifact has one of these states:

```text
CURRENT
STALE
RENDERING
READY
FAILED
TRASHED
RESTORED_UNVERIFIED
MISSING
```

Minimum rules:

- any source, narration, range, order, subtitle, duration, BGM, or audio-mode change marks dependent outputs `STALE`;
- deleting one cut marks the final video `STALE`;
- restoring an artifact produces `RESTORED_UNVERIFIED` until fingerprints are checked;
- only a successful render from the current project fingerprint may be `CURRENT`.

## 13. Trash metadata contract

Each deletion group records sufficient information for reconstruction.

Example:

```json
{
  "schemaVersion": 1,
  "trashId": "trash-20260804T182000-001",
  "project": "01-segment-smoke-v3",
  "kind": "generated-cut",
  "groupLabel": "カット3の生成物",
  "deletedAt": "2026-08-04T18:20:00+09:00",
  "retentionUntil": "2026-09-03T18:20:00+09:00",
  "restorable": true,
  "projectFingerprintBeforeDelete": "sha256:...",
  "items": [
    {
      "originalPath": "output/01-segment-smoke-v3/cuts/cut-003.mp4",
      "trashPath": "projects/01-segment-smoke-v3/.trash/items/trash-20260804T182000-001/cut-003.mp4",
      "sizeBytes": 130023424,
      "sha256": "..."
    }
  ]
}
```

The implementation may use JSON or JSON Lines, but the required fields and semantics must remain recoverable.

## 14. Proposed API surface

Names may be adjusted during implementation, but responsibilities must remain separate.

```text
GET    /api/output/{project}
POST   /api/output/render
DELETE /api/output/cut
DELETE /api/output/all
GET    /api/trash/{project}
POST   /api/trash/restore
POST   /api/trash/restore-all
DELETE /api/trash/purge
DELETE /api/trash/purge-all
```

Destructive endpoints must return:

- trash ID;
- deletion-group summary;
- affected paths or logical objects;
- total size;
- undo availability;
- resulting output-freshness state.

## 15. Confirmation strength

Use confirmation strength proportional to risk.

### Generated cut only

One confirmation:

```text
このカットの生成物だけを削除します。
元素材と編集設定は残ります。
```

### All generated output

Inventory confirmation with affected count and size.

### Source material

Stronger confirmation explaining that attached narration or ranges may also move to trash and that the timeline changes.

### Permanent deletion

Two-step confirmation:

1. explain that restoration becomes impossible;
2. require a deliberate final action such as holding the button or entering a short confirmation word.

## 16. Accessibility and mobile requirements

- destructive and restorative buttons must not be adjacent without spacing;
- button labels must describe the object being affected;
- do not rely on color alone;
- status changes must be expressed in text;
- confirmation dialogs must list what remains untouched;
- the render and restore flows must survive accidental navigation through persistent server-side state;
- microphone tracks must stop after recording, failure, navigation, or discard.

## 17. Acceptance criteria

The v1 UI is acceptable when all of the following are demonstrated:

1. Opening, body, and ending are visibly separated.
2. A user can enter one material detail view and return without losing project context.
3. A saved narration can be applied and rendered from the management flow.
4. Render actions remain visible after closing and reopening the page.
5. Generated cuts can be deleted one at a time without deleting source or edit data.
6. All generated output can be deleted as one recoverable group.
7. Every normal deletion creates a trash record.
8. Immediate undo restores the deletion group.
9. Trash-screen restore works after page reload.
10. Name/path conflicts never silently overwrite existing files.
11. Restored or changed projects visibly mark old final output as stale.
12. Permanent deletion cannot occur through a normal delete button.
13. No automatic publishing or platform upload is introduced.

## 18. Implementation slices

### Slice 1 — Navigation and visible render flow

- composition overview;
- opening / body / ending grouping;
- material-detail navigation;
- global `変更を反映` and render controls;
- current/stale output label.

### Slice 2 — Generated-output inventory

- generated cut list;
- final and preview output list;
- per-cut soft delete;
- bulk generated-output soft delete;
- stale-state propagation.

### Slice 3 — Trash and restore

- trash metadata contract;
- immediate undo;
- trash screen;
- grouped restore;
- conflict-safe restore;
- permanent purge confirmations.

### Slice 4 — Editing expansion

- BGM;
- volume controls;
- richer subtitle review;
- cut-level regeneration;
- optional output fingerprint detail.

Each slice requires focused tests and human mobile review before continuing.

## 19. Current decision

This specification is the approved direction for the next Vlog UI redesign.

It does not by itself authorize merging, deployment, automatic rendering, publishing, or permanent deletion behavior.
