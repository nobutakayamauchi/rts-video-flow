# Vlog project template

Copy this folder and rename it, for example `projects/vlog-001`.

## Put iPhone materials here

```text
vlog-001/
├── camera/       # normal iPhone camera clips
├── screen/       # short iPhone screen recordings; demo use only
├── screenshots/  # normal evidence and progress record
└── README.md
```

Create the three folders if they do not exist. Files are processed in filename order, so use names such as:

```text
camera/01-opening.mov
screenshots/01-spec.png
screenshots/02-github.png
screenshots/03-test.png
screen/01-short-demo.mov
```

## Run

From the repository root:

```bash
./scripts/process_vlog.sh projects/vlog-001
```

The first MVP creates:

```text
output/vlog-001/
├── manifest.json
├── subtitles.srt
├── transcript.md
└── NEXT_STEPS.md
```

Review `NEXT_STEPS.md` before rendering or publishing. Screen recording is optional; screenshots are the default because they are lighter, easier to review, and safer to redact.
