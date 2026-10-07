import pandas as pd
import pytest
import yaml

from immo import analyse


def ids(df):
    return set(df["id_mutation"])


# --- nettoyage ---------------------------------------------------------------

def test_nettoyage_exclut_les_cas_non_comparables(ventes):
    presents = ids(ventes)
    for exclu in ("SPECIAL-MULTI", "SPECIAL-ECHANGE", "SPECIAL-COMMERCE", "SPECIAL-TERRAIN",
                  "SPECIAL-BAS", "SPECIAL-HAUT", "SPECIAL-PETIT", "SPECIAL-VIDE"):
        assert exclu not in presents, exclu


def test_nettoyage_conserve_maison_avec_dependance(ventes):
    assert "SPECIAL-DEP" in ids(ventes)


def test_maison_sur_deux_parcelles_comptee_une_fois(ventes):
    assert (ventes["id_mutation"] == "SPECIAL-PARCELLES").sum() == 1


def test_une_seule_ligne_par_vente(ventes):
    assert ventes["id_mutation"].is_unique


def test_nettoyage_calcule_prix_m2(ventes):
    r = ventes[ventes["id_mutation"] == "SPECIAL-DEP"].iloc[0]
    assert r["prix_m2"] == pytest.approx(2100)
    assert r["commune_norm"] == "ville a"


def test_nettoyage_sans_colonnes_facultatives(dvf_brut):
    minimal = dvf_brut.drop(columns=["surface_terrain", "adresse_numero", "nombre_pieces_principales"])
    assert not analyse.clean(minimal).empty


# --- statistiques par commune ------------------------------------------------

def test_mediane_par_commune_et_type(stats):
    a = stats[(stats["code_commune"] == "49001") & (stats["type_local"] == "Appartement")].iloc[0]
    assert a["prix_m2_median"] == pytest.approx(3300, rel=0.02)
    assert a["evolution_12m"] == pytest.approx(0.10, abs=0.03)
    b = stats[(stats["code_commune"] == "49002") & (stats["type_local"] == "Appartement")].iloc[0]
    assert b["evolution_12m"] == pytest.approx(1400 / 1600 - 1, abs=0.03)
    assert a["fiable"] and b["fiable"]


def test_echantillon_insuffisant_non_fiable(ventes, ref, loyers):
    s = analyse.market_stats(ventes, ref, 500, loyers)
    assert not s["fiable"].any()
    assert s["evolution_12m"].isna().all()


def test_rendement_brut(stats):
    r = stats.iloc[0]
    assert r["rendement_brut"] == pytest.approx(r["loyer_m2"] * 12 / r["prix_m2_median"])
    assert (stats["loyer_origine"] == "défaut config.yml").all()


def test_budget_et_surface_filtrent_les_communes(ventes, ref, loyers):
    s = analyse.market_stats(ventes, ref, 5, loyers, budget_max=150_000, surface_min=60)
    ok = s[s["dans_budget"]]
    hors = s[~s["dans_budget"]]
    # un appartement de 60 m² à Ville-A (3 300 €/m²) dépasse 150 000 €, une maison à 2 100 €/m² non
    assert list(hors["code_commune"]) == ["49001"] and list(hors["type_local"]) == ["Appartement"]
    assert len(ok) == 3 and (ok["prix_bien_type"] <= 150_000).all()
    sans = analyse.market_stats(ventes, ref, 5, loyers)
    assert sans["dans_budget"].all()


# --- tendance et saisonnalité -------------------------------------------------

def serie_synthetique(prix_par_an, saison=None, par_mois=8):
    rows = []
    for an, base in prix_par_an.items():
        for m in range(1, 13):
            for k in range(par_mois):
                rows.append({"type_local": "Maison", "date": pd.Timestamp(an, m, 1 + k),
                             "prix_m2": base * (saison or {}).get(m, 1.0) * (0.98 + 0.005 * k)})
    return pd.DataFrame(rows)


def test_tendance_hausse():
    df = serie_synthetique({2023: 2000, 2024: 2100, 2025: 2300})
    t = analyse.timing(df, df["date"].max(), 5)["Maison"]
    assert t["evo12"] == pytest.approx(2300 / 2100 - 1, abs=0.02)
    assert "hausse" in analyse.lecture(t["evo12"], t["evo6"])


def test_lecture_des_tendances():
    assert "recul" in analyse.lecture(-0.05, -0.03)
    assert "stables" in analyse.lecture(0.005, 0.0)
    assert "insuffisantes" in analyse.lecture(None, None)


