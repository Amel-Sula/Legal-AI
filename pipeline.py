#!/usr/bin/env python3
"""
The whole chain, end to end:

    contract -> clauses -> retrieval -> MODEL -> verification -> report

Everything except MODEL is finished and runs on a laptop. MODEL is stubbed
here with a recorded answer so the chain can be tested, scored and demoed
before any GPU is rented. Swapping the stub for a real call is one function.

The report text is written by TEMPLATES, not by the model. The model only
ever emits numbers, booleans and verbatim quotes. That is why a model with
shaky Albanian grammar can still power a product sold to lawyers.
"""
import copy, json, os, re, sys, threading
from pathlib import Path

from split_clauses import split, defold
from retrieve import BM25
from verify import Verifier, PASSING
import korpusi


# ----------------------------------------------------------------------
# MODEL (stubbed)
# ----------------------------------------------------------------------
def model_stub(clause, candidates):
    """Stands in for the 8B model. Returns what a real model returns: a
    verdict, an article reference and a verbatim quote. Nothing else.

    Deliberately imperfect, to exercise the verifier in the real flow:
      - clause 6 gets a FALSE POSITIVE (the written-agreement exception)
      - clause 9 gets a FABRICATED quote
      - clause 2 gets a MISATTRIBUTED but real quote
    """
    n = clause["nr"]
    if n == 4:
        return [
            {"ka_konflikt": True, "neni_ligjit": "150",
             "citim": "Palët parashikojnë me shkrim një periudhë prove jo më shumë se tre muaj.",
             "vlera_kontrates": "6 muaj", "vlera_ligjore": "3 muaj",
             "lloji": "tejkalim_kufiri", "tema": "periudha e provës"},
            {"ka_konflikt": True, "neni_ligjit": "142/3",
             "citim": "Gjatë kohës së marrjes në provë, secila nga palët mund të zgjidhë kontratën duke i njoftuar vendimin e saj palës tjetër të paktën 5 ditë përpara.",
             "vlera_kontrates": "3 ditë", "vlera_ligjore": "5 ditë",
             "lloji": "nen_kufiri", "tema": "njoftimi gjatë provës"},
        ]
    if n == 5:
        return [
            {"ka_konflikt": True, "neni_ligjit": "83",
             "citim": "Kohëzgjatja normale e javës së punës është jo më shumë se 40 orë.",
             "vlera_kontrates": "50 orë/javë", "vlera_ligjore": "40 orë/javë",
             "lloji": "tejkalim_kufiri", "tema": "koha javore e punës"},
            {"ka_konflikt": True, "neni_ligjit": "90",
             "citim": "Punëdhënësi mund të kërkojë kryerjen e orëve shtesë të punës, por jo më shumë se 200 orë në vit.",
             "vlera_kontrates": "pa kufi", "vlera_ligjore": "200 orë/vit",
             "lloji": "mungese_kufiri", "tema": "orët shtesë"},
        ]
    if n == 6:
        # FALSE POSITIVE: Neni 116/1 expressly allows a different written
        # arrangement, which this clause is. Quote is real, so the verifier
        # will NOT catch this. Only the answer key catches it.
        return [
            {"ka_konflikt": True, "neni_ligjit": "116",
             "citim": "Punëdhënësi i paguan rregullisht pagën punëmarrësit çdo dy javë",
             "vlera_kontrates": "data 10 e muajit pasardhës", "vlera_ligjore": "fundi i muajit",
             "lloji": "tejkalim_kufiri", "tema": "afati i pagesës"},
        ]
    if n == 7:
        return [
            {"ka_konflikt": True, "neni_ligjit": "92/2",
             "citim": "Kohëzgjatja e pushimeve vjetore është jo më pak se 22 ditë pune gjatë vitit të punës në vazhdim.",
             "vlera_kontrates": "10 ditë", "vlera_ligjore": "22 ditë",
             "lloji": "nen_kufiri", "tema": "pushimet vjetore"},
        ]
    if n == 8:
        return [
            {"ka_konflikt": True, "neni_ligjit": "143",
             "citim": "palët duhet të respektojnë një afat njoftimi prej dy javësh, kur marrëdhënia e punësimit ka zgjatur deri në gjashtë muaj",
             "vlera_kontrates": "1 javë, pa dallim", "vlera_ligjore": "2 javë deri 3 muaj sipas vjetërsisë",
             "lloji": "nen_kufiri", "tema": "afati i njoftimit"},
        ]
    if n == 9:
        # FABRICATED quote: the limit is real (Neni 29/1, one year) but the
        # model invented the wording. Verifier must block it.
        return [
            {"ka_konflikt": True, "neni_ligjit": "29",
             "citim": "Ndalimi i konkurrencës nuk mund të kalojë afatin prej dymbëdhjetë muajsh nga përfundimi i kontratës.",
             "vlera_kontrates": "3 vjet", "vlera_ligjore": "1 vit",
             "lloji": "tejkalim_kufiri", "tema": "ndalimi i konkurrencës"},
        ]
    if n == 2:
        # MISATTRIBUTED: real sentence, wrong article.
        return [
            {"ka_konflikt": True, "neni_ligjit": "21",
             "citim": "Kohëzgjatja normale e javës së punës është jo më shumë se 40 orë.",
             "vlera_kontrates": "levizje brenda qarkut", "vlera_ligjore": "-",
             "lloji": "tejkalim_kufiri", "tema": "vendi i punës"},
        ]
    return [{"ka_konflikt": False}]


