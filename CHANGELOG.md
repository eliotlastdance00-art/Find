# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Smaug ONNX AI-image detection alongside the existing face-swap model, including images
  without faces. Three sequential native-resolution crops; independent model scores/verdicts.
- Structured PNG/EXIF/XMP AI provenance hints, explicitly unverified and non-decisive.
- `dfd models --download`: pinned 181 MB model, resumable HTTPS, SHA-256, atomic installation,
  release asset and upstream mirror. Docker downloads at build time; serving stays offline.
- Separate AI-image results, metadata hints and honest heatmap scope in all three UI/PDF languages.
- Integration regression: the generated portrait scores 0.999603; JPEG-60 resized copy 0.999163.
  These are smoke checks, not benchmark accuracy; Smaug's 0.5 threshold remains provisional.

### Changed
- Deploy `aasist-tk` 2.1.0 after 15 continuation epochs (best checkpoint: epoch 13).
  Turkmen test AUC 0.759 → 0.935, EER 31.1% → 14.5%; held-out-generator EER 37.9% → 19.7%.
- Keep the provisional flag and *Suspicious* verdict cap: uncapped real-speech false alarms
  are still 6.3% (14.1% on quiet speech), above the 5% target. Fake-as-real worsened from
  14.4% to 18.2%, and LA eval EER from 3.40% to 3.78%. Do not hide these regressions.
- Archive run-1 metrics and record checkpoint provenance, unchanged dev thresholds and the
  deployment decision in `docs/metrics/audio_tk_continuation.json`.

### Fixed
- Docker smoke check no longer assumes every no-face image is inconclusive: when Smaug is
  installed, require its score and verdict to reach the result. Keep the fallback assertion
  without Smaug; do not assign an accuracy ground truth to the generated gradient control.
- Memory retained between sequential ONNX operations; unused Grad-CAM parameter gradients.
- macOS instructions now use non-editable installs; offline wheel lists include ONNX Runtime.
- A malformed optional XMP field cannot crash image analysis.

### Planned
- Independent calibration/cross-dataset evaluation, then video-frame AI-generation detection.
- Reduce Turkmen audio false alarms and held-out-generator misses; test on independent sources.

## [0.1.0] — 2026-11-22

First public version.

### Added
- **Web application** with seven sections: sign-in, file upload, analysis, result, highlighted
  regions, PDF report and history. Interface and reports in Turkmen, Russian and English; light,
  dark and automatic colour themes; phone layout.
- **Video and image analysis:** YuNet face detection and an EfficientNet-B4 classifier trained on
  FaceForensics++ (c23). Measured on the official test split (840 videos): AUC 0.9914, EER 3.00 %.
- **Audio analysis:** AASIST fine-tuned on ASVspoof 2019 LA and a Turkmen speech set. Measured:
  Turkmen test AUC 0.759, EER 31.1 %; ASVspoof 2019 LA eval AUC 0.9952, EER 3.40 %. The model is
  provisional and its verdict is capped at *Suspicious*.
- **Explanations:** Grad-CAM heat maps over detected faces, per-frame and per-segment charts.
- **Verdicts** (*Real / Suspicious / Fake*) from calibrated probabilities and thresholds stored in
  each model card.
- **Reports:** PDF export in three languages.
- **Accounts and history:** Argon2id password hashes, JWT sessions, login throttling, per-user
  history with search, filters and statistics (SQLite).
- **Deployment:** `dfd` command-line tool, Docker image and Compose file, GitHub Codespaces dev
  container, offline wheel download for slow connections.
- **Quality:** strict typing, linting and a test suite that runs the real pipeline; CI on Linux,
  macOS and Windows plus a Docker smoke test.

### Known limitations
- The visual model learned five face-swap methods; it does not recognise fully AI-generated
  pictures.
- The audio model is not reliable yet on Turkmen speech: 8.3 % of real test speech is judged fake,
  and neural-codec resynthesis is often missed.
- A verdict is a model estimate, not proof.

[Unreleased]: https://github.com/eliotlastdance00-art/Find/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/eliotlastdance00-art/Find/releases/tag/v0.1.0
