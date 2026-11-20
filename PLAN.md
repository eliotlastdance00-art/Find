# PLAN — Dipfeýkleri (Deepfake) kesgitleýän ulgam

> Bu faýl taslamanyň "ýady". Her täze sessiýada ilki şuny okamaly, soň işe başlamaly.
> Soňky täzelenen: 2026-11-20

---

## 0. Her sessiýanyň başynda etmeli (özüm üçin düzgün)

1. Şu faýly oka, 10-njy bölümdäki **Ýagdaý** tablisasyna seret, nirede duranymy bil.
2. `bash scripts/bootstrap.sh` işlet (sandbox-da gurlan paketler sessiýalar arasynda saklanmaýar), soň `make check`.
3. `kaggle config view` bilen Kaggle baglanyşygyny barla. Token `~/.kaggle/access_token` faýlynda; ýok bolsa ulanyjydan täzeden sora.
4. Diňe bir ädimi al, onuň "Taýýar diýilýär, haçan" şertlerini ýerine ýetir, testleri geçir, soň Ýagdaý tablisasyny we gündeligi täzele.
5. Ölçenmedik san ýazma. Metrikalar diňe hakyky işledilen synagdan alynýar we `docs/metrics/` içine faýl bolup düşýär.

**Hiç haçan etmeli däl:** Kaggle ýa-da GitHub tokenini repo, PLAN, log ýa-da notebook içine ýazmak; ölçenmedik metrikany ýazmak.

### 0a. Ulanyjynyň 2026-11-20 görkezmeleri (öňki bölümlerden ýokary durýar)

Aşakdaky bölümlerde bulara gapma-garşy zat bar bolsa, **şu ýer dogry**:

1. **Möhletler işiň depginini kesgitlemeýär.** Olar diňe ýumuş kagyzyndaky seneler. Iş yzygiderli, bökmän, ahyryna çenli edilýär.
2. **Hili: production derejesi.** Ýönekeý diplom maketi däl — hakyky ulanyp boljak ulgam: arassa arhitektura (clean architecture), SOLID, arassa kod, testler, howpsuzlyk.
3. **Docker bilen gowşurylýar.** `docker compose up --build` — başga hiç zat gerek däl. Şonuň üçin taýýar agramlar repo-da (`weights/`) saklanýar we obrazyň içine girýär (öňki «.pth git-e goşulmaýar» düzgüni ýatyryldy; diňe `weights/**` rugsat).
4. **Interfeýs üç dilde:** türkmen (esasy), rus, iňlis. PDF hasabat hem.
5. **Repo:** <https://github.com/eliotlastdance00-art/Find> (şaha `main`).
6. Hemme zady ädimme-ädim etmeli, hiç zady taşlamaly däl, taýýar bolanda push etmeli.

Hakyky kod gurluşy (5-nji bölümdäki köne çyzgynyň ýerine): `docs/ARCHITECTURE.md`.
Hakyky kararlar (4-nji bölüme goşmaça):
- Sessiýa: JWT `Authorization: Bearer` (cookie ýok → CSRF ýok); media faýllary üçin gysga möhletli `?t=` tokeni.
- Höküm bosagalary validasiýada saýlanýar (iki tarapdan iň köp 5 % ýalňyş), `model_card.json` içinde saklanýar.
- Wideoda ses diňe goşmaça subutnama: hökümi «Şübheli» derejesine çenli ýokarlandyrýar, «Galp» edip bilmeýär. Ýüz ýok + ses ýok → «kesgitläp bolmady».
- Ses modeli gaýtadan okadylmaýar: resmi AASIST agramlary; temperatura we bosagalar ASVspoof LA dev-de, metrikalar eval-da ölçenýär.
- Kaggle T4-de `channels_last + AMP + DataParallel` bilelikde «CUDA misaligned address» berýär → okuw NCHW-de.
- Bir konteýner, bir proses (nobat we SSE ýatda), SQLite + faýllar `/data` tomunda, root däl ulanyjy, diňe okalýan faýl ulgamy.
- Bagly paketler `constraints.txt` bilen berkidilen; CI = ruff + mypy strict + pytest (≥85 %) + Docker smoke test.

---

## 1. Maksat we talaplar (ýumuş kagyzyndan)

