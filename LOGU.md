# Logu — çfarë u provua, çfarë u mat, çfarë mbetet

Shoqërues i `MANUALI.md`. Ky është kujtesa e projektit: gabimet e bëra, rrugët
që nuk çuan askund, dhe numrat që vendosën. Lexoje para se të "rregullosh" diçka
që duket e çuditshme — ka gjasa të jetë provuar tashmë.

---

## 1. HAPI TJETËR — nis këtu

### 1.1 Ndarësi i përmbledhjeve ngatërron emrat e ligjeve (KRITIK)

**Gjendja:** `python3 kontrollo_titujt.py` në korpusin e plotë nxjerr **20 ligje**
që mbajnë emrin e gabuar.

Shembulli i provuar:

```
=== Për Shqyrtimin e Vlefshmërisë Ligjore të Krijimit të Titujve të
    Pronësisë mbi Tokën Bujqësore
    150 nene, ligji 9948/2008
    burimi: Përmbledhje_Legjislacioni_për_Pasuritë_e_Paluajtshme_dhe_Trojet.pdf

      Neni 1 .. Neni 19     ligji i vërtetë 9948/2008 (~19 nene)
      Neni 19               "Ky ligj hyn në fuqi 15 ditë pas botimit..."
      Neni 1 .. Neni 9      LIGJ TJETËR (marrja e tokës në pronësi)
      Neni 1 .. Neni 6+     LIGJ I TRETË (planifikimi i territorit, 107/2014)
```

Pra tre ligje nën një emër. Kjo doli kur u pyet *"a ka nevoj per leje ndertimi
per shtepi kasolle"*: u kthyen pesë nene për sportelin me një ndalesë,
koeficientin e shfrytëzimit, shqyrtimin e lejeve nga KKT — të gjitha të
etiketuara si ligji i titujve të tokës bujqësore.

**Pse është kritike:** një emër i gabuar është më keq se një emër që mungon.
Teksti i nenit është i vërtetë, pra gabimi i mbijeton leximit të kujdesshëm dhe
del vetëm kur avokati e kërkon te qbz.gov.al dhe nuk e gjen. Kjo thyen vetinë
kryesore të produktit.

**Rregullimi i propozuar** (në `shto_ligj.py`, funksioni `ndaj_permbledhjen` ose
si hap pas tij):

1. Brenda një segmenti të parsuar, gjej ku **numërimi i neneve kthehet prapa**
   (Neni 19 → Neni 1). Kjo është ndarje ligji, pa asnjë njohuri për përmbajtjen.
2. Shenjë e dytë, shumë e besueshme: fjalia standarde mbyllëse
   *"Ky ligj hyn në fuqi … pas botimit në Fletoren Zyrtare"*. Nëse pas saj vjen
   "Neni 1", aty është kufiri.
3. Për çdo copë të re, kërko titullin dhe numrin në tekstin midis fundit të
   ligjit të mëparshëm dhe "Neni 1" (zakonisht `LIGJ Nr. X datë Y PËR ...`).
4. **Nëse titulli nuk gjendet, mos e fil nën emrin e mëparshëm — hidhe copën.**
   Një citim që mungon është shumë më pak i dëmshëm se një citim me emër të
   gabuar. Shëno sa copa u hodhën.
5. Test: `kontrollo_titujt.py` duhet të bjerë nga 20 në afër zeros, dhe
   `mat_kerkimin.py` nuk duhet të humbasë asnjë gjetje.

**Kujdes:** `kontrollo_titujt.py` ka edhe dy raste që NUK janë ky problem:
- "Kodi i Procedurës Civile, numri më i madh 5111" — gabim parsimi i "Neni 511"
  + "1" i një pike. Problem tjetër, më i vogël.
- Ligjet e ratifikimit të konventave kanë numërim që kthehet prapa natyrshëm
  (ligji ka 3 nene, konventa brenda tij ka 50). Mos i "rregullo" ata.

### 1.2 Pastaj

- Lësho `mat_pyetjet.py --model` pas rregullimit të titujve, me një pyetje reale
  si ajo e kasolles, për të parë nëse përgjigjja del e saktë.
- 132 ligje "PA TE DHENA" te `kontrollo_statusin.py` — nuk dihet nëse janë në
  fuqi. Shumica janë ligje ratifikimi, që rrallë ndryshohen, por nuk është
  provuar.
