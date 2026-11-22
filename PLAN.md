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
7. **(2026-11-21) Her işden öň pikirlenmeli.** Hiç bir işe gönüden-göni başlamaly däl. Tertip:
   (a) meseläni analiz et — näme gerek, näme üçin; (b) başga nähili usullar bar — gerek bolsa internetden gözle;
   (c) usullary deňeşdir, iň gowusyny saýla we sebäbini ýaz; (d) diňe şondan soň ýerine ýetir; (e) netijäni barla.
   Saýlanan çözgüt we ret edilen wariantlar şu faýlyň gündeligine (10-njy bölüm) ýazylýar.
8. **(2026-11-22) Awtor ady diňe `eliot`.** Kodda, resminamalarda, suratlarda, commit-lerde we synag hasabynda başga at, topar ýa-da ýolbaşçy ýazylmaly däl. Iş `eliot` şahasynda, `eliot` ady bilen.

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
| 6. Wizual model | ✅ v2 tamamlandy, ulgama goýuldy | `dfd-train-visual` v2 (199 min). Test: wideo AUC 0.9914, EER 3.0 %; kadr AUC 0.9832, EER 5.27 %. `weights/visual/`, `docs/metrics/visual_effnet_b4_ffpp.json` |
| 7. Grad-CAM | ✅ kod | hakyky model bilen göz bilen barlamaly |
| 8. Ses modeli | 🟡 deslapky kart goýuldy | 3000+3000 ýazgyda ölçendi: eval AUC 0.9991, EER 1.62 %; T=1.448, bosagalar 3.0 % / 99.0 %. Doly toplum (GPU) entek edilmedi |
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
   Şeýle hem: uzyn sesde ýat sarp edilişini ölçemek (AASIST, batch 8) we konteýneriň 4 GB çägine sygýandygyny barlamak.
8. Umumylaşdyrma synagy: Celeb-DF ýa-da başga toplumda ölçemek we dogruçyl ýazmak.
9. `docs/THEORY.md`, diplom ýazgysy, prezentasiýa.

### Ulanyjydan garaşylýan jogaplar
- [ ] GitHub-a push etmek üçin: fine-grained token (diňe `Find` repo, Contents: Read and write) ýa-da özi push etmek.
- [ ] Gorag haýsy kompýuterde geçer (OS, RAM, GPU)? Docker gurlup bilermi?
- [ ] Kaggle tokeni söhbetde açyk ýazyldy — iş gutaransoň täzelemeli.

### Gündelik
- **2026-11-20 (1):** Ýumuş kagyzy seljerildi. Kaggle birikdirildi, GPU smoke test geçdi. Toplumlar we taýýar agramlar tapyldy. Plan ýazyldy.
- **2026-11-20 (2):** Ulanyjynyň täze görkezmeleri (0a). Tutuş taslama ýazyldy: domain/application/infrastructure/presentation, 7 menýu, üç dil, PDF, Grad-CAM, AASIST, okuw skriptleri, Docker, CI, 110 test (95 %), ruff + mypy strict arassa. Wheel arassa venv-e gurlup, `scripts/smoke_test.py` geçdi. Kaggle: CUDA «misaligned address» tapyldy we aýlanyp geçildi; wizual okuw işe goýberildi.
- **2026-11-20 (3):** GitHub-a push edildi (`main`), CI ýaşyl (ulanyjynyň aýtmagyna görä). `dfd-eval-audio-cpu` v2 gutardy (1 sag 53 min, CPU-da 1 ýazgy/s). Kart `weights/audio/model_card.json`, çig sanlar `docs/metrics/audio_aasist_subset.json`. Hakyky serwer arkaly 16 ASVspoof ýazgysy: 16/16 dogry. **Tapyndy:** AASIST 3 bölekli ýazgyda prosesiň ýady 1.1 GB-a ýetdi — uzyn seslerde batch 8 bilen ýady ölçemeli, zerur bolsa batch-y kiçeltmeli.
- **2026-11-20 (4): Türkmen sesi.** Ulanyjynyň haýyşy bilen ses modeli türkmen sesinde barlandy (`/home/user/tk_eval/NOTES.md`, repo-a goşulmady): hakyky 60 ýazgy (`rozumov/TurkmenSpeech`, YouTube) → 0 «Hakyky», 35 «Şübheli», 25 «Galp»; MMS-TTS galplary bilen AUC 0.38–0.55. **Häzirki AASIST türkmen sesinde ýaramsyz.** Gözegçilik: ASVspoof ýazgylary AAC 32k we 4 kHz zolakdan soň hem dogry tanalýar → sebäp ýönekeý gysyş däl.
  Ulanyjy karar berdi: **AASIST-i türkmen + iňlis sesinde bilelikde fine-tuning etmeli, «advanced», türkmen dili möhüm.** Meýilnama (4 ädim): (1) generatorlaryň Kaggle-da işleýändigini barlamak; (2) galp toplumyny döretmek; (3) okatmak + 3 synag (ASVspoof eval, türkmen synagy, görülmedik generator); (4) ulgama goýmak.
  1-nji ädim gidýär: `eliotalderson00/dfd-tk-probe` v1 (CPU; kod `/home/user/tk_eval/probe/`). Ýerli barlanan: gaýtadan sintez — SpeechT5-HiFi-GAN, UnivNet, EnCodec 3/6 kbps, DAC 16k, Mimi (asyl bilen log-spektr korrelýasiýasy 0.88–0.94; baglanyşyksyz ýazgylar 0.44); MMS-TTS işleýär. Kaggle-da garaşylýan: Vocos, kNN-VC, OmniVoice (600+ dil, `tk` bar), VoxCPM2 + Anadil LoRA, MMS-ASR bilen düşnüklilik barlagy.
  Hakyky sesiň ikinji çeşmesi: `fsicoli/common_voice_22_0` `tk` (1972 tassyklanan ýazgy, 74 gürleýji, CC0, MP3, öý şertleri) — «YouTube = hakyky» ýalňyş düzgüniniň öňüni almak üçin.
  Ygtyýarnama: TurkmenSpeech we MMS — CC BY-NC 4.0 (diňe täjirçilik däl).
