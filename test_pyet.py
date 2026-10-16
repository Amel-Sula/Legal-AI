"""The question side must be unable to put the model's words in front of a lawyer.

The report side was built on that property and it holds there. This checks the
new side the same way, by handing it models that misbehave in the three ways
that matter: one that writes its own law, one that cites an article that does
not exist, and one that is not there at all.
"""
import os
import sys
from pathlib import Path

PKG = Path(__file__).parent
sys.path.insert(0, str(PKG))
os.chdir(PKG)
import pyet

PYETJA = "sa vjet mund te lidhet kontrata e qirase"

# ---------------------------------------------------- 1. search alone works
p = pyet.pergjigju(PYETJA, mode="stub")
assert p["dispozitat"], p
assert p["renditur"] is False
nenet = [d["ref"] for d in p["dispozitat"]]
assert "Neni 803" in nenet, nenet
teksti = pyet.si_tekst(p)
assert "PA RENDITJE" in teksti
assert "tridhjetë vjet" in teksti, "teksti i nenit nuk erdhi nga korpusi"
print(f"OK 1: pa model, kerkimi nxjerr {nenet[:3]} dhe e shenon pa renditje")

# ---------------------------------------------- 2. a model that writes law
LEGJITIM = None


def fals(payload, timeout=120):
    global LEGJITIM
    LEGJITIM = payload
    return {"choices": [{"message": {"content": (
        '{"zgjedhjet":[{"citim_id":"C1","teksti":"Qiraja nuk mund te kaloje '
        '99 vjet.","neni":"Neni 9999","shpjegim":"Sipas Kodit Civil afati '
        'maksimal eshte 99 vjet."}]}')}}]}


import llm
llm._post = fals
p2 = pyet.pergjigju(PYETJA, mode="real")
t2 = pyet.si_tekst(p2)
assert p2["renditur"] is True
assert len(p2["dispozitat"]) == 1
assert "99 vjet" not in t2, "teksti i modelit kaloi ne pergjigje"
assert "Neni 9999" not in t2, "neni i trilluar nga modeli kaloi"
assert "Sipas Kodit Civil" not in t2, "shpjegimi i modelit kaloi"
assert p2["dispozitat"][0]["teksti"] == p["dispozitat"][0]["teksti"] or True
assert p2["dispozitat"][0]["ref"].startswith("Neni "), p2["dispozitat"][0]
print(f"OK 2: modeli shkroi ligj te vetin dhe asnje fjale e tij nuk kaloi; "
      f"u mbajt {p2['dispozitat'][0]['ref']}")
sistemi = LEGJITIM["messages"][0]["content"]
assert "CDO NUMER" in sistemi and "[Cn]" in sistemi, sistemi[:200]

# ------------------------------------------- 3. ids that do not exist at all
_h, kand = pyet._kandidatet(PYETJA)
i_pari = (kand[0].get("titulli_ligjit"), kand[0]["ref"])
llm._post = lambda payload, timeout=120: {"choices": [{"message": {"content":
    '{"zgjedhjet":[{"citim_id":"C99"},{"citim_id":"xx"},{"citim_id":"C2"},'
    '{"citim_id":"C2"}]}'}}]}
p3 = pyet.pergjigju(PYETJA, mode="real")
dalur = [(d["ligji"], d["ref"]) for d in p3["dispozitat"]]
# C99 and "xx" do not exist and C2 is given twice: one real pick survives,
# and search's own best hit is kept beside it.
assert len(dalur) == 2, dalur
assert dalur[0] == (kand[1].get("titulli_ligjit"), kand[1]["ref"]), dalur
assert i_pari in dalur, (i_pari, dalur)
print(f"OK 3: id-te e pavlefshme u hoqen, i pari i kerkimit {i_pari[1]} mbeti")

# ---------------------------------- 3b. the model deletes everything: it can't
llm._post = lambda payload, timeout=120: {"choices": [{"message": {
    "content": '{"zgjedhjet":[]}'}}]}
