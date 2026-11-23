# Audio run 1 — archived six-epoch deployment

These JSON files are byte-for-byte copies of the previously deployed results/card, saved
before installing continuation run 2. `baseline.json` describes the original official model.

The old `weights/audio/AASIST.pth` remains recoverable from git revision
`570956b1a0db83477be86fc37a07afc9d4bad6f7` (and from the continuation's pinned initialization
revision `16c22b7ad36ecd8f4f6e7de540588bfd197e7337`). Its SHA-256 is
`b7b91f75e5d815466427ec4176bdf2f0b0fb212c991bd6a84446bd2b2df6ca78`.
The revision's file bytes were checked against this hash during the deployment review.

Do not copy only this model card over the current weights: a card and its weights must match.
See [`../audio_tk_continuation.json`](../audio_tk_continuation.json) for the deployment comparison.