- **2026-11-20 (5): Wizual okuw ýykyldy.** `dfd-train-visual` v1 → ERROR. Ýüzleri kesmek 76 min (6000 wideo, 78 710 ýüz, ýüzsiz wideo ýok), okuw 9 min/epoha (2×T4, ~104 surat/s). 11 epoha gutardy; 12-nji epohada 700/809 ädimden soň çykyş kesildi (11 034-nji sekunt), 20 575-nji sekuntda «Killed». Sebäbi anyklanmady (CUDA/DataParallel doňmagy ýa-da DataLoader işçisi). `history.csv` saklandy (`~/.cache/kout/tv/`), `weights.pth` ýok.
  **v2-den öň hökman düzetmeli (`training/train_visual.py`):** (a) her gowulaşmada iň gowy agramlary + wagtlaýyn karty `/kaggle/working`-e ýazmak; (b) `faces.tar`-y ýüzler kesilen badyna ýazmak (soňky işlerde `--kernel-source` bilen 76 minudy tygşytlamak); (c) doňmagy tutýan gözegçi: ýürek urgusy ýok bolsa stack-i çap edip prosesi öldürmek, ene proses bolsa soňky nokatdan dowam etdirmek ýa-da iň gowy agram bilen kalibrleme/synaga geçmek.
  Kaggle GPU kwotasy hepdede çäkli (takmynan 30 sagat diýip bilýärin, barlamaly); v1 ~5.7 sagat sarp etdi.


### 2026-11-20 (6) — Wizual türgenleşdiriş v2 işe goýberildi

- `training/train_visual.py` täzeden guruldy: iş çaga prosesde gidýär, **gözegçi (supervisor)** bolsa
  `--stall-min` (15 min) dowamynda çykyş bolmasa stack-leri çap edip prosesi öldürýär we
  `--resume` bilen soňky epohadan dowam edýär. Iki gezek yzly-yzyna öňe gidişlik bolmasa,
  iň gowy checkpoint bilen diňe kalibrleme + test edilýär (`--eval-only`).
- Her epohada `last.pt` (dowam etmek üçin), her gowulaşmada `best.pt` + `weights.pth` +
  wagtlaýyn `model_card.json` (`provisional: true`) ýazylýar.
- `faces.tar` ýüz kesilenden **derrew** soň ýazylýar; soňky işe goýberişler ony
  `/kaggle/input` içinden awtomatik tapýar (`--kernel-source eliotalderson00/dfd-train-visual`).
- DataLoader: `timeout=600`, işçilerde OpenCV akymlary öçürildi.
- Ýerli barlag: doly akym, doňdurma (SIGSTOP) → öldürme → 23-nji epohadan dowam, SIGKILL → dowam,
  `--eval-only`, arhiwden ýüzleri dikeltmek. 8 täze unit test (jemi 118).
- Kaggle: `dfd-train-visual` **v2** 22:27 UTC-de işe goýberildi
  (`--epochs 12 --save-faces --time-budget-min 300`). Garaşylýan wagt ~3,2 sagat.

### 2026-11-20 (7) — Türkmen ses, 1-nji ädim tamamlandy (mümkinçilik barlagy)

- Kaggle `dfd-tk-probe` v1: 11 generatoryň hemmesi işledi we düşnükli türkmençe ses berdi
  (MMS-ASR boýunça CER 4–18 %): 3 wokoder (HiFi-GAN, UnivNet, Vocos), 4 kodek (DAC, Mimi,
  EnCodec 3/6 kbps), 3 TTS (MMS, OmniVoice, VoxCPM2 + Anadil), 1 ses öwrüji (kNN-VC).
- OmniVoice we VoxCPM2 CPU-da gaty haýal (RTF ≈ 44) — 2-nji ädimde GPU gerek.
- Maglumat meýilnamasy: hakyky = TurkmenSpeech (wideo boýunça bölünýär) + Common Voice 22 `tk`
  (gepleýji boýunça) + ASVspoof 2019 LA train; galp = ýokardaky generatorlar + ASVspoof train.
  **Türgenleşdirişe goşulmaýanlar:** OmniVoice (görülmedik TTS) we Vocos (görülmedik wokoder).
- Ygtyýarnama: TurkmenSpeech, MMS, OmniVoice agramlary CC BY-NC → netije model diňe täjirçilik
  däl maksat üçin (diplom işi üçin bolýar). DAC, EnCodec, kNN-VC ygtyýarnamalary barlanmady.

### 2026-11-21 (1) — Wizual model v2 tamamlandy

- Kaggle `dfd-train-visual` v2: COMPLETE, 199 minut. 12-nji epohanyň ~600-nji ädiminde işçi proses
  ýene öldürildi (`exit code -9`, v1-däki ýaly şol ýerde) — gözegçi ony 11-nji epohadan dowam
  etdirdi we iş tamamlandy. Sebäbi anyklanmady (çak: ýadyň ýuwaş-ýuwaşdan dolmagy; barlanmady).
- Iň gowy epoha 7. Temperatura 2.247. Bosagalar: surat 0.580 / 0.643, wideo 0.526 / 0.828.
- **Test (resmi bölüniş, 140 hakyky + 700 galp wideo):** wideo AUC 0.9914, EER 3.00 %, takyklyk
  96.55 %; kadr AUC 0.9832, EER 5.27 %, takyklyk 95.10 %.
