#!/usr/bin/env python3
"""Drop Albanian laws into a folder, run this, the corpus grows.

    python3 shto_ligj.py ~/ligjet

Reads every .pdf, .docx and .txt in the folder, works out which law each one
is from its own first page, splits it into articles and writes one combined
corpus. Re-running is safe: a law already present is replaced, not duplicated.

The unit is the ARTICLE, not the numbered point. 79% of Labour Code articles
carry numbered points; the Civil Code carries them in 2%. Every Albanian law
has "Neni N", so that is what the whole corpus can agree on.
"""
import re, json, sys, unicodedata, warnings
from pathlib import Path

warnings.filterwarnings("ignore")        # pypdf's crypto deprecation notice

import ingest


class NukLexohet(Exception):
    pass


def lexo_ligj(p):
    """Extraction for LAWS, which is not the same as for contracts.

    ingest.py rebuilds wrapped paragraphs, which is right for a contract and
    wrong here: it glues "Neni 3" onto the sentence above it and every article
    heading disappears. On the real Civil Code PDF that turned 1,132 articles
    into 2. Laws need the line breaks left as the page has them.

    Measured on the 202-page Civil Code:
        pypdf                  4.8s   1172 articles found
        pdfplumber layout     20.3s   1173
        pdfplumber plain      22.5s   1173
        pdfminer              11.2s   1142
    pypdf is four times faster and misses one article out of 1,173, so it goes
    first. pdfplumber is kept as a fallback for a document pypdf cannot split,
    and neither is run on a scan: the Customs implementing provisions PDF is
    180MB of images, and pdfplumber spends many minutes discovering that.
    """
    if p.suffix.lower() != ".pdf":
        return ingest.lexo(p)        # .docx and .txt are fine as they are

    from pypdf import PdfReader
    lexues = PdfReader(str(p))
    faqe = len(lexues.pages)
    t = "\n".join((f.extract_text() or "") for f in lexues.pages)

    if len(t.strip()) < 100 * max(faqe, 1):
        raise NukLexohet(
            f"duket e skanuar ({len(t.strip())} shkronja ne {faqe} faqe). "
            f"Duhet OCR, qe nuk mbeshtetet ende.")

    if not NENI.search(t):
        # pypdf found text but no article headings; the layout engine sometimes
        # recovers them on documents with unusual column structure.
        try:
            import pdfplumber
            with pdfplumber.open(str(p)) as pdf:
                t2 = "\n".join((f.extract_text(layout=True) or "") for f in pdf.pages)
            if NENI.search(t2):
                return t2
        except Exception:
            pass
    return t


KORPUSI = "korpus_ligjet.json"


# ------------------------------------------------------------- prejardhja
# WHERE A LAW CAME FROM, AND HOW OLD IT IS.
#
# Until now the corpus knew only the Labour Code's consolidation date, because
# its parser was hand-built; the other 242 laws carried nothing and the report
# printed one date and stayed silent on the rest. shkarko_qbz.py writes
# manifest.json with QBZ's own `modifiedAt` per file -- the authority's record
# of when it last republished that text, not a date this program guesses -- and
# it is attached here to every article parsed out of that file.
def gjej_manifestin(dosja: Path):
    """manifest.json sits at the root of the download, so walk up to it."""
    for d in [dosja] + list(dosja.parents)[:4]:
        p = d / "manifest.json"
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8")), d
            except (json.JSONDecodeError, OSError):
                return {}, d
    return {}, dosja


def prejardhja(man, rrenja_man, skedari: Path):
    """What the manifest says about this file, if anything."""
    try:
        rel = str(skedari.resolve().relative_to(rrenja_man.resolve()))
    except ValueError:
        rel = skedari.name
    hyrja = man.get(rel) or {}
    if not hyrja:
        # the manifest keys on the path at download time; fall back on the name
        hyrja = next((v for k, v in man.items()
                      if Path(k).name == skedari.name), {})
    return {
        "burimi": skedari.name,
        "qbz_modifikuar": (hyrja.get("qbz_modifikuar") or "")[:10],
        "shkarkuar": hyrja.get("shkarkuar") or "",
    }