def model_stub_by_id(clause, candidates):
    """Same model, same legal judgement, but it picks a candidate id instead
    of typing a quote. Note clause 9: the model still wants to cite the
    non-compete limit, and now it CAN'T get the wording wrong.

    Clause 6 is unchanged: the false positive survives, because picking the
    right article is not the same as reasoning correctly about it.
    """
    n = clause["nr"]
    want = {
        4: [("periudha e provës", "6 muaj", "3 muaj", "tejkalim_kufiri",
             ("prove", "tre muaj")),
            ("njoftimi gjatë provës", "3 ditë", "5 ditë", "nen_kufiri",
             ("prove", "5 dite"))],
        5: [("koha javore e punës", "50 orë/javë", "40 orë/javë", "tejkalim_kufiri",
             ("jave", "40 ore")),
            ("orët shtesë", "pa kufi", "200 orë/vit", "mungese_kufiri",
             ("shtese", "200 ore"))],
        6: [("afati i pagesës", "data 10 e muajit pasardhës", "fundi i muajit",
             "tejkalim_kufiri", ("paguan rregullisht", "dy jave"))],
        7: [("pushimet vjetore", "10 ditë", "22 ditë", "nen_kufiri",
             ("pushimeve vjetore", "22 dite"))],
        8: [("afati i njoftimit", "1 javë, pa dallim",
             "2 javë deri 3 muaj sipas vjetërsisë", "nen_kufiri",
             ("afat njoftimi", "dy javesh"))],
        9: [("ndalimi i konkurrencës", "3 vjet", "1 vit", "tejkalim_kufiri",
             ("ndalimit", "nje vit"))],
        2: [],
    }.get(n, [])

    from verify import norm
    out = []
    for tema, vk, vl, lloji, needles in want:
        pick = None
        for i, u in enumerate(candidates):
            h = norm(u["teksti"], True)
            if all(nd in h for nd in needles):
                pick = f"C{i+1}"
                break
        if pick:
            out.append({"ka_konflikt": True, "citim_id": pick, "tema": tema,
                        "vlera_kontrates": vk, "vlera_ligjore": vl,
                        "lloji": lloji})
    return out or [{"ka_konflikt": False}]