| № | Talap | Nirede çözülýär |
|---|---|---|
| T1 | Wideo, surat, audio ýüklemek we kadaly görnüşe getirmek (kadrlara bölmek, ýüzi kesmek, sesi arassalamak) | `media/` — Ädim 4 |
| T2 | Wideoda we suratda ýüzüň çalşyrylandygyny kesgitlemek | `models/visual` — Ädim 6 |
| T3 | Emeli ýa-da üýtgedilen sesi kesgitlemek | `models/audio_aasist` — Ädim 8 |
| T4 | Ähtimallyk göterimde + «Hakyky / Galp / Şübheli» | `pipeline/verdict` — Ädim 6, 9 |
| T5 | Heatmap bilen bellemek we hasabat çykarmak | `explain/`, `reports/` — Ädim 7, 10 |
| T6 | Menýular: Giriş, Faýl ýüklemek, Barlag, Netije, Bellenen ýerler, Hasabat (PDF), Taryh | `api/`, `web/` — Ädim 5 |
| T7 | SQLite: barlaglaryň taryhy | `db/` — Ädim 5 |

Tehnologiýa (ýumuşdan): Python; EfficientNet ýa-da XceptionNet (FaceForensics++); AASIST ýa-da wav2vec 2.0 (ASVspoof); OpenCV, MediaPipe/RetinaFace, FFmpeg; **FastAPI** + HTML/JS; Grad-CAM; SQLite.

### Deadline-lar

| № | Iş | Möhlet |
|---|---|---|
| 1 | Deepfake usullaryny we modelleri öwrenmek, hakyky/galp maglumat toplumyny taýýarlamak | 05.12.2026 |
| 2 | Interfeýs, menýular, faýl ýüklemek | 31.12.2026 |
| 3 | Wideo we suratda galp ýüzleri kesgitlemek | 15.02.2027 |
| 4+ | Suratda görünmeýär. Möhletler depgini kesgitlemeýär (0a seret), şonuň üçin soramak gerek däl. | — |

---

## 2. Barlanan faktlar (2026-11-20, hakyky işledip gördüm)

### Kaggle
- Hasap: `eliotalderson00`, token işleýär (`kaggle competitions list` jogap berdi).
- GPU smoke test (`eliotalderson00/dfd-smoke-test`, hususy script kernel) üstünlikli geçdi:
  - **2 × Tesla T4 (hersi 15.6 GB)**, 4 CPU, 31 GB RAM, `/kaggle/working` 20 GB, internet açyk.
  - Python 3.13.16, torch 2.11.0+cu130, torchvision 0.26, torchaudio 2.11, timm 1.0.30, OpenCV 4.14, librosa 0.11, albumentations 2.0.8, scikit-learn 1.6.1, onnx 1.23, ffmpeg bar.
  - **Ýok** (pip bilen gurmaly): `mediapipe`, `onnxruntime`, `pytorch_grad_cam`, `facenet_pytorch`.
- Kernel işletmek usuly: `kaggle kernels push -p <papka>` → `kaggle kernels status` → `kaggle kernels output`.
- Barlanmadyk: hepdelik GPU kwotasy (adatça ~30 sagat) we bir sessiýanyň çägi (adatça 12 sagat). CLI kwotany görkezmeýär — tygşytly ulanmaly.

### Kaggle-däki toplumlar (bar, ölçegi barlandy; **ygtyýarnamalary entek barlanmady**)

| Slug | Näme | Ölçegi |
|---|---|---|
| `xdxd003/ff-c23` | FaceForensics++ c23, `.mp4` wideolar (DeepFakeDetection we beýleki papkalar) | 17.9 GB |
| `gradientvoyager/faceforensics-c23-extracted-faces-100k` | FF++ c23-den kesilen ýüzler, train/test bölünen, `dataset_manifest.csv` bar | 2.6 GB |
| `reubensuju/celeb-df-v2` | Celeb-DF v2 wideolar (cross-dataset synag üçin) | 10.0 GB |
| `pranabr0y/celebdf-v2image-dataset` | Celeb-DF v2 ýüz suratlary (`Celeb_V2/Test/fake/...`) | 1.6 GB |
| `xhlulu/140k-real-and-fake-faces` | StyleGAN bilen döredilen ýüzler (tutuş sintetik ýüz) | 4.0 GB |
| `anishsarkar22/asvpoof-2019-dataset-la` | ASVspoof 2019 LA (protokollary bilen) | 7.6 GB |
| `awsaf49/asvpoof-2019-dataset` | ASVspoof 2019 doly (LA + PA) | 25.3 GB |
| `abdallamohamed312/in-the-wild-dataset` | In-the-Wild audio (cross-dataset synag üçin) | 8.2 GB |

