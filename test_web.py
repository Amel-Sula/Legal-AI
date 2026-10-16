"""The chat page, driven through Flask's test client, with no model and no GPU.

Checks what the page must never do, not what it looks like:
  - serve a document name or a question as markup
  - let the model's own words reach the page
  - present an unchosen search hit as an answer
  - load anything from the internet
  - keep the uploaded file after the analysis
"""
import os
import re
import sys
import time
from pathlib import Path

PKG = Path(__file__).parent
sys.path.insert(0, str(PKG))
os.chdir(PKG)
os.environ["KONTRATA_MODE"] = "by_id"       # deterministic stub, no vLLM
import web
import llm
import pyet

web.app.config["TESTING"] = True
c = web.app.test_client()

# ------------------------------------------------------------------ 1. kreu
r = c.get("/")
assert r.status_code == 200
faqe = r.get_data(as_text=True)
# Inline script is fine; a script with a src is not, and neither is any
# other reference that would make the page need the network.
for jashte in ("http://", "https://", "cdn.", "//fonts", "src=", "@import"):
    assert jashte not in faqe, f"faqja ngarkon nga jashte: {jashte}"
print("OK 1: kreu hapet dhe nuk ngarkon asgje nga internetit")

# ----------------------------------------------- 2. upload -> biseda, raport
doc = Path("kontrata_qiraje.txt").read_bytes()
r = c.post("/nis", data={"dokument": (__import__("io").BytesIO(doc),
                                     "<script>x</script>.txt")},
           content_type="multipart/form-data", follow_redirects=False)
assert r.status_code == 303, r.status_code
bid = r.headers["Location"].rsplit("/", 1)[-1]

for _ in range(120):
    with web._mbrojtje:
        st = web.BISEDAT[bid]["status"]
    if st in ("gati", "gabim"):
        break
    time.sleep(0.5)
assert st == "gati", (st, web.BISEDAT[bid].get("gabim"))

faqe = c.get(f"/biseda/{bid}").get_data(as_text=True)
assert "<script>x</script>" not in faqe, "emri i skedarit kaloi si markup"
# Path(...).name cuts at the slash inside "</script>", so what is left of the
# name is "script>.txt" -- and that remainder must still arrive escaped.
assert "script&gt;.txt" in faqe, "emri nuk u shpetua fare"
assert "Raporti i verifikuar" in faqe
assert "Kodi Civil" in faqe
print("OK 2: dokumenti u analizua, emri i tij doli si tekst, jo si markup")

# ------------------------------------------- 3. the uploaded file is deleted
mbeturina = list(Path("/tmp").glob("kontrata_web_*"))
assert not mbeturina, f"dosja e dokumentit mbeti: {mbeturina}"
print("OK 3: skedari i ngarkuar u fshi pas analizes")

# --------------------------------- 4. a question: model's prose cannot pass
def fals(payload, timeout=120):
    return {"choices": [{"message": {"content":
        '{"zgjedhjet":[{"citim_id":"C1","teksti":"Afati maksimal eshte 99 vjet.",'
        '"neni":"Neni 9999","shpjegim":"Sipas Kodit Civil."}]}'}}]}


llm._post = fals
web.MODE = "real"
r = c.post(f"/pyet/{bid}", data={"pyetja": "sa vjet mund te lidhet <b>qiraja</b>"},
           follow_redirects=False)
assert r.status_code == 303
faqe = c.get(f"/biseda/{bid}").get_data(as_text=True)
assert "99 vjet" not in faqe, "teksti i modelit kaloi ne faqe"
assert "Neni 9999" not in faqe, "neni i trilluar kaloi"
assert "Sipas Kodit Civil" not in faqe, "shpjegimi i modelit kaloi"
assert "<b>qiraja</b>" not in faqe, "pyetja kaloi si markup"
assert "&lt;b&gt;qiraja&lt;/b&gt;" in faqe
assert "Neni 803" in faqe, "nen-i i vertete nuk doli"
assert "tridhjetë vjet" in faqe, "teksti i korpusit nuk doli"
print("OK 4: modeli shkroi ligj te vetin; faqja nxori Nenin 803 nga korpusi")

# ------------------------- 5. model chooses nothing -> not presented as answer
llm._post = lambda payload, timeout=120: {"choices": [{"message": {
    "content": '{"zgjedhjet":[]}'}}]}
c.post(f"/pyet/{bid}", data={"pyetja": "si behet torta me cokollate"})
faqe = c.get(f"/biseda/{bid}").get_data(as_text=True)
assert "Nuk u gjet dispozitë" in faqe
assert "nuk është përgjigje" in faqe, "u paraqit si pergjigje"
print("OK 5: kur modeli zgjedh asgje, faqja e thote dhe e etiketon te perafertin")