# ----------------------------------------------------------------------
# REPORT (templates, not model prose)
# ----------------------------------------------------------------------
SHABLLONE = {
    "tejkalim_kufiri": ("Klauzola parashikon {vlera_kontrates}, ndërsa ligji "
                        "lejon maksimumi {vlera_ligjore}."),
    "nen_kufiri":      ("Klauzola parashikon {vlera_kontrates}, ndërsa ligji "
                        "kërkon të paktën {vlera_ligjore}."),
    "mungese_kufiri":  ("Klauzola nuk vendos asnjë kufi ({vlera_kontrates}), "
                        "ndërsa ligji cakton {vlera_ligjore}."),
    # Used when the two values are not comparable quantities: different units,
    # or a whole sentence where a number was expected. Saying "the law allows
    # at most <a paragraph of prose>" is worse than saying nothing precise.
    "i_pakrahasueshem": ("Klauzola parashikon {vlera_kontrates}. Dispozita e "
                         "mëposhtme mund të zbatohet; krahasimi numerik nuk u "
                         "bë dot automatikisht dhe duhet parë nga juristi."),
    # No figure at all. Reached when the model names no value, or names one the
    # clause does not contain: under LLM_VLERA that resolves to "-" rather than
    # to the model's own words, and "Klauzola parashikon -." must never reach a
    # lawyer.
    "pa_vlere": ("Dispozita e mëposhtme mund të zbatohet për këtë klauzolë. Nuk "
                 "u nxorr një vlerë numerike nga klauzola, pra krahasimin duhet "
                 "ta bëjë juristi."),
}

# values that carry no number and must not be printed as if they did
PA_VLERE = {"", "-", "--", "n/a", "none", "null", "asnje", "asnjë"}


def zgjidh_shabllonin(r):
    """Pick the sentence from the LAW's own direction, not the model's label.

    verify.py already stopped trusting the model's `lloji` for the arithmetic
    gate, because the model gets the direction wrong often. The renderer was
    still trusting it, so a finding could pass the gate and then be printed as
    "the law allows at most 50 per cent" directly above a quote reading "at
    least 50 per cent". The citation was right and the sentence contradicted
    it, which is the most damaging thing this report can do.
    """
    from verify import parse_qty
    vk = str(r.get("vlera_kontrates") or "").strip()
    if vk.lower() in PA_VLERE:
        return SHABLLONE["pa_vlere"]
    a, b = parse_qty(vk), parse_qty(r.get("vlera_ligjore"))
    if not a or not b or a[1] != b[1]:
        return SHABLLONE["i_pakrahasueshem"]
    d = r.get("drejtimi")
    if d == "maksimal":
        return SHABLLONE["tejkalim_kufiri"]
    if d == "minimal":
        return SHABLLONE["nen_kufiri"]
    # The corpus has no direction for this provision. Read it off the numbers
    # instead of the model's label: whatever the finding means, "6 months"
    # against "3 months" is an excess, and the sentence must never contradict
    # the two figures printed inside it.
    return SHABLLONE["tejkalim_kufiri"] if a[0] > b[0] else SHABLLONE["nen_kufiri"]


