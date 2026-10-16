#!/usr/bin/env python3
"""One place that knows what "the law" means. Every program loads it from here.

Until now pipeline.py loaded kodi_punes_flagged.json directly, so the product
could only ever see the Labour Code: an employment contract worked, a rental
contract came back empty. korpus_ligjet.json held the other codes but nothing
read it except the measurement harness.

This module merges the two and tags every single provision with the law it
belongs to. That tag is what makes the rest possible:

  - the document picks its own law (zgjidh_ligjin), so retrieval runs inside
    the one or two laws it is actually about instead of across everything
  - a citation says WHICH law's Neni 5, because "Neni 5" alone names sixteen
    different provisions once the whole library is in
  - verification checks the quote against that law's article and no other

    import korpusi
    units = korpusi.ngarko()                       # everything
    nen, emrat = korpusi.per_dokument(units, text) # just this document's law
"""
import json
import re
from pathlib import Path

import retrieve
import sinjale
from zgjidh_ligjin import ligjet_e_dokumentit

KODI_PUNES = "Kodi i Punës"
SKEDARI_KP = "kodi_punes_flagged.json"
SKEDARI_LIGJET = "korpus_ligjet.json"
SKEDARI_STATUSI = "statusi_ligjeve.json"


def _eshte_kodi_punes(titulli: str) -> bool:
    """The Labour Code is already in, at point level. Recognising it under the
    names the PDFs give it is what stops it being loaded a second time at
    article level, where it would compete against itself for candidate slots."""
    t = (titulli or "").lower().replace("ë", "e").replace("ç", "c")
    t = re.sub(r"\d+", "", t)
    return bool(re.search(r"kodi\s+i\s+punes|kodin\s+e\s+punes", t))


def ngarko(rrenja=".", vetem_kodi_punes=False, skedari_kp=None):
    """Every provision of every law on disk, as one flat list of units.

    The Labour Code comes in at POINT level (Neni 150, pika 1), because
    parse_kodi.py split it that way and flag_limits.py marked each point. The
    other codes come in at ARTICLE level, because that is as far as the generic
    parser can safely split them. Both are units; the units carry `pika` so the
    difference stays visible in a citation.
    """
    # `skedari_kp` lets a caller point at a different point-level corpus, which
    # is what score.py uses to measure against a corpus other than the default.
    meta, units = retrieve.load(skedari_kp or str(Path(rrenja) / SKEDARI_KP))
    for u in units:
        u["titulli_ligjit"] = KODI_PUNES
        u["ligji"] = meta.get("ligji")
        u["qbz_modifikuar"] = meta.get("i_vlefshem_deri") or ""
    meta["ligjet"] = {KODI_PUNES: len({u["neni"] for u in units})}

    p = Path(rrenja) / SKEDARI_LIGJET
    if not vetem_kodi_punes and p.exists():
        for x in json.loads(p.read_text(encoding="utf-8")):
            titulli = x.get("titulli_ligjit") or "?"
            if _eshte_kodi_punes(titulli):
                continue                      # already in, at point level
            sh = sinjale.shenjo(x["teksti"])
            units.append({
                "ref": f"Neni {x['neni']}",
                "neni": x["neni"],
                "pika": None,
                "kreu": None,
                "seksioni": titulli,          # retrieval weights the heading
                "teksti": x["teksti"],
                "temat": [],
                "titulli_ligjit": titulli,
                "ligji": x.get("ligji"),
                "burimi": x.get("burimi"),
                "qbz_modifikuar": x.get("qbz_modifikuar") or "",
                "shkarkuar": x.get("shkarkuar") or "",
                "sinjale": sh["sinjale"],
                "vlera": sh["vlera_numerike"],
                "i_kontrollueshem": sh["i_kontrollueshem"],
                "ndryshuar_me": None,
            })
            meta["ligjet"][titulli] = meta["ligjet"].get(titulli, 0) + 1

    # Collisions are resolved FIRST, because resolving them renames titles, and
    # the two maps below are keyed by title. Built before the rename, they would
    # key on names no unit carries any more and every lookup would miss.
    _zgjidh_perplasjet(units, meta)

    # HOW OLD IS EACH LAW. Per law, the QBZ republication date of the file it
    # was parsed from. The Labour Code keeps its own consolidation date, which
    # is better still: it names the five laws that amended it.
    datat, numrat = {}, {}
    for u in units:
        e = u.get("titulli_ligjit")
        if not e:
            continue
        d = u.get("qbz_modifikuar") or ""
        if d:
            datat[e] = min(datat[e], d) if e in datat else d
        if u.get("ligji"):
            numrat.setdefault(e, u["ligji"])
    datat.setdefault(KODI_PUNES, meta.get("i_vlefshem_deri") or "")
    meta["datat_e_ligjeve"] = datat
    meta["nr_e_ligjeve"] = numrat

    meta["numri_njesive"] = len(units)
    return meta, units


