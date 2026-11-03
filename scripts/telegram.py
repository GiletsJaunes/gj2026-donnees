#!/usr/bin/env python3
"""BLOCUS annonces sur Telegram par des SOURCES DE CONFIANCE designees (scripts/sources_sures.json).

Principe : seuls les canaux Telegram PUBLICS de la liste sont lus (page publique t.me/s/NOM). Une annonce de blocus
devient un point sur la carte, toute seule, si elle contient : le mot blocus/blocage, une ville certaine, une date precise
(dans les 21 jours). L'heure et le lieu sont repris s'ils sont ecrits. Le nom de la source est TOUJOURS affiche sur la carte,
avec le lien du message : la responsabilite de l'annonce est publique. Un message « annule » retire/signale le blocus.
Exemple de message : « BLOCUS samedi 8 novembre, Lyon, 6h, rond-point de Perrache » (n'importe quel ordre).
Sortie : data/blocus.json."""
import datetime as dt, hashlib, html, re, urllib.request
from pathlib import Path
import rdv

TRIG = re.compile(r"\bblocus\b|blocage|bloquer|bloquons|barrage filtrant|filtrage", re.I)
ANNULE = re.compile(r"annul\w+|report\w+|c.est fini|n.aura pas lieu", re.I)
LIEU = re.compile(r"(?:rond-point|giratoire|péage|depot|dépôt|zone industrielle|zone commerciale|raffinerie|plateforme|préfecture|gare|pont|périphérique|autoroute|échangeur|place|devant|parvis|esplanade|entrée)\b[^,.;\n()«»\"!]{0,50}", re.I)
HEURE = re.compile(r"\b(\d{1,2})\s?[hH]\s?(\d{2})?\b")

def lire_canal(canal, pages=8):
    """Lit la page publique du canal, puis les pages plus anciennes (?before=ID) : Telegram n'en montre qu'une vingtaine a la fois."""
    posts, avant = [], None
    for _ in range(pages):
        url = "https://t.me/s/" + canal + ("?before=%d" % avant if avant else "")
        req = urllib.request.Request(url, headers={"User-Agent": rdv.UA, "Accept-Language": "fr"})
        with urllib.request.urlopen(req, timeout=25) as r:
            page = r.read().decode("utf-8", "ignore")
        lot = _lire_page(page)
        if not lot:
            break
        posts += lot
        ids = [int(p["id"].rsplit("/", 1)[1]) for p in lot]
        if min(ids) <= 1 or min(p["date"] for p in lot)[:10] < (dt.date.today() - dt.timedelta(days=2)).isoformat():
            break
        avant = min(ids)
    vus = set()
    return [p for p in posts if not (p["id"] in vus or vus.add(p["id"]))]

def _lire_page(page):
    posts = []
    for bloc in re.split(r'(?=<div class="tgme_widget_message_wrap)', page)[1:]:
        m_id = re.search(r'data-post="([^"]+)"', bloc)
        m_t = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', bloc, re.S)
        m_d = re.search(r'<time[^>]*datetime="([^"]+)"', bloc)
        if not (m_id and m_t and m_d):
            continue
        txt = re.sub(r"<br\s*/?>", "\n", m_t.group(1)); txt = html.unescape(re.sub(r"<[^>]+>", "", txt)).strip()
        posts.append({"id": m_id.group(1), "texte": txt, "date": m_d.group(1)})
    return posts

def heure(t):
    m = HEURE.search(t)
    if m and 3 <= int(m.group(1)) <= 23:
        return "%02d:%s" % (int(m.group(1)), m.group(2) or "00")
    return ""