def render(doc_name, clauses, results, dropped, meta):
    L = [f"# Raport kontrolli ligjor — {doc_name}", ""]
    # Which law the document was read against is the lawyer's first question,
    # and the first thing he must be able to disagree with. It is chosen by the
    # document's own vocabulary, so a wrong choice has to be visible, not buried.
    ligjet = meta.get("ligjet_e_zgjedhura") or ["Kodi i Punës"]
    L.append("Dokumenti u lexua kundrejt: **" + "**, **".join(ligjet) + "**.")
    L.append("")
    L.append(f"Ligji i zgjidhet dokumentit sipas fjalorit të tij. Nëse ky "
             f"dokument rregullohet nga një ligj tjetër, raporti nuk e ka "
             f"parë atë ligj. Korpusi: {meta.get('numri_njesive', '?')} "
             f"dispozita nga {len(meta.get('ligjet') or {})} ligje.")
    L.append("")

    # HOW OLD THE LAW IS, FOR EACH LAW THIS DOCUMENT WAS READ AGAINST.
    #
    # A citation that is letter-perfect from an article repealed last year is
    # worse than no citation, because the lawyer believed it. The report used
    # to print the Labour Code's date and say nothing about the other 242
    # laws. It cannot promise the text is current -- nothing here can -- so it
    # states the date it knows and leaves the judgment where it belongs.
    # Our own date is not enough. QBZ stamps most of its compilation PDFs
    # 2021-02-17 while the acts amending those same laws run through 2026, so a
    # law two republications behind still shows a respectable-looking date. The
    # register says when each law was last amended; only the comparison can
    # warn the lawyer, so a law that is behind is named as behind, loudly and
    # before any finding drawn from it.
    datat = meta.get("datat_e_ligjeve") or {}
    fr = korpusi.freskia(meta)
    L.append("**Sa i freskët është ligji.** Programi nuk garanton se teksti "
             "është në fuqi. Këto janë datat që di:")
    L.append("")
    prapa = []
    for emri in ligjet:
        d = datat.get(emri)
        f = fr.get(emri) or {}
        if emri == "Kodi i Punës" and meta.get("i_vlefshem_deri"):
            L.append(f"- **{emri}**: tekst i konsoliduar, i përditësuar deri më "
                     f"{meta['i_vlefshem_deri']}.")
        elif d:
            L.append(f"- **{emri}**: nga skedari i QBZ-së, i ribotuar nga QBZ "
                     f"më {d}. Ndryshimet pas kësaj date nuk janë brenda.")
        else:
            L.append(f"- **{emri}**: **data e tekstit nuk dihet.** Skedari u "
                     f"shkarkuar pa manifest, pra nuk mbahet gjurmë se kur e "
                     f"ribotoi QBZ-ja. Verifikoje nenin te qbz.gov.al.")
        if f.get("shfuqizuar"):
            L.append(f"    - **KUJDES: sipas regjistrit të QBZ-së ky ligj "
                     f"({f['nr']}) është SHFUQIZUAR.** Asnjë nen i tij nuk "
                     f"duhet cituar. Gjithçka më poshtë nga ky ligj është e "
                     f"pavlefshme.")
            prapa.append(emri)
        elif f.get("prapa"):
            L.append(f"    - **KUJDES: teksti mund të jetë i vjetruar.** Ligji "
                     f"{f['nr']} është ndryshuar {f['here']} herë, i fundit më "
                     f"{f['ndryshimi_i_fundit']}" +
                     (", dhe për skedarin tonë nuk kemi datë për krahasim."
                      if f.get("pa_daten_tone") else
                      f", pas datës së skedarit tonë ({f['data_jone'][:10]})."))
            prapa.append(emri)
    if not fr:
        L.append("")
        L.append("    - Regjistri i akteve të QBZ-së nuk është i ngarkuar, pra "
                 "nuk dihet nëse këto ligje janë ndryshuar pas datave më lart. "
                 "Lësho `qbz_api.py metadata ligj` dhe `qbz_api.py statusi`.")
    if prapa:
        L.append("")
        L.append(f"> Nenet e cituara më poshtë nga {', '.join(prapa)} duhen "
                 f"kontrolluar te qbz.gov.al përpara se të përdoren. Verifikimi "
                 f"i programit tregon se citimi përputhet me korpusin tonë; nuk "
                 f"tregon se korpusi ynë përputhet me ligjin e sotëm.")
    L.append("")
    konflikte = [r for r in results if r.get("ka_konflikt")]
    L.append(f"**{len(konflikte)} problem(e) të gjetura** në "
             f"{len({r['klauzola'] for r in konflikte})} klauzola "
             f"nga {len(clauses)} të kontrolluara.")
    L.append("")

    for c in clauses:
        hits = [r for r in konflikte if r["klauzola"] == c["nr"]]
        if not hits:
            continue
        L.append(f"## Neni {c['nr']} i kontratës — {c['titulli']}")
        L.append(f"> {c['teksti'][:240]}")
        L.append("")
        for r in hits:
            tpl = zgjidh_shabllonin(r)
            # "Neni 150, Kodi i Punës" rather than "Nenin 150 të Kodi i Punës":
            # the law's name comes out of the corpus in the nominative and
            # Albanian declension cannot be faked with an f-string.
            L.append(f"**Bie ndesh me: Neni "
                     f"{r['verifikimi'].get('neni_zgjidhur', r['neni_ligjit'])}, "
                     f"{r.get('ligji') or 'Kodi i Punës'}** ({r['tema']})")
            L.append("")
            L.append(tpl.format(**r))
            L.append("")
            L.append(f"Teksti i ligjit: *\"{r['citim']}\"*")
            L.append("")

    # RETRIEVAL IS USEFUL EVEN WHERE CHECKING IS NOT.
    #
    # A breach can only be asserted where the law states a number: the Labour
    # Code states one in 116 of its 226 articles, the Civil Code in 76 of 1132.
    # So for a rental or a sale contract the answer will often be "no numeric
    # breach found", and a report that stops there looks broken and hides the
    # work that was actually done.
    #
    # These are the provisions retrieval put in front of the model, quoted from
    # the corpus, clause by clause. No model judgment reaches this list -- it is
    # the law the document touches, for the lawyer to read himself.
    per_lexim = [p for p in (meta.get("dispozita_per_lexim") or [])
                 if p["klauzola"] not in {r["klauzola"] for r in konflikte}]

    # A finding held back because no figure could be read out of the clause is
    # not nothing: the model did point at a provision on the same subject, and
    # the citation was verified. It must not be asserted as a breach, and it
    # must not vanish either, so it joins the reading list.
    for d in dropped:
        if d.get("verifikimi", {}).get("verdict") != "PA_VLERE_KUNDREJT_KUFIRIT":
            continue
        if d["klauzola"] in {r["klauzola"] for r in konflikte}:
            continue
        per_lexim = [p for p in per_lexim if p["klauzola"] != d["klauzola"]]
        per_lexim.append({
            "klauzola": d["klauzola"],
            "titulli": next((c["titulli"] for c in clauses
                             if c["nr"] == d["klauzola"]), ""),
            "ligji": d.get("ligji") or "Kodi i Punës",
            "neni": d.get("neni_ligjit"),
            "citim": d.get("citim") or "",
            "kufi": True,
        })
    per_lexim.sort(key=lambda p: p["klauzola"])
    if per_lexim:
        L.append("## Dispozita më e përafërt për çdo klauzolë (për lexim)")
        L.append("")
        L.append("Për secilën klauzolë pa gjetje, kjo është dispozita e radhës "
                 "së parë që kërkimi nxori. **Nuk është gjetje dhe nuk është "
                 "garanci lidhjeje**: kërkimi kthen gjithmonë diçka, edhe kur "
                 "ligji nuk e rregullon temën. Shenja ⚖ tregon se dispozita "
                 "vendos kufi, afat ose ndalim konkret — vetëm te ato mund të "
                 "ketë shkelje numerike.")
        L.append("")
        for p in per_lexim[:25]:
            shenje = "⚖ " if p.get("kufi") else ""
            L.append(f"- **Klauzola {p['klauzola']}** ({p['titulli']}) → "
                     f"{shenje}Neni {p['neni']}, {p['ligji']}: "
                     f"*\"{p['citim'][:200]}\"*")
        L.append("")

    L.append("## Pika që nuk mund të verifikohen")
    L.append("Paga minimale nuk përcaktohet në Kodin e Punës. Neni 111/1 e lë "
             "atë në vendim të Këshillit të Ministrave, i cili nuk është pjesë "
             "e këtij korpusi. Prandaj asnjë klauzolë page nuk është vlerësuar "
             "kundrejt pagës minimale.")
    L.append("")

    if dropped:
        L.append("## Shënim teknik (nuk i shfaqet klientit)")
        L.append(f"{len(dropped)} gjetje u bllokuan nga verifikimi:")
        for d in dropped:
            v = d["verifikimi"]
            L.append(f"- klauzola {d['klauzola']}, Neni {d['neni_ligjit']}: "
                     f"**{v['verdict']}** — {v['detaj'][:110]}")
        L.append("")
    return "\n".join(L)


