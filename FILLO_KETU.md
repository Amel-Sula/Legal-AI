# Fillo ketu

Serveri vLLM duhet te jete ngritur ne nje dritare tjeter:

    source $HOME/venv/bin/activate
    VLLM_USE_FLASHINFER_SAMPLER=0 vllm serve Qwen/Qwen3-14B-AWQ \
        --max-model-len 8192 --seed 42

Pastaj, ne kete dosje:

    source $HOME/venv/bin/activate

## Pese komanda. Asgje tjeter nuk ka pse te leshohet.

    python3 web.py                     # PRODUKTI, me faqe. http://127.0.0.1:7000
    python3 analizo.py <dokumenti>     # i njejti kontroll, nga terminali
    python3 score.py <fikstura> real   # prova: sa mire punon
    python3 shto_ligj.py <dosja>       # shton ligje te korpusi
    python3 mat_kerkimin.py            # a i prishi gje shtimi

Te dyja pranojne .docx, .pdf dhe .txt, dhe skanimet lexohen me OCR.

## Faqja

    python3 web.py

Serveri vLLM duhet te jete ngritur ne dritaren tjeter. Hap
http://127.0.0.1:7000 ne shfletues: zgjidh dokumentin, shto daten e
nenshkrimit nese e di, shtyp Kontrollo. Faqja rifreskohet vete derisa mbaron.

Tri gjera jane te qellimshme dhe nuk duhen ndryshuar pa mendje:

- **Lidhet vetem me 127.0.0.1.** Vetem kjo makine. Ne 0.0.0.0 cdo kompjuter ne
  rrjetin e zyres hap kontratat e klienteve pa fjalekalim. `KONTRATA_HOST` e
  ndryshon dhe shkruan paralajmerim ne terminal.
- **Dokumenti fshihet sapo mbaron analiza.** Vetem raporti mbetet, ne kujtese.
  Nje dosje me kontrata klienteve te mbledhura me vite eshte shkelje ne pritje
  te laptopit te vjedhur, dhe sipas Ligjit 9887 eshte ruajtje pertej qellimit.
- **Nje analize ne cdo moment.** Nje GPU, nje server. I dyti pret ne radhe dhe
  i thuhet.

Faqja nuk merr asgje nga internet: pa fonte, pa skripte, pa stil te jashtem.
Punon me kabllon e rrjetit te shkeputur, qe eshte makina per te cilen u ndertua.

## Cdo dokument, jo vetem kontrata pune

Ligji nuk caktohet me dore. Dokumenti e zgjedh vete ligjin e tij sipas fjalorit
qe permban: kontrata pune -> Kodi i Punes, kontrata qiraje -> Kodi Civil. Pastaj
kerkimi i nenit behet VETEM brenda atij ligji. Kjo matet:

    python3 korpusi.py          # cfare ka ne korpus, dhe cfare zgjedh cdo fikstura
    python3 test_cdo_dokument.py  # kontrata qiraje nga fillimi ne fund, pa GPU
    python3 test_shumeligje.py    # "Neni 5" i ligjit te gabuar bllokohet

Pse ka rendesi: me 16 kode brenda, "Neni 5" emerton 16 dispozita te ndryshme.
Cdo citim mbart ligjin e vet nga momenti kur modeli zgjedh kandidatin, dhe
verifikimi kontrollon citimin kundrejt ATIJ ligji. Pa kete, kontrolli i
vertetesise bie pa u ndjere.

## Ku kontrolli ndalon

Shkelje numerike raportohet vetem ku ligji vendos numer. Matur ne korpus:

    Kodi i Punes             116 nene nga 226 vendosin kufi, afat ose ndalim
    Kodi Civil                84 nene nga 1132
    Kodi i Procedures Civile  70 nene nga 550

Per nje kontrate qiraje, pra, pjesa me e madhe e pergjigjes nuk eshte "bie
ndesh" por "ky nen e rregullon kete klauzole, lexoje". Raporti e ndan kete
vete, dhe e shenon me ⚖ dispoziten qe vendos kufi konkret.

## Permbledhjet legjislative

Nje permbledhje ("Permbledhje Legjislacioni") mban dhjetera ligje ne nje PDF.
E ngarkuar si NJE ligj, "Neni 5" do te emertonte pese dispozita brenda te
njejtit skedar dhe asnje citim nga ajo nuk do verifikohej me. `shto_ligj.py`
tani e ndan ne ligjet pershkruese, ose e refuzon. Here e pare leshoje me:

    python3 shto_ligj.py ~/ligjet/Permbledhje_Legjislacioni --prove

`--prove` nuk shkruan asgje: vetem tregon cilat ligje do te shtoheshin dhe me
sa nene. Shikoji emrat. Nese duken sakte, leshoje pa `--prove`.

## Per t'u kthyer te OpenRouter (vetem per prova, kurre me kontrata reale)

    export OR_API_URL=https://openrouter.ai/api/v1/chat/completions
    export OPENROUTER_API_KEY=sk-or-v1-...
    export OR_MODEL=qwen/qwen3-14b

## Kujdes

Pergjigjet ne `*.key.json` i ka shkruar nje AI dhe kane dale te gabuara tri
here, cdo here aty ku modelet kishin te drejte. Cdo klauzole e shenuar "clean"
eshte e perkohshme derisa ta shohe nje avokat. Kjo vlen edhe per
`kontrata_qiraje.key.json`, ku dy klauzola te dyshimta ligjerisht jane shenuar
"pa konflikt" me qellim, sepse nuk arrita t'i lidh me dispozite numerike.
