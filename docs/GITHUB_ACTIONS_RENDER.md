# GitHub Actions render worker

This repository can use Oracle as the mobile console and persistent storage while GitHub Actions performs temporary CPU-heavy rendering.

## Architecture

```text
iPhone -> Oracle web console -> immutable job snapshot
                              -> GitHub Actions
                              -> rendered MP4 returned to Oracle
                              -> /api/download/<project>
```

Video assets are not committed to Git. Runtime projects, jobs, outputs and CI work directories remain ignored by `.gitignore`.

## Files

- `.github/workflows/render-vlog.yml`: manually dispatched render workflow
- `scripts/create_render_job.sh`: snapshots one Oracle project into an immutable job
- `scripts/oracle_prepare_github_actions.sh`: creates an Oracle SSH key and prints the required repository secrets
- `scripts/ci/fetch_render_job.sh`: copies the job snapshot from Oracle to the runner
- `scripts/ci/install_ci_dependencies.sh`: installs preview or final render dependencies
- `scripts/ci/render_job.sh`: processes and renders the selected profile
- `scripts/ci/publish_render_job.sh`: validates and atomically publishes the MP4 back to Oracle
- `scripts/ci/update_render_status.sh`: writes job state to Oracle

## One-time Oracle preparation

Pull the latest repository and run:

```bash
cd ~/rts-video-flow
git pull
bash scripts/oracle_prepare_github_actions.sh 140.238.62.74
```

The script prints the values for these GitHub repository Actions secrets:

- `ORACLE_HOST`
- `ORACLE_PORT`
- `ORACLE_USER`
- `ORACLE_REPO_DIR`
- `ORACLE_KNOWN_HOSTS`
- `ORACLE_SSH_KEY`

Create the secrets in the repository under:

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

Do not paste the private key into an issue, commit, chat screenshot or workflow file.

After `ORACLE_SSH_KEY` has been saved, the bootstrap script prints a command that removes the local private-key copy. The public key remains in `~/.ssh/authorized_keys` until the integration is retired.

## Create a render job

A job is an immutable snapshot. Editing the live project after this command does not alter the running render.

Preview:

```bash
cd ~/rts-video-flow
bash scripts/create_render_job.sh 01 preview
```

Final:

```bash
cd ~/rts-video-flow
bash scripts/create_render_job.sh 01 final
```

The command prints a value similar to:

```text
JOB_ID=01-20260803T054000Z-a4f92c
```

## Run the workflow manually

Open the repository Actions tab and select **Render Vlog**. Choose **Run workflow** and enter:

```text
job_id: the exact JOB_ID printed by create_render_job.sh
project: 01
mode: preview or final, matching the snapshot
```

The workflow rejects a mode that does not match `job.json`.

## Profiles

### Preview

- 640 x 360
- 10 fps
- Whisper skipped
- intended for order, audio and composition review

### Final

- 1920 x 1080
- 30 fps
- CPU Whisper with `small,base` fallback
- subtitles and final composition enabled

## Job state

Oracle stores status at:

```text
jobs/<job-id>/status.json
```

Normal states are:

```text
queued -> fetching -> setup -> rendering -> publishing -> completed
```

A failed workflow writes:

```text
status: failed
step: github-actions
```

The workflow log is also returned to:

```text
jobs/<job-id>/logs/render.log
```

## Completed video

GitHub Actions first uploads to:

```text
output/.incoming/<job-id>/vlog.mp4
```

Oracle validates the video stream and duration with `ffprobe`, then atomically moves it to:

```text
output/<project>/vlog.mp4
```

The existing download endpoint remains:

```text
https://140-238-62-74.sslip.io/api/download/01
```

## Concurrency and failure safety

- Only one workflow for the same project runs at a time.
- A new failed render does not overwrite the previous successful output.
- Job source material is copied from the immutable snapshot, not the live project.
- Workflow permissions are limited to repository read access.
- Rendered media is returned through SSH and is not uploaded as a GitHub artifact.

## Retire the connection

Remove the matching public key line from:

```text
~/.ssh/authorized_keys
```

Then delete the six `ORACLE_*` repository secrets.
