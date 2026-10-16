#!/usr/bin/env python3
"""The product as a lawyer sees it: a conversation about one document.

    python3 web.py            then open http://127.0.0.1:7000

The page is a chat, because that is what a lawyer actually does with a
document: reads the report, then asks the next question. But the two halves of
the conversation are not the same kind of thing, and the page never lets them
look the same:

  THE REPORT is produced by the full pipeline -- clause by clause, every
  citation verified against the corpus it came from, every figure checked.

  AN ANSWER to a typed question is retrieval. The model is handed the
  provisions the search found and returns which of them answer the question,
  by number. It writes nothing. The text on screen is copied out of the corpus
  by code, so there is no path from the model's own memory of Albanian law to
  the lawyer's eyes. When the model picks nothing, there is no answer, and the
  nearest search hit appears under a heading that says it is not one.

FIVE THINGS HERE ARE SAFETY, NOT CONVENIENCE, and each is the default.

BINDS TO 127.0.0.1. Not 0.0.0.0. On 0.0.0.0 every machine on the office wifi
can open a page that reads client contracts, with no password. The whole
product is sold on client documents never leaving the building; the server
must not be the hole in that. KONTRATA_HOST overrides it and the override
prints a warning, because somebody will eventually need it and should know
what they are doing.

THE DOCUMENT IS DELETED when the analysis finishes. Only the report stays, in
memory. A folder quietly accumulating years of client contracts is a breach
waiting for a stolen laptop, and under Law 9887 it is data held longer than
the purpose requires.

CONVERSATIONS LIVE IN MEMORY and die with the process. Nothing about a client
document is written to disk, including the questions asked about it.

TWO ANALYSES AT A TIME, measured rather than guessed (see NJEKOHESISHT).

NOTHING IS LOADED FROM THE INTERNET: no fonts, no scripts, no stylesheets.
The page works with the network cable pulled out, which is the machine this is
meant to run on.
"""
import html
import os
import re
import threading
import traceback
import uuid
from datetime import date, datetime
from pathlib import Path
from tempfile import mkdtemp

from flask import Flask, abort, redirect, request, Response

import analizo
import ingest
import pyet

HOST = os.environ.get("KONTRATA_HOST", "127.0.0.1")
PORT = int(os.environ.get("KONTRATA_PORT", "7000"))
MODE = os.environ.get("KONTRATA_MODE", "real")
MAX_MB = 40

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024

# conversation id -> dict, in memory on purpose (see the header).
BISEDAT = {}

# HOW MANY AT ONCE. Two, and the two comes from a measurement, not a guess.
#
# A lock of one was never a decision, it was the absence of one. This is what
# mat_paralelizmin.py measured on the A5000, Qwen3-14B-AWQ at 8192 context,
# the lease contract, ten questions each:
#
#     njekohesisht   vonesa   dok/min        vonesa   dok/min
#                     (para rregullimit)     (pas)
#          1          5.6s      10.8          2.6s      23.5
#          2          9.5s      12.6          3.4s      35.0
#          4         37.3s       6.4          8.0s      29.9
#          8         78.9s       6.1         15.7s      30.5
#
# The first pair of columns is why this was ever a question: throughput PEAKED
# at two and then halved. Measured again with the model switched off, the
# collapse was identical, so it was never the GPU -- it was the law's BM25
# sub-index and the verifier being rebuilt per document, pure Python, serialised
# by the interpreter lock. Both are cached now and the second pair is the result.
#
# Two is still the setting, but for a different reason than before: throughput
# peaks there, and a semaphore of two clears eight simultaneous uploads faster
# (8 / 35 per min = 13.7s) than letting all eight run at once (15.7s). What
# changed is the ceiling -- about 2,100 documents an hour.
#
# Determinism held at every level: the same document gave the same findings
# whether it ran alone or alongside seven others.
#
#     KONTRATA_NJEKOHESISHT=1 python3 web.py     # back to one at a time
NJEKOHESISHT = max(1, int(os.environ.get("KONTRATA_NJEKOHESISHT", "2")))
RRESHTI = threading.Semaphore(NJEKOHESISHT)
_mbrojtje = threading.Lock()    # guards BISEDAT


# ----------------------------------------------------------------- markdown
# The report is Markdown. Rather than adding a dependency to render four
# constructs, this handles exactly the ones render() emits -- and escapes
# first, so a document named "<script>.docx" is text and not markup.
def _inline(s):
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])", r"<em>\1</em>", s)
    return re.sub(r"`([^`]+?)`", r"<code>\1</code>", s)


def ne_html(md):
    out, lista, cit = [], False, False
    # The item being built, as RAW text. Emphasis is applied when the item is
    # finished, never line by line: a provision quoted inside a bullet carries
    # the newlines of the PDF it came from, so its opening *" and closing "*
    # land on different lines. Formatted per line, each marker found no partner
    # and was printed as itself, which is how the report filled up with stray
    # asterisks and half-quotes.
    pjesa = {"tekst": None, "klase": ""}

    def mbyll_pjesen():
        if pjesa["tekst"] is not None:
            kl = f" class={pjesa['klase']}" if pjesa["klase"] else ""
            out.append(f"<li{kl}>{_inline(pjesa['tekst'])}</li>")
            pjesa["tekst"] = None
            pjesa["klase"] = ""

    def mbyll():
        nonlocal lista, cit
        mbyll_pjesen()
        if lista:
            out.append("</ul>")
            lista = False
        if cit:
            out.append("</blockquote>")
            cit = False

    for raw in html.escape(md or "").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            mbyll()
            continue
        # A bullet, at any indent. The indented ones carry the per-law
        # freshness warnings and used to fall through as a paragraph that
        # began with a stray hyphen.
        m_pika = re.match(r"^(\s*)-\s+(.*)$", line)
        if m_pika:
            if cit:
                out.append("</blockquote>")
                cit = False
            mbyll_pjesen()
            if not lista:
                out.append("<ul>")
                lista = True
            pjesa["tekst"] = m_pika.group(2)
            pjesa["klase"] = "nenliste" if m_pika.group(1) else ""
            continue
        # Anything that is not a new construct continues the bullet above it.
        if pjesa["tekst"] is not None and not re.match(r"^(&gt;|#{1,4}\s)", line):
            pjesa["tekst"] += " " + line.strip()
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            mbyll()
            n = len(m.group(1))
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
            continue
        if line.startswith("&gt;"):
            trup = re.sub(r"^&gt;\s?", "", line)
            if not cit:
                mbyll()
                out.append("<blockquote>")
                cit = True
            m2 = re.match(r"^(#{1,4})\s+(.*)$", trup)
            if m2:
                out.append(f"<h4>{_inline(m2.group(2))}</h4>")
            elif trup.startswith("- "):
                out.append(f"<div class=rr>{_inline(trup[2:])}</div>")
            elif trup.strip():
                out.append(f"<p>{_inline(trup)}</p>")
            continue
        mbyll()
        out.append(f"<p>{_inline(line)}</p>")
    mbyll()
    return "\n".join(out)


