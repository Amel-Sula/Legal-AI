#!/usr/bin/env python3
"""Does verification still hold when the corpus holds every code?

The danger the multi-law corpus introduces is not that something stops working
loudly. It is that "Neni 5" stops meaning one thing. If the verifier is not
scoped by law, a Civil Code citation gets checked against the Labour Code's
Neni 5, and the outcome is either a correct finding thrown away or an invented
one let through. Both are invisible in the output.

    python3 test_shumeligje.py
"""
import korpusi
from verify import Verifier

meta, units = korpusi.ngarko()
V = Verifier(units=units)
KP = korpusi.gjej_ligjin(units, r"kodi\s+i\s+punes|kodin\s+e\s+punes") or "Kodi i Punës"
ligjet = sorted(V.pika)
print(f"{meta['numri_njesive']} njësi, {len(ligjet)} ligje\n")

ok = n = 0


def provo(emri, kusht):
    global ok, n
    n += 1
    ok += bool(kusht)
    print(f"  [{'PASS' if kusht else 'FAIL'}] {emri}")


# ---- 1. the Labour Code must behave exactly as it did before -------------
v = V.check("150", "Palët parashikojnë me shkrim një periudhë prove jo më "
                   "shumë se tre muaj.", KP)
provo("citim i vertete i Kodit te Punes -> OK", v["verdict"] in ("OK", "OK_NORMALIZED"))
provo("drejtimi i Nenit 150 lexohet nga korpusi",
      V.drejtimi("150", KP) == "maksimal")

# ---- 2. a provision of another law, verified against its own law ---------
tjeter = next((L for L in ligjet if L != KP), None)
if tjeter:
    # take a real article of that law straight from the corpus
    njesi = next(u for u in units
                 if u.get("titulli_ligjit") == tjeter and len(u["teksti"]) > 80)
    citim = njesi["teksti"][:70]
    v = V.check(njesi["neni"], citim, tjeter)
    provo(f"citim i vertete i '{tjeter[:28]}' -> OK",
          v["verdict"] in ("OK", "OK_NORMALIZED"))

    # ---- 3. the same quote attributed to the WRONG LAW must be blocked ---
    v = V.check(njesi["neni"], citim, KP)
    provo("i njejti citim i ngarkuar Kodit te Punes -> BLLOKOHET",
          v["verdict"] not in ("OK", "OK_NORMALIZED"))

    # ---- 4. and an article number that exists in BOTH laws must not be
    #         resolved to the wrong one ----------------------------------
    te_dyja = (set(V.nene.get(KP, {}))
               & set(V.nene.get(tjeter, {})))
    if te_dyja:
        nr = sorted(te_dyja, key=lambda x: (len(x), x))[0]
        a = V._article_text(nr, KP)[1]
        b = V._article_text(nr, tjeter)[1]
        provo(f"Neni {nr} ekziston ne dy ligje dhe kthen tekste te ndryshme",
              a is not None and b is not None and a != b)

# ---- 5. a law that is NOT in the corpus must verify NOTHING -------------
# This is the regression test for a real bug: _ligjet_per fell back to
# searching every law when a title did not resolve, so a citation attributed
# to an unknown law was checked against all sixteen codes, matched somewhere,
# and came back OK. The check passed while verifying nothing. An unknown law
# must now be a refusal, not a wider search.
v = V.check("150", "Palët parashikojnë me shkrim një periudhë prove jo më "
                   "shumë se tre muaj.", "Kodi i Hapesires Kozmike")
provo("ligj i panjohur -> LIGJ_I_PANJOHUR, jo OK",
      v["verdict"] == "LIGJ_I_PANJOHUR")
provo("ligj i panjohur nuk kthen drejtim",
      V.drejtimi("150", "Kodi i Hapesires Kozmike") is None)

print(f"\n{ok}/{n}")
raise SystemExit(0 if ok == n else 1)