NENI = re.compile(r"^[ \t]*Neni[ \t]+(\d+(?:[/-]\d+)?[a-zëç]?)[ \t]*$", re.M)

# "LIGJ Nr. 7850, datë 29.7.1994" / "LIGJ nr. 10 237, date 18.02.2010"
# "LIGJ" and "Nr. 7850, datë 29.7.1994" sit on separate lines in the real
# consolidated PDFs, so whitespace between them includes newlines.
KOKA = re.compile(r"LIGJ\s*(?:Nr\.?|nr\.?)?\s*([\d\s]{2,9}(?:/\d{2,4})?)\s*,?"
                  r"\s*(?:datë|date|dt\.?)\s*([\d./-]{6,12})", re.I)

# The law's own name: an all-caps block opening with PËR or KODI, which the
# page breaks over two or three lines and sprinkles with footnote digits
# ("PËR KODIN CIVIL TË" / "1" / "REPUBLIKËS SË SHQIPËRISË").
# The lookahead for whitespace is load-bearing. Without it, "PËR" also matches
# the first three letters of "PËRMBAJTJA", so the Customs implementing
# provisions were named after their own table of contents: "Përmbajtja
# Dispozitat Zbatuese Te Kodit Doganor".
EMRI = re.compile(r"^[ \t]*((?:P[ËE]R|KODI)(?=[ \t])[ \tA-ZËÇ]{4,}"
                  r"(?:\n[ \t]*[A-ZËÇ0-9][ \tA-ZËÇ0-9]{1,}[ \t]*)*)", re.M)

# Albanian title case keeps the linking words lowercase. str.title() does not
# know that and turns "KODI I PUNËS" into "Kodi I Punës", which then fails to
# match the name the Labour Code already carries in kodi_punes_flagged.json.
FJALE_VOGLA = {"i", "e", "të", "së", "dhe", "për", "me", "nga", "në", "mbi",
               "ose", "a", "as", "ndaj", "sipas", "mes"}
TITULLI = re.compile(r"[“\"'’]([^”\"'’]{10,160})[”\"'’]")


def _pastro_emrin(bllok):
    rreshtat = [re.sub(r"^\s*\d+\s*$", "", r).strip() for r in bllok.split("\n")]
    emri = " ".join(r for r in rreshtat if r)
    emri = re.sub(r"\s{2,}", " ", emri).strip(" .,")
    emri = re.sub(r"\s+\d{1,2}$", "", emri)      # a trailing footnote marker
    # and the same marker when the page glued it to the last word, which is how
    # the Civil Code came out named "...Të Republikës Së Shqipërisë1". That is
    # not cosmetic: the title is the key every citation is verified against, it
    # is printed in the report a lawyer reads, and a stray digit makes the same
    # code look like two different laws.
    emri = re.sub(r"(?<=[A-Za-zËËëÇç])\d{1,2}$", "", emri)
    if emri.isupper():
        fjalet = emri.title().split()
        emri = " ".join(f if i == 0 or f.lower() not in FJALE_VOGLA else f.lower()
                        for i, f in enumerate(fjalet))

    # The codes announce themselves in the subject form, "PËR KODIN CIVIL TË
    # REPUBLIKËS SË SHQIPËRISË". The name the code is known by is "Kodi Civil",
    # and it has to match the name the Labour Code already carries in
    # kodi_punes_flagged.json, or the Labour Code gets loaded a second time at
    # article level and competes with itself in retrieval.
    m = re.match(r"\s*p[ëe]r\s+kodin\s+(.+?)\s*$", emri, re.I)
    if m:
        pjesa = re.sub(r"\s+t[ëe]\s+republik.*$", "", m.group(1), flags=re.I)
        pjesa = re.sub(r"^e\s+", "i ", pjesa.strip(), flags=re.I)
        emri = "Kodi " + pjesa.strip(" .,")
    # and "KODI RRUGOR I REPUBLIKËS SË SHQIPËRISË" -> "Kodi Rrugor"
    emri = re.sub(r"^(Kodi\s+.+?)\s+(?:i|e|t[ëe])\s+Republik.*$", r"\1",
                  emri, flags=re.I)
    return emri.strip(" .,")

