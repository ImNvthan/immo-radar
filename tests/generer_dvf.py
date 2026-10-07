"""Génère tests/data/dvf_synthetique.csv (jeu DVF fictif et déterministe, au format réel).

Ville-A (49001) : appartements en hausse (+10 % sur 12 mois), maisons stables.
Ville-B (49002) : appartements en baisse, maisons stables et bon marché.
Chaque mois compte 6 ventes par commune et type. Juillet est 5 % plus cher, décembre 5 % moins cher.
Des lignes spéciales (identifiants SPECIAL-*) couvrent les cas à exclure ou à conserver.
"""
import csv
from pathlib import Path

COLS = [
    "id_mutation", "date_mutation", "nature_mutation", "valeur_fonciere", "code_commune", "nom_commune",
    "type_local", "surface_reelle_bati", "nombre_pieces_principales", "adresse_numero", "adresse_nom_voie",
    "surface_terrain",
]
COMMUNES = {"49001": "Ville-A", "49002": "Ville-B"}
PRIX = {
    ("49001", "Appartement"): {2023: 2900, 2024: 3000, 2025: 3300},
    ("49001", "Maison"): {2023: 2100, 2024: 2100, 2025: 2100},
    ("49002", "Appartement"): {2023: 1700, 2024: 1600, 2025: 1400},
    ("49002", "Maison"): {2023: 1500, 2024: 1500, 2025: 1500},
}
VARIATION = [0.97, 0.98, 0.99, 1.01, 1.02, 1.03]
SAISON = {7: 1.05, 12: 0.95}


def ligne(id_, date, valeur, code, typ, surface, nature="Vente", pieces="3", adr="1", terrain=""):
    return {
        "id_mutation": id_, "date_mutation": date, "nature_mutation": nature, "valeur_fonciere": valeur,
        "code_commune": code, "nom_commune": COMMUNES[code], "type_local": typ, "surface_reelle_bati": surface,
        "nombre_pieces_principales": pieces, "adresse_numero": adr, "adresse_nom_voie": "RUE TEST",
        "surface_terrain": terrain,
    }


def generer():
    rows = []
    n = 0
    for (code, typ), par_an in PRIX.items():
        for an in (2023, 2024, 2025):
            for mois in range(1, 13):
                for k, var in enumerate(VARIATION):
                    n += 1
                    surface = (60 if typ == "Appartement" else 100) + 5 * k
                    pm2 = par_an[an] * SAISON.get(mois, 1.0) * var
                    rows.append(ligne(f"M{n}", f"{an}-{mois:02d}-{10 + k}", round(pm2 * surface), code, typ, surface))
    s = []
    # multi lots : deux appartements dans la même vente -> exclue
    s += [ligne("SPECIAL-MULTI", "2025-06-01", "300000", "49001", "Appartement", "50"),
          ligne("SPECIAL-MULTI", "2025-06-01", "300000", "49001", "Appartement", "55")]
    # maison + dépendance -> conservée (une seule ligne de logement)
    s += [ligne("SPECIAL-DEP", "2025-06-02", "210000", "49001", "Maison", "100"),
          ligne("SPECIAL-DEP", "2025-06-02", "210000", "49001", "Dépendance", "")]
    # maison sur deux parcelles (lignes identiques) -> comptée une fois
    s += [ligne("SPECIAL-PARCELLES", "2025-06-03", "205000", "49001", "Maison", "98"),
          ligne("SPECIAL-PARCELLES", "2025-06-03", "205000", "49001", "Maison", "98")]
    # nature autre que Vente, local commercial, grand terrain, prix aberrants, surface trop petite
    s += [ligne("SPECIAL-ECHANGE", "2025-06-04", "200000", "49001", "Maison", "100", nature="Echange"),
          ligne("SPECIAL-COMMERCE", "2025-06-05", "500000", "49001", "Appartement", "60"),
          ligne("SPECIAL-COMMERCE", "2025-06-05", "500000", "49001", "Local industriel. commercial ou assimilé", "80"),
          ligne("SPECIAL-TERRAIN", "2025-06-06", "260000", "49001", "Maison", "100", terrain="25000"),
          ligne("SPECIAL-BAS", "2025-06-07", "11000", "49001", "Maison", "100"),
          ligne("SPECIAL-HAUT", "2025-06-08", "9000000", "49001", "Appartement", "60"),
          ligne("SPECIAL-PETIT", "2025-06-09", "50000", "49001", "Appartement", "5"),
          ligne("SPECIAL-VIDE", "2025-06-10", "", "49001", "Appartement", "60")]
    return rows + s


if __name__ == "__main__":
    sortie = Path(__file__).parent / "data" / "dvf_synthetique.csv"
    with sortie.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(generer())
    print(sortie, len(generer()), "lignes")
