"""Téléchargements avec cache disque, nouvelles tentatives et messages d'erreur clairs."""
import logging
import time
from pathlib import Path

import requests

log = logging.getLogger("immo")


class Introuvable(Exception):
    """La ressource demandée n'existe pas (HTTP 404)."""


class ErreurTelechargement(Exception):
    """Le téléchargement a échoué après toutes les tentatives."""


def telecharger(url, dest, ttl_jours=7.0, tentatives=4, timeout=120, pause=time.sleep):
    """Télécharge url vers dest et renvoie le chemin.

    Un fichier déjà présent et plus récent que ttl_jours est réutilisé. Si le réseau échoue
    mais qu'une ancienne copie existe, elle est utilisée avec un avertissement.
    """
    dest = Path(dest)
    if dest.exists() and (time.time() - dest.stat().st_mtime) < ttl_jours * 86400:
        log.info("Cache utilisé : %s", dest.name)
        return dest
    derniere = None
    for essai in range(tentatives):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 404:
                raise Introuvable(url)
            r.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".part")
            tmp.write_bytes(r.content)
            tmp.replace(dest)
            log.info("Téléchargé : %s (%d Ko)", dest.name, len(r.content) // 1024)
            return dest
        except Introuvable:
            raise
        except requests.RequestException as e:
            derniere = e
            attente = 2 ** (essai + 1)
            log.warning("Échec du téléchargement de %s (essai %d/%d) : %s", url, essai + 1, tentatives, e)
            if essai < tentatives - 1:
                pause(attente)
    if dest.exists():
        log.warning("Réseau indisponible, ancienne copie de %s utilisée", dest.name)
        return dest
    raise ErreurTelechargement(f"Impossible de télécharger {url} après {tentatives} essais : {derniere}")
