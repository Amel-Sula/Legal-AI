#!/usr/bin/env python3
"""Why did THIS clause come out the way it did?

score.py gives a number. A number cannot say whether a lost finding was lost
by retrieval, by the model, or by one of the gates in verify.py -- and those
three have completely different fixes. Guessing which one cost an afternoon
and a wrong diagnosis, so this prints the whole chain for one clause:

  the candidates retrieval produced
  the RAW answer the model returned, before anything touches it
  every gate in order, with the reason each one gave

    python3 shqyrto.py kontrata_biocheck.txt 10
    python3 shqyrto.py kontrata_biocheck.txt 10 16 17
    python3 shqyrto.py kontrata_biocheck.txt 10 --sa 3

`--sa 3` asks the same question three times. If the three answers differ, the
server is not deterministic and no single score.py run means anything -- that
has to be settled before any other conclusion is drawn from a number.
"""
import json
import sys
from pathlib import Path

import korpusi
import llm
import retrieve
from pipeline import resolve_by_id, retrieve_for_clause, subpoints, zgjidh_shabllonin
from split_clauses import split
from verify import Verifier, parse_qty

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args:
    print("Perdorim: python3 shqyrto.py <fikstura.txt> [nr klauzole ...] [--sa N]")
    raise SystemExit(2)

sa = 1
if "--sa" in sys.argv:
    sa = int(sys.argv[sys.argv.index("--sa") + 1])
    args = [a for a in args if a != str(sa)]

burimi = Path(args[0])
duam = {int(x) for x in args[1:]} or None
teksti = burimi.read_text(encoding="utf-8")

meta, te_gjitha = korpusi.ngarko()
idx_plote = retrieve.BM25(te_gjitha)
units, ligjet = korpusi.per_dokument(te_gjitha, teksti, idx=idx_plote)
idx = idx_plote if len(units) == len(te_gjitha) else retrieve.BM25(units)
V = Verifier(units=te_gjitha)
llm.vendos_ligjet(ligjet)

print(f"ligjet: {', '.join(ligjet)}   |  korpusi: {meta['numri_njesive']} njesi")
print(f"modeli: {llm.MODEL}  @ {llm.API_URL}")
print(f"prompti: {'ME EMRIN E LIGJIT (LLM_LIGJI=1)' if llm.ME_LIGJIN else 'standard (80%)'}")
print()

for c in split(teksti):
    if c["nr"] == 0 or (duam and c["nr"] not in duam):
        continue
    print("=" * 78)
    print(f"KLAUZOLA {c['nr']}: {c['titulli']}")
    print("=" * 78)

    for sp in subpoints(c):
        kand = retrieve_for_clause(idx, sp, 8)
        print(f"\n--- {sp.get('nenshtese') or 'e plote'} ---")
        print(f"TEKSTI: {sp['teksti'][:300]}")
        print(f"\nKANDIDATET ({len(kand)}):")
        for i, u in enumerate(kand, 1):
            flag = "⚖" if u.get("i_kontrollueshem") else " "
            ref = f"{u['neni']}/{u['pika']}" if u.get("pika") else u["neni"]
            print(f"  C{i} {flag} Neni {ref:<8} {u['teksti'][:88]}")

        for prova in range(sa):
            raw = llm.ask(sp, kand)
            etiketa = f"  [prova {prova+1}/{sa}]" if sa > 1 else ""
            print(f"\nPERGJIGJA E MODELIT{etiketa}:")
            if not any(f.get("ka_konflikt") for f in raw):
                print("  (pa shkelje)")
                if raw and raw[0].get("_gabim"):
                    print(f"  GABIM: {raw[0]['_gabim']}")
                continue
            for f in raw:
                if f.get("ka_konflikt"):
                    print(f"  {json.dumps({k: v for k, v in f.items() if not k.startswith('_')}, ensure_ascii=False)}")

            # now every gate, in the order pipeline.run applies them
            gjetjet = resolve_by_id([dict(f) for f in raw], kand)
            for f in gjetjet:
                if not f.get("ka_konflikt"):
                    print(f"  RRETHUAR: {f.get('_arsye_rrezimi')}")
                    continue
                f["drejtimi"] = V.drejtimi(f.get("neni_ligjit"), f.get("ligji"))
                ref = f"Neni {f['neni_ligjit']} ({f.get('ligji')})"
                print(f"\n  PORTAT per {ref}:")
                print(f"    drejtimi nga korpusi : {f['drejtimi']}")
                print(f"    vlera_kontrates      : {f.get('vlera_kontrates')!r}"
                      f"  -> parse {parse_qty(f.get('vlera_kontrates'))}")
                print(f"    vlera_ligjore        : {f.get('vlera_ligjore')!r}"
                      f"  -> parse {parse_qty(f.get('vlera_ligjore'))}")

                ok1, pse1 = V.vlera_ne_klauzole(f.get("vlera_kontrates"), sp.get("teksti"))
                print(f"    1. vlera ne klauzole : {'KALON' if ok1 else 'BLLOKON'}"
                      f"{'' if ok1 else '  <- ' + pse1}")
                if not ok1:
                    continue
                ok2, pse2 = V.numeric_check(f)
                print(f"    2. aritmetika        : {'KALON' if ok2 else 'BLLOKON'}"
                      f"{'' if ok2 else '  <- ' + pse2}")
                if not ok2:
                    continue
                v = V.check(f.get("neni_ligjit"), f.get("citim"), f.get("ligji"))
                print(f"    3. citimi            : {v['verdict']}"
                      f"{'  <- ' + v['detaj'][:90] if v['detaj'] else ''}")
                if v["verdict"] in ("OK", "OK_NORMALIZED"):
                    print(f"    FJALIA: {zgjidh_shabllonin(f).format(**f)}")
    print()