# ----------------------------------------------------------------------
# A sub-point marker must start the clause or follow end-of-sentence
# punctuation, and the trailing space is optional because contracts are
# typed as "11.1.Punemarresi" as often as "11.1 Punemarresi". The anchoring
# is what stops a date like 08.11.2023 being read as point 11.20.
WORKERS = int(os.environ.get("OR_WORKERS", "4"))

SUBPOINT = re.compile(r"(?:^|(?<=[\.\;\:]\s))(\d{1,2})\.(\d{1,2})\.?\s*(?=[A-Za-zËÇëç“\"])")


def subpoints(clause):
    """Split a contract article into its numbered sub-points (11.1, 11.2...).

    The citable unit in a contract is the sub-point, exactly as it is in the
    law. Article 11 of the BIOCHECK contract is 1,477 characters covering
    weekly rest, holidays, holiday pay, annual leave, scheduling and leave pay.
    Searched as one block, six topics compete for eight slots and the article
    that actually gets breached (Neni 91 on holiday pay) never surfaces.
    Searched one sub-point at a time, each obligation gets its own shot.
    """
    text = clause["teksti"]
    marks, last = [], 0
    for m in SUBPOINT.finditer(text):
        if m.group(1) != str(clause["nr"]):
            continue
        n = int(m.group(2))
        if n != last + 1:          # sub-points must ascend 1,2,3...
            continue
        last = n
        marks.append((m.start(), f"{m.group(1)}.{n}"))
    if len(marks) < 2:
        return [clause]

    out = []
    for i, (pos, label) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        body = text[pos:end].strip()
        if len(body) < 25:
            continue
        out.append({**clause, "teksti": body,
                    "teksti_kerkimit": defold(body), "nenshtese": label})
    return out or [clause]


