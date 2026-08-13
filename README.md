# rts-video-flow

> **Status: DEVELOPMENT ENDED / STANDALONE EDITOR SUPERSEDED — 2026-08-14**
>
> This repository is preserved as development history and evidence. No new Vlog-owned editing engine work is authorized by default.

`rts-video-flow` was a smartphone-first Vlog pipeline for turning development records into videos without making video production itself heavy work.

The project implemented and explored iPhone media intake, transcription, subtitles, jump cuts, narration, composition UI, rendering, output management, recoverable trash, and guarded overflow compute.

On 2026-08-14 the project was run through a `/goal` / METEOR replacement review using the rule:

```text
KEEP EXISTING → EXTRACT → NEW BUILD ONLY IF IRREDUCIBLE
```

The standalone editor boundary did not survive.

## Final disposition

**Killed as Vlog-owned responsibilities**

- custom Whisper / transcription pipeline
- custom subtitle / SRT generation
- custom silence / jump-cut engine
- custom narration / audio-editing engine
- Remotion render runtime
- Oracle render-worker responsibility
- Google Cloud emergency overflow path
- custom composition/editor UI
- custom generated-output management
- custom trash / restore subsystem
- Vlog-specific debug-engine continuation

**Preserved / surviving responsibilities**

- development history and source code: `PRESERVE`
- editorial intent derived from development history: `STANDBY / EXTRACT CANDIDATE`
- privacy / publication safety responsibility: `KEEP RESPONSIBILITY`
- final human publication decision: `HARD KEEP`

No replacement bridge is authorized yet. Before any new Vlog-specific code is created, representative smartphone development material must be processed with existing external tools. Only recurring friction that survives those tools and cannot be removed by process, prompting, or existing capabilities may become an `IRREDUCIBLE` candidate.

Until then:

```text
NO NEW BUILD
```

Canonical closure record:

- [VLOG METEOR — 2026-08-14](docs/VLOG_METEOR_2026-08-14.md)

## Historical project description

The original project goal was to create a lightweight Vlog pipeline from smartphone-shot material, using short front-camera clips, short screen recordings, screenshots, and automatic subtitles so that YouTube operation would not become a major workload.

The repository historically included:

- iPhone front/rear camera media intake
- iPhone screen-recording intake
- screenshot ordering and duration controls
- explicit opening / body / ending composition
- Japanese transcription
- Japanese subtitle segmentation and SRT output
- Remotion-based 1920×1080 rendering
- narration/source/mute audio modes
- privacy pre-publication checks
- experimental preview/final rendering and output lifecycle controls

## Historical operating principle retained

The following publication boundary remains valid even though the standalone editor is retired:

- use screen recordings mainly for short functional demos or evidence
- prefer screenshots for routine development records
- do not expose notifications, DMs, email, personal information, API keys, or private URLs
- treat video as an output of development records, not the development project itself
- do not auto-publish; retain a human review and publication decision

## Historical specification

- [Vlog MVP specification](docs/VLOG_MVP_SPEC.md)

The implementation history, merged commits, closed pull requests, experiments, and branches remain available for reconstruction and future study. Retirement of the standalone editor is an operational decision, not deletion of history.
