#!/usr/bin/env python3
"""
The trust layer. Nothing the model says reaches a lawyer unless this passes it.

The model is allowed to be wrong. It is not allowed to be wrong INVISIBLY.
Every finding must carry an article number and a verbatim quote; this checks
the quote really is in that article, character for character, and throws away
anything that is not. A dropped true finding costs recall. A published invented
citation costs the whole business.
"""
import re, json, unicodedata
from difflib import SequenceMatcher
from pathlib import Path

FOLD = str.maketrans({"ë": "e", "Ë": "e", "ç": "c", "Ç": "c"})
QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'",
                        "’": "'", "″": '"', "«": '"',
                        "»": '"', "–": "-", "—": "-"})

# verdicts that may be shown to a user
PASSING = {"OK", "OK_NORMALIZED"}

FJALE_NUM = {
    "nje": 1, "nje)": 1, "dy": 2, "tre": 3, "tri": 3, "kater": 4, "pese": 5,
    "gjashte": 6, "shtate": 7, "tete": 8, "nente": 9, "dhjete": 10,
    "njembedhjete": 11, "dymbedhjete": 12, "trembedhjete": 13,
    "katermbedhjete": 14, "pesembedhjete": 15, "gjashtembedhjete": 16,
    "shtatembedhjete": 17, "tetembedhjete": 18, "nentembedhjete": 19,
    "njezet": 20, "njezetedy": 22, "tridhjete": 30, "dyzet": 40,
    "pesedhjete": 50, "gjashtedhjete": 60,
}
NJESI = {
    "ore": "ore", "oresh": "ore", "oret": "ore", "orë": "ore",
    "dite": "dite", "ditesh": "dite", "ditet": "dite", "ditë": "dite",
    "jave": "jave", "javesh": "jave", "javë": "jave", "javet": "jave",
    "muaj": "muaj", "muajsh": "muaj", "muaji": "muaj",
    "vit": "vit", "vjet": "vit", "vjetesh": "vit", "vite": "vit",
    "perqind": "perqind", "%": "perqind", "leke": "leke", "lek": "leke",
}
def _as_number(tok):
    if re.fullmatch(r"\d+(?:[.,]\d+)?", tok):
        return float(tok.replace(",", "."))
    return FJALE_NUM.get(tok)


def parse_qty(s):
    """'6 (gjashte) muaj' -> (6.0,'muaj');  '25 per qind' -> (25.0,'perqind').

    Token scan rather than one regex, because the values the model returns are
    written every way a human writes them: digits, Albanian words, both at once
    with the word in brackets, and units one or two tokens later.
    """
    if not s:
        return None
    t = norm(str(s), fold_diacritics=True)
    t = re.sub(r"[()\[\],;/]", " ", t)
    t = re.sub(r"\bper\s+qind\b", "perqind", t)
    t = re.sub(r"(\d)\s+(?=\d{3}\b)", r"\1", t)      # 100 000 -> 100000
    t = t.replace("%", " perqind ")
    toks = [x for x in t.split() if x]

    val = None
    for i, tok in enumerate(toks):
        n = _as_number(tok)
        if n is not None:
            val = n if val is None else val          # keep the FIRST number
            continue
        unit = NJESI.get(tok)
        if unit and val is not None:
            return val, unit
    return None


def norm(s: str, fold_diacritics=False) -> str:
    s = unicodedata.normalize("NFC", s or "")
    s = s.translate(QUOTES)
    s = re.sub(r"\s+", " ", s).strip().strip('"\'')
    s = s.lower()
    if fold_diacritics:
        s = s.translate(FOLD)
    return s


