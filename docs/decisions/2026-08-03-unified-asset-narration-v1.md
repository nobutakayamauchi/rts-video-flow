# Unified Asset Narration v1

Date: 2026-08-03

## Decision

Reopen the frozen prototype for one narrow implementation task: apply the same audio model to every timeline asset.

Each asset now uses one of three explicit modes:

- `source`: use the original video's audio
- `narration`: mute the source video and use attached narration
- `mute`: use no audio

Subtitles are generated from whichever audio source is active for that asset and are offset into the global timeline.

## Why

The first end-to-end preview proved that multiple assets could be rendered and returned through Oracle and GitHub Actions, but also exposed a practical failure: a screen recording can be valid video while containing no usable speech.

Screenshot-only narration was not enough. Video assets need the same post-recorded narration path.

## Included

- stable asset IDs and normalized audio/subtitle modes
- per-video source audio transcription
- per-video and per-image narration transcription
- global subtitle timing across all assets
- source/narration/mute behavior in Remotion
- mobile material-management controls for narration upload and audio mode
- stale-output invalidation after project changes
- focused unit tests

## Boundaries

This change does not add:

- automatic YouTube upload or publishing
- platform automation
- credentials, secrets, private links, or media files
- an always-on worker or new background service
- customer media or copyrighted sample media

Final review and publication remain manual.

## Duration rule

- narrated images use narration duration
- narrated videos keep the source-video duration
- narration longer than its video is rejected to prevent silent truncation
- shorter narration is allowed and produces a warning about the silent tail

## Validation

Completed locally against reconstructed branch files:

- Python syntax compilation
- `bash -n scripts/process_vlog.sh`
- JavaScript syntax check for `manage.html`
- six unit tests for audio defaults, legacy manifest normalization, narration normalization, and subtitle offsets
- synthetic FFmpeg integration with source-audio video, narrated video, and narrated image

Full GitHub Actions and Oracle deployment validation remains required before merge.
