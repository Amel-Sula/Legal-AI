#!/usr/bin/env python3
"""Minimum-wage check. Deterministic: no model, no retrieval.

The model is not asked anything here, so this finding cannot be hallucinated,
cannot cite the wrong provision, and gives the same answer every run. The whole
check is two numbers and a date.

The date matters more than it looks. The national minimum changed on
2026-01-01 from 40,000 to 50,000 leke. Checking a 2023 contract against the
2026 figure would report a breach that did not exist when it was signed. So a
contract with no readable date is NOT judged: it is reported as uncheckable,
which is the honest answer and the one a lawyer can act on.
"""
import re, unicodedata
from datetime import date

# Each row: in force from this date, gross monthly, gross hourly, the decision.
# Sources agree on both rows: inspektoriatipunes.gov.al's own VKM list, plus two
# independent accounting firms. Confirm against Fletorja Zyrtare before this is
# shown to a paying client.
TABELA = [
    (date(2023, 3, 1),  40000, None,  "VKM nr. 113, datë 1.3.2023"),
    (date(2026, 1, 1),  50000, 287.3, "VKM nr. 776, datë 19.12.2025"),
]
ME_HERSHME = TABELA[0][0]          # before this we hold no figures

FOLD = str.maketrans({"ë": "e", "Ë": "e", "ç": "c", "Ç": "c"})


def _fold(s):
    return unicodedata.normalize("NFC", s or "").translate(FOLD).lower()


def minimumi(d: date):
    """The row in force on `d`, or None if we hold no figure for that date."""
    row = None
    for frm, mujore, oreshe, vkm in TABELA:
        if d >= frm:
            row = (frm, mujore, oreshe, vkm)
    return row


# "100 000", "85.000", "100,000", "100000" -- Albanian documents use all four
NUM = r"\d{1,3}(?:[ .,]\d{3})+|\d{4,}"
PAGA = re.compile(
    r"pag[ae][^.\n]{0,80}?(" + NUM + r")\s*(?:\(|lek)", re.I)


def _si_numer(s):
    return int(re.sub(r"[ .,]", "", s))


DATA = re.compile(r"\b(\d{1,2})[./\-](\d{1,2})[./\-](20\d{2})\b")


def gjej_daten(text):
    """First dd.mm.yyyy in the document. Contracts put it in the header."""
    m = DATA.search(text)
    if not m:
        return None
    d, mth, y = (int(x) for x in m.groups())
    try:
        return date(y, mth, d)
    except ValueError:
        return None


def kontrollo(text, data_nenshkrimit=None):
    """Returns a list of findings in the shape pipeline.render() already prints."""
    t = _fold(text)
    d = data_nenshkrimit or gjej_daten(text)
    out = []

    pagat = [(_si_numer(m.group(1)), m.start()) for m in PAGA.finditer(t)]
    if not pagat:
        return [{"lloji": "paga_e_palexueshme", "ka_konflikt": False,
                 "detaj": "Nuk u gjet asnje shume page ne kontrate."}]

    paga = max(p for p, _ in pagat)       # the monthly figure is the largest

    # Net vs gross: the legal minimum is gross. Comparing it to a net figure
    # would invent a breach, so we decline to judge instead of guessing.
    if re.search(r"\bneto\b", t) and not re.search(r"\bbruto\b", t):
        return [{"lloji": "paga_neto", "ka_konflikt": False,
                 "detaj": f"Kontrata jep {paga:,} leke NETO. Minimumi ligjor "
                          f"eshte bruto, prandaj nuk krahasohet dot."}]

    if d is None:
        return [{"lloji": "data_e_panjohur", "ka_konflikt": False,
                 "detaj": f"Paga {paga:,} leke nuk u kontrollua: data e "
                          f"nenshkrimit nuk u lexua dot nga dokumenti."}]
    if d < ME_HERSHME:
        return [{"lloji": "data_para_tabeles", "ka_konflikt": False,
                 "detaj": f"Kontrata eshte e {d.isoformat()}, me e hershme se "
                          f"figurat qe mbajme ({ME_HERSHME.isoformat()})."}]

    _frm, mujore, _oreshe, vkm = minimumi(d)
    if paga < mujore:
        out.append({
            "ka_konflikt": True, "lloji": "nen_kufiri",
            "burimi": vkm, "neni_ligjit": vkm,
            "vlera_kontrates": f"{paga} leke", "vlera_ligjore": f"{mujore} leke",
            "tema": "paga minimale",
            "detaj": (f"Paga {paga:,} leke bie nen pagen minimale {mujore:,} "
                      f"leke ne fuqi me {d.isoformat()} ({vkm})."),
        })
    return out


if __name__ == "__main__":
    import sys
    from pathlib import Path
    if len(sys.argv) > 1:                       # kontrollo nje kontrate
        txt = Path(sys.argv[1]).read_text(encoding="utf-8")
        d = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else None
        gjetur = kontrollo(txt, d)
        print(f"Dokumenti : {sys.argv[1]}")
        print(f"Data      : {d or gjej_daten(txt) or 'nuk u lexua'}")
        if not gjetur:
            print("Rezultati : paga eshte mbi pagen minimale ne fuqi.")
        for r in gjetur:
            mark = "SHKELJE" if r.get("ka_konflikt") else "PA GJYKIM"
            print(f"Rezultati : [{mark}] {r.get('detaj')}")
        raise SystemExit(0)

    casos = [
        ("BIOCHECK, 100k, nenshkruar 2023", "paga prej 100 000 leke (nje qind mije)", date(2023, 11, 8), False),
        ("85.000 bruto, nenshkruar 2024", "Paga bruto mujore eshte 85.000 leke", date(2024, 5, 1), False),
        ("45.000 ne 2024 -> mbi minimumin e atehershem", "Paga bruto eshte 45.000 leke", date(2024, 5, 1), False),
        ("45.000 ne 2026 -> SHKELJE", "Paga bruto eshte 45.000 leke", date(2026, 2, 1), True),
        ("35.000 ne 2024 -> SHKELJE", "Paga bruto eshte 35.000 leke", date(2024, 5, 1), True),
        ("50.000 fiks ne 2026 -> ne rregull", "Paga bruto eshte 50 000 leke", date(2026, 3, 1), False),
        ("pa date -> nuk gjykohet", "Paga bruto eshte 30.000 leke", None, False),
        ("neto -> nuk gjykohet", "Paga neto eshte 30.000 leke", date(2026, 3, 1), False),
        ("2019, para tabeles -> nuk gjykohet", "Paga bruto eshte 20.000 leke", date(2019, 5, 1), False),
    ]
    bad = 0
    for label, txt, d, want in casos:
        r = kontrollo(txt, d)
        got = any(x.get("ka_konflikt") for x in r)
        bad += got != want
        print(f"[{'SHKELJE' if got else '  ok   '}] {label}{'   <-- GABIM' if got != want else ''}")
        msg = r[0].get("detaj", "") if r else "Paga eshte mbi minimumin ne fuqi."
        print(f"          {msg}")
    print(f"\nDESHTIME: {bad}")
    assert bad == 0