def extraire_post(p, canal, nom, idx, aujourdhui):
    t = p["texte"]
    if not TRIG.search(t) or rdv.NEGATION.search(t):
        return []
    try:
        base = dt.date.fromisoformat(p["date"][:10])
    except Exception:
        return []
    dates = rdv.dates_de(t, base, aujourdhui)
    if not dates:
        return []
    mots = t.replace("’", "'").replace("l'", "l' ").replace("\n", " ").split()
    villes, i = [], 0
    while i < len(mots):
        if mots[i][:1].isupper():
            r = rdv.trouver_ville(idx, mots, i, set())
            if r:
                villes.append(r[0]); i += r[1]; continue
        i += 1
    if not villes:
        return []
    c = villes[0]; lieu = LIEU.search(t)
    out = []
    for d in dates:
        out.append({"id": hashlib.sha1((c[0] + c[1] + d.isoformat() + p["id"]).encode()).hexdigest()[:10], "ville": c[0], "dep": c[1], "lat": c[2], "lng": c[3],
                    "date": d.isoformat(), "heure": heure(t), "type": "blocage", "lieu": lieu.group(0).strip() if lieu else "", "organisateurs": [],
                    "mouvement": True, "alerte": "annulée" if ANNULE.search(t) else "", "statut": "annonce", "nb_medias": 0, "confiance": nom,
                    "post": "https://t.me/" + p["id"], "sources": [], "texte": t[:280]})
    return out

INFO = re.compile(r"interpell|police|CRS|gaz|lacrymo|évacu|evacu|levé|fin du blocus|tension|blessé|AED|garde à vue", re.I)

def date_paris(iso):
    d = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (d.astimezone(rdv.PARIS) if d.tzinfo else d).date()

def centres_deps(idx):
    """Centre approximatif de chaque departement (moyenne de ses communes), pour « Lycee X en Seine-Saint-Denis »."""
    acc = {}
    for lst in idx.values():
        for nom, dep, lat, lng, pop in lst:
            a = acc.setdefault(dep, [0, 0, 0]); a[0] += lat; a[1] += lng; a[2] += 1
    return {d: (a[0] / a[2], a[1] / a[2]) for d, a in acc.items()}

def extraire_implicite(p, nom, idx, aujourdhui, centres, noms_deps, ignores=None):
    """Canal dedie aux blocus : CHAQUE ligne est un lieu bloque (« Lycee Pasteur a Strasbourg »), le jour du message."""
    try:
        jour = date_paris(p["date"])
    except Exception:
        return []
    autres = rdv.dates_de(p["texte"], jour, aujourdhui)
    dates = sorted(autres) or ([jour] if jour >= aujourdhui else [])
    out = []
    for ligne in [l.strip(" -•·*\t") for l in p["texte"].split("\n")]:
        if len(ligne) < 4 or INFO.search(ligne) or rdv.NEGATION.search(ligne):
            if ignores is not None and len(ligne) >= 4:
                ignores.append({"ligne": ligne[:120], "raison": "information (police, évacuation…) ou négation", "post": p["id"]})
            continue
        ln = rdv.norm(ligne).replace("-", " ")
        ville = None
        mots = ligne.replace("’", "'").replace("l'", "l' ").split()
        i = 0
        while i < len(mots):
            if mots[i][:1].isupper():
                r = rdv.trouver_ville(idx, mots, i, set())
                if r and (i > 0 or len(mots) == 1 or True):
                    ville = r[0]
                    if i > 0 or r[1] < len(mots):   # on prefere la ville citee apres « a / en / de » la plus loin dans la ligne
                        pass
                    i += r[1]; continue
            i += 1
        lat = lng = None
        if ville:
            nomv, dep, lat, lng = ville[0], ville[1], ville[2], ville[3]
        else:
            trouve = [d for d, n in noms_deps.items() if n in ln and d in centres]
            if not trouve:
                if ignores is not None:
                    ignores.append({"ligne": ligne[:120], "raison": "aucune ville reconnue (commune de 1500 habitants ou plus) ni département", "post": p["id"]})
                continue
            dep = max(trouve, key=lambda d: len(noms_deps[d])); lat, lng = centres[dep]; nomv = "Dép. " + dep + " · " + rdv_dep(dep)
        lieu = re.split(r"\s+(?:à|en|au|aux)\s+[A-ZÉÈ]", ligne)[0].strip(" ,.;:") or ligne
        for d in dates:
            out.append({"id": hashlib.sha1((nomv + dep + d.isoformat() + rdv.norm(lieu)).encode()).hexdigest()[:10], "ville": nomv, "dep": dep, "lat": lat, "lng": lng,
                        "date": d.isoformat(), "heure": heure(ligne), "type": "blocage", "lieu": lieu[:80], "organisateurs": [], "mouvement": False,
                        "alerte": "annulée" if ANNULE.search(ligne) else "", "statut": "annonce", "nb_medias": 0, "confiance": nom,
                        "post": "https://t.me/" + p["id"], "sources": [], "texte": ligne[:200]})
    return out

