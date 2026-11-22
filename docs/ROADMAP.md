# Indiki işler: peýda, töwekgelçilik we ýerine ýetiriş tertibi

> Bu sanaw ýerine ýetirilen aýratynlyklar däl. Smaug birikdirilenden soňky tehniki baha.
> Esasy maksat — has köp düwme däl, nädogry ynamy azaltmak we gaýtalap bolýan hil.

## Häzirki ýagdaý

Ýedi menýu, hasaplar, üç media görnüşi, üç dil, taryh, Grad-CAM we PDF işleýär.
EfficientNet FF++ ýüz çalşygyny, Smaug bolsa häzir diňe suratdaky AI generasiýasyny barlaýar.
Ses modeli türkmençede gowulaşdy, emma entek çäkli. Smaug-yň portret regression-y düzeldi;
bu onuň hakyky durmuşda ähli suratlary dogry tanajakdygyny aňlatmaýar.

## P0 — Howpsuzlyk we dogruçyl çäkler

1. **Öň söhbetde paýlaşylan GitHub/Kaggle tokenlerini täzelemek.** Muny hasap eýesi etmeli.
   Tokenleri repoda ýa-da logda saklamazlyk olaryň öň paýlaşylandygyny ýatyrmaýar.
2. **Model/data ygtyýarnamalarynyň doly auditi.** MIT kody bilen maglumatdan gelip çykýan
   model çäklendirmeleri bir zat däl. Aýratyn-da türkmen ses çeşmeleriniň NC şertleri.
3. **Her netijede näme barlanmadygyny görkezmek.** Smaug/ýüz/ses şahasy ýok ýa-da şowsuz bolsa,
   «Hakyky» sözüni tutuş faýlyň kepilligi hökmünde düşündirmeli däl. Smaug üçin bu duýduryş
   eýýäm bar; indiki ädim — umumy coverage/quality kartasy.

## P1 — Indiki iň peýdaly iş: garaşsyz ölçeg we kalibrleme

**Näme üçin:** täze model goşmak hakyky suratlarda näçe täze ýalňyş duýduryş döredýändigini
ölçemän hil gazanylandygyny subut etmeýär. Iki detektoryň iň güýçli hökümini almak olaryň
haýsydyr biriniň ýalňyşyny hem geçirýär; FF++ sanlaryny täze ulgama göçürip bolmaýar.

- Kalibrleme üçin dev we diňe soňky baha üçin aýratyn test bölegi; şol bir surat, adam,
  wideo ýa-da onuň JPEG nusgasy iki bölege düşmesin.
- Kamera suratlary, telefon/sosial ulgam gysyşy, skrinşotlar, grafika we pes hilli suratlar.
  Häzirki/öňki generatorlar we okuw/saýlawda görülmedik generatorlar aýratyn.
- Diňe accuracy däl: AUC, EER, FPR/FNR, iki bosagaly hökümleriň paýy, çeşme/generator boýunça
  netijeler, ynam aralyklary. Ýalňyş bellenen mysallary hem saklamaly.
- Öňki portret model saýlamakda ulanyldy: ony garaşsyz benchmark hökmünde görkezmeli däl.
- Ahyrynda AI we birleşen şekil ýolunyň bosagalaryny doňdurmak; FPR ≤5% ýaly maksat diňe
  ölçeg bilen, degişli synag toplumynyň çäginde aýdylýar.

**Taýýar diýilýär:** wersiýaly manifest, bölünişik düzgüni, gaýtadan işledilýän skript, JSON
netijeler, öňki model bilen deňeşdirme; test bölegi boýunça bosaga saýlanmaýar.

## P1 — Türkmen ses okuwynyň netijesini deňeşdirmek

Işleýän okuwy gaýtadan ibermeli däl. Tamamlananda öňki agramlar bilen şol bir saklanan
testlerde deňeşdirmeli: hakyky türkmen sesinde ýalňyş duýduryş, görülmedik generatorlar,
LA eval, ýuwaş ses we kodekler. Maksat: hakyky türkmen sesinde «Galp» ≤5%; çäk diňe
ölçeg ýeterlik bolsa aýrylýar. Ýeterlik bolmasa SSL öň bölegi (meselem XLS-R) bilen kiçi
tejribe; uly modeli diňe netije zerurlygyny görkezse goşmaly.

