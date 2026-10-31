#!/usr/bin/env python3
"""Veille presse du site Gilets jaunes 2026.
Lit les flux des journaux, garde les articles qui parlent du mouvement, releve les chiffres (barometre),
ecrit les fichiers du dossier data/. Aucune IA obligatoire. Utilisation :  python scripts/veille.py
Test sans internet :  python scripts/veille.py --fixtures essai.json --sortie /tmp/essai"""
import argparse, datetime as dt, hashlib, html, json, os, re, sys, urllib.parse, urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extraction as x

ICI = Path(__file__).resolve().parent
PARIS = ZoneInfo("Europe/Paris")
UA = "Mozilla/5.0 (compatible; GJ2026-veille/1.0; +https://github.com)"
CONSERVER_ARTICLES_JOURS = 21
CONSERVER_FAITS_JOURS = 60

def lire_json(chemin, defaut):
    try:
        return json.loads(Path(chemin).read_text(encoding="utf-8"))
    except Exception:
        return defaut

def ecrire_json(chemin, obj):
    Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    Path(chemin).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

def norm(t):
    return re.sub(r"[^a-z0-9]+", " ", x.sans_accents(t).lower()).strip()

def sha(t, n=12):
    return hashlib.sha1(t.encode("utf-8")).hexdigest()[:n]

