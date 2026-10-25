"""Extraction des chiffres (barometre) et classement des articles. Aucune IA : regles ecrites ici.
Tout est volontairement lisible : pour changer une regle, modifier les listes ci-dessous."""
import re, unicodedata

MOIS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
        "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12}
MOTS_NOMBRES = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
                "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15,
                "seize": 16, "vingt": 20, "trente": 30}

# ---------- themes (ordre = priorite) ----------
THEMES = [
    ("krach", r"krach|obligataire|taux d.emprunt|taux français|spread|OAT\b|taux à 10 ans|notation de la France|agence de notation"),
    ("repression", r"\bLBD\b|\bCRS\b|grenade|violences? policière|répression|gaz lacrymo|lacrymog|interpell|garde[s]? à vue|gendarmes? mobiles?|maintien de l.ordre|policiers? blessé|forces de l.ordre|casseurs|écroué|détention provisoire"),
    ("mouvement", r"gilets? jaunes?|blocus|lycéen|mobilisation|manifest|\bRIC\b|référendum d.initiative|rond-point|blocage|intersyndicale|convergence des (luttes|colères)"),
    ("pandemie", r"épidémie|pandémie|covid|grippe|virus|bronchiolite|vaccin"),
    ("colere", r"vie chère|pouvoir d.achat|carburant|essence|gazole|salaire|inflation|\bgrève|colère|précarité|loyers?|factures? d.énergie|prix (des|de l)"),
    ("argent", r"\bdette\b|déficit|budget|retraites?|impôts?|abattement fiscal|économies|finances publiques|milliards? d.euros|fiscal"),
    ("politique", r"présidentielle|2027|Macron|Lecornu|Assemblée nationale|Sénat|candidat|Mélenchon|Le Pen|Bardella|Retailleau|Attal|gouvernement|député|premier ministre|motion de censure"),
]
THEMES_NOMS = {"mouvement": "Le mouvement", "colere": "Colère sociale", "repression": "Répression", "argent": "Argent & crise",
               "krach": "Krach obligataire", "politique": "Politique & 2027", "pandemie": "Pandémie"}
MOTS_CLES = [
    ("gilets-jaunes", r"gilets? jaunes?"), ("blocus", r"blocus|lycée[s]? bloqué|blocage des lycées"),
    ("greve", r"\bgrève"), ("manifestation", r"manifest"), ("violences-policieres", r"violences? policière|\bLBD\b|grenade"),
    ("crs", r"\bCRS\b"), ("pouvoir-achat", r"pouvoir d.achat|vie chère"), ("carburant", r"carburant|essence|gazole"),
    ("dette", r"\bdette\b"), ("taux", r"taux d.intérêt|taux d.emprunt|taux français|\bOAT\b"),
    ("presidentielle", r"présidentielle|2027"), ("macron", r"Macron"), ("epidemie", r"épidémie|pandémie|grippe|covid"),
    ("virus", r"virus"),
]
# un article est garde s'il touche au mouvement ou a son contexte
PERTINENT = re.compile(r"gilets? jaunes?|blocus|lycéen|mobilisation|manifest|\bRIC\b|référendum d.initiative|vie chère|pouvoir d.achat|casseurs|\bLBD\b|violences? policière|intersyndicale|krach|taux d.emprunt|\bOAT\b|dette (publique|de la France)|présidentielle 2027|Lecornu|Nuñez|colère (sociale|des)|mobilisation lycéenne", re.I)