# ----------------------------------------------------------------- stili
STILI = """
/* NJE PALETE, JO NJE NGJYRE. The first version was ink on paper and nothing
   else, and read as a document rather than a product. Each colour here has a
   job: indigo carries the product's own voice (the answer, the send button),
   gold marks a provision that sets a limit, red marks text that may be out of
   date, green marks a text we know is current. Nothing is decorative -- a
   colour a lawyer cannot name the meaning of is noise. */
:root{
--mur:#faf8f5;--mur2:#f2eee7;--leter:#fff;--bri:#e6e1d8;--bri2:#d6d0c4;
--bojë:#1c1a19;--zbehte:#6e6861;--zbehte2:#948d84;
--indigo:#2f3f6b;--indigoZbehte:#eef1f8;--indigoFort:#1f2b4d;
--ar:#b8860b;--arZbehte:#fdf6e3;
--kuq:#9c3522;--kuqZbehte:#fdf2ef;
--jeshil:#2f6b45;--jeshilZbehte:#edf5f0;
--hije:0 1px 2px rgba(28,26,25,.05);--hije2:0 4px 20px rgba(28,26,25,.07);
--rr:14px}
*{box-sizing:border-box}
body{margin:0;background:var(--mur);color:var(--bojë);
font:16px/1.65 ui-serif,Georgia,"Times New Roman",serif;
background-image:radial-gradient(900px 420px at 88% -12%,var(--indigoZbehte),transparent 62%),
radial-gradient(760px 380px at -8% 8%,var(--arZbehte),transparent 60%);
background-attachment:fixed}
.sans{font-family:ui-sans-serif,system-ui,-apple-system,sans-serif}
h1,h2,h3{letter-spacing:-.3px}

/* ---------------------------------------------------------------- hyrja */
.hyrja{max-width:1120px;margin:0 auto;padding:11vh 32px 110px;
display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,.85fr);
gap:60px;align-items:start}
.hyrja .majtas{min-width:0}
.marka{display:inline-flex;align-items:center;gap:9px;margin:0 0 22px;
font-family:ui-sans-serif,system-ui,sans-serif;font-size:12.5px;
letter-spacing:1.3px;text-transform:uppercase;color:var(--indigo)}
.marka b{display:inline-block;width:9px;height:9px;border-radius:3px;
background:var(--indigo);transform:rotate(45deg)}
.hyrja h1{font-size:clamp(30px,4vw,44px);margin:0 0 14px;line-height:1.15;
font-weight:600}
.hyrja h1 em{font-style:normal;color:var(--indigo)}
.hyrja .nen{color:var(--zbehte);font-size:16.5px;margin:0 0 30px;max-width:50ch}
.rene{border:1.5px dashed var(--bri2);border-radius:var(--rr);padding:3px;
transition:border-color .15s,background .15s}
.rene.aktive{border-color:var(--indigo);background:var(--indigoZbehte)}
.composer{display:flex;align-items:flex-end;gap:8px;background:var(--leter);
border:1px solid var(--bri);border-radius:12px;padding:9px 9px 9px 11px;
box-shadow:var(--hije2);transition:border-color .15s}
.composer:focus-within{border-color:var(--indigo)}
.composer textarea{flex:1;border:0;background:transparent;font:inherit;
font-size:16.5px;color:var(--bojë);outline:0;padding:9px 2px;min-width:0;
resize:none;max-height:190px;line-height:1.55;font-family:inherit}
.composer input[type=file],.poshte input[type=file],#fdok{display:none}
.kapese{display:flex;align-items:center;justify-content:center;width:38px;
height:38px;border-radius:10px;color:var(--zbehte);cursor:pointer;margin:0;
flex:none;transition:background .13s,color .13s}
.kapese:hover{background:var(--indigoZbehte);color:var(--indigo)}
.kapese svg,.composer button svg{display:block;width:19px;height:19px;flex:none}
.composer button{display:flex;align-items:center;justify-content:center;
width:38px;height:38px;border:0;border-radius:10px;background:var(--indigo);
color:#fff;cursor:pointer;flex:none;padding:0;transition:background .13s}
.composer button:hover{background:var(--indigoFort)}
.composer button:disabled{background:var(--bri2);cursor:default}
.skedari{margin:11px 3px 0;min-height:1.3em;color:var(--indigo);font-weight:600}
.nen-composer{margin:7px 3px 0}
.vogel{font-size:13.5px;color:var(--zbehte);
font-family:ui-sans-serif,system-ui,sans-serif}
.cipat{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0 0}
.cip{font-family:ui-sans-serif,system-ui,sans-serif;font-size:13.5px;
padding:8px 14px;border-radius:999px;border:1px solid var(--bri);
background:var(--leter);color:var(--zbehte);cursor:pointer;
transition:border-color .13s,color .13s}
.cip:hover{border-color:var(--indigo);color:var(--indigo)}

/* kolona e djathte: pse duhet dokumenti */
.djathtas{min-width:0}
.ftesa{background:var(--leter);border:1px solid var(--bri);
border-radius:var(--rr);padding:24px 26px;box-shadow:var(--hije)}
.ftesa h2{font-size:18px;margin:0 0 6px}
.ftesa p{margin:0 0 18px;font-size:14.5px;color:var(--zbehte)}
.hapat{list-style:none;margin:0;padding:0;counter-reset:h}
.hapat li{counter-increment:h;display:flex;gap:13px;margin:0 0 15px;
font-size:14.5px;line-height:1.5}
.hapat li::before{content:counter(h);flex:none;width:23px;height:23px;
border-radius:7px;background:var(--indigoZbehte);color:var(--indigo);
font-family:ui-sans-serif,system-ui,sans-serif;font-size:12.5px;font-weight:600;
display:flex;align-items:center;justify-content:center;margin-top:2px}
.ftesa .butoni{display:block;width:100%;margin-top:4px;padding:12px;
border:0;border-radius:10px;background:var(--indigo);color:#fff;font:inherit;
font-size:15px;cursor:pointer;text-align:center;
font-family:ui-sans-serif,system-ui,sans-serif}
.ftesa .butoni:hover{background:var(--indigoFort)}
.te-fundit{grid-column:1/-1;margin-top:10px}
.rresht-bisede{display:flex;align-items:center;gap:13px;padding:12px 15px;
margin:0 -15px;border-radius:10px;text-decoration:none;color:var(--bojë)}
.rresht-bisede:hover{background:var(--leter);box-shadow:var(--hije)}
.rresht-bisede .emri{flex:1;font-size:15px;overflow:hidden;
text-overflow:ellipsis;white-space:nowrap}
.rresht-bisede .ora{font-size:12.5px;color:var(--zbehte2);
font-family:ui-sans-serif,system-ui,sans-serif}
@media(max-width:860px){.hyrja{grid-template-columns:1fr;gap:34px;padding:7vh 20px 110px}}

/* --------------------------------------------------- shiriti i bisedave */
.shtresa{display:flex;min-height:100vh}
.anesore{width:252px;flex:none;border-right:1px solid var(--bri);
background:rgba(255,255,255,.55);padding:18px 12px;position:sticky;top:0;
height:100vh;overflow-y:auto}
.anesore .marka{margin:4px 10px 16px;font-size:12px}
.e-re{display:flex;align-items:center;gap:9px;margin:0 0 18px;padding:10px 12px;
border-radius:10px;background:var(--indigo);color:#fff;text-decoration:none;
font-family:ui-sans-serif,system-ui,sans-serif;font-size:14px;font-weight:600}
.e-re:hover{background:var(--indigoFort)}
.anesore .titull{font-size:11px;letter-spacing:.9px;text-transform:uppercase;
color:var(--zbehte2);font-family:ui-sans-serif,system-ui,sans-serif;
margin:0 12px 7px}
.lidhje-bisede{display:block;padding:9px 12px;border-radius:9px;
text-decoration:none;color:var(--bojë);font-size:14px;line-height:1.35;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lidhje-bisede:hover{background:var(--mur2)}
.lidhje-bisede.tanishme{background:var(--indigoZbehte);color:var(--indigoFort);
font-weight:600}
.lidhje-bisede small{display:block;font-size:11.5px;color:var(--zbehte2);
font-family:ui-sans-serif,system-ui,sans-serif;font-weight:400}
.kryesore{flex:1;min-width:0}
@media(max-width:900px){.anesore{display:none}}

/* ---------------------------------------------------------------- biseda */
.ballina{position:sticky;top:0;z-index:5;background:rgba(250,248,245,.9);
backdrop-filter:blur(10px);border-bottom:1px solid var(--bri)}
.ballina .brenda{max-width:900px;margin:0 auto;padding:13px 28px;
display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.ballina h1{font-size:17px;margin:0;font-weight:600}
.ballina .meta{font-size:13px;color:var(--zbehte);
font-family:ui-sans-serif,system-ui,sans-serif}
.ballina a{color:var(--indigo);text-decoration:none;font-weight:600}
.biseda{max-width:900px;margin:0 auto;padding:28px 28px 200px}
.msg{margin:0 0 24px}
.etiketa{font-size:11.5px;letter-spacing:.9px;text-transform:uppercase;
color:var(--zbehte2);font-family:ui-sans-serif,system-ui,sans-serif;margin:0 0 8px}
.pyetje{display:flex;justify-content:flex-end}
.pyetje .flluska{background:var(--indigo);color:#fff;padding:12px 18px;
border-radius:16px 16px 5px 16px;max-width:74%;font-size:16px;
white-space:pre-wrap}
.kart{background:var(--leter);border:1px solid var(--bri);
border-radius:var(--rr);padding:23px 26px;box-shadow:var(--hije)}
.kart.e-ngushte{padding:16px 19px}
.kart.pergjigjja{border-left:4px solid var(--indigo);
background:linear-gradient(90deg,var(--indigoZbehte) 0 3px,var(--leter) 3px)}
.teksti-pergj{margin:0;font-size:17.5px;line-height:1.62}
.vogel.hequr{margin:8px 0 0;color:var(--kuq)}

/* dispozitat, ne rrjete kur ka vend */
.rrjeta{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));
gap:16px}
.disp{border-left:3px solid var(--ar);padding:3px 0 3px 16px}
.disp .koka{font-family:ui-sans-serif,system-ui,sans-serif;font-size:13.5px;
color:var(--zbehte);margin:0 0 8px;display:flex;gap:8px;flex-wrap:wrap;
align-items:center}
.disp .nen{font-weight:700;color:var(--bojë);font-size:15px}
.disp .tekst{white-space:pre-wrap;font-size:15.5px;margin:0}
.disp.jo-pergjigje{border-left-color:var(--bri2);opacity:.9}
.disp.vjeter{border-left-color:var(--kuq)}
.disp.vdekur{border-left-color:var(--kuq);background:var(--kuqZbehte);
border-radius:0 9px 9px 0;padding-right:14px}
.shenje{display:inline-block;padding:3px 10px;border-radius:999px;
font-size:11.5px;font-family:ui-sans-serif,system-ui,sans-serif;
white-space:nowrap;font-weight:600}
.sh-kufi{background:var(--arZbehte);color:var(--ar)}
.sh-vjeter{background:var(--kuqZbehte);color:var(--kuq)}
.sh-vdekur{background:var(--kuq);color:#fff}
.sh-ok{background:var(--jeshilZbehte);color:var(--jeshil)}
.vogel.ndarje{margin-top:17px;padding-top:14px;border-top:1px solid var(--mur2)}

/* fusha e poshtme */
.poshte{position:fixed;left:252px;right:0;bottom:0;z-index:6;
background:linear-gradient(to top,var(--mur) 58%,rgba(250,248,245,0));
padding:26px 28px 24px}
.poshte .brenda{max-width:900px;margin:0 auto}
.poshte .nen-fushe{margin:10px auto 0;text-align:center;max-width:900px}
.ftese-dok{max-width:900px;margin:0 auto 12px;display:flex;align-items:center;
gap:12px;background:var(--indigoZbehte);border:1px solid #dde3f2;
border-radius:11px;padding:11px 16px;font-size:14.5px;color:var(--indigoFort);
font-family:ui-sans-serif,system-ui,sans-serif}
.ftese-dok b{font-weight:600}
.ftese-dok .veprim{margin-left:auto;color:var(--indigo);cursor:pointer;
font-weight:600;white-space:nowrap}

/* raporti */
.rap h1{font-size:20px;margin:0 0 14px}
.rap h2{font-size:17px;margin:30px 0 6px;padding-top:17px;
border-top:1px solid var(--mur2)}
.rap h3,.rap h4{font-size:15px;margin:16px 0 4px}
.rap blockquote{margin:14px 0;padding:14px 18px;background:var(--arZbehte);
border-left:3px solid var(--ar);border-radius:0 9px 9px 0;font-size:14.5px}
.rap blockquote .rr{margin:3px 0}
.rap ul{padding-left:22px}.rap li{margin:5px 0}
.rap li.nenliste{list-style:none;margin:8px 0 8px -10px;padding:10px 14px;
background:var(--kuqZbehte);border-radius:9px;font-size:14px}
.rap code{background:var(--mur2);padding:1px 6px;border-radius:5px;font-size:13px}
.rap em{color:#4a453d}
.gab{background:var(--kuqZbehte);border-color:#eccec5;color:#73281a}
.flamur{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;
font-family:ui-sans-serif,system-ui,sans-serif;font-weight:600}
.pune{background:var(--arZbehte);color:var(--ar)}
.gati{background:var(--jeshilZbehte);color:var(--jeshil)}
.keq{background:var(--kuqZbehte);color:var(--kuq)}
.pulso{display:inline-block;width:8px;height:8px;border-radius:50%;
background:var(--ar);margin-right:8px;animation:p 1.4s ease-in-out infinite}
@keyframes p{0%,100%{opacity:.25}50%{opacity:1}}
.mendon{display:flex;gap:5px;align-items:center;padding:4px 0}
.mendon i{width:7px;height:7px;border-radius:50%;background:var(--indigo);
display:inline-block;animation:m 1.3s ease-in-out infinite}
.mendon i:nth-child(2){animation-delay:.18s}
.mendon i:nth-child(3){animation-delay:.36s}
@keyframes m{0%,70%,100%{opacity:.22;transform:translateY(0)}
35%{opacity:.95;transform:translateY(-3px)}}
@media(max-width:900px){.poshte{left:0}}
@media(max-width:700px){.biseda,.ballina .brenda{padding-left:18px;padding-right:18px}
.poshte{padding:18px 16px 16px}.rrjeta{grid-template-columns:1fr}}

@media(prefers-color-scheme:dark){
:root{--mur:#15161a;--mur2:#1f2026;--leter:#1c1d23;--bri:#2e3039;--bri2:#3d404c;
--bojë:#e9e6e0;--zbehte:#9a948c;--zbehte2:#746e67;
--indigo:#8fa6dd;--indigoZbehte:#1e2231;--indigoFort:#a6b8e6;
--ar:#d6a73a;--arZbehte:#262013;
--kuq:#e08469;--kuqZbehte:#2a1a16;
--jeshil:#86c79b;--jeshilZbehte:#17241c;
--hije:0 1px 2px rgba(0,0,0,.3);--hije2:0 4px 20px rgba(0,0,0,.35)}
body{background-image:radial-gradient(900px 420px at 88% -12%,#1a1f30,transparent 62%),
radial-gradient(760px 380px at -8% 8%,#221d12,transparent 60%)}
.ballina{background:rgba(21,22,26,.9)}
.poshte{background:linear-gradient(to top,var(--mur) 58%,rgba(21,22,26,0))}
.pyetje .flluska{background:#3a4a7a;color:#fff}
.composer button{color:#15161a}
.sh-vdekur{background:#9c3522;color:#fff}
.ftese-dok{border-color:#2b3147}
.kart.pergjigjja{background:linear-gradient(90deg,var(--indigoZbehte) 0 3px,var(--leter) 3px)}}
"""


