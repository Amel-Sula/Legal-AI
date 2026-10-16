#!/usr/bin/env python3
"""Mark a provision: does it state a ceiling, a floor, a duty, a ban, a number?

flag_limits.py did this for the Labour Code only, and the Labour Code was the
only law in the corpus, so that was enough. Now the corpus holds every Albanian
code, and two things break without this module:

  1. verify.drejtimi() reads the direction of a limit from the corpus, never
     from the model. An article with no `sinjale` has no direction, so the
     arithmetic gate cannot fire and the report template falls back to a guess.
  2. retrieve.BM25 boosts points that STATE A LIMIT. Articles with no flag
     never get that boost and lose to articles that merely share vocabulary.

The regexes for ceiling / floor / duty / ban are not employment-specific: they
are the standard Albanian legislative phrasings ("jo më shumë se", "së paku",
"ndalohet"). They work in the Civil Code exactly as they work in the Labour
Code. Only flag_limits.py's TOPIC list was employment-specific, and topics are
not used here: a provision carrying a bounded number is checkable on its own.
"""
import re

# A comparison carries its direction in the adjective, not in the frame. The
# frame varies freely ("jo më X se", "nuk mund të jetë më X se", "më X se"), so
# matching frames one at a time is how Neni 803 of the Civil Code was read as
# having no ceiling at all: it says "nuk mund të lidhet për një kohë më të
# gjatë se tridhjetë vjet" -- neither "jo më shumë se" nor "më e gjatë se".
#
# These two word sets must stay disjoint and must not be merged into one
# generic "më ... se": "më e vogël se" is a FLOOR, and a ceiling pattern that
# swallowed it would invert the direction of every finding under it.
_MADH = r"(?:gjat[ëe]|shum[ëe]|lart[ëe]|madh[ëe]?|tep[ëe]r|vonsh[ëe]m)"
_VOGEL = r"(?:pak|pakt[ëe]|vog[ëe]l|vog[ëe]l[ëe]|ul[ëe]t|shkurt[ëe]r|par[ëe]sh[ëe]m)"

CEILING = re.compile(
    rf"(jo m[ëe] {_MADH} se"
    rf"|m[ëe] (?:e|i|t[ëe]|s[ëe]) {_MADH} se"
    rf"|nuk mund t[ëe] (?:jet[ëe]|kalojn?[ëe]|tejkaloj[ëe]?n?)"
    rf"|nuk duhet t[ëe] (?:kaloj|tejkaloj)"
    rf"|maksimumi|maksimal"
    rf"|brenda afat(?:it|eve) (?:prej|t[ëe])"
    rf"|deri n[ëe] (?=\d|nj[ëe]|dy|tre|kat[ëe]r|pes[ëe]|gjasht[ëe]))", re.I)
FLOOR = re.compile(
    rf"(s[ëe] paku|t[ëe] pakt[ëe]n|minimumi|minimale"
    rf"|jo m[ëe] {_VOGEL} se"
    rf"|m[ëe] (?:e|i|t[ëe]|s[ëe]) {_VOGEL} se)", re.I)
DUTY = re.compile(r"\b(duhet|detyrohet|[ëe]sht[ëe] i detyruar|ngarkohet|detyrimisht)\b", re.I)
BAN = re.compile(r"\b(ndalohet|nuk lejohet|[ëe]sht[ëe] i ndaluar|e pavlefshme|absolutisht e ndaluar)\b", re.I)

UNIT = re.compile(
    r"\b(\d{1,3}(?:[ \.]\d{3})*(?:[.,]\d+)?)\s*"
    r"(or[ëe]|dit[ëe]|jav[ëe]|muaj|vjet|vite|vit|vjec|lek[ëe]|%|p[ëe]rqind)", re.I)
# The whole word-number range, not the subset the Labour Code happens to use.
# The older codes spell almost every figure out: Neni 803 of the Civil Code caps
# a lease at "tridhjetë vjet", and with "tridhjetë" missing from this list the
# article carried a ceiling with no value, failed the checkable test, lost its
# retrieval boost, and a forty-year lease passed as lawful. verify.FJALE_NUM
# already reads these; this is the half that was missing.
WORDNUM = re.compile(
    r"\b(nj[ëe]|dy|tre|tri|kat[ëe]r|pes[ëe]|gjasht[ëe]|shtat[ëe]|tet[ëe]|n[ëe]nt[ëe]|dhjet[ëe]|"
    r"nj[ëe]mb[ëe]dhjet[ëe]|dymb[ëe]dhjet[ëe]|trembedhjet[ëe]|kat[ëe]rmb[ëe]dhjet[ëe]|"
    r"pes[ëe]mb[ëe]dhjet[ëe]|gjasht[ëe]mb[ëe]dhjet[ëe]|shtat[ëe]mb[ëe]dhjet[ëe]|"
    r"tet[ëe]mb[ëe]dhjet[ëe]|n[ëe]nt[ëe]mb[ëe]dhjet[ëe]|nj[ëe]zet|tridhjet[ëe]|dyzet|"
    r"pes[ëe]dhjet[ëe]|gjasht[ëe]dhjet[ëe]|shtat[ëe]dhjet[ëe]|tet[ëe]dhjet[ëe]|"
    r"n[ëe]nt[ëe]dhjet[ëe]|nj[ëe]qind)\s+"
    r"(or[ëe]|dit[ëe]|jav[ëe]|muaj|vjet|vite|vit|vjec|javore|mujore|vjetor|"
    r"p[ëe]rqind|lek[ëe])", re.I)


def shenjo(teksti: str) -> dict:
    """{'sinjale':..., 'vlera_numerike': [...], 'i_kontrollueshem': bool}"""
    t = teksti or ""
    sig = {
        "kufi_maksimal": bool(CEILING.search(t)),
        "kufi_minimal": bool(FLOOR.search(t)),
        "detyrim": bool(DUTY.search(t)),
        "ndalim": bool(BAN.search(t)),
    }
    nums = [f"{m.group(1)} {m.group(2)}" for m in UNIT.finditer(t)]
    nums += [f"{m.group(1)} {m.group(2)}" for m in WORDNUM.finditer(t)]
    return {
        "sinjale": sig,
        "vlera_numerike": nums,
        # Without a topic list, the bar is: it bounds something, and there is a
        # number to bound; or it forbids something outright.
        "i_kontrollueshem": bool(
            ((sig["kufi_maksimal"] or sig["kufi_minimal"]) and nums)
            or sig["ndalim"]
            or (sig["detyrim"] and nums)
        ),
    }
