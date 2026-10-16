#!/usr/bin/env python3
"""
Listwise LLM reranker.

Input: a contract clause + a wide pool of candidate law provisions.
Output: a ranked short list (top N).

The model returns ONLY ids and scores. It never writes text. Same design rule
as llm.py - the citation is copied out of the corpus by pipeline.py, verify.py
checks it character-for-character.

Uses the same local vLLM server as llm.py, with guided_json so the response
parses deterministically.
"""
import json, urllib.request, urllib.error, os

API_URL = os.environ.get("OR_API_URL", "http://localhost:8000/v1/chat/completions")
MODEL = os.environ.get("OR_MODEL", "Qwen/Qwen3-14B-AWQ")
KEY = os.environ.get("OPENROUTER_API_KEY", "local")

SYSTEM = """Je nje reranker per nje sistem kontrolli kontratash pune.

Te jepet nje klauzole kontrate dhe nje liste dispozitash te Kodit te Punes te
numeruara me ID. Detyra jote eshte te vleresosh, per secilen dispozite, sa e
lidhur eshte me klauzolen.

SHUME E RENDESISHME:
- Dispozita qe PERCAKTON NJE RREGULL qe klauzola MUND TE SHKELJE meriton 8-10.
- Dispozita qe flet per te njejten TEME por nuk e rregullon klauzolen: 3-5.
- Dispozita pa lidhje: 0-2.

Shembull: klauzola thote "ndalese te pages ditore si sanksion disiplinor".
- Neni 122/3 "ndalohet dhenia e gjobave nga punedhenesi" -> 10 (ndalon saktesisht kete)
- Neni 143 "afati i njoftimit per zgjidhjen e kontrates" -> 1 (pa lidhje)
- Neni 37 "mbrojtja e te drejtave te punemarresit" -> 2 (e pergjithshme)

Rregulla:
- Numri i dispozitave qe shkel klauzola eshte 0 ose 1 ne shumicen e rasteve.
- Mos i jep te gjitheve note te larte.
- Kthe VETEM JSON: {"<id>": <numer 0-10>}
"""


def _post(payload, timeout=120):
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _build_user(clause, pool):
    lines = [f"KLAUZOLA {clause['nr']} ({clause['titulli']}):", clause["teksti"], "", "DISPOZITAT:"]
    for u in pool:
        snippet = u["teksti"][:280].replace("\n", " ")
        lines.append(f"[ID={u['ref']}] {snippet}")
    lines += ["", "Vlereso sa e lidhur eshte secila dispozite me klauzolen. Kthe vetem JSON."]
    return "\n".join(lines)


def rerank(clause, pool, top_k=8, keep_bm25_top=3):
    """Return a ranked list of up to top_k candidates.

    Fallback: if the model call fails or returns garbage, keep the pool order.
    Regression safety: the first keep_bm25_top entries of the incoming pool
    are always kept (they were the BM25 winners); the LLM fills the rest.
    """
    if not pool:
        return []

    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": _build_user(clause, pool)}],
        "temperature": 0,
        "max_tokens": 800,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
    }

    try:
        resp = _post(payload)
        txt = resp["choices"][0]["message"].get("content") or ""
        i, j = txt.find("{"), txt.rfind("}")
        if i < 0 or j <= i:
            raise ValueError("no json in response")
        scores = json.loads(txt[i:j + 1])
    except Exception as e:
        print(f"    [rerank deshtoi, klauzola {clause['nr']}] {type(e).__name__}: {e}")
        return pool[:top_k]

    # build ref -> candidate map
    by_ref = {u["ref"]: u for u in pool}

    # parse scores, defensive; strip any "ID=" prefix the model may add
    ranked = []
    for ref, sc in scores.items():
        ref = str(ref).strip()
        if ref.startswith("ID="):
            ref = ref[3:].strip()
        if ref in by_ref:
            try:
                ranked.append((float(sc), by_ref[ref]))
            except (TypeError, ValueError):
                continue
    ranked.sort(key=lambda x: -x[0])

    # union: LLM top + forced BM25 top
    out, seen = [], set()
    for _s, u in ranked:
        key = (u["neni"], u["pika"])
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
        if len(out) >= top_k:
            break
    for u in pool[:keep_bm25_top]:
        key = (u["neni"], u["pika"])
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
        if len(out) >= top_k:
            break
    return out
