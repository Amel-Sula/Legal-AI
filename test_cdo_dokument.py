#!/usr/bin/env python3
"""Does the chain work on a document that is NOT an employment contract?

This is the claim the wiring has to earn, and it is testable without a GPU:
everything except the model's choice is deterministic. So this runs a lease
contract through corpus loading, law selection, retrieval and verification, and
asserts at each step that the Civil Code -- not the Labour Code -- is what the
document got read against.

The model step is the only one left out. Run it for real with:

    python3 analizo.py kontrata_qiraje.txt

    python3 test_cdo_dokument.py
"""
from pathlib import Path

import korpusi
import retrieve
from pipeline import subpoints, retrieve_for_clause
from split_clauses import split
from verify import Verifier

FIKSTURA = "kontrata_qiraje.txt"
teksti = Path(FIKSTURA).read_text(encoding="utf-8")

meta, te_gjitha = korpusi.ngarko()

# the names these two laws carry in THIS corpus, whatever spelling the PDF
# title block gave them
CIVIL = korpusi.gjej_ligjin(te_gjitha, r"kodi\s+civil|kodin\s+civil")
PUNES = korpusi.gjej_ligjin(te_gjitha, r"kodi\s+i\s+punes|kodin\s+e\s+punes")
if not CIVIL:
    print("Kodi Civil nuk ndodhet ne korpus. Lesho: python3 shto_ligj.py ~/ligjet/Kodet")
    raise SystemExit(1)

idx_plote = retrieve.BM25(te_gjitha)
units, ligjet = korpusi.per_dokument(te_gjitha, teksti, idx=idx_plote)
idx = retrieve.BM25(units)
V = Verifier(units=te_gjitha)

ok = n = 0


def provo(emri, kusht, detaj=""):
    global ok, n
    n += 1
    ok += bool(kusht)
    print(f"  [{'PASS' if kusht else 'FAIL'}] {emri}" + (f"  {detaj}" if detaj else ""))


print(f"ligjet e zgjedhura: {', '.join(ligjet)}")
print(f"Kodi Civil ne korpus: {CIVIL!r}\n")

# ---- 1. the document must choose its own law ----------------------------
provo("kontrata e qirase zgjedh Kodin Civil", CIVIL in ligjet)
provo("NUK zgjedh Kodin e Punes", PUNES not in ligjet,
      "(nje kontrate qiraje nuk lexohet kundrejt Kodit te Punes)")

# ---- 2. the governing article must actually be retrieved ---------------
# Neni 803: "Qiraja nuk mund të lidhet për një kohë më të gjatë se tridhjetë
# vjet". The contract is for forty. This is the whole product in one line.
clauses = split(teksti)
kohezgjatja = next(c for c in clauses if "Kohezgjatja" in c["titulli"])
gjetur = []
for sp in subpoints(kohezgjatja):
    gjetur += [(u["neni"], u.get("titulli_ligjit"))
               for u in retrieve_for_clause(idx, sp, 8)]
provo("Neni 803 i Kodit Civil del ne kandidatet e klauzoles 2",
      ("803", CIVIL) in gjetur,
      f"kandidatet: {[a for a, _ in gjetur][:8]}")

# ---- 3. verification must work against the Civil Code -----------------
_k, teksti_803 = V._article_text("803", CIVIL)
provo("Neni 803 lexohet nga korpusi", bool(teksti_803))
if teksti_803:
    citim = teksti_803[:90]
    provo("citimi i Nenit 803 verifikohet kundrejt Kodit Civil",
          V.check("803", citim, CIVIL)["verdict"] in ("OK", "OK_NORMALIZED"))
    provo("i njejti citim i ngarkuar Kodit te Punes bllokohet",
          V.check("803", citim, PUNES)["verdict"]
          not in ("OK", "OK_NORMALIZED"))

# ---- 4. the direction of the limit must come from the Civil Code ------
provo("drejtimi i Nenit 803 = maksimal",
      V.drejtimi("803", CIVIL) == "maksimal")

# ---- 5. the arithmetic gate must fire on the Civil Code too ----------
#         40 years against a 30-year ceiling is a breach; 20 is not.
shkelje = {"ka_konflikt": True, "ligji": CIVIL, "neni_ligjit": "803",
           "vlera_kontrates": "40 vjet", "vlera_ligjore": "tridhjete vjet"}