def sans_accents(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")

def theme_de(texte):
    for cle, motif in THEMES:
        if re.search(motif, texte, re.I):
            return cle
    return "mouvement"

def mots_cles_de(texte):
    return [cle for cle, motif in MOTS_CLES if re.search(motif, texte, re.I)]

# ---------- chiffres ----------
RE_NOMBRE = re.compile(r"(?<![\w.,])(\d{1,3}(?:[   .]\d{3})+|\d+)(?:,(\d+))?(?:\s?(millions?|milliards?|milliers?))?(?!\w)", re.I)
RE_MOT_NOMBRE = re.compile(r"^(" + "|".join(MOTS_NOMBRES) + r")\b", re.I)

def lire_nombre(m):
    brut = re.sub(r"[   .]", "", m.group(1))
    v = float(brut + ("." + m.group(2) if m.group(2) else ""))
    u = (m.group(3) or "").lower()
    if u.startswith("millio"): v *= 1_000_000
    elif u.startswith("milliard"): v *= 1_000_000_000
    elif u.startswith("millier"): v *= 1000
    return int(round(v))

AUTORITES = re.compile(r"minist[eè]re|ministre|Nuñez|Lecornu|Matignon|préfectur|préfet|police|gendarmerie|autorités|gouvernement|exécutif|Chancellerie|procureur|parquet|rectorat|académie|Intérieur|Justice|Éducation nationale|Elysée|Élysée|Bercy|cour d.appel|tribunal|région|métropole|mairie", re.I)
ORGANISATEURS = re.compile(r"organisateurs?|intersyndicale|CGT|FSU|FO\b|CFDT|Solidaires|syndicats?|collectifs?|gilets? jaunes|UNL|FIDL|SGL|lycéens|organisations? (lycéennes|étudiantes)|Confédération paysanne|Coordination rurale|FNSEA|LFI|France insoumise", re.I)
SONDEURS = re.compile(r"sondage|Ifop|Elabe|Odoxa|Harris|Ipsos|CSA|Toluna|Cluster17|Verian|Opinionway|YouGov|Viavoice", re.I)
FUTUR = re.compile(r"s.attendre|attend(?:u|ent|re)|prévu|prévoi|pourrait|devrait|appelle|appel à|appelé|annoncé pour|pour le \d|à venir|attendus?|espère|objectif", re.I)

def trouver_date(phrase, annee=2026):
    """Premiere date citee (hors 'depuis le ...')."""
    for m in re.finditer(r"(?:(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+)?(1er|\d{1,2})\s+(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)(?:\s+(\d{4}))?", phrase, re.I):
        avant = phrase[max(0, m.start() - 12):m.start()].lower()
        if "depuis" in avant:
            continue
        j = 1 if m.group(2) == "1er" else int(m.group(2))
        mois = MOIS[m.group(3).lower()]
        an = int(m.group(4)) if m.group(4) else annee
        return "%04d-%02d-%02d" % (an, mois, j)
    return None

SUJETS = (r"(?:(?:le |la |les |l['’])?(?:organisateurs?|intersyndicale(?: [\wÀ-ÿ’' -]{0,25})?|CGT|FSU|syndicats?|préfecture(?: de [A-ZÀ-Ý][\wÀ-ÿ-]+)?|"
          r"ministère de l['’][A-Za-zÀ-ÿ]+|ministère de la [A-Za-zÀ-ÿ]+|ministre de l['’][A-Za-zÀ-ÿ]+|police|autorités|gouvernement|Chancellerie|parquet|Matignon|Sébastien Lecornu|Laurent Nuñez))")
VERBES = r"(?:revendiquent|annoncent|annonce|comptent|dénombrent|recensent|estiment|évoquent|font état|parlent|indiquent|indique|ont compté|ont dénombré|ont recensé|déclarent|affirment|a annoncé|ont annoncé|a indiqué|ont indiqué|a précisé)"

def trouver_qui(phrase):
    qui = None
    m = re.search(r"(?:selon|d.après)\s+(?:un sondage\s+|une étude\s+)?((?:le |la |les |l[’'])?[^,.;()«»]{3,70})", phrase, re.I)
    if m:
        qui = re.sub(r"\s+(le|ce|cette|hier|depuis|dans|pour|sur|publié|publiée|mardi|lundi|mercredi|jeudi|vendredi|samedi|dimanche|à|au)\b.*$", "", m.group(1).strip(), flags=re.I).strip(" ,;:")
    if not qui:
        m = re.search("(" + SUJETS[3:-1] + r")\s+" + VERBES, phrase, re.I) or re.search(VERBES + r"\s+(?:le |la |les |l['’])?(" + SUJETS[3:-1] + ")", phrase, re.I)
        if m:
            qui = m.group(1).strip()
    if not qui or len(qui) < 3:
        return None, None
    cote = "autres"
    if AUTORITES.search(qui): cote = "autorites"
    elif ORGANISATEURS.search(qui): cote = "organisateurs"
    elif SONDEURS.search(phrase): cote = "sondeurs"
    return qui, cote

def decouper_phrases(texte):
    texte = re.sub(r"\s+", " ", texte).strip()
    return [p.strip() for p in re.split(r"(?<=[.!?…])\s+(?=[A-ZÀ-ÖØ-Ý«\"“0-9])", texte) if len(p.strip()) > 20]

PATRONS = [
    ("manifestants", re.compile(r"^\s*(?:de\s+)?(?:manifestants?|personnes? (?:ont )?(?:défilé|manifesté)|participants)", re.I)),
    ("blesses_education", re.compile(r"^\s*(?:personnels? de l.éducation nationale|chefs? d.établissement|enseignants?|professeurs?|personnels? (?:éducatifs?|enseignants?)|membres du personnel)[^.;]{0,40}?bless", re.I)),
    ("blesses_eleves", re.compile(r"^\s*(?:élèves?|lycéens?|collégiens?|jeunes|mineurs?|étudiants?)[^.;]{0,25}?bless", re.I)),
    ("blesses_forces", re.compile(r"^\s*(?:policiers?|gendarmes?|membres des forces de l.ordre|forces de l.ordre|agents?|CRS|fonctionnaires de police)[^.;]{0,45}?bless", re.I)),
    ("gardes_a_vue", re.compile(r"^\s*(?:personnes?|individus?|jeunes|mineurs?|gardes? à vue|manifestants?|lycéens?)?[^.;]{0,30}?garde[s]? à vue", re.I)),
    ("detention", re.compile(r"^\s*(?:personnes?|individus?|jeunes|mineurs?|manifestants?)?[^.;]{0,30}?(?:détention provisoire|écrou|incarcér|prison ferme|mandat de dépôt|placés? en détention|condamnés? à de la prison)", re.I)),
    ("interpellations", re.compile(r"^\s*(?:personnes?|individus?|jeunes|mineurs?|manifestants?|lycéens?|élèves?)?[^.;]{0,30}?interpell", re.I)),
    ("etablissements", re.compile(r"^\s*(?:établissements?|lycées?|collèges?|écoles?)[^.;]{0,35}?(?:perturb|bloqu|fermé)", re.I)),
]
LIBELLES = {"manifestants": "Manifestants", "etablissements": "Établissements bloqués ou perturbés", "blesses_forces": "Policiers et gendarmes blessés",
            "blesses_eleves": "Élèves blessés", "blesses_education": "Personnels de l’Éducation blessés", "interpellations": "Interpellations",
            "gardes_a_vue": "Gardes à vue", "detention": "Détentions et écrous", "degats": "Dégâts", "sondage": "Sondages"}

def extraire_faits(phrase, date_article):
    """Retourne la liste des faits chiffres trouves dans une phrase."""
    faits = []
    if FUTUR.search(phrase) and not re.search(r"selon", phrase, re.I):
        return faits
    qui, cote = trouver_qui(phrase)
    jour = trouver_date(phrase) or date_article
    cumul = bool(re.search(r"depuis (?:le )?(?:début|\d|le (?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)|l.ouverture|la rentrée)|au total|jusqu.ici|à ce jour|bilan (?:total|global)", phrase, re.I))
    # sondages : pourcentage + sondage/institut
    if SONDEURS.search(phrase):
        m = re.search(r"(\d{1,3}(?:,\d+)?)\s?%", phrase)
        if m and not FUTUR.search(phrase):
            faits.append({"metrique": "sondage", "valeur": float(m.group(1).replace(",", ".")), "unite": "%", "qui": qui or "sondage", "cote": "sondeurs",
                          "portee": "ponctuel", "jour": jour, "phrase": phrase})
            return faits
    # degats : euros + degats
    if re.search(r"dégâts|dégradations|dommages|coût(?:e|ent)? ", phrase, re.I):
        for m in RE_NOMBRE.finditer(phrase):
            apres = phrase[m.end():m.end() + 25]
            if re.match(r"\s*(?:d['’]\s?)?euros?|\s*€", apres, re.I):
                faits.append({"metrique": "degats", "valeur": lire_nombre(m), "unite": "€", "qui": qui, "cote": cote or "autres",
                              "portee": "cumul" if cumul else "ponctuel", "jour": jour, "phrase": phrase})
                return faits
    for m in RE_NOMBRE.finditer(phrase):
        apres = phrase[m.end():m.end() + 90]
        if re.match(r"\s*(?:%|euros?|€|ans?\b|h\b|heures?|kilom)", apres, re.I):
            continue
        for cle, motif in PATRONS:
            if motif.match(apres):
                # evite de compter deux fois l'age ("un lycéen de 16 ans")
                faits.append({"metrique": cle, "valeur": lire_nombre(m), "unite": "", "qui": qui, "cote": cote,
                              "portee": "cumul" if (cumul and cle not in ("manifestants", "etablissements")) else "jour", "jour": jour, "phrase": phrase})
                break
        else:
            continue
        break
    return faits
