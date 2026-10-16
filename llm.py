#!/usr/bin/env python3
"""
The real model, replacing the stub.

Design rule carried over from the stub: the model NEVER writes a quote and
NEVER writes Albanian prose. It is shown the retrieved articles as C1..Cn and
returns only ids, booleans and numbers. The quote is copied out of the corpus
by us; the sentences the lawyer reads come from templates.

That is what lets an 8B model with shaky Albanian grammar power a product
sold to lawyers.
"""
import os, json, re, time, random, urllib.request, urllib.error

import verify

# Default is the LOCAL vLLM server. To go back to OpenRouter:
#   export OR_API_URL=https://openrouter.ai/api/v1/chat/completions
API_URL = os.environ.get("OR_API_URL", "http://localhost:8000/v1/chat/completions")
LOCAL = "localhost" in API_URL or "127.0.0.1" in API_URL
MODEL = os.environ.get("OR_MODEL", "Qwen/Qwen3-14B-AWQ")
KEY = os.environ.get("OPENROUTER_API_KEY", "local")

# THE PROMPT IS A MEASURED ARTEFACT, NOT A DRAFT.
#
# This wording measured 80% strict recall on the BIOCHECK contract. Rewording
# the first two lines to cover any document type, and adding the law's name to
# each candidate label, dropped it to 60%: the model still cited the right
# article for clause 10 (Neni 90/2) but the figures it pulled out of the clause
# changed, and the arithmetic gate rejected them. Retrieval was identical --
# mat_kerkimin.py confirmed every rank -- so the prompt was the only changed
# input.
#
# So the 80% wording is the default and the law-aware wording is an option,
# switched on with LLM_LIGJI=1, to be measured against it rather than assumed
# better. The lease contract works under BOTH; only the employment fixture has
# an answer key good enough to tell them apart.
ME_LIGJIN = os.environ.get("LLM_LIGJI") == "1"

# VALUE BY REFERENCE, behind a flag so the baseline stays reproducible.
#
# Asked to write the contract's figure, the model wrote "48 orë" for a clause
# reading "Koha javore e punes eshte 40 ore ne jave", deterministically, three
# runs out of three -- having copied the 48 out of the LAW text in its own
# candidate list. verify.vlerat() now extracts the clause's own figures and the
# model returns an id, so a figure the clause does not contain cannot be
# reported at all. Measure it against the default before trusting it.
ME_VLERA = os.environ.get("LLM_VLERA") == "1"

RREGULL_VLERA = """

RREGULL SHTESE PER VLERAT:
Nen "VLERAT NE KLAUZOLE" te jepen numrat qe permban klauzola, si V1, V2, V3...
- vlera_kontrates NUK shkruhet me dore. Vendos "vlera_id": "V2" (ose cilen t'i
  takoje). Numrin e kopjon kodi nga klauzola.
- MOS marr asnjehere numer nga dispozitat C1..Cn per vlera_id. Dispozitat jane
  ligji; vlera_id duhet te jete numer i KLAUZOLES.
- Nese klauzola nuk permban numer qe i pershtatet, hiq fare vlera_id.
Formati: {"gjetjet": [{"citim_id": "C2", "vlera_id": "V1", "lloji": "...",
"vlera_ligjore": "3 muaj", "tema": "..."}]}"""

# the laws this document was read against, set per run by pipeline.run()
LIGJET = []


def vendos_ligjet(emrat):
    global LIGJET
    LIGJET = list(emrat or [])


SYSTEM = """Je nje kontrollues klauzolash kontratash pune kundrejt Kodit te Punes shqiptar.

Te jepen: nje klauzole kontrate, dhe disa dispozita ligjore te numertuara C1, C2, C3...

PIKENISJA: SHUMICA E KLAUZOLAVE JANE TE LIGJSHME.
Ne nje kontrate tipike, 8 nga 10 klauzola nuk kane asnje problem. Dispozitat te
jepen sepse jane per te njejten TEME, jo sepse ka shkelje. Pergjigjja bosh eshte
pergjigjja e zakonshme dhe e sakte.

RAPORTO SHKELJE VETEM NESE:
1. Dispozita percakton nje kufi KONKRET (nje numer, nje afat, nje ndalim), DHE
2. Klauzola percakton nje vlere KONKRETE qe e shkel ate kufi, DHE
3. Mund ta tregosh ndryshimin me numra: kontrata X, ligji Y, dhe X e shkel Y.

MOS RAPORTO KURRE NE KETO RASTE:
- Klauzola e perserit ligjin SAKTE (p.sh. kontrata jep 5 dite, ligji jep 5 dite).
  Kjo eshte PERPUTHJE, jo shkelje. Eshte gabimi me i shpeshte: mos e bej.
- Klauzola i referohet nje neni te Kodit ose i ngarkon detyrimet ligjit.
- Klauzola flet per nje teme qe asnje nga dispozitat nuk e rregullon
  (konfidencialitet, forca madhore, zgjidhje mosmarreveshjesh, njoftime,
  ndryshime te kontrates, taksa, sigurime shoqerore, dokumenta punesimi).
- Dispozita lejon marreveshje ndryshe me shkrim dhe klauzola eshte pikerisht
  nje marreveshje me shkrim.
- Klauzola i jep punemarresit ME SHUME se minimumi ligjor. Me shume eshte e lejuar.
- Ke dyshime. Ne dyshim, mos raporto.

RREGULLA TE PREREA:
- Mos shkruaj asnjehere tekstin e ligjit. Vetem numrin e dispozites (C1, C2...).
- Perdor VETEM dispozitat e dhena. Mos cito nga kujtesa.
- vlera_kontrates dhe vlera_ligjore duhet te jene numra me njesi (p.sh. "6 muaj",
  "25 per qind"), te marra fjale per fjale nga klauzola dhe nga dispozita.
- Pergjigju VETEM me JSON, pa tekst tjeter.

Formati:
{"gjetjet": [{"citim_id": "C2", "lloji": "tejkalim_kufiri", "vlera_kontrates": "6 muaj", "vlera_ligjore": "3 muaj", "tema": "periudha e proves"}]}

Pa shkelje:
{"gjetjet": []}

lloji: tejkalim_kufiri (kalon nje maksimum), nen_kufiri (bie nen nje minimum),
mungese_kufiri (nuk vendos kufi aty ku ligji kerkon nje)."""


