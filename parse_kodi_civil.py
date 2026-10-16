#!/usr/bin/env python3
"""
Parse the consolidated Kodi i Punes (Ligji 7961/1995, as amended through 91/2024)
into one structured record per article.
"""
import re, json, unicodedata
from pathlib import Path

SRC = Path("ligje/kodi_civil.txt")
raw = SRC.read_text(encoding="utf-8")
lines = raw.split("\n")

ART_RE   = re.compile(r"^\s*Neni\s+(\d+(?:/\d+)?)\s*$")
KREU_RE  = re.compile(r"^\s*(KREU\s+[IVXLCDM]+(?:/\d+)?)\s*$")
# Parenthetical amendment annotation, possibly opened on this line
ANNO_OPEN = re.compile(r"^\s*\((Ndryshuar|Shtuar|Shfuqizuar|Riemertuar|Hequr)\b")
# An all-caps structural heading (section / part title)
CAPS_RE  = re.compile(r"^\s*([A-ZËÇ][A-ZËÇ\s\.,;:\-/\"'0-9()]{6,})\s*$")

LAW_RE   = re.compile(r"ligj(?:in|et|i)?\s+nr\.\s*([\d\s]+(?:/\d+)?)\s*,?\s*dat[ëe]\s*([\d\.]+)", re.I)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


POINT_RE  = re.compile(r"(\d{1,2})\.\s+")
LETTER_RE = re.compile(r"\b([a-zç-ë]{1,2})\)\s+")


def split_points(flat: str):
    """Split an article into numbered points (pika), each into lettered
    sub-points (shkronja). These are the units a lawyer actually cites."""
    marks = []
    for m in POINT_RE.finditer(flat):
        # a point marker starts the string or follows end-of-sentence punctuation
        if m.start() == 0 or flat[max(0, m.start() - 2):m.start()] in (". ", "; ", ": "):
            n = int(m.group(1))
            # numbering must ascend from 1, else it's a date or an amount
            if (not marks and n == 1) or (marks and n == marks[-1][0] + 1):
                marks.append((n, m.start(), m.end()))

    if not marks:
        return [{"pika": None, "teksti": flat, "shkronjat": split_letters(flat)}]

    out = []
    if marks[0][1] > 0:
        lead = norm(flat[:marks[0][1]])
        if lead:
            out.append({"pika": None, "teksti": lead, "shkronjat": []})
    for i, (n, _s, e) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(flat)
        body = norm(flat[e:end])
        if body:
            out.append({"pika": n, "teksti": body, "shkronjat": split_letters(body)})
    return out


def split_letters(s: str):
    ms = []
    for m in LETTER_RE.finditer(s):
        if m.start() == 0 or s[max(0, m.start() - 2):m.start()] in ("; ", ": ", ", ", ". "):
            ms.append((m.group(1), m.start(), m.end()))
    if len(ms) < 2:
        return []
    out = []
    for i, (lt, _s, e) in enumerate(ms):
        end = ms[i + 1][1] if i + 1 < len(ms) else len(s)
        body = norm(s[e:end])
        if body:
            out.append({"shkronja": lt, "teksti": body})
    return out


# ---- pass 1: locate article headings and surrounding structure -------------
headings = []  # (line_idx, art_no)
for i, ln in enumerate(lines):
    m = ART_RE.match(ln)
    if m:
        headings.append((i, m.group(1)))

# structural context tracker
kreu_at = {}
caps_at = {}
cur_kreu = None
cur_caps = None
for i, ln in enumerate(lines):
    mk = KREU_RE.match(ln)
    if mk:
        cur_kreu = norm(mk.group(1))
    else:
        mc = CAPS_RE.match(ln)
        if mc and not ART_RE.match(ln) and "FLETOR" not in ln.upper():
            txt = norm(mc.group(1))
            # skip the document's own title block and running headers
            if not txt.startswith(("LIGJ", "KODI I PUNËS", "KUVENDI", "REPUBLIK", "VENDOSI")):
                cur_caps = txt
    kreu_at[i] = cur_kreu
    caps_at[i] = cur_caps


