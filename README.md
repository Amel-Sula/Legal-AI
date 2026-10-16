# Kontrolli i kontratave te punes — pipeline

Çdo gje funksionon pa GPU. Modeli thirret permes OpenRouter.

## Files

| File | Çfare ben |
|---|---|
| `kodi_punes_flagged.json` | Korpusi. 226 nene, 578 pika, 114 kufij te shenuar. **Ky eshte aseti.** |
| `split_clauses.py` | Kontrata -> klauzola te numeruara |
| `retrieve.py` | Klauzole -> 8 dispozitat me te lidhura (BM25) |
| `llm.py` | Modeli. Kthen vetem id-te C1..C8, kurre tekst ligji |
| `verify.py` | Bllokon çdo citim te shpikur, te ndryshuar ose te gabuar |
| `pipeline.py` | I lidh te gjitha, nxjerr raportin |
| `score.py` | Krahason me pergjigjet e sakta |
| `kontrata_test_01.txt` | Kontrate testi me 7 shkelje te qellimshme |
| `kontrata_test_01.key.json` | Pergjigjet e sakta, te shkruara me dore |

## Si ta nisesh

Duhet Python 3. Vendos çelesin e OpenRouter:

**Windows (PowerShell):**
```powershell
$env:OPENROUTER_API_KEY="sk-or-v1-..."
$env:OR_MODEL="qwen/qwen3-8b"
python pipeline.py kontrata_test_01.txt real
```

**Linux / Mac:**
```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
export OR_MODEL="qwen/qwen3-8b"
python3 pipeline.py kontrata_test_01.txt real
```

## Per te marre rezultatin me numra

```bash
python3 score.py kontrata_test_01.txt real
```

Te jep:
- **recall** — sa nga shkeljet e verteta i kapi
- **precision** — sa alarme false ngriti
- çfare bllokoi verifikuesi dhe pse

## Modelet per te provuar

```
qwen/qwen3-8b                  # me i lire, kaloi testet shqip
qwen/qwen3-14b
mistralai/mistral-small-3.2-24b-instruct
```

Ndrysho `OR_MODEL` dhe nis perseri. Modeli me i vogel qe kalon percakton
sa VRAM te duhet, pra edhe sa kushton makina.

## Rregulli i arkitektures

Modeli NUK shkruan kurre tekstin e ligjit dhe NUK shkruan shqip per klientin.
Ai kthen vetem id, numra dhe true/false. Citimin e kopjojme ne nga korpusi.
Fjalite qe lexon avokati dalin nga shabllonet ne `pipeline.py`.

Prandaj nje model 8B me gramatike te dobet shqipe mund te shesesh te avokatet.