# Amendment footnotes sit between a heading and its body and are not law text.
FUSNOTE = re.compile(
    r"^\s*\d*\s*(?:Ligj|Vendim|Shtuar|Ndryshuar|Shfuqizuar)\b.{0,400}?"
    r"(?:shprehet|ndryshuar|shfuqizuar)\b.*?$", re.M | re.S)
CITAT = re.compile(r"^\s*[‘'’\"“].{0,600}?[’'\"”]\s*$", re.M | re.S)


def identifiko(teksti, emri_skedarit):
    """Who is this law? Ask the document first, fall back to the file name."""
    koka = teksti[:3000]
    m = KOKA.search(koka)
    nr = re.sub(r"\s+", "", m.group(1)) + "/" + m.group(2)[-4:] if m else None
    # A quoted phrase in the preamble is usually some OTHER law being cited.
    # The document's own name is a line reading "KODI ..." or "KODI I ...".
    vet = EMRI.search(koka)
    titulli = _pastro_emrin(vet.group(1)) if vet else None
    if not titulli:
        t = TITULLI.search(koka)
        titulli = t.group(1).strip() if t else None
    if not titulli:
        # file names like "LIGJ_nr._7850-1994_-KC-i_perditesuar.pdf"
        titulli = re.sub(r"[_\-]+", " ", Path(emri_skedarit).stem).strip()
    return nr or Path(emri_skedarit).stem, titulli