### Taýýar agramlar (URL-ler barlandy, HTTP 200)
- DeepfakeBench release `v1.0.1`: `effnb4_best.pth` (71 MB), `xception_best.pth` (88 MB) we beýlekiler.
  `https://github.com/SCLBD/DeepfakeBench/releases/tag/v1.0.1`
- AASIST resmi repo: `models/weights/AASIST.pth` (1.28 MB), `AASIST-L.pth` (0.43 MB).
  `https://github.com/clovaai/aasist`
- YuNet ýüz detektory (OpenCV Zoo): `face_detection_yunet_2023mar.onnx` (233 KB).
- Barlanmadyk: bu agramlaryň ygtyýarnama şertleri we biziň kodumyz bilen laýyk ýüklenýändigi (Ädim 6, 8-de barlanýar).

### Sandbox (meniň iş ýerim)
- Python 3.13.18, 2 CPU, **2 GB RAM**, 21 GB disk. Ulgamda `ffmpeg` ýok, `sudo` ýok.
- `opencv-python 4.11` bar, `cv2.FaceDetectorYN` (YuNet) elýeterli.
- torch CPU (2.15.0+cpu) 20 sekuntda guruldy; EfficientNet-B0, 8 surat, 0.44 s, ~490 MB RAM. Diýmek CPU-da inference we testler bu ýerde işleýär.
- `mediapipe` we `imageio-ffmpeg` üçin Python 3.13 wheel bar.
- Snapshot çägi ~128 MB: **agramlar workspace-de saklanmaýar**, her gezek skript bilen `.cache/weights/` içine ýüklenýär.

### GitHub
- Bu ýerde GitHub konnektory **goldanmaýar**. Men workflow faýlyny ýazyp bilerin, ýöne Actions-y özüm işledip bilmerin (8-nji bölüme seret).

---

## 3. Ilki öwrenmeli zatlar (goragda soraljak nazaryýet)

Ädim 2-de her biri boýunça `docs/theory/` içine gysga ýazgy taýýarlanýar.

1. **Deepfake görnüşleri:** face swap, face reenactment, tutuş ýüz sintezi (GAN/diffusion), lip-sync; sesde TTS we voice conversion.
2. **FaceForensics++ gurluşy:** Deepfakes, Face2Face, FaceSwap, NeuralTextures (+ FaceShifter, DFD); gysyş derejeleri c0/c23/c40; resmi train/val/test bölünişi (720/140/140 wideo).
3. **Maglumat syzmasy (leakage):** bölünişik kadr boýunça däl, **wideo/şahs boýunça** bolmaly. Bu iň köp goýberilýän ýalňyşlyk.
4. **Transfer learning:** ImageNet-de okadylan EfficientNet/Xception-i fine-tune etmek; augmentasiýa (JPEG gysyş, bulaşdyrma, kiçeltmek) näme üçin gerek.
5. **Metrikalar:** AUC, EER, accuracy, confusion matrix, FPR/FNR; kadr derejesi bilen wideo derejesiniň tapawudy.
6. **Kalibrleme we bosagalar:** temperature scaling; «Şübheli» zolagy nädip saýlanýar.
7. **Grad-CAM:** soňky conv gatlagynyň gradiýentlerinden heatmap nädip alynýar; çäkleri (ol "subutnama" däl, modeliň nirä seredendigini görkezýär).
8. **AASIST:** çig tolkun (raw waveform), sinc-conv, spektral-temporal graph attention; ASVspoof 2019 LA hüjüm görnüşleri A01–A19.
9. **Umumylaşdyrma meselesi:** bir toplumda okadylan model beýleki toplumda näme üçin gowşaýar (cross-dataset synag).
10. **FastAPI:** async, dependency injection, Pydantic, fon işleri, SSE.

---

## 4. Esasy tehniki kararlar

