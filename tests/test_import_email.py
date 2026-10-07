import csv
from email.message import EmailMessage

from immo import import_email as ie

HTML_ALERTE = """
<html><body>
<h1>3 nouvelles annonces pour votre recherche</h1>
<table>
<tr><td><a href="https://www.leboncoin.fr/ad/ventes_immobilieres/2812345678?utm=abc"><img src="x.jpg"></a>
<a href="https://www.leboncoin.fr/ad/ventes_immobilieres/2812345678?utm=abc">Appartement T3 lumineux</a>
<p>185&nbsp;000 &euro;</p><p>62 m²</p><p>Angers (49000)</p></td></tr>
<tr><td><a href="https://www.seloger.com/annonces/achat/maison/cholet-49/123456789.htm">Maison de ville avec jardin</a>
<p>249 000 €</p><p>110 m² - 49300 Cholet</p></td></tr>
<tr><td><a href="https://click.tracking.example/redirect?x=1">Se désabonner</a></td></tr>
<tr><td><a href="https://www.pap.fr/annonce/vente-maison-saumur-49-r1">Maison à Saumur</a> <p>Prix incomplet</p></td></tr>
</table></body></html>
"""


def message(sujet="Alerte", html=None, texte=None):
    m = EmailMessage()
    m["Subject"] = sujet
    m["From"] = "alertes@exemple.test"
    m.set_content(texte or "version texte")
    if html:
        m.add_alternative(html, subtype="html")
    return m


def test_extraction_depuis_email_html():
    res = {a["url"]: a for a in ie.annonces_depuis_message(message(html=HTML_ALERTE))}
    assert len(res) == 3  # le lien de désabonnement est ignoré, l'image et le titre ne font qu'une annonce
    lbc = res["https://www.leboncoin.fr/ad/ventes_immobilieres/2812345678"]
    assert (lbc["type_local"], lbc["commune"], lbc["surface"], lbc["prix"]) == ("Appartement", "Angers", 62.0, 185000.0)
    sl = res["https://www.seloger.com/annonces/achat/maison/cholet-49/123456789.htm"]
    assert (sl["type_local"], sl["commune"], sl["surface"], sl["prix"]) == ("Maison", "Cholet", 110.0, 249000.0)


def test_extraction_depuis_email_texte_brut():
    texte = (
        "Nouvelle annonce : Maison 4 pièces à Saumur\n95 m² - 189 000 €\n"
        "https://www.bienici.com/annonce/vente/saumur/maison/abc123?src=mail\n"
    )
    res = ie.annonces_depuis_message(message(texte=texte))
    assert len(res) == 1
    a = res[0]
    assert a["url"] == "https://www.bienici.com/annonce/vente/saumur/maison/abc123"
    assert (a["type_local"], a["commune"], a["surface"], a["prix"]) == ("Maison", "Saumur", 95.0, 189000.0)


def test_email_sans_annonce_ou_illisible_ne_plante_pas():
    assert ie.annonces_depuis_message(message(texte="Bonjour, rien ici")) == []
    assert ie.annonces_depuis_message(message(html="<html><a href='https://www.leboncoin.fr/ad/x/1'>")) != [None]
    assert ie.annonces_depuis_message(None) == []
    assert ie.annonces_depuis_message(message(html="<<<>>><a href=")) == []


def test_urls_non_annonces_refusees():
    assert ie.url_annonce("https://evil.example/leboncoin.fr/ad/1") == ""
    assert ie.url_annonce("javascript:alert(1)") == ""
    assert ie.url_annonce("https://www.leboncoin.fr/") == ""
    assert ie.url_annonce("https://www.leboncoin.fr/ad/ventes/12?utm=1#x") == "https://www.leboncoin.fr/ad/ventes/12"


def test_champs_formats_de_prix_et_surface():
    c = ie.extraire_champs("Studio 24,5 m² 1 250 000 € à Paris")
    assert c["surface"] == 24.5 and c["prix"] == 1250000.0
    assert ie.extraire_champs("Maison 120m2 250.000 euros")["prix"] == 250000.0


def test_fusion_sans_doublons_et_ignore_les_incompletes(tmp_path):
    path = tmp_path / "annonces.csv"
    path.write_text("url,type_local,commune,surface,prix,titre\nhttps://www.pap.fr/annonce/a,Maison,Saumur,90,150000,deja la\n", encoding="utf-8")
    trouvees = ie.annonces_depuis_message(message(html=HTML_ALERTE)) + [
        {"url": "https://www.pap.fr/annonce/a", "type_local": "Maison", "commune": "Saumur", "surface": 90, "prix": 150000, "titre": "doublon"},
    ]
    assert ie.fusionner(path, trouvees) == 2  # Saumur incomplète ignorée, doublon ignoré
    assert ie.fusionner(path, trouvees) == 0  # idempotent
    with path.open(encoding="utf-8", newline="") as f:
        lignes = list(csv.DictReader(f))
    assert len(lignes) == 3 and lignes[0]["titre"] == "deja la"


def test_desactive_sans_secrets(monkeypatch, tmp_path):
    for v in ("IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD"):
        monkeypatch.delenv(v, raising=False)
    assert ie.main(tmp_path / "annonces.csv") == 0
    assert not (tmp_path / "annonces.csv").exists()


def test_erreur_imap_ne_plante_pas(monkeypatch, tmp_path):
    monkeypatch.setenv("IMAP_HOST", "imap.invalide.test")
    monkeypatch.setenv("IMAP_USER", "u")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")

    def echec(*a, **k):
        raise OSError("réseau")

    monkeypatch.setattr(ie, "recuperer_messages", echec)
    assert ie.main(tmp_path / "annonces.csv") == 0
