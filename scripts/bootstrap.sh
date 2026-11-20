#!/usr/bin/env bash
# Sandbox/dev bootstrap: installs CPU-only PyTorch first (small wheel), then the project with dev extras.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pip install -q --upgrade pip
python -m pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu
python -m pip install -q -e ".[dev]"
python -c "import dfd, torch; print('dfd', dfd.__version__, '| torch', torch.__version__)"