def retrieve_for_clause(idx, clause, top_k=8):
    """Retrieve per SENTENCE, then merge.

    A contract clause often carries more than one obligation. Clause 5 of the
    test contract sets a 50-hour week AND unlimited overtime; sent as one
    query the overtime wording dominates and Neni 83 (the 40-hour cap) never
    surfaces. Querying each sentence separately gives every obligation its own
    shot, and interleaving the results keeps one long sentence from taking
    every slot.
    """
    text = clause["teksti_kerkimit"]
    sents = [s.strip() for s in re.split(r"(?<=[\.\;])\s+", text) if len(s.strip()) > 25]
    if len(sents) < 2:
        return [u for _s, u in idx.search(text, top=top_k)]

    per_sentence = [idx.search(s, top=top_k) for s in sents]
    per_sentence.append(idx.search(text, top=top_k))   # whole clause too

    merged, seen = [], set()
    for rank in range(top_k):
        for lst in per_sentence:
            if rank >= len(lst):
                continue
            u = lst[rank][1]
            key = (u["neni"], u["pika"])
            if key in seen:
                continue
            seen.add(key)
            merged.append(u)
            if len(merged) >= top_k:
                return merged
    return merged


def resolve_by_id(findings, cands):
    """CITATION BY REFERENCE.

    Instead of letting the model WRITE the quote (which it can invent), the
    retrieved points are handed to it as C1..Cn and it returns an id. We then
    copy the quote out of the corpus ourselves. A fabricated quote stops being
    possible by construction rather than being caught after the fact.
    """
    table = {f"C{i+1}": u for i, u in enumerate(cands)}
    for f in findings:
        cid = f.pop("citim_id", None)
        if not cid:
            continue
        u = table.get(cid)
        if u is None:
            f["ka_konflikt"] = False
            f["_arsye_rrezimi"] = f"id i panjohur: {cid}"
            continue
        f["neni_ligjit"] = f"{u['neni']}/{u['pika']}" if u["pika"] else u["neni"]
        f["citim"] = u["teksti"]
        # Which law this provision came from. The model never names a law and
        # must never be asked to: the candidate it picked already knows, and
        # everything downstream (verification, the report heading) reads it
        # from here. Without it "Neni 5" is sixteen different provisions.
        f["ligji"] = u.get("titulli_ligjit") or "Kodi i Punës"
    return findings


_KESHI = {}
_KESHI_BRAVA = threading.Lock()


def _korpusi_i_ngarkuar(corpus=None):
    """The corpus and its index, loaded once per process instead of per request.

    web.py calls run() for every upload, and run() was re-reading all 19,475
    provisions and rebuilding the BM25 index each time -- seconds of CPU and a
    second copy of the corpus in memory per concurrent document, for data that
    changes only when shto_ligj.py is re-run. With the serialising lock removed
    so several lawyers can be served at once, that cost multiplies by the number
    of them.

    The cache key carries the file's mtime, so re-running shto_ligj.py while the
    server is up is picked up on the next request rather than serving the old
    law until someone restarts it -- a stale corpus is exactly the failure this
    product cannot have.

    `units` and the index are shared read-only: nothing downstream writes to
    them (asserted by a test). `meta` IS written to -- run() records the chosen
    laws and the failed questions in it -- so each caller gets its own copy.
    """
    hyrja = _hyrja(corpus)
    return copy.deepcopy(hyrja["meta"]), hyrja["units"], hyrja["idx"]