def faqe(titull, trup, rifresko=0, klase="kuti"):
    meta = (f'<meta http-equiv="refresh" content="{rifresko}">' if rifresko else "")
    return Response(f"""<!doctype html><html lang=sq><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">{meta}
<title>{html.escape(titull)}</title><style>{STILI}</style>
{f'<div class=shtresa>{trup}</div>' if klase is None else f'<div class="{klase}">{trup}</div>'}""",
                    mimetype="text/html; charset=utf-8")


# ----------------------------------------------------------------- kreu
@app.get("/")
def kreu():
    """THE FIRST SCREEN IS THE CHAT, AND IT ASKS FOR A DOCUMENT.

    It opened as a form, then as a bare composer floating in the middle of an
    empty page. Both were wrong in the same way: nothing on screen told a
    lawyer what this is for. The product is worth most when it has a contract
    to read a document against, so the right-hand column says so, the drop zone
    takes a file dragged anywhere onto the page, and the chips offer questions
    worth asking. A question alone still works -- it is simply not the thing
    being encouraged.
    """
    with _mbrojtje:
        te_fundit = sorted(BISEDAT.items(),
                           key=lambda kv: -kv[1]["koha"].timestamp())[:8]
        rreshtat = "".join(
            f"<a class=rresht-bisede href='/biseda/{i}'>"
            f"<span class=emri>{html.escape(b['emri'])}</span>"
            f"<span class='flamur {_flamur(b)[0]}'>{_flamur(b)[1]}</span>"
            f"<span class=ora>{b['koha'].strftime('%H:%M')}</span></a>"
            for i, b in te_fundit)
    lista = (f"<div class=te-fundit><p class=etiketa>Bisedat e fundit</p>"
             f"{rreshtat}</div>") if rreshtat else ""
    cipat = "".join(
        f"<button type=button class=cip data-pyetje=\"{html.escape(x)}\">"
        f"{html.escape(x)}</button>"
        for x in ("Sa vjet mund të lidhet kontrata e qirasë?",
                  "A mund të jetë paga nën pagën minimale?",
                  "Kur mund të zgjidhet menjëherë kontrata e punës?",
                  "Sa ditë pushime vjetore ka punëmarrësi?"))
    return faqe("Kontrata AI", f"""
<div class=hyrja>
  <div class=majtas>
    <p class=marka><b></b> Kontrata AI</p>
    <h1>Ngarko kontratën.<br><em>Kthehet nen për nen.</em></h1>
    <p class=nen>Çdo klauzolë lexohet kundrejt legjislacionit shqiptar dhe
    raporti citon nenin, ligjin dhe datën e tekstit. Mund edhe vetëm ta pyesësh
    ligjin — por kur ka një dokument përballë, programi bën punën e vet.</p>

    <div class=rene id=rene>
      <form id=nis method=post action=/nis enctype=multipart/form-data>
        <div class=composer>
          <label class=kapese for=dok title="Ngarko dokument">
            <svg viewBox="0 0 24 24" fill=none stroke=currentColor
                 stroke-width=1.7 stroke-linecap=round><path d="M20 11.5l-8 8a5 5 0
                 01-7-7l8.5-8.5a3.3 3.3 0 014.7 4.7L9.6 17.3a1.7 1.7 0 01-2.4-2.4
                 L15 7"/></svg>
          </label>
          <input id=dok type=file name=dokument
                 accept=".pdf,.docx,.txt,application/pdf">
          <textarea id=q name=pyetja rows=1 autofocus maxlength=400
            placeholder="Lësho këtu një kontratë, ose shkruaj një pyetje…"></textarea>
          <button type=submit aria-label=Dërgo>
            <svg viewBox="0 0 24 24" fill=none stroke=currentColor
                 stroke-width=2.4 stroke-linecap=round stroke-linejoin=round>
              <path d="M12 19V5M5 12l7-7 7 7"/></svg>
          </button>
        </div>
      </form>
    </div>
    <p id=zgjedhur class="vogel skedari"></p>
    <p class="vogel nen-composer">Enter dërgon, Shift+Enter bën rresht të ri.
    Skedari fshihet sapo mbaron analiza, dhe asgjë nuk del nga ky kompjuter.</p>
    <div class=cipat>{cipat}</div>
  </div>

  <div class=djathtas>
    <div class=ftesa>
      <h2>Me një dokument përballë</h2>
      <p>Pyetjet e thata kërkojnë në korpus. Një dokument i vërtetë nxjerr
      konflikte që nuk do t'i kishe pyetur.</p>
      <ol class=hapat>
        <li>Lexon çdo klauzolë dhe gjen nenin që e rregullon.</li>
        <li>Krahason afatet e kufijtë: 40 vjet qira kundrejt 30 që lejon ligji.</li>
        <li>Verifikon çdo citim kundrejt tekstit të QBZ-së dhe tregon datën.</li>
        <li>Pastaj pyete lirisht për çdo klauzolë.</li>
      </ol>
      <button type=button class=butoni id=zgjidh>Zgjidh një dokument</button>
    </div>
  </div>
  {lista}
</div>
<script>
(function(){{
  var dok=document.getElementById('dok'), q=document.getElementById('q'),
      zg=document.getElementById('zgjedhur'), f=document.getElementById('nis'),
      rene=document.getElementById('rene');
  document.getElementById('zgjidh').addEventListener('click',function(){{dok.click();}});
  function trego(){{
    var emri = dok.files && dok.files[0] ? dok.files[0].name : '';
    zg.textContent = emri ? ('Gati për analizë: ' + emri) : '';
    if(emri) q.placeholder='Shto një pyetje për këtë dokument (fakultative)…';
  }}
  dok.addEventListener('change', trego);
  // Dragging a file anywhere onto the page is the shortest path to the thing
  // this product is for, so the whole window is the drop zone, not a strip.
  ['dragenter','dragover'].forEach(function(e){{
    window.addEventListener(e,function(ev){{ev.preventDefault();
      rene.classList.add('aktive');}});}});
  ['dragleave','drop'].forEach(function(e){{
    window.addEventListener(e,function(ev){{ev.preventDefault();
      if(e==='dragleave' && ev.relatedTarget) return;
      rene.classList.remove('aktive');}});}});
  window.addEventListener('drop',function(ev){{
    if(ev.dataTransfer && ev.dataTransfer.files.length){{
      dok.files = ev.dataTransfer.files; trego(); q.focus();}}
  }});
  // Enter sends, Shift+Enter makes a new line.
  q.addEventListener('keydown',function(e){{
    if(e.key==='Enter' && !e.shiftKey){{e.preventDefault();
      if((q.value||'').trim() || (dok.files && dok.files.length)) f.submit();}}
  }});
  q.addEventListener('input',function(){{
    q.style.height='auto'; q.style.height=Math.min(q.scrollHeight,190)+'px';}});
  Array.prototype.forEach.call(document.querySelectorAll('.cip'),function(c){{
    c.addEventListener('click',function(){{q.value=c.dataset.pyetje; f.submit();}});
  }});
  f.addEventListener('submit', function(e){{
    if(!(dok.files && dok.files.length) && !(q.value||'').trim()) e.preventDefault();
  }});
}})();
</script>""")


