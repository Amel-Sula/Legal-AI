# Kontrata AI — manuali i plotë

Për këdo që vazhdon punën. Shkruar më 13.10.2026. Lexoje të gjithë para se të
prekësh kodin: shumica e vendimeve këtu janë të matura, dhe disa duken të
çuditshme derisa të lexosh pse.

Pronari: Boyie (Amel Sula), Tiranë. Makina: HP Z8 G4, RTX A5000 24GB, WSL2
Ubuntu, kodi në `~/pkg`, venv në `~/venv`, PDF-të e ligjeve në `~/ligjet`.

---

## 1. Çfarë është produkti

Një avokat shqiptar ngarkon një dokument. Programi e lexon klauzolë për
klauzolë kundrejt legjislacionit shqiptar dhe kthen një raport që citon nenin,
ligjin dhe datën e tekstit. Pastaj avokati mund t'i bëjë pyetje, dhe përgjigjet
vijnë nga dispozitat e korpusit.

Vetitë mbi të cilat shitet, dhe që nuk negociohen:

1. **Asgjë nuk del nga kompjuteri.** Vetë-strehuar, modeli lokal (vLLM +
   Qwen3-14B-AWQ). Dokumentet e klientëve nuk shkojnë kurrë te një API e
   jashtme. Kjo është e gjithë arsyeja pse produkti ekziston; pa të nuk ka
   produkt, ka vetëm një ndërfaqe mbi ChatGPT.
2. **Modeli nuk shkruan ligj.** Teksti i çdo dispozite kopjohet nga korpusi me
   kod. Modeli zgjedh vetëm cilat dispozita të shfaqen, dhe (vetëm në anën e
   pyetjeve) shkruan fjali që pastaj verifikohen.
3. **Kur nuk di, e thotë.** Kjo vlen më shumë se çdo përqindje saktësie. Një
   avokat nuk ka nevojë për sistem që ka gjithmonë të drejtë; ka nevojë për
   sistem që nuk gënjen kurrë.

### Kufijtë ligjorë që duhen mbajtur mend

- Bëhet **përpunues të dhënash sipas ligjit 9887** (mbrojtja e të dhënave
  personale). Çdo zyrë avokatie që e përdor duhet të ketë marrëveshje të
  shkruar përpunimi. **Nuk është bërë ende.**
- Nëse ndonjëherë dërgohet ndonjë tekst te një API e jashtme (vetëm për prova,
  kurrë për dokumente klientësh), duhet **anonimizuar** më parë: emra, numra
  personalë, adresa. Shifrat e pagës dhe datat mbahen.
- Çelësat API: krijo të freskët, vendos limit 5 dollarë, fshij pas përdorimit.
  Mos i ngjit kurrë në bisedë.

---

## 2. Si ta nisësh

Dy dritare Ubuntu. E para mban modelin, e dyta programin.

**Dritarja 1 — modeli:**

```
source ~/venv/bin/activate
VLLM_USE_FLASHINFER_SAMPLER=0 vllm serve Qwen/Qwen3-14B-AWQ --max-model-len 8192 --seed 42
```

Prit `Application startup complete`. Mos e mbyll.

**Dritarja 2 — programi:**

```
cd ~/pkg
source ~/venv/bin/activate
python3 web.py
```

Hap `http://127.0.0.1:7000`.

`VLLM_USE_FLASHINFER_SAMPLER=0` dhe `--seed 42` janë për determinizëm; u
provuan tri leshime identike. Mos i hiq.

### Komandat e tjera

```
python3 analizo.py kontrata.pdf        # raport nga rreshti i komandës
python3 pyet.py "pyetja jote"          # pyetje nga rreshti i komandës
python3 test_web.py                    # 19 teste të faqes
python3 test_pyet.py                   # 8 teste të anës së pyetjeve
python3 verify.py                      # 9 teste të verifikuesit
python3 test_cdo_dokument.py           # 17 teste
python3 test_shumeligje.py             # 7 teste
python3 test_numrat.py                 # 16 teste
python3 mat_kerkimin.py                # matja e kërkimit, me bazë krahasimi
python3 mat_pyetjet.py --model         # matja e anës së pyetjeve
python3 mat_paralelizmin.py 1 2 4 8    # sa dokumente njëkohësisht
python3 kontrollo_titujt.py            # cilat ligje mbajnë emër të gabuar
python3 kontrollo_statusin.py          # cilat ligje janë vjetruar a shfuqizuar
```

