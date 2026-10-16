# vjetrimi.zip — paralajmërimi për tekst të vjetruar

Zinxhiri punoi. Manifesti: 94 skedarë me datë QBZ. Korpusi u riparsua i gjithi.
`kontrollo_statusin.py` tani krahason data më data dhe nuk ka më asnjë ligj në
"nuk e dimë":

    TEKST I VJETRUAR (22)      ndryshuar PAS skedarit tonë
    skedari yne me i ri (79)   ne rregull
    PA TE DHENA (132)          nuk dalin ne regjistrin e QBZ-se

## Çfarë tregojnë vërtet ato 22

Shiko datat:

    9947/2008  Për Pronësinë Industriale
               skedari yne: 2021-09-28   ndryshimi i fundit: 2026-07-23 (5 here)
    9632/2006  Për Sistemin e Taksave Vendore
               skedari yne: 2021-02-17   ndryshimi i fundit: 2025-12-11 (19 here)

Skedarët tanë janë nga shkurti 2021, sepse QBZ-ja nuk i ka ribotuar më ato
përmbledhje. Pra këto 22 ligje NUK rregullohen duke rishkarkuar: teksti i sotëm
nuk gjendet në atë PDF. Duhen aktet ndryshuese veç e veç, dhe ajo është punë
tjetër.

Ndërkohë programi nuk duhet të citojë nen nga ato ligje si të ishte në fuqi.

## Çfarë bëra

`pipeline.py` tani krahason datën tonë me regjistrin dhe e thotë në raport,
PARA gjetjeve:

    - **Për Pronësinë Industriale**: ribotuar nga QBZ më 2021-09-28.
        - **KUJDES: teksti mund të jetë i vjetruar.** Ligji 9947/2008 është
          ndryshuar 5 herë, i fundit më 2026-07-23, pas datës së skedarit tonë.

    > Nenet e cituara më poshtë duhen kontrolluar te qbz.gov.al përpara se të
    > përdoren. Verifikimi i programit tregon se citimi përputhet me korpusin
    > tonë; nuk tregon se korpusi ynë përputhet me ligjin e sotëm.

Tre gjendje, të provuara veç e veç:
ndryshuar pas nesh (paralajmërim), ndryshuar para nesh (hesht), dhe ndryshuar
por pa datë nga ana jonë (paralajmërim, se "nuk e dimë" nuk është "në rregull").
Ligji i shfuqizuar merr rresht më të rëndë. Pa regjistër, raporti thotë që nuk e
di, në vend që të lërë të kuptohet se teksti është i freskët.

## Komandat

    cd ~/pkg
    unzip -o /mnt/c/Users/User/Downloads/vjetrimi.zip
    source ~/venv/bin/activate
    python3 kontrollo_statusin.py

Pastaj një raport i vërtetë, që duhet të mbajë paralajmërimin:

    python3 analizo.py kontrata_qiraje.txt