class Verifier:
    def __init__(self, corpus_path="kodi_punes_flagged.json"):
        d = json.load(open(corpus_path, encoding="utf-8"))
        self.meta = d["meta"]
        self.by_article = {}
        self.by_point = {}
        self.sinjale = {}          # key -> {"kufi_maksimal":bool,"kufi_minimal":bool,...}
        for a in d["nenet"]:
            self.by_article[a["neni"]] = a["teksti"]
            for p in a["pikat"]:
                key = f"{a['neni']}/{p['pika']}" if p["pika"] else a["neni"]
                self.by_point[key] = p["teksti"]
                if p.get("sinjale"):
                    self.sinjale[key] = p["sinjale"]
        # one flat haystack for detecting misattribution
        self._flat = [(k, norm(v), norm(v, True))
                      for k, v in self.by_point.items()]

    # ------------------------------------------------------------------
    def _article_text(self, ref: str):
        """Accept '150', '150/1', 'Neni 150, pika 1' and the like."""
        if ref is None:
            return None, None
        r = str(ref).strip()
        r = re.sub(r"^\s*neni\s*", "", r, flags=re.I)
        r = re.sub(r"\s*,?\s*pika\s*", "/", r, flags=re.I)
        r = r.replace(" ", "")
        if r in self.by_point:
            return r, self.by_point[r]
        base = r.split("/")[0]
        # a sub-numbered article like 18/5 is its own article, check that first
        if r in self.by_article:
            return r, self.by_article[r]
        if base in self.by_article:
            return base, self.by_article[base]
        return None, None

    def _find_elsewhere(self, q: str, qf: str):
        for key, hay, hayf in self._flat:
            if q and q in hay:
                return key, "exact"
            if qf and qf in hayf:
                return key, "folded"
        return None, None

    def _closest(self, q: str, text: str):
        """Best matching window of `text` for `q`, to tell a paraphrase from
        an invention."""
        if not q or not text:
            return 0.0, ""
        n = len(q)
        best, bestseg = 0.0, ""
        step = max(1, n // 4)
        for i in range(0, max(1, len(text) - n + 1), step):
            seg = text[i:i + n + 20]
            r = SequenceMatcher(None, q, seg).ratio()
            if r > best:
                best, bestseg = r, seg
        return best, bestseg

    # ------------------------------------------------------------------
    def check(self, neni, citim):
        """Verify one claimed citation. Returns a verdict dict."""
        out = {"neni": neni, "citim": citim, "verdict": None, "detaj": ""}

        key, text = self._article_text(neni)
        if text is None:
            out["verdict"] = "NO_SUCH_ARTICLE"
            out["detaj"] = f"Neni {neni} nuk ekziston ne korpus"
            return out
        out["neni_zgjidhur"] = key

        q, qf = norm(citim), norm(citim, True)
        if not q:
            out["verdict"] = "EMPTY_QUOTE"
            out["detaj"] = "Citim bosh"
            return out

        hay, hayf = norm(text), norm(text, True)

        if q in hay:
            out["verdict"] = "OK"
            return out
        if qf in hayf:
            out["verdict"] = "OK_NORMALIZED"
            out["detaj"] = "Perputhje pas normalizimit te shkronjave e/ë, c/ç"
            return out

        where, how = self._find_elsewhere(q, qf)
        if where:
            out["verdict"] = "WRONG_ARTICLE"
            out["detaj"] = (f"Citimi ekziston, por te Neni {where}, "
                            f"jo te Neni {neni} ({how})")
            out["neni_i_sakte"] = where
            return out

        sim, seg = self._closest(qf, hayf)
        if sim >= 0.80:
            out["verdict"] = "ALTERED"
            out["detaj"] = (f"Afer tekstit te nenit ({sim:.0%}) por i ndryshuar. "
                            f"Teksti real: \"{seg.strip()[:120]}\"")
            out["ngjashmeria"] = round(sim, 3)
            return out

        out["verdict"] = "NOT_FOUND"
        out["ngjashmeria"] = round(sim, 3)
        out["detaj"] = f"Citimi nuk gjendet askund ne Kodin e Punes (max {sim:.0%})"
        return out

    # ------------------------------------------------------------------
    def drejtimi(self, ref):
        """Does this provision state a ceiling or a floor? Ask the LAW, not the model.

        The model labels `lloji` and gets the direction wrong often enough that
        trusting it threw away two correct findings on the BIOCHECK contract.
        flag_limits.py already recorded, per point, whether the text says
        "jo me shume se" (a ceiling) or "te pakten" (a floor). That is ground
        truth and costs nothing to look up.
        """
        key, _ = self._article_text(ref)
        sig = self.sinjale.get(key) or {}
        if not sig and key and "/" in str(key):
            sig = self.sinjale.get(str(key).split("/")[0]) or {}
        maks, mini = bool(sig.get("kufi_maksimal")), bool(sig.get("kufi_minimal"))
        if maks and not mini:
            return "maksimal"
        if mini and not maks:
            return "minimal"
        return None

    def numeric_check(self, f):
        """Does the arithmetic of the claimed breach actually hold?

        Two jobs, in order of how often they matter:

        1. Reject a clause that COPIES the law. The contract grants 5 days'
           marriage leave, Neni 96/1 grants 5 days, and the model still calls it
           a breach. Equal values are never a breach. This was the original
           purpose and it still fires.

        2. Reject a breach whose direction contradicts the provision. A value
           under a ceiling, or over a floor, is compliance. The direction comes
           from the CORPUS, never from the model's `lloji` label.

        When the provision states neither a ceiling nor a floor, any difference
        is let through: there is nothing to check the direction against, and a
        silently dropped true finding costs more than a false alarm a lawyer
        can dismiss in one glance.
        """
        a = parse_qty(f.get("vlera_kontrates"))
        b = parse_qty(f.get("vlera_ligjore"))
        if not a or not b or a[1] != b[1]:
            return True, ""
        kv, lv, unit = a[0], b[0], a[1]

        if kv == lv:
            return False, f"kontrata {kv} {unit} = ligji {lv} {unit}, nuk ka ndryshim"

        d = self.drejtimi(f.get("neni_ligjit"))
        if d == "maksimal" and not kv > lv:
            return False, f"kontrata {kv} {unit} nuk e kalon kufirin {lv} {unit}"
        if d == "minimal" and not kv < lv:
            return False, f"kontrata {kv} {unit} nuk bie nen minimumin {lv} {unit}"
        return True, ""

    # ------------------------------------------------------------------
    def filter_findings(self, findings):
        """Split model output into what may be published and what may not."""
        kept, dropped = [], []
        for f in findings:
            if not f.get("ka_konflikt"):
                kept.append({**f, "verifikimi": {"verdict": "N/A_NO_CONFLICT"}})
                continue
            ok, why = self.numeric_check(f)
            if not ok:
                dropped.append({**f, "verifikimi": {
                    "verdict": "ARITMETIKA_NUK_QENDRON", "detaj": why}})
                continue
            v = self.check(f.get("neni_ligjit"), f.get("citim"))
            rec = {**f, "verifikimi": v}
            (kept if v["verdict"] in PASSING else dropped).append(rec)
        return kept, dropped


if __name__ == "__main__":
    V = Verifier()
    print(f"corpus: {V.meta['numri_neneve']} nene, "
          f"{len(V.by_point)} pika, i vlefshem deri {V.meta['i_vlefshem_deri']}\n")

    cases = [
        ("real, exact", "150",
         "Palët parashikojnë me shkrim një periudhë prove jo më shumë se tre muaj."),
        ("real, no diacritics (typed on a plain keyboard)", "150",
         "Palet parashikojne me shkrim nje periudhe prove jo me shume se tre muaj."),
        ("real, point reference", "92/2",
         "Kohëzgjatja e pushimeve vjetore është jo më pak se 22 ditë pune"),
        ("MISATTRIBUTED: real text, wrong article", "99",
         "Kohëzgjatja normale e javës së punës është jo më shumë se 40 orë."),
        ("ALTERED: number changed 3 -> 6", "150",
         "Palët parashikojnë me shkrim një periudhë prove jo më shumë se gjashtë muaj."),
        ("ALTERED: negation removed", "83",
         "Kohëzgjatja normale e javës së punës është 40 orë."),
        ("FABRICATED quote", "150",
         "Periudha e provës nuk mund të kalojë 90 ditë kalendarike sipas ligjit."),
        ("FABRICATED article", "411",
         "Punëdhënësi detyrohet të paguajë shpërblim shtesë."),
        ("plausible but invented minimum wage", "111",
         "Paga minimale mujore është 40.000 lekë."),
    ]

    width = max(len(c[0]) for c in cases)
    for label, neni, citim in cases:
        r = V.check(neni, citim)
        mark = "PASS" if r["verdict"] in PASSING else "BLOCK"
        print(f"[{mark}] {label:<{width}}  -> {r['verdict']}")
        if r["detaj"]:
            print(f"         {r['detaj'][:150]}")