def _anesorja(bid_tanishem=None):
    """The conversations, down the left, the way a lawyer keeps his files open.

    They were only on the home page, so going into a conversation meant leaving
    every other one behind a back button. Memory holds them anyway; this just
    stops hiding them.
    """
    with _mbrojtje:
        te_gjitha = sorted(BISEDAT.items(),
                           key=lambda kv: -kv[1]["koha"].timestamp())[:40]
        rreshtat = "".join(
            f"<a class='lidhje-bisede{' tanishme' if i == bid_tanishem else ''}' "
            f"href='/biseda/{i}'>{html.escape(b['emri'][:52])}"
            f"<small>{b['koha'].strftime('%H:%M')}"
            f"{' · ' + html.escape((b.get('ligjet') or [''])[0][:26]) if b.get('ligjet') else ''}"
            f"</small></a>"
            for i, b in te_gjitha)
    return (f"<div class=anesore>"
            f"<p class=marka><b></b> Kontrata AI</p>"
            f"<a class=e-re href='/'>"
            f"<svg viewBox='0 0 24 24' width=15 height=15 fill=none "
            f"stroke=currentColor stroke-width=2 stroke-linecap=round>"
            f"<path d='M12 5v14M5 12h14'/></svg> Bisedë e re</a>"
            f"<p class=titull>Bisedat</p>{rreshtat}</div>")


