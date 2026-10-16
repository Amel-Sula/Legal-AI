#!/usr/bin/env python3
"""Does Labour Code retrieval still work now that the corpus is ten times bigger?

    python3 mat_kerkimin.py            # Labour Code alone, then plus everything

Runs the 10 known violations from both answer keys through retrieval twice:
once against the Labour Code on its own, once with every other code added. No
model is called, so it takes seconds and isolates retrieval from everything
else.

If recall holds, the other codes can stay. If it drops, the number says by how
much, and the two-layer design (pick the law, then the article) is needed
before any more law goes in.
"""
import json, sys
from pathlib import Path

import korpusi
import retrieve
from pipeline import subpoints, retrieve_for_clause
from split_clauses import split

FIXTURAT = ("kontrata_biocheck", "kontrata_test_01")


def ndertо_indeksin(me_kodet_e_tjera):
    """The corpus the PRODUCT loads, not a second copy of it.

    This harness used to build its own index from the two json files. That was
    fine while pipeline.py loaded only the Labour Code, because the two could
    not disagree about anything that mattered. Now that the product loads the
    whole library through korpusi.ngarko(), a separate loader here would mean
    measuring something the product does not run.
    """
    if not me_kodet_e_tjera:
        meta, units = korpusi.ngarko(vetem_kodi_punes=True)
    else:
        if not Path("korpus_ligjet.json").exists():
            print("korpus_ligjet.json nuk u gjet. Lesho me pare shto_ligj.py")
            raise SystemExit(1)
        meta, units = korpusi.ngarko()
    return units, retrieve.BM25(units)


def mat(me_kodet_e_tjera, zgjidh_ligjin=False):
    units, idx = ndertо_indeksin(me_kodet_e_tjera)
    rreshtat, te_huaj = [], 0
    for fx in FIXTURAT:
        key = json.load(open(f"{fx}.key.json", encoding="utf-8"))
        clauses = split(Path(f"{fx}.txt").read_text(encoding="utf-8"))
        duhet = {k["neni_kontrates"]: {str(n).split("/")[0]
                 for sh in (k.get("shkeljet") or []) for n in sh["nenet"]}
                 for k in key["klauzolat"] if k["ka_konflikt"]}
        idx_dok = idx
        if zgjidh_ligjin:
            # The law is chosen once per DOCUMENT, not per clause: every clause
            # of an employment contract belongs to the same body of law. Same
            # call the product makes, so this measures the product.
            nen_units, _emrat = korpusi.per_dokument(
                units, Path(f"{fx}.txt").read_text(encoding="utf-8"), idx=idx)
            idx_dok = retrieve.BM25(nen_units)
        for c in clauses:
            if c["nr"] not in duhet:
                continue
            me_i_miri = None
            for sp in subpoints(c):
                for i, u in enumerate(retrieve_for_clause(idx_dok, sp, 8), 1):
                    if u.get("titulli_ligjit") != "Kodi i Punës":
                        te_huaj += 1
                    if (str(u["neni"]).split("/")[0] in duhet[c["nr"]]
                            and u.get("titulli_ligjit") == "Kodi i Punës"):
                        me_i_miri = i if me_i_miri is None else min(me_i_miri, i)
            rreshtat.append((f"{fx[9:13]}#{c['nr']}", me_i_miri))
    gjetur = sum(1 for _k, v in rreshtat if v is not None)
    return len(units), gjetur, len(rreshtat), te_huaj, rreshtat


print(f"{'indeksi':<34} {'recall':>8}   kandidate nga ligje te tjera")
rez = {}
for etiketa, me, zgj in (("vetem Kodi i Punes", False, False),
                         ("plus te gjitha kodet", True, False),
                         ("te gjitha + zgjedhje ligji", True, True)):
    n, gjetur, nga, te_huaj, rreshtat = mat(me, zgj)
    rez[etiketa] = rreshtat
    njesi_gjithsej = n
    print(f"{etiketa + f' ({n} nene)':<34} {gjetur}/{nga} = {gjetur/nga:>4.0%}   {te_huaj}")

print(f"\n{'klauzola':<12} {'vetem KP':>9} {'me gjithcka':>12} {'+ zgjedhje':>12}")
a, b, c = (rez["vetem Kodi i Punes"], rez["plus te gjitha kodet"],
           rez["te gjitha + zgjedhje ligji"])