def test_saisonnalite_detecte_mois_chers_et_bon_marche():
    df = serie_synthetique({2023: 2000, 2024: 2000, 2025: 2000}, saison={7: 1.08, 12: 0.92})
    t = analyse.timing(df, df["date"].max(), 5)["Maison"]
    assert t["mois_hauts"][0] == 7
    assert t["mois_bas"][0] == 12
    assert t["saison"][7] > 1.03 and t["saison"][12] < 0.97


def test_timing_ignore_types_sans_assez_de_ventes():
    df = serie_synthetique({2025: 2000}, par_mois=1)
    assert analyse.timing(df, df["date"].max(), 15) == {}


def test_serie_mensuelle(ventes, ref):
    s = analyse.serie_mensuelle(ventes, ref, 5, nb_mois=12)
    assert s["mois"].nunique() <= 13
    assert set(s["type_local"]) == {"Appartement", "Maison"}


# --- scoring des annonces ----------------------------------------------------

def annonces_csv(tmp_path, lignes):
    p = tmp_path / "annonces.csv"
    p.write_text("url,type_local,commune,surface,prix,titre\n" + "\n".join(lignes) + "\n", encoding="utf-8")
    return p


def test_annonce_opportunite(tmp_path, stats, cfg, loyers):
    # 60 m² à 120 000 € = 2000 €/m² (1900 après négociation) contre 3300 €/m² : très forte décote
    p = annonces_csv(tmp_path, ["https://x/1,Appartement,Ville-A,60,120000,bonne affaire"])
    r = analyse.score_annonces(p, stats, cfg, loyers).iloc[0]
    assert r["opportunite"] and r["ecart"] < -0.3
    assert r["loyer_origine"] == "défaut config.yml"
    assert r["rendement_net"] == pytest.approx(12 * 60 * 12 * 0.75 / 120000, abs=0.001)


def test_annonce_au_prix_du_marche_ou_sans_reference(tmp_path, stats, cfg, loyers):
    p = annonces_csv(tmp_path, [
        "https://x/2,Appartement,Ville-A,60,198000,au prix",
        "https://x/3,Appartement,Inconnue,60,100000,commune inconnue",
        "https://x/4,Appartement,Ville-A,0,100000,surface nulle",
    ])
    s = analyse.score_annonces(p, stats, cfg, loyers).set_index("url")
    assert not s.loc["https://x/2", "opportunite"]
    assert "sans référence" in s.loc["https://x/3", "note"]
    assert not s.loc["https://x/4", "opportunite"]


def test_annonce_hors_budget_ou_trop_petite(tmp_path, stats, loyers):
    cfg = analyse.normaliser_config({"min_ventes": 5, "budget_max": 100_000, "surface_min": 50})
    p = annonces_csv(tmp_path, [
        "https://x/5,Appartement,Ville-A,60,120000,trop cher",
        "https://x/6,Appartement,Ville-A,40,80000,trop petit",
    ])
    s = analyse.score_annonces(p, stats, cfg, loyers).set_index("url")
    assert s.loc["https://x/5", "note"] == "hors budget" and not s.loc["https://x/5", "opportunite"]
    assert "surface" in s.loc["https://x/6", "note"] and not s.loc["https://x/6", "opportunite"]


def test_annonces_absentes_ou_vides(tmp_path, stats, cfg, loyers):
    assert analyse.score_annonces(tmp_path / "nexistepas.csv", stats, cfg, loyers).empty
    p = annonces_csv(tmp_path, [])
    assert analyse.score_annonces(p, stats, cfg, loyers).empty


def test_nouvelles_opportunites(tmp_path, stats, cfg, loyers):
    p = annonces_csv(tmp_path, [
        "https://x/1,Appartement,Ville-A,60,120000,a",
        "https://x/7,Appartement,Ville-A,70,130000,b",
    ])
    scored = analyse.score_annonces(p, stats, cfg, loyers)
    assert set(analyse.nouvelles_opportunites(scored, set())["url"]) == {"https://x/1", "https://x/7"}
    assert set(analyse.nouvelles_opportunites(scored, {"https://x/1"})["url"]) == {"https://x/7"}
    assert analyse.nouvelles_opportunites(scored.iloc[0:0], set()).empty
    assert "https://x/7" in analyse.message_telegram(scored)


def test_urls_precedentes(tmp_path, stats, cfg, loyers):
    p = annonces_csv(tmp_path, ["https://x/1,Appartement,Ville-A,60,120000,a"])
    out = tmp_path / "opp.csv"
    analyse.score_annonces(p, stats, cfg, loyers).to_csv(out, index=False)
    assert analyse.urls_precedentes(out) == {"https://x/1"}
    assert analyse.urls_precedentes(tmp_path / "absent.csv") == set()