def _flamur(b):
    return {"ne_pritje": ("pune", "në radhë"), "duke_punuar": ("pune", "po punon"),
            "gati": ("gati", "gati"), "gabim": ("keq", "gabim"),
            "pa_dokument": ("gati", "pa dokument")}[b["status"]]


# ----------------------------------------------------------------- puna
def _puno(bid, shtegu, data, emri):
    """The analysis itself, on a worker thread, limited by RRESHTI."""
    with RRESHTI:
        with _mbrojtje:
            BISEDAT[bid]["status"] = "duke_punuar"
        try:
            raport, deshtime, meta = analizo.analizo(
                str(shtegu), mode=MODE, data=data, emri=emri, kthe_meta=True)
            with _mbrojtje:
                b = BISEDAT[bid]
                b.update(status="gati", deshtime=deshtime,
                         ligjet=sorted(set(b.get("ligjet") or [])
                                       | set(meta.get("ligjet") or [])))
                b["mesazhet"].append({"tip": "raport", "raport": raport,
                                      "deshtime": deshtime})
                ne_pritje = b.pop("pyetje_ne_pritje", None)
            if ne_pritje:
                _beje_pyetjen(bid, ne_pritje)
        except ingest.NukLexohet as e:
            with _mbrojtje:
                BISEDAT[bid].update(status="gabim", gabim=f"Nuk lexohet: {e}")
        except Exception as e:
            traceback.print_exc()
            with _mbrojtje:
                BISEDAT[bid].update(status="gabim",
                                    gabim=f"{type(e).__name__}: {e}")
        finally:
            # THE CLIENT'S DOCUMENT GOES NOW, not when the process exits.
            try:
                shtegu.unlink(missing_ok=True)
                shtegu.parent.rmdir()
            except OSError:
                pass


@app.post("/nis")
def nis_bisede():
    """One door for both. A document, a question, or a document and a question.

    The typed question does not race the analysis: it is parked on the
    conversation and asked by the worker thread the moment the report exists,
    because asking it earlier would search without knowing which law the
    document belongs to -- which is the whole reason follow-up questions on a
    document are better than questions on their own.
    """
    f = request.files.get("dokument")
    pyetja = (request.form.get("pyetja") or "").strip()[:400]
    if f and f.filename:
        return _nis_me_dokument(f, pyetja)
    if not pyetja:
        return redirect("/", code=303)
    bid = uuid.uuid4().hex[:12]
    with _mbrojtje:
        BISEDAT[bid] = {"emri": pyetja[:60], "status": "pa_dokument",
                        "gabim": None, "deshtime": 0, "ligjet": [],
                        "koha": datetime.now(), "mesazhet": [],
                        "pyetje_ne_pritje": None}
    _beje_pyetjen(bid, pyetja)
    return redirect(f"/biseda/{bid}", code=303)


@app.post("/analizo")
def nis():
    f = request.files.get("dokument")
    return _nis_me_dokument(f, (request.form.get("pyetja") or "").strip()[:400])


def _nis_me_dokument(f, pyetja=""):
    if not f or not f.filename:
        return faqe("Gabim", "<div class='kart gab'><p>Nuk u zgjodh skedar.</p></div>"
                             "<p><a href='/'>Kthehu</a></p>"), 400
    suf = Path(f.filename).suffix.lower()
    if suf not in (".pdf", ".docx", ".txt"):
        return faqe("Gabim", f"<div class='kart gab'><p>Formati <code>"
                             f"{html.escape(suf or '?')}</code> nuk pranohet. "
                             f"Vetëm .pdf, .docx dhe .txt.</p></div>"
                             f"<p><a href='/'>Kthehu</a></p>"), 400
    data = None
    if request.form.get("data"):
        try:
            data = date.fromisoformat(request.form["data"])
        except ValueError:
            data = None

    # the original name is never used as a path: a filename is attacker-chosen
    dosja = Path(mkdtemp(prefix="kontrata_web_"))
    shtegu = dosja / f"dokument{suf}"
    f.save(shtegu)

    bid = uuid.uuid4().hex[:12]
    emri = Path(f.filename).name
    with _mbrojtje:
        BISEDAT[bid] = {"emri": emri, "status": "ne_pritje", "gabim": None,
                        "deshtime": 0, "ligjet": [], "koha": datetime.now(),
                        "mesazhet": [{"tip": "dokument", "emri": emri}],
                        "pyetje_ne_pritje": pyetja or None}
    threading.Thread(target=_puno, args=(bid, shtegu, data, emri),
                     daemon=True).start()
    return redirect(f"/biseda/{bid}", code=303)


@app.get("/biseda/re")
def biseda_re():
    bid = uuid.uuid4().hex[:12]
    with _mbrojtje:
        BISEDAT[bid] = {"emri": "Pyetje pa dokument", "status": "pa_dokument",
                        "gabim": None, "deshtime": 0, "ligjet": [],
                        "koha": datetime.now(), "mesazhet": []}
    return redirect(f"/biseda/{bid}", code=303)