**Rregull: pas çdo ndryshimi, lësho të gjitha testet dhe `mat_kerkimin.py`.**
Ky i fundit mban `baza_kerkimit.json` dhe të thotë çfarë u zhvendos.

---

## 3. Si punon, hap pas hapi

### 3.1 Korpusi

`korpus_ligjet.json` — 243 ligje, 19.475 njësi, nxjerrë nga PDF-të e QBZ-së.
`kodi_punes_flagged.json` — Kodi i Punës veçmas, i ndarë në **pika** (Neni 150,
pika 1), jo vetëm nene.

`korpusi.ngarko()` i bashkon të dyja dhe e etiketon çdo njësi me ligjin të cilit
i përket. Ajo etiketë bën të mundur gjithçka tjetër: zgjedhjen e ligjit,
citimin me emër ligji, dhe verifikimin brenda ligjit të duhur.

**`_zgjidh_perplasjet()`**: dy ligje të ndryshme nuk guxojnë të ndajnë të
njëjtin titull. Nëse ndodh, nenet e tyre bashkohen dhe Neni 5 i njërit mbishkruan
Nenin 5 të tjetrit — pastaj asnjë citim nuk verifikohet dot. Prandaj zgjidhet
këtu, jo besohet se nuk ndodh.

### 3.2 Kërkimi — dy shtresa

Ky është zbulimi që bën të mundur korpus të madh.

1. **Cili ligj.** `zgjidh_ligjin.ligjet_e_dokumentit()` mbledh pikët BM25 për
   ligj dhe merr dy më të lartët.
2. **Cili nen.** BM25 brenda atij ligji.

Pa shtresën e parë, me 19.475 njësi, dy shkelje të njohura binin në radhën 7 dhe
8 nga 8, dhe ligji tjetër që shtohej do i nxirrte jashtë. Me të, radhët janë
identike me ato kur ishte vetëm Kodi i Punës.

Matur (`mat_kerkimin.py`, 19.475 njësi):

```
vetem Kodi i Punes                10/10 = 100%    0 kandidate te huaj
plus te gjitha kodet               8/10 =  80%   88 kandidate te huaj
te gjitha + zgjedhje ligji        10/10 = 100%    0 kandidate te huaj
```

`retrieve.PREFIX_LEN = 4` — sa shkronja të para unifikojnë një familje fjalësh.
Ishte 6, dhe 6 i ndante familjet që ndahen te shkronja e gjashtë: "njoftuar" →
`~njoftu`, "njoftim" → `~njofti`. Prandaj Neni 143/1 dilte në radhën 218 nga 492.
Matur në të dyja anët para se të ndryshohej:

```
prefiks   mat_kerkimin (vetem KP / me zgjedhje)   pyetje: ne tri te paret
   6              9/10  /  9/10                           5/9
   5              9/10  /  9/10                           6/9
   4             10/10  / 10/10                           7/9
```

### 3.3 Ana e raportit — `pipeline.py`

Dokumenti → klauzola (`split_clauses.py`) → për çdo klauzolë, kandidatë nga
kërkimi → modeli → verifikim → raport.

**Citimi me referencë.** Modeli NUK shkruan kurrë citim. Ai kthen
`{"citim_id": "C2"}` dhe kodi e kopjon tekstin nga korpusi. Pra nuk ka shteg nga
kujtesa e modelit te syri i avokatit.

**Vlera me referencë** (`LLM_VLERA=1`). Njësoj për numrat: kodi nxjerr sasitë e
vetë klauzolës si V1..Vn, modeli kthen `vlera_id`, kodi e mbush numrin. Pa këtë,
modeli kopjonte një shifër nga teksti i LIGJIT në vendin e klauzolës.

**Verifikimi** (`verify.py`) — verdiktet:

```
OK                          citimi gjendet fjalë për fjalë
OK_NORMALIZED               gjendet pas normalizimit
WRONG_ARTICLE               teksti gjendet, por në nen tjetër
ALTERED                     teksti është ndryshuar
NOT_FOUND                   nuk gjendet askund
NO_SUCH_ARTICLE             neni nuk ekziston
EMPTY_QUOTE                 citim bosh
ARITMETIKA_NUK_QENDRON      llogaria nuk del
VLERA_JO_NE_KLAUZOLE        numri nuk është në klauzolë
PA_VLERE_KUNDREJT_KUFIRIT   klauzola s'ka numër për ta krahasuar me kufirin
LIGJ_I_PANJOHUR             ligji i cituar nuk njihet
```

