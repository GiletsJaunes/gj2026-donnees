"""Rattrapage du barometre : relit la presse jour par jour depuis le debut du mouvement (10 septembre) jusqu'a aujourd'hui,
releve les chiffres (manifestants, blesses, interpellations, sondages, morts, eborgnes, mains arrachees...) et les ajoute a data/barometre.json.
Lance a la main depuis l'onglet Actions (« Rattrapage du barometre »). Sans risque : on peut le relancer, rien n'est duplique."""
import argparse, datetime as dt
from pathlib import Path
import veille as v

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--depuis", default=v.DEBUT_MOUVEMENT)
    ap.add_argument("--jusqua")
    ap.add_argument("--sortie")
    a = ap.parse_args()
    racine = v.ICI.parent
    data = Path(a.sortie) if a.sortie else racine / "data"
    v.charger_villes(racine)
    maintenant = dt.datetime.now(v.PARIS)
    fin = dt.date.fromisoformat(a.jusqua) if a.jusqua else maintenant.date()
    jour = dt.date.fromisoformat(a.depuis)
    config = v.lire_json(v.ICI / "feeds.json", {"flux": [], "google_actualites": []})
    masques = v.lire_json(data / "masques.json", {"faits": [], "articles": []})
    faits = v.nettoyer_faits(v.lire_json(data / "barometre.json", {"faits": []})["faits"])
    total_articles = total_nouveaux = n = 0
    while jour <= fin:
        try:
            arts = v.collecter_jour(config, jour.isoformat(), maintenant)
        except Exception as e:
            print("Jour", jour, ":", e); arts = []
        faits, nb = v.mettre_a_jour_faits(faits, arts, maintenant)
        faits = [f for f in faits if f["id"] not in masques.get("faits", [])]
        total_articles += len(arts); total_nouveaux += nb; n += 1
        print("%s : %d articles, %d nouveaux chiffres" % (jour, len(arts), nb))
        if n % 5 == 0:   # on enregistre au fur et a mesure
            v.ecrire_json(data / "barometre.json", {"maj": maintenant.isoformat(), "faits": faits})
        jour += dt.timedelta(days=1)
    faits = v.nettoyer_faits(faits)
    v.ecrire_json(data / "barometre.json", {"maj": maintenant.isoformat(), "faits": faits})
    print("Rattrapage termine : %d jours, %d articles lus, %d nouveaux chiffres, %d chiffres au total." % (n, total_articles, total_nouveaux, len(faits)))

if __name__ == "__main__":
    main()