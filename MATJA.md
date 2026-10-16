# matja.zip — hapi 2: sa avokatë njëkohësisht

## Para kësaj: e pata gabim për Nenin 1023

Thashë që mungonte Neni 1023 dhe të çova pas tij. Kjo ishte gabim i im nga
kujtesa, dhe `kontrata_qiraje.key.json` e thotë bardhë e zi: tri konfliktet e
pritura janë klauzola 2 (Neni 803), klauzola 6 (Neni 818) dhe **klauzola 8
(Neni 816)**. Neni 1023 nuk është fare në çelës — dhe nuk duhet të jetë: është
dispozitë e kontratave BANKARE ("në çdo mbyllje të llogarisë"). Të ishte dalë
për një kontratë qiraje, do kishte qenë gjetje e rremë.

Pra kërkimi nuk u ul: `mat_kerkimin.py` dha 9/10 me radhë identike, 0 kandidate
nga ligje të tjera. Korpusi i ri nuk kostoi gjë. Mungesa e vërtetë është
**klauzola 8 / Neni 816**, dhe kërkimi e nxori atë në radhën e parë — pra
modeli e pa dhe nuk e shënoi.

Pse e kapërceu, me gjasë: fjalia e parë e Nenit 816 thotë që qiramarrësi NUK ka
të drejtë shpërblimi, e cila përputhet me klauzolën. Shkelja është me kusht,
vetëm kur ka pëlqim — çelësi i vetë e quan "shkelje me kusht". Pra kjo është
pyetje për juristin, bashkë me klauzolat e biocheck-ut, dhe nuk e ndjek më me
hamendje. Nuk mund të pretendoj më as "3/3" të herës së kaluar: vjen nga e
njëjta kujtesë që e pati gabim Nenin 1023.

## Matja

    python3 mat_paralelizmin.py                      # 1, 2, 4, 8
    python3 mat_paralelizmin.py kontrata_qiraje.txt 1 2 4 8 16

Mat tre gjëra veç e veç, se rregullohen në mënyra të ndryshme:

    koha e korpusit   CPU, një herë. 19.475 dispozita + indeksi BM25.
    vonesa            sa pret NJË avokat. Kjo është ajo që ndjen ai.
    dokumente/min     kapaciteti total. Kjo vendos sa firma mban makina.

Dhe një të katërt, që peshon më shumë se tri të parat: **determinizmin.** vLLM-i
i grupon kërkesat njëkohëse, dhe përbërja e grupit ndryshon radhën e
mbledhjeve në pikë të dhjetë. I njëjti nen, pyetur vetëm dhe pyetur bashkë me
shtatë të tjerë, mund të kthehet i ndryshëm. Për këtë produkt kjo nuk është
detaj shpejtësie: i gjithë pretendimi është që i njëjti dokument jep të njëjtin
raport. Pra çdo raport krahasohet shkronjë për shkronjë me atë të bërë vetëm, dhe
nëse ndryshojnë, numrat e shpejtësisë nuk vlejnë derisa kjo të rregullohet.

Gishti i krahasimit shpërfill emrin e skedarit dhe kap gjetjen e humbur ose
numrin e ndryshuar — e provuar veç.

## Dy rregullime që i hoqa nga rruga

**Korpusi ngarkohej për çdo kërkesë.** `web.py` thërret `run()` për çdo upload,
dhe `run()` rilexonte të 19.475 dispozitat dhe rindërtonte indeksin BM25 nga e
para — sekonda CPU dhe një kopje e dytë e korpusit në kujtesë për çdo dokument
njëkohësisht. Tani ngarkohet një herë për proces. Keshi mban mtime-in e
skedarit, pra rilëshimi i `shto_ligj.py` kapet në kërkesën tjetër dhe nuk
shërben ligj të vjetër derisa dikush rinis serverin.

**Brava e web.py** nuk ishte vendim, ishte mungesë vendimi. Tani është semafor
dhe numri vjen nga matja, nuk nga hamendja:

    KONTRATA_NJEKOHESISHT=4 python3 web.py

Parazgjedhja mbetet **1**, derisa matja të jetë lëshuar në këtë makinë. Dy
mënyrat si dështon para një avokati janë GPU pa kujtesë dhe, më keq, i njëjti
dokument që kthen gjetje të ndryshme sipas trafikut.

## Komandat

Lëre vLLM-in ndezur në dritaren e dytë. Në të parën:

    cd ~/pkg
    unzip -o /mnt/c/Users/User/Downloads/matja.zip
    source ~/venv/bin/activate
    python3 mat_paralelizmin.py kontrata_qiraje.txt 1 2 4 8

Merr disa minuta. Dërgoma tabelën e plotë bashkë me verdiktin.