| Sorag | Karar | Sebäbi |
|---|---|---|
| Surat/wideo modeli | **EfficientNet-B4** (`timm`), FF++ c23-de özümiz okadýarys. Deňeşdirmek üçin DeepfakeBench-iň `effnb4_best.pth` we `xception_best.pth` agramlary | Ýumuş "FF++-da okadylan" diýýär; öz okadan modelimiz + taýýar baseline bilen deňeşdirme diplom üçin güýçli |
| Ses modeli | **AASIST**, ilki resmi agramlar, soň öz barlagymyz (EER) we mümkin bolsa fine-tune | Agramlar 1.3 MB, CPU-da çalt; wav2vec 2.0 ~300 MB we haýal |
| Ýüz detektory | **YuNet** (`cv2.FaceDetectorYN`) esasy, MediaPipe ätiýaçlyk | Goşmaça paket gerek däl, 233 KB, Kaggle-de we Windows-da deň işleýär, 5 nokat berýär (ýüzi deňlemek üçin) |
| Train/serve deňligi | Okatmakda we programmada **şol bir** `media/faces.py` kody ulanylýar | Taýýar kesilen toplum bilen biziň kesişimiz tapawutly bolsa takyklyk düşýär. Şonuň üçin ýüzleri `xdxd003/ff-c23` wideolaryndan özümiz kesýäris |
| FFmpeg | `imageio-ffmpeg` (pip bilen gelýän binar) | Ulgama aýratyn gurmak gerek däl, Windows-da hem işleýär |
| Inference | PyTorch (CPU ýa-da GPU awtomat saýlanýar) | Grad-CAM üçin gradiýent gerek. ONNX eksport — soňky goşmaça ädim |
| Grad-CAM | Öz ýazan hook-ly realizasiýamyz, `pytorch-grad-cam` bilen test arkaly deňeşdirilýär | Düşündirip bolýar, garaşlylyk az |
| Fon işleri | Proses içindäki nobat (asyncio + thread pool), ýagdaýlar `queued → preprocessing → analyzing → explaining → done/failed`, öňe gidişlik SSE bilen | Redis/Celery diplom üçin artykmaç, oflaýn işlemeli |
| Baza | SQLAlchemy 2.0 + SQLite (WAL) | Ýumuş boýunça |
| Giriş | Parol argon2 bilen heşlenýär, JWT HttpOnly cookie-de, rollar `admin`/`user` | Howpsuz we ýönekeý |
| Frontend | Jinja2 + arassa HTML/CSS/JS, **CDN ýok**, ähli faýllar ýerli | Goragda internet bolmazlygy mümkin |
| PDF | `fpdf2` + DejaVu Sans | Türkmen harplary (ň, ý, ş, ž, ä, ö, ü) dogry çykmaly |
| Hökümiň bosagalary | Validasiýa ROC-dan: FPR ≤ 5% bolýan nokatdan ýokary — «Galp», FNR ≤ 5% bolýan nokatdan aşak — «Hakyky», arasy — «Şübheli» | "40/70" ýaly göz çaky sanlardan has esasly; goragda düşündirip bolýar |
| Wideonyň jemi | Kadrlaryň ähtimallyklarynyň ortaçasy + iň ýokary 10%-iň ortaçasy; ses ýoly bar bolsa aýratyn barlanýar, jemleýji höküm ikisiniň iň ýokarysy | Wideonyň diňe bir bölegi galp bolup biler |
| Python | 3.12–3.13 | Kaggle we sandbox 3.13 |

---

## 5. Arhitektura

```
Faýl → [sniff: magic bytes, ölçeg, dowamlylyk, SHA-256] → Scan ýazgysy (queued) → nobat
   ├─ Surat:  YuNet → deňlemek/kesmek (margin 1.3) → EfficientNet → p → Grad-CAM
   ├─ Wideo:  ffmpeg → N kadr (deň aralyk) → her kadrda ýüz → EfficientNet → p(t)
   │           → wagt çyzgysy + iň şübheli K kadr üçin Grad-CAM
   │           → ses ýoly bar bolsa → Ses şahasy
   └─ Ses:    16 kHz mono → 4 s penjireler (64600 nusga) → AASIST → p(t) → wagt çyzgysy
→ kalibrleme → höküm (Hakyky/Şübheli/Galp) → artefaktlar (heatmap PNG, grafik) → SQLite → PDF
```

