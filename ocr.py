#!/usr/bin/env python3
"""Reading scanned contracts, and refusing to trust their numbers blindly.

Every signed contract in Albania is a scan, so without this the product cannot
read a single real client document. But OCR is not just "slower text": it is
text with an error rate, and this product's whole output rests on numbers.

A misread digit is the worst failure this system can produce. If "40 orë" is
read as "48 orë", then:

  - verify.vlera_ne_klauzole passes it, because 48 really is in the text it was
    given
  - verify.numeric_check compares 48 against the legal 40 and finds a breach
  - the citation is genuine and verifies perfectly
  - the report tells a lawyer his client's contract says 48 hours

Nothing downstream can catch it, because every layer is working correctly on a
document that was wrong before they saw it. So the guard has to live here: the
text comes back with the per-word confidence tesseract already computes, and
every numeric token it was unsure about is listed. analizo.py prints those at
the top of the report, where the lawyer sees them before reading conclusions.

Needs the Albanian language pack:

    sudo apt install -y tesseract-ocr tesseract-ocr-sqi

    python3 ocr.py                      # is it installed and working
    python3 ocr.py kontrata_skanuar.pdf # OCR one document
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Overridable so a machine without the Albanian pack can still be exercised
# (OCR_GJUHA=eng), and so a bilingual contract can be read with "sqi+eng".
GJUHA = os.environ.get("OCR_GJUHA", "sqi")
DPI = int(os.environ.get("OCR_DPI", "300"))

# Below this, tesseract is guessing. Tuned to be noisy rather than quiet: a
# flagged number the lawyer checks in ten seconds costs far less than a wrong
# one he does not know to check.
PRAGU_NUMRI = 85
PRAGU_FAQE = 70

NUMRI = re.compile(r"\d")


class OcrMungon(Exception):
    pass


def gjuhet():
    if not shutil.which("tesseract"):
        return []
    r = subprocess.run(["tesseract", "--list-langs"],
                       capture_output=True, text=True)
    return [x.strip() for x in (r.stdout or "").splitlines()[1:] if x.strip()]


def kontrollo(gjuha=GJUHA):
    """What is installed, and what that means for the language being asked for.

    Takes the language as an argument rather than always testing Albanian: it
    is called by lexo(), which can be pointed at another model, and a check
    that ignores its caller's argument is a check that reports on something
    other than what is about to run.
    """
    if not shutil.which("tesseract"):
        raise OcrMungon("tesseract nuk eshte instaluar. "
                        "sudo apt install -y tesseract-ocr tesseract-ocr-sqi")
    g = gjuhet()
    if gjuha not in g:
        shtese = "-sqi" if gjuha == GJUHA else ""
        raise OcrMungon(
            f"modeli '{gjuha}' mungon (ka: {', '.join(g) or 'asnje'}). "
            f"sudo apt install -y tesseract-ocr{shtese}")
    return g


def _faqet(pdf: Path, dpi=DPI):
    """PDF pages as PIL images. pypdfium2 renders without an external binary."""
    import pypdfium2 as pdfium
    dok = pdfium.PdfDocument(str(pdf))
    for i in range(len(dok)):
        yield i + 1, dok[i].render(scale=dpi / 72).to_pil()


def lexo_faqen(img, gjuha=GJUHA):
    """One page: its text, its mean confidence, and the numbers in doubt.

    tesseract's own per-word confidence is used rather than a second model
    judging the first: it costs nothing and it is the only signal here that was
    not produced by guesswork.
    """
    import pytesseract
    from pytesseract import Output

    d = pytesseract.image_to_data(img, lang=gjuha, output_type=Output.DICT)
    fjale, besimet, dyshimta = [], [], []
    for teksti, conf in zip(d["text"], d["conf"]):
        t = (teksti or "").strip()
        if not t:
            continue
        try:
            c = float(conf)
        except (TypeError, ValueError):
            continue
        if c < 0:
            continue
        fjale.append(t)
        besimet.append(c)
        if NUMRI.search(t) and c < PRAGU_NUMRI:
            dyshimta.append((t, round(c)))

    teksti = pytesseract.image_to_string(img, lang=gjuha)
    mesatarja = sum(besimet) / len(besimet) if besimet else 0.0
    return teksti, mesatarja, dyshimta


def lexo(pdf, gjuha=GJUHA, dpi=DPI):
    """A scanned PDF as text, plus everything needed to distrust it properly.

    Returns (teksti, meta) where meta carries:
        besimi          mean per-word confidence over the document
        numra_dyshimta  [(token, confidence, page)] for every uncertain number
        faqe_dyshimta   pages whose overall confidence is low
    """
    kontrollo(gjuha)
    pjese, besimet, dyshimta, faqe_keq = [], [], [], []
    for nr, img in _faqet(Path(pdf), dpi):
        t, besimi, numra = lexo_faqen(img, gjuha)
        pjese.append(t)
        besimet.append(besimi)
        dyshimta += [(tok, c, nr) for tok, c in numra]
        if besimi and besimi < PRAGU_FAQE:
            faqe_keq.append((nr, round(besimi)))
    return "\n".join(pjese), {
        "nga_ocr": True,
        "gjuha": gjuha,
        "dpi": dpi,
        "faqe": len(besimet),
        "besimi": round(sum(besimet) / len(besimet), 1) if besimet else 0.0,
        "numra_dyshimta": dyshimta,
        "faqe_dyshimta": faqe_keq,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        try:
            g = kontrollo()
            print(f"OK. tesseract ka: {', '.join(g)}")
            print(f"Shqipja '{GJUHA}' e gatshme. {DPI} DPI, "
                  f"pragu i numrit {PRAGU_NUMRI}%.")
        except OcrMungon as e:
            print(f"[MUNGON] {e}")
            raise SystemExit(1)
        raise SystemExit(0)

    try:
        teksti, meta = lexo(sys.argv[1])
    except OcrMungon as e:
        print(f"[MUNGON] {e}")
        raise SystemExit(1)
    print(f"{meta['faqe']} faqe, besimi mesatar {meta['besimi']}%")
    if meta["faqe_dyshimta"]:
        print(f"FAQE TE DOBETA: {meta['faqe_dyshimta']}")
    if meta["numra_dyshimta"]:
        print(f"\nNUMRA NE DYSHIM ({len(meta['numra_dyshimta'])}) - "
              f"kontrolloji me dore kundrejt origjinalit:")
        for tok, c, faqe in meta["numra_dyshimta"][:40]:
            print(f"   faqe {faqe}  {c:>3}%  {tok!r}")
    out = Path(sys.argv[1]).with_suffix(".ocr.txt")
    out.write_text(teksti, encoding="utf-8")
    print(f"\nTeksti: {out}")