**`LIGJ_I_PANJOHUR` ekziston për një gabim real timin:** `_ligjet_per()` kthente
të gjitha ligjet kur emri nuk njihej, pra kërkonte në 16 kode dhe thoshte OK. Një
citim "Neni 803 verifikohet kundrejt Kodit Civil — PASS" kalonte pa verifikuar
asgjë. Tani kthen listë bosh.

### 3.4 Ana e pyetjeve — `pyet.py`

Pyetje → kandidatë → modeli zgjedh id-të **dhe** shkruan 2–5 fjali → verifikim i
prozës → faqja.

**`verifiko_prozen()` është zemra.** Modeli lejohet të formulojë, dhe kjo
kontrollohet pas, jo kërkohet në prompt:

- Çdo fjali duhet të mbajë `[Cn]` që emërton një dispozitë të nxjerrë vërtet,
  përndryshe hidhet.
- **Çdo shifër në atë fjali duhet të gjendet në tekstin e asaj dispozite**, me
  njësinë e vet.
- Përjashtim: një fjali e shkurtër pa shifër dhe pa përmendje neni/ligji (p.sh.
  "Jo.") kalon, sepse është formulim, jo pretendim.

Faqja shkruan sa fjali u hoqën. Nuk shkurton në heshtje.

**Njësia është pjesë e shifrës.** Pyetja për kushtin e **15 për qind** të tatimit
mori përgjigje nga Neni 725, që jep **15 ditë**. Numri përputhej, kuptimi jo.
Tani `_numrat()` kthen çifte (vlerë, njësi) dhe `15 ditë` nuk vërteton `15%`.

**Zgjedhja e ligjit për pyetjet: e ndezur** (`PYET_ZGJEDH_LIGJIN=1`). Matur:

```
                     pa zgjedhje   me zgjedhje   pa zgjedhje K=30
recall@10                7/9           8/9             7/9
vs pa zgjedhje            -       fitoi 4, humbi 0   fitoi 1
```

**Buxheti i promptit: 18.000 shkronja** (`PYET_BUXHETI`). vLLM shërbehet me
`--max-model-len 8192`. Dhjetë dispozita të plota kalonin 13.000 token, kërkesa
dështonte, dhe programi binte te radha e kërkimit — që dukej si model i heshtur.
Dispozitat priten, nuk hiqen; avokati e sheh tekstin e plotë poshtë.

**Konteksti i bisedës.** Një pyetje që varet nga e mëparshmja (e shkurtër, ose
nis me "domethënë", "pra", "po", "pse") kërkohet bashkë me atë para saj, dhe
biseda i jepet modelit. Konteksti **nuk** bëhet kurrë burim: dispozitat vijnë nga
kërkimi i këtij raundi. Pa këtë, "domethen bleresi esht ne gabim?" dilte nga
**Kodi Detar**.

**Biseda rri brenda ligjeve që ka cituar** (`ligjet_e_cituara`, deri në 3).

### 3.5 Freskia e ligjit

`qbz_api.py` lexon regjistrin publik të QBZ-së (Alfresco, pa autentikim):
4.957 ligje, 3.089 bazë, 1.731 ndryshues, 97 shfuqizues; 30.198 vendime.

`kontrollo_statusin.py` krahason korpusin me regjistrin. Gjendja sot:

```
TEKST I VJETRUAR (22)      ndryshuar PAS skedarit tonë
skedari ynë më i ri (79)   në rregull
PA TE DHENA (132)          nuk dalin në regjistër me atë numër
```

Ato 22 **nuk rregullohen me rishkarkim**: skedarët e QBZ-së janë nga shkurti
2021 sepse QBZ-ja nuk i ka ribotuar ato përmbledhje. Duhen aktet ndryshuese veç
e veç.

Raporti e shkruan paralajmërimin para gjetjeve, me numrin e herëve dhe datën e
fundit.

**Kufi i njohur:** lidhja e një akti me ligjin që prek gjendet VETËM në titullin
e tij. Për ndryshimet del ~92%; **për shfuqizimet vetëm ~14%** (14 nga 97),
sepse titujt si "Për kadastrën" nuk e emërtojnë ligjin që vrasin. Lista e
shfuqizimeve është **dysheme, jo e plotë.**

### 3.6 Faqja — `web.py`

Pesë veti sigurie, secila parazgjedhje:

1. **Lidhet me 127.0.0.1**, jo 0.0.0.0. Me 0.0.0.0 çdo makinë në wifi-n e zyrës
   hap kontratat e klientëve pa fjalëkalim. `KONTRATA_HOST` e ndryshon dhe
   printon paralajmërim.