- Höküm (wideo): hakyky → 93.6 / 5.7 / 0.7 % (Hakyky/Şübheli/Galp); galp → 2.3 / 4.1 / 93.6 %.
- Agramlar `weights/visual/weights.pth` (34 MB, float16) + `model_card.json` (`provisional: false`).
- HTTP API arkaly barlag (synag böleginden 5 wideo + 1 surat): 2 hakyky → Hakyky; 3 galp → 2 Galp,
  1 Şübheli; ýüz suraty → Hakyky. Wideo ~10 s (CPU), serweriň RSS-i 1194 MB.
- `faces.tar` (2 GB) Kaggle çykyşynda bar — indiki okuwlar ýüz kesmegi gaýtalamaz.
- Galan iş: başga toplumda (cross-dataset) ölçeg ýok; 12-nji epohadaky öldürilmegiň sebäbi.

### 2026-11-21 (2) — Ses üçin wagtlaýyn gorag + türkmen ses toplumyny gurujy

- **Gorag:** model kartasyna `max_verdict` meýdany goşuldy (`ModelCard`, `ModalityResult`,
  `scoring.cap`). `weights/audio/model_card.json` → `"max_verdict": "suspicious"`: ses modeli
  ýeke özi «Galp» diýip bilmeýär, netijede/PDF-de üç dilde düşündiriş belligi (`audio_capped`)
  görkezilýär. Täze (türkmençe okadylan) modeliň kartasynda bu çäk bolmaz. 8 täze test.
- **Gurujy:** `training/tk_audio/` — `sources.py` (TurkmenSpeech + Common Voice), `plan.py`
  (haýsy galp haýsy hakyky ýazgydan; bölünişler arassa, OmniVoice/Vocos diňe testde),
  `gen_*.py` (9 generator), `check_asr.py`, `build.py` (her ädim aýratyn prosesde, gözegçi,
  dowam etdirmek, her generatordan soň arhiw). `training/proc.py` — umumy gözegçi.
- Ýerli synag (CPU, 20 hakyky ýazgy): sources → resynth (5 generator) → MMS işledi, 67 ýazgy.
- Kaggle `dfd-tk-build` v1 (kiçi GPU synagy, ~400 hakyky ýazgy, 55 min çäk) 04:06 UTC-de goýberildi.
  Maksat: GPU-da ähli generatorlaryň işleýändigini we tizligini ölçemek, soň doly gurluş.

### 2026-11-21 (3) — Türkmen ses toplumy: GPU synagy geçdi, doly gurluş goýberildi

- `dfd-tk-build` v1 (kiçi synag, 15 min, 2×T4): 11 generatoryň hemmesi GPU-da işledi, 1613 ýazgy,
  OmniVoice/Vocos diňe testde. GPU tizligi (RTF): wokoder/kodek 0.02–0.06, MMS 0.04,
  kNN-VC 0.09, OmniVoice 0.48 (~2.4 s/ýazgy), VoxCPM2+Anadil 2.36 (~11.5 s/ýazgy — iň haýal).
- ASR barlagy (10 ýazgy/generator, CER): 0.05–0.16; kNN-VC 0.34–0.36 (pes hil).
- Düzedişler: kNN-VC-de VAD öçürildi (ýuwaş ýazgylary boşadýardy, 4 ýalňyşlyk), salgy toplumy
  8 → 20 ýazgy we her ses üçin bir gezek hasaplanýar; VoxCPM üçin ikinji işçi (GPU0 boşanda).
- Bellik (3-nji ädim üçin): MMS we kNN-VC çykyşy hakyky sesden ~2 esse gaty (RMS 0.13–0.15 vs
  0.06–0.07) → türgenleşdirişde iki synp üçin hem dereje deňleşdirmesi hökman.
- `dfd-tk-build` **v2 (doly gurluş)** 07:05 UTC-de goýberildi: 482 wideo × 10 + Common Voice
  (≤120/gepleýji), çäk 225 min. Garaşylýan: ~7 000 hakyky, ~22 000 galp ýazgy.

### 2026-11-21 (4) — Mugt bulutda ýerleşdirmek: GitHub Codespaces

- Mugt hyzmatlar deňeşdirildi: serwer ~1.2 GB RAM alýar, şonuň üçin 512 MB berýänler (Render,
  Koyeb, Railway) bolmaýar; Hugging Face Docker Space 2026-07-den bäri PRO talap edýär;
  Oracle (2 ARM ýadro / 12 GB) kart talap edýär. Saýlanan: GitHub Codespaces (2 ýadro, 8 GB,
  aýda 60 sagat, kartsyz).
- Goşuldy: `.devcontainer/devcontainer.json`, `scripts/codespace.sh` (setup/start/stop/info/logs;
  ilkinji başlangyçda tötänleýin parolly administrator döredýär), README bölümi.
- Hakyky codespace-da barlandy (`basicLinux32gb`): döredilenden ~4 min soň serwer taýýar;
  `smoke_test.py` geçdi; FF++ hakyky wideo → «Hakyky» (13 s), Deepfakes → «Galp» (11 s);
  dur/başla aýlawyndan soň serwer ~75 s-de özi işe başlady, hasap saklanyp galdy.
- Barlanmadyk: portuň «Public» görnüşi; brauzerde janly öňe gidişlik (SSE) proksiniň üsti bilen.
- Goşmaça (ulanyjynyň islegi: «göni URL bilen girer ýaly»): port her başlangyçda awtomatik
  «Public» edilýär (`gh codespace ports visibility`, dev container-de `github-cli` goşuldy).
  Barlandy: täze codespace-da tokensiz `smoke_test.py` geçdi; dur/başla aýlawyndan 68 s soň
  salgy ýene tokensiz açyldy. Çäk (GitHub resminamasy): ulanylmasa durýar, iň köp 12 sagat
  yzygiderli, duran gurşawy diňe eýesi açyp bilýär — hakyky önümçilik üçin VPS gerek.
