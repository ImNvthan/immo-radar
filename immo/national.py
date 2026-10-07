#!/usr/bin/env python3
"""Génère une page de suivi par département dans docs/d/<code>/index.html.

Chaque page contient ses propres données (marché, tendance, saisonnalité) : le visiteur change de
département depuis le sélecteur de la page, sans rien modifier dans le dépôt.
Un département sans donnée DVF (Alsace-Moselle, Mayotte) est simplement ignoré.
"""
import argparse
import datetime as dt
import logging
import sys
import tempfile
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from immo import analyse  # noqa: E402
from immo.departements import NOMS  # noqa: E402
from immo.loyers import charger_loyers_officiels  # noqa: E402
from immo.page import generer_page  # noqa: E402
from immo.reseau import ErreurTelechargement  # noqa: E402

log = logging.getLogger("immo")


def page_departement(dep, base_cfg, officiel, sortie_dir, local_dir=None, annee_courante=None) -> bool:
    """Calcule et écrit la page d'un département. Renvoie False s'il n'y a pas de données."""
    cfg = analyse.normaliser_config({**base_cfg, "zone": {"departements": [dep], "nb_annees": base_cfg.get("zone", {}).get("nb_annees", 3)},
                                     "budget_max": 0, "surface_min": 0})
    try:
        df = analyse.clean(analyse.load_dvf(cfg, local_dir, annee_courante))
    except ErreurTelechargement as e:
        log.warning("Département %s ignoré : %s", dep, e)
        return False
    if df.empty:
        log.warning("Département %s ignoré : aucune vente exploitable", dep)
        return False
    loyers = analyse.Loyers(cfg["loyer_m2_defaut"], {}, officiel, cfg["loyer_officiel"]["coefficient"])
    min_n = int(cfg["min_ventes"])
    ref = df["date"].max()
    stats = analyse.market_stats(df, ref, min_n, loyers)
    tim = analyse.timing(df, ref, min_n)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stats.round({"prix_m2_median": 0, "prix_m2_prec": 0, "evolution_12m": 4, "loyer_m2": 2, "rendement_brut": 4}).to_csv(
            tmp / "marche_communes.csv", index=False)
        analyse.ecrire_tendances(tim, analyse.serie_mensuelle(df, ref, min_n), tmp)
        analyse.ecrire_meta(cfg, ref, tmp)
        generer_page(tmp, Path(sortie_dir) / dep / "index.html", prefixe="../../")
    log.info("Département %s : %d ventes, %d communes/types", dep, len(df), len(stats))
    return True


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S", stream=sys.stdout)
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yml"))
    ap.add_argument("--sortie", default=str(ROOT / "docs" / "d"))
    ap.add_argument("--departements", nargs="*", help="codes à traiter (tous par défaut)")
    ap.add_argument("--local-dir", help="dossier de CSV DVF (tests hors ligne)")
    args = ap.parse_args(argv)

    base_cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    deps = [d.upper() for d in args.departements] if args.departements else sorted(NOMS)
    analyse.CACHE.mkdir(parents=True, exist_ok=True)
    officiel = {}
    if not args.local_dir:
        officiel = charger_loyers_officiels(analyse.CACHE, dt.date.today().year)
    faits = 0
    for dep in deps:
        try:
            faits += page_departement(dep, base_cfg, officiel, args.sortie, args.local_dir)
        except Exception as e:  # noqa: BLE001 - un département défaillant ne doit pas bloquer les autres
            log.warning("Département %s : échec inattendu (%s)", dep, e)
    log.info("%d page(s) départementale(s) générée(s) sur %d", faits, len(deps))
    if faits == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
