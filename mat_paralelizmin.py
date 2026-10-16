#!/usr/bin/env python3
"""How many lawyers can this one machine serve at the same time.

    python3 mat_paralelizmin.py                       # 1, 2, 4, 8 njekohesisht
    python3 mat_paralelizmin.py kontrata_qiraje.txt 1 2 4 8 16

The product was sold on "several firms can use it at once" and then web.py
serialised every upload behind one lock, because nobody had measured what
happens without it. This measures it, on the real GPU, with the real corpus,
end to end through the same entry point the web page calls.

THREE NUMBERS, AND THEY ANSWER DIFFERENT QUESTIONS.

  koha e korpusit   CPU, once per process. Loading 19,475 provisions and
                    building the BM25 index. Shared cache now, so this is paid
                    once and not per document -- measured separately because
                    it is the one cost that is fixable in software.

  vonesa            how long ONE lawyer waits. This is the number he feels.
                    It grows with concurrency because vLLM batches: the GPU
                    does more total work per second but each sequence finishes
                    later.

  dokumente/min     total throughput. This is the number that decides how many
                    firms the machine can carry.

AND ONE THAT MATTERS MORE THAN ALL THREE.

Determinism. vLLM batches concurrent requests together, and the batch's
composition changes the order of floating-point reductions. The same clause,
asked alone and asked alongside seven others, can come back different. For this
product that is not a performance detail: the whole claim is that the same
document gives the same report, and a lawyer who reruns an analysis and sees a
finding vanish has no reason to trust either run. So every report produced here
is compared, character for character, against the one produced alone. If they
diverge, the verdict says so and the concurrency number is worthless until it
is fixed (--max-num-seqs 1, or accept it and say so in the product).
"""
import hashlib
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import analizo
import pipeline

# "real" is the only setting that measures anything about the GPU. MAT_MODE=by_id
# runs the deterministic stub instead, which is how the harness itself is tested
# on a machine with no model -- it proves the timing, the fingerprinting and the
# cache work before any of it is pointed at the A5000.
MODE = os.environ.get("MAT_MODE", "real")


def _nje(dok, emri):
    """One document, through the product's own entry point."""
    t0 = time.perf_counter()
    raport, deshtime = analizo.analizo(dok, mode=MODE, emri=emri)
    return time.perf_counter() - t0, raport, deshtime


def _gishtat(raport):
    """A fingerprint of the FINDINGS, not of the whole report.

    The report carries the document's name, which differs per copy on purpose,
    so hashing the whole thing would report a false difference every time. What
    must be identical is the legal content: which articles were cited and what
    was said about them.
    """
    rreshtat = [r for r in raport.split("\n")
                if r.startswith("**Bie ndesh me")
                or r.startswith("Klauzola parashikon")
                or r.startswith("## Neni")]
    return hashlib.sha256("\n".join(rreshtat).encode()).hexdigest()[:12], rreshtat


def kontrollo_modelin():
    """Is the model up, BEFORE twelve seconds of corpus loading find out for us.

    The first run of this measurement spent twelve seconds loading the corpus
    and then produced a sweep of 1, 2, 4 and 8 documents in which every single
    request was refused -- a full table of numbers measuring how fast a
    connection can fail. A measurement that keeps going after its baseline
    collapsed is not a measurement.
    """
    if MODE != "real":
        return True, f"MAT_MODE={MODE}, pa model"
    import json
    import urllib.request
    import llm
    rrenja = llm.API_URL.split("/v1/")[0]
    try:
        with urllib.request.urlopen(f"{rrenja}/v1/models", timeout=5) as r:
            emrat = [m.get("id") for m in json.loads(r.read()).get("data", [])]
    except Exception as e:
        return False, (f"{llm.API_URL} nuk pergjigjet ({type(e).__name__}).\n"
                       f"  Hap nje dritare TE DYTE te Ubuntu dhe lesho:\n"
                       f"      source ~/venv/bin/activate\n"
                       f"      VLLM_USE_FLASHINFER_SAMPLER=0 vllm serve "
                       f"{llm.MODEL} --max-model-len 8192 --seed 42\n"
                       f"  Prit 'Application startup complete', pastaj rilesho "
                       f"kete matje.")
    if llm.MODEL not in emrat:
        return False, (f"Serveri punon por nuk ka '{llm.MODEL}'.\n"
                       f"  Ka: {', '.join(emrat) or '(asnje)'}\n"
                       f"  Vendos OR_MODEL te njerin prej tyre, ose rinis "
                       f"vLLM-in me modelin e duhur.")
    return True, f"{llm.MODEL} ne {rrenja}"


