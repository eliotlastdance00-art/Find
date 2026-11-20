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
PyJWT (MIT). `imageio-ffmpeg` (BSD-2-Clause) downloads a static **FFmpeg** binary, which is
licensed under the GPL; it is executed as a separate program and is not linked into this code.
