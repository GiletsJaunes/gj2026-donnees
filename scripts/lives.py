"""Cherche les directs YouTube : ceux du mouvement (recherche) et ceux des chaines d'info (page /live).
Resultat : data/lives.json. Ne plante jamais : en cas d'echec, l'ancien fichier est garde."""
import json, re, urllib.parse, urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleRoot/1.0 Chrome/124.0 Safari/537.36"
ENTETES = {"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9", "Cookie": "SOCS=CAI; CONSENT=YES+1"}
CHAINES = [("franceinfo", "@franceinfo"), ("France 24", "@FRANCE24"), ("BFMTV", "@BFMTV"), ("LCI", "@LCI"),
           ("CNEWS", "@CNEWS"), ("Le Média", "@LeMedia"), ("Euronews", "@euronewsfr"), ("Brut", "@brutofficiel")]
RECHERCHES = ["gilets jaunes direct", "manifestation direct", "blocus lycée direct", "manif Paris direct", "mobilisation 24 octobre direct", "acte 2 gilets jaunes live"]
PERTINENT = re.compile(r"gilets? jaunes?|manif|blocus|lyc[ée]|mobilisation|\bacte\b|\bRIC\b|gr[èe]ve|vie ch[èe]re|rassemblement|cort[èe]ge", re.I)

def telecharger(url):
    req = urllib.request.Request(url, headers=ENTETES)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore")

def direct_de_chaine(nom, handle):
    page = telecharger("https://www.youtube.com/%s/live" % handle)
    if '"isLiveNow":true' not in page:
        return None
    m = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})"', page)
    if not m:
        return None
    t = re.search(r'<meta name="title" content="([^"]+)"', page)
    return {"id": m.group(1), "titre": (t.group(1) if t else nom), "chaine": nom, "spectateurs": ""}

def parcourir(o, cle):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == cle:
                yield v
            else:
                yield from parcourir(v, cle)
    elif isinstance(o, list):
        for v in o:
            yield from parcourir(v, cle)

def texte(x):
    if not x:
        return ""
    if "simpleText" in x:
        return x["simpleText"]
    return "".join(r.get("text", "") for r in x.get("runs", []))

def lire_recherche(page):
    m = re.search(r"ytInitialData\s*=\s*(\{.*?\});\s*</script>", page, re.S)
    if not m:
        return []
    data = json.loads(m.group(1))
    out = []
    for vr in parcourir(data, "videoRenderer"):
        brut = json.dumps({"b": vr.get("badges"), "o": vr.get("thumbnailOverlays")})
        if "LIVE" not in brut.upper():
            continue
        vid = vr.get("videoId")
        if not vid or not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
            continue
        out.append({"id": vid, "titre": texte(vr.get("title")), "chaine": texte(vr.get("ownerText")),
                    "spectateurs": texte(vr.get("viewCountText")).replace("\xa0", " ")})
    return out

def chercher(ancien):
    resultat = {"mouvement": [], "chaines": []}
    reussi = 0
    deja = set()
    for nom, handle in CHAINES:
        try:
            d = direct_de_chaine(nom, handle); reussi += 1
            if d and d["id"] not in deja:
                resultat["chaines"].append(d); deja.add(d["id"])
        except Exception as e:
            print("Direct de chaine indisponible :", nom, e)
    for q in RECHERCHES:
        try:
            page = telecharger("https://www.youtube.com/results?search_query=%s&sp=EgJAAQ%%3D%%3D" % urllib.parse.quote(q)); reussi += 1
            for d in lire_recherche(page):
                if d["id"] in deja or not PERTINENT.search(d["titre"]):
                    continue
                resultat["mouvement"].append(d); deja.add(d["id"])
        except Exception as e:
            print("Recherche de directs indisponible :", q, e)
    resultat["mouvement"] = resultat["mouvement"][:8]
    if reussi == 0:
        return ancien
    print("Directs : %d du mouvement, %d chaines" % (len(resultat["mouvement"]), len(resultat["chaines"])))
    return resultat
