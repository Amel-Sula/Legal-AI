#!/usr/bin/env python3
"""Which laws in the corpus are wearing somebody else's name.

    python3 kontrollo_titujt.py
    python3 kontrollo_titujt.py "Për Shqyrtimin"     # one law, in detail

WHY THIS EXISTS.

Asked whether a wooden hut needs a building permit, the product returned five
provisions, all of them labelled

    Për Shqyrtimin e Vlefshmërisë Ligjore të Krijimit të Titujve të
    Pronësisë mbi Tokën Bujqësore

and none of them about agricultural land titles. Their subjects were the
one-stop permit desk, the site coverage ratio, KKT review of building permit
applications, the general local plan, and administrative offences in
construction. That is the territorial planning law and its implementing
decision, filed under the name of a different, much smaller law.

A citation carries the law's name, and the name is what a lawyer checks at
qbz.gov.al. A wrong name is worse than a missing one: the article text is real,
so the error survives a careful reading and only fails when he goes looking for
it in the wrong law.

The cause is the compendium splitter. One PDF holds many laws, ndaj_permbledhjen
cuts it into segments, and when a cut is missed the following laws' articles
are swallowed by the segment before them and inherit its title. This cannot be
fixed blind, so it is first measured: a law whose article count is far beyond
what its own numbering reaches, or whose articles come from a compendium under
a name that occurs nowhere in their text, is a law to look at.
"""
import json
import re
import sys
from collections import Counter

import korpusi


def _nr(ref):
    m = re.match(r"\D*(\d+)", str(ref or ""))
    return int(m.group(1)) if m else 0


def analizo(units):
    sipas = {}
    for u in units:
        sipas.setdefault(u.get("titulli_ligjit") or "?", []).append(u)
    dyshimet = []
    for titulli, nenet in sipas.items():
        # DISTINCT articles, in the order the parser met them. The Labour Code
        # is stored point by point -- Neni 150 appears four times -- so counting
        # units would call every point-level law suspicious, which it did on the
        # first run. What matters is the sequence of article numbers.
        nr, pare = [], set()
        for u in nenet:
            n = _nr(u["neni"])
            if n and n not in pare:
                pare.add(n)
                nr.append(n)
        if not nr:
            continue
        burimet = Counter((u.get("burimi") or "?") for u in nenet)
        # A COMPENDIUM THAT SWALLOWED THE NEXT LAW restarts its numbering: the
        # articles run 1..52, then 1..60 again under the same title. Counting
        # how often article numbers go BACKWARDS is the cheapest signal for it,
        # and it needs no knowledge of what the law should contain.
        # A real restart drops a long way, 52 -> 1. Articles like 803/1 landing
        # beside 803 move by one or two and are not restarts.
        kthesat = [(a, b) for a, b in zip(nr, nr[1:]) if a - b > 10]
        arsyet = []
        if kthesat:
            arsyet.append("numërimi kthehet prapa " + ", ".join(
                f"{a}->{b}" for a, b in kthesat[:4])
                + (" …" if len(kthesat) > 4 else ""))
        burimi = str(list(burimet)[0] or "")
        if (len(nr) > 100 and len(burimet) == 1
                and "ermbledh" in burimi.lower().replace("ë", "e")):
            arsyet.append(f"{len(nr)} nene nga një përmbledhje e vetme")
        if arsyet:
            dyshimet.append((titulli, len(nr), max(nr), arsyet, burimet))
    return sipas, dyshimet


def main(kerko=None):
    meta, units = korpusi.ngarko()
    sipas, dyshimet = analizo(units)
    print(f"{len(sipas)} ligje, {len(units)} njësi.\n")

    if kerko:
        rx = re.compile(re.escape(kerko), re.I)
        for titulli, nenet in sipas.items():
            if not rx.search(titulli):
                continue
            nr = [_nr(u["neni"]) for u in nenet]
            print(f"=== {titulli}")
            print(f"    {len(nenet)} nene, numri më i madh {max(nr)}, "
                  f"ligji {nenet[0].get('ligji')}")
            print(f"    burimi: {Counter(u.get('burimi') for u in nenet)}\n")
            for u in nenet[:40]:
                krye = (u["teksti"].strip().split("\n")[0])[:72]
                print(f"      {u['ref']:<16} {krye}")
            if len(nenet) > 40:
                print(f"      ... dhe {len(nenet) - 40} të tjerë")
        return

    if not dyshimet:
        print("Asnjë titull nuk duket se mbulon më shumë se një ligj.")
        return
    print(f"TË DYSHIMTA ({len(dyshimet)}) — një titull mbi disa ligje:\n")
    for titulli, sa, maxi, arsyet, burimet in sorted(dyshimet,
                                                    key=lambda x: -x[1]):
        print(f"  {titulli[:66]}")
        print(f"      {sa} nene te dallueshem, numri me i madh {maxi}")
        for a in arsyet:
            print(f"      - {a}")
        for b, n in burimet.most_common(2):
            print(f"      nga: {str(b)[:62]} ({n})")
        print()
    print("Çdo citim nga këto ligje mban emrin e gabuar. Shiko njërin me:")
    print('   python3 kontrollo_titujt.py "pjesë e titullit"')


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or None)