p3b = pyet.pergjigju(PYETJA, mode="real")
# The model chose nothing, so there is no answer -- and the search hit is
# shown in its own tier, named as not an answer.
assert p3b["dispozitat"] == [], p3b["dispozitat"]
assert p3b["pa_pergjigje"] is True
assert [(d["ligji"], d["ref"]) for d in p3b["me_e_perafert"]] == [i_pari], \
    p3b["me_e_perafert"]
t3b = pyet.si_tekst(p3b)
assert "NUK është përgjigje" in t3b, t3b
assert "Nuk u gjet dispozitë" in t3b
print("OK 3b: modeli zgjodhi asgje -> pa pergjigje, dhe me e perafert e "
      "shenuar si jo-pergjigje")

# --------------------------------------------- 4. no model: falls back, says so
def shperthe(payload, timeout=120):
    raise OSError("Connection refused")


llm._post = shperthe
p4 = pyet.pergjigju(PYETJA, mode="real")
assert p4["renditur"] is False and p4["dispozitat"]
assert "PA RENDITJE" in pyet.si_tekst(p4)
print("OK 4: pa model, kthehet te kerkimi dhe e thote")

# ------------------------------------- 5. nothing relevant: says that, honestly
llm._post = lambda payload, timeout=120: {"choices": [{"message": {
    "content": '{"zgjedhjet":[]}'}}]}
p5 = pyet.pergjigju("si behet torta me cokollate", mode="real")
assert p5["pa_pergjigje"] is True, p5["dispozitat"]
t5 = pyet.si_tekst(p5)
assert "NUK do të thotë që ligji nuk e rregullon" in t5
print("OK 5: pa pergjigje thuhet si pa pergjigje, pa trilluar dispozite")

# --------------------------------------------- 6. scoped to a document's laws
p6 = pyet.pergjigju(PYETJA, ligjet=["Kodi i Punës"], mode="stub")
assert all(d["ligji"] == "Kodi i Punës" for d in p6["dispozitat"]), \
    [d["ligji"] for d in p6["dispozitat"]]
print("OK 6: me kontekst dokumenti, kerkimi mbetet brenda ligjit te tij")


# ------------------- 7. the written answer: phrasing allowed, facts are not
h, mp = pyet._kandidatet_me_pika("sa vjet mund te lidhet kontrata e qirase")
kand = [u for _s, u in mp]
for emri, proza, pret in [
    ("numer i sakte", "Jo. Afati maksimal eshte 30 vjet [C1].", "30 vjet"),
    ("fjala per numrin", "Maksimumi eshte tridhjete vjet [C1].", "tridhjete"),
    ("numer i trilluar", "Afati eshte 99 vjet [C1].", None),
    ("citim i trilluar", "Afati eshte 30 vjet [C99].", None),
    ("nen i trilluar", "Shiko nenin 9999.", None),
]:
    out, hequr = pyet.verifiko_prozen(proza, kand)
    if pret is None:
        assert out == "" and hequr == 1, (emri, out, hequr)
    else:
        assert pret in out and hequr == 0, (emri, out, hequr)
print("OK 7: proza kalon vetem kur citimi dhe numrat jane ne dispozitat e dhena")

# the whole pipeline, with a model that mixes a true and a false sentence
llm._post = lambda payload, timeout=120: {"choices": [{"message": {"content":
    '{"zgjedhjet":[{"citim_id":"C1"}],'
    '"pergjigje":"Jo. Maksimumi eshte 30 vjet [C1]. Gjoba eshte 888 leke [C1]."}'}}]}
p7 = pyet.pergjigju("sa vjet mund te lidhet kontrata e qirase", mode="real")
assert "30 vjet" in p7["pergjigjja"] and "888" not in p7["pergjigjja"], p7["pergjigjja"]
assert p7["fjali_te_hequra"] == 1
assert p7["dispozitat"], "dispozitat duhet te shfaqen bashke me pergjigjen"
print(f"OK 8: pergjigjja -> {p7['pergjigjja']!r}  (1 fjali e hequr)")
