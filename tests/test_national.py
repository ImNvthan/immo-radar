from immo import national


def test_page_departement_avec_donnees_locales(tmp_path, dvf_brut):
    local = tmp_path / "dvf"
    local.mkdir()
    for an in (2023, 2024, 2025):
        dvf_brut[dvf_brut["date_mutation"].str.startswith(str(an))].to_csv(local / f"{an}.csv", index=False)
    sortie = tmp_path / "d"
    ok = national.page_departement("49", {"min_ventes": 5}, {}, sortie, local_dir=local, annee_courante=2025)
    assert ok
    html = (sortie / "49" / "index.html").read_text(encoding="utf-8")
    assert "Maine-et-Loire (49)" in html
    assert "data-prefixe='../../'" in html and "id='r-dep'" in html
    assert "Ville-A" in html


def test_departement_sans_donnees_ignore(tmp_path):
    vide = tmp_path / "vide"
    vide.mkdir()
    assert not national.page_departement("57", {}, {}, tmp_path / "d", local_dir=vide, annee_courante=2025)
    assert not (tmp_path / "d" / "57").exists()