def _hyrja(corpus=None):
    skedaret = [Path(corpus or korpusi.SKEDARI_KP), Path(korpusi.SKEDARI_LIGJET)]
    celesi = tuple((str(p), p.stat().st_mtime_ns if p.exists() else 0)
                   for p in skedaret)
    with _KESHI_BRAVA:
        hyrja = _KESHI.get(celesi)
        if hyrja is None:
            meta, te_gjitha = korpusi.ngarko(skedari_kp=corpus)
            hyrja = {"meta": meta, "units": te_gjitha, "idx": BM25(te_gjitha),
                     "nen_idx": {}, "verifier": None}
            _KESHI.clear()            # one corpus at a time; it is large
            _KESHI[celesi] = hyrja
    return hyrja


def _nen_indeksi(hyrja, units, ligjet):
    """The BM25 index for ONE law, built once and then shared.

    Measured on this corpus, per document: 0.5s to build the chosen law's index
    and 0.3s to build the verifier, both pure Python and both derived only from
    the corpus, which never changes between requests. Every document about a
    lease contract was rebuilding the identical Civil Code index.

    This is what the concurrency measurement actually found. Throughput halved
    from two documents to four, and it did so IDENTICALLY with the model
    switched off (MAT_MODE=by_id: 17.7, 16.9, 6.8, 6.5 documents a minute), so
    the GPU was never the bottleneck -- it was this Python work, serialised by
    the interpreter lock, repeated per document.
    """
    if len(units) == len(hyrja["units"]):
        return hyrja["idx"]
    celesi = frozenset(ligjet)
    with _KESHI_BRAVA:
        idx = hyrja["nen_idx"].get(celesi)
        if idx is None:
            idx = BM25(units)
            if len(hyrja["nen_idx"]) > 24:
                hyrja["nen_idx"].clear()     # bounded; 243 laws exist
            hyrja["nen_idx"][celesi] = idx
    return idx


def _verifikuesi(hyrja):
    """One verifier for the whole process.

    Safe to share: everything it writes, it writes in its constructor; after
    that every method only reads. A test asserts that, because if it ever stops
    being true two lawyers' documents would be verified against each other's
    state, and the failure would be silent.
    """
    with _KESHI_BRAVA:
        if hyrja["verifier"] is None:
            hyrja["verifier"] = Verifier(units=hyrja["units"])
    return hyrja["verifier"]


