# rts-video-flow Next Actions

The next goal is freeze review, not expansion.

## Next Tasks

1. Confirm which files are scaffold, prototype code, generated media, or temporary artifacts.
2. Classify each material as ready, draft, stale, duplicate, risky, move, or archive.
3. Confirm that no credentials, private links, customer media, or copyrighted source media are present.
4. Confirm that no automatic upload, publishing, platform automation, or unattended service behavior is present.
5. Confirm that generated subtitles and rendered outputs are treated as local review artifacts.
6. Decide whether the repository should remain frozen, be archived, or receive a narrow video-workflow update.

## Suggested Follow-up Files

```text
docs/inventory/video_flow_inventory.md
docs/contracts/media_review_contract.md
docs/governance/publishing_boundary.md
```

## Inventory Categories

Use these labels during the next pass:

- READY: safe as local workflow documentation or reviewed prototype material
- DRAFT: useful but incomplete
- STALE: likely outdated or superseded
- DUPLICATE: overlaps another script, template, or workflow note
- RISKY: media rights, privacy, upload, platform automation, or unattended execution risk needs review
- MOVE: belongs in another repository
- ARCHIVE: preserve for history only

## Video Review Checklist

Each video workflow item should explicitly describe:

- name
- path
- material type
- purpose
- status label
- input expectations
- output expectations
- rights or privacy risk
- upload or publishing risk
- runtime or automation risk
- next smallest safe action

If an item implies automatic publishing, platform automation, unattended execution, sensitive media, or public use of unreviewed assets, mark it as `RISKY` and do not expand it until reviewed.

## Do Not Do Yet

Do not:

- add automatic upload or publishing behavior
- add platform automation
- add credentials, API keys, tokens, secrets, or private links
- add customer or private video material
- add copyrighted source media
- add background processing services
- add unattended execution workflows
- rewrite all scripts at once

## Next Recommended Task

Create `docs/inventory/video_flow_inventory.md` only if this repository is intentionally reviewed again.

That file should list each known video workflow material with:

1. name
2. path
3. material type
4. status label
5. input expectations
6. output expectations
7. rights or privacy risk
8. upload or publishing risk
9. runtime or automation risk
10. next smallest safe action