def rdv_dep(dep):
    return DEPS.get(dep, dep)
DEPS = rdv.lire_json(Path(__file__).resolve().parent / "departements.json", {})

def maj(data, maintenant=None, aujourdhui=None, fetch=lire_canal):
    maintenant = maintenant or dt.datetime.now(rdv.PARIS)
    aujourdhui = aujourdhui or maintenant.date()
    idx = rdv.charger_communes(data, None)
    if not idx:
        print("Blocus : aucune commune disponible, rien n'est modifie."); return None
    cfg = rdv.lire_json(Path(__file__).resolve().parent / "sources_sures.json", {"canaux": []})
    masques = set(rdv.lire_json(Path(data) / "masques.json", {}).get("blocus", []))
    evts, lus, ignores = {}, 0, []
    centres = centres_deps(idx); noms_deps = {d: rdv.norm(n).replace("-", " ") for d, n in DEPS.items()}
    for c in cfg.get("canaux", []):
        try:
            posts = fetch(c["canal"]); lus += len(posts)
        except Exception as e:
            print("Telegram indisponible pour", c.get("canal"), ":", e); return None   # on ne touche a rien si la lecture echoue
        for p in sorted(posts, key=lambda x: x["date"]):
            lst = extraire_implicite(p, c.get("nom", c["canal"]), idx, aujourdhui, centres, noms_deps, ignores) if c.get("tout_est_blocus") else extraire_post(p, c["canal"], c.get("nom", c["canal"]), idx, aujourdhui)
            for e in lst:
                cle = (e["ville"], e["dep"], e["date"], rdv.norm(e["lieu"]) if c.get("tout_est_blocus") else "")
                if e["alerte"] == "annulée" or cle not in evts:
                    evts[cle] = e
                else:   # message plus recent, meme blocus : on met a jour heure et lieu
                    evts[cle].update({k: e[k] for k in ("heure", "lieu", "post", "texte") if e[k]})
    # Telegram ne montre que les derniers messages : on garde les blocus deja releves tant que leur date n'est pas passee
    deja = {e["id"] for e in evts.values()}
    for e in rdv.lire_json(Path(data) / "blocus.json", {}).get("evenements", []):
        cle = (e["ville"], e["dep"], e["date"], rdv.norm(e.get("lieu", "")))
        if e["id"] not in deja and e["date"] >= aujourdhui.isoformat():
            evts.setdefault(cle, e)
    rdv.ecrire_json(Path(data) / "blocus_ignores.json", {"maj": maintenant.isoformat(), "lignes": ignores[:300]})
    res = [e for e in evts.values() if e["id"] not in masques and e["date"] >= aujourdhui.isoformat()]
    res.sort(key=lambda e: (e["date"], e["ville"]))
    rdv.ecrire_json(Path(data) / "blocus.json", {"maj": maintenant.isoformat(), "evenements": res})
    print("Blocus (Telegram, sources de confiance) : %d annonces, %d messages lus" % (len(res), lus))
    return res

if __name__ == "__main__":
    import sys
    maj(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data")