# ----------------------------------------------------------------- pyetja
def _beje_pyetjen(bid, pyetja):
    """One place both the scripted and the plain path go through."""
    with _mbrojtje:
        b = BISEDAT.get(bid)
        if not b:
            return None, None
        ligjet = list(b.get("ligjet") or [])
        # THE THREAD, NOT THE LINE. Each question used to be answered alone, so
        # "domethen bleresi esht ne gabim?" went into the library carrying
        # nothing, and came back out of the Maritime Code. The earlier turns go
        # with it now -- to steer retrieval and to let the model keep the
        # thread -- but they are never a source: the provisions come from this
        # turn's search and every sentence is still checked against them.
        mepara = [{"pyetja": m["teksti"]} if m["tip"] == "pyetje"
                  else {"pergjigjja": m["p"].get("pergjigjja", "")}
                  for m in b["mesazhet"] if m["tip"] in ("pyetje", "pergjigje")]
        bashkuar = []
        for h in mepara:
            if "pyetja" in h:
                bashkuar.append(dict(h))
            elif bashkuar:
                bashkuar[-1].update(h)
        # A conversation that has cited laws stays inside them unless it is
        # plainly moving on; without this a follow-up can wander into a code
        # that shares a word with the question and nothing else.
        if not ligjet:
            ligjet = list(b.get("ligjet_e_cituara") or [])
    if not pyetja:
        return None, b
    with _mbrojtje:
        BISEDAT[bid]["mesazhet"].append({"tip": "pyetje", "teksti": pyetja})
    try:
        # The document's laws scope the search. That choice was made on the
        # document's whole vocabulary, which is far better evidence than the
        # dozen words of a follow-up question.
        p = pyet.pergjigju(pyetja, ligjet=ligjet or None, mode=MODE,
                           mepara=bashkuar[-3:] or None)
    except Exception as e:
        traceback.print_exc()
        p = {"pyetja": pyetja, "dispozitat": [], "me_e_perafert": [],
             "renditur": False, "pa_pergjigje": True, "pergjigjja": "",
             "gabim": f"{type(e).__name__}: {e}"}
    with _mbrojtje:
        BISEDAT[bid]["mesazhet"].append({"tip": "pergjigje", "p": p})
        reja = {d["ligji"] for d in p.get("dispozitat") or [] if d.get("ligji")}
        if reja:
            BISEDAT[bid]["ligjet_e_cituara"] = sorted(
                set(BISEDAT[bid].get("ligjet_e_cituara") or []) | reja)[:3]
    return p, b


@app.post("/ngarko/<bid>")
def ngarko(bid):
    """A document added to a conversation that is already under way.

    The thread keeps everything it already has and gains a report; the laws it
    searches inside become the union, so the questions asked before the upload
    and after it live in the same place. This is how the work actually goes --
    a question first, then the contract the question was really about.
    """
    with _mbrojtje:
        if bid not in BISEDAT:
            abort(404)
    f = request.files.get("dokument")
    if not f or not f.filename:
        return redirect(f"/biseda/{bid}", code=303)
    suf = Path(f.filename).suffix.lower()
    if suf not in (".pdf", ".docx", ".txt"):
        with _mbrojtje:
            BISEDAT[bid]["mesazhet"].append(
                {"tip": "njoftim", "teksti": f"Formati {suf or '?'} nuk pranohet. "
                                             f"Vetëm .pdf, .docx dhe .txt."})
        return redirect(f"/biseda/{bid}", code=303)
    dosja = Path(mkdtemp(prefix="kontrata_web_"))
    shtegu = dosja / f"dokument{suf}"
    f.save(shtegu)
    emri = Path(f.filename).name
    with _mbrojtje:
        b = BISEDAT[bid]
        b["status"] = "ne_pritje"
        b["mesazhet"].append({"tip": "dokument", "emri": emri})
        if b["emri"].startswith("Pyetje ") or b.get("status") == "pa_dokument":
            b["emri"] = emri
        b["emri"] = emri
    threading.Thread(target=_puno, args=(bid, shtegu, None, emri),
                     daemon=True).start()
    return redirect(f"/biseda/{bid}", code=303)


@app.post("/pyet/<bid>")
def pyet_route(bid):
    p, b = _beje_pyetjen(bid, (request.form.get("pyetja") or "").strip()[:400])
    if b is None:
        abort(404)
    return redirect(f"/biseda/{bid}#fundi", code=303)


# ----------------------------------------------------------------- shfaqja
def _disp_html(d, jo_pergjigje=False):
    shenjat = []
    if d["shfuqizuar"]:
        shenjat.append("<span class='shenje sh-vdekur'>ligj i shfuqizuar</span>")
    elif d["i_vjetruar"]:
        shenjat.append(f"<span class='shenje sh-vjeter'>tekst i vjetruar — "
                       f"ndryshuar {d['here_ndryshuar']}x, i fundit "
                       f"{html.escape(d['ndryshimi_i_fundit'][:10])}</span>")
    elif d["data_e_tekstit"]:
        shenjat.append(f"<span class='shenje sh-ok'>teksti i QBZ-së i "
                       f"{html.escape(d['data_e_tekstit'][:10])}</span>")
    if d["vendos_kufi"]:
        shenjat.append("<span class='shenje sh-kufi'>vendos kufi ose afat</span>")
    klase = "disp jo-pergjigje" if jo_pergjigje else "disp"
    return (f"<div class='{klase}'><p class=koka>"
            f"<span class=nen>{html.escape(d['ref'])}</span>"
            f"<span>{html.escape(d['ligji'] or '')}</span>"
            f"{''.join(shenjat)}</p>"
            f"<p class=tekst>{html.escape(d['teksti'])}</p></div>")