- 22 ligje me tekst të vjetruar: duhen aktet ndryshuese veç e veç nga QBZ-ja.
- VKM-të (30.198) nuk janë vjelë fare. 23 nene të Kodit të Punës e lënë numrin
  te një VKM.
- Juristi: klauzolat 7, 10, 12, 13, 16, 17 të `kontrata_biocheck.key.json` nuk
  janë verifikuar nga jurist. `score.py` jep 40–60% kundrejt një çelësi që ka
  dalë i gabuar tri herë.
- Nisja automatike në boot; kopje rezervë e korpusit.
- Marrëveshja e përpunimit sipas ligjit 9887, për çdo zyrë.

---

## 2. Gabimet e bëra, që të mos përsëriten

### 2.1 Pretendim nga kujtesa, jo nga teksti

Thashë se Neni 1023 i Kodit Civil ishte përgjigjja për njoftimin në kontratën e
qirasë. Neni 1023 rregullon **kontratat bankare** ("në çdo mbyllje të
llogarisë"). Dërgova punë në gabim.

**Rregulli që doli:** çdo çelës testi ndërtohet duke **kërkuar tekstin e
korpusit**, jo nga kujtesa. `pyetje_kyc.json` e ka këtë të shkruar në fushën
`si_u_ndertua`. Lexoje para se t'i besosh ndonjë përqindjeje.

### 2.2 Dalje që dukej e suksesshme pa bërë punë

Tri herë i njëjti lloj gabimi:

1. `shto_ligj.py` — të 62 PDF-të dështuan me `ModuleNotFoundError`, dhe programi
   mbylli me `korpus_ligjet.json: 243 ligje, 19126 nene` dhe listën e plotë. Ajo
   listë lexohej nga skedari i një leshimi të mëparshëm. Tani ndalon dhe thotë
   `ASNJE LIGJ NUK U PARSUA`.
2. `shkarko_qbz.py` — manifesti shkruhej vetëm kur shkarkohej diçka. Në një
   makinë ku të 94 skedarët ekzistojnë, manifesti mbetej bosh dhe hapi dukej se
   punoi. Tani data shkruhet edhe pa shkarkim.
3. `kontrollo_statusin.py` — 101 ligje pa datë binin në degën "skedari ynë është
   më i ri → në rregull". Bosh nuk është më i ri; është i panjohur.

**Rregulli:** asnjë dalje nuk duhet të duket e suksesshme kur nuk ka bërë punë.

### 2.3 Verdikt i matur me krahasim të gabuar

`mat_kerkimin.py` krahasonte numrin e gjetjeve "në buzë" midis dy kolonave dhe
shkruante *"zgjedhja nuk mjafton; mos shto ligje te tjera ende"* — mbi një
leshim ku recall ishte 10/10 dhe asgjë nuk kishte humbur. Një gjetje që
**mungon** numëron zero në buzën e saj, pra kolona që humb gjetje duket më e
shëndetshme. Tani ruhet `baza_kerkimit.json` dhe krahasimi bëhet kundrejt
leshimit të fundit.

### 2.4 Mbrojtës i vendosur pa kusht

Modeli dy herë bëri dëm: hoqi nga koka e listës një dispozitë të saktë, dhe një
herë u përgjigj me `{"zgjedhjet": []}` në një pyetje që kërkimi e kishte
përgjigjur në radhën e parë. Vendosa mbrojtës që e fuste gjithmonë të parën e
kërkimit. Ai mbrojtës pastaj vuri **Nenin 72 (prokura)** përballë pyetjes *"si
behet torta me cokollate"*.

Provova prag pikësh. Matur në korpusin e plotë: pyetje ligjore 16.8–62.6, jo
ligjore 4.9–16.2. **Hapësira 0.6 nuk është prag, është rastësi.** Provova edhe
raportin top/mediana (nuk ndan fare) dhe mbulimin e fjalëve (ndan me 0.05).

**Zgjidhja pa prag:** dy nivele. Kur modeli zgjedh dispozita, ato janë përgjigje
dhe të parën e kërkimit nuk mund ta fshijë. Kur zgjedh asgjë, nuk ka përgjigje,
dhe dispozita më e përafërt shfaqet veç, me shkrim **"NUK është përgjigje"**.
E njëjta strukturë që ana e raportit e ka që nga fillimi.

### 2.5 Hipotezë e përmbysur nga vetë prova

Rënia 80% → 60% e recall-it u diagnostikua si pasojë e ndryshimit të promptit. E
ktheva prapa promptin dhe recall-i NUK u kthye. Hipoteza ime u përmbys nga testi
im.

---

## 3. Matjet, me numra

### Kërkimi (`mat_kerkimin.py`, 19.475 njësi, prefiks 4)

```
vetem Kodi i Punes (578 nene)            10/10 = 100%    0
plus te gjitha kodet (19475 nene)         8/10 =  80%   88
te gjitha + zgjedhje ligji (19475 nene)  10/10 = 100%    0
GJETJE TE HUMBURA me zgjedhje: 0, me thelle: 0
```

### Pyetjet (`mat_pyetjet.py`, 9 pyetje me çelës nga teksti)

```
                     pa zgjedhje   me zgjedhje   K=30   zgjedhje K=30
recall@10                7/9           8/9        7/9        8/9
ne tri te paret          5/9           5/9        5/9        5/9
(me prefiks 4)           5/9           7/9        5/9        7/9
```

Me model: kërkimi e kishte të parin të duhurin 4/9, modeli 6/9, ndrequr 4,
prishur 1.

### Paralelizmi (`mat_paralelizmin.py`)

Shih MANUALI §3.7. Shkurt: 2 njëkohësisht, ~35 dok/min, determinizmi mbajti.

### Keshet (pipeline)

```
ngarkimi i korpusit:  12.5s i ftohtë  →  0.000s nga keshi
BM25 i nën-korpusit:  0.51s/dokument  →  një herë
Verifier:             0.31s/dokument  →  një herë
```

Verifikuesi ndahet mes fijeve: gjithçka shkruan, e shkruan në konstruktor. Testi
`t_keshi2.py` e provon me 8 fije njëkohësisht.

### QBZ

```
ligje:    4.957 gjithsej — 3.089 bazë, 1.731 ndryshues, 97 shfuqizues
vendime: 30.198 gjithsej — 23.259 bazë
lidhjet e nxjerra nga titulli: ~92% për ndryshimet, ~14% për shfuqizimet
```

---

## 4. Vendime që duken të çuditshme por janë me qëllim

- **Modeli nuk shkruan kurrë citim.** Edhe pse do ishte më e lehtë. Shih
  MANUALI §3.3.
- **"30" dhe "tridhjetë" janë i njëjti numër**, por "15 ditë" dhe "15%" nuk janë.
- **Dispozitat priten për modelin, jo për avokatin.** Avokati e sheh tekstin e
  plotë; modeli sheh kreun, ku zakonisht është rregulli.
- **Konteksti i bisedës nuk është kurrë burim.** Shkon te kërkimi dhe te modeli,
  por dispozitat vijnë nga ky raund dhe verifikohen nga e para.
- **Parazgjedhja e paralelizmit është 2, jo 8**, sepse kapaciteti kulmon atje —
  jo nga kujdesi.
- **`korpus_ligjet.json` nuk shkruhet kur asgjë nuk parsohet.**
- **Keshi mban mtime-in**, pra rilëshimi i `shto_ligj.py` kapet pa rinisur
  serverin. Ligj i vjetër i shërbyer sepse askush nuk rinisi serverin është
  pikërisht dështimi që ky produkt nuk e lejon.

---

## 5. Çfarë NUK duhet bërë

- **Mos shto ligje të reja derisa të rregullohen titujt.** Me 243 ligje një
  pyetje shitblerjeje doli te Kodi Detar. Me 3.000 do dalë diçka më e largët.
  Mbulesa nuk është problemi; drejtimi është.
- **Mos instalo driver NVIDIA të Linux-it brenda WSL2.** E prish plotësisht
  kalimin e GPU-së.
- **Mos hiq `--seed 42` as `VLLM_USE_FLASHINFER_SAMPLER=0`.**
- **Mos e lidh serverin me 0.0.0.0** pa e kuptuar se çdo makinë në wifi hap
  kontratat e klientëve pa fjalëkalim.
- **Mos dërgo dokument klienti te asnjë API e jashtme.** As për provë.
- **Mos e "rregullo" një numër pa e matur më parë në të dyja anët** —
  `mat_kerkimin.py` dhe `mat_pyetjet.py`.