def _system():
    """The 80% prompt, plus whichever measured variants are switched on."""
    if not (ME_LIGJIN or ME_VLERA):
        return SYSTEM
    s = SYSTEM
    if ME_LIGJIN:
        emrat = ", ".join(LIGJET) if LIGJET else "legjislacionit shqiptar"
        s = s.replace(
            "klauzolash kontratash pune kundrejt Kodit te Punes shqiptar",
            f"klauzolash dokumentesh kundrejt: {emrat}").replace(
            "nje klauzole kontrate", "nje klauzole e dokumentit")
    if ME_VLERA:
        s += RREGULL_VLERA
    return s


def build_prompt(clause, candidates):
    lines = [f"KLAUZOLA {clause['nr']} ({clause['titulli']}):", clause["teksti"], "", "DISPOZITAT:"]
    for i, u in enumerate(candidates):
        # The law's name goes in the label, never in the answer: the model
        # returns C2 and the code looks up which law C2 came from. Showing it
        # matters anyway -- with several codes retrieved, a Civil Code article
        # and a Labour Code article can look interchangeable out of context.
        ligji = u.get("titulli_ligjit")
        etiketa = (f"{ligji} — {u['ref']}" if (ligji and ME_LIGJIN
                   and len(set(LIGJET)) > 1) else u["ref"])
        lines.append(f"C{i+1} [{etiketa}]: {u['teksti']}")
    if ME_VLERA:
        vs = verify.vlerat(clause["teksti"])
        if vs:
            lines += ["", "VLERAT NE KLAUZOLE:"]
            lines += [f"V{i+1}: {v}" for i, v in enumerate(vs)]
        else:
            lines += ["", "VLERAT NE KLAUZOLE: (asnje numer i matshem)"]
    lines += ["", "A bie ndesh klauzola me ndonje dispozite? Pergjigju vetem me JSON."]
    return "\n".join(lines)


def _vlera_kontrates(g, clause):
    """The contract figure: looked up from the clause, never taken as written."""
    if not ME_VLERA:
        return g.get("vlera_kontrates", "-")
    vs = verify.vlerat(clause["teksti"])
    m = re.fullmatch(r"V?(\d{1,2})", str(g.get("vlera_id") or "").strip().upper())
    if m and 1 <= int(m.group(1)) <= len(vs):
        return vs[int(m.group(1)) - 1]
    return "-"


def _post(payload, timeout=120):
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _extract_json(text):
    """Models wrap JSON in prose or fences no matter what you tell them."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"```(?:json)?", "", text)
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(text[i:j + 1])
    except json.JSONDecodeError:
        # last resort: trim trailing junk one char at a time
        for k in range(j, i, -1):
            try:
                return json.loads(text[i:k + 1])
            except json.JSONDecodeError:
                continue
    return None


def ask(clause, candidates, retries=5):
    """Returns findings in the same shape the stub produced."""
    if not KEY:
        raise RuntimeError("OPENROUTER_API_KEY nuk eshte vendosur")

    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": _system()},
                     {"role": "user", "content": build_prompt(clause, candidates)}],
        "temperature": 0,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
    }
    if LOCAL:
        # Qwen3 thinks out loud by default; the <think> block can swallow the
        # whole budget before any JSON appears. vLLM lets us turn it off.
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    last = None
    for attempt in range(retries + 1):
        try:
            resp = _post(payload)
            # some models return null content when they emit only reasoning
            txt = resp["choices"][0]["message"].get("content") or ""
            data = _extract_json(txt)
            if data is None:
                last = f"JSON i pavlefshem: {txt[:160]}"
                continue
            out = []
            for g in data.get("gjetjet", []) or []:
                if not g.get("citim_id"):
                    continue
                out.append({
                    "ka_konflikt": True,
                    "citim_id": str(g["citim_id"]).strip().upper(),
                    "lloji": g.get("lloji", "tejkalim_kufiri"),
                    "vlera_kontrates": _vlera_kontrates(g, clause),
                    "vlera_ligjore": g.get("vlera_ligjore", "-"),
                    "tema": g.get("tema", ""),
                })
            return out or [{"ka_konflikt": False}]
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            last = f"HTTP {e.code}: {body}"
            if e.code in (429, 500, 502, 503, 529):
                # exponential backoff with jitter: a burst of parallel requests
                # all retrying on the same schedule just recreates the burst
                time.sleep(min(30, 2 ** attempt) + random.uniform(0, 1.5))
                continue
            break
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(2)

    print(f"    [model deshtoi, klauzola {clause['nr']}] {last}")
    return [{"ka_konflikt": False, "_gabim": last}]
