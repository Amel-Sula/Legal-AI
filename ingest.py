#!/usr/bin/env python3
"""Turn whatever a law firm sends into the plain text split_clauses.py expects.

No firm sends .txt. They send .docx and .pdf, and a fair share of the PDFs are
scans of a signed paper copy. This reads the first two and REFUSES the third
loudly, because a scan silently yielding three characters of text would walk
through the whole pipeline and produce a confident report about nothing.

Output shape matches the existing fixtures: one block per line, a blank line
between blocks, headings left on their own line.
"""
import re, sys, unicodedata
from pathlib import Path

# A page of a real contract holds hundreds of characters. Far below that and
# the PDF is a picture of a page, not a page.
MIN_SHKRONJA_FAQE = 100

# Lines that must never be glued to the line above: article headings, numbered
# sub-points, and lettered sub-points, in the spellings Albanian contracts use.
TITULL = re.compile(
    r"^\s*(?:neni\s+\d|kreu\b|nen\s+\d|\d+\s*\.\s*\d|\d+\s*\.\s|[a-zçë]\s*[.)]\s)",
    re.I)


# Filled by _pdf() when a document had to be read with OCR, so analizo.py can
# put the uncertain numbers at the top of the report. Cleared on every read, so
# a report never carries the previous document's warnings.
OCR_META = {}


class NukLexohet(Exception):
    pass


def _pastro(bllok):
    """Normalise whitespace inside one block, keep the block itself intact."""
    out = []
    for b in bllok:
        b = unicodedata.normalize("NFC", b).replace(" ", " ")
        b = re.sub(r"[ \t]+", " ", b).strip()
        if b:
            out.append(b)
    return "\n\n".join(out) + "\n"


# ---------------------------------------------------------------- docx
def _docx(path):
    try:
        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError:
        raise NukLexohet("Mungon python-docx.  pip install python-docx")

    d = docx.Document(str(path))
    blocks = []
    # Walk the body in document order. document.paragraphs alone SKIPS tables,
    # and Albanian contracts put the parties, salary and dates in tables often
    # enough that losing them would quietly drop half the clauses.
    for child in d.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            t = Paragraph(child, d).text
            if t.strip():
                blocks.append(t)
        elif tag == "tbl":
            for row in Table(child, d).rows:
                cells = [c.text.strip() for c in row.cells]
                # a row repeated across merged cells collapses to one value
                uniq, seen = [], set()
                for c in cells:
                    if c and c not in seen:
                        seen.add(c); uniq.append(c)
                if uniq:
                    blocks.append(" | ".join(uniq))
    if not blocks:
        raise NukLexohet("Dokumenti .docx eshte bosh ose vetem me figura.")
    return _pastro(blocks)


# ---------------------------------------------------------------- pdf
def _pdf(path):
    try:
        import pdfplumber
    except ImportError:
        raise NukLexohet("Mungon pdfplumber.  pip install pdfplumber")

    faqe, gjithsej = [], 0
    with pdfplumber.open(str(path)) as pdf:
        n = len(pdf.pages)
        for p in pdf.pages:
            t = p.extract_text() or ""
            gjithsej += len(t.strip())
            faqe.append(t)

    if n and gjithsej / n < MIN_SHKRONJA_FAQE:
        # A SCAN. Every signed contract in Albania is one, so refusing here
        # refused every real client document. OCR it instead -- and carry back
        # what OCR was unsure about, because a misread digit is the one error
        # no later layer can catch: the quote verifies, the arithmetic holds,
        # and the number is simply not what the paper says.
        try:
            import ocr
            teksti, meta = ocr.lexo(path)
            OCR_META.clear()
            OCR_META.update(meta)
            if len(teksti.strip()) < MIN_SHKRONJA_FAQE:
                raise NukLexohet(
                    f"OCR-i nxori vetem {len(teksti.strip())} shkronja nga "
                    f"{n} faqe. Skanimi eshte shume i dobet per te lexuar.")
            return teksti
        except ocr.OcrMungon as e:
            raise NukLexohet(
                f"PDF-ja duket e skanuar: {gjithsej} shkronja ne {n} faqe, "
                f"dhe OCR-i nuk eshte gati: {e}")
        except ImportError:
            raise NukLexohet(
                f"PDF-ja duket e skanuar: {gjithsej} shkronja ne {n} faqe. "
                f"Mungon ocr.py.")

    # PDF text comes out one VISUAL line at a time with no blank line between
    # paragraphs. Splitting on blank lines therefore glues "Neni 5" onto the
    # sentence above it and the clause splitter stops seeing any headings at
    # all: 21 clauses became 4. So rebuild wrapped paragraphs instead, and
    # always let a heading start its own block.
    blocks = []
    for t in faqe:
        for raw in t.split("\n"):
            line = raw.strip()
            if not line:
                continue
            if TITULL.match(line) or not blocks or re.search(r"[.;:]$", blocks[-1]):
                blocks.append(line)
            else:
                blocks[-1] += " " + line     # a wrapped continuation
    return _pastro(blocks)


# ---------------------------------------------------------------- hyrja
def lexo(path):
    """path -> plain text. Raises NukLexohet with a reason a human can act on."""
    p = Path(path)
    OCR_META.clear()
    if not p.exists():
        raise NukLexohet(f"Skedari nuk u gjet: {p}")
    suf = p.suffix.lower()
    if suf == ".txt":
        return p.read_text(encoding="utf-8", errors="replace")
    if suf == ".docx":
        return _docx(p)
    if suf == ".pdf":
        return _pdf(p)
    if suf == ".doc":
        raise NukLexohet(
            "Formati i vjeter .doc nuk lexohet. Hape me Word dhe ruaje si .docx.")
    raise NukLexohet(f"Format i panjohur: {suf}. Pranohen .docx, .pdf, .txt")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Perdorim: python3 ingest.py <skedari> [dalja.txt]")
        raise SystemExit(2)
    try:
        txt = lexo(sys.argv[1])
    except NukLexohet as e:
        print(f"[NUK LEXOHET] {e}")
        raise SystemExit(1)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(txt, encoding="utf-8")
        print(f"U shkrua {sys.argv[2]}  ({len(txt)} shkronja)")
    else:
        sys.stdout.write(txt)
