#!/usr/bin/env python3
"""The product command: a document in, a report out.

score.py is the TEST harness. It needs an answer key, and a real client contract
does not have one. This is the entry point for actual work:

    python3 analizo.py kontrata.docx

Reads .docx, .pdf or .txt, splits it, checks every clause against the Labour
Code, checks the salary against the minimum wage in force on the signing date,
and writes a Markdown report next to the source document.
"""
import sys, tempfile
from pathlib import Path
from datetime import date

import ingest
import paga_minimale
from pipeline import run, render

# render() still carries a paragraph saying the minimum wage was not checked.
# It was true until paga_minimale.py existed. Swap it for the real answer.
MARKER = "## Pika që nuk mund të verifikohen"


def _seksioni_i_pages(teksti, data=None):
    gjetur = paga_minimale.kontrollo(teksti, data)
    d = data or paga_minimale.gjej_daten(teksti)
    L = ["## Paga minimale", ""]
    L.append(f"Kontrolluar kundrejt pagës minimale në fuqi më "
             f"{d.isoformat() if d else '(datë e palexuar)'}.")
    L.append("")
    if not gjetur:
        L.append("Paga e parashikuar është **mbi pagën minimale** në fuqi. "
                 "Nuk ka problem.")
    for r in gjetur:
        if r.get("ka_konflikt"):
            L.append(f"**Bie ndesh me {r['burimi']}**")
            L.append("")
            L.append(r["detaj"])
        else:
            L.append(f"**Nuk u vlerësua.** {r['detaj']}")
    L.append("")
    return "\n".join(L)


def _kreu_ocr(meta):
    """The OCR warning, and it goes ABOVE the findings on purpose.

    A lawyer who reads "the clause provides 48 hours" and only afterwards
    learns the document was machine-read has already formed the conclusion. The
    uncertain figures have to arrive before the conclusions that rest on them.
    """
    if not meta.get("nga_ocr"):
        return ""
    L = ["> ### Lexuar me OCR", ">",
         f"> Dokumenti u dorezuar i skanuar dhe u lexua me njohje teksti "
         f"({meta['faqe']} faqe, besueshmeri mesatare **{meta['besimi']}%**). "
         f"Teksti nuk vjen nga skedari; vjen nga leximi i figures.", ">"]
    numra = meta.get("numra_dyshimta") or []
    if numra:
        L.append(f"> **{len(numra)} numra u lexuan me siguri te ulet.** Nje "
                 f"shifre e lexuar gabim i kalon te gjitha kontrollet e "
                 f"raportit: citimi verifikohet, aritmetika qendron, dhe numri "
                 f"thjesht nuk eshte ai i letres. Kontrolloji keta kundrejt "
                 f"origjinalit para se te besosh ndonje perfundim mbi te:")
        L.append(">")
        for tok, c, faqe in numra[:25]:
            L.append(f"> - faqe {faqe}, lexuar `{tok}` me {c}% siguri")
        if len(numra) > 25:
            L.append(f"> - ...dhe {len(numra) - 25} te tjere")
    else:
        L.append("> Asnje numer nen pragun e sigurise. Kontrolli i pages dhe "
                 "i afateve mbetet i mire per t'u pare nga juristi.")
    faqe_keq = meta.get("faqe_dyshimta") or []
    if faqe_keq:
        L.append(">")
        L.append(f"> Faqe te lexuara dobet: "
                 f"{', '.join(f'{nr} ({b}%)' for nr, b in faqe_keq)}. "
                 f"Klauzolat ne keto faqe mund te mungojne fare ne raport.")
    L.append("")
    return "\n".join(L)


def analizo(path, mode="real", data=None, emri=None, kthe_meta=False):
    """`emri` is the name the REPORT carries, when it differs from the file's.

    web.py stores an upload under a fixed safe name, because a filename chosen
    by whoever sent the document must never become part of a path. That
    protection leaked into the output: every report was titled "dokument.txt",
    so a lawyer saving three of them got three files that named no contract.
    The path stays safe and the title tells the truth.
    """
    src = Path(path)
    teksti = ingest.lexo(src)

    # run() takes a path, so stage the extracted text in a temp file. The
    # client's document is never modified and nothing is written beside it
    # except the report.
    tmpdir = Path(tempfile.mkdtemp(prefix="kontrata_"))
    staged = tmpdir / (src.stem + ".txt")
    staged.write_text(teksti, encoding="utf-8")

    ocr_meta = dict(ingest.OCR_META)      # captured before anything else reads

    clauses, kept, dropped, meta = run(str(staged), mode=mode)
    raport = render(emri or src.name, clauses, kept, dropped, meta)

    # straight after the title, before the count of problems found
    kreu = _kreu_ocr(ocr_meta)
    if kreu:
        rreshtat = raport.split("\n")
        raport = "\n".join(rreshtat[:2] + [kreu] + rreshtat[2:])

    # The minimum wage is an employment question. Running it on a rental
    # contract would print a salary verdict about a document that has no
    # salary, which is the kind of confident irrelevance that costs trust.
    ligjet = meta.get("ligjet_e_zgjedhura") or []
    eshte_pune = any("punës" in L.lower() or "punes" in L.lower() for L in ligjet)
    if not eshte_pune:
        seksioni = ("## Paga minimale\n\nDokumenti nuk u lexua kundrejt Kodit "
                    "të Punës, pra nuk u kontrollua paga minimale.\n")
    else:
        seksioni = _seksioni_i_pages(teksti, data)
    if MARKER in raport:
        koka, _bishti = raport.split(MARKER, 1)
        pjesa = _bishti.split("## ", 1)
        mbetja = ("## " + pjesa[1]) if len(pjesa) > 1 else ""
        raport = koka + seksioni + "\n" + mbetja
    else:
        raport += "\n" + seksioni

    deshtime = meta.get("deshtime") or []
    # The chat side needs to know which laws the document was read against, so
    # that a follow-up question searches inside the same body of law instead of
    # all 243. Parsing it back out of the rendered report would be reading our
    # own prose, which breaks the first time the wording changes.
    if kthe_meta:
        meta_out = {"ligjet": meta.get("ligjet_e_zgjedhura") or [],
                    "njesi": meta.get("numri_njesive"),
                    "nga_ocr": bool(ocr_meta.get("nga_ocr"))}
    if deshtime:
        raport += (f"\n## KUJDES\n\n{len(deshtime)} pyetje nuk morën përgjigje. "
                   f"Raporti është i paplotë dhe nuk duhet dërguar ashtu siç është.\n")
    if kthe_meta:
        return raport, len(deshtime), meta_out
    return raport, len(deshtime)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Perdorim: python3 analizo.py <dokumenti> [data-nenshkrimit YYYY-MM-DD]")
        raise SystemExit(2)
    d = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else None
    mode = "real" if len(sys.argv) < 4 else sys.argv[3]
    try:
        raport, deshtime = analizo(sys.argv[1], mode=mode, data=d)
    except ingest.NukLexohet as e:
        print(f"[NUK LEXOHET] {e}")
        raise SystemExit(1)
    out = Path(sys.argv[1]).with_suffix("").with_name(
        Path(sys.argv[1]).stem + ".raport.md")
    out.write_text(raport, encoding="utf-8")
    print(f"\nRaporti: {out}")
    if deshtime:
        print(f"KUJDES: {deshtime} pyetje deshtuan. Mos e dergo keshtu.")
