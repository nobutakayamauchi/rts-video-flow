# RTS_PROCESS_VISIBILITY_CONTRACT_V1

## Purpose

Prevent users from mistaking a live process for a frozen interface and prevent duplicate execution caused by repeated taps.

This contract applies to every RTS operation that may take longer than three seconds or whose completion depends on an external system.

## Mandatory interaction contract

1. A user action must produce visible acknowledgement immediately.
2. The same logical operation must not start twice while an earlier instance is active.
3. A fixed, scroll-following progress overlay must remain visible while the operation is active.
4. The overlay must communicate whether the operation is progressing, waiting, stalled, completed, or failed.
5. Completion and failure must always be visible; failures remain until the user leaves or a new operation starts.

## Standard overlay

The canonical UI is `RTS Progress Overlay`, implemented by:

```text
web_console/static/rts-progress-overlay.js
```

The overlay is fixed near the bottom safe area on mobile devices and follows the viewport while scrolling.

## Required fields

Every long-running process must expose as much of the following information as is available:

- acceptance acknowledgement;
- current stage;
- completed units and total units;
- percentage, or an indeterminate progress animation when percentage is unknown;
- elapsed time;
- time since the last progress update;
- whether closing the screen cancels or does not cancel the operation;
- completion or failure details.

## State model

Supported user-facing states:

```text
accepted
running
waiting
stalled
completed
failed
```

A process with no progress update for 30 seconds changes visually to waiting. A process with no progress update for 120 seconds changes visually to stalled. This warning does not itself cancel the underlying process.

## Duplicate prevention

While a logical process is active:

- its initiating controls are disabled;
- repeated pointer, touch, or click events must not create a second server-side request;
- repeated activation should keep the existing overlay visible instead of starting another operation;
- server-side idempotency or active-request lookup should be used when available.

Client-side disabling is not considered sufficient protection by itself for operations that can incur cost or mutate persistent data.

## API

The shared browser API is:

```javascript
RTSProgressOverlay.show({
  title: '✓ 受け付けました',
  stage: '素材を確認しています…',
  note: '画面を閉じずにお待ちください。',
});

RTSProgressOverlay.update({
  stage: '素材を正規化しています 2 / 4',
  percent: 45,
});

RTSProgressOverlay.finish({
  title: '✓ 完了しました',
  stage: '書き出し準備が完了しました。',
});

RTSProgressOverlay.fail(errorMessage);
```

## Percentage rules

Do not invent a precise percentage when the backend cannot calculate one. Use indeterminate progress and a concrete stage name instead.

A percentage may be based on:

- completed items divided by total items;
- completed stages divided by total stages;
- bytes transferred divided by total bytes;
- a backend-provided progress value.

## Process lifecycle

A normal lifecycle is:

```text
user tap
-> immediate accepted state
-> running stage updates
-> waiting or stalled warning when updates stop
-> completed or failed state
```

For externally dispatched work, the overlay must explicitly say that the operation continues after the screen is closed.

## Initial adoption

The first governed implementation is the Vlog Cloud Render flow:

```text
compose-cloud-render.js
```

Its preparation request may take approximately one minute. The overlay must therefore acknowledge the tap immediately, display elapsed time, prevent duplicate taps, and remain visible until the approval prompt or an error is returned.

## Future adoption rule

New RTS features that may exceed three seconds must use the shared overlay rather than introducing a private progress UI. Existing features should migrate when they are next modified.
