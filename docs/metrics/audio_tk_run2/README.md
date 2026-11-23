# Audio continuation — source artifacts

Source: Kaggle `eliotalderson00/dfd-train-audio-2`, version 2, status `COMPLETE`.

- `training.txt`: downloaded training log, checked for credentials before archiving.
- `exported_model_card.json`: **unmodified training export, for provenance only**.
  The exporter reused version `2.0.0`, set `provisional: false`, and omitted the verdict cap.
  This is **not** the deployed card and must not replace it.
- Reviewed deployment card: [`../../../weights/audio/model_card.json`](../../../weights/audio/model_card.json),
  `aasist-tk` **2.1.0**, `provisional: true`, `max_verdict: suspicious`.
- Metrics/history remain at `../audio_tk_{metrics,history,baseline}.json`.
  `audio_tk_baseline.json` measures the **official original weights before initialization**,
  not the six-epoch starting checkpoint; run-1 vs run-2 comparisons use the two saved test reports.
- Decision, comparisons, source revision and artifact hashes:
  [`../audio_tk_continuation.json`](../audio_tk_continuation.json).

The job completed 15 continuation epochs (~501.8 training minutes). The selected checkpoint
is continuation epoch **13**, minimizing the mean of Turkmen-dev and LA-dev EER.
The initialization was the six-epoch weights from run 1; training restarted with the same seed
and a new optimizer schedule. These are not 21 uninterrupted training epochs.

The temperature and thresholds were fitted on pooled dev data, not test data. Test results
were used to review deployment safety, not to retune the checkpoint or thresholds.
The suspicious cap prevents the audio model from making a strong *Fake* accusation; it does
**not** address fake speech incorrectly labelled *Real*, which worsened on the held-out tests.
AUC 0.935 is a ranking metric, **not** 93.5% classification accuracy.
