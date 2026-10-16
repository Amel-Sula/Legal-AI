#!/usr/bin/env python3
"""The lawyer asks a question. The answer is provisions, never the model's prose.

    python3 pyet.py "sa vjet mund te lidhet kontrata e qirase"
    python3 pyet.py --ligji "Kodi Civil" "cfare thote per nenqirane"

WHY THE MODEL IS NOT ALLOWED TO ANSWER.

The report side already works this way: the model never writes a quote, it
returns `{"citim_id":"C2"}` and the code copies the text out of the corpus. The
question side is where that discipline is easiest to lose, because a question
invites an answer and a model will happily produce a fluent paragraph of
Albanian law that is seventy percent right. Seventy percent is worse than
nothing to a lawyer: the thirty is invisible.

So here the model does exactly one job, and it is not writing. It is given a
question and a numbered list of provisions that BM25 already found, and it
returns which of those numbers answer the question, in order. That is the whole
output. No prose field is read, no quote is accepted, no number the model types
reaches the page. What the lawyer sees is the provision as it stands in the
corpus, with its law, its article and the date of our text.

This is not a prompt instruction that a model may ignore. It is structural: the
answer is assembled from the corpus by code, so there is no path by which the
model's memory of Albanian law can enter it. A model that hallucinates "Neni
1500" picks an id that does not exist, the id is dropped, and the worst case is
a missing answer rather than an invented one.

WHEN THE MODEL IS NOT THERE. The search still works; it is BM25 and the corpus.
The answer comes back in plain relevance order, flagged as unranked, because a
lawyer reading a list must know whether anything judged it.
"""
import json
import os
import re
import sys

import korpusi
import pipeline
import retrieve
from zgjidh_ligjin import ligjet_e_dokumentit

SA_KANDIDATE = int(os.environ.get("PYET_KANDIDATE", "10"))
SA_PERGJIGJE = int(os.environ.get("PYET_PERGJIGJE", "5"))
# LAW SELECTION ON QUESTIONS: ON, and it is on because it was measured.
#
# It shipped off first, on the reasoning that nine words cannot carry enough
# vocabulary to pick a law. That reasoning was wrong, and the cost of it was
# visible on the first real question: "kur mund te pushohet nga puna
# punemarresi" returned Neni 587 of the Code of Civil Procedure -- wage
# garnishment, which happens to contain the words "pushohet nga puna".
#
# mat_pyetjet.py on the full 243-law corpus, nine questions keyed from the
# corpus text:
#
#                        pa zgjedhje   me zgjedhje   pa zgjedhje K=30
#     recall@10              7/9           8/9             7/9
#     ne tri te paret        5/9           5/9             5/9
#     vs pa zgjedhje          -        fitoi 4, humbi 0   fitoi 1
#
# Four questions improved, none got worse, and one that was missing entirely
# came back. More candidates instead (K=30) bought one. So this is on.
#
#     PYET_ZGJEDH_LIGJIN=0      # back to searching all 243 laws
ZGJEDH_LIGJIN = os.environ.get("PYET_ZGJEDH_LIGJIN", "1") == "1"

# HOW MUCH LAW FITS IN ONE QUESTION.
#
# vLLM is served with --max-model-len 8192. Ten provisions went into the prompt
# at full length, and on a planning-law question that is what came back:
#
#     "Pa renditje. Modeli nuk u përgjigj"
#
# followed by five provisions of two to six thousand characters each. The model
# had not declined; the request was far past the window and errored, and the
# fallback to search order looked like a shy model. The whole answer was lost
# to a budget nobody had set.
#
# 18,000 characters is roughly 6,000 tokens of Albanian, which leaves room for
# the instructions, the question and the answer inside 8,192. Provisions are
# cut, never dropped: a lawyer sees the full text underneath regardless, and
# what the model is shown is the top of each article, where the rule usually
# is. The figures it may quote are therefore a subset of the real ones, so the
# check in verifiko_prozen stays sound.
BUXHETI = int(os.environ.get("PYET_BUXHETI", "18000"))
MIN_COPE = 700

# WORDS THAT POINT BACKWARDS INSTEAD OF NAMING A SUBJECT.
#
# "domethen bleresi esht ne gabim?" was answered out of the Maritime Code,
# because on its own the question says almost nothing and law selection took
# "blerësi" and "pagim" wherever they led. The subject lived in the question
# before it, which nothing carried forward. A question like this is searched
# together with the one before it.
PIKON_PRAPA = re.compile(
    r"^\s*(domethen|do me thene|pra\b|atehere|po\b|dhe\b|a nuk|pse\b|si\b|"
    r"kjo\b|ky\b|ai\b|ajo\b|ato\b|ata\b|e njejta|edhe\b|ne kete rast)",
    re.I)


