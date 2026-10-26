"""Le livre du mouvement : un chapitre par jour, ecrit a partir des articles et des chiffres recoupes du jour.
- Avec une cle ANTHROPIC_API_KEY : redaction par IA, a partir UNIQUEMENT des elements fournis (titres, resumes, chiffres, sources).
- Sans cle, ou en cas d'echec : chapitre automatique (modele) construit avec les memes elements.
Garde-fous : tout chiffre ecrit par l'IA doit figurer dans les elements fournis, toute source citee doit exister."""
import datetime as dt, json, os, re, sys, urllib.request
from pathlib import Path

PREMIER_JOUR = "2026-10-16"      # le chapitre 14 (15 octobre) existe deja dans le livre
NUMERO_PREMIER = 15
MODELE = os.environ.get("LIVRE_MODELE", "claude-haiku-5-5")
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
LIB = {"manifestants": "manifestants en France", "blesses_forces": "policiers et gendarmes blessés", "blesses_eleves": "lycéens et manifestants blessés",
       "blesses_education": "blessés parmi les personnels de l’Éducation", "interpellations": "interpellations", "gardes_a_vue": "gardes à vue",
       "detention": "détentions et écrous", "degats": "d’euros de dégâts", "etablissements": "établissements perturbés", "sondage": "% dans un sondage"}
ORDRE = ["manifestants", "interpellations", "gardes_a_vue", "detention", "blesses_forces", "blesses_eleves", "blesses_education", "etablissements", "degats", "sondage"]
THEMES = {"mouvement": "Le mouvement", "repression": "Répression", "colere": "Colère sociale", "argent": "Argent et crise", "politique": "Politique", "krach": "Marchés", "pandemie": "Santé"}

def d(iso): return dt.date.fromisoformat(iso)
def jour_long(iso):
    x = d(iso); return "%s %d %s" % (JOURS[x.weekday()], x.day, MOIS[x.month - 1])
def acte_du(iso):
    x = d(iso)
    if x.weekday() != 5 or x < dt.date(2026, 10, 17): return ""
    n = (x - dt.date(2026, 10, 17)).days // 7 + 1
    r, o = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")], ""
    for v, s in r:
        while n >= v: o += s; n -= v
    return "Acte " + o
def num(v): return "{:,}".format(int(v)).replace(",", " ")
def numero(iso): return NUMERO_PREMIER + (d(iso) - d(PREMIER_JOUR)).days

def jours_a_ecrire(data, maintenant):
    fin = (maintenant.date() - dt.timedelta(days=1)) if maintenant.hour >= 6 else (maintenant.date() - dt.timedelta(days=2))
    out, x = [], d(PREMIER_JOUR)
    while x <= fin:
        if not (data / "chronique" / (x.isoformat() + ".json")).exists():
            out.append(x.isoformat())
        x += dt.timedelta(days=1)
    return out

def chapitres_ia_a_refaire(data, maintenant):
    """Chapitres ecrits par le modele (sans IA) qu'on peut retenter, si une cle existe."""
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip(): return []
    out = []
    for p in sorted((data / "chronique").glob("20*.json")) if (data / "chronique").exists() else []:
        try: c = json.loads(p.read_text(encoding="utf-8"))
        except Exception: continue
        if c.get("auteur") != "ia" and c.get("essais_ia", 0) < 3: out.append(c["date"])
    return out

# ---------------- elements du jour ----------------
def elements(actus, faits, jour):
    arts = [a for a in actus if a["date"][:10] == jour]
    arts.sort(key=lambda a: (a["nb_medias"], a["date"]), reverse=True)
    arts = arts[:45]
    fs = [f for f in faits if f["jour"] == jour]
    fs.sort(key=lambda f: (not f["recoupe"], ORDRE.index(f["metrique"]) if f["metrique"] in ORDRE else 99, -f["valeur"]))
    sources, par_url = [], {}
    def ajoute(nom, url, titre, date):
        if url in par_url: return par_url[url]
        sources.append({"n": len(sources) + 1, "nom": nom, "url": url, "titre": titre, "date": date}); par_url[url] = len(sources); return len(sources)
    lignes = []
    for a in arts:
        n = ajoute(a["medias"][0]["nom"], a["medias"][0]["url"], a["titre"], jour)
        lignes.append({"n": n, "titre": a["titre"], "resume": a.get("resume", ""), "medias": [m["nom"] for m in a["medias"]][:4], "nb_medias": a["nb_medias"], "theme": a.get("theme", "mouvement")})
    fl = []
    for f in fs[:40]:
        ns = [ajoute(s["nom"], s["url"], s.get("titre", ""), jour) for s in f["sources"][:3]]
        fl.append({"metrique": f["metrique"], "valeur": f["valeur"], "qui": f.get("qui"), "recoupe": f["recoupe"], "phrase": f["phrase"], "sources": ns, "noms": [s["nom"] for s in f["sources"]]})
    return lignes, fl, sources

