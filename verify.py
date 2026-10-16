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

# Clause numbering ("11.4.", "16.2.") would otherwise count as the contract
# containing the number 4 or 2.
NUMERIM = re.compile(r"\b\d+\s*\.\s*\d+\s*\.?")

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
    # The Albanian decimal separator is the comma, and it was being wiped out
    # with the brackets below: "4,8 orë" parsed as 4. Turned into a dot first,
    # which also folds the American "100,000" into the thousands rule above.
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)
    t = re.sub(r"[()\[\],;/]", " ", t)
    t = re.sub(r"\bper\s+qind\b", "perqind", t)
    # ALBANIAN THOUSANDS ARE SEPARATED BY A DOT, and float() reads a dot as a
    # decimal point, so "85.000 lekë" -- eighty-five thousand -- parsed as 85.0.
    # That has been wrong since the first fixture was written: kontrata_test_01
    # states a salary of 85.000 lekë and the arithmetic gate has been comparing
    # 85 all along. paga_minimale.py got this right; parse_qty did not.
    #
    # A separator run is collapsed only before exactly three digits not
    # followed by a fourth, so "85.000" and "85. 000" (OCR splits the group)
    # become 85000, while a real decimal like "4.8 orë" and clause numbering
    # like "16.2." are left alone.
    for _ in range(4):                                   # 1.234.567, one pass each
        t2 = re.sub(r"(?<=\d)[ .]+(?=\d{3}(?!\d))", "", t)
        if t2 == t:
            break
        t = t2
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


# escaped: FJALE_NUM holds "nje)" and NJESI holds "%", which are regex syntax
NJESI_RX = "|".join(re.escape(x) for x in
                    sorted(set(NJESI) | {"minuta", "minut"}, key=len, reverse=True))
FJALE_RX = "|".join(re.escape(x) for x in
                    sorted(FJALE_NUM, key=len, reverse=True))

# A quantity as the CLAUSE itself writes it: a number, optionally with the same
# number spelled out in brackets, then a unit. Used to hand the model the
# clause's own figures to choose from instead of letting it write one.
VLERA_RX = re.compile(
    rf"((?:\d{{1,3}}(?:[ .]\d{{3}})+|\d+(?:[.,]\d+)?|{FJALE_RX})"
    rf"\s*(?:\((?:[^)]{{0,24}})\)\s*)?"
    rf"(?:{NJESI_RX})\b"
    rf"(?:\s*(?:ne|në|per|për)\s+(?:{NJESI_RX})\b)?)", re.I)


def vlerat(teksti):
    """Every quantity the clause states, verbatim, de-duplicated, in order.

    VALUE BY REFERENCE, the same move that made fabricated quotes impossible.
    The model was asked to write vlera_kontrates itself and it wrote "48 orë"
    for a clause reading "Koha javore e punes eshte 40 ore ne jave" -- three
    runs out of three, deterministically. The 48 was not invented out of
    nothing: it was copied out of the LAW text in the candidate list (Neni
    90/2, "kur punëmarrësi ka kryer 48 orë pune"). A model that is shown the
    law and asked for the contract's number will sometimes return the law's.

    So it stops being asked. The clause's own figures are extracted here, shown
    as V1..Vn, and the model returns an id. Then no figure can reach a lawyer
    that the clause does not literally contain, by construction rather than by
    a check after the fact.
    """
    out, pare = [], set()
    for m in VLERA_RX.finditer(teksti or ""):
        s = re.sub(r"\s+", " ", m.group(1)).strip(" .,;")
        k = norm(s, True)
        if k in pare or not parse_qty(s):
            continue
        pare.add(k)
        out.append(s)
    return out


def norm(s: str, fold_diacritics=False) -> str:
    s = unicodedata.normalize("NFC", s or "")
    s = s.translate(QUOTES)
    s = re.sub(r"\s+", " ", s).strip().strip('"\'')
    s = s.lower()
    if fold_diacritics:
        s = s.translate(FOLD)
    return s


