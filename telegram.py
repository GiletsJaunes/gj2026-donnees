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

def lire_canal(canal):
    req = urllib.request.Request("https://t.me/s/" + canal, headers={"User-Agent": rdv.UA, "Accept-Language": "fr"})
    with urllib.request.urlopen(req, timeout=25) as r:
        page = r.read().decode("utf-8", "ignore")
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

def maj(data, maintenant=None, aujourdhui=None, fetch=lire_canal):
    maintenant = maintenant or dt.datetime.now(rdv.PARIS)
    aujourdhui = aujourdhui or maintenant.date()
    idx = rdv.charger_communes(data, None)
    if not idx:
        print("Blocus : aucune commune disponible, rien n'est modifie."); return None
    cfg = rdv.lire_json(Path(__file__).resolve().parent / "sources_sures.json", {"canaux": []})
    masques = set(rdv.lire_json(Path(data) / "masques.json", {}).get("blocus", []))
    evts, lus = {}, 0
    for c in cfg.get("canaux", []):
        try:
            posts = fetch(c["canal"]); lus += len(posts)
        except Exception as e:
            print("Telegram indisponible pour", c.get("canal"), ":", e); return None   # on ne touche a rien si la lecture echoue
        for p in sorted(posts, key=lambda x: x["date"]):
            for e in extraire_post(p, c["canal"], c.get("nom", c["canal"]), idx, aujourdhui):
                cle = (e["ville"], e["dep"], e["date"])
                if e["alerte"] == "annulée" or cle not in evts:
                    evts[cle] = e
                else:   # message plus recent, meme blocus : on met a jour heure et lieu
                    evts[cle].update({k: e[k] for k in ("heure", "lieu", "post", "texte") if e[k]})
    res = [e for e in evts.values() if e["id"] not in masques and e["date"] >= aujourdhui.isoformat()]
    res.sort(key=lambda e: (e["date"], e["ville"]))
    rdv.ecrire_json(Path(data) / "blocus.json", {"maj": maintenant.isoformat(), "evenements": res})
    print("Blocus (Telegram, sources de confiance) : %d annonces, %d messages lus" % (len(res), lus))
    return res

if __name__ == "__main__":
    import sys
    maj(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data")