- **2026-11-21 (5) — UI/UX täzelenişi** (ulanyjynyň islegi: telefon menýusynda geçişler, seljeriş
  animasiýasy, faýl görnüşini tanamak animasiýasy, ekranda `.png`/`.mp4` ýaly format ýazgylary
  bolmasyn, nädogry formatda düşnükli habar).
  - Format çipleri aýryldy; ýerine üç sany janly nyşan (Surat / Wideo / Ses).
  - `js/motion.js`: faýl görnüşi brauzerde ilkinji baýtlar boýunça kesgitlenýär (serwerdäki
    `sniff()` bilen deň; soňky söz serwerde). Nädogry faýl ýüklenmän, meýdançanyň içinde
    «Bu format goldanmaýar» diýlip görkezilýär; serweriň `unsupported_media` jogaby hem şol ýerde.
  - Tanamak: faýlyň öz suraty/kadry/tolkuny + «Surat tanaldy» nyşany, soň barlag sahypasy.
  - Seljeriş: deslapky görnüşiň üstünde skaner (tor, çyzyk, burçlar, ýylylyk), ses üçin ekwalaýzer;
    halka görnüşli göterim; tapgyr ýazgysy. Aragatnaşyk kesilse animasiýa durýar we habar çykýar.
  - Menýu: gabyk bir gezek gurulýar, işjeň bellik bir elementden beýlekisine süýşýär; telefonda
    ýüzýän aşaky panel, gysga atlar; sahypalar menýunyň ugruna görä girýär. Taryh telefonda kartlar.
  - `prefers-reduced-motion` hormatlanýar. `/static/*` üçin `Cache-Control: no-cache`.
  - Barlandy: Playwright bilen telefon (390×844) we kompýuter (1280×800), ýagty/garaňky tema;
    surat, wideo, ses, nädogry faýl; konsolda ýalňyşlyk ýok. 136 test, ruff, mypy arassa.
  - Barlanmadyk: hakyky telefon (iOS Safari), animasiýalaryň hereketi (diňe kadrlar görüldi).
- **2026-11-21 (6) — README, logo, platformalar** (ulanyjynyň islegi: macOS/Linux/Windows üçin gurnama,
  «iň gowy README-ler ýaly», Sherlock görnüşli gara logo).
  - Logo: `docs/assets/logo-light.png` (ýagty tema), `logo-dark.png` (garaňky tema); çeşme surat
    emeli aň bilen döredildi, ulanyjy iki wariantdan birini saýlady.
  - README täzeden guruldy: logo, nyşanlar, ekran suratlary, her ulgam üçin aýratyn ädimler,
    «Gurnandan soň», «Näsazlyk çyksa» (ulanyjynyň hakykatdan duş gelen ýalňyşlyklary), sazlamalar.
  - Ekran suratlaryndaky portret emeli aň bilen döredilen; model ony «Hakyky» diýýär (0.0 %) —
    README-de açyk ýazyldy (model diňe ýüz çalşygyny tanaýar).
  - CI-a `platforms` işi goşuldy: macOS (arm64) we Windows-da gurnama, testler, serwer + smoke test.
    Ilkinji işledişde tapylan ýalňyşlyklar: macOS-da `training/proc.py` (`killpg` → EPERM, düzedildi);
    Windows-da POSIX-a degişli 3 test (indi geçirilýär: faýl rugsatlary, okuw gözegçisi).
    Netije: macOS 134 geçdi, Windows 132 geçdi + 4 geçirildi, ikisinde-de smoke test geçdi.
  - Barlanmadyk: Windows-da PowerShell buýruklary (`winget`, `py`, `Activate.ps1`) — CI bash ulanýar;
    Intel Mac; Windows-da `secret.key` faýlynyň rugsatlary çäklendirilmeýär (papkanyň ACL-i miras alynýar).
- **2026-11-21 (7) — doly emeli döredilen suratlar (täze mesele, 1-nji ädim: gözleg + synag).**
  Ulanyjynyň nägileligi: README suratyndaky emeli portret «Hakyky» (0.0 %) çykdy. Sebäbi: şekil modeli
  diňe FF++ ýüz çalşygyny öwrendi. Çözgüt ugry: ikinji şekil modeli — «emeli döredilen surat» detektory.
  - Gözleg: garaşsyz deňeşdirme (arXiv 2602.07814) — açyk detektorlaryň iň gowusy (Community Forensics)
    ortaça 75 %, iň täze generatorlarda 35–42 %. Abacus.AI Smaug (Apache-2.0, 439M parametr, 880 MB;
    öz karty boýunça AUC 0.97–0.99, hakyky suratlaryň 0.4–3 %-i ýalňyş bellenýär).
  - Kiçi synag (ölçeg däl!): 4 emeli portret (häzirki generator) + 2 DALL-E 2 + 16 hakyky surat (Wikimedia Commons).
    | Model | ölçegi | 4 täze emeli | 16 hakyky (>0.5) |
    |---|---|---|---|
    | CommFor-384 (MIT) | 87 MB | 0.00–0.10 (0/4) | 0 |
    | Detectra v3 (MIT) | 44 MB | 1/4 | 1 |
    | detectra-openfake (CC BY-NC) | 30 MB | 3/4 (portret 0.10) | 2 |
    | **Smaug web ONNX (Apache-2.0, `21amd21/smaug-ai-image-detector-web`)** | 181 MB | **0.991–1.000 (4/4)** | **0 (iň ulusy 0.002)** |
    Smaug: 2 ýadroda bir kesim ≈3 s; köne DALL-E 2-de gowşak (0.59, 0.005). Synag faýllary: `/home/user/probe/`.
  - Meýilnama: (2) `onnxruntime` + model birikdirmek (surat: tutuş kadr; wideo: birnäçe kadr), aýratyn kart we
    höküm düzgüni, model GitHub-a sygmaýar (>100 MB) → gurnamada dowam etdirip ýüklemek; (3) Kaggle-da hakyky
    ölçeg + bosagalar (OpenFake synag bölegi, FF++ hakyky kadrlar); (4) README/UI täzelemek. Kepillik ýok.