def nettoyer(t):
    t = re.sub(r"<[^>]+>", " ", t or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()

# ---------------- medias, departements ----------------
MEDIAS = {norm(k): v for k, v in lire_json(ICI / "medias.json", {}).items()}
DEPS = lire_json(ICI / "departements.json", {})
VILLES = {}

def charger_villes(racine):
    global VILLES
    brut = lire_json(racine / "data" / "actions.json", [])
    par_ville = {}
    for a in brut:
        par_ville.setdefault(a["v"], set()).add(a["dep"])
    VILLES = {v: list(d)[0] for v, d in par_ville.items() if len(d) == 1 and len(v) >= 5}

def bord_de(nom):
    return MEDIAS.get(norm(nom))

def detecter_deps(texte):
    trouves = set()
    for code, nom in DEPS.items():
        if len(nom) >= 5 and re.search(r"(?<!\w)" + re.escape(nom) + r"(?!\w)", texte):
            trouves.add(code)
    for ville, code in VILLES.items():
        if re.search(r"(?<!\w)" + re.escape(ville) + r"(?!\w)", texte):
            trouves.add(code)
    if re.search(r"(?<!\w)Paris(?!\w)", texte):
        trouves.add("75")
    return sorted(trouves)[:4]

# ---------------- lecture des flux ----------------
def telecharger(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()

def local(tag):
    return tag.split("}")[-1]

def parse_date(t, defaut):
    if not t:
        return defaut
    try:
        d = parsedate_to_datetime(t)
    except Exception:
        try:
            d = dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
        except Exception:
            return defaut
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(PARIS)

def lire_flux(octets, nom_media, maintenant, google=False):
    racine = ET.fromstring(octets)
    articles = []
    for it in racine.iter():
        if local(it.tag) not in ("item", "entry"):
            continue
        champs = {}
        for c in it:
            champs.setdefault(local(c.tag), c)
        titre = nettoyer(champs["title"].text if "title" in champs else "")
        lien = ""
        if "link" in champs:
            lien = (champs["link"].text or champs["link"].attrib.get("href", "")).strip()
        def premier(*noms):
            for n in noms:
                if n in champs and (champs[n].text or "").strip():
                    return champs[n].text
            return None
        resume = nettoyer(premier("description", "summary", "content") or "")
        date = parse_date(premier("pubDate", "published", "updated", "date"), maintenant)
        media = nom_media
        if google:
            src = champs.get("source")
            if src is not None and src.text:
                media = nettoyer(src.text)
                titre = re.sub(r"\s+-\s+" + re.escape(media) + r"\s*$", "", titre)
            resume = ""
        if titre and lien:
            articles.append({"titre": titre, "resume": resume[:320], "url": lien, "media": media, "date": date.isoformat()})
    return articles

# ---------------- regroupement des articles ----------------
STOP = set("dans pour avec cette leur leurs sont plus mais comme tout tous aussi entre sans sous chez vers apres avant depuis lors sera sera ete etre avoir fait faire sur par une des les aux ces ses mes nos vos dont donc ainsi alors encore deja tres bien meme quand quel quelle quels quelles".split())

def jetons(titre):
    return {m for m in norm(titre).split() if len(m) > 3 and m not in STOP}

def proches(a, b):
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= 0.55

def ajouter_article(articles, nouveau):
    """Fusionne dans un article existant sur le meme sujet, sinon ajoute."""
    jt = jetons(nouveau["titre"])
    for a in articles:
        if a["url"] == nouveau["url"] or proches(jt, jetons(a["titre"])):
            noms = {m["nom"] for m in a["medias"]}
            if nouveau["media"] not in noms:
                a["medias"].append({"nom": nouveau["media"], "url": nouveau["url"], "bord": bord_de(nouveau["media"])})
                a["nb_medias"] = len(a["medias"]) + a.get("autres", 0)
            if nouveau["date"] < a["date"]:
                a["date"] = nouveau["date"]
            return False
    texte = nouveau["titre"] + " " + nouveau["resume"]
    articles.append({"id": sha(nouveau["url"]), "titre": nouveau["titre"], "resume": nouveau["resume"], "url": nouveau["url"], "date": nouveau["date"],
                     "theme": x.theme_de(texte), "mots": x.mots_cles_de(texte), "deps": detecter_deps(texte),
                     "medias": [{"nom": nouveau["media"], "url": nouveau["url"], "bord": bord_de(nouveau["media"])}], "autres": 0, "nb_medias": 1})
    return True

# ---------------- chiffres ----------------
def cle_fait(f):
    qui = f["cote"] if f["metrique"] == "manifestants" else norm(f.get("qui") or "")
    return sha("|".join([f["metrique"], str(qui), f["portee"], str(f["jour"]), str(f["valeur"])]), 10)

def mettre_a_jour_faits(faits, items, maintenant):
    par_id = {f["id"]: f for f in faits}
    nouveaux = 0
    for it in items:
        jour = it["date"][:10]
        texte = it["titre"] + ". " + it["resume"]
        for phrase in x.decouper_phrases(texte):
            for f in x.extraire_faits(phrase, jour):
                if f["jour"] > jour:  # une date dans le futur n'est pas un releve
                    continue
                fid = cle_fait(f)
                src = {"nom": it["media"], "url": it["url"], "titre": it["titre"]}
                e = par_id.get(fid)
                if e is None:
                    e = {"id": fid, "metrique": f["metrique"], "valeur": f["valeur"], "unite": f["unite"], "qui": f["qui"], "cote": f["cote"],
                         "portee": f["portee"], "jour": f["jour"], "phrase": phrase, "sources": [], "bords": [], "recoupe": False,
                         "maj": maintenant.isoformat()}
                    par_id[fid] = e
                    nouveaux += 1
                if all(s["nom"] != src["nom"] for s in e["sources"]):
                    e["sources"].append(src)
                    e["maj"] = maintenant.isoformat()
    for e in par_id.values():
        bords = set(e.get("bords", []))
        for s in e["sources"]:
            b = s.get("bord") or bord_de(s["nom"])
            if b:
                bords.add(b)
        e["bords"] = sorted(bords)
        e["recoupe"] = bool(e.get("qui")) and len(e["sources"]) >= 2 and len(bords) >= 2
    limite = (maintenant - dt.timedelta(days=CONSERVER_FAITS_JOURS)).strftime("%Y-%m-%d")
    liste = [f for f in par_id.values() if (f["jour"] or "") >= limite]
    liste.sort(key=lambda f: (f["jour"] or "", f["maj"]), reverse=True)
    return liste, nouveaux

# ---------------- resume du jour ----------------
def meilleur(faits, **crit):
    c = [f for f in faits if f["recoupe"] and all(f.get(k) == v for k, v in crit.items())]
    c.sort(key=lambda f: (len(f["sources"]), f["maj"]), reverse=True)
    return c[0] if c else None

def faire_resume(articles, faits, jour):
    du_jour = [a for a in articles if a["date"][:10] == jour]
    du_jour.sort(key=lambda a: (a["nb_medias"], a["date"]), reverse=True)
    chiffres = []
    for lib, crit in (("Manifestants selon les autorités", dict(metrique="manifestants", cote="autorites", jour=jour)),
                      ("Manifestants selon les organisateurs", dict(metrique="manifestants", cote="organisateurs", jour=jour)),
                      ("Interpellations", dict(metrique="interpellations", jour=jour)),
                      ("Policiers et gendarmes blessés", dict(metrique="blesses_forces", jour=jour))):
        f = meilleur(faits, **crit)
        if f:
            chiffres.append({"libelle": lib, "valeur": f["valeur"], "qui": f.get("qui"), "sources": [s["nom"] for s in f["sources"]][:4]})
    phrases = ["%d articles ont parlé du mouvement ce jour-là." % len(du_jour)] if du_jour else []
    for c in chiffres:
        phrases.append("%s : %s%s." % (c["libelle"], "{:,}".format(c["valeur"]).replace(",", " "), (" (" + c["qui"] + ")") if c["qui"] else ""))
    resume = {"date": jour, "texte": " ".join(phrases), "chiffres": chiffres,
              "titres": [{"titre": a["titre"], "url": a["url"], "media": a["medias"][0]["nom"], "nb_medias": a["nb_medias"]} for a in du_jour[:8]],
              "auteur": "automatique"}
    cle = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if cle and du_jour:
        try:
            invite = ("Tu rédiges la chronique du jour d'un site d'information sur le mouvement des gilets jaunes. "
                      "Écris 6 à 8 phrases factuelles en français, ton neutre, sans slogan, en citant « selon … » pour chaque chiffre. "
                      "N'invente rien : utilise seulement ces éléments.\nChiffres : %s\nTitres : %s" %
                      (json.dumps(chiffres, ensure_ascii=False), " | ".join(a["titre"] for a in du_jour[:12])))
            corps = json.dumps({"model": "claude-haiku-5-5", "max_tokens": 700, "messages": [{"role": "user", "content": invite}]}).encode()
            req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=corps, headers={
                "x-api-key": cle, "anthropic-version": "2023-06-01", "content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                texte = json.loads(r.read())["content"][0]["text"].strip()
            if len(texte) > 80:
                resume["texte"], resume["auteur"] = texte, "ia"
        except Exception as e:
            print("Résumé IA indisponible :", e)
    return resume


def maj_durees(data):
    """Ajoute la duree (secondes) des videos de la radio, pour que la radio tourne comme un direct."""
    chemin = data / "radio.json"
    if not chemin.exists():
        return
    radio = lire_json(chemin, None)
    if not radio:
        return
    change = False
    for liste in (radio.get("pistes", []), radio.get("interruptions", [])):
        for p in liste:
            m = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})", p.get("youtube", "") or "") or re.fullmatch(r"([A-Za-z0-9_-]{11})", (p.get("youtube", "") or "").strip())
            if not m:
                continue
            ident = m.group(1)
            if p.get("duree") and p.get("duree_id") == ident:
                continue
            try:
                req = urllib.request.Request("https://www.youtube.com/watch?v=" + ident, headers={"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"})
                with urllib.request.urlopen(req, timeout=25) as r:
                    page = r.read().decode("utf-8", "ignore")
                d = re.search(r'"lengthSeconds":"(\d+)"', page)
                if d and int(d.group(1)) > 5:
                    p["duree"], p["duree_id"] = int(d.group(1)), ident
                    change = True
                else:
                    print("Duree introuvable pour", ident)
            except Exception as e:
                print("Duree YouTube indisponible pour", ident, ":", e)
    if change:
        chemin.write_text(json.dumps(radio, ensure_ascii=False, indent=1), encoding="utf-8")
        print("Durees de la radio mises a jour")

def nettoyer_faits(faits):
    """Re-verifie les comptages deja gardes avec les regles actuelles : national seulement, bon 'selon qui', bon jour."""
    out, vus = [], {}
    for f in faits:
        if f["metrique"] == "manifestants":
            ok = [g for g in x.extraire_faits(f["phrase"], f["jour"]) if g["metrique"] == "manifestants" and g["valeur"] == f["valeur"]]
            if not ok:
                continue
            f["qui"], f["cote"], f["jour"] = ok[0]["qui"], ok[0]["cote"], ok[0]["jour"]
            f["id"] = cle_fait(f)
        cle = (f["metrique"], f["valeur"], f["jour"], f.get("cote") if f["metrique"] == "manifestants" else norm(f.get("qui") or ""))
        if cle in vus:
            e = vus[cle]
            noms = {s["nom"] for s in e["sources"]}
            e["sources"] += [s for s in f["sources"] if s["nom"] not in noms]
            continue
        vus[cle] = f
        out.append(f)
    return out


BASE_REQUETES = ["gilets jaunes", "mobilisation manifestation", "blocus lycées", "manifestants selon le ministère de l'Intérieur", "interpellations gardes à vue manifestation",
                 "policiers blessés manifestation", "RIC référendum d'initiative citoyenne", "vie chère manifestation", "intersyndicale CGT mobilisation", "dette taux d'emprunt France"]

def collecter_jour(config, jour, maintenant):
    """Articles d'un jour precis (Google Actualites, requetes bornees par date) : sert au rattrapage du livre."""
    x1 = dt.date.fromisoformat(jour)
    borne = " after:%s before:%s" % (x1.isoformat(), (x1 + dt.timedelta(days=1)).isoformat())
    recus = []
    for q in BASE_REQUETES + list(config.get("google_actualites", []))[:4]:
        url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(q + borne) + "&hl=fr&gl=FR&ceid=FR:fr"
        try:
            recus += [a for a in lire_flux(telecharger(url), "Google Actualités", maintenant, True) if a["date"][:10] == jour]
        except Exception as e:
            print("Rattrapage", jour, ":", q, e)
    vus, uniques = set(), []
    for a in recus:
        if a["url"] not in vus:
            vus.add(a["url"]); uniques.append(a)
    return [a for a in uniques if x.PERTINENT.search(a["titre"] + " " + a["resume"])]

# ---------------- programme principal ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", help="fichier JSON d'articles (test sans internet)")
    ap.add_argument("--sortie", help="dossier data de sortie (par defaut ../data)")
    args = ap.parse_args()
    racine = ICI.parent
    data = Path(args.sortie) if args.sortie else racine / "data"
    charger_villes(racine)
    if not args.fixtures:
        try:
            maj_durees(data)
        except Exception as e:
            print('Radio :', e)
    maintenant = dt.datetime.now(PARIS)
    config = lire_json(ICI / "feeds.json", {"flux": [], "google_actualites": []})
    etat = {"maj": maintenant.isoformat(), "flux": []}
    recus = []
    if args.fixtures:
        recus = lire_json(args.fixtures, [])
    else:
        sources = [(f["nom"], f["url"], False) for f in config["flux"]]
        for q in config.get("google_actualites", []):
            sources.append(("Google Actualités", "https://news.google.com/rss/search?q=" + urllib.parse.quote(q + " when:3d") + "&hl=fr&gl=FR&ceid=FR:fr", True))
        for nom, url, google in sources:
            try:
                arts = lire_flux(telecharger(url), nom, maintenant, google)
                recus += arts
                etat["flux"].append({"nom": nom if not google else "Google : " + urllib.parse.unquote(url.split("q=")[1].split("&")[0])[:40], "ok": True, "n": len(arts)})
            except Exception as e:
                etat["flux"].append({"nom": nom, "ok": False, "erreur": str(e)[:120]})
                print("FLUX EN ERREUR :", nom, url, e)
    pertinents = [a for a in recus if x.PERTINENT.search(a["titre"] + " " + a["resume"])]
    print("%d articles lus, %d retenus" % (len(recus), len(pertinents)))
    masques = lire_json(data / "masques.json", {"faits": [], "articles": []})
    actus = lire_json(data / "actus.json", {"articles": []})["articles"]
    ajoutes = sum(ajouter_article(actus, a) for a in sorted(pertinents, key=lambda a: a["date"]))
    limite = (maintenant - dt.timedelta(days=CONSERVER_ARTICLES_JOURS)).isoformat()
    actus = [a for a in actus if a["date"] >= limite and a["id"] not in masques.get("articles", [])]
    actus.sort(key=lambda a: a["date"], reverse=True)
    actus = actus[:1500]
    faits_exist = lire_json(data / "barometre.json", {"faits": []})["faits"]
    faits_exist = nettoyer_faits(faits_exist)
    faits, nouveaux = mettre_a_jour_faits(faits_exist, pertinents, maintenant)
    faits = [f for f in faits if f["id"] not in masques.get("faits", [])]
    print("%d nouveaux articles, %d nouveaux chiffres" % (ajoutes, nouveaux))
    if not args.fixtures:
        try:
            import livre
            a_faire = livre.jours_a_ecrire(data, maintenant)
            a_refaire = [j for j in livre.chapitres_ia_a_refaire(data, maintenant) if j not in a_faire][:2]
            for jr in (a_faire[:3] + a_refaire):
                if sum(a["date"][:10] == jr for a in actus) < 60:
                    pj = collecter_jour(config, jr, maintenant)
                    print("Rattrapage %s : %d articles retrouves" % (jr, len(pj)))
                    for a in sorted(pj, key=lambda a: a["date"]):
                        ajouter_article(actus, a)
                    faits, nb = mettre_a_jour_faits(faits, pj, maintenant)
                    faits = [f for f in faits if f["id"] not in masques.get("faits", [])]
                livre.generer(actus, faits, jr, data)
            livre.maj_index(data)
        except Exception as e:
            print("Livre :", e)
        actus.sort(key=lambda a: a["date"], reverse=True)
    ecrire_json(data / "actus.json", {"maj": maintenant.isoformat(), "articles": actus})
    ecrire_json(data / "barometre.json", {"maj": maintenant.isoformat(), "faits": faits})
    jour = maintenant.strftime("%Y-%m-%d")
    hier = (maintenant - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    jours_dispo = sorted({a["date"][:10] for a in actus})
    cible = hier if sum(a["date"][:10] == hier for a in actus) >= 3 else (jour if sum(a["date"][:10] == jour for a in actus) >= 3 else (jours_dispo[-1] if jours_dispo else hier))
    resume = faire_resume(actus, faits, cible)
    ecrire_json(data / "resume.json", resume)
    ecrire_json(data / "archives" / (jour + ".json"), {"date": jour, "maj": maintenant.isoformat(),
        "faits": [f for f in faits if f["recoupe"] and (f["jour"] == jour or f["maj"][:10] == jour)],
        "articles": [{"titre": a["titre"], "url": a["url"], "theme": a["theme"], "nb_medias": a["nb_medias"]} for a in actus if a["date"][:10] == jour][:60]})
    ecrire_json(data / "etat.json", etat)
    try:
        import rdv
        brut = list(recus)
        if not args.fixtures:
            for q in rdv.requetes(maintenant.date()):
                try:
                    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(q + " when:7d") + "&hl=fr&gl=FR&ceid=FR:fr"
                    brut += lire_flux(telecharger(url), "Google Actualités", maintenant, True)
                except Exception as e:
                    print("Rendez-vous :", q, e)
        vus, uniques = set(), []
        for a in brut:
            if a["url"] not in vus:
                vus.add(a["url"]); uniques.append(a)
        rdv.maj(uniques, data, maintenant)
    except Exception as e:
        print("Rendez-vous :", e)
    if not args.fixtures:
        try:
            import lives
            ancien = lire_json(data / "lives.json", {"mouvement": [], "chaines": []})
            res = lives.chercher({"mouvement": ancien.get("mouvement", []), "chaines": ancien.get("chaines", [])})
            res["maj"] = maintenant.isoformat()
            ecrire_json(data / "lives.json", res)
        except Exception as e:
            print("Directs :", e)
    ko = [f for f in etat["flux"] if not f["ok"]]
    if etat["flux"] and len(ko) == len(etat["flux"]):
        print("TOUS LES FLUX ONT ECHOUE")
        sys.exit(1)

if __name__ == "__main__":
    main()
