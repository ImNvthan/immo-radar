#!/usr/bin/env python3
"""Radar immobilier : analyse des ventes DVF, indicateurs de timing et scoring d'annonces.

Sortie dans data/ : rapport.md, marche_communes.csv, opportunites.csv, tendance.csv,
tendance_mensuelle.csv, saisonnalite.csv. La page docs/index.html est générée par immo/page.py.
"""
import argparse
import copy
import datetime as dt
import json
import logging
import os
import sys
import unicodedata
from pathlib import Path

import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from immo.loyers import charger_loyers_officiels  # noqa: E402
from immo.reseau import ErreurTelechargement, Introuvable, telecharger  # noqa: E402

DATA = ROOT / "data"
CACHE = DATA / "cache"
DOCS = ROOT / "docs"
DVF_URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/departements/{dep}.csv.gz"
COLS = [
    "id_mutation", "date_mutation", "nature_mutation", "valeur_fonciere", "code_commune",
    "nom_commune", "type_local", "surface_reelle_bati", "nombre_pieces_principales",
    "adresse_numero", "adresse_nom_voie", "surface_terrain",
]
TYPES = ["Appartement", "Maison"]
COMMERCE = "Local industriel. commercial ou assimilé"
MOIS = ["", "janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]

DEFAUTS = {
    "zone": {"departements": ["49"], "communes": [], "nb_annees": 3},
    "min_ventes": 15,
    "budget_max": 0,
    "surface_min": 0,
    "loyer_m2_defaut": {"Appartement": 12.0, "Maison": 10.0},
    "loyers_communes": {},
    "loyer_officiel": {"actif": True, "coefficient": 0.9},
    "annonces": {
        "marge_negociation": 0.05, "decote_min": 0.08,
        "rendement_net_min": 0.045, "charges_et_vacance": 0.25,
    },
}

log = logging.getLogger("immo")


def norm(texte) -> str:
    """Minuscules, sans accents ni ponctuation, pour comparer les noms de communes."""
    texte = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode()
    for c in "-'_.,":
        texte = texte.replace(c, " ")
    return " ".join(texte.lower().split())


# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

def _fusion(base, extra):
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _fusion(base[k], v)
        else:
            base[k] = v
    return base


def normaliser_config(brut) -> dict:
    """Complète la configuration avec les valeurs par défaut et accepte l'ancien format."""
    cfg = _fusion(copy.deepcopy(DEFAUTS), brut or {})
    zone = cfg["zone"]
    zone_brut = (brut or {}).get("zone") or {}
    deps = zone_brut.get("departements") or zone_brut.get("departement") or []  # l'ancien format est accepté
    zone.pop("departement", None)
    if isinstance(deps, (str, int)):
        deps = [deps]
    communes = zone.get("communes") or []
    if isinstance(communes, (str, int)):
        communes = [communes]
    zone["communes"] = [str(c).strip() for c in communes]
    if not deps and zone["communes"]:  # déduit des codes INSEE listés
        deps = [c[:3] if c.startswith("97") else c[:2] for c in zone["communes"] if c.isalnum() and len(c) == 5]
    if not deps and not any(k in zone_brut for k in ("departements", "departement")):
        deps = DEFAUTS["zone"]["departements"]
    zone["departements"] = sorted({str(d).strip().upper().zfill(2) for d in deps if str(d).strip()})
    if not zone["departements"]:
        raise ValueError("config.yml : indique au moins un département dans zone.departements")
    zone["nb_annees"] = int(zone.get("nb_annees", 3))
    for cle in ("budget_max", "surface_min"):
        cfg[cle] = float(cfg.get(cle) or 0)
    return cfg


class Loyers:
    """Résout le loyer au m2 : config.yml (commune), puis carte des loyers officielle, puis défaut."""

    def __init__(self, defaut, communes, officiel=None, coefficient=1.0):
        self.defaut = defaut
        self.communes = {(k if str(k).isdigit() else norm(k)): v for k, v in (communes or {}).items()}
        self.officiel = officiel or {}
        self.coef = float(coefficient)

    def resoudre(self, code, nom_norm, typ):
        for cle in (str(code), nom_norm):
            if cle in self.communes:
                v = self.communes[cle]
                v = v.get(typ) if isinstance(v, dict) else v
                if v:
                    return float(v), "config.yml"
        if (str(code), typ) in self.officiel:
            valeur, origine = self.officiel[(str(code), typ)]
            return valeur * self.coef, origine
        return float(self.defaut[typ]), "défaut config.yml"


# ----------------------------------------------------------------------------
# Chargement et nettoyage DVF
# ----------------------------------------------------------------------------

def read_dvf_year(year: int, dep: str, local_dir=None, cache_dir=CACHE, ttl_jours=7.0):
    if local_dir:
        for nom in (f"{year}_{dep}.csv", f"{year}.csv"):
            path = Path(local_dir) / nom
            if path.exists():
                return pd.read_csv(path, usecols=lambda c: c in COLS, dtype=str)
        return None
    try:
        chemin = telecharger(DVF_URL.format(year=year, dep=dep), Path(cache_dir) / f"dvf_{year}_{dep}.csv.gz", ttl_jours)
    except Introuvable:
        log.info("DVF %s département %s : pas encore publié, ignoré", year, dep)
        return None
    return pd.read_csv(chemin, compression="gzip", usecols=lambda c: c in COLS, dtype=str)


def load_dvf(cfg, local_dir=None, annee_courante=None) -> pd.DataFrame:
    """Charge les nb_annees dernières années disponibles pour chaque département."""
    nb = cfg["zone"]["nb_annees"]
    annee = annee_courante or dt.date.today().year
    frames = []
    for dep in cfg["zone"]["departements"]:
        trouvees = 0
        for y in range(annee, annee - nb - 2, -1):
            if trouvees >= nb:
                break
            df = read_dvf_year(y, dep, local_dir)
            if df is not None:
                log.info("DVF %s département %s : %d lignes", y, dep, len(df))
                frames.append(df)
                trouvees += 1
        if trouvees == 0:
            raise ErreurTelechargement(f"Aucune donnée DVF pour le département {dep} (vérifie le code et la connexion)")
    return pd.concat(frames, ignore_index=True)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Ne garde que les ventes d'un seul logement (appartement ou maison) au prix au m2 plausible."""
    df = df[df["nature_mutation"] == "Vente"].copy()
    for c in ("surface_terrain", "nombre_pieces_principales", "adresse_numero", "adresse_nom_voie"):
        if c not in df:
            df[c] = None
    df["valeur_fonciere"] = pd.to_numeric(df["valeur_fonciere"], errors="coerce")
    df["surface"] = pd.to_numeric(df["surface_reelle_bati"], errors="coerce")
    df["terrain"] = pd.to_numeric(df["surface_terrain"], errors="coerce").fillna(0)
    df["date"] = pd.to_datetime(df["date_mutation"], errors="coerce")

    # Une maison sur plusieurs parcelles apparaît sur plusieurs lignes identiques : on la compte une fois.
    est_maison = df["type_local"] == "Maison"
    doublon = est_maison & df.duplicated(
        ["id_mutation", "type_local", "surface_reelle_bati", "nombre_pieces_principales", "adresse_numero", "adresse_nom_voie"]
    )
    # Ventes d'un bien avec un gros terrain (ferme, lotissement) ou un local commercial : exclues.
    terrain_total = df.groupby("id_mutation")["terrain"].transform("sum")
    avec_commerce = (df["type_local"] == COMMERCE).groupby(df["id_mutation"]).transform("any")
    df = df[~doublon & ~avec_commerce & (terrain_total <= 10_000)]

    # Une seule ligne de logement par vente : on exclut les ventes multi lots.
    df = df[df["type_local"].isin(TYPES)]
    taille = df.groupby("id_mutation")["id_mutation"].transform("size")
    df = df[taille == 1]

    df = df.dropna(subset=["valeur_fonciere", "surface", "date", "nom_commune", "code_commune"])
    df = df[(df["valeur_fonciere"] > 10_000) & (df["surface"] >= 9)]
    df = df[((df["type_local"] == "Appartement") & (df["surface"] <= 300)) | ((df["type_local"] == "Maison") & (df["surface"] <= 500))]
    df = df.copy()
    df["prix_m2"] = df["valeur_fonciere"] / df["surface"]
    df = df[(df["prix_m2"] >= 300) & (df["prix_m2"] <= 20_000)]
    # écrête les extrêmes par commune, type et année quand l'échantillon le permet
    g = df.groupby(["code_commune", "type_local", df["date"].dt.year])["prix_m2"]
    lo = g.transform(lambda x: x.quantile(0.02))
    hi = g.transform(lambda x: x.quantile(0.98))
    gros = g.transform("size") >= 20
    df = df[~gros | ((df["prix_m2"] >= lo) & (df["prix_m2"] <= hi))]
    df["commune_norm"] = df["nom_commune"].map(norm)
    return df.reset_index(drop=True)


def filtrer_zone(df: pd.DataFrame, communes) -> pd.DataFrame:
    """Restreint aux communes listées (code INSEE ou nom). Liste vide : tout le département."""
    if not communes:
        return df
    codes = {c for c in communes if c.isdigit()}
    noms = {norm(c) for c in communes if not c.isdigit()}
    return df[df["code_commune"].isin(codes) | df["commune_norm"].isin(noms)].reset_index(drop=True)


# ----------------------------------------------------------------------------
# Indicateurs
# ----------------------------------------------------------------------------

def market_stats(df, ref, min_n, loyers: Loyers, budget_max=0, surface_min=0) -> pd.DataFrame:
    recent = df[df["date"] > ref - pd.Timedelta(days=365)]
    prev = df[(df["date"] <= ref - pd.Timedelta(days=365)) & (df["date"] > ref - pd.Timedelta(days=730))]
    keys = ["code_commune", "nom_commune", "commune_norm", "type_local"]
    a = recent.groupby(keys)["prix_m2"].agg(prix_m2_median="median", n_ventes="size").reset_index()
    b = prev.groupby(keys)["prix_m2"].agg(prix_m2_prec="median", n_prec="size").reset_index()
    out = a.merge(b, on=keys, how="left")
    ok = out["n_prec"].fillna(0) >= min_n
    out["evolution_12m"] = (out["prix_m2_median"] / out["prix_m2_prec"] - 1).where(ok)
    res = [loyers.resoudre(c, n, t) for c, n, t in zip(out["code_commune"], out["commune_norm"], out["type_local"])]
    out["loyer_m2"] = [r[0] for r in res]
    out["loyer_origine"] = [r[1] for r in res]
    out["rendement_brut"] = out["loyer_m2"] * 12 / out["prix_m2_median"]
    out["fiable"] = out["n_ventes"] >= min_n
    if budget_max > 0 and surface_min > 0:
        out["prix_bien_type"] = (out["prix_m2_median"] * surface_min).round()
        out["dans_budget"] = out["prix_bien_type"] <= budget_max
    else:
        out["prix_bien_type"] = None
        out["dans_budget"] = True
    return out.sort_values(["type_local", "rendement_brut"], ascending=[True, False]).reset_index(drop=True)


def timing(df, ref, min_n) -> dict:
    """Tendance du prix au m2 et saisonnalité sur la zone, par type de bien."""
    res = {}
    for t in TYPES:
        d = df[df["type_local"] == t]
        if len(d) < min_n * 4:
            continue

        def med(start_days, end_days):
            m = d[(d["date"] <= ref - pd.Timedelta(days=start_days)) & (d["date"] > ref - pd.Timedelta(days=end_days))]
            return (m["prix_m2"].median(), len(m))

        r12, n12 = med(0, 365)
        p12, np12 = med(365, 730)
        r6, n6 = med(0, 182)
        p6, np6 = med(182, 365)
        evo12 = r12 / p12 - 1 if np12 >= min_n and n12 >= min_n else None
        evo6 = r6 / p6 - 1 if np6 >= min_n and n6 >= min_n else None

        # saisonnalité : écart du prix médian de chaque mois par rapport à la médiane de son année
        d = d.assign(annee=d["date"].dt.year, mois=d["date"].dt.month)
        ratios = {}
        for (an, m), g in d.groupby(["annee", "mois"]):
            ref_an = d[d["annee"] == an]["prix_m2"].median()
            if len(g) >= min_n:
                ratios.setdefault(m, []).append(g["prix_m2"].median() / ref_an)
        saison = {m: sum(v) / len(v) for m, v in ratios.items() if len(v) >= 2}
        ordre = sorted(saison, key=saison.get)
        res[t] = {
            "prix_m2": r12, "n": n12, "evo12": evo12, "evo6": evo6,
            "mois_bas": ordre[:3], "mois_hauts": ordre[-3:][::-1], "saison": saison,
        }
    return res


def serie_mensuelle(df, ref, min_n, nb_mois=36) -> pd.DataFrame:
    """Prix médian au m2 par mois et par type, sur les nb_mois derniers mois."""
    d = df[df["date"] > ref - pd.DateOffset(months=nb_mois)].copy()
    d["mois"] = d["date"].dt.strftime("%Y-%m")
    s = d.groupby(["type_local", "mois"])["prix_m2"].agg(prix_m2_median="median", n_ventes="size").reset_index()
    s = s[s["n_ventes"] >= max(5, min_n // 3)]
    s["prix_m2_median"] = s["prix_m2_median"].round(0)
    return s


def lecture(evo12, evo6) -> str:
    if evo12 is None:
        return "Données insuffisantes pour juger la tendance."
    if evo12 < -0.02 and (evo6 is None or evo6 < 0.01):
        return "Prix en recul : contexte plutôt favorable à l'acheteur, marge de négociation probable."
    if evo12 > 0.02 and (evo6 is None or evo6 > -0.01):
        return "Prix en hausse : marché plus tendu, les bons biens partent vite et la négociation est plus limitée."
    return "Prix globalement stables : pas de signal fort, le choix du bien pèse plus que le timing."


# ----------------------------------------------------------------------------
# Annonces
# ----------------------------------------------------------------------------

SORTIE_ANNONCES = [
    "url", "type_local", "commune", "surface", "prix", "titre", "prix_m2_estime", "mediane_dvf", "ecart",
    "rendement_net", "loyer_m2", "loyer_origine", "ventes_ref", "opportunite", "note",
]


def score_annonces(path: Path, stats: pd.DataFrame, cfg, loyers: Loyers) -> pd.DataFrame:
    vide = pd.DataFrame(columns=SORTIE_ANNONCES)
    if not Path(path).exists():
        return vide
    a = pd.read_csv(path)
    if a.empty:
        return vide
    p = cfg["annonces"]
    budget, smin = cfg["budget_max"], cfg["surface_min"]
    for c in ("url", "type_local", "commune", "titre"):
        if c not in a:
            a[c] = ""
    a["surface"] = pd.to_numeric(a["surface"], errors="coerce")
    a["prix"] = pd.to_numeric(a["prix"], errors="coerce")
    a["commune_norm"] = a["commune"].map(norm)
    fiables = stats[stats["fiable"]].sort_values("n_ventes", ascending=False)
    ref = fiables.drop_duplicates(["commune_norm", "type_local"]).set_index(["commune_norm", "type_local"])
    rows = []
    for _, r in a.iterrows():
        key = (r["commune_norm"], r["type_local"])
        row = {c: r.get(c) for c in ("url", "type_local", "commune", "surface", "prix", "titre")}
        row.update(prix_m2_estime=None, mediane_dvf=None, ecart=None, rendement_net=None, loyer_m2=None,
                   loyer_origine=None, ventes_ref=None, opportunite=False, note="")
        if key not in ref.index or not (r["surface"] > 0 and r["prix"] > 0):
            row["note"] = "commune ou type sans référence fiable"
            rows.append(row)
            continue
        m = ref.loc[key]
        prix_m2 = r["prix"] * (1 - p["marge_negociation"]) / r["surface"]
        ecart = prix_m2 / m["prix_m2_median"] - 1
        loyer, origine = loyers.resoudre(m["code_commune"], r["commune_norm"], r["type_local"])
        net = loyer * r["surface"] * 12 * (1 - p["charges_et_vacance"]) / r["prix"]
        hors = ""
        if budget > 0 and r["prix"] > budget:
            hors = "hors budget"
        elif smin > 0 and r["surface"] < smin:
            hors = "surface inférieure au minimum"
        row.update(
            prix_m2_estime=round(prix_m2), mediane_dvf=round(m["prix_m2_median"]), ecart=round(ecart, 3),
            rendement_net=round(net, 3), loyer_m2=round(loyer, 2), loyer_origine=origine,
            ventes_ref=int(m["n_ventes"]), note=hors,
            opportunite=bool(not hors and ecart <= -p["decote_min"] and net >= p["rendement_net_min"]),
        )
        rows.append(row)
    return pd.DataFrame(rows, columns=SORTIE_ANNONCES).sort_values("ecart", na_position="last").reset_index(drop=True)


def nouvelles_opportunites(scored: pd.DataFrame, previous_urls: set) -> pd.DataFrame:
    if scored.empty:
        return scored
    return scored[scored["opportunite"].astype(bool) & ~scored["url"].isin(previous_urls)]


def urls_precedentes(path: Path) -> set:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    old = pd.read_csv(path)
    if "opportunite" not in old.columns or "url" not in old.columns:
        return set()
    return set(old.loc[old["opportunite"].astype(str) == "True", "url"])


# ----------------------------------------------------------------------------
# Rapport et alertes
# ----------------------------------------------------------------------------

def pct(x):
    return "n/d" if x is None or pd.isna(x) else f"{x * 100:+.1f} %".replace(".", ",")


def fr(x, nd=1) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def libelle_zone(cfg) -> str:
    z = cfg["zone"]
    txt = "Département" + ("s " if len(z["departements"]) > 1 else " ") + ", ".join(z["departements"])
    if z["communes"]:
        txt += f" (communes : {', '.join(z['communes'])})"
    return txt


def write_report(cfg, ref, tim, stats, scored, data_dir=None) -> str:
    data_dir = Path(data_dir or DATA)
    lines = [
        "# Radar immobilier",
        "",
        f"{libelle_zone(cfg)} | dernière vente DVF : {ref.date()}",
        "",
        "Indicateurs statistiques calculés sur les ventes réelles (DVF). Ce n'est pas un conseil en investissement.",
        "",
    ]
    if cfg["budget_max"] > 0 or cfg["surface_min"] > 0:
        crit = []
        if cfg["budget_max"] > 0:
            crit.append(f"budget maximum {cfg['budget_max']:.0f} €")
        if cfg["surface_min"] > 0:
            crit.append(f"surface minimale {cfg['surface_min']:.0f} m²")
        lines += [f"Critères : {', '.join(crit)}.", ""]
    lines += ["## Quand acheter", ""]
    if not tim:
        lines.append("Pas assez de ventes pour établir une tendance.")
    for t, v in tim.items():
        lines += [
            f"### {t}",
            f"- Prix médian sur 12 mois : {v['prix_m2']:.0f} €/m² ({v['n']} ventes)",
            f"- Évolution sur 12 mois : {pct(v['evo12'])} | sur 6 mois : {pct(v['evo6'])}",
            f"- Lecture : {lecture(v['evo12'], v['evo6'])}",
        ]
        if v["mois_bas"]:
            bas = ", ".join(MOIS[m] for m in v["mois_bas"])
            haut = ", ".join(MOIS[m] for m in v["mois_hauts"])
            lines.append(f"- Saisonnalité historique : prix plus bas en {bas} ; plus hauts en {haut}")
        lines.append("")
    lines += [
        "## Quoi regarder (communes)", "",
        "Classement par rendement brut indicatif. Communes avec échantillon fiable uniquement. "
        "Origine du loyer : `config.yml` (surcharge manuelle), `ANIL` (carte des loyers officielle, "
        "`maille` si estimée à partir des communes voisines) ou `défaut` (valeur par défaut de config.yml).",
        "",
    ]
    if cfg["budget_max"] > 0 and cfg["surface_min"] > 0:
        lines += [f"Seules les communes où un bien de {cfg['surface_min']:.0f} m² au prix médian reste sous {cfg['budget_max']:.0f} € sont listées.", ""]
    for t in TYPES:
        s = stats[(stats["type_local"] == t) & stats["fiable"] & stats["dans_budget"]].head(15)
        if s.empty:
            continue
        lines += [f"### {t}", "", "| Commune | €/m² médian | Ventes 12m | Évol. 12m | Loyer €/m² | Origine loyer | Rend. brut |", "|---|---|---|---|---|---|---|"]
        for _, r in s.iterrows():
            lines.append(
                f"| {r['nom_commune']} | {r['prix_m2_median']:.0f} | {r['n_ventes']} | {pct(r['evolution_12m'])} | "
                f"{fr(r['loyer_m2'])} | {r['loyer_origine']} | {fr(r['rendement_brut'] * 100)} % |"
            )
        lines.append("")
    lines += ["## Annonces", ""]
    if scored.empty:
        lines.append("Aucune annonce dans annonces.csv.")
    else:
        opp = scored[scored["opportunite"].astype(bool)]
        lines.append(f"{len(opp)} opportunité(s) sur {len(scored)} annonce(s) analysée(s).")
        lines.append("")
        for _, r in opp.iterrows():
            lines.append(
                f"- {r['commune']} | {r['type_local']} {r['surface']:.0f} m² | {r['prix']:.0f} € | décote {pct(r['ecart'])} "
                f"| rend. net {fr(r['rendement_net'] * 100)} % (loyer {r['loyer_origine']}) | {r['url']}"
            )
    text = "\n".join(lines) + "\n"
    (data_dir / "rapport.md").write_text(text, encoding="utf-8")
    return text


def message_telegram(new: pd.DataFrame) -> str:
    msg = ["Nouvelles opportunités immobilières :"]
    for _, r in new.head(10).iterrows():
        msg.append(f"{r['commune']} {r['type_local']} {r['surface']:.0f} m² {r['prix']:.0f} € ({pct(r['ecart'])} vs DVF)\n{r['url']}")
    return "\n\n".join(msg)


def envoyer_telegram(texte: str) -> bool:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": texte, "disable_web_page_preview": True}, timeout=30,
        )
        r.raise_for_status()
        return True
    except requests.RequestException as e:
        log.warning("Alerte Telegram non envoyée : %s", type(e).__name__)  # le message peut contenir le jeton
        return False


def notify(scored: pd.DataFrame, previous_urls: set):
    new = nouvelles_opportunites(scored, previous_urls)
    if not new.empty:
        envoyer_telegram(message_telegram(new))


# ----------------------------------------------------------------------------
# Programme principal
# ----------------------------------------------------------------------------

def ecrire_tendances(tim, serie, data_dir):
    lignes = [
        {"type_local": t, "prix_m2": round(v["prix_m2"]), "n_ventes": v["n"], "evo12": v["evo12"], "evo6": v["evo6"],
         "lecture": lecture(v["evo12"], v["evo6"])}
        for t, v in tim.items()
    ]
    pd.DataFrame(lignes, columns=["type_local", "prix_m2", "n_ventes", "evo12", "evo6", "lecture"]).round(4).to_csv(
        data_dir / "tendance.csv", index=False)
    saison = [{"type_local": t, "mois": m, "indice": round(i, 4)} for t, v in tim.items() for m, i in sorted(v["saison"].items())]
    pd.DataFrame(saison, columns=["type_local", "mois", "indice"]).to_csv(data_dir / "saisonnalite.csv", index=False)
    serie.to_csv(data_dir / "tendance_mensuelle.csv", index=False)


def ecrire_meta(cfg, ref, data_dir):
    meta = {
        "zone": libelle_zone(cfg), "derniere_vente": str(ref.date()),
        "budget_max": cfg["budget_max"], "surface_min": cfg["surface_min"],
        "seuils": cfg["annonces"], "min_ventes": cfg["min_ventes"],
    }
    (data_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def executer(args):
    cfg = normaliser_config(yaml.safe_load(Path(args.config).read_text(encoding="utf-8")))
    min_n = int(cfg["min_ventes"])
    DATA.mkdir(exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    officiel = {}
    if cfg["loyer_officiel"]["actif"] and not args.local_dir:
        officiel = charger_loyers_officiels(CACHE, dt.date.today().year)
    loyers = Loyers(cfg["loyer_m2_defaut"], cfg["loyers_communes"], officiel, cfg["loyer_officiel"]["coefficient"])

    df = filtrer_zone(clean(load_dvf(cfg, args.local_dir)), cfg["zone"]["communes"])
    if df.empty:
        raise ValueError("Aucune vente exploitable après nettoyage et filtrage par communes.")
    ref = df["date"].max()
    stats = market_stats(df, ref, min_n, loyers, cfg["budget_max"], cfg["surface_min"])
    tim = timing(df, ref, min_n)
    scored = score_annonces(Path(args.annonces), stats, cfg, loyers)

    prev_path = DATA / "opportunites.csv"
    previous = urls_precedentes(prev_path)

    stats.round({"prix_m2_median": 0, "prix_m2_prec": 0, "evolution_12m": 4, "loyer_m2": 2, "rendement_brut": 4}).to_csv(
        DATA / "marche_communes.csv", index=False)
    scored.to_csv(prev_path, index=False)
    ecrire_tendances(tim, serie_mensuelle(df, ref, min_n), DATA)
    ecrire_meta(cfg, ref, DATA)
    write_report(cfg, ref, tim, stats, scored)
    try:
        from immo.page import generer_page
        generer_page(DATA, DOCS / "index.html")
    except Exception as e:  # noqa: BLE001 - la page est un bonus, elle ne doit pas faire échouer l'analyse
        log.warning("Page de suivi non générée : %s", e)
    notify(scored, previous)
    nb_opp = int(scored["opportunite"].astype(bool).sum()) if not scored.empty else 0
    log.info("OK : %d ventes, %d lignes commune/type, %d opportunité(s)", len(df), len(stats), nb_opp)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S", stream=sys.stdout)
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yml"))
    ap.add_argument("--annonces", default=str(ROOT / "annonces.csv"))
    ap.add_argument("--local-dir", help="dossier de CSV DVF {annee}.csv (tests hors ligne)")
    args = ap.parse_args()
    try:
        executer(args)
    except (ErreurTelechargement, ValueError, yaml.YAMLError) as e:
        log.error("%s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