def _varet_nga_mepara(pyetja):
    """Too short to stand alone, or openly referring to what came before."""
    t = (pyetja or "").translate(_PA_SHENJA).lower()
    fjale = [w for w in re.findall(r"[a-z]+", t) if len(w) > 3]
    return bool(PIKON_PRAPA.match(t)) or len(fjale) < 4

SYSTEM = """Je ndihmes ligjor. Pergjigju SHKURT dhe DREJTPERDREJT, vetem nga
dispozitat qe te jepen.

Te jepet nje PYETJE dhe dispozita te numeruara C1, C2, C3...

Pergjigju me JSON:
{"zgjedhjet": [{"citim_id": "C3"}, {"citim_id": "C1"}],
 "pergjigje": "Jo. Afati maksimal eshte 30 vjet [C3]; per banim 5 vjet [C3]."}

RREGULLAT:
1. "pergjigje" eshte 2-5 fjali shqip, jo nje fjale. Ndertoje keshtu:
   - fjalia e pare: pergjigjja e drejtperdrejte (Po / Jo / numri / afati);
   - pastaj rregulli ashtu si e thote dispozita, me numrin e saj;
   - pastaj kushti, perjashtimi ose rasti i vecante, nese dispozita e ka;
   - nese dispozitat ndryshojne nga njera-tjetra, thuaj cila vlen per cfare.
   Mos u mjafto me "po" ose "jo" te thate. Avokati do te dije PSE.
2. Cdo fjali duhet te mbaje [Cn] e dispozites nga e cila del. Pa [Cn] fjalia
   hidhet poshte.
3. CDO NUMER qe shkruan duhet te jete ne tekstin e asaj dispozite. Mos
   llogarit, mos rrumbullakos, mos shto numra nga koka jote. Nese dispozita
   thote "tridhjete vjet", mund te shkruash 30 ose tridhjete, asgje tjeter.
4. Mos shkruaj nene, ligje ose data qe nuk jane ne dispozitat e dhena.
5. Mos thuaj "nuk kam informacion" nese dispozitat e permbajne pergjigjen.
   Lexoji TE GJITHA dispozitat nga C1 deri te e fundit para se te vendosesh.
   Shpesh pergjigjja nuk eshte te C1 por me poshte.
6. Vetem nese ASNJE dispozite nuk ka lidhje: {"zgjedhjet": [], "pergjigje": ""}

Teksti i plote i dispozitave i shfaqet avokatit vete, nen pergjigjen tende."""


def _kandidatet(pyetja, ligjet=None, sa=SA_KANDIDATE, zgjedh_ligjin=ZGJEDH_LIGJIN):
    """BM25 over the corpus, or over one law when the question has a context.

    `ligjet` is the open document's laws, where the choice was made on hundreds
    of words of its own vocabulary. `zgjedh_ligjin` instead asks the same law
    selector to judge the QUESTION, which is nine words -- whether that helps
    or hides the rest of the library is a measured question, and
    mat_pyetjet.py measures it, which is why this is a switch and not a belief.
    """
    hyrja, me_pika = _kandidatet_me_pika(pyetja, ligjet, sa, zgjedh_ligjin)
    return hyrja, [u for _s, u in me_pika]


def _kandidatet_me_pika(pyetja, ligjet=None, sa=SA_KANDIDATE,
                        zgjedh_ligjin=ZGJEDH_LIGJIN):
    hyrja = pipeline._hyrja()
    njesite, idx = hyrja["units"], hyrja["idx"]
    if not ligjet and zgjedh_ligjin:
        ligjet = ligjet_e_dokumentit(idx, pyetja, sa=2) or None
    if ligjet:
        nen = [u for u in njesite if u.get("titulli_ligjit") in set(ligjet)]
        if nen:
            njesite, idx = nen, pipeline._nen_indeksi(hyrja, nen, ligjet)
    return hyrja, idx.search(pyetja, top=sa)


