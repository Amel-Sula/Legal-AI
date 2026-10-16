#!/usr/bin/env python3
"""
Step 1 of the pipeline: a contract goes in, numbered clauses come out.

Albanian contracts are not consistently formatted, so this handles the common
shapes: "Neni 4.", "Neni 4 -", "4.", "4)", "KREU II", and ALL-CAPS headings.
Anything before the first recognised clause is kept as a preamble, because the
parties and the signing date live there and the report needs them.
"""
import re, sys, json, unicodedata
from pathlib import Path

# Albanian contracts are often typed without diacritics; fold them so the
# retriever sees the same tokens either way.
FOLD = str.maketrans({"ë": "e", "Ë": "E", "ç": "c", "Ç": "C"})

CLAUSE_PATTERNS = [
    # "Neni 4." / "Neni 4 -" / "NENI 4:" optionally followed by a title
    re.compile(r"^\s*(?:NENI|Neni|neni)\s+(\d+)\s*[\.\-:–]?\s*(.*)$"),
    # "4. Title" at line start, title must start with a capital
    re.compile(r"^\s*(\d{1,2})\s*[\.\)]\s+([A-ZËÇ].*)$"),
    # "PIKA 4"
    re.compile(r"^\s*(?:PIKA|Pika)\s+(\d+)\s*[\.\-:]?\s*(.*)$"),
]


def defold(s: str) -> str:
    return s.translate(FOLD)


def _title_from_next_line(lines, i):
    """Real contracts often print 'Neni 5' on one line and its heading on the
    next. Take that line as the title when it looks like a heading: short, and
    not a sentence."""
    for j in range(i + 1, min(i + 3, len(lines))):
        s = lines[j].strip()
        if not s:
            continue
        if len(s) <= 80 and not s.endswith(".") and not re.match(r"^\d+[\.\)]", s):
            return s, j
        return "", i
    return "", i


def split(text: str):
    lines = text.split("\n")

    # Decide the document's heading style FIRST. If it uses "Neni N" headings,
    # then bare "2." lines are sub-points inside an article, not new clauses —
    # reading them as clauses shreds the document.
    uses_neni = sum(1 for ln in lines if CLAUSE_PATTERNS[0].match(ln)) >= 3
    patterns = CLAUSE_PATTERNS[:1] if uses_neni else CLAUSE_PATTERNS

    marks = []          # (line_index, number, title, title_line)
    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        for rx in patterns:
            m = rx.match(ln)
            if m:
                num = int(m.group(1))
                title = (m.group(2) or "").strip(" .:-–")
                tline = i
                if not title:
                    title, tline = _title_from_next_line(lines, i)
                # numbering must advance, else we are matching a date,
                # an amount or a cross-reference inside running text
                if not marks or num > marks[-1][1]:
                    marks.append((i, num, title, tline))
                break

    clauses = []
    if not marks:
        body = "\n".join(lines).strip()
        return [{"nr": 1, "titulli": "", "teksti": body,
                 "teksti_kerkimit": defold(body), "rreshti": 1}] if body else []

    preamble = "\n".join(lines[: marks[0][0]]).strip()
    if preamble:
        clauses.append({
            "nr": 0, "titulli": "Hyrje / Palet", "teksti": preamble,
            "teksti_kerkimit": defold(preamble), "rreshti": 1,
        })

    for idx, (start, num, title, tline) in enumerate(marks):
        end = marks[idx + 1][0] if idx + 1 < len(marks) else len(lines)
        body = "\n".join(lines[max(start, tline) + 1:end]).strip()
        body = re.sub(r"\n{2,}", "\n", body)
        if not body and title:
            body = title
        if not body:
            continue
        clauses.append({
            "nr": num,
            "titulli": title,
            "teksti": re.sub(r"\s*\n\s*", " ", body).strip(),
            "teksti_kerkimit": defold(re.sub(r"\s*\n\s*", " ", body).strip()),
            "rreshti": start + 1,
        })
    return clauses


if __name__ == "__main__":
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "kontrata_test_01.txt")
    cl = split(src.read_text(encoding="utf-8"))
    print(f"{src.name}: {len(cl)} klauzola\n")
    for c in cl:
        print(f"[{c['nr']:>2}] {c['titulli'][:46]:46s} {len(c['teksti']):4d} shkronja")
        print(f"     {c['teksti'][:96]}")
    Path(src.stem + ".clauses.json").write_text(
        json.dumps(cl, ensure_ascii=False, indent=2), encoding="utf-8")
