# Contributing

Thank you for your interest in Deepfake Detektor. Bug reports, wrong-verdict reports, translations,
documentation fixes and code are all welcome — in Turkmen, Russian or English.

## Ways to help

| I want to… | Where |
|---|---|
| report a bug | [New issue → Bug report](https://github.com/eliotlastdance00-art/Find/issues/new/choose) |
| report a file that was judged wrongly | [New issue → Wrong verdict](https://github.com/eliotlastdance00-art/Find/issues/new/choose) |
| propose a feature | [New issue → Feature request](https://github.com/eliotlastdance00-art/Find/issues/new/choose) |
| report a security problem | privately, see [SECURITY.md](SECURITY.md) |

Please never attach private media of real people to a public issue.

## Development setup

Python 3.11–3.13 and Git are required. No GPU and no internet access are needed to run the tests.

```bash
git clone https://github.com/eliotlastdance00-art/Find.git && cd Find
python3 -m venv .venv && source .venv/bin/activate     # Windows: py -m venv .venv; .venv\Scripts\Activate.ps1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev]"
dfd serve                                              # http://localhost:8000
```

On Linux and macOS `make install` does the same, and `make help` lists the other targets.

## Before you open a pull request

Run what CI runs:

```bash
make check                       # ruff check + ruff format --check + mypy + pytest
```

or, without `make`:

```bash
ruff check . && ruff format --check .
mypy
pytest --cov=dfd
```

* Formatting: `ruff format .` (line length 100). Types: `mypy` is strict for the `dfd` package.
* Tests live in `tests/unit` and `tests/api`; they run the real pipeline (FFmpeg, OpenCV, PyTorch,
  Grad-CAM, PDF) on synthetic media and small random networks. CI requires at least 85 % coverage.
* Front-end JavaScript has no build step and no external libraries; CI runs `node --check` on it.

## Project rules

1. **Layers.** `domain` knows nothing about frameworks; `application` holds the use cases;
   `infrastructure` holds SQLite, FFmpeg, models and PDF; `presentation` holds FastAPI and the web
   interface. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
2. **Three languages.** Every interface or report text is added in `tk`, `ru` and `en` with the
   same key (`src/dfd/presentation/static/js/i18n.js`, `src/dfd/infrastructure/report/texts.py`).
   A test fails if the key sets differ.
3. **Only measured numbers.** Metrics in the README, model cards and reports must come from a run
   whose output is stored in `docs/metrics/`. Do not round a result into a better one, and say so
   when a model is provisional.
4. **Models.** Weights are shipped with a `model_card.json` (training data, calibration
   temperature, decision thresholds, SHA-256). A new model needs its card, its measured metrics and
   the training or evaluation script under `training/`.
5. **No external assets** in the web interface (fonts, scripts, CDNs): the application must work
   offline and under its Content-Security-Policy.
6. **Privacy.** No personal data, credentials or real people's private media in commits, tests or
   issues.

## Commits and pull requests

* Keep a pull request focused on one change and describe how you checked it.
* Write commit subjects in the imperative or as `Area: what changed`, for example
  `Audio: cap the verdict of provisional models`.
* By contributing you agree that your contribution is licensed under the [MIT License](LICENSE)
  and that you follow the [Code of Conduct](CODE_OF_CONDUCT.md).
