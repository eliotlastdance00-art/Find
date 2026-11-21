"""Build a Turkmen bona fide / spoof speech set for fine-tuning the audio detector.

Real speech comes from TurkmenSpeech (YouTube broadcasts) and Common Voice (read speech).
Fakes are made from it with neural vocoders and codecs (copy-synthesis), text-to-speech,
voice cloning and voice conversion. Two generators are produced for the test split only, so
that the trained detector can be measured on generators it has never seen.

Entry point: ``python -m training.tk_audio.build`` (see that module).
"""
