#!/usr/bin/env python3
"""Rendez-vous annonces (manifestations, rassemblements, blocages) releves dans la presse pour la CARTE.

Regles anti-fausses-infos (on ne reproduit pas les erreurs des sites qui listent tout sans verifier) :
 - un rendez-vous n'existe sur la carte que s'il est ANNONCE AU FUTUR dans un article (appel, prevu, aura lieu...),
   jamais a partir d'un compte rendu au passe ;
 - il faut une ville certaine (nom exact de commune, homonymes ecartes sauf si le departement est cite),
   une date precise dans les 3 prochaines semaines, et au moins un article cite en source ;
 - statut « recoupe » = au moins 2 medias differents ; sinon « annonce » (1 seul media), affiche a part ;
 - une mention « interdite » ou « annulee » est signalee, et ces rendez-vous ne sont jamais comptes comme confirmes ;
 - aucun ajout manuel anonyme : seuls les articles lus par le robot comptent. masques.json (cle « rdv ») retire un id.
Sortie : data/rdv.json. Cache des communes : data/cache/communes.json (API officielle geo.api.gouv.fr)."""
import datetime as dt, hashlib, json, re, unicodedata, urllib.parse, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
HORIZON_JOURS = 21
UA = "Mozilla/5.0 (compatible; GJ2026-veille/1.0)"

TRIGGERS = [("blocage", r"blocage|bloquer|bloqueront|filtrage|barrage"), ("manifestation", r"manifestation|manifester|manifesteront|cortège|défilé|défileront"),
            ("rassemblement", r"rassemblement|rassembler|se rassembleront|piquet|sit-in|occupation"), ("marche", r"\bmarche\b|marcheront"),
            ("mobilisation", r"mobilisation|journée d.action|appel à la grève|grève")]
FUTUR = re.compile(r"\b(appel|appelle|appellent|appelé|prévu|prévue|prévus|prévues|aura lieu|auront lieu|se tiendra|se tiendront|se rassembleront|rendez-vous|organis[ée]|organisera|manifesteront|défileront|bloqueront|invit|à partir de|dès|ce samedi|demain|samedi prochain|ce week-end|annonc|déclaré|déclarée|attendu|attendus|veulent|souhaitent|comptent|entendent|prévoient|prévoit|lancent|lance|appeler)\b", re.I)
PASSE = re.compile(r"\b(a réuni|ont réuni|ont manifesté|a manifesté|ont défilé|a défilé|s.est tenu|se sont tenus|se sont rassemblés|s.est rassemblé|ont rassemblé|a rassemblé|ont bloqué|a bloqué|hier|samedi dernier|dernier|ce week-end dernier|avant-hier|ont été interpellés|bilan|selon la préfecture de police, \d)", re.I)
HORS_SUJET = re.compile(r"marche blanche|hommage|commémor|marché|match|concert|festival|téléthon|pro-palestin|ukraine|gaza|israël", re.I)
ORGAS = [("CGT", r"\bCGT\b"), ("FO", r"\bFO\b|Force ouvrière"), ("CFDT", r"\bCFDT\b"), ("Solidaires", r"Solidaires|\bSUD\b"), ("FSU", r"\bFSU\b"),
         ("UNEF", r"\bUNEF\b"), ("Confédération paysanne", r"Confédération paysanne|Coordination rurale"), ("intersyndicale", r"intersyndicale"),
         ("lycéens", r"lycéens|étudiants|lycée"), ("gilets jaunes", r"gilets? jaunes?"), ("LFI", r"insoumis|\bLFI\b"), ("agriculteurs", r"agriculteurs|éleveurs")]
PRO_DEMANDE = re.compile(r"gilets? jaunes?|\bRIC\b|référendum d.initiative|31 octobre|bloquons tout|17 octobre|24 octobre", re.I)
NON_VILLES = {"France", "Paris-Match", "Macron", "Bayrou", "Lecornu", "Retailleau", "Mélenchon", "Tondelier", "Bardella", "Attal", "Faure", "Rousseau", "Ruffin", "Philippe", "Villepin", "Gilets",
              "Dimanche", "Samedi", "Vendredi", "Jeudi", "Lundi", "Mardi", "Mercredi", "Octobre", "Novembre", "Décembre", "Janvier", "Mars", "Mai", "Juin", "Juillet", "Août", "Union", "Europe", "Marine",
              "Sud", "Nord", "Est", "Ouest", "Centre", "République", "Assemblée", "Sénat", "Matignon", "Élysée", "Bercy", "Bon", "Mont", "Pont", "Port", "Château", "Saint", "Sainte", "Grand", "Grande", "Petit"}
PREP = {"à", "au", "aux", "dans", "de", "d", "devant", "vers", "sur", "entre", "et", "ou", ",", "(", "-", "–", "devant", "près", "autour", "pour", "En", "À", "Au", "Aux", "Dans", "De", "Devant", "Vers", "Pour"}

def norm(t):
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower().strip()

def lire_json(p, d):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return d

