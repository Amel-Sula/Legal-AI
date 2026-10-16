#!/usr/bin/env python3
"""Does a plain question reach the article that answers it.

    python3 mat_pyetjet.py            # retrieval only, no model, fast
    python3 mat_pyetjet.py --model    # also measure what the model ranks first

mat_kerkimin.py measures the report side: a contract clause against the law.
This measures the chat side, which is a different problem and failed differently
the first time it was tried on a real question. Asked "kur mund te pushohet nga
puna punemarresi", the first provision returned was Neni 587 of the Code of
Civil Procedure -- wage garnishment, which contains the words "pushohet nga
puna" and nothing else to do with the question. A lawyer reading that gets a
confidently presented irrelevance at the top of the answer.

TWO NUMBERS, BECAUSE THEY HAVE DIFFERENT FIXES.

  recall@K   is a correct article anywhere in the candidates. If it is not,
             the model cannot possibly answer: the fix is retrieval.
  top-1      is a correct article FIRST. If recall is fine and top-1 is not,
             the fix is the ranking step.

THREE VARIANTS, measured rather than argued:

  gjithcka         BM25 over all 243 laws (what ships today)
  zgjedhje ligji   the law selector judges the question first, then search
                   runs inside the law it picked
  gjithcka K=30    no selection, three times the candidates

The key is pyetje_kyc.json, and it was built by searching the corpus text, not
from memory. Read its `si_u_ndertua` field before trusting a percentage here.
"""
import json
import os
import sys
from pathlib import Path

import pyet

KYC = "pyetje_kyc.json"


def _rendi(kandidatet, pranohen):
    """1-based rank of the first acceptable provision, or 0 if absent."""
    pranuar = {(l, r) for l, r in pranohen}
    for i, u in enumerate(kandidatet, 1):
        if (u.get("titulli_ligjit"), u["ref"]) in pranuar:
            return i
    return 0


VARIANTET = [
    ("gjithcka",        dict(sa=10, zgjedh_ligjin=False)),
    ("zgjedhje ligji",  dict(sa=10, zgjedh_ligjin=True)),
    ("gjithcka K=30",   dict(sa=30, zgjedh_ligjin=False)),
    # The combination was missing from the first three, and it is the one the
    # remaining miss needs: "sa kohe me pare duhet njoftuar" stayed MUNGON with
    # selection at K=10 and was only ever tried at K=30 WITHOUT selection. A
    # variant grid with a hole in it is how a fix goes unnoticed.
    ("zgjedhje K=30",   dict(sa=30, zgjedh_ligjin=True)),
]


def main(me_model=False):
    p = Path(KYC)
    if not p.exists():
        print(f"{KYC} nuk u gjet.")
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    pyetjet = d["pyetjet"]
    print(f"{len(pyetjet)} pyetje, qeles i nxjerre nga teksti i korpusit.\n")

    rendet = {}
    for emri, kw in VARIANTET:
        rendet[emri] = []
        for q in pyetjet:
            _h, kand = pyet._kandidatet(q["pyetja"], **kw)
            rendet[emri].append(_rendi(kand, q["pranohen"]))

    kryet = "".join(f"{e:>16}" for e, _ in VARIANTET)
    print(f"{'pyetja':<52}{kryet}")
    for i, q in enumerate(pyetjet):
        rr = "".join(
            f"{('#' + str(rendet[e][i])) if rendet[e][i] else 'MUNGON':>16}"
            for e, _ in VARIANTET)
        print(f"{q['pyetja'][:50]:<52}{rr}")

    print()
    print(f"{'':<52}" + "".join(f"{e:>16}" for e, _ in VARIANTET))
    n = len(pyetjet)
    for etiketa, prove in [("recall@10", lambda r: 0 < r <= 10),
                           ("recall (gjithe listen)", lambda r: r > 0),
                           ("ne radhen e pare", lambda r: r == 1),
                           ("ne tri te paret", lambda r: 0 < r <= 3)]:
        rr = "".join(f"{sum(1 for r in rendet[e] if prove(r))}/{n:<13}"
                     for e, _ in VARIANTET)
        print(f"{etiketa:<52}{rr}")

    _verdikti(rendet, n)
    if me_model:
        _me_model(pyetjet)


