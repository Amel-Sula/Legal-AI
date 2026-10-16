#!/usr/bin/env python3
"""Download the official QBZ legislation library, and record how fresh it is.

    python3 shkarko_qbz.py ~/ligjet --shiko    # what is there, download nothing
    python3 shkarko_qbz.py ~/ligjet            # download new and CHANGED files
    python3 shkarko_qbz.py ~/ligjet --zbulo    # hunt for folders beyond the known ones

qbz.gov.al runs on Alfresco and exposes its public REST API with no login:

    /alfresco/api/-default-/public/alfresco/versions/1/nodes/{id}/children
    /alfresco/api/-default-/public/alfresco/versions/1/nodes/{id}/content

WHY THE MANIFEST MATTERS MORE THAN THE DOWNLOAD.

Every provision this product cites comes out of one of these files, and a
citation that is letter-perfect from a repealed article is worse than no
citation, because the lawyer believed it. Until now the corpus knew the
Labour Code's consolidation date and nothing at all about the other 242 laws:
the report printed one date and stayed silent on the rest.

Alfresco returns `modifiedAt` for every document -- QBZ's own record of when
it last republished that file. That is not a date this program invents, it is
the authority's. It is written to manifest.json beside the downloads, and
shto_ligj.py attaches it to every law it parses out of that file, so the
report can state per law how old the text behind it is.

The same field gives the update behaviour: a file whose `modifiedAt` is newer
than the manifest's is re-downloaded. Before the manifest existed, a file
already on disk was skipped forever, so an amended law would never have
arrived no matter how often this ran.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BAZA = "https://qbz.gov.al/alfresco/api/-default-/public/alfresco/versions/1/nodes/"

# The folders known to hold the published library. --zbulo looks for more.
DOSJET = {
    "Kodet":                     "7f7b6612-4ebc-4ed0-aae6-07eac1188d5c",
    "Kushtetuta":                "fc29256a-5bee-4837-9cc4-f1227f0d24ba",
    "Permbledhje_Legjislacioni": "66106990-e394-47c0-afbc-7b124c8a0623",
    "Treguesit_Kronologjik":     "ac647ffa-bf01-4f89-b2c8-9f01e23359b2",
    "Legjislacion_QBZ":          "1e9b044a-d036-49f1-b8af-8df2b40e89dd",
}

# Alfresco aliases that may stand at the top of a public repository. Tried in
# order by --zbulo; whichever answers gets walked.
RRENJET = ("-root-", "-shared-", "-my-")

KOKA = {"User-Agent": "Mozilla/5.0", "Accept": "*/*"}
MANIFESTI = "manifest.json"
SHTRIRJE = (".pdf", ".doc", ".docx")


def _merr(url, binare=False, provat=3):
    for p in range(provat):
        try:
            req = urllib.request.Request(url, headers=KOKA)
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read() if binare else json.loads(r.read().decode())
        except Exception:
            if p == provat - 1:
                raise
            time.sleep(2 * (p + 1))


def femijet(node_id):
    """All children of a folder, paged, folders and files alike."""
    out, skip = [], 0
    while True:
        d = _merr(f"{BAZA}{node_id}/children?maxItems=100&skipCount={skip}")
        hyrjet = d.get("list", {}).get("entries", [])
        out += [e["entry"] for e in hyrjet]
        pag = d.get("list", {}).get("pagination", {})
        if not pag.get("hasMoreItems"):
            return out
        skip += len(hyrjet)


def emer_i_sigurt(s):
    s = re.sub(r"[^\w\s.\-()]", "", s or "", flags=re.U).strip()
    return re.sub(r"\s+", "_", s)[:120] or "pa_emer"


# ----------------------------------------------------------------- manifesti
def lexo_manifestin(rrenja):
    p = Path(rrenja) / MANIFESTI
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(f"   [kujdes] {MANIFESTI} nuk lexohet; do ndertohet nga e para")
        return {}


def shkruaj_manifestin(rrenja, m):
    (Path(rrenja) / MANIFESTI).write_text(
        json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8")


# ----------------------------------------------------------------- zbritja
def zbrit(node_id, dosja, rrenja, man, shiko, thelle=0, stat=None):
    stat = stat if stat is not None else {"marre": 0, "kaluar": 0,
                                          "rifreskuar": 0, "deshtuar": 0,
                                          "pare": 0}
    if not shiko:
        dosja.mkdir(parents=True, exist_ok=True)
    hap = "  " * thelle
    for e in femijet(node_id):
        if e.get("isFolder"):
            print(f"   {hap}/{e['name'][:60]}")
            zbrit(e["id"], dosja / emer_i_sigurt(e["name"]), rrenja, man,
                  shiko, thelle + 1, stat)
            continue

        emri = emer_i_sigurt(e["name"])
        if not emri.lower().endswith(SHTRIRJE):
            emri += ".pdf"
        dest = dosja / emri
        rel = str(dest.relative_to(rrenja))
        qbz_mod = e.get("modifiedAt") or ""
        stat["pare"] += 1

        e_vjeter = man.get(rel, {})
        ka_skedar = dest.exists() and dest.stat().st_size > 1000
        # QBZ republished it since we last took it -> take it again
        ndryshuar = bool(qbz_mod and e_vjeter.get("qbz_modifikuar")
                         and qbz_mod > e_vjeter["qbz_modifikuar"])

        if shiko:
            gjendja = ("I RI" if not ka_skedar else
                       "NDRYSHUAR" if ndryshuar else "ka")
            print(f"   {hap}[{gjendja:9}] {emri[:58]}  "
                  f"{(qbz_mod or '?')[:10]}")
            continue

        if ka_skedar and not ndryshuar:
            # RECORD IT ANYWAY. The QBZ date arrives with the listing, before
            # the decision to download, and it is the whole point of this run.
            # Writing it only on download meant that on a machine where every
            # file was already present -- which is every machine after the
            # first run -- the manifest stayed empty, no date ever reached the
            # corpus, and the step looked like it had worked.
            man.setdefault(rel, {}).update({
                "id": e["id"],
                "emri_qbz": e["name"],
                "qbz_modifikuar": qbz_mod,
                "qbz_krijuar": e.get("createdAt") or "",
                "madhesia": dest.stat().st_size,
            })
            man[rel].setdefault("shkarkuar", "")   # we did not fetch it now
            stat["kaluar"] += 1
            continue
        try:
            te_dhenat = _merr(f"{BAZA}{e['id']}/content?attachment=true",
                              binare=True)
            dest.write_bytes(te_dhenat)
            man[rel] = {
                "id": e["id"],
                "emri_qbz": e["name"],
                "qbz_modifikuar": qbz_mod,
                "qbz_krijuar": e.get("createdAt") or "",
                "madhesia": len(te_dhenat),
                "shkarkuar": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            }
            fjala = "rifreskuar" if ndryshuar else "ok"
            stat["rifreskuar" if ndryshuar else "marre"] += 1
            print(f"   {hap}[{fjala}] {emri[:58]}  "
                  f"({len(te_dhenat)//1024} KB, QBZ {(qbz_mod or '?')[:10]})")
        except Exception as ex:
            stat["deshtuar"] += 1
            print(f"   {hap}[DESHTOI] {emri[:46]}: {str(ex)[:56]}")
    return stat


def zbulo():
    """Is there more than the five known folders? Ask the repository root."""
    print("Po kerkoj dosje pertej atyre te njohura...\n")
    te_njohura = set(DOSJET.values())
    for alias in RRENJET:
        try:
            femije = femijet(alias)
        except Exception as ex:
            print(f"  {alias:10} -> nuk pergjigjet ({str(ex)[:50]})")
            continue
        print(f"  {alias:10} -> {len(femije)} elemente")
        for e in femije:
            if not e.get("isFolder"):
                continue
            shenje = "  (e njohur)" if e["id"] in te_njohura else "  <-- E RE"
            print(f"       {e['name'][:52]:54} {e['id']}{shenje}")
    print("\nNese del dosje E RE, shtoje te DOSJET ne krye te skedarit.")


def main(ku, shiko=False):
    rrenja = Path(ku).expanduser()
    man = lexo_manifestin(rrenja)
    e_para = not man
    total = {"marre": 0, "kaluar": 0, "rifreskuar": 0, "deshtuar": 0, "pare": 0}
    for emri, nid in DOSJET.items():
        print(f"\n=== {emri} ===")
        try:
            st = zbrit(nid, rrenja / emri, rrenja, man, shiko)
        except Exception as ex:
            print(f"   [DESHTOI E GJITHA] {str(ex)[:90]}")
            continue
        for k in total:
            total[k] += st[k]

    print(f"\n{'=' * 58}")
    if shiko:
        print(f"[SHIKO] {total['pare']} skedare te QBZ-se. Asgje nuk u shkarkuar.")
        if e_para:
            print("Nuk ka manifest, pra nuk dallohet 'ndryshuar' nga 'i ri':")
            print("leshoje njehere pa --shiko, pastaj --shiko tregon ndryshimet.")
        return
    shkruaj_manifestin(rrenja, man)
    pdfs = [p for p in rrenja.rglob("*") if p.suffix.lower() in SHTRIRJE]
    print(f"Te rinj: {total['marre']}   rifreskuar: {total['rifreskuar']}   "
          f"pa ndryshim: {total['kaluar']}   deshtuan: {total['deshtuar']}")
    print(f"Ne {rrenja}: {len(pdfs)} skedare, "
          f"{sum(p.stat().st_size for p in pdfs)//(1024*1024)} MB")
    print(f"Manifesti: {rrenja / MANIFESTI}  ({len(man)} skedare me date QBZ)")
    if total["marre"] or total["rifreskuar"]:
        print(f"\nTani rilesho parsimin, se korpusi mban tekstin e vjeter:")
        print(f"   python3 shto_ligj.py {rrenja}/Kodet")
        print(f"   python3 shto_ligj.py {rrenja}/Permbledhje_Legjislacioni")
        print(f"   python3 mat_kerkimin.py")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--zbulo" in sys.argv:
        zbulo()
    else:
        main(args[0] if args else "~/ligjet", shiko="--shiko" in sys.argv)