```
deepfake-detector/
├─ PLAN.md
├─ pyproject.toml  Makefile  Dockerfile  .gitignore
├─ .github/workflows/   ci.yml, model-eval.yml
├─ src/dfd/
│  ├─ api/        auth, files, scans, reports, history, admin, pages
│  ├─ core/       config, security, logging, i18n (tk)
│  ├─ db/         models, session
│  ├─ media/      sniff, ffmpeg, frames, faces, audio
│  ├─ models/     visual, audio_aasist, registry, calibration
│  ├─ explain/    gradcam, overlay, timeline
│  ├─ pipeline/   image, video, audio, fusion, verdict
│  ├─ jobs/       queue, worker, progress
│  ├─ reports/    pdf, fonts/
│  └─ web/        templates/, static/
├─ training/      extract_faces.py, train_visual.py, eval_visual.py, eval_audio.py, train_audio.py
├─ scripts/       bootstrap.sh, kaggle_run.py, fetch_weights.py, make_samples.py
├─ kaggle/        kernel metadata, smoke/
├─ tests/         unit/, api/, e2e/
└─ docs/          theory/, metrics/, diagrams/, user-guide.md
```

**Baza:** `users(id, username, password_hash, role, created_at)`;
`scans(id, user_id, filename, sha256, media_type, status, progress, verdict, prob_fake, visual_prob, audio_prob, model_versions, duration_ms, error, created_at)`;
`artifacts(id, scan_id, kind, path, frame_idx, timestamp_s, score)`.

**API:** `POST /api/auth/login|logout|register`, `POST /api/files`, `POST /api/scans`, `GET /api/scans/{id}`, `GET /api/scans/{id}/events` (SSE), `GET /api/scans/{id}/artifacts`, `GET /api/scans/{id}/report.pdf`, `GET /api/history`, `DELETE /api/scans/{id}`, `GET /health`.

---

## 6. Ädimler

Tertip deadline-lara görä düzüldi: ilki interfeýs (31.12), soň model (15.02).

### Tapgyr A — 05.12.2026 çenli

**Ädim 0. Gurşaw we baglanyşyklar** — ✅ taýýar (2-nji bölüm).

**Ädim 1. Repo skeleti + CI**
- `pyproject.toml`, `ruff`, `mypy`, `pytest`, `Makefile` (`make ci` = lint + type + test), `scripts/bootstrap.sh`, `.gitignore`.
- FastAPI programmasy diňe `/health` bilen.
- `.github/workflows/ci.yml` (torch CPU, pip cache).
- Taýýar diýilýär, haçan: `make ci` sandbox-da ýaşyl; workflow faýly `actionlint` ýa-da YAML barlagyndan geçýär.

**Ädim 2. Nazaryýet we maglumatlar**
- `docs/theory/` ýazgylary (3-nji bölüm).
- Kaggle-de toplumlaryň gurluşyny, ygtyýarnamalaryny, papkalaryny, wideo sanlaryny barlamak (CPU kernel).
- FF++ resmi bölünişigini (splits JSON) tapmak; ýok bolsa wideo ID boýunça öz 720/140/140 bölünişigimiz, seed bellenen.
- ASVspoof 2019 LA protokol faýllaryny okamak (bonafide/spoof sanlary).
- Taýýar diýilýär, haçan: `docs/metrics/datasets.md` içinde her toplum üçin hakyky sanlar; bölünişik faýly repo-da; "bir wideo iki bölege düşmeýär" diýen test bar.

**Ädim 3. Ýüzleri kesmek (Kaggle)**
- `media/faces.py` (YuNet, deňlemek, margin) + `training/extract_faces.py`.
- `scripts/kaggle_run.py`: `src/dfd` kodyny hususy Kaggle toplumyna (`dfd-code`) ýükleýär, kerneli işledýär, netijäni alýar.
- Her wideodan 32 kadr → hususy toplum `eliotalderson00/dfd-ffpp-faces` + `manifest.csv`.
- Şol bir kod bilen Celeb-DF v2 test bölegi (cross-dataset üçin).
- Taýýar diýilýär, haçan: manifestde synp/usul/bölek boýunça sanlar; ýüz tapylmadyk wideolaryň paýy hasabatda; 20 tötänleýin kesilen ýüzi göz bilen barladym.