# ---- pass 2: build records ------------------------------------------------
records = {}
for idx, (start, art_no) in enumerate(headings):
    end = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
    block = lines[start + 1:end]

    # peel leading parenthetical amendment annotations
    annos, body_start = [], 0
    j = 0
    while j < len(block):
        s = block[j].strip()
        if not s:
            j += 1
            continue
        if ANNO_OPEN.match(block[j]):
            buf = s
            # annotation may wrap across lines until the closing paren
            while buf.count("(") > buf.count(")") and j + 1 < len(block):
                j += 1
                buf += " " + block[j].strip()
            annos.append(norm(buf).strip("()"))
            j += 1
            continue
        break
    body_start = j

    # drop all-caps structural headings that belong to the NEXT section,
    # not to this article's text
    body_lines = []
    for ln in block[body_start:]:
        mc = CAPS_RE.match(ln)
        if mc and not ART_RE.match(ln):
            t = norm(mc.group(1))
            # a caps line with no lowercase at all is a heading, not legal text
            if not any(c.islower() for c in t):
                continue
        body_lines.append(ln)
    body = "\n".join(body_lines)

    # collapse layout padding but keep paragraph breaks
    paras = [norm(p) for p in re.split(r"\n\s*\n", body) if norm(p)]
    text = "\n".join(paras)

    if not text:
        continue

    pikat = split_points(norm(text))

    # amending laws touching this article
    amend_laws = []
    for a in annos:
        for lm in LAW_RE.finditer(a):
            amend_laws.append({
                "ligji": re.sub(r"\s+", "", lm.group(1)),
                "data": lm.group(2).strip("."),
                "veprimi": a.split()[0],
            })

    rec = {
        "neni": art_no,
        "kreu": kreu_at.get(start),
        "seksioni": caps_at.get(start),
        "teksti": text,
        "pikat": pikat,
        "shenime_ndryshimi": annos,
        "ndryshuar_me": amend_laws,
        "rreshti_burim": start + 1,
        "gjatesia_karaktere": len(text),
    }

    # dedupe: the PDF repeats some closing provisions; keep the longest version
    prev = records.get(art_no)
    if prev is None or len(text) > len(prev["teksti"]):
        records[art_no] = rec


def sort_key(k):
    parts = k.split("/")
    return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)


out = [records[k] for k in sorted(records, key=sort_key)]

meta = {
    "ligji": "7850",
    "data_miratimit": "1994-07-29",
    "titulli": "Kodi Civil i Republikës së Shqipërisë",
    "konsolidim": "i përditësuar",
    "ndryshuar_me_ligjet": [
        {"ligji": "8536", "data": "1999-10-18"},
        {"ligji": "8781", "data": "2001-05-03"},
        {"ligji": "17/2012", "data": "2012-02-16"},
        {"ligji": "121/2013", "data": "2013-04-18"},
        {"ligji": "113/2016", "data": "2016-11-03"},
        {"ligji": "69/Kushtetues", "data": "2023-12-27"},
        {"ligji": "82/2026", "data": "2026-07-23"},
    ],
    "burimi": "Qendra e Botimeve Zyrtare",
    "burimi_url": "https://qbz.gov.al",
    "i_vlefshem_deri": "2026-07-23",
    "numri_neneve": len(out),
}

Path("kodi_civil.json").write_text(
    json.dumps({"meta": meta, "nenet": out}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(f"articles parsed      : {len(out)}")
print(f"with amendment notes : {sum(1 for r in out if r['shenime_ndryshimi'])}")
print(f"total chars of text  : {sum(r['gjatesia_karaktere'] for r in out):,}")
print(f"chapters seen        : {len({r['kreu'] for r in out if r['kreu']})}")
print(f"empty-text skipped   : {len(headings) - len(out)} heading(s)")
print()
print("first 8:", [r["neni"] for r in out[:8]])
print("last 8 :", [r["neni"] for r in out[-8:]])
