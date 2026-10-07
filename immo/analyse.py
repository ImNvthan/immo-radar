#!/usr/bin/env python3
"""Radar immobilier : analyse des ventes DVF, indicateurs de timing et scoring d'annonces.

Sortie dans data/ : rapport.md, marche_communes.csv, opportunites.csv
"""
import argparse
import datetime as dt
import io
import os
import sys
import unicodedata
from pathlib import Path

import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DVF_URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/departements/{dep}.csv.gz"
COLS = [
    "id_mutation", "date_mutation", "nature_mutation", "valeur_fonciere",
    "code_commune", "nom_commune", "type_local", "surface_reelle_bati",
]
TYPES = ["Appartement", "Maison"]
MOIS = ["", "janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def norm(texte) -> str:
    """Minuscules, sans accents ni ponctuation, pour comparer les noms de communes."""
    texte = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode()
    for c in "-'_.,":
        texte = texte.replace(c, " ")
    return " ".join(texte.lower().split())


# ----------------------------------------------------------------------------
# Chargement et nettoyage DVF
# ----------------------------------------------------------------------------

def read_dvf_year(year: int, dep: str, local_dir):
    if local_dir:
        path = Path(local_dir) / f"{year}.csv"
        if not path.exists():
            return None
        return pd.read_csv(path, usecols=COLS, dtype=str)
    url = DVF_URL.format(year=year, dep=dep)
    r = requests.get(url, timeout=120)
    if r.status_code == 404:
        print(f"DVF {year} indisponible (404), ignoré")
        return None
    r.raise_for_status()
    return pd.read_csv(io.BytesIO(r.content), compression="gzip", usecols=COLS, dtype=str)


def load_dvf(cfg, local_dir=None) -> pd.DataFrame:
    dep = str(cfg["zone"]["departement"])
    this_year = dt.date.today().year
    years = range(this_year - int(cfg["zone"].get("nb_annees", 3)) + 1, this_year + 1)
    frames = []
    for y in years:
        df = read_dvf_year(y, dep, local_dir)
        if df is not None:
            print(f"DVF {y} : {len(df)} lignes")
            frames.append(df)
    if not frames:
        sys.exit("Aucune donnée DVF chargée. Vérifie le département et la connexion.")
    return pd.concat(frames, ignore_index=True)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["nature_mutation"] == "Vente"]
    df = df[df["type_local"].isin(TYPES)].copy()
    df["valeur_fonciere"] = pd.to_numeric(df["valeur_fonciere"], errors="coerce")
    df["surface"] = pd.to_numeric(df["surface_reelle_bati"], errors="coerce")
    df["date"] = pd.to_datetime(df["date_mutation"], errors="coerce")
    df = df.dropna(subset=["valeur_fonciere", "surface", "date", "nom_commune"])
    df = df[(df["valeur_fonciere"] > 10_000) & (df["surface"] >= 9)]
    # une seule ligne de local par vente : on exclut les ventes multi lots
    taille = df.groupby("id_mutation")["id_mutation"].transform("size")
    df = df[taille == 1].copy()
    df["prix_m2"] = df["valeur_fonciere"] / df["surface"]
    df = df[(df["prix_m2"] >= 300) & (df["prix_m2"] <= 20_000)]
    # écrête les extrêmes par commune et type quand l'échantillon le permet
    g = df.groupby(["code_commune", "type_local"])["prix_m2"]
    lo = g.transform(lambda x: x.quantile(0.02))
    hi = g.transform(lambda x: x.quantile(0.98))
    gros = g.transform("size") >= 20
    df = df[~gros | ((df["prix_m2"] >= lo) & (df["prix_m2"] <= hi))]
    df["commune_norm"] = df["nom_commune"].map(norm)
    return df.reset_index(drop=True)


# ----------------------------------------------------------------------------
# Indicateurs
# ----------------------------------------------------------------------------

def market_stats(df, ref, min_n, loyers, loyers_communes) -> pd.DataFrame:
    recent = df[df["date"] > ref - pd.Timedelta(days=365)]
    prev = df[(df["date"] <= ref - pd.Timedelta(days=365)) & (df["date"] > ref - pd.Timedelta(days=730))]
    keys = ["code_commune", "nom_commune", "commune_norm", "type_local"]
    a = recent.groupby(keys)["prix_m2"].agg(prix_m2_median="median", n_ventes="size").reset_index()
    b = prev.groupby(keys)["prix_m2"].agg(prix_m2_prec="median", n_prec="size").reset_index()
    out = a.merge(b, on=keys, how="left")
    ok = out["n_prec"].fillna(0) >= min_n
    out["evolution_12m"] = (out["prix_m2_median"] / out["prix_m2_prec"] - 1).where(ok)
    out["loyer_m2"] = [
        loyers_communes.get(c, loyers.get(t)) for c, t in zip(out["commune_norm"], out["type_local"])
    ]
    out["rendement_brut"] = out["loyer_m2"] * 12 / out["prix_m2_median"]
    out["fiable"] = out["n_ventes"] >= min_n
    return out.sort_values(["type_local", "rendement_brut"], ascending=[True, False])


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

