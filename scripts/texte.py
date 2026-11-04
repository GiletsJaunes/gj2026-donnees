#!/usr/bin/env python3
"""Lecture du TEXTE COMPLET des articles (le flux Google Actualites ne donne que le titre).

Un article « Mobilisation du 5 novembre : les rassemblements ville par ville » a ses lieux et horaires dans le texte, pas dans le titre.
Le robot ouvre donc les articles utiles, en extrait les paragraphes, et les garde en cache (data/cache/textes.json, 3 jours) pour ne pas les relire.
Aucun contournement de paywall : si la page est payante, bloquee ou illisible, on garde juste le titre."""
import datetime as dt, html, json, re, urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (compatible; GJ2026-veille/1.0)"
UTILE = re.compile(r"mobilis|manifest|rassembl|bloc(?:us|age)|appel|gr[èe]ve|cort[èe]ge|intersyndicale|gilets? jaunes|vie ch[èe]re|acte (?:iii|iv|v|3|4|5)", re.I)

def decoder(url):
    """Les liens Google Actualites sont des redirections : on retrouve l'adresse reelle de l'article (paquet googlenewsdecoder, installe par le workflow)."""
    if "news.google.com" not in url:
        return url
    try:
        from googlenewsdecoder import gnewsdecoder
        r = gnewsdecoder(url, interval=0)
        if r.get("status") and r.get("decoded_url"):
            return r["decoded_url"]
    except Exception as e:
        print("Decodage Google Actualites impossible :", str(e)[:80])
    return None

def extraire_texte(page):
    page = re.sub(r"(?is)<(script|style|noscript|nav|footer|aside|form|svg|iframe)\b.*?</\1>", " ", page)
    blocs = re.findall(r"(?is)<(?:p|h2|h3|li)\b[^>]*>(.*?)</(?:p|h2|h3|li)>", page)
    out, vus = [], set()
    for b in blocs:
        t = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b))).strip()
        if len(t) < 25 or t in vus or re.search(r"(?i)abonn|cookie|newsletter|publicit|inscri|connectez|partager|lire aussi|à lire", t):
            continue
        vus.add(t); out.append(t)
    return "\n".join(out)[:4500]

def lire(url):
    reel = decoder(url)
    if not reel:
        return ""
    req = urllib.request.Request(reel, headers={"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9", "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=20) as r:
        if "html" not in (r.headers.get("Content-Type") or ""):
            return ""
        page = r.read(1_500_000).decode("utf-8", "ignore")
    return extraire_texte(page)

def charger_cache(data):
    try:
        return json.loads((Path(data) / "cache" / "textes.json").read_text(encoding="utf-8"))
    except Exception:
        return {}

def sauver_cache(data, cache, maintenant):
    limite = (maintenant - dt.timedelta(days=3)).isoformat()
    cache = {u: v for u, v in cache.items() if v.get("d", "") >= limite}
    p = Path(data) / "cache" / "textes.json"; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

def enrichir(articles, data, maintenant, max_lectures=40, lire_fn=lire):
    """Retourne une copie des articles utiles avec leur texte complet dans 'resume' et plein_texte=True. Ne modifie pas la liste d'origine."""
    cache = charger_cache(data)
    sortie, lus = [], 0
    for a in sorted(articles, key=lambda x: x.get("date", ""), reverse=True):
        if not UTILE.search(a.get("titre", "")):
            sortie.append(a); continue
        u = a["url"]; c = cache.get(u)
        if c is None and lus < max_lectures:
            lus += 1
            try:
                t = lire_fn(u)
            except Exception as e:
                t = ""
                print("Lecture impossible :", u[:70], str(e)[:60])
            c = cache[u] = {"t": t, "d": maintenant.isoformat()}
        if c and len(c.get("t", "")) > 200:
            sortie.append(dict(a, resume=(a.get("resume", "") + "\n" + c["t"]).strip(), plein_texte=True))
        else:
            sortie.append(a)
    sauver_cache(data, cache, maintenant)
    print("Textes complets : %d articles lus, %d disponibles" % (lus, sum(1 for a in sortie if a.get("plein_texte"))))
    return sortie