e_ligjshme = {**shkelje, "vlera_kontrates": "20 vjet"}
provo("40 vjet kundrejt kufirit 30 vjet kalon porten", V.numeric_check(shkelje)[0])
provo("20 vjet kundrejt kufirit 30 vjet bllokohet", not V.numeric_check(e_ligjshme)[0],
      V.numeric_check(e_ligjshme)[1])

# ---- 6. a quote the model invented must still be caught --------------
provo("citim i trilluar bllokohet",
      V.check("803", "Qiraja nuk mund te lidhet per me shume se pese vjet.",
              CIVIL)["verdict"] not in ("OK", "OK_NORMALIZED"))

# ---- 7. "no figure" must block a numeric breach and spare a prohibition ----
# Under value-by-reference the model returns no figure when the clause has no
# violating one. Against Neni 83 ("jo më shumë se 40 orë") that must hold the
# finding back, or clause 10 of the BIOCHECK contract -- 40 hours a week, which
# equals the maximum -- gets printed as a breach on the citation alone. Against
# Neni 818 of the Civil Code, a prohibition carrying no number, the same
# missing figure must NOT block it: that breach is real.
provo("Neni 83 njihet si kufi numerik", V.kufi_numerik("83", PUNES))
provo("Neni 818 NUK njihet si kufi numerik", not V.kufi_numerik("818", CIVIL))

pa_numer = {"ka_konflikt": True, "ligji": PUNES, "neni_ligjit": "83",
            "vlera_kontrates": "-", "vlera_ligjore": "jo me shume se 40 ore",
            "citim": "x", "tema": "koha"}
_kept, _dropped = V.filter_findings(
    [dict(pa_numer)], "Punemarresi punon sipas orarit te caktuar nga punedhenesi.")
provo("pa vlere, klauzola pa numer -> mbahet",
      bool(_dropped) and _dropped[0]["verifikimi"]["verdict"]
      == "PA_VLERE_KUNDREJT_KUFIRIT")

# ---- 8. the figure comes from the CLAUSE when the model names none --------
# Blocking every figureless finding cost a true breach: clause 7 of the lease
# sets a one-day termination notice against Neni 1023's ten-day minimum, and
# the clause states the figure plainly even when the model does not name it.
_k3, t1023 = V._article_text("1023", CIVIL)
if t1023:
    njoftimi = {"ka_konflikt": True, "ligji": CIVIL, "neni_ligjit": "1023",
                "vlera_kontrates": "-", "vlera_ligjore": "te pakten 10 dite",
                "citim": t1023[:90], "tema": "njoftimi"}
    _kept, _dropped = V.filter_findings(
        [dict(njoftimi)],
        "Secila pale mund ta zgjidhe kontraten me njoftim paraprak prej 1 (nje) dite.")
    provo("1 dite kundrejt minimumit 10 dite -> kalon, me vleren e klauzoles",
          bool(_kept) and _kept[0].get("vlera_nga_klauzola") is True,
          f"vlera: {_kept[0].get('vlera_kontrates')!r}" if _kept else "")

# and the same mechanism must still refuse what is NOT a breach
for teksti_kl, vl, nen, pritet in (
        ("Koha javore e punes eshte 40 ore ne jave.", "jo me shume se 40 ore", "83",
         "40 = 40 nuk raportohet"),
        ("oresh shtese jo me shume se 8 ore ne jave.", "48 ore", "90/2",
         "8 nen kufirin 48 nuk raportohet")):
    _k4, txt = V._article_text(nen, PUNES)
    f = {"ka_konflikt": True, "ligji": PUNES, "neni_ligjit": nen,
         "vlera_kontrates": "-", "vlera_ligjore": vl, "citim": (txt or "")[:88],
         "tema": "koha"}
    _kept, _dropped = V.filter_findings([dict(f)], teksti_kl)
    provo(pritet, not _kept and bool(_dropped),
          _dropped[0]["verifikimi"]["detaj"][:60] if _dropped else "U PUBLIKUA")

_k2, t818 = V._article_text("818", CIVIL)
ndalim = {"ka_konflikt": True, "ligji": CIVIL, "neni_ligjit": "818",
          "vlera_kontrates": "pa pelqimin", "vlera_ligjore": "-",
          "citim": (t818 or "")[:80], "tema": "nenqiraja"}
_kept, _dropped = V.filter_findings(
    [dict(ndalim)], "Qiramarresi ka te drejte te transferoje kontraten pa pelqim.")
provo("pa vlere kundrejt ndalimi -> kalon", bool(_kept))

print(f"\n{ok}/{n}")
raise SystemExit(0 if ok == n else 1)