def _verdikti(rendet, n):
    baza = rendet["gjithcka"]
    print()
    for emri, _kw in VARIANTET[1:]:
        r = rendet[emri]
        fituan = [i for i in range(n) if r[i] and (not baza[i] or r[i] < baza[i])]
        humben = [i for i in range(n) if baza[i] and (not r[i] or r[i] > baza[i])]
        vdiqen = [i for i in range(n) if baza[i] and not r[i]]
        print(f"{emri:<18} fitoi {len(fituan)}, humbi {len(humben)}"
              + (f", NGORDHI FARE {len(vdiqen)}" if vdiqen else ""))
    if any(not x for x in baza):
        print("\nKUJDES: ku shkruan MUNGON, nen-i i duhur nuk ishte fare ne\n"
              "kandidatet, pra modeli nuk kishte si ta zgjidhte. Atje rregullimi\n"
              "eshte kerkimi, nuk renditja.")


def _me_model(pyetjet):
    """What the model puts first, next to what retrieval had already put first.

    Both columns, because the interesting failure is not the model being wrong
    where search was wrong -- it is the model taking a correct provision off
    the top. That happened on the first real run: for the minimum-wage question
    BM25 had Neni 111/1 at rank 1 and the model replaced it with Neni 123. A
    reranker that does that is not earning its place, and only this comparison
    shows it.
    """
    print(f"\nPYET_ZGJEDH_LIGJIN={'1' if pyet.ZGJEDH_LIGJIN else '0'}  "
          f"(ashtu si do punoje ne produkt)")
    ok, mesazhi = _modeli_punon()
    print(f"Modeli: {mesazhi}")
    if not ok:
        return
    print(f"\n{'pyetja':<46}{'kerkimi':<9}{'radha 1 e modelit':<32} par  liste")
    sakte = kerkimi_sakte = prishur = ndrequr = ne_pergjigje = 0
    for q in pyetjet:
        _h, kand = pyet._kandidatet(q["pyetja"])
        r = _rendi(kand, q["pranohen"])
        kerkimi_mire = (r == 1)
        kerkimi_sakte += bool(kerkimi_mire)
        p = pyet.pergjigju(q["pyetja"], mode="real")
        if not p["dispozitat"]:
            print(f"{q['pyetja'][:44]:<46}{('#' + str(r)) if r else 'MUNGON':<9}"
                  f"{'(pa pergjigje)':<32} -")
            continue
        d = p["dispozitat"][0]
        pranuar = [list(x) for x in q["pranohen"]]
        mire = [d["ligji"], d["ref"]] in pranuar
        # WHAT THE LAWYER ACTUALLY SEES. The page shows up to four provisions,
        # verbatim, so a correct article at position two is a served lawyer.
        # Top-1 is the stricter number and both are printed, because reporting
        # only the flattering one is how a product gets sold on a number it
        # does not have.
        ne_liste = any([x["ligji"], x["ref"]] in pranuar for x in p["dispozitat"])
        sakte += bool(mire)
        ne_pergjigje += bool(ne_liste)
        prishur += bool(kerkimi_mire and not ne_liste)
        ndrequr += bool(mire and not kerkimi_mire)
        shenim = "" if p["renditur"] else "  [pa renditje]"
        print(f"{q['pyetja'][:44]:<46}{('#' + str(r)) if r else 'MUNGON':<9}"
              f"{(d['ref'] + ', ' + (d['ligji'] or ''))[:30]:<32}"
              f" {'po' if mire else 'JO':<4}"
              f"{'po' if ne_liste else 'JO'}{shenim}")
    n = len(pyetjet)
    print(f"\nKerkimi e kishte te parin te duhurin : {kerkimi_sakte}/{n}")
    print(f"Modeli e vuri te parin te duhurin    : {sakte}/{n}")
    print(f"Ne listen qe lexon avokati (4 nene)  : {ne_pergjigje}/{n}   "
          f"<- numri i produktit")
    print(f"Modeli ndrequr {ndrequr}, prishur {prishur}.")
    if prishur:
        print(f"\nKUJDES: ne {prishur} pyetje kerkimi e kishte sakte dhe modeli e\n"
              f"zhvendosi. Nese kjo mbahet ne matje te tjera, renditja me model\n"
              f"nuk e meriton vendin: hiqe dhe lere radhen e kerkimit.")


def _modeli_punon():
    import mat_paralelizmin
    return mat_paralelizmin.kontrollo_modelin()


if __name__ == "__main__":
    main(me_model="--model" in sys.argv)
