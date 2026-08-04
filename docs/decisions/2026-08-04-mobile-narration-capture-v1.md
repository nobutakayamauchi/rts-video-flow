# Mobile Narration Capture v1

Date: 2026-08-04

## Goal

Finish the practical mobile workflow for post-recorded narration.

A user should be able to open the material-management page on an iPhone, select either an entire asset or a time range inside a video, record narration with the phone microphone, preview it, and save it without first creating a separate audio file in another application.

## User flow

### Whole-asset narration

1. Open a project and locate an asset.
2. Tap **Record**.
3. Speak while the timer runs.
4. Tap **Stop**.
5. Preview the recording.
6. Save it as the asset's narration.

The existing file picker remains available as a fallback.

### Range narration

1. Enter start and end seconds.
2. Record or select an audio file.
3. Preview the recording.
4. Save it to the selected range.
5. The existing source audio is replaced only inside that range.

Before upload, the browser compares the audio duration with the selected range:

- audio longer than the range is blocked;
- audio substantially shorter than the range produces a confirmation warning;
- unreadable duration is allowed and remains subject to server/render validation.

## Recording rules

- only one microphone recording may run at a time;
- recording requires HTTPS and browser support for `getUserMedia` and `MediaRecorder`;
- supported MIME types are selected at runtime, preferring MP4 audio on Safari/iPhone and Opus WebM/Ogg where available;
- microphone streams are stopped immediately after recording;
- generated object URLs are revoked when recordings are replaced, discarded, or the page closes;
- unsaved recordings stay in browser memory only;
- the user may discard and record again before upload.

## Boundaries

This slice does not add:

- automatic silence detection;
- automatic range selection;
- background recording;
- automatic rendering after upload;
- automatic publishing;
- permanent browser-side storage.

The server-side project plan, soft-delete behavior, output invalidation, FFmpeg range replacement, subtitle generation, and manual publication gate remain unchanged.

## Acceptance criteria

- whole-asset microphone recording can be previewed and uploaded;
- range microphone recording can be previewed and uploaded;
- file selection still works for both paths;
- the UI prevents two simultaneous recordings;
- a range recording longer than the selected range is rejected before upload;
- a shorter recording warns that the remainder will be silent;
- permission or browser-support failures produce a clear fallback message;
- no microphone track remains active after stop, failure, or page exit.