2. **Dokumenti fshihet** sapo mbaron analiza. Vetëm raporti mbetet, në kujtesë.
3. **Bisedat rrojnë në kujtesë** dhe vdesin me procesin. Asgjë në disk.
4. **Dy analiza njëkohësisht** (`KONTRATA_NJEKOHESISHT=2`), numër i matur.
5. **Asgjë nuk ngarkohet nga interneti.** Pa fonte, pa skripte të jashtme.

Rrugët: `/` (composer), `/nis`, `/analizo`, `/ngarko/<bid>`, `/pyet/<bid>`,
`/api/pyet/<bid>`, `/biseda/<bid>`, `/biseda/re`, `/raport/<bid>.md`.

### 3.7 Paralelizmi

Matur me `mat_paralelizmin.py` në A5000:

```
njekohesisht   vonesa   dok/min        vonesa   dok/min
                (para rregullimit)      (pas)
     1          5.6s      10.8          2.6s      23.5
     2          9.5s      12.6          3.4s      35.0
     4         37.3s       6.4          8.0s      29.9
     8         78.9s       6.1         15.7s      30.5
```

Kolonat e para janë arsyeja pse u matur: kapaciteti kulmonte te 2 dhe
përgjysmohej. **Matur sërish me modelin të fikur, rënia ishte identike** — pra
nuk ishte kurrë GPU-ja. Ishte indeksi BM25 i ligjit dhe verifikuesi që
rindërtoheshin për çdo dokument, Python i pastër, i serializuar nga GIL. Të dy
janë në kesh tani (`pipeline._nen_indeksi`, `pipeline._verifikuesi`).

**Determinizmi mbajti në çdo nivel** — i njëjti dokument dha të njëjtat gjetje
vetëm dhe bashkë me shtatë të tjerë. Kjo ishte vetia që mund ta bënte
paralelizmin të papërdorshëm në çdo numër.

Kapaciteti: ~35 dokumente/minutë, ~2.100 në orë.

---

## 4. Skedarët

| Skedari | Puna |
|---|---|
| `web.py` | Faqja: composer, bisedë, shirit majtas, ngarkim, API |
| `pyet.py` | Ana e pyetjeve: kandidatë, modeli, verifikimi i prozës |
| `pipeline.py` | Ana e raportit: klauzola → kandidatë → model → verifikim |
| `analizo.py` | Dokument → raport (hyrja e produktit) |
| `verify.py` | Verifikimi i citimeve dhe numrave |
| `korpusi.py` | Një vend që di se ç'është "ligji"; freskia |
| `retrieve.py` | BM25, rrënjëzim shqip, harta e koncepteve |
| `zgjidh_ligjin.py` | Cili ligj i përket dokumentit |
| `sinjale.py` | Shënon dispozitat që vendosin kufi/afat/ndalim |
| `split_clauses.py` | Ndan dokumentin në klauzola |
| `ingest.py`, `ocr.py` | Lexon pdf/docx/txt; OCR me besueshmëri |
| `shto_ligj.py` | PDF → `korpus_ligjet.json` |
| `shkarko_qbz.py` | Shkarkon bibliotekën e QBZ-së + `manifest.json` |
| `qbz_api.py` | Regjistri i akteve të QBZ-së |
| `kontrollo_statusin.py` | Cilat ligje janë vjetruar/shfuqizuar |
| `kontrollo_titujt.py` | Cilat ligje mbajnë emër të gabuar |
| `paga_minimale.py` | Paga minimale në fuqi sipas datës |
| `llm.py` | Thirrja e modelit, prompti i matur |
| `mat_*.py` | Matjet |
| `test_*.py` | Testet |

---

## 5. Si shkruhet kodi këtu

Nuk është stil, është mënyra si është ndërtuar besimi te ky program.

1. **Mos hamendëso, mat.** Tri herë në një ditë hamendësimi im ra kundrejt
   matjes. Çdo konstante në kod ka tabelën e matjes së vet në koment.
2. **Komentet thonë PSE, jo ÇFARË.** Dhe veçanërisht: çfarë dështoi më parë. Një
   koment që thotë "ky rresht ekziston sepse pa të ndodhi X" e ndalon gabimin të
   kthehet.
3. **Çdo rregullim vjen me test që dështonte më parë.**
4. **Kur programi nuk di, duhet ta thotë.** Asnjë dalje nuk duhet të duket e
   suksesshme kur nuk ka bërë punë. (Shih §6, gabimet 2 dhe 3.)
5. **Shqip për avokatin, anglisht për kodin.** Çdo tekst që sheh përdoruesi është
   shqip; emrat e funksioneve dhe komentet janë si janë.