LIGJI_PARE = "Kodi i Punës"


class Verifier:
    """Checks a claimed citation against the law it claims to come from.

    Every lookup is scoped by LAW. With one law in the corpus that scoping was
    invisible, so it did not exist: by_point["5"] was Neni 5 of the Labour Code
    because there was nothing else it could be. With sixteen codes loaded,
    "Neni 5" is sixteen different provisions, and an unscoped lookup would
    verify a Civil Code quote against the Labour Code's Neni 5, find it absent,
    and throw away a correct finding — or, worse, find a stray match and pass
    an invented one. So `ligji` travels with the citation from the moment the
    model picks a candidate, and nothing here ever guesses it.
    """

    def __init__(self, corpus_path="kodi_punes_flagged.json", units=None):
        self.nene = {}       # ligji -> {neni -> teksti}
        self.pika = {}       # ligji -> {neni[/pika] -> teksti}
        self.sinjale = {}    # ligji -> {key -> {"kufi_maksimal":bool,...}}
        self.vlera = {}      # ligji -> {key -> ["40 ore", ...]}
        self.nr_ligjit = {}  # "7850/1994" -> titulli

        if units is not None:
            self._nga_units(units)
        else:
            self._nga_skedari(corpus_path)

        # per-law haystack for detecting misattribution. Scoped: a quote that
        # exists in ANOTHER law is not the same error as one sitting in the
        # wrong article of the law the model named, and the lawyer needs the
        # difference.
        self._flat = {
            L: [(k, norm(v), norm(v, True)) for k, v in p.items()]
            for L, p in self.pika.items()
        }

    # ------------------------------------------------------------------
    def _shto(self, ligji, neni, pika, teksti, sig=None, vlera=None):
        key = f"{neni}/{pika}" if pika else str(neni)
        self.pika.setdefault(ligji, {})[key] = teksti
        if sig:
            self.sinjale.setdefault(ligji, {})[key] = sig
        if vlera:
            self.vlera.setdefault(ligji, {})[key] = vlera

    def _nga_skedari(self, corpus_path):
        d = json.load(open(corpus_path, encoding="utf-8"))
        self.meta = d["meta"]
        L = LIGJI_PARE
        for a in d["nenet"]:
            self.nene.setdefault(L, {})[a["neni"]] = a["teksti"]
            for p in a["pikat"]:
                self._shto(L, a["neni"], p["pika"], p["teksti"], p.get("sinjale"),
                           p.get("vlera_numerike"))

    def _nga_units(self, units):
        """Built straight from the retrieval corpus, so the two can never
        disagree about what the law says."""
        copa = {}
        for u in units:
            L = u.get("titulli_ligjit") or LIGJI_PARE
            if u.get("ligji"):
                self.nr_ligjit[str(u["ligji"])] = L
            self._shto(L, u["neni"], u.get("pika"), u["teksti"], u.get("sinjale"),
                       u.get("vlera"))
            copa.setdefault((L, u["neni"]), []).append(u["teksti"])
        # the whole-article text, for a citation that names no point
        for (L, neni), pjeset in copa.items():
            self.nene.setdefault(L, {})[neni] = "\n".join(pjeset)
        self.meta = {
            "numri_neneve": len(copa),
            "numri_ligjeve": len(self.pika),
            "i_vlefshem_deri": "-",
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _celes(emri):
        """A law title reduced to what is stable about it. Titles come out of
        PDF title blocks and arrive dirty: diacritics typed or not, the page's
        footnote digit glued to the last word ("...Së Shqipërisë1"), and the
        same code named either "Kodi Civil" or "Për Kodin Civil Të Republikës
        Së Shqipërisë"."""
        t = norm(emri or "", fold_diacritics=True)
        t = re.sub(r"\d+", "", t)
        t = re.sub(r"^per\s+kodin\s+", "kodi ", t)
        t = re.sub(r"\s+t[ëe]?\s+republikes.*$", "", t)
        t = re.sub(r"^kodi\s+(?:i|e)\s+", "kodi ", t)
        return re.sub(r"[^a-z ]", "", t).strip()

    def _ligjet_per(self, ligji):
        """Which laws to look in.

        A named law resolves to that law ALONE, or to nothing. The earlier
        version of this fell back to the whole corpus when a name did not
        resolve, and that fallback is what it was written to prevent: on
        Boyie's machine the Civil Code is titled "Për Kodin Civil Të
        Republikës Së Shqipërisë1", so a lookup for "Kodi Civil" matched
        nothing, searched all sixteen codes, found Neni 803 in one of them and
        reported OK. The check passed while verifying nothing.

        An unnamed law still searches everything, which is right only for the
        single-law corpus the legacy constructor builds.
        """
        if not ligji:
            return list(self.pika)
        if ligji in self.pika:
            return [ligji]
        c = self._celes(ligji)
        for L in self.pika:
            if self._celes(L) == c:
                return [L]
        # the law number, when the title cannot be matched ("7850/1994")
        if ligji in self.nr_ligjit:
            return [self.nr_ligjit[ligji]]
        return []                      # unknown law: nothing to verify against

    def _article_text(self, ref: str, ligji=None):
        """Accept '150', '150/1', 'Neni 150, pika 1' and the like."""
        if ref is None:
            return None, None
        r = str(ref).strip()
        r = re.sub(r"^\s*neni\s*", "", r, flags=re.I)
        r = re.sub(r"\s*,?\s*pika\s*", "/", r, flags=re.I)
        r = r.replace(" ", "")
        base = r.split("/")[0]
        for L in self._ligjet_per(ligji):
            pika, nene = self.pika.get(L, {}), self.nene.get(L, {})
            if r in pika:
                return r, pika[r]
            # a sub-numbered article like 18/5 is its own article, check first
            if r in nene:
                return r, nene[r]
            if base in nene:
                return base, nene[base]
        return None, None

    def _find_elsewhere(self, q: str, qf: str, ligji=None):
        for L in self._ligjet_per(ligji):
            for key, hay, hayf in self._flat.get(L, []):
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
    def check(self, neni, citim, ligji=None):
        """Verify one claimed citation. Returns a verdict dict."""
        out = {"neni": neni, "citim": citim, "ligji": ligji,
               "verdict": None, "detaj": ""}

        if ligji and not self._ligjet_per(ligji):
            out["verdict"] = "LIGJ_I_PANJOHUR"
            out["detaj"] = (f"Ligji '{ligji}' nuk ndodhet ne korpus, pra citimi "
                            f"nuk verifikohet dot")
            return out

        key, text = self._article_text(neni, ligji)
        if text is None:
            out["verdict"] = "NO_SUCH_ARTICLE"
            out["detaj"] = (f"Neni {neni} nuk ekziston ne "
                            f"{ligji or 'korpus'}")
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

        where, how = self._find_elsewhere(q, qf, ligji)
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
        out["detaj"] = (f"Citimi nuk gjendet askund ne "
                        f"{ligji or 'korpus'} (max {sim:.0%})")
        return out

    # ------------------------------------------------------------------
    def drejtimi(self, ref, ligji=None):
        """Does this provision state a ceiling or a floor? Ask the LAW, not the model.

        The model labels `lloji` and gets the direction wrong often enough that
        trusting it threw away two correct findings on the BIOCHECK contract.
        flag_limits.py already recorded, per point, whether the text says
        "jo me shume se" (a ceiling) or "te pakten" (a floor). That is ground
        truth and costs nothing to look up.
        """
        key, _ = self._article_text(ref, ligji)
        # the law's own signals, and only that law's. _ligjet_per returns one
        # law when named and nothing when the name is unknown, so a direction
        # can never be read off the wrong code.
        sig_ligji = {}
        for L in self._ligjet_per(ligji):
            if key in (self.sinjale.get(L) or {}):
                sig_ligji = self.sinjale[L]
                break
            if self.sinjale.get(L) and not sig_ligji:
                sig_ligji = self.sinjale[L]
        sig = sig_ligji.get(key) or {}
        if not sig and key:
            # The model often cites an article without its point ("150"), while
            # the corpus files the limit on the point ("150/1"). Fall back to
            # the article's points: if they agree on a direction, use it.
            base = str(key).split("/")[0]
            pikat = [v for k, v in sig_ligji.items()
                     if str(k).split("/")[0] == base]
            sig = {"kufi_maksimal": any(x.get("kufi_maksimal") for x in pikat),
                   "kufi_minimal":  any(x.get("kufi_minimal") for x in pikat)}
        maks, mini = bool(sig.get("kufi_maksimal")), bool(sig.get("kufi_minimal"))
        if maks and not mini:
            return "maksimal"
        if mini and not maks:
            return "minimal"
        return None

    def kufi_numerik(self, ref, ligji=None):
        """Does this provision state a limit AS A NUMBER?

        The distinction decides whether a finding carrying no figure may be
        published. Neni 83 says "jo më shumë se 40 orë": to claim a contract
        breaches it, the contract's own figure has to be shown, and without one
        there is nothing to assert. Neni 818 of the Civil Code says the tenant
        "nuk mund t'ia kalojë kontratën pa pëlqimin e qiradhënësit": that is a
        prohibition with no number, and a breach of it is real even though no
        arithmetic exists. So "no figure" cannot mean "not a breach" in
        general; it means that only against a numeric limit.
        """
        key, _ = self._article_text(ref, ligji)
        if not key:
            return False
        for L in self._ligjet_per(ligji):
            sig = (self.sinjale.get(L) or {}).get(key) or {}
            vl = (self.vlera.get(L) or {}).get(key) or []
            if sig or vl:
                return bool((sig.get("kufi_maksimal") or sig.get("kufi_minimal"))
                            and vl)
        return False

    def vlera_nga_klauzola(self, teksti, vlera_ligjore):
        """The clause's own figure, when the model failed to name one.

        Blocking every figureless finding against a numeric limit cost more
        than it saved. On the lease contract, clause 7 sets a termination
        notice of "1 (nje) dite" against Neni 1023's "te pakten 10 dite": a
        real breach, blocked, because the model named no value even though the
        clause plainly contains one. Clause 7 of the BIOCHECK contract went the
        same way, after being caught in every earlier run.

        So the figure is taken from the clause instead. Exactly one of the
        clause's own quantities must share the unit of the law's: with none
        there is nothing comparable, and with several, picking one would be a
        guess printed as fact. The number comes out of the clause verbatim, so
        it cannot be an invention -- that is the same guarantee value-by-
        reference gives, reached without the model's help.
        """
        b = parse_qty(vlera_ligjore)
        if not b or not teksti:
            return None
        njesia = b[1]
        kandidate = []
        for v in vlerat(teksti):
            q = parse_qty(v)
            if q and q[1] == njesia:
                kandidate.append(v)
        return kandidate[0] if len(kandidate) == 1 else None

    def vlera_ne_klauzole(self, vlera, teksti):
        """Does the contract really say what the model claims it says?

        Every quote of the LAW is checked character for character against the
        corpus. The value the model attributes to the CONTRACT was never
        checked against anything. On the BIOCHECK contract the model reported
        "the clause provides 48 hours" for a clause reading "Koha javore e
        punes eshte 40 ore", twice, and both findings reached the report.

        A lawyer who opens the contract and finds 40 where the report says 48
        stops trusting every other line on the page, including the correct
        ones. So this is checked like a citation: the claimed figure must
        appear in the clause, as digits or as the Albanian word.

        Values carrying no number ("pa kufi") are let through: there is
        nothing to look for.
        """
        q = parse_qty(vlera)
        if not q or not teksti:
            return True, ""
        n = q[0]
        t = NUMERIM.sub(" ", norm(teksti, True))
        t = re.sub(r"(\d)[ .,](?=\d{3}\b)", r"\1", t)      # 100 000 -> 100000
        nn = int(n) if float(n).is_integer() else n
        if re.search(rf"(?<!\d){nn}(?!\d)", t):
            return True, ""
        for fjale, vlere in FJALE_NUM.items():
            if vlere == nn and fjale in t:
                return True, ""
        return False, (f"klauzola nuk e permban vleren {nn}; "
                       f"numrat e saj: {sorted(set(re.findall(r'[0-9]+', t)))[:9]}")


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

        d = self.drejtimi(f.get("neni_ligjit"), f.get("ligji"))
        if d == "maksimal" and not kv > lv:
            return False, f"kontrata {kv} {unit} nuk e kalon kufirin {lv} {unit}"
        if d == "minimal" and not kv < lv:
            return False, f"kontrata {kv} {unit} nuk bie nen minimumin {lv} {unit}"
        return True, ""

    # ------------------------------------------------------------------
    def filter_findings(self, findings, klauzola_teksti=None):
        """Split model output into what may be published and what may not."""
        kept, dropped = [], []
        for f in findings:
            if not f.get("ka_konflikt"):
                kept.append({**f, "verifikimi": {"verdict": "N/A_NO_CONFLICT"}})
                continue
            ok, why = self.vlera_ne_klauzole(f.get("vlera_kontrates"), klauzola_teksti)
            if not ok:
                dropped.append({**f, "verifikimi": {
                    "verdict": "VLERA_JO_NE_KLAUZOLE", "detaj": why}})
                continue
            # A FINDING WITH NO FIGURE, AGAINST A PROVISION THAT STATES ONE.
            #
            # Under value-by-reference the model can no longer invent the
            # contract's number, and when it has none it returns nothing. Every
            # gate below then passes trivially -- there is nothing to compare --
            # so the arithmetic check silently stops existing and the finding is
            # printed as a breach on the strength of the citation alone. On the
            # BIOCHECK contract that is exactly what happened to clause 10,
            # whose 40 hours a week equals the Neni 83 maximum and breaches
            # nothing. Such a finding is not published as a conflict; it goes to
            # the report's reading list, where the lawyer decides.
            # No figure from the model: before holding the finding back, look
            # for the clause's own.
            if not parse_qty(f.get("vlera_kontrates")):
                vk = self.vlera_nga_klauzola(klauzola_teksti, f.get("vlera_ligjore"))
                if vk:
                    f = {**f, "vlera_kontrates": vk, "vlera_nga_klauzola": True}

            if not parse_qty(f.get("vlera_kontrates")) and self.kufi_numerik(
                    f.get("neni_ligjit"), f.get("ligji")):
                dropped.append({**f, "verifikimi": {
                    "verdict": "PA_VLERE_KUNDREJT_KUFIRIT",
                    "detaj": ("dispozita vendos kufi numerik, por nga klauzola "
                              "nuk u nxorr vlere; shkelja nuk pohohet")}})
                continue
            ok, why = self.numeric_check(f)
            if not ok:
                dropped.append({**f, "verifikimi": {
                    "verdict": "ARITMETIKA_NUK_QENDRON", "detaj": why}})
                continue
            v = self.check(f.get("neni_ligjit"), f.get("citim"), f.get("ligji"))
            rec = {**f, "verifikimi": v}
            (kept if v["verdict"] in PASSING else dropped).append(rec)
        return kept, dropped


if __name__ == "__main__":
    V = Verifier()
    print(f"corpus: {V.meta['numri_neneve']} nene, "
          f"{sum(len(p) for p in V.pika.values())} pika, "
          f"i vlefshem deri {V.meta['i_vlefshem_deri']}\n")

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
