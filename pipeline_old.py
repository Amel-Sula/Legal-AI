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
import json, os, re, sys
from pathlib import Path

from split_clauses import split, defold
from retrieve import load as load_corpus, BM25
from verify import Verifier, PASSING


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
}


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
    a, b = parse_qty(r.get("vlera_kontrates")), parse_qty(r.get("vlera_ligjore"))
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
    L.append(f"Bazuar në Kodin e Punës (Ligji {meta['ligji']}), "
             f"i përditësuar deri më {meta['i_vlefshem_deri']}.")
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
            L.append(f"**Bie ndesh me Nenin {r['verifikimi'].get('neni_zgjidhur', r['neni_ligjit'])} "
                     f"të Kodit të Punës** ({r['tema']})")
            L.append("")
            L.append(tpl.format(**r))
            L.append("")
            L.append(f"Teksti i ligjit: *\"{r['citim']}\"*")
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
    return findings


def run(contract_path, top_k=8, mode="free"):
    """mode='free'  : stub writes the quote itself (what we tested first)
       mode='by_id' : stub picks from retrieved candidates (the fix)
       mode='real'  : a REAL model picks from retrieved candidates"""
    text = Path(contract_path).read_text(encoding="utf-8")
    clauses = split(text)

    meta, units = load_corpus()
    idx = BM25(units)
    V = Verifier()

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

    kept_all, dropped_all = [], []
    for (c, sp, cands), raw in zip(jobs, answers):
        findings = raw if mode == "free" else resolve_by_id(raw, cands)
        for f in findings:
            f["klauzola"] = c["nr"]
            if sp.get("nenshtese"):
                f["nenshtese"] = sp["nenshtese"]
        for f in findings:
            if f.get("ka_konflikt"):
                f["drejtimi"] = V.drejtimi(f.get("neni_ligjit"))
        kept, dropped = V.filter_findings(findings)
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