def _pergjigje_html(p):
    if p.get("gabim"):
        return (f"<div class='kart gab e-ngushte'><p>{html.escape(p['gabim'])}"
                f"</p></div>")
    pjeset = []
    # THE ANSWER FIRST, THE PROVISIONS UNDER IT.
    #
    # The first version showed only provisions, and the verdict on it was fair:
    # a lawyer asks a question and wants an answer, not a reading list. The
    # model writes these sentences, which it is allowed to do nowhere else here,
    # and pyet.verifiko_prozen() throws away any sentence whose citation or
    # figures are not in the retrieved text before it reaches this function.
    if p.get("pergjigjja"):
        pjeset.append(f"<div class='kart pergjigjja'><p class=teksti-pergj>"
                      f"{html.escape(p['pergjigjja'])}</p></div>")
        if p.get("fjali_te_hequra"):
            pjeset.append(
                f"<p class='vogel hequr'>{p['fjali_te_hequra']} fjali u hoqën "
                f"nga përgjigjja: mbanin numra ose citime që nuk gjenden në "
                f"dispozitat më poshtë.</p>")
    if p["pa_pergjigje"]:
        pjeset.append(
            "<div class='kart e-ngushte'><p>Nuk u gjet dispozitë që t'i "
            "përgjigjet kësaj pyetjeje.</p><p class=vogel>Kjo nuk do të thotë "
            "që ligji nuk e rregullon — do të thotë që kërkimi nuk e nxori. "
            "Provoje me fjalë të tjera, ose shiko te qbz.gov.al.</p></div>")
        for d in p.get("me_e_perafert") or []:
            pjeset.append(
                "<p class=etiketa style='margin-top:18px'>Më e përafërta që "
                "nxori kërkimi — nuk është përgjigje</p>"
                f"<div class='kart e-ngushte'>{_disp_html(d, True)}"
                "<p class='vogel ndarje'>Kërkimi kthen gjithmonë diçka, edhe "
                "kur ligji nuk e rregullon temën. Modeli nuk e zgjodhi këtë si "
                "përgjigje.</p></div>")
        return "".join(pjeset)

    koka = ""
    if p.get("lidhur_me_meparshmen"):
        koka += ("<p class=vogel style='margin:0 0 10px'>Kjo pyetje u lexua "
                 "bashkë me atë përpara saj.</p>")
    if not p["renditur"]:
        koka = ("<p class=vogel style='margin:0 0 4px'><strong>Pa renditje.</strong> "
                "Modeli nuk u përgjigj, pra kjo është radha e kërkimit. "
                "Lexoji të gjitha.</p>")
    trupi = "".join(_disp_html(d) for d in p["dispozitat"])
    fundi = ("<p class='vogel ndarje'>Dispozitat janë kopjuar fjalë për fjalë "
             "nga korpusi. Çdo fjali e përgjigjes mbi to u kontrollua: citimi "
             "duhet të jetë një nga këto dispozita dhe çdo numër duhet të "
             "gjendet në tekstin e saj.</p>")
    etiketa = ("<p class=etiketa style='margin:16px 0 7px'>Dispozitat</p>"
               if p.get("pergjigjja") else "")
    pjeset.append(f"{etiketa}<div class=kart>{koka}{trupi}{fundi}</div>")
    return "".join(pjeset)


def _mesazh_html(m, bid):
    if m["tip"] == "dokument":
        return (f"<div class=msg><p class=etiketa>Dokumenti</p>"
                f"<div class='kart e-ngushte'><p style='margin:0'>"
                f"{html.escape(m['emri'])}</p></div></div>")
    if m["tip"] == "pyetje":
        return (f"<div class='msg pyetje'><div class=flluska>"
                f"{html.escape(m['teksti'])}</div></div>")
    if m["tip"] == "pergjigje":
        # The block is labelled by what it actually leads with: a written
        # answer, or -- when the model wrote nothing that survived checking --
        # the provisions themselves.
        etiketa = "Përgjigjja" if m["p"].get("pergjigjja") else "Dispozitat"
        return (f"<div class=msg><p class=etiketa>{etiketa}</p>"
                f"{_pergjigje_html(m['p'])}</div>")
    if m["tip"] == "njoftim":
        return (f"<div class=msg><div class='kart gab e-ngushte'>"
                f"<p style='margin:0'>{html.escape(m['teksti'])}</p></div></div>")
    if m["tip"] == "raport":
        kujdes = ""
        if m["deshtime"]:
            kujdes = (f"<div class='kart gab e-ngushte' style='margin-bottom:14px'>"
                      f"<p style='margin:0'><strong>{m['deshtime']} pyetje nuk "
                      f"marrën përgjigje.</strong> Raporti është i paplotë dhe "
                      f"nuk duhet dërguar ashtu siç është.</p></div>")
        return (f"<div class=msg><p class=etiketa>Raporti i verifikuar &nbsp;·&nbsp; "
                f"<a href='/raport/{bid}.md'>shkarko .md</a></p>{kujdes}"
                f"<div class='kart rap'>{ne_html(m['raport'])}</div></div>")
    return ""


FUSHA = """
<div class=poshte>
  __FTESA__
  <div class=brenda>
    <form id=f method=post action="/pyet/__BID__">
      <div class=composer>
        <label class=kapese for=dok2 title="Shto një dokument në këtë bisedë">
          <svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=1.7
               stroke-linecap=round><path d="M20 11.5l-8 8a5 5 0 01-7-7l8.5-8.5a3.3
               3.3 0 014.7 4.7L9.6 17.3a1.7 1.7 0 01-2.4-2.4L15 7"/></svg>
        </label>
        <textarea id=q name=pyetja rows=1 maxlength=400 autofocus
                  placeholder="__VENDMBAJTES__"></textarea>
        <button id=b type=submit aria-label=Dërgo>
          <svg viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2.4
               stroke-linecap=round stroke-linejoin=round>
            <path d="M12 19V5M5 12l7-7 7 7"/></svg>
        </button>
      </div>
    </form>
    <form id=fdok method=post action="/ngarko/__BID__" enctype=multipart/form-data>
      <input id=dok2 type=file name=dokument accept=".pdf,.docx,.txt,application/pdf">
    </form>
  </div>
  <p class="vogel nen-fushe">__NEN__</p>
</div>
<script>
// A CHAT, NOT A FORM THAT RELOADS THE PAGE.
//
// Posting and redirecting threw away the whole conversation on every question,
// lost the caret, and left the lawyer looking at a frozen page. Here the
// question appears as it is sent, three dots say the machine is working, and
// the answer replaces them in place. The server still renders the answer's
// HTML -- the same function the no-script path uses -- so there is one
// renderer and the escaping stays on the server.
(function(){
  var f=document.getElementById('f'), q=document.getElementById('q'),
      b=document.getElementById('b'), rrjedha=document.getElementById('rrjedha'),
      dok=document.getElementById('dok2'), fdok=document.getElementById('fdok');
  if(!f||!rrjedha) return;
  function poshte(){ window.scrollTo({top:document.body.scrollHeight,
                                      behavior:'smooth'}); }
  poshte();
  // Attaching mid-conversation: the thread keeps its history and gains a
  // document, which is how a lawyer actually works -- ask first, then produce
  // the contract the question was really about.
  dok.addEventListener('change', function(){ if(dok.files.length) fdok.submit(); });
  Array.prototype.forEach.call(document.querySelectorAll('[data-ngarko]'),
    function(el){ el.addEventListener('click', function(){ dok.click(); }); });
  ['dragenter','dragover'].forEach(function(e){
    window.addEventListener(e,function(ev){ev.preventDefault();});});
  window.addEventListener('drop',function(ev){
    ev.preventDefault();
    if(ev.dataTransfer && ev.dataTransfer.files.length){
      dok.files=ev.dataTransfer.files; fdok.submit();}});

  q.addEventListener('input',function(){
    q.style.height='auto'; q.style.height=Math.min(q.scrollHeight,190)+'px';});
  q.addEventListener('keydown',function(e){
    if(e.key==='Enter' && !e.shiftKey){e.preventDefault();
      f.dispatchEvent(new Event('submit',{cancelable:true}));}});

  f.addEventListener('submit', function(e){
    e.preventDefault();
    var teksti=(q.value||'').trim();
    if(!teksti) return;
    q.value=''; q.style.height='auto'; q.disabled=true; b.disabled=true;

    var p=document.createElement('div');
    p.className='msg pyetje';
    var fl=document.createElement('div'); fl.className='flluska';
    fl.textContent=teksti;          // textContent, never innerHTML
    p.appendChild(fl); rrjedha.appendChild(p);

    var pres=document.createElement('div');
    pres.className='msg';
    pres.innerHTML='<p class=etiketa>Po kërkon në korpus</p>'+
      '<div class="kart e-ngushte"><div class=mendon><i></i><i></i><i></i></div></div>';
    rrjedha.appendChild(pres); poshte();

    var d=new FormData(); d.append('pyetja', teksti);
    fetch(f.action.replace('/pyet/','/api/pyet/'), {method:'POST', body:d})
      .then(function(r){ return r.json(); })
      .then(function(j){
        pres.innerHTML='<p class=etiketa>'+(j.etiketa||'Përgjigjja')+'</p>'+j.html;
        q.disabled=false; b.disabled=false; q.focus(); poshte();
      })
      .catch(function(err){
        pres.innerHTML='<div class="kart gab e-ngushte"><p>Nuk u mor përgjigje: '+
          String(err).replace(/[<>&]/g,'')+'</p><p class=vogel>Shiko nëse vLLM-i '+
          'është ngritur në dritaren tjetër.</p></div>';
        q.disabled=false; b.disabled=false; q.focus();
      });
  });
})();
</script>"""