- **2026-11-21 (8) — logo web sahypada; emeli suratlar üçin usullaryň analizi (0a.7 boýunça: ilki pikir, soň iş).**
  **A. Logo (ýerine ýetirildi).** Wariantlar: (1) PNG `<img>` — iki faýl (ýagty/garaňky), kiçi ölçegde bulaşyk;
  (2) CSS mask — bir PNG, ýöne goşmaça sorag we Safari prefiksi; (3) **wektor SVG (potrace bilen yzarlanan)** —
  islendik ölçegde dury, 7 KB, `currentColor` bilen tema özi uýgunlaşýar. Saýlanan: (3).
  `static/js/logo.js` (ýol), `icons.logo`, `favicon.svg` (ak plitada gara şekil — ýagty we garaňky brauzerde görünýär).
  Ýerleri: gapdal menýu (44 px), giriş sahypasy (56 px + uly ýarym dury suw belgisi), telefon giriş (60 px),
  telefon ýokarky zolak (30 px; ≤480 px-de sahypa ady gizlenýär, sebäbi aşakda sözbaşy bar).
  Playwright: 4 görnüş (kompýuter/telefon × ýagty/garaňky), konsol ýalňyşy ýok. README suratlary entek köne nyşanly — 4-nji ädimde täzelenýär.
  **B. Ulgamdaky modeller (häzir 3 neýron tor):** YuNet (ýüz tapyjy, 0.2 MB) → EfficientNet-B4 `effnet-b4-ffpp`
  (ýüz çalşygy, 34 MB; Grad-CAM — model däl, düşündiriş usuly) ; AASIST (ses, 1.3 MB). Goşuljak 4-nji: Smaug (emeli surat).
  **C. Doly emeli suraty tanamagyň usullary — deňeşdirme:**
  | # | Usul | Güýçli tarapy | Gowşak tarapy | Karar |
  |---|---|---|---|---|
  | 1 | Faýlyň içindäki gelip çykyş belligi: C2PA/JUMBF, IPTC `trainedAlgorithmicMedia`, PNG `parameters`/`prompt`, EXIF Software | takyk, mugt, 0 MB, hakyky surata ýalňyş bellik ýok | messenjer/skrinşot belligi pozýar; goly barlanmasa galplaşdyryp bolýar; biziň 4 synag suratymyzda ýok | **goşmaly (1-nji gatlak, subutnama setiri)** |
  | 2 | Öwredilen klassifikator (Smaug web ONNX, Apache-2.0) | synagda 4/4, hakykyda 0/16; garaşsyz kiçi synag (TAYO): 197/200, 0/100 | 181 MB; iň täze generatorlary sypdyryp biler; köne DALL-E 2-de gowşak | **esasy usul (2-nji gatlak)** |
  | 3 | Birnäçe klassifikatoryň ansambly | deňeşdirmede (arXiv 2602.07814) iň durnukly | MIT modeller täze suratlary sypdyrýar; galanlary CC BY-NC + ýalňyş duýduryş köp | ölçegden soň gaýtadan seretmeli |
  | 4 | El bilen düzülen alamatlar (spektr, galmagal) | kiçi, düşnükli | täze generatorlarda tötänlige ýakyn (CNNSpot 37.5 %) | ret |
  | 5 | Öwretmesiz, dikeldiş esasly (AEROBLADE we ş.m.) | täze generatorlara durnukly | birnäçe GB diffuziýa modeli + GPU gerek | ret (2 GB RAM) |
  | 6 | Bulut hyzmatlary (Hive, SynthID Detector, Sightengine) | takyklygy ýokary | faýl daşary iberilýär, internet + töleg | ret (ulgam oflaýn işlemeli) |
  | 7 | Öz modelimizi Kaggle-da öwretmek (OpenFake) | doly gözegçilik | uly iş; taýýar modelden gowy boljagy belli däl | diňe ölçeg zerurlygy görkezse |
  **Karar: 1 + 2.** Höküm: emeli-surat bahasy aýratyn subutnama; jemleýji baha iki ugruň ulusy. Bosagalar ölçelýänçä
  model `provisional` (kartdaky 0.5). Wideo kadrlary üçin Smaug barlanmadyk — ilki diňe surat, wideoda aýratyn ölçegden soň.
  **181 MB-ny eltmek:** (a) GitHub Release faýly + `dfd models --download` (Range bilen dowam etdirmek, SHA-256) — **saýlandy**;
  Docker gurnamada özi ýükleýär (0a.3 «bir buýruk» saklanýar); (b) Git LFS — mugt çägi dar, ret; (c) repo içinde bölekläp — klon agyrlaşýar, ret.
  **Indiki ädimler:** (2) birikdirmek + testler; (3) Kaggle-da ölçeg we bosagalar; (4) README, suratlar, çäklendirmeler.
  Ugur B: `dfd-tk-build` v2 11:09 UTC-de COMPLETE — netijesi entek barlanmady.