f = lambda v: "MUNGON" if v is None else f"#{v}"
keq = thelle = 0
for (k, va), (_1, vb), (_2, vc) in zip(a, b, c):
    shenje = ""
    if va is not None and vc is None:
        shenje = "  <-- U HUMB"; keq += 1
    elif va is not None and vc is not None and vc > va:
        shenje = "  (me thelle)"; thelle += 1
    print(f"{k:<12} {f(va):>9} {f(vb):>12} {f(vc):>12}{shenje}")

buza_me = sum(1 for _k, v in c if v is not None and v >= 7)
print(f"\nGjetje ne buze te top-8 (#7 ose #8), me zgjedhje ligji: {buza_me}")
print(f"GJETJE TE HUMBURA me zgjedhje: {keq}, me thelle: {thelle}")

# THE EDGE COUNT ALONE CANNOT TELL A RESCUE FROM A DEGRADATION.
#
# This used to compare the edge count of the "everything" column against the
# "with selection" column and declare the design insufficient if the second was
# higher. That comparison was wrong in both directions: a finding that is
# MUNGON in a column counts zero toward its edge count, so a column that loses
# findings entirely looks healthier than one that finds them at rank seven.
#
# On the real corpus it duly printed "zgjedhja nuk mjafton; mos shto ligje te
# tjera ende" on a run where recall was 10/10, nothing was lost, and the single
# edge finding was bioc#16 arriving at #7 after having been missing altogether.
# That is advice to stop, printed on the best result the harness has recorded.
#
# A rank only means something against the last run's rank, so that is what is
# compared now, and with no baseline on disk the harness says so instead of
# pronouncing.
BAZA = Path("baza_kerkimit.json")
tanishme = {k: v for k, v in c}
celesi = {"prefiks": retrieve.PREFIX_LEN, "njesi": njesi_gjithsej}

e_vjeter = None
if BAZA.exists():
    try:
        d = json.loads(BAZA.read_text(encoding="utf-8"))
        e_vjeter = d.get("rendet")
        kushtet = d.get("kushtet") or {}
    except (json.JSONDecodeError, OSError):
        e_vjeter = None

if e_vjeter is None:
    print("\nPa baze krahasimi. Keto rende u ruajten si baze; leshimi tjeter\n"
          "do tregoje cfare u zhvendos. Nuk nxjerr verdikt sot.")
    BAZA.write_text(json.dumps({"kushtet": celesi, "rendet": tanishme},
                               ensure_ascii=False, indent=1), encoding="utf-8")
else:
    if kushtet and kushtet != celesi:
        print(f"\n[kujdes] baza u ruajt me {kushtet}, ky leshim eshte {celesi}.")
    fituar, humbur, thelluar = [], [], []
    for k, tani in tanishme.items():
        para = e_vjeter.get(k, "?")
        if para == "?":
            continue
        if para is None and tani is not None:
            fituar.append((k, "MUNGON", tani))
        elif para is not None and tani is None:
            humbur.append((k, para, "MUNGON"))
        elif para is not None and tani is not None and tani > para:
            thelluar.append((k, para, tani))
        elif para is not None and tani is not None and tani < para:
            fituar.append((k, para, tani))
    for emri, lst in (("FITUAR", fituar), ("HUMBUR", humbur),
                      ("ME THELLE", thelluar)):
        for k, para, tani in lst:
            print(f"   [{emri}] {k}: {para} -> {tani}")
    if not (fituar or humbur or thelluar):
        print("\nAsnje rend nuk u zhvendos nga leshimi i fundit.")
    print("\nVerdikti:", "asnje gjetje e humbur dhe asnje me thelle. "
          "Mund te shtosh ligje."
          if keq == 0 and not humbur and not thelluar
          else "dicka u zhvendos per keq; shiko rreshtat me lart para se te "
               "shtosh ligje.")
    if "--ruaj" in sys.argv:
        BAZA.write_text(json.dumps({"kushtet": celesi, "rendet": tanishme},
                                   ensure_ascii=False, indent=1),
                        encoding="utf-8")
        print(f"Baza u rifreskua ({BAZA}).")
    else:
        print(f"Per te pranuar keto rende si baze te re: "
              f"python3 mat_kerkimin.py --ruaj")
