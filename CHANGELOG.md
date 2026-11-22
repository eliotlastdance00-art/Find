# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Planned
- A second image model for fully AI-generated pictures, with a provenance-metadata check.
- Longer training of the Turkmen audio model.

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
