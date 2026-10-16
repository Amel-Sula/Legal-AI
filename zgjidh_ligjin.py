#!/usr/bin/env python3
"""Layer one: decide WHICH LAW the document belongs to, before looking for articles.

With only the Labour Code indexed, the right article sat at rank 1-3. With all
sixteen codes in, two of them fell to rank 7 and 8 of 8. Nothing was lost yet,
but one more law and they drop out. And the next law to be added is employment
legislation, which speaks the same vocabulary as the Labour Code and will
compete directly, unlike the Civil Code.

So article retrieval must not run across the whole library. It runs inside the
one or two laws the document is actually about.

How the law is chosen: the document is searched against everything once, wide,
and each law scores the sum of its hits. A contract full of "punëmarrës",
"punëdhënës" and "pushime vjetore" scores the Labour Code far above the
Maritime Code, because those words barely occur there. No model, no training.
"""
from collections import defaultdict


def renditi_ligjet(idx, teksti, shiko=120):
    """Every law that matched, with its total score. Strongest first."""
    pikët = defaultdict(float)
    for pike, u in idx.search(teksti, top=shiko):
        pikët[u.get("titulli_ligjit") or "?"] += pike
    return sorted(pikët.items(), key=lambda kv: -kv[1])


def ligjet_e_dokumentit(idx, teksti, sa=2, pragu=0.45):
    """The laws to search inside.

    Takes the top `sa`, but drops any scoring under `pragu` of the leader: when
    a document is plainly about one law, carrying a weak second one in only
    gives its articles free places in the candidate list.

    Where `pragu` sits, measured on three documents, runner-up as a share of
    the leader:

        employment contract (biocheck)   8%   second law is noise
        employment contract (test_01)   13%   second law is noise
        lease contract                  35%   second law is noise

    and what the noise costs: carrying the Labour Code into the lease contract
    pushed Neni 803 of the Civil Code -- the article that caps a lease at
    thirty years, against a contract written for forty -- from rank 1 to rank
    4, and on the termination clause took seven of the eight candidate slots.
    It did not help a single clause.

    So the bar is high on purpose: a second law joins only when the document
    genuinely speaks two bodies of law, which is what will happen once the
    employment legislation goes in beside the Labour Code. Tuned on three
    documents; re-measure with mat_kerkimin.py as fixtures accumulate.
    """
    rend = renditi_ligjet(idx, teksti)
    if not rend:
        return []
    kreu = rend[0][1]
    return [emri for emri, p in rend[:sa] if p >= kreu * pragu]