- **2026-11-21 (9) — türkmen ses toplumy (2-nji ädim) tamamlandy we barlandy.** `dfd-tk-build` v2: COMPLETE, 187.5 min, ähli tapgyr `ok`.
  Çykyş Kaggle-da galýar (kernel output, 2.9 GB tar); ýerli nusga: `/home/user/tk_build_out/tkset/` (report, manifest, asr_check, logs, samples — tar-syz).
  - **Sanlar:** 28 969 kesim ≈ 49.6 sag. Hakyky 7 060 (12.0 sag): Common Voice 2 961 (124 gürleýji), TW/YouTube 4 099 (411 wideo).
    Galp 21 909 (37.6 sag), 11 generator: kodek/wokoder gaýtadan sintez (dac, encodec, hifigan, mimi, univnet, vocos) 15 166;
    TTS MMS 2 118; MMS+kNN-VC 887; ses klonlama VoxCPM 919 + OmniVoice 1 020; ses öwürmek kNN-VC 1 799.
    Bölünişi (hakyky/galp): train 5 119 / 14 393, dev 895 / 2 531, test 1 046 / 4 985.
  - **Syzma ýok (özüm manifestden barladym):** hiç bir gürleýji/wideo topary iki bölekde däl (535 topar); hiç bir «ene» kesimiň önümi başga bölekde däl;
    klonlama/VC nusga gürleýjisi şol bir bölekden; gizlin generatorlar (`rs_vocos`, `tts_omnivoice`) diňe testde.
  - **Düşnüklilik (MMS ASR, hakyky kesime görä CER, n=25):** gaýtadan sintez 5–10 %, TTS 14–16 %, kNN-VC 20–23 % (pes däl, ýöne ulanarlyk).
  - **Kemçilikler (3-nji ädimde çözülmeli):**
    1. Ses derejesi tapawutly: `tts_mms`, `tts_mms_knnvc`, `vc_knnvc` rms ≈ 0.13–0.16, hakyky ≈ 0.05–0.065 → model «gaty ses = galp» öwrenip biler.
       Çözgüt: okuwda iki synp üçin hem RMS deňlemek + tötän güýçlendirme. (Faýllar kesilmedik: ýazyjy 0.99-a çenli kiçeldýär.)
    2. Synp deňagramsyzlygy 1 : 3 → deňagramly saýlama ýa-da agramly ýitgi.
    3. VoxCPM haýal (RTF 2.3): meýilleşdirilen 2 473-den 919 kesim; OmniVoice 1 046-dan 1 020.
    4. Hakyky test sözlemleriniň 202-si (1 046-dan) okuwda hem bar (başga gürleýji) — tekst syzmasy, gürleýji däl; hasabatda bellemeli.
    5. Spektr/zolak giňligi synplar boýunça barlanmady (ýerli gurallar ýok) — okuw skriptinde barlamaly.
  - **Indiki (3-nji ädim):** AASIST-i bilelikde öwretmek (ASVspoof 2019 LA + bu toplum), skript entek ýazylmady.
- **2026-11-21 (10) — ses modeli, 3-nji ädim: bilelikde öwretmek skripti (`training/train_audio.py`) ýazyldy we Kaggle-da işe goýberildi.**
  **Pikir (0a.7):** wariantlar — (1) diňe türkmen toplumynda öwretmek: iňlisçäni unudar; (2) diňe soňky gatlagy öwretmek: türkmen
  hakyky sesini tanamaga ýetmez (häzirki model 60-dan 0); (3) **resmi agramlardan başlap, LA train + türkmen toplumynda ähli gatlaklary
  bilelikde öwretmek** — saýlandy. Uly öňünden öwredilen modeller (wav2vec2/XLS-R + AASIST) has takyk, ýöne 300 MB+ we CPU-da haýal — ret (2 GB RAM).
  **Toplumdaky gysga ýollara garşy:** (a) ses derejesi → iki synpa hem tötän dereje (peak 0.02–0.99); (b) gysyş taryhy (hakyky türkmen
  sesi MP3/AAC/Opus-dan geçen, galplaryň köpüsi arassa) → tötän kodek (mp3/aac/opus), galpda 0.7, hakykyda 0.3 ähtimallyk; (c) synp we
  generator ölçegi → partiýa: 60 % türkmen / 40 % LA, hakyky/galp 50/50, generatorlar deň; (d) galmagal 0.3.
  **Okuw:** Adam 1e-4 → 5e-6 kosinus, batch 24 (GPU ýadyna sygmasa awtomat ýarpylanýar), 1000 ädim/epoha, wagt býujeti 240 min
  (1-nji epohadan soň epoha sany býujete görä kesgitlenýär), saýlaw: türkmen-dev EER + LA-dev EER ortaçasy. Gözegçi + `--resume`.
  **Ölçeg (serweriň öz penjireleme kody bilen):** öňki model (baseline.json), dev-de temperatura + bosagalar, türkmen test (görlen /
  görülmedik generatorlar aýratyn, generator boýunça, hakyky çeşme boýunça), LA eval doly, durnuklylyk: ýuwaş / gaty / MP3 64k.
  **Barlag:** emeli kiçi toplumda ýerli doly geçiş (CPU, kodekler bilen) — başdan ahyra işledi; 8 birlik test; ruff arassa; 143 test geçdi.
  **Kaggle:** `python3 scripts/kaggle_run.py training.train_audio --kernel dfd-train-audio --dataset anishsarkar22/asvpoof-2019-dataset-la
  --kernel-source eliotalderson00/dfd-tk-build --gpu -- --budget-min 240` (≈4.5–5 sag). Çykyş: `AASIST.pth`, `model_card.json`, `metrics.json`, `baseline.json`, `history.json`.
  **Soň (4-nji ädim):** netijä görä `weights/audio`-a goýmak; `max_verdict` çägini diňe hakyky türkmen sesinde ýalňyş duýduryş pes bolsa aýyrmak.