# --- loyers et configuration -------------------------------------------------

def test_priorite_des_loyers():
    officiel = {("49001", "Appartement"): (10.0, "ANIL 2025")}
    L = analyse.Loyers({"Appartement": 12.0, "Maison": 9.0}, {"Ville-B": 15, "49001": {"Maison": 11}}, officiel, 0.9)
    assert L.resoudre("49002", "ville b", "Appartement") == (15.0, "config.yml")
    assert L.resoudre("49001", "ville a", "Maison") == (11.0, "config.yml")
    assert L.resoudre("49001", "ville a", "Appartement") == (9.0, "ANIL 2025")
    assert L.resoudre("49003", "autre", "Maison") == (9.0, "défaut config.yml")


def test_config_ancien_format():
    cfg = analyse.normaliser_config(yaml.safe_load('zone:\n  departement: "49"\n  nb_annees: 2\n'))
    assert cfg["zone"]["departements"] == ["49"]
    assert cfg["zone"]["nb_annees"] == 2
    assert cfg["annonces"]["decote_min"] == 0.08  # valeurs par défaut conservées


def test_config_plusieurs_departements_et_communes():
    cfg = analyse.normaliser_config({"zone": {"departements": [49, "44", "2a"]}})
    assert cfg["zone"]["departements"] == ["2A", "44", "49"]
    cfg = analyse.normaliser_config({"zone": {"communes": ["49007", "97411"]}})
    assert cfg["zone"]["departements"] == ["49", "974"]


def test_config_sans_zone_invalide():
    with pytest.raises(ValueError):
        analyse.normaliser_config({"zone": {"departements": [], "departement": ""}})


def test_filtrer_zone(ventes):
    assert set(analyse.filtrer_zone(ventes, ["49002"])["code_commune"]) == {"49002"}
    assert set(analyse.filtrer_zone(ventes, ["ville-a"])["code_commune"]) == {"49001"}
    assert len(analyse.filtrer_zone(ventes, [])) == len(ventes)


# --- chargement et de bout en bout ------------------------------------------

def test_load_dvf_local_prend_les_annees_disponibles(tmp_path, dvf_brut):
    dvf_brut.to_csv(tmp_path / "2025.csv", index=False)
    dvf_brut.to_csv(tmp_path / "2024_49.csv", index=False)
    cfg = analyse.normaliser_config({"zone": {"departements": ["49"], "nb_annees": 2}})
    df = analyse.load_dvf(cfg, tmp_path, annee_courante=2026)
    assert len(df) == 2 * len(dvf_brut)  # 2026 absent : on remonte à 2025 et 2024


def test_executer_de_bout_en_bout(tmp_path, monkeypatch, dvf_brut):
    local = tmp_path / "dvf"
    local.mkdir()
    for an in (2023, 2024, 2025):
        dvf_brut[dvf_brut["date_mutation"].str.startswith(str(an))].to_csv(local / f"{an}.csv", index=False)
    conf = tmp_path / "config.yml"
    conf.write_text("zone:\n  departement: '49'\nmin_ventes: 5\nloyers_communes:\n  ville-a: 14\n", encoding="utf-8")
    ann = tmp_path / "annonces.csv"
    ann.write_text("url,type_local,commune,surface,prix,titre\nhttps://x/1,Appartement,Ville-A,60,120000,a\n", encoding="utf-8")
    data = tmp_path / "data"
    monkeypatch.setattr(analyse, "DATA", data)
    monkeypatch.setattr(analyse, "CACHE", data / "cache")
    monkeypatch.setattr(analyse, "DOCS", tmp_path / "docs")
    envoyes = []
    monkeypatch.setattr(analyse, "envoyer_telegram", lambda t: envoyes.append(t) or True)

    class Args:
        config, annonces, local_dir = str(conf), str(ann), str(local)

    analyse.executer(Args)
    for f in ("rapport.md", "marche_communes.csv", "opportunites.csv", "tendance.csv", "saisonnalite.csv", "tendance_mensuelle.csv", "meta.json"):
        assert (data / f).stat().st_size > 0, f
    rapport = (data / "rapport.md").read_text(encoding="utf-8")
    assert "1 opportunité(s) sur 1" in rapport and "config.yml" in rapport
    assert "—" not in rapport  # pas de tiret cadratin
    assert (tmp_path / "docs" / "index.html").exists()
    assert len(envoyes) == 1  # première détection : alerte

    analyse.executer(Args)  # deuxième passage : plus de nouvelle opportunité
    assert len(envoyes) == 1