## P1 — Hil/ýeterlik maglumat duýduryşlary

Ýüz örän kiçi, kadr garaňky, surat aşa kiçi, gürleýiş ýok ýa-da ses örän pes bolsa muny
netijeden öň düşündirmeli. Ýeterlik maglumat ýok wagty «Kesgitläp bolmady» peýdaly jogapdyr.
Hil bosagalaryny hem el çaky bilen «takyklyk kepilligi» edip görkezmeli däl.

## P2 — Smaug-y wideo kadrlaryna giňeltmek

Peýdasy: tutuş AI bilen döredilen wideolar häzir diňe ýüz çalşygy modeli bilen barlanýar.
Emma 24 kadr × 3 kesim CPU-da gymmat. Ilki az sanly giň ýaýran kadr, wagt çyzgysynda
AI/ýüz/ses tapawudy we wagt býujeti. Bir kadryň iň uly balyny göni wideo hökümi etmek
ýalňyş duýduryşy artdyryp biler. Wideo derejesinde aggregation we bosagalar aýratyn ölçelmeli.

## P2 — Ulanyş we ekspluatasiýa

| Goşundy | Näme üçin | Kabul ediş şerti |
|---|---|---|
| Parol üýtgetmek | ulanyjy howpsuzlygy | köne paroly soramak, täze hash, degişli sessiýalary ýatyrmak |
| Hasap/registrasiýa dolandyryşy | açyk salgyny gözegçilikde saklamak | diňe admin, rugsat testleri, administrator özüni soňky admin hökmünde pozup bilmesin |
| Maglumat saklama syýasaty | şahsy surat/sesleri hemişelik saklamazlyk | retention möhleti, aýyrmak, backup/restore synagy |
| Uzyn işiň goýbolsun edilmegi | CPU/ýat tygşytlamak | hakyky backend cancel, ýarym artefaktlary arassalamak |
| Nobat we serişde gözegçiligi | gaýtalanýan işe durnuklylyk | restart recovery, çäkli workers, gaýtalanýan surat/wideo/ses stress synagy |
| Brauzer elýeterliligi | hakyky telefonda ulanmak | Safari/Firefox, klawiatura, kontrast we reduced-motion barlagy |
| Paketlenen Docker obrazy | haýal internetde ýeňil gurnama | wersiýaly GHCR image, hash/SBOM, hakyky smoke test |

Faýllary buluda iberýän API ýa-da diňe bezeg üçin täze animasiýa häzir bulardan öňe geçmeli däl.

## P3 — Düşündiriş we görkeziş

- `docs/THEORY.md`: modeller, domen tapawudy, maglumat syzmasy, kalibrleme, Grad-CAM-yň çägi.
- Kanuny paýlaşylyp bilinýän demo toplumy: hakyky/galp, ýeňil/kyn we bilkastlaýyn sypdyrylýan
  mysallar. Diňe owadan üstünlikleri saýlap «takyklyk» hasaplamaly däl.
- PDF-de logo, has aýdyň model wersiýalary we barlanmadyk ugurlar; öňki hasabatlar bozulyşsyz.
- C2PA gollaryny hakykatdan barlamak aýratyn iş: ygtybarly gol hem mazmunyň doly hakykydygyny
  kepillendirmeýär; goluň ýoklugy bolsa galplyk däl. Häzirki metadata belligi bilen garyşdyrmaly däl.

## Häzir goşmagy maslahat bermeýänlerim

- **Birden köp täze neýron tor:** RAM, disk we ygtyýarnama kynlaşýar; öň ölçeg gerek.
- **Ýasama takyk göterim/agramly ansambl:** maglumat bolmasa has ynamly görünýän nädogry baha.
- **Smaug üçin ýasama heatmap:** şol modeliň düşündirişi bolmasa subutnama ýaly görünýär.
- **Redis/Kubernetes/mikrohyzmatlar:** häzirki bir serwerli oflaýn ulgam üçin çykdajy peýdadan köp;
  nobat ýa-da gerim meselesi ölçelende gaýtadan seretmeli.

**Teklip edilýän tertip:** açarlary täzelemek → ses netijesini almak we garaşsyz şekil ölçegi
→ hil/coverage duýduryşlary → wideo üçin Smaug → hasap/privacy/ekspluatasiýa amatlyklary.