- **2026-11-21 (11) — interfeýs: «dünýä», menýular, Şerlok derňewi (ulanyjynyň 5 belligi boýunça).**
  **Bellikler:** (1) dil çalşyjy halanmady; (2) gapdal menýu ýygnanmaly; (3) aşakdaky «çykmak» has ösen bolmaly, başga näme goýup bolar — pikirlenmeli;
  (4) animasiýa gowşak: girende wirtual dünýä/oýun başlan ýaly bolmaly, diňe dörtburç çarçuwalar gowy däl; seljerme «kompýuter skaneri» däl-de, Şerlok derňeýän ýaly bolmaly; (5) her işden öň pikirlenmeli.
  **Analiz we saýlanan çözgütler:**
  - *Dil:* üç harply segment (TK/RU/EN) ýerine globus nyşanly düwme + açylýan sanaw; diller öz dilinde ýazylýar («Türkmençe», «Русский», «English»), baýdak ýok
    (çeşmeler: baýdak ýurdy aňladýar, dili däl; öz dilindäki at — standart). Ret edildi: baýdaklar; diňe hasap menýusynda gizlemek (giriş sahypasynda hem gerek).
  - *Gapdal menýu:* nyşanly inçe zolaga (76 px) ýygnanýar, düwme + `Ctrl/⌘+B`, ýagdaý `localStorage`-da; ýygnalanda atlar gapdalynda çykýar. Ret edildi: doly gizlemek (nawigasiýa ýitýär). Telefonda aşaky zolak öňküsi ýaly.
  - *Hasap menýusy («çykmak» ýerine):* ulanyjy kartasy → açylýan menýu: at, rol, hakyky sanlar (`/api/stats`), reňk tertibi (Ýagty/Garaňky/Awto), dil, «Ulgam barada» (wersiýa, modelleriň hakyky ýagdaýy, çäkler), «Çykmak» (tassyklama + geçiş). Üstünde ulgam ýagdaýy (modeller ýüklenenmi). Parol üýtgetmek goýulmady — API ýok.
  - *Dünýä:* (a) fon — çuňlukly nokatlar meýdany (canvas 2D, görüjä tarap ýuwaş akýar, görkeziji bilen süýşýär); (b) açylyş — logo garaňkydan gelýär, at harp-harp ýygnanýar, ýükleýji hakyky başlangyja bagly, soň lupanyň içinden «uçup» girilýär (bir wkladkada bir gezek, islendik düwme geçirýär);
    (c) giriş/çykyş — tegelek perde + «Hoş geldiňiz, …». (d) kartalar görkezijiniň astynda ýagtylanýar; sahypalar çuňlukdan gelýär; ýüklemekde dörtburç «ping» ýerine orbitalar. Ret edildi: three.js/WebGL (CSP `self`, daşky kitaphana, agyr); wideo fon (ölçeg).
    Başlangyç tertip indi garaňky (gijeki sahna); «Awto» aýdyň saýlanýar.
  - *Şerlok derňewi:* skaner çyzygy, tor, burç çarçuwalary we ýasama «ýylylyk tegmilleri» aýryldy. Ýerine: faýlyň üstünde gezýän lupa — astyndakyny hakykatdanam ulaldýar (surat: nusga; wideo: kadr; ses: tolkun), Şerlogyň ýazylyp çykýan sözleri (her tapgyrda serweriň hakykatdan edýän işi + Holmsdan jümleler), «iş №», yz zynjyry, ahyrynda höküm möhüri.
    **Dogruçyllyk:** lupanyň duran ýeri «tapyndy» däl — bezeg; şonuň üçin belgi/pin goýulmaýar, sözler diňe tapgyry beýan edýär.
  **Faýllar:** `static/js/fx.js`, `menus.js`, `sleuth.js`, `css/world.css` (täze); `app.js`, `views.js`, `ui.js`, `i18n.js` (täze açarlar, 3 dilde), `theme.js`, `css/app.css` (köne skaner aýryldy).
  **Barlag:** Playwright bilen 1440×900 we 390×800: açylyş, giriş, dil sanawy, geçiş, hasap menýusy, ýygnalan menýu, «Ulgam barada», çykyş soragy, surat/wideo/ses üstünde lupa, möhür — konsol ýalňyşsyz. `prefers-reduced-motion`-da kod boýunça öçýär (aýratyn synalmady).
  **Barlanmadyk:** hakyky telefon, Safari/Firefox; README suratlary köne görnüşde.

- **2026-11-21 (12) — Kaggle: ses okuwy (`dfd-train-audio`) başlamady, GPU nobatynda dur.**
  v1 11:51 UTC-de iberildi, 13:49-da henizem `QUEUED` (ýalňyşlyk habary ýok). Kod we sazlama barlandy: LA bukjalary we `manifest.csv` + `audio_*.tar` gabat gelýär, `enable_gpu` açyk.
  13:50-de gaýtadan iberildi (v2) — 17:00-da henizem `QUEUED`. CPU synag kerneli (`dfd-queue-probe`) derrew işläp gutardy → mesele diňe GPU-da.
  Mümkin sebäpler: (a) hepdelik GPU kwotasy gutardy (CLI görkezmeýär, saýtda «Settings → Quotas»); (b) Kaggle-yň GPU nobaty (2026-11-15 senesindäki product-feedback 757624: T4 ×2 sessiýalary «Queued»-da galýar).
  **Ölen ýol:** P100-e geçmek — CLI 2.2.5-de P100 «retired», serwer ony T4 bilen çalyşýar. Gaýtadan ibermek kömek etmeýär — indi iberme.
  **Indiki:** ulanyjy saýtda kwotany barlaýar; kernel nobatda galýar; başlansa ≈4.5–5 sagat.