def run(contract_path, top_k=8, mode="free", corpus=None):
    """mode='free'  : stub writes the quote itself (what we tested first)
       mode='by_id' : stub picks from retrieved candidates (the fix)
       mode='real'  : a REAL model picks from retrieved candidates

       corpus: an alternative point-level corpus file in place of
       kodi_punes_flagged.json. score.py passes this; the whole library is
       still loaded around it."""
    text = Path(contract_path).read_text(encoding="utf-8")
    clauses = split(text)

    # THE WHOLE LAW, then this document's share of it.
    #
    # Until now this loaded kodi_punes_flagged.json and nothing else, so the
    # product could only read an employment contract: a rental agreement came
    # back with no findings and no explanation, because the law that governs it
    # was never in the index.
    #
    # Retrieval still must not run across the entire library. Measured: with
    # all codes in one flat index, two known violations fell to rank 7 and 8 of
    # 8 and the next law added would have pushed them out. So the law is chosen
    # once per DOCUMENT -- every clause of one contract belongs to the same
    # body of law -- and the article search runs inside it. That is what makes
    # corpus size stop mattering.
    hyrja = _hyrja(corpus)
    meta, te_gjitha, idx_plote = (copy.deepcopy(hyrja["meta"]),
                                  hyrja["units"], hyrja["idx"])
    units, ligjet = korpusi.per_dokument(te_gjitha, text, idx=idx_plote)
    meta["ligjet_e_zgjedhura"] = ligjet
    idx = _nen_indeksi(hyrja, units, ligjet)

    # The verifier keeps the FULL corpus: a quote must be checked against the
    # law it was taken from even if law selection was wrong, and a citation
    # from outside the chosen laws must come back NO_SUCH_ARTICLE rather than
    # being silently unverifiable.
    V = _verifikuesi(hyrja)

    # build every question first: (parent clause, sub-point, candidates)
    jobs = []
    for c in clauses:
        if c["nr"] == 0:
            continue
        for sp in subpoints(c):
            jobs.append((c, sp, retrieve_for_clause(idx, sp, top_k)))

    # Ask them concurrently. Each question is independent, so waiting for 60
    # round trips one at a time was pure latency. Workers kept modest because
    # the cheaper models rate-limit, and a 429 costs more than it saves.
    if mode == "real":
        import llm
        llm.vendos_ligjet(ligjet)      # only read when LLM_LIGJI=1
        from concurrent.futures import ThreadPoolExecutor
        print(f"  {len(jobs)} pyetje, {WORKERS} paralel...", flush=True)
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            answers = list(ex.map(lambda j: llm.ask(j[1], j[2]), jobs))
    elif mode == "by_id":
        answers = [model_stub_by_id(sp, cd) for _c, sp, cd in jobs]
    else:
        answers = [model_stub(sp, cd) for _c, sp, cd in jobs]

    # A failed request returns "no conflict", which is indistinguishable from
    # the model actually finding nothing. Count them separately or a run that
    # lost half its answers to rate limiting reads as a model with poor recall.
    meta["deshtime"] = [
        {"klauzola": c["nr"], "nenshtese": sp.get("nenshtese"),
         "gabim": str(f.get("_gabim"))[:120]}
        for (c, sp, _cd), raw in zip(jobs, answers)
        for f in raw if f.get("_gabim")
    ]

    # the best-ranked provision per clause, for the report's reading list
    per_lexim, vendosur = [], set()
    for c, sp, cands in jobs:
        if c["nr"] in vendosur or not cands:
            continue
        # strictly rank 1. Digging down the list for a provision that happens
        # to state a limit would dress up rank 8 as "the relevant article".
        u = cands[0]
        vendosur.add(c["nr"])
        per_lexim.append({
            "klauzola": c["nr"], "titulli": c["titulli"],
            "ligji": u.get("titulli_ligjit") or "Kodi i Punës",
            "neni": f"{u['neni']}/{u['pika']}" if u.get("pika") else u["neni"],
            "citim": u["teksti"],
            "kufi": bool(u.get("i_kontrollueshem")),
        })
    meta["dispozita_per_lexim"] = per_lexim

    kept_all, dropped_all = [], []
    for (c, sp, cands), raw in zip(jobs, answers):
        findings = raw if mode == "free" else resolve_by_id(raw, cands)
        for f in findings:
            f["klauzola"] = c["nr"]
            if sp.get("nenshtese"):
                f["nenshtese"] = sp["nenshtese"]
        for f in findings:
            if f.get("ka_konflikt"):
                f["drejtimi"] = V.drejtimi(f.get("neni_ligjit"), f.get("ligji"))
        kept, dropped = V.filter_findings(findings, sp.get("teksti"))
        kept_all += [k for k in kept if k.get("ka_konflikt")]
        dropped_all += dropped

    return clauses, kept_all, dropped_all, meta


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "kontrata_test_01.txt"
    clauses, kept, dropped, meta = run(src)

    print(f"klauzola: {len(clauses)}   "
          f"gjetje te publikuara: {len(kept)}   "
          f"te bllokuara nga verifikimi: {len(dropped)}\n")
    for d in dropped:
        print(f"  BLOCKED  klauzola {d['klauzola']}  Neni {d['neni_ligjit']}  "
              f"{d['verifikimi']['verdict']}")
    print()

    report = render(Path(src).name, clauses, kept, dropped, meta)
    Path(Path(src).stem + ".raport.md").write_text(report, encoding="utf-8")
    print(report)