def freskia(meta, skedari=SKEDARI_STATUSI):
    """Per law: our text's date, and whether QBZ amended it AFTER that date.

    Our own date alone cannot answer the question that matters. The compilation
    PDFs QBZ publishes are mostly stamped 2021-02-17, while the acts amending
    those same laws run through 2026 -- so a law can be two republications
    behind and our file looks perfectly respectable. The register
    (statusi_ligjeve.json) holds the amending acts' dates, and comparing the two
    is the only way the report can say "this article may no longer read this
    way" instead of printing a date and leaving the lawyer to guess.

    Returns {} when the register has not been harvested, and the caller says so
    rather than implying the text is current.
    """
    p = Path(skedari)
    if not p.exists():
        return {}
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    datat = meta.get("datat_e_ligjeve") or {}
    numrat = meta.get("nr_e_ligjeve") or {}
    out = {}
    for emri, nr in numrat.items():
        info = st.get(nr)
        if not info:
            continue
        jona = datat.get(emri) or ""
        i_fundit = info.get("ndryshimi_i_fundit") or ""
        out[emri] = {
            "nr": nr,
            "data_jone": jona,
            "ndryshimi_i_fundit": i_fundit,
            "here": info.get("here_ndryshuar", 0),
            "shfuqizuar": bool(info.get("shfuqizuar")),
            # Unknown is not "fine". With no date of our own we cannot compare,
            # and that has to read as a gap, not as a pass.
            "prapa": bool(i_fundit) and (not jona or i_fundit > jona[:10]),
            "pa_daten_tone": not jona,
        }
    return out


def _zgjidh_perplasjet(units, meta):
    """Two DIFFERENT laws must never share a title.

    The title is the key every citation is verified against, so if the Customs
    Code and the implementing provisions of the Customs Code both come out
    named "Kodi Doganor", their articles merge: one law's Neni 5 silently
    overwrites the other's, and a citation to either can no longer be checked.
    That is the one property the product is sold on, so the collision is
    resolved here rather than trusted not to happen -- titles are read out of
    PDF title blocks and will collide again.
    """
    nr_per_emer = {}
    for u in units:
        nr_per_emer.setdefault(u.get("titulli_ligjit"), set()).add(u.get("ligji"))
    perplasur = {e for e, nr in nr_per_emer.items() if len(nr) > 1}
    if not perplasur:
        return
    for u in units:
        if u.get("titulli_ligjit") in perplasur:
            u["titulli_ligjit"] = f"{u['titulli_ligjit']} ({u.get('ligji')})"
    nene = {}
    for u in units:
        nene.setdefault(u["titulli_ligjit"], set()).add(u["neni"])
    meta["ligjet"] = {k: len(v) for k, v in nene.items()}
    meta["perplasje_emrash"] = sorted(perplasur)


def gjej_ligjin(units, model):
    """The title a law actually carries in THIS corpus, found by pattern.

    Law titles are read out of PDF title blocks, so they are not stable text:
    the Civil Code arrived as "Kodi Civil" from one build and "Për Kodin Civil
    Të Republikës Së Shqipërisë1" from another. Nothing should hardcode one
    spelling -- a test that does will fail on a corpus that is perfectly fine,
    which is exactly what happened.
    """
    rx = re.compile(model, re.I)
    emrat = {u.get("titulli_ligjit") for u in units if u.get("titulli_ligjit")}
    gjetur = sorted((e for e in emrat if rx.search(e.replace("ë", "e"))), key=len)
    return gjetur[0] if gjetur else None


def per_dokument(units, teksti, sa=2, idx=None):
    """Narrow the corpus to the law(s) this document is about.

    Returns (units of those laws, their names). The names go in the report:
    the lawyer must be able to see which body of law the document was read
    against, and disagree with that choice if it is wrong.
    """
    idx = idx or retrieve.BM25(units)
    emrat = set(ligjet_e_dokumentit(idx, teksti, sa=sa))
    if not emrat:
        return units, []
    nen = [u for u in units if u.get("titulli_ligjit") in emrat]
    return (nen or units), sorted(emrat)


if __name__ == "__main__":
    meta, units = ngarko()
    print(f"{meta['numri_njesive']} njësi nga {len(meta['ligjet'])} ligje\n")
    for k, v in sorted(meta["ligjet"].items(), key=lambda kv: -kv[1]):
        kontroll = sum(1 for u in units
                       if u.get("titulli_ligjit") == k and u.get("i_kontrollueshem"))
        print(f"  {v:5d} nene  {kontroll:5d} me kufij numerike  {k[:56]}")

    print("\nZgjedhja e ligjit per fiksturat:")
    idx = retrieve.BM25(units)
    for fx in ("kontrata_biocheck.txt", "kontrata_test_01.txt"):
        if not Path(fx).exists():
            continue
        t = Path(fx).read_text(encoding="utf-8")
        nen, emrat = per_dokument(units, t, idx=idx)
        print(f"  {fx:26s} -> {', '.join(emrat)}  ({len(nen)} njesi)")