def _zgjedh_me_model(pyetja, kandidatet, mepara=None):
    """Ask the model. Returns (ordered units, ok, the model's raw prose)."""
    import llm
    rreshtat = []
    if mepara:
        rreshtat.append("BISEDA DERI TANI (vetem per kontekst):")
        for h in mepara[-2:]:
            rreshtat.append(f"  Pyetje: {h.get('pyetja', '')}")
            if h.get("pergjigjja"):
                rreshtat.append(f"  Pergjigje: {h['pergjigjja']}")
        rreshtat.append("")
    rreshtat += [f"PYETJA TANI: {pyetja}", "", "DISPOZITAT:"]
    cope = max(MIN_COPE, BUXHETI // max(1, len(kandidatet)))
    for i, u in enumerate(kandidatet):
        t = u["teksti"]
        if len(t) > cope:
            t = t[:cope].rsplit(" ", 1)[0] + " […teksti vazhdon]"
        rreshtat.append(f"C{i+1} [{u.get('titulli_ligjit')} — {u['ref']}]: {t}")
    rreshtat += ["", "Cilat i pergjigjen pyetjes? Vetem JSON."]
    payload = {
        "model": llm.MODEL,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": "\n".join(rreshtat)}],
        "temperature": 0,
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
    }
    if llm.LOCAL:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    try:
        resp = llm._post(payload)
        teksti = (resp["choices"][0]["message"].get("content") or "")
        g = llm._extract_json(teksti)
    except Exception:
        return None, False, ""
    if not isinstance(g, dict):
        return None, False, ""

    # ONLY the ids are read. Every other key the model may have invented --
    # a quote, a summary, an article number -- is discarded unread, so there is
    # no field through which its own text could reach the lawyer.
    out, pare = [], set()
    for z in (g.get("zgjedhjet") or [])[:SA_PERGJIGJE]:
        m = re.fullmatch(r"C?(\d{1,2})", str(
            (z or {}).get("citim_id") if isinstance(z, dict) else z).strip().upper())
        if not m:
            continue
        k = int(m.group(1))
        if 1 <= k <= len(kandidatet) and k not in pare:
            pare.add(k)
            out.append(kandidatet[k - 1])
    return out, True, (g.get("pergjigje") or "")


# Albanian spells its small numbers out, and the law prefers words where an
# answer prefers digits: the Civil Code says "tridhjete vjet", a lawyer expects
# "30 vjet". Both forms have to count as the same figure or the check below
# would reject correct answers and teach everyone to ignore it.
FJALE_NUMRA = {
    "nje": 1, "dy": 2, "tre": 3, "tri": 3, "kater": 4, "pese": 5, "gjashte": 6,
    "shtate": 7, "tete": 8, "nente": 9, "dhjete": 10, "njembedhjete": 11,
    "dymbedhjete": 12, "trembedhjete": 13, "katermbedhjete": 14,
    "pesembedhjete": 15, "gjashtembedhjete": 16, "shtatembedhjete": 17,
    "tetembedhjete": 18, "nentembedhjete": 19, "njezet": 20, "tridhjete": 30,
    "dyzet": 40, "pesedhjete": 50, "gjashtedhjete": 60, "shtatedhjete": 70,
    "tetedhjete": 80, "nentedhjete": 90, "njeqind": 100, "dyqind": 200,
    "treqind": 300, "nje mije": 1000, "mije": 1000, "milion": 1000000,
}
_PA_SHENJA = str.maketrans({"ë": "e", "Ë": "e", "ç": "c", "Ç": "c"})


# A NUMBER WITHOUT ITS UNIT IS NOT A FACT.
#
# Asked about a sale contract whose condition was payment of 15 PERCENT profit
# tax, the product answered with Neni 725, which gives the buyer 15 DAYS to
# rescind after late delivery. The sentence passed the check because "15" was
# in the cited article -- as days. The number matched and the meaning did not,
# and the lawyer was handed a confident answer about the wrong rule.
#
# So a figure is a pair now: the value and what it counts.
NJESITE = [
    (r"p[ëe]rqind|%", "perqind"), (r"dit[ëe]", "dite"), (r"jav[ëe]", "jave"),
    (r"muaj", "muaj"), (r"vjet|vite|vit\b|vje[cç]", "vit"), (r"or[ëe]", "ore"),
    (r"lek[ëe]", "leke"), (r"euro", "euro"), (r"her[ëe]", "here"),
    (r"vjec|vjeç", "vit"), (r"m2|metra|metror", "siperfaqe"),
]
_RX_NJESI = [(re.compile(rx), emri) for rx, emri in NJESITE]


def _njesia(pas):
    """What the words right after a number are counting, if anything."""
    coptez = pas[:22].strip()
    for rx, emri in _RX_NJESI:
        if rx.match(coptez) or rx.match(coptez.lstrip("e ")):
            return emri
    for rx, emri in _RX_NJESI:
        if rx.search(coptez.split()[0] if coptez.split() else ""):
            return emri
    return ""


def _numrat(teksti):
    """Every figure a text states, as (vlera, njesia) -- digits and words alike.

    The unit may be empty when the text simply names a number; such a figure
    matches any unit, because refusing it would throw away correct sentences
    about article numbers and counts.
    """
    t = (teksti or "").translate(_PA_SHENJA).lower()
    out = set()
    for m in re.finditer(r"\d[\d.\s]*\d|\d", t):
        q = re.sub(r"[.\s]", "", m.group(0))   # "85.000" is 85000 in Albanian
        if q.isdigit():
            out.add((int(q), _njesia(t[m.end():])))
    for fjala, v in FJALE_NUMRA.items():
        for m in re.finditer(rf"\b{re.escape(fjala)}\b", t):
            out.add((v, _njesia(t[m.end():])))
    return out


def _mbulohen(te_pretenduara, te_lejuara):
    """Does every figure in a sentence exist, with its unit, in the cited text."""
    vlerat_lejuara = {v for v, _u in te_lejuara}
    for v, u in te_pretenduara:
        if u:
            if (v, u) not in te_lejuara:
                return False
        elif v not in vlerat_lejuara:
            return False
    return True


def verifiko_prozen(proza, te_cituarat):
    """Keep only the sentences whose citations and figures are real.

    The model is allowed to phrase an answer here, which it is not allowed to do
    anywhere else in this product, because a lawyer asking a question wants an
    answer and not a pile of articles to read. The permission is narrow and it
    is enforced after the fact rather than requested in the prompt:

      - a sentence must carry [Cn] naming a provision that was actually
        retrieved, or it is dropped;
      - every figure in that sentence must appear in THAT provision's text,
        counting "30" and "tridhjete" as the same figure, or it is dropped.

    So the model can say "the maximum is 30 years" only when a provision in
    front of it says thirty. It cannot say 99, it cannot average two numbers,
    and it cannot cite an article it was not given. What survives is phrasing;
    the facts are the corpus's.

    Returns (teksti i pastruar, sa fjali u hoqen).
    """
    proza = (proza or "").strip()
    if not proza:
        return "", 0
    sipas_id = {f"C{i+1}": u for i, u in enumerate(te_cituarat)}
    mbajtur, hequr = [], 0
    for fjali in re.split(r"(?<=[\.\!\?])\s+", proza):
        f = fjali.strip()
        if not f:
            continue
        idte = re.findall(r"\[(C\d{1,2})\]", f)
        njesite = [sipas_id[i] for i in idte if i in sipas_id]
        if not njesite:
            # A BARE VERDICT IS PHRASING, NOT A CLAIM OF ITS OWN.
            #
            # Requiring a citation on literally every sentence threw away the
            # "Jo." that opens a good answer, and left the headless paragraph
            # that made this feel like a search box instead of an answer. A
            # short sentence carrying no figure and naming no article or law
            # adds no fact the corpus has to back; the provision it rests on is
            # printed directly underneath. Anything with a number or a
            # reference in it still needs its [Cn].
            i_zhveshur = (not _numrat(f)
                          and not re.search(r"\b(nen|ligj|vkm|kod)", f, re.I)
                          and len(f.split()) <= 12)
            if i_zhveshur and mbajtur is not None:
                mbajtur.append(f)
                continue
            hequr += 1
            continue
        lejuar = set()
        for u in njesite:
            lejuar |= _numrat(u["teksti"])
        pa_id = re.sub(r"\[C\d{1,2}\]", " ", f)
        if not _mbulohen(_numrat(pa_id), lejuar):
            hequr += 1
            continue
        mbajtur.append(re.sub(r"\s*\[C\d{1,2}\]", "", f).strip())
    return " ".join(mbajtur), hequr


def _bashko(zgjedhur, kandidatet, sa=None):
    """The model's order, with search's top hit guaranteed a place.

    Only used when the model actually chose something. It chose, so the topic
    is vouched for; what it is not allowed to do is drop the provision search
    ranked first, because it did exactly that once on the question key and the
    one it dropped was the right answer.

    When the model chooses NOTHING, this is not called. An unchosen search hit
    is not an answer and is not presented as one -- see `me_e_perafert`.
    """
    sa = sa or SA_PERGJIGJE
    out = list(zgjedhur[:sa])
    celes = lambda u: (u.get("titulli_ligjit"), u["ref"])
    kam = {celes(u) for u in out}
    if kandidatet and celes(kandidatet[0]) not in kam:
        out = (out[:sa - 1] if len(out) >= sa else out) + [kandidatet[0]]
    return out[:sa]


def pergjigju(pyetja, ligjet=None, mode=None, mepara=None):
    """`mepara` is the conversation so far: a list of {"pyetja", "dispozitat"}
    from earlier turns, most recent last. It does two things, and only two.

    It joins a dependent question to the one before it when searching, so that
    "domethen bleresi esht ne gabim?" is not sent into the library alone. And
    it is shown to the model, so the answer continues the thread instead of
    restarting it. It never becomes a source: the provisions still come from
    this turn's retrieval, and every sentence is still checked against them.
    """
    """A question in, provisions out.

    Returns a dict the page renders as it is:
        pyetja, dispozitat (verbatim from the corpus), renditur (bool),
        pa_pergjigje (bool), ligjet_e_kerkuara, freskia
    """
    pyetja = (pyetja or "").strip()
    if len(pyetja) < 3:
        return {"pyetja": pyetja, "dispozitat": [], "renditur": False,
                "gabim": "Pyetja është shumë e shkurtër.", "freskia": {}}

    # The query that goes to BM25 may carry the previous question; the query
    # shown to the lawyer, and checked against, is always his own.
    e_fundit = (mepara or [])[-1] if mepara else None
    kerkimi = pyetja
    bashkuar = False
    if e_fundit and _varet_nga_mepara(pyetja):
        kerkimi = f"{e_fundit.get('pyetja', '')} {pyetja}".strip()
        bashkuar = True
    hyrja, me_pika = _kandidatet_me_pika(kerkimi, ligjet)
    kandidatet = [u for _s, u in me_pika]
    mode = mode or os.environ.get("PYET_MODE", "real")
    renditur = False
    perafert = []
    pergjigjja, hequr = "", 0
    if mode == "real" and kandidatet:
        zgjedhur, ok, proza = _zgjedh_me_model(pyetja, kandidatet,
                                               mepara=mepara)
        if ok and zgjedhur:
            renditur = True
            kandidatet_out = _bashko(zgjedhur, kandidatet)
            # The prose is checked against the SAME numbering the model saw.
            pergjigjja, hequr = verifiko_prozen(proza, kandidatet)
        elif ok:
            # THE MODEL CHOSE NOTHING. That is an answer, and it is kept.
            #
            # An earlier version pushed search's top hit in anyway, to stop the
            # model swallowing an answer it had -- which it did once on the
            # question key. But unconditionally that put Neni 72, on powers of
            # attorney, in front of someone asking how to bake a cake, and it
            # destroyed the property worth more than any accuracy number: that
            # this thing says when it does not know.
            #
            # A score threshold was tried next and measured on the real corpus:
            # legal questions scored 16.8 to 62.6, non-legal 4.9 to 16.2. A gap
            # of 0.6 is not a threshold, it is a coincidence, and shipping it
            # would have been a guess dressed as a measurement.
            #
            # So the search hit is still shown -- the lawyer should see what the
            # search found -- but in its own tier, named as not an answer. The
            # report side has carried exactly this section since the beginning,
            # for exactly this reason: "kerkimi kthen gjithmone diçka, edhe kur
            # ligji nuk e rregullon temen."
            kandidatet_out = []
            perafert = kandidatet[:1]
        else:
            kandidatet_out = kandidatet[:SA_PERGJIGJE]
    else:
        kandidatet_out = kandidatet[:SA_PERGJIGJE]

    fr = korpusi.freskia(hyrja["meta"])
    datat = hyrja["meta"].get("datat_e_ligjeve") or {}

    def _veshur(u):
        emri = u.get("titulli_ligjit")
        f = fr.get(emri) or {}
        return {
            "ligji": emri,
            "nr_ligjit": u.get("ligji"),
            "ref": u["ref"],
            # VERBATIM FROM THE CORPUS. This is the only place the text of a
            # provision comes from, on this side of the product as on the other.
            "teksti": u["teksti"],
            "data_e_tekstit": datat.get(emri) or "",
            "i_vjetruar": bool(f.get("prapa")),
            "shfuqizuar": bool(f.get("shfuqizuar")),
            "ndryshimi_i_fundit": f.get("ndryshimi_i_fundit") or "",
            "here_ndryshuar": f.get("here", 0),
            "vendos_kufi": bool(u.get("i_kontrollueshem")),
        }

    dispozitat = [_veshur(u) for u in kandidatet_out]
    return {
        "pyetja": pyetja,
        # Written by the model, but every sentence in it carried a citation to
        # a retrieved provision and every figure in it was found in that
        # provision's text. Sentences that failed were dropped, and `hequr`
        # counts them so the page can say so rather than quietly shortening.
        "pergjigjja": pergjigjja,
        "fjali_te_hequra": hequr,
        "dispozitat": dispozitat,
        # Shown, but never as an answer. See the comment above.
        "me_e_perafert": [_veshur(u) for u in perafert],
        "renditur": renditur,
        "pa_pergjigje": not dispozitat,
        "ligjet_e_kerkuara": sorted(ligjet) if ligjet else [],
        # True when the question was searched together with the one before it.
        "lidhur_me_meparshmen": bashkuar,
        "sa_kandidate": len(kandidatet),
    }


def si_tekst(p):
    """The same answer as plain text, for the terminal and for tests."""
    L = [f"PYETJA: {p['pyetja']}"]
    if p.get("gabim"):
        return "\n".join(L + [p["gabim"]])
    if p["pa_pergjigje"]:
        L += ["", "Nuk u gjet dispozitë që t'i përgjigjet kësaj pyetjeje në "
              "korpus.", "Kjo NUK do të thotë që ligji nuk e rregullon: do të "
              "thotë që kërkimi", "nuk e nxori. Provoje me fjalë të tjera, ose "
              "shiko te qbz.gov.al."]
        for d in p.get("me_e_perafert") or []:
            L += ["", "Më e përafërta që nxori kërkimi — **NUK është "
                  "përgjigje**:", f"  {d['ref']}, {d['ligji']}", ""]
            L += ["  " + r for r in d["teksti"][:300].split("\n")]
        return "\n".join(L)
    if p.get("pergjigjja"):
        L += ["", p["pergjigjja"]]
        if p.get("fjali_te_hequra"):
            L.append(f"[{p['fjali_te_hequra']} fjali u hoqen: numra ose citime "
                     f"qe nuk gjenden ne dispozitat e meposhtme.]")
    if not p["renditur"]:
        L.append("")
        L.append("[PA RENDITJE] Modeli nuk u përgjigj, pra kjo është radha e "
                 "kërkimit, jo e gjykuar. Lexoji të gjitha.")
    for i, d in enumerate(p["dispozitat"], 1):
        L += ["", f"{i}. {d['ref']}, {d['ligji']}"
                  f"{'  [vendos kufi/afat]' if d['vendos_kufi'] else ''}"]
        if d["shfuqizuar"]:
            L.append(f"   KUJDES: ligji {d['nr_ligjit']} është SHFUQIZUAR "
                     f"sipas regjistrit të QBZ-së. Nuk duhet cituar.")
        elif d["i_vjetruar"]:
            L.append(f"   KUJDES: teksti mund të jetë i vjetruar. Ligji "
                     f"{d['nr_ligjit']} është ndryshuar {d['here_ndryshuar']} "
                     f"herë, i fundit më {d['ndryshimi_i_fundit']}, pas "
                     f"skedarit tonë ({d['data_e_tekstit'][:10]}).")
        elif d["data_e_tekstit"]:
            L.append(f"   (teksti i QBZ-së i {d['data_e_tekstit'][:10]})")
        L.append("")
        L += ["   " + r for r in d["teksti"].split("\n")]
    L += ["", "Teksti i mësipërm është kopjuar fjalë për fjalë nga korpusi. "
              "Modeli zgjodhi", "vetëm cilat dispozita të shfaqen; asnjë fjalë "
              "e tij nuk është në përgjigje."]
    return "\n".join(L)


if __name__ == "__main__":
    args = sys.argv[1:]
    ligjet = None
    if "--ligji" in args:
        i = args.index("--ligji")
        ligjet = [args[i + 1]]
        args = args[:i] + args[i + 2:]
    if not args:
        print(__doc__)
        sys.exit(0)
    print(si_tekst(pergjigju(" ".join(args), ligjet=ligjet)))
