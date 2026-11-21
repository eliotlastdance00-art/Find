# Deepfake Detektor — dipfeýkleri kesgitleýän ulgam

[![CI](https://github.com/eliotlastdance00-art/Find/actions/workflows/ci.yml/badge.svg)](https://github.com/eliotlastdance00-art/Find/actions/workflows/ci.yml)

Wideo, surat we ses faýllarynyň hakykydygyny ýa-da emeli usulda üýtgedilendigini barlaýan
web ulgam. Ýüz çalşylan (face swap) wideolary we suratlary, emeli döredilen ýa-da üýtgedilen
sesi kesgitleýär, galp bolmak ähtimallygyny göterimde görkezýär, **Hakyky / Şübheli / Galp**
diýen netije berýär, şübheli ýerleri ýylylyk kartasy (heatmap) bilen belleýär we PDF hasabat
taýýarlaýar.

*English summary: [see below](#english).*

## Mümkinçilikler

| № | Menýu | Näme edýär |
|---|---|---|
| 1 | **Giriş** | Hasaba girmek / hasap döretmek (Argon2id, JWT) |
| 2 | **Faýl ýüklemek** | Wideo, surat, ses — süýräp goýmak ýa-da saýlamak; faýlyň görnüşi mazmuny boýunça barlanýar |
| 3 | **Barlag** | Kadrlara bölmek → ýüzi tapyp kesmek → sesi taýýarlamak → neýron tor; ädimler göni wagtda görkezilýär |
| 4 | **Netije** | Galp bolmak ähtimallygy (%), höküm, kadrlar we ses bölekleri boýunça grafikler |
| 5 | **Bellenen ýerler** | Grad-CAM ýylylyk kartalary: modeliň ünsüni çeken ýerler |
| 6 | **Hasabat** | PDF hasabat — türkmen, rus ýa-da iňlis dilinde |
| 7 | **Taryh** | Öňki barlaglar, gözleg, süzgüçler, statistika (SQLite) |

Interfeýs üç dilde: **türkmençe, rusça, iňlisçe**; açyk we garaňky reňk tertibi; telefon
ekranyna uýgunlaşýar.

## Çalt başlamak (Docker)

Diňe [Docker](https://docs.docker.com/get-docker/) gerek. Modeller eýýäm ammaryň içinde.

```bash
git clone https://github.com/eliotlastdance00-art/Find.git
cd Find
docker compose up --build
```

Soňra brauzerde <http://localhost:8000> açyň. Ilkinji döredilen hasap administrator bolýar.

Sazlamalar hökmany däl. Üýtgetmek isleseňiz: `cp .env.example .env` we içini düzediň
(administrator hasaby, faýl çägi, kadr sany we ş.m.). Maglumatlar `dfd-data` tomunda saklanýar.

## Docker-siz işletmek

Python 3.11+ gerek (FFmpeg aýratyn gurmak gerek däl — `imageio-ffmpeg` bilen gelýär).

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -e .
dfd serve                                               # http://localhost:8000
```

Beýleki buýruklar: `dfd create-user <at> --admin`, `dfd models`. API resminamasy:
<http://localhost:8000/api/docs>.

## Nähili işleýär

```
faýl ─► görnüşini anyklamak ─► taýýarlamak ─────────────► seljermek ───────────► netije
        (mazmuny boýunça)      wideo: kadrlar (FFmpeg/OpenCV)   EfficientNet-B4      ähtimallyk %
                               ýüz: YuNet → kesmek              AASIST (ses)         Hakyky/Şübheli/Galp
                               ses: 16 kHz mono, 4 s bölekler   Grad-CAM             PDF hasabat, taryh
```

* **Şekil (ýüz çalşygy):** EfficientNet-B4, FaceForensics++ (c23) maglumatlarynda okadyldy.
* **Ses (emeli ses):** AASIST, ASVspoof 2019 LA; awtorlaryň resmi agramlary.
* **Düşündiriş:** Grad-CAM — ýüzüň haýsy ýerleri «galp» bahasyna täsir edendigini görkezýär.
* **Höküm:** iki bosaga barlag maglumatlarynda saýlanýar; aralykdaky bahalar «Şübheli».
  Wideoda ses diňe goşmaça subutnama — ol hökümi «Şübheli» derejesine çenli ýokarlandyryp bilýär.
  Ýüz tapylmasa we ses bolmasa, ulgam çak etmeýär: «kesgitläp bolmady» diýýär.

Jikme-jik: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Modeller we ölçenen netijeler

Bu ýerde diňe hakykatdan ölçenen sanlar ýazylýar. Çig maglumatlar: `docs/metrics/`.

### Ses — AASIST (deslapky ölçeg)

Awtorlaryň resmi agramlary (gaýtadan okadylmady). ASVspoof 2019 LA toplumynyň **tötänleýin
böleginde** ölçendi: dev-den 3000 ýazgy (temperatura we bosagalary saýlamak üçin), eval-dan
3000 ýazgy (synag üçin; 304 hakyky, 2696 galp). Doly toplum bilen ölçeg entek geçirilmedi,
şonuň üçin model karty `provisional` diýlip bellenen.

| Görkeziji | dev (3000) | eval (3000) |
|---|---|---|
| AUC | 0.9998 | 0.9991 |
| EER | 0.38 % | 1.62 % |

Eval böleginde höküm (bosagalar: ≤ 3.0 % — Hakyky, ≥ 99.0 % — Galp, arasy — Şübheli):

| Hakykatda | Hakyky | Şübheli | Galp |
|---|---|---|---|
| Hakyky ses (304) | 96.4 % | 3.6 % | 0 % |
| Galp ses (2696) | 0.7 % | 34.8 % | 64.6 % |

Galp sesleriň üçden biri «Şübheli» bolýar: eval böleginde bosagalar saýlananda görülmedik
13 usul (A07–A19) bar. Iň kyn usullar: A18 (EER 4.9 %), A17 (3.0 %).

### Şekil — EfficientNet-B4

FaceForensics++ (c23) toplumynda okadyldy (`training/train_visual.py`, Kaggle 2×T4, 12 epoha,
iň gowy — 7-nji epoha). Toplumyň **resmi bölünişi** ulanyldy: okuw 4320 wideo, barlag
(validation) 840, synag (test) 840; bir adam diňe bir bölekde bar. Temperatura we bosagalar
barlag böleginde saýlandy, aşakdaky sanlar bolsa modeliň hiç görmedik **synag böleginde** ölçendi
(140 hakyky + 700 galp wideo; 2240 + 11200 kadr).

| Görkeziji | Kadr (surat) | Wideo |
|---|---|---|
| AUC | 0.9832 | 0.9914 |
| EER | 5.27 % | 3.00 % |
| Takyklyk (bosaga 0.5) | 95.10 % | 96.55 % |

Synag böleginde wideo boýunça höküm (bosagalar: ≤ 52.6 % — Hakyky, ≥ 82.8 % — Galp):

| Hakykatda | Hakyky | Şübheli | Galp |
|---|---|---|---|
| Hakyky wideo (140) | 93.6 % | 5.7 % | 0.7 % |
| Galp wideo (700) | 2.3 % | 4.1 % | 93.6 % |

Usullar boýunça wideo AUC: Deepfakes 0.997, FaceShifter 0.996, Face2Face 0.992,
FaceSwap 0.991, NeuralTextures 0.982 (iň kyny).

Bu sanlar diňe FaceForensics++ üçin dogry. Başga toplumlarda (meselem, Celeb-DF) ölçeg
geçirilmedi; adatça şeýle modelleriň takyklygy nätanyş maglumatlarda ep-esli peselýär.
Çig maglumatlar we ROC egrisi: `docs/metrics/visual_effnet_b4_ffpp*`.

## Çäklendirmeler (dogruçyl bellik)

* Netije — awtomatiki modeliň bahasy, kepillik däl. Möhüm karar üçin hünärmeniň barlagy zerur.
* Şekil modeli FaceForensics++ maglumatlaryndaky bäş usuly öwrendi. Başga usullar bilen
  (meselem, doly emeli döredilen suratlar, diffuziýa modelleri, täze face-swap programmalary)
  ýasalan materiallarda takyklyk ep-esli pes bolup biler.
* Güýçli gysylan, kiçi ýa-da garaňky wideolarda hakyky faýl «Şübheli» diýlip bilner.
* Ses modeli diňe **iňlis** dilinde ölçenen. Türkmen dilindäki synagda ol ýalňyşdy (60 hakyky
  ýazgynyň hiç biri «Hakyky» çykmady), şonuň üçin türkmen dilinde okadylan model taýýar bolýança
  ses boýunça höküm «Şübheli» derejesinden ýokary çykarylmaýar (`model_card.json` → `max_verdict`).
* Ses modeli **gürleýiş** üçin okadylan. Aýdym-saz, şowhun ýa-da arassa ton ýaly gürleýiş däl
  seslerde netijä ynanmaly däl (şonuň üçin wideoda ses hökümi «Galp» edip bilmeýär).
* Ulgam diňe ýüzi barlaýar; ýüz ýok bolsa şekil boýunça baha berilmeýär.

## Işläp düzmek

```bash
make install     # CPU PyTorch + taslama + gurallar
make check       # ruff + mypy (strict) + pytest
make run
```

Testler hakyky zynjyry (FFmpeg, OpenCV, PyTorch, Grad-CAM, PDF) emeli döredilen faýllarda we
kiçi tötänleýin torlarda işledýär — internet ýa-da GPU gerek däl. GitHub Actions her push-da
lint, tip barlagy, testler (Python 3.11 we 3.13), soňra Docker obrazyny gurup, işledip,
`scripts/smoke_test.py` bilen barlaýar.

Modelleri gaýtadan okatmak (Kaggle GPU): `training/train_visual.py`, ses modelini
kalibrlemek we bahalandyrmak: `training/eval_audio.py`; işe goýbermek üçin
`scripts/kaggle_run.py`.

## Gurluşy

```
src/dfd/domain          arassa logika: düzgünler, höküm, portlar
src/dfd/application     ulanyş ýagdaýlary: giriş, barlag
src/dfd/infrastructure  SQLite, FFmpeg, modeller, Grad-CAM, PDF, howpsuzlyk
src/dfd/presentation    FastAPI + web interfeýs (HTML/CSS/JS, daşarky kitaphanasyz)
training/               modeli okatmak we bahalandyrmak
tests/                  unit we API testleri
weights/                modeller we olaryň kartlary (model_card.json)
```

## Ygtyýarnama

MIT — `LICENSE`. Üçünji taraplaryň materiallary: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

<a id="english"></a>
## English

A web application that checks whether a video, image or audio file is genuine or
manipulated: face-swap detection (EfficientNet-B4 trained on FaceForensics++), synthetic
voice detection (AASIST, ASVspoof 2019), a fake probability with a three-way verdict
(*Real / Suspicious / Fake*), Grad-CAM heatmaps, PDF reports and a scan history. The UI is
available in Turkmen, Russian and English.

**Run it:** `docker compose up --build`, then open <http://localhost:8000>. Model weights
are in the repository; no other setup is required. Without Docker: install CPU PyTorch,
`pip install -e .`, `dfd serve`.

**Stack:** Python, FastAPI, SQLAlchemy/SQLite, PyTorch + timm, OpenCV (YuNet), FFmpeg,
fpdf2; plain HTML/CSS/JS front end with no external assets. Clean architecture
(domain / application / infrastructure / presentation), strict typing (mypy), ruff, and a
test suite that runs the real pipeline on synthetic media. CI builds and smoke-tests the
Docker image. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design and security
notes, and the *Çäklendirmeler* section above for the limitations: the verdict is a model
estimate, not proof, and accuracy drops on manipulation methods unlike the training data.