- **2026-11-22 (13) — ses okuwynyň netijesi (`dfd-train-audio` v2, 6 epoha) we 4-nji ädim.**
  Kernel GPU nobatyndan soň işledi (jemi 278 min; kwota ýeterlikdi — sebäp Kaggle nobatydy). Tizlik 13–14 kesim/s → epoha 33 min → 240 minuda diňe 6 epoha sygdy.
  **Ölçeg (türkmen synag bölegi, 6031):** AUC 0.393 → **0.759**, EER 57.9 % → **31.1 %** (görlen generatorlar 26.2 %, görülmedik 37.9 %).
  Höküm: hakyky ses «Hakyky» 1.9 % → 44.4 %, «Galp» 43.2 % → 8.3 %; galp ses «Galp» 29.1 % → 42.1 %, «Hakyky» 3.6 % → 14.4 %.
  Generator boýunça «Galp» diýlen paý: tts_mms 99 %, mms+knnvc 89 %, univnet 68 %, knnvc 54 %, voxcpm 50 %, omnivoice (görülmedik) 49 %, encodec 48 %, hifigan 46 %, mimi 32 %, dac 22 %, vocos (görülmedik) 8 %.
  Şertler: ýuwaş (peak 0.05) AUC 0.678, hakyky→«Galp» 22.6 %; gaty 0.769; mp3 64k 0.751. LA eval (71 237): EER 1.62 %¹ → 3.40 %, AUC 0.9952 (¹ 3000-lik bölekde).
  **Baha:** gowulaşma uly, ýöne ygtybarly däl. tk_dev EER her epohada peselýärdi (0.389 → 0.347 → 0.317 → 0.278 → 0.245 → 0.246); soňky epohada lr iň pes derejä düşüpdi → **okuw ýetmezçilik edýär**.
  **Karar:** (a) täze agramlar `weights/audio`-a goýuldy (`aasist-tk` 2.0.0) — hakyky türkmen sesi indi 44 % «Hakyky» (öň 2 %); `provisional: true` we `max_verdict: suspicious` **galdy** (ýalňyş duýduryş 8.3 % pes däl).
  (b) okuwy dowam etdirmek: `--init` (öňki agramlardan başlamak) goşuldy; Kaggle-da `--init <raw URL> --lr 7e-5 --budget-min 540` (≈16 epoha, ≈10.2 sag GPU).
  (c) Eger AASIST 15–20 % EER-den aşak düşmese — indiki usul: SSL öň bölegi (XLS-R + ýeňil kelle; edebiýatda başga domenlerde has durnukly), ýöne ≈1.2 GB model → Smaug ýaly ýükleme ädimi gerek. Entek başlanmady.
  README (`#results`, çäklendirmeler, English) täze ölçenen sanlar bilen täzelendi; doly sanlar `docs/metrics/audio_tk_*.json`.

  **Dowamy (şol gün):** `--init` düzedildi (resmi agramlaryň bazasy öňküsi ýaly ölçenýär; başlangyç agramlar «iň gowy» hökmünde saklanýar — täze epoha diňe ondan gowy bolsa çalşyrýar; `[train]` setirinde `data wait` paýy çap edilýär — tizligiň päsgelçiligini bilmek üçin).
  **Kaggle `eliotalderson00/dfd-train-audio-2` v1 iberildi (07:06 UTC, 22 Nov)**: `--init <raw c9f36da weights/audio/AASIST.pth> --lr 7e-5 --budget-min 540` (≈15 epoha, jemi ≈10 sag; GPU kwotasyndan ≈10 sag). Gaýtadan iberme. Netije gelende: `weights/audio` + kart + README sanlary + `max_verdict` kararyny täzeden gözden geçir.

- **2026-11-22 (14) — README suratlary we awtor ady.** README suratlary täze interfeýsden täzeden alyndy (`screen-scan.jpg`, `screen-login.jpg`, `screen-upload.jpg`, `screen-phone.png`); README-däki diplom setiri aýryldy.
  Awtor ady hemme ýerde **`eliot`** (§0a.8). Commit awtory: `eliot <eliotlastdance00-art@users.noreply.github.com>`. Şahalar: `eliot` (iş şahasy) we `main` — bir ýagdaýda saklanýar.
  Git taryhy täzeden ýazyldy → **ähli commit SHA-lary üýtgedi** (ýokardaky ýazgylardaky köne SHA-lar indi ýok). Köne nusgalar (Mac, Codespace): `git fetch origin && git reset --hard origin/main`.
  Kaggle `dfd-train-audio-2` şonuň üçin **v2** hökmünde gaýtadan iberildi (07:26 UTC, 22 Nov; sazlamalar öňküsi ýaly); 07:30-da RUNNING. Gaýtadan iberme.
  Synag sahypasy: giriş `eliot`, maglumat bukjasy `/home/user/dfd-eliot-data`.

- **2026-11-22 (15) — ammaryň «About» bölegi we jemgyýet faýllary (meşhur ammarlardaky ýaly).**
  Pikirlenme: meşhur ammarlarda (a) gysga iňlisçe düşündiriş + topic-ler (gözlegde tapylmak üçin), (b) jemgyýet faýllary (GitHub «Community standards» 100 %), (c) wersiýa/release, (d) social preview suraty, (e) web sahypa (Pages/demo), (f) Docker obrazy (GHCR) bolýar. Şu gezek (a)–(d) edildi; (e), (f) teklip edildi.
  **API bilen:** description (iňlisçe, gysga), 20 topic (GitHub-da hakyky ulanylýanlary sanap saýlandy: `deepfake-detection` 1401 ammar, `anti-spoofing` 302, `image-forensics` 323, …), Wiki we Projects öçürildi (boş goşmaçalar), Dependabot duýduryşlary + hususy howpsuzlyk habary açyldy, `detection` belligi döredildi.
  **Faýllar:** `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`, `CITATION.cff` (cffconvert bilen barlandy), `.github/ISSUE_TEMPLATE/` (bug, feature, wrong verdict, config), `.github/PULL_REQUEST_TEMPLATE.md`, `.github/dependabot.yml` (diňe Actions, aýda bir toparlanan PR), README: release we ýyldyz nyşanlary, «Goşant goşmak» bölümi, `#troubleshooting` labyry.
  **Release `v0.1.0`** (CHANGELOG-dan; ölçenen sanlar we çäklendirmeler bilen).
  **Social preview:** `docs/assets/social-preview.png` (1280×640) — API ýok, ulanyjy Settings → General → Social preview-dan ýüklemeli.
  Bu faýllarda hem awtor diňe `eliot` (§0a.8); aragatnaşyk — e-poçta däl, GitHub-yň hususy habar beriş ulgamy.