def ecrire_json(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(o, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

# ---------------- communes ----------------
def charger_communes(data, secours=None):
    """Retourne {nom_normalise: [ (nom, dep, lat, lng, population), ... ]}. Cache puis API officielle puis liste de secours."""
    cache = Path(data) / "cache" / "communes.json"
    liste = lire_json(cache, None)
    if not liste:
        try:
            url = "https://geo.api.gouv.fr/communes?fields=nom,codeDepartement,centre,population&format=json&geometry=centre"
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            brut = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
            liste = [[c["nom"], c.get("codeDepartement", ""), round(c["centre"]["coordinates"][1], 4), round(c["centre"]["coordinates"][0], 4), c.get("population", 0)]
                     for c in brut if c.get("centre") and c.get("population", 0) >= 1500]
            ecrire_json(cache, liste)
        except Exception as e:
            print("Communes (API) :", e)
            liste = secours or lire_json(Path(__file__).resolve().parent / "villes_secours.json", [])
    idx = {}
    for nom, dep, lat, lng, pop in liste:
        idx.setdefault(norm(nom), []).append((nom, dep, lat, lng, pop))
    return idx

def trouver_ville(idx, mots, i, deps_texte):
    """Plus long nom de commune commencant au mot i. Retourne (commune, nb_mots) ou None."""
    for n in (4, 3, 2, 1):
        cand = " ".join(mots[i:i + n])
        if len(mots[i:i + n]) < n:
            continue
        cand = re.sub(r"[.,;:!?)»]+$", "", cand)
        if cand in NON_VILLES or cand.split(" ")[0] in {"Mont", "Port", "Pont"} and n == 1:
            continue
        trouves = idx.get(norm(cand))
        if not trouves:
            continue
        if len(trouves) == 1:
            return trouves[0], n
        dans = [c for c in trouves if c[1] in deps_texte]
        if len(dans) == 1:
            return dans[0], n
        gros = sorted(trouves, key=lambda c: -c[4])
        if gros[0][4] >= 3 * gros[1][4] and gros[0][4] >= 20000:
            return gros[0], n
        return None   # homonymes : on prefere ne rien mettre que se tromper
    return None

# ---------------- dates ----------------
def prochain_jour(base, wd, meme_jour_ok):
    delta = (wd - base.weekday()) % 7
    if delta == 0 and not meme_jour_ok:
        delta = 7
    return base + dt.timedelta(days=delta)

def dates_de(phrase, base, aujourdhui):
    out = set()
    for m in re.finditer(r"\b(\d{1,2})(?:er)?\s+(" + "|".join(MOIS) + r")\b", phrase, re.I):
        j, mois = int(m.group(1)), MOIS.index(m.group(2).lower().replace("fevrier", "février")) + 1
        an = base.year
        try:
            d = dt.date(an, mois, j)
            if d < base - dt.timedelta(days=180):
                d = dt.date(an + 1, mois, j)
            out.add(d)
        except ValueError:
            pass
    for m in re.finditer(r"\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\b(\s+prochain)?", phrase, re.I):
        wd = JOURS.index(m.group(1).lower())
        ce = bool(re.search(r"\bce\s+" + m.group(1), phrase, re.I))
        out.add(prochain_jour(base, wd, ce or wd == base.weekday() and "aujourd" in phrase.lower()))
    if re.search(r"\bdemain\b", phrase, re.I):
        out.add(base + dt.timedelta(days=1))
    if re.search(r"aujourd.hui|ce matin|cet après-midi|ce soir", phrase, re.I):
        out.add(base)
    if re.search(r"ce week-end", phrase, re.I):
        out.add(prochain_jour(base, 5, True))
    return {d for d in out if aujourdhui <= d <= aujourdhui + dt.timedelta(days=HORIZON_JOURS)}

def phrases(texte):
    return [p.strip() for p in re.split(r"(?<=[.!?…])\s+|\s[:|]\s|\n", texte) if len(p.strip()) > 20]

def heure_de(p):
    m = re.search(r"\b(\d{1,2})\s?[hH]\s?(\d{2})?\b", p)
    if not m or int(m.group(1)) > 23:
        return ""
    return "%02d:%s" % (int(m.group(1)), m.group(2) or "00")

# ---------------- extraction ----------------
def extraire(articles, idx, aujourdhui, bords=None):
    """Retourne la liste de rendez-vous (dict) cle par (commune, date)."""
    evts = {}
    for a in articles:
        try:
            base = dt.date.fromisoformat(a["date"][:10])
        except Exception:
            continue
        texte = (a.get("titre", "") + ". " + a.get("resume", ""))
        if HORS_SUJET.search(texte):
            continue
        deps_texte = set(a.get("deps", []))
        medias = a.get("medias") or [a.get("media", "")]
        for ph in phrases(texte):
            type_ = next((nom for nom, rx in TRIGGERS if re.search(rx, ph, re.I)), None)
            if not type_ or not FUTUR.search(ph) or PASSE.search(ph):
                continue
            dates = dates_de(ph, base, aujourdhui)
            if not dates:
                continue
            mots = ph.replace("’", "'").replace("l'", "l' ").split()
            vus = set()
            i = 0
            while i < len(mots):
                mot = mots[i]
                if mot[:1].isupper() and (i == 0 or re.sub(r"[^\wÀ-ÿ,()–-]", "", mots[i - 1]).lower().rstrip(",") in {p.lower() for p in PREP} or mots[i - 1].endswith(",") or mots[i - 1].endswith("'")):
                    r = trouver_ville(idx, mots, i, deps_texte)
                    if r:
                        (nom, dep, lat, lng, pop), n = r
                        for d in dates:
                            cle = (norm(nom), dep, d.isoformat())
                            e = evts.setdefault(cle, {"ville": nom, "dep": dep, "lat": lat, "lng": lng, "date": d.isoformat(), "heure": "", "types": set(), "orgas": set(),
                                                       "sources": {}, "mouvement": False, "alerte": ""})
                            e["types"].add(type_)
                            e["heure"] = e["heure"] or heure_de(ph)
                            for nom_o, rx in ORGAS:
                                if re.search(rx, texte):
                                    e["orgas"].add(nom_o)
                            e["mouvement"] = e["mouvement"] or bool(PRO_DEMANDE.search(texte))
                            if re.search(r"interdit|interdiction", ph, re.I):
                                e["alerte"] = "interdite"
                            if re.search(r"annul|reporté|reportée", ph, re.I):
                                e["alerte"] = "annulée"
                            for m in medias:
                                if m and m not in e["sources"]:
                                    e["sources"][m] = {"media": m, "url": a["url"], "titre": a["titre"][:140], "date": a["date"][:10]}
                        i += n
                        continue
                i += 1
    return evts

def construire(evts, masques):
    sortie = []
    for (nom, dep, d), e in evts.items():
        ident = hashlib.sha1((nom + dep + d).encode()).hexdigest()[:10]
        if ident in masques:
            continue
        medias = sorted(e["sources"])
        recoupe = len(medias) >= 2 and not e["alerte"]
        type_ = sorted(e["types"], key=lambda t: ["manifestation", "rassemblement", "blocage", "marche", "mobilisation"].index(t))[0]
        sortie.append({"id": ident, "ville": e["ville"], "dep": e["dep"], "lat": e["lat"], "lng": e["lng"], "date": e["date"], "heure": e["heure"],
                       "type": type_, "organisateurs": sorted(e["orgas"]), "mouvement": e["mouvement"], "alerte": e["alerte"],
                       "statut": "recoupe" if recoupe else "annonce", "nb_medias": len(medias),
                       "sources": [e["sources"][m] for m in medias][:5]})
    sortie.sort(key=lambda x: (x["date"], -x["nb_medias"], x["ville"]))
    return sortie[:600]

def maj(articles, data, maintenant=None, secours=None, aujourdhui=None):
    maintenant = maintenant or dt.datetime.now(PARIS)
    aujourdhui = aujourdhui or maintenant.date()
    idx = charger_communes(data, secours)
    if not idx:
        print("Rendez-vous : aucune commune disponible, rien n'est modifie.")
        return None
    masques = set(lire_json(Path(data) / "masques.json", {}).get("rdv", []))
    evts = extraire(articles, idx, aujourdhui)
    # on garde les rendez-vous deja connus tant qu'ils ne sont pas passes (un article peut sortir du flux avant la date)
    ancien = lire_json(Path(data) / "rdv.json", {}).get("evenements", [])
    nouveaux = construire(evts, masques)
    cles = {(e["ville"], e["dep"], e["date"]) for e in nouveaux}
    for e in ancien:
        if e["date"] >= aujourdhui.isoformat() and (e["ville"], e["dep"], e["date"]) not in cles and e["id"] not in masques:
            nouveaux.append(e)
    nouveaux.sort(key=lambda x: (x["date"], -x["nb_medias"], x["ville"]))
    res = {"maj": maintenant.isoformat(), "evenements": nouveaux,
           "stats": {"total": len(nouveaux), "recoupes": sum(e["statut"] == "recoupe" for e in nouveaux), "villes": len({(e["ville"], e["dep"]) for e in nouveaux})}}
    ecrire_json(Path(data) / "rdv.json", res)
    print("Rendez-vous : %d (%d recoupés) dans %d villes" % (res["stats"]["total"], res["stats"]["recoupes"], res["stats"]["villes"]))
    return res

def requetes(aujourdhui):
    """Requetes Google Actualites ciblees sur les prochains samedis et jours de mobilisation."""
    jours = []
    for k in range(0, 15):
        d = aujourdhui + dt.timedelta(days=k)
        if d.weekday() == 5:
            jours.append("%d %s" % (d.day, MOIS[d.month - 1]))
    qs = ["appel à manifester samedi gilets jaunes", "rassemblement prévu samedi préfecture manifestation déclarée", "blocage prévu samedi gilets jaunes",
          "intersyndicale appel manifestation samedi", "CGT appel manifestation rassemblement"]
    for j in jours[:2]:
        qs += ["manifestation \"%s\" gilets jaunes" % j, "rassemblement \"%s\" appel" % j, "blocage \"%s\"" % j]
    return qs

if __name__ == "__main__":
    import sys
    data = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data"
    arts = lire_json(data / "actus.json", {"articles": []})["articles"]
    maj(arts, data)