def score_annonces(path: Path, stats: pd.DataFrame, cfg, loyers, loyers_communes) -> pd.DataFrame:
    cols = ["url", "type_local", "commune", "surface", "prix", "titre"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    a = pd.read_csv(path)
    if a.empty:
        return pd.DataFrame(columns=cols)
    p = cfg["annonces"]
    a["surface"] = pd.to_numeric(a["surface"], errors="coerce")
    a["prix"] = pd.to_numeric(a["prix"], errors="coerce")
    a["commune_norm"] = a["commune"].map(norm)
    ref = stats[stats["fiable"]].set_index(["commune_norm", "type_local"])
    rows = []
    for _, r in a.iterrows():
        key = (r["commune_norm"], r["type_local"])
        row = r.to_dict()
        if key not in ref.index or not (r["surface"] > 0 and r["prix"] > 0):
            row.update(prix_m2_estime=None, mediane_dvf=None, ecart=None, rendement_net=None,
                       ventes_ref=None, opportunite=False, note="commune ou type sans référence fiable")
            rows.append(row)
            continue
        m = ref.loc[key]
        prix_m2 = r["prix"] * (1 - p["marge_negociation"]) / r["surface"]
        ecart = prix_m2 / m["prix_m2_median"] - 1
        loyer = loyers_communes.get(r["commune_norm"], loyers.get(r["type_local"]))
        net = loyer * r["surface"] * 12 * (1 - p["charges_et_vacance"]) / r["prix"]
        row.update(
            prix_m2_estime=round(prix_m2), mediane_dvf=round(m["prix_m2_median"]),
            ecart=round(ecart, 3), rendement_net=round(net, 3), ventes_ref=int(m["n_ventes"]),
            opportunite=bool(ecart <= -p["decote_min"] and net >= p["rendement_net_min"]), note="",
        )
        rows.append(row)
    out = pd.DataFrame(rows).drop(columns=["commune_norm"])
    return out.sort_values("ecart", na_position="last")


# ----------------------------------------------------------------------------
# Rapport et alertes
# ----------------------------------------------------------------------------

def pct(x):
    return "n/d" if x is None or pd.isna(x) else f"{x * 100:+.1f} %"


def write_report(cfg, ref, tim, stats, scored) -> str:
    lines = [
        "# Radar immobilier",
        "",
        f"Département {cfg['zone']['departement']} | dernière vente DVF : {ref.date()} | généré le {dt.date.today()}",
        "",
        "Indicateurs statistiques calculés sur les ventes réelles (DVF). Ce n'est pas un conseil en investissement.",
        "",
        "## Quand acheter",
        "",
    ]
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
    lines += ["## Quoi regarder (communes)", "",
              "Classement par rendement brut indicatif (loyer de config.yml, à adapter). Communes avec échantillon fiable uniquement.", ""]
    for t in TYPES:
        s = stats[(stats["type_local"] == t) & stats["fiable"]].head(12)
        if s.empty:
            continue
        lines += [f"### {t}", "", "| Commune | €/m² médian | Ventes 12m | Évol. 12m | Rend. brut |", "|---|---|---|---|---|"]
        for _, r in s.iterrows():
            lines.append(f"| {r['nom_commune']} | {r['prix_m2_median']:.0f} | {r['n_ventes']} | {pct(r['evolution_12m'])} | {r['rendement_brut'] * 100:.1f} % |")
        lines.append("")
    lines += ["## Annonces", ""]
    if scored.empty:
        lines.append("Aucune annonce dans annonces.csv.")
    else:
        opp = scored[scored["opportunite"]]
        lines.append(f"{len(opp)} opportunité(s) sur {len(scored)} annonce(s) analysée(s).")
        lines.append("")
        for _, r in opp.iterrows():
            lines.append(f"- {r['commune']} | {r['type_local']} {r['surface']:.0f} m² | {r['prix']:.0f} € | décote {pct(r['ecart'])} | rend. net {r['rendement_net'] * 100:.1f} % | {r['url']}")
    text = "\n".join(lines) + "\n"
    (DATA / "rapport.md").write_text(text, encoding="utf-8")
    return text


def notify(scored: pd.DataFrame, previous_urls: set):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if scored.empty or not token or not chat:
        return
    new = scored[scored["opportunite"] & ~scored["url"].isin(previous_urls)]
    if new.empty:
        return
    msg = ["Nouvelles opportunités immobilières :"]
    for _, r in new.head(10).iterrows():
        msg.append(f"{r['commune']} {r['type_local']} {r['surface']:.0f} m² {r['prix']:.0f} € ({pct(r['ecart'])} vs DVF)\n{r['url']}")
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat, "text": "\n\n".join(msg), "disable_web_page_preview": True},
        timeout=30,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yml"))
    ap.add_argument("--annonces", default=str(ROOT / "annonces.csv"))
    ap.add_argument("--local-dir", help="dossier de CSV DVF {annee}.csv (tests hors ligne)")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    loyers = cfg["loyer_m2_defaut"]
    loyers_communes = {norm(k): v for k, v in (cfg.get("loyers_communes") or {}).items()}
    min_n = int(cfg.get("min_ventes", 15))
    DATA.mkdir(exist_ok=True)

    df = clean(load_dvf(cfg, args.local_dir))
    if df.empty:
        sys.exit("Aucune vente exploitable après nettoyage.")
    ref = df["date"].max()
    stats = market_stats(df, ref, min_n, loyers, loyers_communes)
    tim = timing(df, ref, min_n)
    scored = score_annonces(Path(args.annonces), stats, cfg, loyers, loyers_communes)

    prev_path = DATA / "opportunites.csv"
    previous = set()
    if prev_path.exists() and prev_path.stat().st_size > 0:
        old = pd.read_csv(prev_path)
        if "opportunite" in old.columns:
            previous = set(old.loc[old["opportunite"].astype(str) == "True", "url"])

    stats.to_csv(DATA / "marche_communes.csv", index=False)
    scored.to_csv(prev_path, index=False)
    write_report(cfg, ref, tim, stats, scored)
    notify(scored, previous)
    print(f"OK : {len(df)} ventes, {len(stats)} lignes commune/type, {int(scored['opportunite'].sum()) if not scored.empty else 0} opportunité(s)")


if __name__ == "__main__":
    main()