# ---------------- chapitre sans IA ----------------
def chapitre_modele(jour, lignes, fl, sources):
    acte = acte_du(jour)
    rec = [f for f in fl if f["recoupe"]]
    chiffres = []
    vus = set()
    for f in rec:
        cle = (f["metrique"], f["qui"])
        if cle in vus or len(chiffres) >= 6: continue
        vus.add(cle)
        v = num(f["valeur"]) if f["metrique"] != "degats" else num(f["valeur"] / 1e6) + " millions"
        chiffres.append({"valeur": v, "libelle": LIB.get(f["metrique"], f["metrique"]), "detail": ("selon " + f["qui"]) if f["qui"] else "", "sources": f["sources"]})
    for f in fl:
        if not f["recoupe"] and f["metrique"] == "manifestants" and f["qui"] and len(chiffres) < 6:
            chiffres.append({"valeur": num(f["valeur"]), "libelle": LIB["manifestants"], "detail": "selon " + f["qui"] + " (non recoupé à ce stade)", "sources": f["sources"]})
    if chiffres:
        c0 = chiffres[0]
        chapeau = "Le mouvement continue%s : %s %s %s, et la presse suit les suites de la journée." % ((" avec l’" + acte) if acte else "", c0["valeur"], c0["libelle"], c0["detail"])
    else:
        chapeau = "%d articles ont parlé du mouvement ce jour-là ; aucun chiffre n’a pu être recoupé par des médias de bords différents." % len(lignes)
    points = [{"texte": f["phrase"], "sources": f["sources"]} for f in rec[:7]]
    recit, par_theme = [], {}
    for l in lignes:
        par_theme.setdefault(l["theme"], []).append(l)
    for t in ("repression", "mouvement", "colere", "argent", "politique", "krach"):
        ls = par_theme.get(t, [])[:4]
        if not ls: continue
        phr = ["Selon %s, %s" % (l["medias"][0], l["titre"].rstrip(".")) + ((" (repris par %d médias)" % l["nb_medias"]) if l["nb_medias"] > 2 else "") + "." for l in ls]
        recit.append({"texte": " ".join(phr), "sources": [l["n"] for l in ls], "theme": THEMES.get(t, t)})
    titre = (jour_long(jour).capitalize() + (" : " + acte if acte else " : ce que dit la presse"))
    return {"titre": titre, "chapeau": chapeau, "chiffres": chiffres, "points": points, "recit": recit,
            "a_suivre": {"texte": "Le prochain rendez-vous du mouvement est le samedi suivant ; les chiffres de chaque journée sont mis à jour au Baromètre.", "sources": []}}

# ---------------- chapitre avec IA ----------------
CONSIGNE = """Tu écris un chapitre du « livre du mouvement » (gilets jaunes 2026, mobilisation lycéenne et contre la vie chère) pour le jour indiqué.
RÈGLES STRICTES :
- Utilise UNIQUEMENT les éléments fournis (titres, résumés, chiffres). N'invente rien : ni chiffre, ni citation, ni nom, ni lieu.
- Chaque chiffre est attribué (« selon le ministère de l'Intérieur », « d'après la CGT »…). Quand deux camps donnent des chiffres différents, donne les deux côte à côte, sans dire lequel est vrai.
- Un chiffre marqué non recoupé est présenté comme tel (« non recoupé à ce stade »). N'affirme pas qu'un média ou un camp ment ; dis seulement ce que chacun annonce.
- Cite chaque information avec les numéros de sources [n] fournis. N'invente aucun numéro.
- Ton sobre de chroniqueur, phrases claires, pas de slogan, pas d'insulte.
Réponds par UN SEUL objet JSON, sans texte autour, de cette forme :
{"titre": "...(80 caractères max)", "chapeau": "2 phrases", "chiffres": [{"valeur": "410 000", "libelle": "manifestants en France", "detail": "selon le ministère de l'Intérieur ; 800 000 selon la CGT", "sources": [3]}],
 "points": [{"texte": "...", "sources": [3, 5]}], "recit": [{"texte": "paragraphe de 3 à 6 phrases", "sources": [1, 2]}], "a_suivre": {"texte": "...", "sources": []}}
Donne 3 à 6 chiffres, 5 à 8 points, 3 à 5 paragraphes de récit."""

