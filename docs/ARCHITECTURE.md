# Architecture

## Layers

The code follows a ports-and-adapters ("clean") layout. Dependencies point inwards only:
`presentation → application → domain ← infrastructure`.

```
src/dfd/
├── domain/            Pure Python, no framework imports
│   ├── entities.py    User, Scan, Analysis, Thresholds, Verdict …
│   ├── scoring.py     Score aggregation, three-way verdict, audio/visual fusion
│   ├── errors.py      Domain errors, each with a stable code and HTTP status
│   └── ports.py       Protocols the application needs (repositories, storage, analyzer …)
├── application/       Use cases
│   ├── auth.py        Register, log in, authenticate, media tokens
│   └── scans.py       Upload, start, history, delete; ScanProcessor runs one scan
├── infrastructure/    Adapters implementing the ports
│   ├── db/            SQLAlchemy 2 models + repositories (SQLite, WAL)
│   ├── media/         FFmpeg, frame sampling, YuNet face detection, PCM windows, file sniffing
│   ├── ml/            Model cards, registry, EfficientNet detector, AASIST detector, Grad-CAM, metrics
│   ├── report/        PDF report (fpdf2 + DejaVu), report texts in tk/ru/en
│   ├── analysis.py    TorchMediaAnalyzer: the full pipeline for one file
│   ├── jobs.py        Worker pool and the live-progress event broker
│   ├── security.py    Argon2id hashing, JWT sessions, login rate limiter
│   └── storage.py     Uploads and per-scan artifacts on disk
├── presentation/      FastAPI app: routers, schemas, dependencies, static single-page UI
├── container.py       Composition root: the only module that wires concrete classes
├── config.py          Settings from DFD_* environment variables
└── cli.py             dfd serve | create-user | models
```

`training/` (not shipped in the image) trains the visual model and calibrates the audio
model on Kaggle; it imports the *same* preprocessing and scoring code the server uses, so
there is no train/serve skew.

## Life of a scan

1. **Upload** `POST /api/scans` — the stream is written to disk under a server-chosen name
   while it is hashed (SHA-256) and the size cap is enforced. The type is decided from the
   file's content (magic bytes, then a decode/probe), never from its extension or the
   client's MIME type. Status `uploaded`.
2. **Start** `POST /api/scans/{id}/start` — status `queued`; the id goes to the worker pool.
3. **Preprocess** — video: frames are sampled evenly; in each frame the largest face is found
   with YuNet and cropped with a 1.3× margin. Image: up to `DFD_MAX_FACES` faces. Audio
   (and a video's sound track): FFmpeg decodes to 16 kHz mono PCM, cut into 4.04 s windows
   with 50 % overlap.
4. **Analyze** — face crops go through EfficientNet-B4 (one logit, positive = fake), audio
   windows through AASIST. Logits are divided by the calibration temperature stored in the
   model card and passed through a sigmoid.
5. **Aggregate** — `0.5 · mean + 0.5 · mean(top 25 %)` over frames or windows, so partly
   manipulated clips still score high while one noisy frame cannot dominate.
6. **Verdict** — the model card holds two thresholds per scope, chosen on validation data so
   that at most 5 % of fakes fall below `real_max` and at most 5 % of real samples lie above
   `fake_min`. `p ≤ real_max` → *Hakyky*, `p ≥ fake_min` → *Galp*, otherwise *Şübheli*.
   For video, the sound track is supporting evidence: it can raise the verdict to *Şübheli*
   but not to *Galp*. With no face and no usable audio the result is *inconclusive* —
   the system does not guess.
7. **Explain** — Grad-CAM on the last convolutional block for the highest-scoring crops;
   heatmaps and an annotated overview frame are saved as scan artifacts.
8. **Report** — the PDF is rendered on request in Turkmen, Russian or English.

Progress is published through an in-process broker and streamed to the browser as
server-sent events (`GET /api/scans/{id}/events`).

## Security

* Passwords: Argon2id. Sessions: signed JWT (HS256) sent as `Authorization: Bearer`, so
  there are no cookies and no CSRF surface. Login failures are rate limited per client.
* `<img>`, `<video>` and PDF links cannot send headers; they use a short-lived token bound
  to one scan (`?t=`), which is not accepted as a session.
* Every scan query is scoped to its owner; another user's scan answers 404, not 403.
* Uploads are stored outside the static tree under generated names; artifact names are
  matched against a strict pattern, so path traversal is not possible.
* Model weights are loaded with `weights_only=True` and verified against the SHA-256 in
  their model card.
* Response headers: strict Content-Security-Policy (no inline or third-party scripts),
  `X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors`.
* The container runs as an unprivileged user on a read-only root filesystem; only `/data`
  is writable.

## Deployment notes

* One process by design: the queue and the event broker live in memory. Scale up
  (`DFD_WORKERS`, more CPU, or a GPU image), not out. Scans interrupted by a restart are
  re-queued at start-up.
* State is `/data`: `dfd.db` (SQLite), `uploads/`, `scans/`, `secret.key`. Back up that volume.
* Put a TLS-terminating reverse proxy in front for anything beyond a local network, and
  raise its body-size limit to `DFD_MAX_UPLOAD_MB`.

## Model cards

Each model lives in `weights/<kind>/` next to a `model_card.json` with: architecture,
weights file and SHA-256, calibration temperature, decision thresholds per scope, the data
it was trained/evaluated on, and the measured metrics. The server reads everything from
the card, so replacing a model needs no code change. `provisional: true` marks a model
whose thresholds must not be trusted; the UI and the report then show a warning.