def mat(dok, nivelet=(1, 2, 4, 8)):
    print(f"Dokumenti: {dok}")
    ok, mesazhi = kontrollo_modelin()
    print(f"Modeli: {mesazhi}\n")
    if not ok:
        return []

    # The corpus cost, alone and once, before any GPU work muddies it.
    t0 = time.perf_counter()
    pipeline._KESHI.clear()
    pipeline._korpusi_i_ngarkuar()
    t_ftohte = time.perf_counter() - t0
    t0 = time.perf_counter()
    pipeline._korpusi_i_ngarkuar()
    t_ngrohte = time.perf_counter() - t0
    meta, units, _ = pipeline._korpusi_i_ngarkuar()
    print(f"Korpusi: {len(units)} njesi, {len(meta.get('ligjet') or {})} ligje")
    print(f"  ngarkimi i pare : {t_ftohte:6.2f}s   (nje here per proces)")
    print(f"  nga keshi       : {t_ngrohte:6.3f}s   (cdo dokument tjeter)\n")

    # WARM FIRST, THEN MEASURE.
    #
    # The first analysis also builds the chosen law's index and the verifier,
    # which the ones after it reuse. Taking the baseline cold made the single
    # document look slower than it is, and since every other level is judged
    # against twice that number, a cold baseline quietly raises the bar and
    # flatters concurrency. One throwaway run, not counted.
    print("Nxehja (nuk numerohet)...", end=" ", flush=True)
    t_nxehje, _, dsh_nxehje = _nje(dok, "nxehje.txt")
    print(f"{t_nxehje:.1f}s\n")

    # The baseline run, alone. Everything else is compared against this.
    vonesa_1, raport_1, dsh_1 = _nje(dok, "baza.txt")
    gishti_1, gjetjet_1 = _gishtat(raport_1)
    print(f"Vetem (1): {vonesa_1:5.1f}s, {len(gjetjet_1)} rreshta gjetjesh, "
          f"gishti {gishti_1}, {dsh_1} deshtime\n")
    if dsh_1:
        # STOP. Throughput measured while requests are erroring is the speed of
        # the error, and the determinism check would compare one broken report
        # against another and report that determinism held.
        print(f"NDALOJ: {dsh_1} pyetje deshtuan edhe kur dokumenti ishte "
              f"vetem.\nMatja e paralelizmit nuk ka kuptim derisa nje dokument "
              f"i vetem\nte kaloje i plote. Shiko daljen e vLLM-it ne dritaren "
              f"e dyte.")
        return []

    print(f"{'njekohesisht':>12} {'koha':>7} {'vonesa mes':>11} "
          f"{'vonesa max':>11} {'dok/min':>8} {'deshtime':>9} {'i njejte':>9}")
    rreshtat = []
    for n in nivelet:
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=n) as ex:
            rez = list(ex.map(lambda i: _nje(dok, f"kopja{i}.txt"), range(n)))
        gjithsej = time.perf_counter() - t0
        vonesat = [r[0] for r in rez]
        deshtime = sum(r[2] for r in rez)
        gishtat = {_gishtat(r[1])[0] for r in rez}
        njejte = (gishtat == {gishti_1})
        rreshtat.append((n, gjithsej, statistics.median(vonesat), max(vonesat),
                         n / gjithsej * 60, deshtime, njejte))
        print(f"{n:>12} {gjithsej:>6.1f}s {statistics.median(vonesat):>10.1f}s "
              f"{max(vonesat):>10.1f}s {n / gjithsej * 60:>8.1f} {deshtime:>9} "
              f"{'po' if njejte else 'NDRYSHOJNE':>9}")

    print()
    _verdikti(rreshtat, vonesa_1)
    return rreshtat


def _verdikti(rreshtat, vonesa_1):
    ndryshojne = [r for r in rreshtat if not r[6]]
    if ndryshojne:
        print("DETERMINIZMI U THYE.")
        print(f"  Ne {', '.join(str(r[0]) for r in ndryshojne)} dokumente "
              f"njekohesisht, raportet nuk dalin te njejta me ate te vetmin.")
        print("  Pra i njejti dokument jep raporte te ndryshme sipas se cfare")
        print("  po perpunohet bashke me te. Numrat e shpejtesise me lart nuk")
        print("  vlejne derisa kjo te rregullohet: lesho vLLM-in me")
        print("      --max-num-seqs 1")
        print("  dhe matja prapa, ose prano jo-determinizmin dhe shkruaje te")
        print("  dukshem ne produkt. Mos e shit si te verifikueshem ndersa")
        print("  rezultati varet nga trafiku.")
    else:
        print("Determinizmi mbajti: cdo nivel dha te njejtat gjetje si i vetmi.")

    deshtuan = [r for r in rreshtat if r[5]]
    if deshtuan:
        print(f"\nDESHTIME nga {deshtuan[0][0]} dokumente e lart. Kjo zakonisht"
              f"\neshte vLLM-i duke refuzuar kerkesa kur rradha mbushet, ose "
              f"\nkujtesa e GPU-se. Numri i sigurt eshte poshte tij.")

    # The practical answer: the largest level whose per-document wait is still
    # within twice the alone-time, with no failures and no divergence.
    kufi = vonesa_1 * 2
    mire = [r for r in rreshtat if r[6] and not r[5] and r[2] <= kufi]
    if mire:
        m = max(mire, key=lambda r: r[0])
        print(f"\nPRAKTIKISHT: {m[0]} dokumente njekohesisht. Vonesa mesatare "
              f"{m[2]:.0f}s\n(kufiri i pranuar: {kufi:.0f}s, dyfishi i kohes kur "
              f"eshte vetem)\nKapaciteti: {m[4]:.1f} dokumente/minute.")
    else:
        print(f"\nPRAKTIKISHT: 1 dokument njekohesisht. Asnje nivel me i larte "
              f"nuk\ne mbajti vonesen nen {kufi:.0f}s pa deshtime dhe pa "
              f"ndryshime.")
    print("\nKJO MATJE ESHTE PER NJE DOKUMENT TE PERSERITUR. Dokumente te")
    print("gjate ose te skanuar kushtojne me shume; kjo eshte dyshemeja, jo")
    print("premtimi.")


if __name__ == "__main__":
    args = sys.argv[1:]
    dok = args[0] if args and not args[0].isdigit() else "kontrata_qiraje.txt"
    nivelet = tuple(int(a) for a in args if a.isdigit()) or (1, 2, 4, 8)
    if not Path(dok).exists():
        print(f"{dok} nuk u gjet.")
        sys.exit(1)
    mat(dok, nivelet)
