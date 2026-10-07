import os
import time

import pytest
import requests

from immo import loyers, reseau


class Reponse:
    def __init__(self, code=200, contenu=b"donnees"):
        self.status_code, self.content = code, contenu

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_telechargement_reessaie_puis_reussit(tmp_path, monkeypatch):
    appels, pauses = [], []

    def faux_get(url, timeout):
        appels.append(url)
        if len(appels) < 3:
            raise requests.ConnectionError("coupure")
        return Reponse()

    monkeypatch.setattr(reseau.requests, "get", faux_get)
    dest = reseau.telecharger("https://x/f.gz", tmp_path / "f.gz", pause=pauses.append)
    assert dest.read_bytes() == b"donnees"
    assert len(appels) == 3 and pauses == [2, 4]  # attente exponentielle


def test_telechargement_echoue_avec_message_clair(tmp_path, monkeypatch):
    monkeypatch.setattr(reseau.requests, "get", lambda url, timeout: Reponse(503))
    with pytest.raises(reseau.ErreurTelechargement, match="https://x/f.gz"):
        reseau.telecharger("https://x/f.gz", tmp_path / "f.gz", tentatives=2, pause=lambda s: None)


def test_telechargement_404_sans_nouvelle_tentative(tmp_path, monkeypatch):
    appels = []
    monkeypatch.setattr(reseau.requests, "get", lambda url, timeout: appels.append(1) or Reponse(404))
    with pytest.raises(reseau.Introuvable):
        reseau.telecharger("https://x/f.gz", tmp_path / "f.gz", pause=lambda s: None)
    assert len(appels) == 1


def test_cache_recent_reutilise_et_ancien_secours(tmp_path, monkeypatch):
    dest = tmp_path / "f.gz"
    dest.write_bytes(b"cache")
    monkeypatch.setattr(reseau.requests, "get", lambda url, timeout: pytest.fail("ne doit pas télécharger"))
    assert reseau.telecharger("https://x", dest, ttl_jours=7).read_bytes() == b"cache"
    vieux = time.time() - 30 * 86400
    os.utime(dest, (vieux, vieux))
    monkeypatch.setattr(reseau.requests, "get", lambda url, timeout: Reponse(500))
    assert reseau.telecharger("https://x", dest, ttl_jours=7, tentatives=1, pause=lambda s: None).read_bytes() == b"cache"


CSV_LOYERS = (
    '"id_zone";"INSEE_C";"LIBGEO";"EPCI";"DEP";"REG";"loypredm2";"lwr.IPm2";"upr.IPm2";"TYPPRED";"nbobs_com";"nbobs_mail";"R2_adj"\n'
    '"1";"49007";"Angers";"244900015";"49";"52";14,5;11,2;18,8;"commune";29741;29904;0,83\n'
    '"2";"49010";"Armaillé";"244900809";"49";"52";9,76;8,0;11,8;"maille";6;697;0,78\n'
    '"3";"5066";"Sans loyer";"1";"05";"93";;;;"maille";0;1;0,1\n'
)


def test_lecture_csv_loyers_latin1_virgule_decimale(tmp_path):
    p = tmp_path / "app.csv"
    p.write_bytes(CSV_LOYERS.encode("latin-1"))
    d = loyers.lire_csv_loyers(p, 2025)
    assert d["49007"] == (14.5, "ANIL 2025")
    assert d["49010"] == (9.76, "ANIL 2025 (maille)")
    assert "05066" not in d  # loyer manquant ignoré


def test_loyers_officiels_indisponibles_ne_plantent_pas(tmp_path, monkeypatch):
    def echec(*a, **k):
        raise requests.ConnectionError("hors ligne")

    monkeypatch.setattr(loyers.requests, "get", echec)
    assert loyers.charger_loyers_officiels(tmp_path, 2026) == {}


def test_loyers_officiels_chargement(tmp_path, monkeypatch):
    class Api:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"resources": [
                {"url": "https://static/x/pred-app-mef-dhup.csv"},
                {"url": "https://static/x/pred-mai-mef-dhup.csv"},
                {"url": "https://static/x/note.pdf"},
            ]}

    monkeypatch.setattr(loyers.requests, "get", lambda url, timeout: Api())
    monkeypatch.setattr(loyers, "telecharger", lambda url, dest, ttl_jours: _ecrire(dest))
    res = loyers.charger_loyers_officiels(tmp_path, 2025)
    assert res[("49007", "Appartement")] == (14.5, "ANIL 2025")
    assert res[("49007", "Maison")] == (14.5, "ANIL 2025")


def _ecrire(dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(CSV_LOYERS.encode("latin-1"))
    return dest