### Tapgyr B — 31.12.2026 çenli (interfeýs)

**Ädim 4. Media kitaphanasy**
- `sniff` (magic bytes, rugsat berlen görnüşler, ölçeg/dowamlylyk çägi), `ffmpeg` (kadr almak, sesi 16 kHz mono çykarmak), `audio` (normalizasiýa, sessizligi kesmek, penjireler).
- Taýýar diýilýär, haçan: testler sintetik faýllar bilen (ffmpeg bilen döredilen wideo, sinus ses) geçýär; zaýa/ýalan giňeltmeli faýl ret edilýär.

**Ädim 5. Backend + 7 menýu (stub detektor bilen)**
- Baza, giriş, faýl ýüklemek, nobat, SSE, taryh, pozmak.
- Sahypalar: Giriş, Faýl ýüklemek, Barlag (öňe gidişlik), Netije, Bellenen ýerler, Hasabat, Taryh. Dili türkmençe.
- Detektor interfeýsi (`Protocol`) + tötän san berýän stub, soň hakyky model şol ýere dakylýar.
- Taýýar diýilýär, haçan: API testleri doly akymy geçýär (giriş → ýüklemek → barlag → netije → taryh); başga ulanyjynyň barlagyny görüp bolmaýandygy test edilen; brauzerde el bilen barlandy.

### Tapgyr C — 15.02.2027 çenli (surat/wideo modeli)

**Ädim 6. Wizual model**
- `training/train_visual.py`: EfficientNet-B4, AMP, 2×T4, augmentasiýa, synp deňagramlylygy, wideo derejesinde validasiýa AUC boýunça iň gowy checkpoint.
- Baseline: DeepfakeBench agramlaryny şol bir test böleginde ölçemek.
- Synaglar: FF++ test (umumy we usul boýunça), cross-dataset Celeb-DF v2, gysyşa durnuklylyk.
- Kalibrleme + bosagalar → `model_card.json` (wersiýa, sha256, metrikalar, bosagalar).
- Agramlar hususy Kaggle toplumyna; `scripts/fetch_weights.py` sha256 barlagy bilen ýükleýär.
- Maksat (wada däl, ölçenmeli): FF++ c23 test AUC ≥ 0.95. Cross-dataset AUC has pes bolar — näçe çyksa, şony ýazýarys.
- Taýýar diýilýär, haçan: `docs/metrics/visual.json` + ROC suraty; programmada stub ýerine hakyky model; sandbox-da CPU-da birnäçe hakyky/galp nusga dogry işlenýär.

**Ädim 7. Grad-CAM we bellenen ýerler**
- `explain/gradcam.py`, overlay, wideo üçin iň şübheli K kadr, wagt çyzgysy.
- Taýýar diýilýär, haçan: biziň CAM `pytorch-grad-cam` netijesi bilen test içinde gabat gelýär (korrelýasiýa > 0.95); "Bellenen ýerler" sahypasy hakyky heatmap görkezýär.

### Tapgyr D — möhleti näbelli (4+ setirler)

**Ädim 8. Ses modeli**
- AASIST kodyny geçirmek, resmi agramlary ýüklemek, Kaggle-de LA eval böleginde EER ölçemek (makaladaky san bilen deňeşdirmek), In-the-Wild-da cross-dataset.
- Uzyn faýllar üçin süýşýän penjire, wagt çyzgysy. Mümkin bolsa augmentasiýa bilen fine-tune.
- Taýýar diýilýär, haçan: `docs/metrics/audio.json`; ses faýly we wideonyň ses ýoly programmada barlanýar.

**Ädim 9. Birleşdirme we höküm** — wizual + ses, kalibrlenen bosagalar, SHA-256 boýunça keş, ýüz tapylmasa aýdyň habar.

**Ädim 10. PDF hasabat** — faýl maglumatlary, heş, höküm, ähtimallyklar, heatmap-lar, wagt çyzgysy, model wersiýalary, çäklendirmeler barada bellik.
- Taýýar diýilýär, haçan: PDF-den tekst çykarylyp, türkmen harplary test bilen barlanýar.