def pastro(t):
    t = unicodedata.normalize("NFC", t)
    t = FUSNOTE.sub(" ", t)
    t = CITAT.sub(" ", t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{2,}", "\n", t).strip()


# A COMPILATION ("Përmbledhje Legjislacioni") is one PDF holding dozens of
# separate laws. Loaded as a single law it destroys the one property the
# product is sold on: "Neni 5" would name five different provisions inside the
# same file, so no citation in it could be verified. Hence it is split here or
# refused outright -- never loaded whole.
#
# The split point is a law's own title block, which in these documents is the
# word LIGJ alone on a line, uppercase, followed by its number and date. The
# looser KOKA above cannot be used for this: it is case-insensitive and matches
# citations of OTHER laws inside amendment footnotes ("me ligj nr. 10, datë
# ..."), which appear hundreds of times in a consolidated text and would shred
# one law into hundreds of fragments.
KOKA_FILLIM = re.compile(
    r"^[ \t]*LIGJ[ \t]*\n?[ \t]*(?:Nr\.?|NR\.?)?[ \t]*"
    r"([\d\s]{2,9}(?:/\d{2,4})?)[ \t]*,?[ \t]*(?:datë|date|dt\.?)[ \t]*"
    r"([\d./-]{6,12})", re.M)

MIN_NENE_PER_LIGJ = 3

# A law announces itself in one of a few ways. Anything else is a parse
# failure, and a parse failure must not be loaded under whatever string it
# happened to grab. Four compilation PDFs were about to enter the corpus named
# "Nikolla Jorgo" -- the compilation's editor -- carrying 922, 507, 324 and 14
# articles drawn from dozens of different laws under that one name. "Neni 5"
# would then have named dozens of provisions and no citation from any of them
# could have been verified, which is the one property this product sells.
EMER_LIGJI = re.compile(
    r"^\s*(p[ëe]r\b|kod(i|in)\b|kushtetut|statusi\b|ligj(i|e)?\b|"
    r"dispozita\b|rregullore)", re.I)

# "Paketa e Ligjeve ..." is a package of laws by definition, never one law, so
# it is refused however well-formed the name looks.
EMER_SHUMESH = re.compile(r"^\s*(paket|p[ëe]rmbledh|tekst(e|i)\b)", re.I)

# Court-decision collections are not statutes. Their "Neni N" are articles of
# the Convention quoted inside a judgment, so loading them makes retrieval
# offer "Neni 6" of a case digest as though it were Albanian law. Six files in
# the library are these. Rename a file to override.
JO_LIGJ = re.compile(r"vendime|vendimeve|gjykat[ae]s|jurisprudenc", re.I)


def ndaj_permbledhjen(teksti):
    """One text in, one segment per law out. Empty list = not a compilation.

    A header only counts if real articles follow it before the next header.
    That single rule is what separates a compilation from a consolidated law
    whose preamble happens to quote another law's number.
    """
    pozicionet = [m.start() for m in KOKA_FILLIM.finditer(teksti)]
    if len(pozicionet) < 2:
        return []
    kufijte = pozicionet + [len(teksti)]
    segmente = []
    for a, b in zip(kufijte, kufijte[1:]):
        seg = teksti[a:b]
        if len(NENI.findall(seg)) >= MIN_NENE_PER_LIGJ:
            segmente.append(seg)
    return segmente if len(segmente) >= 2 else []


# The last article of a chapter runs straight into the next chapter's heading,
# because "Neni N" is the only boundary the splitter knows and a heading is not
# one. Neni 1023 of the Civil Code therefore ended with "KREU XVIII / KONTRATAT
# BANKARE / A. Depozitat bankare" -- and that text was quoted to a lawyer as
# part of the provision the contract allegedly breached. 128 of 1,682 articles
# carried a foreign heading this way in a two-code corpus.
#
# Uppercase and at the start of a line, so a sentence mentioning "kreu" in
# passing is untouched. The cut is made only when what remains still clears the
# same 25-character bar ndaj() uses to keep an article at all -- tied to that
# threshold rather than to a number picked by feel, which is how a first
# attempt at this silently declined to cut a short article.
KREU_TJETER = re.compile(
    r"\n[ \t\x0c]*(?:KREU|SEKSIONI|PJESA|TITULLI|KAPITULLI)\b.*$",
    re.S)


def _hiq_kreun(txt):
    m = KREU_TJETER.search(txt)
    if not m:
        return txt
    mbetja = txt[:m.start()].rstrip()
    return mbetja if len(mbetja) >= 25 else txt


def ndaj(teksti, ligji, titulli, prej=None):
    pjeset = NENI.split(teksti)
    out = []
    for nr, trup in zip(pjeset[1::2], pjeset[2::2]):
        txt = _hiq_kreun(pastro(trup))
        if len(txt) < 25:
            continue
        out.append({"ligji": ligji, "titulli_ligjit": titulli,
                    "neni": nr, "teksti": txt[:4000], **(prej or {})})
    return out


def kryesore(dosja, prove=False):
    dosja = Path(dosja)
    korpusi = Path(KORPUSI)
    ekzistues = json.loads(korpusi.read_text(encoding="utf-8")) if korpusi.exists() else []
    sipas_ligjit = {}
    refuzuar, perplasje = [], []
    # Which laws THIS run has written. The smaller-wins rule below belongs to
    # collisions inside one run -- two different compilations claiming the same
    # law -- and must not apply to a law carried in from the corpus on disk: a
    # re-run after a parser change has to refresh it, and refreshing does not
    # change the article COUNT, only the text. Without this distinction every
    # compilation reported "asnje ligj i vlefshem" on the second run and the
    # chapter-heading fix never reached any of them.
    nga_ky_leshim = set()
    # WHAT WENT WRONG, COUNTED. Without this the loop printed one GABIM line per
    # file and then a healthy 243-law listing read off the corpus already on
    # disk, so a run in which every single PDF failed looked exactly like a run
    # that worked.
    gabime, mungon = {}, set()
    for n in ekzistues:
        sipas_ligjit.setdefault(n["ligji"], []).append(n)

    man, rrenja_man = gjej_manifestin(dosja)
    if man:
        print(f"manifesti: {len(man)} skedare me date QBZ ({rrenja_man})")
    else:
        print("pa manifest: ligjet nuk do mbajne date QBZ. "
              "Lesho shkarko_qbz.py per ta ndertuar.")

    skedaret = sorted(p for p in dosja.iterdir()
                      if p.suffix.lower() in (".pdf", ".docx", ".txt"))
    if not skedaret:
        print(f"Asnje .pdf/.docx/.txt ne {dosja}")
        return

    for i, p in enumerate(skedaret, 1):
        mb = p.stat().st_size / (1024 * 1024)
        print(f"  ({i}/{len(skedaret)}) {p.name[:56]:<58} {mb:>6.1f} MB ... ",
              end="", flush=True)
        if JO_LIGJ.search(p.stem):
            print("KALUAR (vendime gjykate, jo legjislacion)")
            continue
        try:
            teksti = lexo_ligj(p)
        except (ingest.NukLexohet, NukLexohet) as e:
            print(f"KALUAR ({e})")
            continue
        except Exception as e:
            print(f"GABIM ({type(e).__name__}: {str(e)[:50]})")
            if isinstance(e, ModuleNotFoundError):
                mungon.add(e.name or "?")
            gabime[type(e).__name__] = gabime.get(type(e).__name__, 0) + 1
            continue
        # A compilation first: several laws in one file, each loaded under its
        # own number, or the file is refused.
        segmente = ndaj_permbledhjen(teksti)
        if segmente:
            print(f"PERMBLEDHJE: {len(segmente)} ligje")
            u_shtuan = 0
            for seg in segmente:
                ligji, titulli = identifiko(seg, p.name)
                nenet = ndaj(seg, ligji, titulli, prejardhja(man, rrenja_man, p))
                if not nenet:
                    continue
                if ligji in nga_ky_leshim:
                    # THE SAME LAW, TWO DIFFERENT ARTICLE COUNTS.
                    #
                    # Law 8626/2000 came out of one compilation with 22
                    # articles and out of another with 198. The longer one is
                    # not the more complete one: it is the one whose split ran
                    # past the end of the law and swallowed the next law's
                    # articles. Keeping it would file another law's Neni 150 as
                    # this law's -- a citation that verifies against the wrong
                    # text, which is worse than a missing article. So the
                    # smaller extraction wins and the conflict is reported.
                    e_vjeter = len(sipas_ligjit[ligji])
                    if abs(e_vjeter - len(nenet)) > 2:
                        perplasje.append((ligji, titulli, e_vjeter, len(nenet)))
                    if e_vjeter <= len(nenet):
                        continue
                shenje = "+" if ligji not in sipas_ligjit else "~"
                if not prove:
                    sipas_ligjit[ligji] = nenet
                nga_ky_leshim.add(ligji)
                u_shtuan += 1
                print(f"        {shenje} {len(nenet):>5} nene  "
                      f"{titulli[:46]:<48} {ligji}")
            if not u_shtuan:
                print("        (asnje ligj i vlefshem)")
            continue

        ligji, titulli = identifiko(teksti, p.name)
        nenet = ndaj(teksti, ligji, titulli, prejardhja(man, rrenja_man, p))
        if not nenet:
            print("KALUAR (asnje 'Neni N' nuk u gjet)")
            continue
        if not EMER_LIGJI.match(titulli or "") or EMER_SHUMESH.match(titulli or ""):
            print(f"REFUZUAR: '{titulli[:40]}' nuk duket emer ligji. "
                  f"{len(nenet)} nene nga ndoshta shume ligje nen nje emer -> "
                  f"citimet nuk do verifikoheshin.")
            refuzuar.append((p.name, titulli, len(nenet)))
            continue
        i_ri = ligji not in sipas_ligjit
        if not prove:
            sipas_ligjit[ligji] = nenet        # replace, never duplicate
        nga_ky_leshim.add(ligji)
        print(f"{'shtuar' if i_ri else 'rifreskuar'}: {len(nenet)} nene  "
              f"({titulli[:42]}, {ligji})")

    if mungon:
        print(f"\nMUNGON NJE LIBRARI: {', '.join(sorted(mungon))}")
        print("Asnje PDF nuk u lexua dot. Ndoshta po leshon pa venv-in. Lesho:")
        print(f"   source ~/pkg/.venv/bin/activate     # ose ku e ke venv-in")
        print(f"   pip install {' '.join(sorted(mungon))}")
    elif gabime:
        print(f"\nGABIME: " + ", ".join(f"{k} x{v}" for k, v in gabime.items()))

    if not nga_ky_leshim:
        # NOTHING WAS PARSED. STOP HERE.
        #
        # The listing below is read off korpus_ligjet.json, which is whatever a
        # PREVIOUS run left on disk. Printing it after a run that parsed zero
        # files announced "243 ligje, 19126 nene" as though the run had
        # succeeded -- the exact false reassurance this program exists to
        # prevent, pointed at its own operator. A run that achieved nothing
        # says so and writes nothing.
        print(f"\nASNJE LIGJ NUK U PARSUA NE KETE LESHIM.")
        print(f"{KORPUSI} NUK u shkruar; mbeti si ishte "
              f"({len(ekzistues)} nene nga me pare).")
        print("Rregullo gabimin me lart dhe rilesho. Mos vazhdo me "
              "kontrollo_statusin.py:\nnuk ka date te re per te krahasuar.")
        return

    if refuzuar:
        print(f"\nREFUZUAR {len(refuzuar)} skedare (emer ligji i panjohur):")
        for emri, tit, sa in refuzuar:
            print(f"   {emri[:46]:<48} '{(tit or '')[:26]}'  {sa} nene")
    if perplasje:
        print(f"\nPERPLASJE: i njejti ligj me numra nenesh te ndryshme. "
              f"U mbajt i vogli (i madhi ka kapur tepër):")
        for nr, tit, a, b in perplasje:
            print(f"   {nr:<14} {(tit or '')[:34]:<36} {a} nene  vs  {b} nene")

    gjithe = [n for v in sipas_ligjit.values() for n in v]
    if prove:
        print(f"\n[PROVE] Asgje nuk u shkruar. {KORPUSI} mbeti si ishte.")
        print("Shiko listen me lart: emrat e ligjeve dhe numri i neneve.")
        print("Nese duken sakte, lesho te njejten komande pa --prove.")
        return
    korpusi.write_text(json.dumps(gjithe, ensure_ascii=False), encoding="utf-8")
    print(f"\n{KORPUSI}: {len(sipas_ligjit)} ligje, {len(gjithe)} nene gjithsej.")
    for l, v in sorted(sipas_ligjit.items(), key=lambda kv: -len(kv[1])):
        print(f"   {v[0]['titulli_ligjit'][:52]:<54} {len(v):>5} nene")
    print("\nTani lesho:  python3 mat_kerkimin.py   "
          "(a i prishi gje shtimi renditjen)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("Perdorim: python3 shto_ligj.py <dosja-me-ligjet> [--prove]")
        print("  --prove : vetem trego cfare do shtohej, pa shkruar asgje.")
        print("            Perdore GJITHMONE here e pare me permbledhjet.")
        raise SystemExit(2)
    kryesore(args[0], prove="--prove" in sys.argv)
