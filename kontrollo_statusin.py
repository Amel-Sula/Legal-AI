#!/usr/bin/env python3
"""Which laws in OUR corpus are dead, and which are out of date.

    python3 kontrollo_statusin.py

The register from qbz_api.py covers all 3,088 base laws in Albania. This asks
the only question that matters today: of the 243 laws this product actually
cites, which ones have been repealed, and which have been amended since the
file we parsed was published?

The second question is the sharper one. A repealed law is at least a clean
failure once we know. A law amended after our copy was published is worse: the
text still exists, the citation still verifies letter-perfect against our
corpus, and the article simply no longer says what we print. Nothing in the
pipeline can catch that, because our corpus IS the authority it checks against.

Two dates decide it:

    ndryshimi i fundit   when QBZ last published an act amending this law
    skedari yne          when QBZ last republished the file we parsed
                         (from manifest.json, via the corpus)

If the amendment is newer than our file, our text is behind. That is stated
per law rather than summarised, because the lawyer needs to know WHICH law.
"""
import json
from pathlib import Path

KORPUSI = "korpus_ligjet.json"
STATUSI = "statusi_ligjeve.json"
KODI_PUNES = "kodi_punes_flagged.json"


def _ngarko(p, default):
    f = Path(p)
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def ligjet_tona():
    """Every law in the corpus: its key, title, and the date of our file."""
    out = {}
    d = _ngarko(KORPUSI, [])
    if d is None:
        print(f"{KORPUSI} nuk u gjet.")
        return out
    for x in d:
        k = (x.get("ligji") or "").strip()
        if not k or "/" not in k:
            continue
        rec = out.setdefault(k, {"titulli": x.get("titulli_ligjit"),
                                 "qbz_modifikuar": x.get("qbz_modifikuar") or "",
                                 "burimi": x.get("burimi") or "",
                                 "nene": 0})
        rec["nene"] += 1

    kp = _ngarko(KODI_PUNES, {})
    if kp and kp.get("meta"):
        m = kp["meta"]
        nr = str(m.get("ligji") or "").strip()
        data = str(m.get("data_miratimit") or "")[:4]
        if nr and data:
            out[f"{nr}/{data}"] = {
                "titulli": "Kodi i Punës",
                "qbz_modifikuar": m.get("i_vlefshem_deri") or "",
                "burimi": "kodi_punes_flagged.json",
                "nene": m.get("numri_neneve", 0),
            }
    return out


def main():
    tonat = ligjet_tona()
    st = _ngarko(STATUSI, {})
    if st is None:
        print(f"{STATUSI} nuk u gjet. Lesho me pare:\n"
              f"   python3 qbz_api.py metadata ligj\n"
              f"   python3 qbz_api.py statusi")
        return
    if not tonat:
        return

    vdekur, vjetruar, ndryshuar_ok, pa_daten_tone, te_panjohur = [], [], [], [], []
    for k, ynë in sorted(tonat.items()):
        info = st.get(k)
        if not info:
            te_panjohur.append((k, ynë))
            continue
        if info.get("shfuqizuar"):
            vdekur.append((k, ynë, info))
            continue
        i_fundit = info.get("ndryshimi_i_fundit") or ""
        ynai = ynë.get("qbz_modifikuar") or ""
        if not i_fundit:
            continue
        if not ynai:
            # NOT KNOWING IS ITS OWN ANSWER.
            #
            # The first version of this compared the two dates and, when ours
            # was missing, fell through to "our file is newer -- fine". Empty
            # is not newer; it is unknown. On the first real run that declared
            # 101 amended laws healthy while holding no date for any of them,
            # which is the false reassurance this whole tool exists to prevent.
            pa_daten_tone.append((k, ynë, info))
        elif i_fundit > ynai:
            vjetruar.append((k, ynë, info))
        else:
            ndryshuar_ok.append((k, ynë, info))

    print(f"Ligje ne korpus: {len(tonat)}\n")

    if vdekur:
        print(f"SHFUQIZUAR ({len(vdekur)}) - keto nuk duhen cituar fare:")
        for k, y, i in vdekur:
            print(f"  {k:<13} {(y['titulli'] or '')[:50]:<52} {y['nene']:>5} nene")
            for a in i["aktet"]["shfuqizuar"][:1]:
                print(f"                nga ligji {a['nr']} i {a['data']}")
        print()

    if vjetruar:
        print(f"TEKST I VJETRUAR ({len(vjetruar)}) - ndryshuar PAS skedarit tone:")
        for k, y, i in vjetruar:
            print(f"  {k:<13} {(y['titulli'] or '')[:46]:<48}")
            print(f"                skedari yne: {y['qbz_modifikuar'] or '?'}   "
                  f"ndryshimi i fundit: {i['ndryshimi_i_fundit']}  "
                  f"({i['here_ndryshuar']} here)")
        print()

    if pa_daten_tone:
        print(f"TE NDRYSHUARA, POR NUK E DIME NESE JEMI PRAPA "
              f"({len(pa_daten_tone)}):")
        print("  Keto ligje jane ndryshuar nga QBZ-ja, dhe per skedarin tone")
        print("  nuk kemi date fare, pra nuk krahasohet dot. Lesho:")
        print("      python3 shkarko_qbz.py ~/ligjet")
        print("      python3 shto_ligj.py ~/ligjet/Kodet")
        print("      python3 shto_ligj.py ~/ligjet/Permbledhje_Legjislacioni")
        print("  qe manifesti te ndertohet dhe datat te hyjne ne korpus.")
        for k, y, i in pa_daten_tone[:6]:
            print(f"    {k:<13} {(y['titulli'] or '')[:40]:<42} "
                  f"ndryshuar {i['here_ndryshuar']}x, i fundit "
                  f"{i['ndryshimi_i_fundit']}")
        if len(pa_daten_tone) > 6:
            print(f"    ... dhe {len(pa_daten_tone) - 6} te tjere")
        print()

    if ndryshuar_ok:
        print(f"TE NDRYSHUARA, dhe skedari yne eshte me i ri "
              f"({len(ndryshuar_ok)}). Ne rregull.")
    if te_panjohur:
        print(f"\nPA TE DHENA ({len(te_panjohur)}): nuk u gjeten ne regjistrin e "
              f"QBZ-se me kete numer.")
        print("  Shkaqet e mundshme: numri i ligjit u nxor gabim nga PDF-ja, ose")
        print("  ligji nuk eshte prekur kurre nga nje akt tjeter (pra eshte ne")
        print("  rregull), ose eshte shfuqizuar nga nje akt qe nuk e emerton.")
        for k, y in te_panjohur[:8]:
            print(f"    {k:<13} {(y['titulli'] or '')[:54]}")
        if len(te_panjohur) > 8:
            print(f"    ... dhe {len(te_panjohur) - 8} te tjere")

    print(f"\nKUJDES: 'pa te dhena' NUK do te thote 'ne fuqi'. Vetem 14 nga 97 "
          f"\nshfuqizimet e ligjeve u lidhen dot me ligjin qe vrasin, sepse "
          f"\ntitulli i tyre shpesh nuk e emerton. Kjo liste eshte dysheme.")


if __name__ == "__main__":
    main()