### Tapgyr E — jemleýji

**Ädim 11. Berkitmek** — Dockerfile, çäkler (ölçeg, dowamlylyk, ýygylyk), admin sahypasy, loglar, ONNX eksport (isleg boýunça), Windows-da işledmek gollanmasy.

**Ädim 12. Diplom üçin materiallar** — metrika tablisalary, ROC, confusion matrix, tizlik ölçegleri (CPU/GPU), arhitektura diagrammalary, ulanyjy gollanmasy, demo ssenariýasy.

---

## 7. Test strategiýasy

| Dereje | Näme | Nirede | Haçan |
|---|---|---|---|
| 1. Lint/type | `ruff`, `mypy` | sandbox + GitHub Actions | her üýtgeşmede |
| 2. Unit | media, verdict, kalibrleme, Grad-CAM, PDF — kiçi tötän agramly modeller we sintetik faýllar bilen, agram ýüklemezden | sandbox + GitHub Actions | her üýtgeşmede |
| 3. API | `httpx`/TestClient bilen doly akym, stub detektor, wagtlaýyn SQLite | sandbox + GitHub Actions | her üýtgeşmede |
| 4. E2E | hakyky agramlar bilen birnäçe nusga (CPU) | sandbox, `make e2e` | model üýtgände |
| 5. Model hili | AUC/EER doly test böleginde, cross-dataset | **Kaggle GPU** | her täze model |
| 6. El bilen | brauzerde 7 menýu | sandbox preview | Ädim 5-den soň |

5-nji dereje üçin gözegçilik: täze modeliň AUC-si öňküden 1 punktdan köp pese düşse, ol kabul edilmeýär.

## 8. GitHub Actions barada

- Men bu ýerden GitHub-a birikip bilemok (konnektor goldanmaýar). Şonuň üçin:
  - `ci.yml` faýlyny ýazýaryn we onuň edýän zatlarynyň hemmesini `make ci` bilen sandbox-da işledýärin — netije birmeňzeş bolmaly.
  - Ulanyjy repony GitHub-a push edende Actions awtomat işlär.
  - Eger ulanyjy **diňe bir repo üçin** fine-grained token berse, men `git push` edip, Actions netijesini API arkaly okap bilerin.
- `model-eval.yml` (`workflow_dispatch`, el bilen): `KAGGLE_API_TOKEN` secret bilen Kaggle kernelini işledýär, `metrics.json` alýar, bosagadan pes bolsa ýykylýar.

---

## 9. Töwekgelçilikler

| Töwekgelçilik | Näme etmeli |
|---|---|
| Kaggle GPU kwotasy (hepdede çäkli) | Ilki kiçi bölekde (5%) synag, soň doly okatmak; maglumat işlerini CPU kernelde etmek |
| Kaggle-däki FF++ göçürmeleriniň ygtyýarnamasy | Ädim 2-de barlamak; ulanyjy resmi FF++ anketasyny hem ugratmaly (diplomda salgylanmak üçin) |
| Täze deepfake görnüşlerinde (diffusion) gowşak netije | Cross-dataset synagyny dogruçyl görkezmek; PDF-de çäklendirme belligi; mümkin bolsa 140k toplumyndan sintetik ýüzleri goşmak |
| Train/serve tapawudy | Şol bir kesiş kody; e2e test |
| Sandbox 2 GB RAM | B4 CPU-da bir wagtda az kadr (batch 4); agyr zatlar Kaggle-de |
| Agramlar snapshot-a sygmaýar | `.cache/weights/` + `fetch_weights.py` |
| Goragda internet ýok | CDN ýok, agramlar öňünden ýüklenen, oflaýn işleýändigi test edilýär |
| Ulanyjynyň kompýuteri näbelli (OS, GPU) | Soramaly; Windows gollanmasy; CPU režimi hökman işlemeli |

---

## 10. Ýagdaý