@app.post("/api/pyet/<bid>")
def api_pyet(bid):
    """The same work as /pyet, rendered to HTML here instead of on a reload."""
    p, _b = _beje_pyetjen(bid, (request.form.get("pyetja") or "").strip()[:400])
    if p is None:
        abort(404)
    return {"html": _pergjigje_html(p),
            "etiketa": "Përgjigjja" if p.get("pergjigjja") else "Dispozitat"}


@app.get("/biseda/<bid>")
def biseda(bid):
    with _mbrojtje:
        b = BISEDAT.get(bid)
        if not b:
            abort(404)
        b = {**b, "mesazhet": list(b["mesazhet"])}

    emri = html.escape(b["emri"])
    ligjet = ", ".join(b.get("ligjet") or [])
    meta = []
    if ligjet:
        meta.append(f"lexuar kundrejt: {html.escape(ligjet)}")
    nr_pyetje = len([m for m in b["mesazhet"] if m["tip"] == "pyetje"])
    if nr_pyetje:
        meta.append(f"{nr_pyetje} pyetje")
    ballina = (f"<div class=ballina><div class=brenda>"
               f"<h1>{emri}</h1>"
               f"<span class=meta>{' &nbsp;·&nbsp; '.join(meta)}</span>"
               f"<span style='flex:1'></span>"
               f"<a class=meta href='/'>Kreu</a></div></div>")

    trupi = "".join(_mesazh_html(m, bid) for m in b["mesazhet"])

    if b["status"] in ("ne_pritje", "duke_punuar"):
        teksti = ("Në radhë — dy analiza punojnë njëkohësisht."
                  if b["status"] == "ne_pritje" else
                  "Po lexohet dokumenti dhe po kontrollohen klauzolat.")
        trupi += (f"<div class=msg><p class=etiketa>Raporti</p>"
                  f"<div class='kart e-ngushte'><p style='margin:0'>"
                  f"<span class=pulso></span>{teksti}</p>"
                  f"<p class='vogel' style='margin:9px 0 0'>Faqja rifreskohet "
                  f"vetë. Mund ta lësh hapur.</p></div></div>")
        return faqe(f"{b['emri']} — po punon",
                    _anesorja(bid) + f"<div class=kryesore>{ballina}"
                    f"<div class=biseda>{trupi}</div></div>",
                    rifresko=4, klase=None)

    if b["status"] == "gabim":
        trupi += (f"<div class=msg><div class='kart gab'>"
                  f"<p>{html.escape(b['gabim'] or '')}</p>"
                  f"<p class=vogel>Nëse dokumenti është skanim shumë i dobët, "
                  f"OCR-i nuk nxjerr tekst të mjaftueshëm. Kërko një kopje "
                  f".docx ose një skanim më të mirë.</p></div></div>")
        return faqe(f"{b['emri']} — gabim",
                    _anesorja(bid) + f"<div class=kryesore>{ballina}"
                    f"<div class=biseda>{trupi}</div></div>", klase=None)

    if b["status"] == "pa_dokument" and not b["mesazhet"]:
        trupi += ("<div class=msg><div class=kart>"
                  "<p style='margin:0 0 8px'>Pyet ligjin.</p>"
                  "<p class=vogel style='margin:0'>Shkruaj një pyetje dhe "
                  "përgjigja do jenë dispozitat e korpusit, fjalë për fjalë, "
                  "me ligjin, nenin dhe datën e tekstit. Modeli zgjedh vetëm "
                  "cilat dispozita të shfaqen — nuk shkruan ligj.</p>"
                  "<p class=vogel style='margin:10px 0 0'>Për shembull: "
                  "<em>sa vjet mund te lidhet kontrata e qirase</em>, ose "
                  "<em>a mund te jete paga me e ulet se paga minimale</em>."
                  "</p></div></div>")

    ftesa = ("" if b.get("ligjet") else
             "<div class=ftese-dok><span>📄</span><span>Kjo bisedë nuk ka ende "
             "dokument. <b>Ngarko një kontratë</b> dhe çdo klauzolë e saj "
             "kontrollohet nen për nen.</span>"
             "<span class=veprim data-ngarko>Zgjidh skedarin</span></div>")
    fusha = (FUSHA
             .replace("__FTESA__", ftesa)
             .replace("__BID__", bid)
             .replace("__VENDMBAJTES__",
                      "Pyet për këtë dokument, ose për ligjin…"
                      if b.get("ligjet") else "Shkruaj një pyetje për ligjin…")
             .replace("__NEN__",
                      "Përgjigjja vjen nga dispozitat e korpusit; çdo numër në "
                      "të kontrollohet kundrejt tekstit të tyre."
                      + (f" Brenda: {html.escape(ligjet)}." if ligjet else "")))
    return faqe(f"{b['emri']}",
                _anesorja(bid) + f"<div class=kryesore>{ballina}"
                f"<div class=biseda><div id=rrjedha>{trupi}</div>"
                f"<div id=fundi></div></div></div>" + fusha, klase=None)


@app.get("/raport/<bid>.md")
def shkarko(bid):
    with _mbrojtje:
        b = BISEDAT.get(bid)
        raporti = next((m["raport"] for m in (b or {}).get("mesazhet", [])
                        if m["tip"] == "raport"), None) if b else None
    if not raporti:
        abort(404)
    emri = re.sub(r"[^A-Za-z0-9._-]", "_", Path(b["emri"]).stem)[:60] or "raport"
    return Response(raporti, mimetype="text/markdown; charset=utf-8",
                    headers={"Content-Disposition":
                             f'attachment; filename="{emri}.raport.md"'})


if __name__ == "__main__":
    print(f"Kontrolli i kontratave  ->  http://{HOST}:{PORT}")
    if HOST not in ("127.0.0.1", "localhost", "::1"):
        print(f"\n  KUJDES: lidhur me {HOST}, pra e hapur per rrjetin.")
        print(f"  Kushdo ne rrjet mund te hapi kontratat e klienteve, pa fjalekalim.")
        print(f"  Hiqe KONTRATA_HOST per t'u kthyer te 127.0.0.1.\n")
    print(f"modeli: {MODE}   njekohesisht: {NJEKOHESISHT}"
          f"   (serveri vLLM duhet te jete ngritur)")
    app.run(host=HOST, port=PORT, threaded=True)
