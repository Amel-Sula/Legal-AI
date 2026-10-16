#!/usr/bin/env python3
"""The QBZ act register: every act's metadata, and which laws are still alive.

    python3 qbz_api.py numrat              # how many acts of each kind exist
    python3 qbz_api.py metadata ligj       # harvest all laws  -> akte_ligj.json
    python3 qbz_api.py metadata vendim     # harvest all VKMs  -> akte_vendim.json
    python3 qbz_api.py statusi             # which laws are amended or repealed

WHY METADATA FIRST, AND TEXT LATER.

Downloading 3,089 laws and 30,197 VKMs as PDFs is about 2.7 GB and many hours,
and most of those files will never be retrieved by a contract review. The
metadata for all of them is a few megabytes and arrives in minutes -- and it
carries the thing the corpus has never had:

    qbz:actType     Akt bazë | Akt ndryshues | Akt shfuqizues | Ndreqje gabimi

QBZ states, per act, whether it is a law, an amendment to one, or a repeal of
one. 97 of the 4,957 laws are repeals. The corpus today holds 243 laws and has
no idea whether any of them was killed in 2019, so it can quote a dead article
letter-perfect and the lawyer will believe it. That is the failure this fixes,
and it does not require a single PDF.

WHAT THE METADATA CANNOT GIVE, measured on live data rather than assumed:

  - An amending act names its target only in its TITLE ("...në ligjin nr.
    96/2016..."). There is no relation field. Parsed out of the title, this
    works for about 92% of amendments.
  - A repealing act names its target in the title only about 13% of the time.
    The rest are new laws that replace an old one without naming it: "Për
    kadastrën", "Për efiçencën e energjisë." Those repeals are stated in the
    act's TEXT, not its metadata, so closing that gap needs the PDF.

So the status layer is strong for amendments, partial for repeals, and the
report must say which it knows rather than implying it knows both.

API verified live, no authentication: paging past 1000 works, maxItems 1000
works, sorting works.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

KERKIMI = ("https://qbz.gov.al/alfresco/api/-default-/public/search/"
           "versions/1/search")
NYJA = ("https://qbz.gov.al/alfresco/api/-default-/public/alfresco/"
        "versions/1/nodes/")
KOKA = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}

FAQJA = 500          # maxItems per request; 1000 works, 500 is gentler
LLOJET = ("ligj", "vendim", "udhezim", "urdher", "dekret", "akt-normativ",
          "rregullore", "konvente", "marreveshje")

# "...në ligjin nr. 96/2016..."  /  "...në ligjin nr. 10 093, datë 9.3.2009..."
# The number may carry a space ("10 093"), and the year may arrive either as
# /YYYY or at the end of a dotted date.
REF_LIGJI = re.compile(
    r"ligj(?:in|it|i|et|e)?\b[^\"“]{0,30}?nr\.?\s*"
    r"(\d[\d\s]{0,8}?)\s*"
    r"(?:/\s*(\d{4})|,?\s*dat[ëe]\s*\d{1,2}\.\d{1,2}\.(\d{4}))", re.I)


def _post(trupi, provat=3):
    dhena = json.dumps(trupi).encode()
    for p in range(provat):
        try:
            req = urllib.request.Request(KERKIMI, data=dhena, headers=KOKA)
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode())
        except Exception:
            if p == provat - 1:
                raise
            time.sleep(2 * (p + 1))


def kerko(afts, maxItems=1, skipCount=0, fusha=True, facets=None):
    trupi = {
        "query": {"language": "afts", "query": afts},
        "paging": {"maxItems": maxItems, "skipCount": skipCount},
        "sort": [{"type": "FIELD", "field": "qbz:actDate", "ascending": True}],
    }
    if fusha:
        trupi["include"] = ["properties"]
    if facets:
        trupi["facetFields"] = {"facets": [{"field": f, "label": f}
                                           for f in facets]}
    return _post(trupi)


def sa_ka(afts):
    j = kerko(afts, maxItems=1, fusha=False)
    return (j.get("list", {}).get("pagination", {}) or {}).get("totalItems", 0)


def _pyetja(lloji, akt_tipi=None):
    q = f'TYPE:"qbz:act" AND qbz:actActType:"*document-type/{lloji}"'
    if akt_tipi:
        q += f' AND qbz:actType:"{akt_tipi}"'
    return q


def _rresht(e):
    p = e.get("properties", {}) or {}
    return {
        "id": e.get("id"),
        "skedari": e.get("name"),
        "numri": p.get("qbz:actNumber"),
        "data": (p.get("qbz:actDate") or "")[:10],
        "titulli": p.get("qbz:actTitle"),
        "lloji_akti": p.get("qbz:actType"),
        "fletorja": p.get("qbz:actOfficialJournalNr"),
        "fletorja_data": (p.get("qbz:actOfficialJournalDate") or "")[:10],
        "tema": [t.rsplit("/", 1)[-1]
                 for t in (p.get("qbz:actContext") or [])],
        "institucioni": (p.get("qbz:actResponsibleInstitution") or "")
                        .rsplit("/", 1)[-1],
        "url": p.get("qbz:url"),
    }


def metadata(lloji, out=None):
    """Every act of one kind, metadata only, paged."""
    afts = _pyetja(lloji)
    gjithsej = sa_ka(afts)
    print(f"{lloji}: {gjithsej} akte")
    rreshtat, skip = [], 0
    while skip < gjithsej:
        j = kerko(afts, maxItems=FAQJA, skipCount=skip)
        hyrjet = j.get("list", {}).get("entries", []) or []
        if not hyrjet:
            print(f"   [ndal] asnje rezultat ne skip={skip}")
            break
        rreshtat += [_rresht(x["entry"]) for x in hyrjet]
        skip += len(hyrjet)
        print(f"   {skip}/{gjithsej}", end="\r", flush=True)
    dest = Path(out or f"akte_{lloji}.json")
    dest.write_text(json.dumps(rreshtat, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print(f"\n   -> {dest}  ({len(rreshtat)} akte)")
    return rreshtat


def numrat():
    """How big is each pile, and how much of it is amendment or repeal."""
    print(f"{'lloji':<14} {'gjithsej':>9}   {'baze':>7} {'ndrysh.':>8} "
          f"{'shfuq.':>7} {'ndreqje':>8}")
    for l in LLOJET:
        t = sa_ka(_pyetja(l))
        if not t:
            continue
        b = sa_ka(_pyetja(l, "Akt bazë"))
        n = sa_ka(_pyetja(l, "Akt ndryshues"))
        s = sa_ka(_pyetja(l, "Akt shfuqizues"))
        k = sa_ka(_pyetja(l, "Ndreqje gabimi"))
        print(f"{l:<14} {t:>9}   {b:>7} {n:>8} {s:>7} {k:>8}")


def _celes(nr, vit):
    return f"{re.sub(r'[^0-9]', '', nr or '')}/{vit}"


def statusi(skedari="akte_ligj.json"):
    """Which laws have been amended, and which repealed.

    The link lives in the amending act's title and nowhere else, so this is
    text matching, not a lookup, and it reports its own coverage instead of
    presenting a partial answer as a complete one.
    """
    p = Path(skedari)
    if not p.exists():
        print(f"{skedari} nuk u gjet. Lesho me pare: "
              f"python3 qbz_api.py metadata ligj")
        return
    aktet = json.loads(p.read_text(encoding="utf-8"))
    baza = {}
    for a in aktet:
        if a["lloji_akti"] == "Akt bazë":
            baza[_celes(a["numri"], (a["data"] or "")[:4])] = a

    prekur, pa_lidhje = {}, {"ndryshues": 0, "shfuqizues": 0}
    for a in aktet:
        lloji = a["lloji_akti"]
        if lloji not in ("Akt ndryshues", "Akt shfuqizues"):
            continue
        m = REF_LIGJI.search(a["titulli"] or "")
        if not m:
            pa_lidhje["ndryshues" if lloji == "Akt ndryshues"
                      else "shfuqizues"] += 1
            continue
        k = _celes(m.group(1), m.group(2) or m.group(3))
        rec = prekur.setdefault(k, {"ndryshuar": [], "shfuqizuar": []})
        rec["shfuqizuar" if lloji == "Akt shfuqizues"
            else "ndryshuar"].append({"nr": a["numri"], "data": a["data"],
                                      "titulli": (a["titulli"] or "")[:90]})

    dest = Path("statusi_ligjeve.json")
    dalja = {}
    for k, v in prekur.items():
        b = baza.get(k)
        dalja[k] = {
            "titulli": (b or {}).get("titulli"),
            "ne_korpus_si": k,
            "shfuqizuar": bool(v["shfuqizuar"]),
            "here_ndryshuar": len(v["ndryshuar"]),
            "ndryshimi_i_fundit": max([x["data"] for x in v["ndryshuar"]],
                                      default=""),
            "aktet": v,
        }
    dest.write_text(json.dumps(dalja, ensure_ascii=False, indent=1),
                    encoding="utf-8")

    shfuq = sum(1 for v in dalja.values() if v["shfuqizuar"])
    print(f"ligje baze            : {len(baza)}")
    print(f"ligje te prekura      : {len(dalja)}  "
          f"(shfuqizuar: {shfuq}, vetem te ndryshuara: {len(dalja) - shfuq})")
    print(f"lidhje qe nuk u nxoren: {pa_lidhje['ndryshues']} ndryshues, "
          f"{pa_lidhje['shfuqizues']} shfuqizues")
    print(f"\n-> {dest}")
    print("\nKUJDES: lidhja e nje akti me ligjin qe prek gjendet VETEM ne\n"
          "titullin e tij. Per shfuqizimet kjo del shpesh e paemertuar\n"
          "('Per kadastren'), pra lista e shfuqizimeve eshte DYSHEME, jo e\n"
          "plote. Nje ligj qe nuk del ketu nuk eshte deshmuar ne fuqi.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "numrat"
    if cmd == "numrat":
        numrat()
    elif cmd == "metadata":
        metadata(sys.argv[2] if len(sys.argv) > 2 else "ligj")
    elif cmd == "statusi":
        statusi(sys.argv[2] if len(sys.argv) > 2 else "akte_ligj.json")
    else:
        print(__doc__)