| Ädim | Ýagdaý | Bellik |
|---|---|---|
| 0. Gurşaw, Kaggle, GPU smoke test | ✅ 2026-11-20 | 2×T4 tassyklandy |
| 1. Repo skeleti + CI | ✅ kod; ⚠️ CI we Docker entek hiç ýerde işledilmedi | sandbox-da Docker ýok — ilkinji GitHub Actions işi barlamaly |
| 2. Nazaryýet we maglumatlar | 🟡 | toplumlar tapyldy; ygtyýarnamalary we `THIRD_PARTY_NOTICES.md` barlamaly; nazaryýet ýazgysy (`docs/THEORY.md`) ýok |
| 3. Ýüzleri kesmek | ✅ | YuNet, okuwda we serwerde şol bir kod |
| 4. Media kitaphanasy | ✅ | FFmpeg (imageio-ffmpeg), kadrlar, 16 kHz ses bölekleri |
| 5. Backend + 7 menýu | ✅ | FastAPI + SPA, tk/ru/en, açyk/garaňky |
| 6. Wizual model | 🟡 okuw Kaggle-da gidýär | `eliotalderson00/dfd-train-visual` v1; netije gelýänçä `weights/visual/` boş |
| 7. Grad-CAM | ✅ kod | hakyky model bilen göz bilen barlamaly |
| 8. Ses modeli | 🟡 | AASIST işleýär; kalibrleme `dfd-eval-audio-cpu` v2 gidýär (3000 faýl — bölekleýin; doly GPU işi gerek) |
| 9. Birleşdirme we höküm | ✅ kod | bosagalar hakyky kartlardan gelmeli |
| 10. PDF hasabat | ✅ | tk/ru/en; soňky ýerleşiş düzedişi göz bilen gaýtadan barlanmady |
| 11. Berkitmek | 🟡 | howpsuzlyk sözbaşylary, çäkler, testler 95 %; brauzer e2e soňky refaktordan soň gaýtalanmady |
| 12. Diplom materiallary | ⬜ | düşündiriş ýazgysy, prezentasiýa, görkeziş wideosy |

### Açyk işler (tertip boýunça)
1. Kaggle netijelerini almak → `weights/visual/{weights.pth,model_card.json}`, `weights/audio/model_card.json`, README-däki metrika tablisasy (diňe ölçenen sanlar).
2. Hakyky modeller bilen: FF++ test wideolarynda we öz mysallarymyzda el bilen barlag; Grad-CAM-yň manylydygyny görmek.
3. GitHub-a push; CI-niň ýaşyl bolmagyny gazanmak (Docker obrazy ilkinji gezek şol ýerde gurlar).
4. `THIRD_PARTY_NOTICES.md` — ygtyýarnamalary çeşmelerden barlamak (häzir ýatdan ýazylan).
5. `js/i18n.js`: `err.not_found`, `err.method_not_allowed` goşmak; ulanylmaýan 11 açary aýyrmak.
6. Brauzer e2e-ni gaýtalamak (rus dilinde gapdal menýu, telefon ekrany).
7. Ses: doly ASVspoof LA dev+eval (GPU) bilen kalibrleme; gürleýiş däl ses üçin duýduryş.
8. Umumylaşdyrma synagy: Celeb-DF ýa-da başga toplumda ölçemek we dogruçyl ýazmak.
9. `docs/THEORY.md`, diplom ýazgysy, prezentasiýa.

### Ulanyjydan garaşylýan jogaplar
- [ ] GitHub-a push etmek üçin: fine-grained token (diňe `Find` repo, Contents: Read and write) ýa-da özi push etmek.
- [ ] Gorag haýsy kompýuterde geçer (OS, RAM, GPU)? Docker gurlup bilermi?
- [ ] Kaggle tokeni söhbetde açyk ýazyldy — iş gutaransoň täzelemeli.

### Gündelik
- **2026-11-20 (1):** Ýumuş kagyzy seljerildi. Kaggle birikdirildi, GPU smoke test geçdi. Toplumlar we taýýar agramlar tapyldy. Plan ýazyldy.
- **2026-11-20 (2):** Ulanyjynyň täze görkezmeleri (0a). Tutuş taslama ýazyldy: domain/application/infrastructure/presentation, 7 menýu, üç dil, PDF, Grad-CAM, AASIST, okuw skriptleri, Docker, CI, 110 test (95 %), ruff + mypy strict arassa. Wheel arassa venv-e gurlup, `scripts/smoke_test.py` geçdi. Kaggle: CUDA «misaligned address» tapyldy we aýlanyp geçildi; wizual okuw işe goýberildi.
