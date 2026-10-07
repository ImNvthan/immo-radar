"""Loyers officiels : carte des loyers ANIL / Ministère de la Transition écologique (data.gouv.fr).

Licence Ouverte 2.0. Indicateurs de loyers d'annonce par commune, en euros par m2 et par mois,
charges comprises, estimés par modèle statistique (maille de communes si la commune a peu d'annonces).
"""
import logging
from pathlib import Path

import pandas as pd
import requests

from immo.reseau import ErreurTelechargement, Introuvable, telecharger

log = logging.getLogger("immo")

API = "https://www.data.gouv.fr/api/1/datasets/carte-des-loyers-indicateurs-de-loyers-dannonce-par-commune-en-{annee}/"
FICHIERS = {"Appartement": "pred-app-mef-dhup.csv", "Maison": "pred-mai-mef-dhup.csv"}


def lire_csv_loyers(chemin, annee) -> dict:
    """Renvoie {code_insee: (loyer_m2, origine)} pour un fichier de la carte des loyers."""
    df = pd.read_csv(chemin, sep=";", decimal=",", encoding="latin-1", dtype={"INSEE_C": str})
    out = {}
    for code, loyer, typ in zip(df["INSEE_C"], df["loypredm2"], df["TYPPRED"]):
        if pd.isna(loyer) or loyer <= 0:
            continue
        origine = f"ANIL {annee}" + (" (maille)" if str(typ).strip() == "maille" else "")
        out[code.zfill(5)] = (float(loyer), origine)
    return out


def trouver_urls(annee, session=requests):
    r = session.get(API.format(annee=annee), timeout=60)
    if r.status_code == 404:
        raise Introuvable(annee)
    r.raise_for_status()
    urls = {}
    for res in r.json().get("resources", []):
        for typ, nom in FICHIERS.items():
            if res.get("url", "").endswith("/" + nom):
                urls[typ] = res["url"]
    if len(urls) != len(FICHIERS):
        raise ErreurTelechargement(f"Fichiers de loyers introuvables pour {annee}")
    return urls


def charger_loyers_officiels(cache_dir, annee_max, ttl_jours=90.0, nb_annees_essai=3) -> dict:
    """Renvoie {(code_insee, type_local): (loyer_m2, origine)}, ou {} si la source est indisponible.

    Ne lève jamais d'exception : le radar fonctionne aussi sans loyers officiels.
    """
    cache_dir = Path(cache_dir)
    for annee in range(annee_max, annee_max - nb_annees_essai, -1):
        try:
            urls = trouver_urls(annee)
            resultat = {}
            for typ, url in urls.items():
                chemin = telecharger(url, cache_dir / f"loyers_{annee}_{FICHIERS[typ]}", ttl_jours=ttl_jours)
                for code, valeur in lire_csv_loyers(chemin, annee).items():
                    resultat[(code, typ)] = valeur
            log.info("Loyers officiels %s : %d communes", annee, len(resultat) // 2)
            return resultat
        except Introuvable:
            continue
        except Exception as e:  # noqa: BLE001 - la source de loyers est optionnelle
            log.warning("Loyers officiels indisponibles (%s), loyers de config.yml utilisés", e)
            return {}
    log.warning("Aucune carte des loyers trouvée, loyers de config.yml utilisés")
    return {}
