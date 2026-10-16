#!/usr/bin/env python3
"""
Strict scoring.

The old version asked "did it flag the right clause". That is too generous:
a system can flag the right clause while citing a law that does not support
the finding, and a lawyer checking the citation would catch it instantly.

This version asks "did it flag the right clause AND cite a law that actually
governs it", and reports anything else as a HOLLOW catch.
"""
import json, sys
from pathlib import Path
from pipeline import run

src = sys.argv[1] if len(sys.argv) > 1 else "kontrata_test_01.txt"
mode = sys.argv[2] if len(sys.argv) > 2 else "free"
corpus_name = sys.argv[3] if len(sys.argv) > 3 else "kodi_punes"
corpus_file = corpus_name + "_flagged.json"
key = json.load(open(Path(src).stem + ".key.json", encoding="utf-8"))

print(f"MODE: {mode}")
clauses, kept, dropped, meta = run(src, mode=mode, corpus=corpus_file)


def base(a):
    return str(a).split("/")[0].strip()


# ---- ground truth -----------------------------------------------------
truth = {}
for k in key["klauzolat"]:
    exp = set()
    for sh in k.get("shkeljet", []) or []:
        for n in sh["nenet"]:
            exp.add(base(n))
    truth[k["neni_kontrates"]] = {"bad": k["ka_konflikt"], "exp": exp,
                                  "why": k.get("arsyeja", "")}

# ---- predictions ------------------------------------------------------
pred = {}
for f in kept:
    c = f["klauzola"]
    cited = base(f["verifikimi"].get("neni_zgjidhur", f["neni_ligjit"]))
    pred.setdefault(c, []).append(cited)

# ---- classify ---------------------------------------------------------
solid, hollow, fp, miss = [], [], [], []
for n, t in sorted(truth.items()):
    got = pred.get(n)
    if t["bad"]:
        if not got:
            miss.append(n)
        elif t["exp"] & set(got):
            solid.append(n)
        else:
            hollow.append((n, sorted(t["exp"]), sorted(set(got))))
    else:
        if got:
            fp.append((n, sorted(set(got))))

nbad = sum(1 for t in truth.values() if t["bad"])

print()
print("=" * 70)
print("PER KLAUZOLE")
print("=" * 70)
for n, t in sorted(truth.items()):
    got = sorted(set(pred.get(n, [])))
    if t["bad"]:
        if n in solid:
            tag, note = "OK      ", f"cited {got}"
        elif any(n == h[0] for h in hollow):
            tag, note = "HOLLOW  ", f"cited {got}, needed one of {sorted(t['exp'])}"
        else:
            tag, note = "MISSED  ", f"needed one of {sorted(t['exp'])}"
    else:
        tag, note = ("FALSE+  ", f"flagged with {got}, clause is CLEAN") if got \
                    else ("clean   ", "")
    if note:
        print(f"  [{tag}] klauzola {n:>2}: {note}")

print()
print("=" * 70)
print("REZULTATI")
print("=" * 70)
print(f"  solid catches (right clause AND right law) : {len(solid)}/{nbad}")
print(f"  hollow catches (right clause, wrong law)   : {len(hollow)}")
print(f"  false alarms on clean clauses              : {len(fp)}")
print(f"  missed entirely                            : {len(miss)}")
print()
print(f"  STRICT RECALL    {len(solid)}/{nbad} = {len(solid)/nbad:.0%}")
denom = len(solid) + len(hollow) + len(fp)
print(f"  STRICT PRECISION {len(solid)}/{denom} = {len(solid)/denom:.0%}" if denom
      else "  STRICT PRECISION n/a")

# every individual citation, not just every clause: a correctly flagged clause
# can still carry a second citation that does not support anything, and that is
# one more thing a lawyer opens and finds empty
cit_ok = cit_all = 0
for n, cited in pred.items():
    exp = truth.get(n, {}).get("exp", set())
    for c in cited:
        cit_all += 1
        cit_ok += (c in exp)
print(f"  CITATION ACCURACY {cit_ok}/{cit_all} = "
      f"{cit_ok/cit_all:.0%}" if cit_all else "  CITATION ACCURACY n/a")

if hollow:
    print()
    print("  HOLLOW detail (a lawyer would check these and find nothing):")
    for n, exp, got in hollow:
        print(f"    klauzola {n}: cited {got}, but the rule lives in {exp}")

if dropped:
    print()
    print("  bllokuar nga verifikuesi:")
    for d in dropped:
        print(f"    klauzola {d['klauzola']} Neni {d['neni_ligjit']}: "
              f"{d['verifikimi']['verdict']}")

errs = meta.get("deshtime", [])
if errs:
    print()
    print("!" * 70)
    print(f"  KUJDES: {len(errs)} pyetje nuk morren pergjigje (rate limit, JSON i prishur).")
    print("  Keto numerohen si 'pa konflikt', pra REKALLI MESIPER ESHTE ME I ULET SE REALITETI.")
    print("  Nese ky numer eshte > 2, mos e krahaso kete model me te tjeret. Rilesho.")
    for e in errs[:8]:
        ref = f"{e['klauzola']}" + (f".{e['nenshtese'].split('.')[-1]}" if e.get("nenshtese") else "")
        print(f"    klauzola {ref}: {e['gabim']}")
    if len(errs) > 8:
        print(f"    ... edhe {len(errs)-8} te tjera")
    print("!" * 70)
else:
    print("\n  (asnje deshtim teknik - rezultati eshte i krahasueshem)")