# ------------------------------------------------ 6. questions with no document
r = c.get("/biseda/re", follow_redirects=False)
bid2 = r.headers["Location"].rsplit("/", 1)[-1]
faqe = c.get(f"/biseda/{bid2}").get_data(as_text=True)
assert "Pyet ligjin" in faqe
llm._post = fals
c.post(f"/pyet/{bid2}", data={"pyetja": "sa vjet mund te lidhet kontrata e qirase"})
faqe = c.get(f"/biseda/{bid2}").get_data(as_text=True)
assert "Neni 803" in faqe and "99 vjet" not in faqe
print("OK 6: biseda pa dokument punon, me te njejtat kufizime")

# --------------------------------------------------------- 7. download, 404
assert c.get(f"/raport/{bid}.md").status_code == 200
assert c.get(f"/raport/{bid2}.md").status_code == 404      # no report there
assert c.get("/biseda/nuk-ekziston").status_code == 404
print("OK 7: shkarkimi punon; bisedat pa raport dhe te paqena kthejne 404")

# ------------------------------- 8. the live endpoint renders the same answer
llm._post = lambda payload, timeout=120: {"choices": [{"message": {"content":
    '{"zgjedhjet":[{"citim_id":"C1"}],'
    '"pergjigje":"Jo. Afati maksimal eshte 30 vjet [C1]. '
    'Gjoba eshte 777 leke [C1]."}'}}]}
r = c.post(f"/api/pyet/{bid}", data={"pyetja": "sa vjet zgjat qiraja"})
assert r.status_code == 200
j = r.get_json()
assert "Afati maksimal është 30 vjet" in j["html"] or \
       "Afati maksimal eshte 30 vjet" in j["html"], j["html"][:400]
assert "777" not in j["html"], "numri i trilluar kaloi ne pergjigje"
assert "1 fjali u hoqën" in j["html"], j["html"][:600]
assert "Neni 803" in j["html"]
print("OK 8: /api/pyet kthen pergjigjen e shkruar, me numrin e trilluar te hequr")

# ----------------------------------------- 9. the page carries the chat script
faqe = c.get(f"/biseda/{bid}").get_data(as_text=True)
assert "id=rrjedha" in faqe and "api/pyet" in faqe
assert "textContent" in faqe, "flluska e pyetjes duhet te vendoset si tekst"
print("OK 9: faqja e mban bisedesine pa rifreskim")


# ------------------------------- 10. the first screen is a composer, not a form
faqe = c.get("/").get_data(as_text=True)
assert "class=composer" in faqe, "kreu nuk e ka composer-in"
assert 'action=/nis' in faqe
assert "Ngarko kontratën" in faqe
print("OK 10: kreu eshte nje composer, jo formular")

# a question typed with no document starts a conversation and is answered
llm._post = fals
r = c.post("/nis", data={"pyetja": "sa vjet mund te lidhet kontrata e qirase"},
           follow_redirects=False)
assert r.status_code == 303, r.status_code
bid3 = r.headers["Location"].rsplit("/", 1)[-1]
faqe = c.get(f"/biseda/{bid3}").get_data(as_text=True)
assert "Neni 803" in faqe and "99 vjet" not in faqe
print("OK 11: pyetje pa dokument nga kreu -> biseda me pergjigje")

# a document AND a question: the question waits for the report, then is asked
llm._post = fals
r = c.post("/nis", data={"dokument": (__import__("io").BytesIO(doc), "kontrata.txt"),
                         "pyetja": "sa vjet mund te lidhet kontrata e qirase"},
           content_type="multipart/form-data", follow_redirects=False)
bid4 = r.headers["Location"].rsplit("/", 1)[-1]
for _ in range(120):
    with web._mbrojtje:
        tipat = [m["tip"] for m in web.BISEDAT[bid4]["mesazhet"]]
    if "pergjigje" in tipat or web.BISEDAT[bid4]["status"] == "gabim":
        break
    time.sleep(0.5)
assert tipat.index("raport") < tipat.index("pergjigje"), tipat
print("OK 12: dokument + pyetje -> raporti i pari, pastaj pergjigjja")


# ---------------------------- 13. a document attached to a running conversation
r = c.post("/nis", data={"pyetja": "sa vjet mund te lidhet kontrata e qirase"},
           follow_redirects=False)
bid5 = r.headers["Location"].rsplit("/", 1)[-1]
faqe = c.get(f"/biseda/{bid5}").get_data(as_text=True)
assert "Ngarko një kontratë" in faqe, "biseda pa dokument duhet ta ftoje"
r = c.post(f"/ngarko/{bid5}",
           data={"dokument": (__import__("io").BytesIO(doc), "e_dyta.txt")},
           content_type="multipart/form-data", follow_redirects=False)
assert r.status_code == 303
for _ in range(120):
    with web._mbrojtje:
        st5 = web.BISEDAT[bid5]["status"]
    if st5 in ("gati", "gabim"):
        break
    time.sleep(0.5)
assert st5 == "gati", (st5, web.BISEDAT[bid5].get("gabim"))
with web._mbrojtje:
    tipat5 = [m["tip"] for m in web.BISEDAT[bid5]["mesazhet"]]
    ligjet5 = web.BISEDAT[bid5]["ligjet"]
