# Third-party notices

This project is released under the MIT licence (see `LICENSE`). It bundles or downloads the
following third-party material.

## Bundled in the repository

| Component | Where | Licence | Source |
|---|---|---|---|
| AASIST model definition | `src/dfd/infrastructure/ml/vendor/aasist_model.py` | MIT, © 2021 NAVER Corp. | <https://github.com/clovaai/aasist> |
| AASIST pretrained weights | `weights/audio/AASIST.pth` | MIT, © 2021 NAVER Corp. | <https://github.com/clovaai/aasist> (`models/weights/AASIST.pth`) |
| YuNet face detector | `src/dfd/infrastructure/media/assets/face_detection_yunet_2023mar.onnx` | MIT | <https://github.com/opencv/opencv_zoo> |
| DejaVu Sans fonts | `src/dfd/infrastructure/report/fonts/` | Bitstream Vera / DejaVu licence (free to use, embed and redistribute) | <https://dejavu-fonts.github.io> |
| FaceForensics++ split lists | `training/splits/*.json` | part of the FaceForensics++ repository | <https://github.com/ondyari/FaceForensics> |

The AASIST paper: Jung et al., *AASIST: Audio Anti-Spoofing using Integrated
Spectro-Temporal Graph Attention Networks*, ICASSP 2022.

## Models trained for this project

`weights/visual/weights.pth` is an EfficientNet-B4 (architecture and ImageNet initialisation
from `timm`, Apache-2.0) fine-tuned by this project on FaceForensics++ (c23).

## Downloaded AI-image detector

**Smaug-AI-Image-Detector** by Abacus.AI; quantised, image-only ONNX build by **21amd21**.
Both source repositories declare **Apache-2.0**:

- Original: <https://huggingface.co/abacusai/Smaug-AI-Image-Detector>
- ONNX build: <https://huggingface.co/21amd21/smaug-ai-image-detector-web>
- Pinned ONNX revision: `1f7d2da952f86543c6c878450ee8fc82750bd14d`.
- SHA-256: `982222b91a85102fc7fadfce488c182afd9556f7166343f51606670724b951e6`.
- Full licence: `src/dfd/infrastructure/ml/assets/LICENSE-Smaug.txt`, also copied next to downloaded weights.

The ONNX build removes unused text/audio components and quantises weights (mixed INT4/INT8),
as described by its author. This project does not alter those ONNX bytes or claim to have
trained Smaug. It supplies an inference adapter, upstream-compatible crop preprocessing,
resumable distribution and reporting. No upstream Python code is downloaded or executed.

The audio weights currently shipped are this project's `aasist-tk` fine-tune, not the
unmodified original AASIST weights. Some Turkmen training sources have non-commercial
terms; the application code's MIT licence does not override data/model restrictions.
The full dataset/derived-model licensing audit remains open; see PLAN.md.

## Datasets (not redistributed)

No dataset files are included in this repository or in the Docker image.

* **FaceForensics++** — Rössler et al., ICCV 2019. Access is granted by the authors under
  their terms of use, for research purposes. Anyone retraining the visual model must obtain
  the data under those terms.
* **ASVspoof 2019 (LA)** — Wang et al., 2020, distributed by the University of Edinburgh
  DataShare under the ODC-By licence. Used here to calibrate and evaluate the audio model.

## Runtime dependencies

Installed from PyPI; see `pyproject.toml` and `constraints.txt`. Notable licences:
PyTorch (BSD-3-Clause), timm (Apache-2.0), OpenCV (Apache-2.0), FastAPI (MIT),
SQLAlchemy (MIT), fpdf2 (LGPL-3.0, used as an unmodified library), argon2-cffi (MIT),
PyJWT (MIT), ONNX Runtime (MIT), Pillow (MIT-CMU). `imageio-ffmpeg` (BSD-2-Clause) downloads a static **FFmpeg** binary, which is
licensed under the GPL; it is executed as a separate program and is not linked into this code.
