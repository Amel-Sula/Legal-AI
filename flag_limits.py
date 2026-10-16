#!/usr/bin/env python3
"""
Second pass over kodi_punes.json: mark the points that a contract clause can
actually violate, and the points that defer a limit to a VKM decision.
Writes kodi_punes_flagged.json plus a human-readable audit list.
"""
import json, re
from pathlib import Path

d = json.load(open("kodi_punes.json", encoding="utf-8"))

# ---- signals ---------------------------------------------------------------
CEILING = re.compile(
    r"(jo m[ëe] shum[ëe] se|nuk mund t[ëe] (?:jet[ëe]|kalojn?[ëe]|tejkaloj[ëe]?n?)"
    r"|m[ëe] e gjat[ëe] se|maksimumi|deri n[ëe] (?=\d|nj[ëe]|dy|tre|kat[ëe]r|pes[ëe]|gjasht[ëe]))", re.I)
FLOOR = re.compile(r"(s[ëe] paku|t[ëe] pakt[ëe]n|minimumi|jo m[ëe] pak se|minimale)", re.I)
DUTY  = re.compile(r"\b(duhet|detyrohet|[ëe]sht[ëe] i detyruar|ngarkohet|detyrimisht)\b", re.I)
BAN   = re.compile(r"\b(ndalohet|nuk lejohet|[ëe]sht[ëe] i ndaluar|e pavlefshme|absolutisht e ndaluar)\b", re.I)
VKM   = re.compile(r"K[ëe]shilli(?:t)? i(?:t)? Ministrave|vendim(?:i|it)? i K[ëe]shillit t[ëe] Ministrave|VKM", re.I)

UNIT  = re.compile(
    r"\b(\d{1,3}(?:[ \.]\d{3})*(?:[.,]\d+)?)\s*"
    r"(or[ëe]|dit[ëe]|jav[ëe]|muaj|vjet|vite|vit|vjec|lek[ëe]|%|p[ëe]rqind)", re.I)
WORDNUM = re.compile(
    r"\b(nj[ëe]|dy|tre|tri|kat[ëe]r|pes[ëe]|gjasht[ëe]|shtat[ëe]|tet[ëe]|n[ëe]nt[ëe]|dhjet[ëe]|"
    r"dymb[ëe]dhjet[ëe]|katermb[ëe]dhjet[ëe]|gjashtëmbëdhjet[ëe]|tetëmbëdhjet[ëe]|njëzet)\s+"
    r"(or[ëe]|dit[ëe]|jav[ëe]|muaj|vjet|vite|vit|javore|mujore|vjetor)", re.I)

TOPICS = {
    "periudha_e_proves":  r"prov[ëe]s\b|n[ëe] prov[ëe]|periudh[ëa] prove",
    "afati_i_njoftimit":  r"njoftim|zgjidhj.{0,40}kontrat|kontrat.{0,40}zgjidh",
    "koha_e_punes":       r"koh[ëe]zgjatj|koh[ëe]n? e pun|or[ëe]s? pun|orar|jav[ëe]s? s[ëe] pun|ditore|javore|mujore",
    "puna_jashte_orarit": r"or[ëe] shtes|or[ëe]s? shtes|jasht[ëe] orarit|mbi koh[ëe]zgjatjen|pun[ëe] nat",
    "pushimet":           r"pushim|lej[ëe]\b|leje\b|festa zyrtare|vjetor",
    "paga":               r"\bpag[ëa]\b|pag[ëe]s|pag[ëe]n|shp[ëe]rblim|paga minimale",
    "kontrata_me_afat":   r"afat t[ëe] caktuar|afat t[ëe] pacaktuar|kontrat[ëe] me afat",
    "te_mitur":           r"t[ëe] mitur|f[ëe]mij|mosh[ëe]|adoleshent",
    "shtatzenia":         r"shtatz[ëe]n|lehon|am[ëe]si|gjidh[ëe]n|lindj",
    "diskriminimi":       r"diskriminim|barazi|trajtim i barabart|ngacmim",
    "disiplina":          r"disiplinor",
    "sanksione":          r"g[ji]ob[ëa]|sanksion|kund[ëe]rvajtje|d[ëe]nohet",
    "forma_e_kontrates":  r"form[ëe] t[ëe] shkruar|me shkrim|duhet t[ëe] p[ëe]rmbaj",
    "konkurrenca":        r"konkurrenc|konkurrue|konkurrent|ndalim.{0,20}konkurr",
    "transferimi":        r"transferim|ndryshim.{0,20}vendit t[ëe] pun",
}
TOPIC_RE = {k: re.compile(v, re.I) for k, v in TOPICS.items()}

flagged, vkm_gaps = [], []
for art in d["nenet"]:
    for p in art["pikat"]:
        t = p["teksti"]
        sig = {
            "kufi_maksimal": bool(CEILING.search(t)),
            "kufi_minimal":  bool(FLOOR.search(t)),
            "detyrim":       bool(DUTY.search(t)),
            "ndalim":        bool(BAN.search(t)),
        }
        nums = [f"{m.group(1)} {m.group(2)}" for m in UNIT.finditer(t)]
        nums += [f"{m.group(1)} {m.group(2)}" for m in WORDNUM.finditer(t)]
        topics = [k for k, rx in TOPIC_RE.items() if rx.search(t)]

        p["sinjale"] = sig
        p["vlera_numerike"] = nums
        p["temat"] = topics
        # a point is checkable if it constrains and is about something a
        # contract puts in writing
        # A number bounded by a ceiling or floor is checkable on its own: the
        # topic list must never be the thing that decides, or a limit whose
        # wording we did not anticipate disappears silently.
        p["i_kontrollueshem"] = bool(
            ((sig["kufi_maksimal"] or sig["kufi_minimal"]) and (nums or topics))
            or sig["ndalim"]
            or (sig["detyrim"] and nums)
        )

        if p["i_kontrollueshem"]:
            flagged.append({
                "neni": art["neni"], "pika": p["pika"], "kreu": art["kreu"],
                "temat": topics, "vlera": nums, "sinjale": sig,
                "teksti": t,
                "ndryshuar_me": art["ndryshuar_me"],
            })
        if VKM.search(t):
            vkm_gaps.append({
                "neni": art["neni"], "pika": p["pika"],
                "temat": topics, "teksti": t,
            })

d["meta"]["pika_te_kontrollueshme"] = len(flagged)
d["meta"]["pika_me_referenca_vkm"] = len(vkm_gaps)

Path("kodi_punes_flagged.json").write_text(
    json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
Path("checklist_kufijve.json").write_text(
    json.dumps({"kufijte": flagged, "boshllekete_vkm": vkm_gaps},
               ensure_ascii=False, indent=2), encoding="utf-8")

from collections import Counter
print(f"checkable points : {len(flagged)}  (across "
      f"{len({f['neni'] for f in flagged})} articles)")
print(f"VKM deferrals    : {len(vkm_gaps)}  (across "
      f"{len({v['neni'] for v in vkm_gaps})} articles)")
print()
print("by topic:")
c = Counter(t for f in flagged for t in f["temat"])
for k, v in c.most_common():
    print(f"  {k:22s} {v:3d}")