assert tipat5[:2] == ["pyetje", "pergjigje"], tipat5
assert "raport" in tipat5 and "dokument" in tipat5, tipat5
assert ligjet5, "ligjet e dokumentit nuk hyne ne bisede"
faqe = c.get(f"/biseda/{bid5}").get_data(as_text=True)
assert "Ngarko një kontratë" not in faqe, "ftesa duhet te hiqet pas ngarkimit"
print(f"OK 13: dokumenti u shtua ne bisede ekzistuese; ligjet: {ligjet5}")

# ------------------------------------- 14. Enter sends, Shift+Enter breaks line
assert "e.key==='Enter' && !e.shiftKey" in faqe
assert "<textarea" in faqe
print("OK 14: fusha eshte textarea dhe Enter dergon")


# ------------------------------------------- 15. the conversations are listed
faqe = c.get(f"/biseda/{bid}").get_data(as_text=True)
assert "class=anesore" in faqe, "mungon shiriti i bisedave"
assert "Bisedë e re" in faqe
assert "class='lidhje-bisede tanishme'" in faqe, "biseda e hapur nuk eshte e shenuar"
print("OK 15: shiriti i majte i mban bisedat dhe shenon ate te hapur")

# ------------------------- 16. a huge provision cannot blow the context window
import pyet
h, mp = pyet._kandidatet_me_pika("sa vjet mund te lidhet kontrata e qirase")
e_madhe = dict(mp[0][1]); e_madhe["teksti"] = "x " * 9000
kand = [e_madhe] + [u for _s, u in mp[1:]]
par = {}
llm._post = lambda payload, timeout=120: (par.update(p=payload) or
    {"choices": [{"message": {"content": '{"zgjedhjet":[],"pergjigje":""}'}}]})
pyet._zgjedh_me_model("a duhet leje", kand)
trupi = par["p"]["messages"][1]["content"]
assert len(trupi) < 24000, f"prompti {len(trupi)} shkronja, del nga dritarja"
assert "teksti vazhdon" in trupi, "teksti i gjate duhet te pritet, jo te hiqet"
print(f"OK 16: prompti u mbajt ne {len(trupi)} shkronja (~{len(trupi)//3} token)")


# ---------------------------------- 17. the hidden upload input stays hidden
faqe = c.get(f"/biseda/{bid}").get_data(as_text=True)
import re as _re
stili = _re.search(r"<style>(.*?)</style>", faqe, _re.S).group(1)
assert "#fdok{display:none}" in stili.replace(" ", ""), \
    "forma e ngarkimit del si 'Choose File' nen fushen e pyetjes"
print("OK 17: fusha e fshehur e ngarkimit nuk duket ne faqe")


# ------------------------- 18. a follow-up question inherits the one before it
par = {}
def kap(payload, timeout=120):
    par["p"] = payload
    return {"choices": [{"message": {"content":
        '{"zgjedhjet":[{"citim_id":"C1"}],"pergjigje":"Po [C1]."}'}}]}


llm._post = kap
r = c.post("/nis", data={"pyetja": "sa vjet mund te lidhet kontrata e qirase"},
           follow_redirects=False)
bid6 = r.headers["Location"].rsplit("/", 1)[-1]
with web._mbrojtje:
    cituar = list(web.BISEDAT[bid6].get("ligjet_e_cituara") or [])
assert cituar, "ligjet e cituara nuk u mbajten mend"

c.post(f"/api/pyet/{bid6}", data={"pyetja": "domethen eshte i pavlefshem?"})
trupi = par["p"]["messages"][1]["content"]
assert "BISEDA DERI TANI" in trupi, trupi[:300]
assert "kontrata e qirase" in trupi, "pyetja e meparshme nuk shkoi te modeli"
with web._mbrojtje:
    msg = web.BISEDAT[bid6]["mesazhet"][-1]["p"]
assert msg["lidhur_me_meparshmen"] is True
assert all(d["ligji"] in cituar for d in msg["dispozitat"]), \
    [d["ligji"] for d in msg["dispozitat"]]
print(f"OK 18: pyetja vijuese u lexua me te meparshmen, brenda {cituar}")

# ---------------------- 19. a number without its unit no longer passes a claim
import pyet
kand = [{"titulli_ligjit": "Kodi Civil", "ref": "Neni 725",
         "teksti": "jo me shume se 15 dite nga momenti kur ka marre dijeni"}]
out, hequr = pyet.verifiko_prozen(
    "Kushti i pageses se 15% te tatimit lidhet me kalimin [C1].", kand)
assert out == "" and hequr == 1, (out, hequr)
out2, hequr2 = pyet.verifiko_prozen("Afati eshte 15 dite [C1].", kand)
assert "15 dite" in out2 and hequr2 == 0, (out2, hequr2)
print("OK 19: '15 dite' nuk e vertetoi me '15 perqind'")
