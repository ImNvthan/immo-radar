import json

import pandas as pd

from immo import page


def test_page_vide_ne_plante_pas(tmp_path):
    html = page.generer_page(tmp_path, tmp_path / "docs" / "index.html")
    assert "<title>Radar immobilier</title>" in html
    assert (tmp_path / "docs" / "index.html").exists()


def test_page_complete(tmp_path):
    (tmp_path / "meta.json").write_text('{"zone": "Département 49", "derniere_vente": "2025-12-31", "budget_max": 0, "surface_min": 0}', encoding="utf-8")
    pd.DataFrame([{"type_local": "Maison", "prix_m2": 2000, "n_ventes": 50, "evo12": 0.05, "evo6": 0.01, "lecture": "Prix en hausse"}]).to_csv(tmp_path / "tendance.csv", index=False)
    pd.DataFrame([{"type_local": "Maison", "mois": m, "indice": 1 + (m - 6) / 100} for m in range(1, 13)]).to_csv(tmp_path / "saisonnalite.csv", index=False)
    pd.DataFrame([{"type_local": "Maison", "mois": f"2025-{m:02d}", "prix_m2_median": 2000 + m * 10, "n_ventes": 9} for m in range(1, 13)]).to_csv(tmp_path / "tendance_mensuelle.csv", index=False)
    pd.DataFrame([{"nom_commune": "Ville <b>", "type_local": "Maison", "prix_m2_median": 2000, "n_ventes": 30, "evolution_12m": 0.04,
                   "loyer_m2": 9.5, "loyer_origine": "ANIL 2025", "rendement_brut": 0.057, "fiable": True, "dans_budget": True}]).to_csv(tmp_path / "marche_communes.csv", index=False)
    pd.DataFrame([{"url": "https://www.pap.fr/annonce/x", "type_local": "Maison", "commune": "Ville", "surface": 90, "prix": 150000, "ecart": -0.2,
                   "rendement_net": 0.06, "opportunite": True},
                  {"url": "javascript:alert(1)", "type_local": "Maison", "commune": "Autre", "surface": 90, "prix": 150000, "ecart": -0.2,
                   "rendement_net": 0.06, "opportunite": True}]).to_csv(tmp_path / "opportunites.csv", index=False)
    html = page.generer_page(tmp_path, tmp_path / "index.html")
    assert "Département 49" in html and "<polyline" in html and "<polygon class='forme'" in html
    assert "Ville &lt;b&gt;" in html  # échappement
    assert "href='https://www.pap.fr/annonce/x'" in html
    assert "javascript:" not in html  # liens non http refusés
    assert "viewport" in html
    assert "<script src" not in html and "<link" not in html  # aucune ressource externe
    assert "@import" not in html and "url(http" not in html


def test_page_donnees_embarquees_et_interactivite(tmp_path):
    pd.DataFrame([{"nom_commune": "Ville </script>", "type_local": "Maison", "prix_m2_median": 2000, "n_ventes": 30, "evolution_12m": None,
                   "loyer_m2": 9.5, "loyer_origine": "ANIL 2025", "rendement_brut": 0.057, "fiable": True, "dans_budget": True,
                   "code_commune": "72001"}]).to_csv(tmp_path / "marche_communes.csv", index=False)
    html = page.generer_page(tmp_path, tmp_path / "index.html")
    brut = html.split('id="donnees">')[1].split("</script>")[0]
    d = json.loads(brut)  # JSON valide malgré le nom piégé
    assert d["communes"][0]["k"] == "72001" and d["communes"][0]["e"] is None
    assert d["seuils"]["decote_min"] == 0.08
    for ident in ("c-budget", "c-surface", "c-q", "form-annonce", "a-commune", "liste-communes", "mes-annonces"):
        assert f'id="{ident}"' in html or f"id='{ident}'" in html
