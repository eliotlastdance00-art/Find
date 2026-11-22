# Smaug: AI-generated still images

## Install once; run offline

From the project root, with the virtual environment active:

```bash
pip install .
dfd models --download
dfd models
dfd serve
```

For an Apple Silicon Mac with Python 3.13 and an unstable connection:

```bash
source .venv/bin/activate
python scripts/fetch_wheels.py requirements/wheels/macos-arm64-py313.txt
pip install --no-index --find-links wheels .
dfd models --download
```

The updated wheel lists include ONNX Runtime and its dependencies (the pinned ONNX
Runtime macOS wheel requires macOS 14+). Do **not** use an editable `-e` install on the Mac
where hidden `.pth` files are not imported. After updating the project, repeat the install
and restart the server. Existing `data/` accounts/history are unaffected.

Smaug is 181,210,404 bytes, separate from pip wheels. The explicit download command:

- resumes `weights/synthetic/model.onnx.part` after a network failure;
- checks HTTP Content-Range, exact size and SHA-256 before atomically installing;
- reuses an existing verified copy without network access;
- tries the GitHub Release asset, then a revision-pinned Hugging Face mirror;
- installs the model card and Apache-2.0 licence next to the weights.

Re-run the command after interruption. It never disables TLS verification. The web
server never downloads models and never sends uploaded media to either host.
Docker installs Smaug during the image build; serving in a read-only container stays offline.

## Sources and immutable identity

- Original model, Abacus.AI: <https://huggingface.co/abacusai/Smaug-AI-Image-Detector>
- Quantised image-only ONNX build, 21amd21:
  <https://huggingface.co/21amd21/smaug-ai-image-detector-web>
- Pinned revision: `1f7d2da952f86543c6c878450ee8fc82750bd14d`.
- SHA-256: `982222b91a85102fc7fadfce488c182afd9556f7166343f51606670724b951e6`.
- Licence: Apache-2.0, full text in `src/dfd/infrastructure/ml/assets/LICENSE-Smaug.txt`.

This project does not train Smaug or modify the downloaded ONNX bytes. It does not
execute downloaded Python code. The upstream author's benchmark numbers are not local
measurements and are intentionally not advertised as this system's accuracy.

## What the adapter does

The shared decoder honours EXIF orientation; BGR pixels become RGB. Preprocessing follows
Abacus.AI's `smaug_image_detect.py`, rather than treating the model like EfficientNet:

1. If the shorter side exceeds 576 px, downsize to 576 with Lanczos.
2. If it is under 528 px, upscale to at least 528 with bicubic interpolation.
3. Otherwise keep native resolution. Take three 528×528 crops: start, centre and end of
   the longer side, centred on the shorter side.
4. Run float32 RGB values in [0,1], without ImageNet normalisation, one crop at a time.
5. Average the three **logits**, then apply sigmoid. Averaging probabilities is different.

The ONNX graph is already optimised; re-optimisation and weight prepacking are disabled
for memory headroom. CPU inference uses two threads and serialised calls per detector.
On Linux/glibc, freed temporary workspaces are returned between operations; Grad-CAM
parameter gradients are cleared after use. This does not impose a hard RSS limit.

Allow at least 4 GB system RAM for OS, media and model headroom; more for concurrent
workers. In the recorded two-core Linux smoke run, three consecutive images completed
at 18–24 seconds each and peak process RSS 1,179 MiB. Large uploads, video/audio, other
hardware and concurrency can use more. These are observations, not performance guarantees.

## Decisions are separate from scores

- **EfficientNet** checks detected faces for face swapping.
- **Smaug** checks still-image pixels for AI generation, even without a face.
- Each result keeps its model version, score, thresholds, provisional flag and verdict.
- The strongest per-model verdict wins. A low face-swap score does not cancel a high
  AI-generation finding, nor the reverse.
- The headline percentage is the maximum individual image score, **not a calibrated joint
  probability**. The UI labels it a forgery score when Smaug was used.
- Smaug uses the upstream 0.5 threshold, explicitly **provisional**. No representative local
  false-positive rate or calibration has been established. In particular, the combined
  detector does not inherit the earlier FF++ model's accuracy or false-alarm guarantee.

No arbitrary ensemble weights or '100% because metadata says AI' rule are used. A missing
or broken Smaug produces a visible warning; the face path may still run. With no usable
model result the system cannot assess the image. Video and audio paths are unchanged.

## Metadata and explanations: do not confuse evidence

Supported hints: IPTC `DigitalSourceType` AI declarations in XMP; structured PNG generation
settings (`Steps`, `Sampler`, `Seed`); a known AI tool named in the EXIF/PNG Software tag.
A prompt alone or a normal Photoshop tag is not treated as an AI declaration. Raw prompts,
GPS and other private metadata are not returned in the API or report.

Metadata can be forged or stripped. These are **unverified hints**, not verified provenance,
and do not decide the verdict. No C2PA signatures are verified. Missing metadata does not
prove authenticity.

Grad-CAM belongs **only to EfficientNet's face-swap result**. Smaug has no localisation
explanation in this integration. A real-looking face heatmap cannot refute Smaug and must
not be presented as an explanation of its score. The UI and PDF make this explicit.

## Recorded regression, not a benchmark

Measured with real weights and the complete image pipeline, ONNX Runtime 1.32.0:

| Input | Smaug score | Face-swap score | Final verdict |
|---|---:|---:|---|
| Existing fully generated portrait | 99.9603% | 0.0088% | Fake |
| Same portrait, 768×768 JPEG quality 60, metadata stripped | 99.9163% | 0.0616% | Fake |
| One real photo from the existing Wikimedia probe | 0.0156% | 49.2683% | Real |

All three had no supported AI metadata markers: the generated examples were detected
from pixels. PDF reports also rendered in Turkmen, Russian and English.

Raw scores, hashes, timings and scope: [metrics/smaug_integration_smoke.json](metrics/smaug_integration_smoke.json).
The portrait was already used to choose this model, and the second image is a transform of
it. These are **not independent accuracy samples**. Do not derive AUC, sensitivity or false
alarm percentages from them. Earlier exploratory checks also found missed old DALL·E 2
images. New generators, screenshots and heavy edits/compression remain risks.

Next: independent held-out calibration/evaluation (including real camera photos, screenshots,
compression, older/newer and unseen generators), then a separately calibrated video path.
See [ROADMAP.md](ROADMAP.md) for priorities and acceptance criteria.