def appeler_ia(jour, lignes, fl):
    cle = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not cle: raise RuntimeError("pas de cle API")
    mat = {"jour": jour_long(jour), "acte": acte_du(jour), "articles": [{"n": l["n"], "titre": l["titre"], "resume": l["resume"], "medias": l["medias"], "nb_medias": l["nb_medias"]} for l in lignes[:40]],
           "chiffres": [{"metrique": f["metrique"], "valeur": f["valeur"], "selon": f["qui"], "recoupe": f["recoupe"], "phrase": f["phrase"], "sources": f["sources"]} for f in fl]}
    corps = json.dumps({"model": MODELE, "max_tokens": 4500, "system": CONSIGNE, "messages": [{"role": "user", "content": json.dumps(mat, ensure_ascii=False)}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=corps, headers={"x-api-key": cle, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        texte = json.loads(r.read())["content"][0]["text"].strip()
    texte = re.sub(r"^```(?:json)?|```$", "", texte.strip(), flags=re.M).strip()
    return json.loads(texte[texte.index("{"):texte.rindex("}") + 1])

def chiffres_de(t):
    out = set()
    for m in re.finditer(r"\d[\d  .,]*\d|\d", t):
        s = re.sub(r"\D", "", m.group(0))
        if s and int(s) > 31 and s != "2026": out.add(s)
    return out

def verifier(ch, corpus, maxn):
    """Retourne la liste des problemes : chiffre absent des elements, source inexistante."""
    ok = chiffres_de(corpus)
    corpus_n = re.sub(r"\D", "", corpus)
    pbs = []
    textes = [ch.get("titre", ""), ch.get("chapeau", "")] + [p.get("texte", "") for p in ch.get("points", [])] + [p.get("texte", "") for p in ch.get("recit", [])] + [(ch.get("a_suivre") or {}).get("texte", "")]
    textes += [c.get("valeur", "") + " " + c.get("detail", "") for c in ch.get("chiffres", [])]
    for t in textes:
        for n in chiffres_de(t):
            if n not in ok and n not in corpus_n: pbs.append("chiffre " + n)
    blocs = ch.get("points", []) + ch.get("recit", []) + ch.get("chiffres", []) + [ch.get("a_suivre") or {}]
    for b in blocs:
        b["sources"] = [n for n in b.get("sources", []) if isinstance(n, int) and 1 <= n <= maxn]
    return pbs

def generer(actus, faits, jour, data):
    lignes, fl, sources = elements(actus, faits, jour)
    if not lignes and not fl:
        print("Livre : aucun element pour", jour); return None
    corpus = " ".join([l["titre"] + " " + l["resume"] for l in lignes] + [f["phrase"] + " " + str(f["valeur"]) for f in fl])
    essais = 0
    chemin = data / "chronique" / (jour + ".json")
    if chemin.exists():
        try: essais = json.loads(chemin.read_text(encoding="utf-8")).get("essais_ia", 0)
        except Exception: pass
    ch, auteur = None, "automatique"
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        essais += 1
        for tentative in range(2):
            try:
                brut = appeler_ia(jour, lignes, fl)
                pbs = verifier(brut, corpus, len(sources))
                if pbs:
                    print("Livre %s : IA refusee (%s)" % (jour, ", ".join(sorted(set(pbs))[:6]))); continue
                ch, auteur = brut, "ia"; break
            except Exception as e:
                print("Livre %s : IA indisponible : %s" % (jour, str(e)[:160])); break
    if ch is None:
        ch = chapitre_modele(jour, lignes, fl, sources)
    ch.update({"date": jour, "numero": numero(jour), "jour_long": jour_long(jour), "acte": acte_du(jour), "auteur": auteur, "essais_ia": essais,
               "sources": sources, "genere": dt.datetime.now(dt.timezone.utc).isoformat()})
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(ch, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Livre : chapitre %d (%s) ecrit, auteur : %s" % (ch["numero"], jour, auteur))
    return ch

def maj_index(data):
    liste = []
    for p in sorted((data / "chronique").glob("20*.json")):
        try: c = json.loads(p.read_text(encoding="utf-8"))
        except Exception: continue
        liste.append({"date": c["date"], "numero": c["numero"], "titre": c["titre"], "chapeau": c.get("chapeau", ""), "auteur": c.get("auteur", "")})
    (data / "chronique").mkdir(parents=True, exist_ok=True)
    (data / "chronique" / "index.json").write_text(json.dumps({"chapitres": liste}, ensure_ascii=False, indent=1), encoding="utf-8")
