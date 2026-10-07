"""Génère docs/index.html : page statique autonome (aucune dépendance externe) à partir de data/."""
import html
import json
from pathlib import Path

import pandas as pd

MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
COULEURS = {"Appartement": "var(--c1)", "Maison": "var(--c2)"}

CSS = """
:root{--bg:#f6f7f9;--carte:#fff;--txt:#1b2430;--doux:#5b6675;--bord:#dde2e8;--c1:#1d6fd6;--c2:#d6781d;--ok:#18794e;--ko:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#12161c;--carte:#1b2129;--txt:#e8ecf1;--doux:#9aa5b4;--bord:#2d3643;--c1:#5aa2f5;--c2:#f0a050;--ok:#4cc38a;--ko:#ff8a80}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:980px;margin:0 auto;padding:16px}
h1{font-size:1.5rem;margin:.2em 0}h2{font-size:1.2rem;margin:1.6em 0 .5em}h3{font-size:1rem;margin:1em 0 .3em}
.doux{color:var(--doux);font-size:.9rem}
.carte{background:var(--carte);border:1px solid var(--bord);border-radius:12px;padding:14px;margin:10px 0}
.grille{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}
.grille .carte{margin:0}
.gros{font-size:1.7rem;font-weight:700}
.hausse{color:var(--ko)}.baisse{color:var(--ok)}
svg{width:100%;height:auto;display:block}svg text{fill:var(--doux);font-size:16px}
.defil{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{padding:6px 8px;border-bottom:1px solid var(--bord);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:var(--doux);font-weight:600}
a{color:var(--c1)}
"""


def e(x):
    return html.escape(str(x), quote=True)


def fr(x, nd=1):
    return f"{x:.{nd}f}".replace(".", ",")


def pct(x):
    return "n/d" if x is None or pd.isna(x) else f"{x * 100:+.1f} %".replace(".", ",")


def classe_evo(x):
    """Une hausse des prix est défavorable à l'acheteur (rouge), une baisse lui est favorable (vert)."""
    if x is None or pd.isna(x):
        return ""
    return "hausse" if x > 0.02 else "baisse" if x < -0.02 else ""


def lire(data, nom):
    chemin = Path(data) / nom
    if not chemin.exists() or chemin.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(chemin)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def courbe(serie: pd.DataFrame) -> str:
    """Courbe SVG du prix médian mensuel par type."""
    if serie.empty:
        return "<p class='doux'>Pas assez de données.</p>"
    mois = sorted(serie["mois"].unique())
    idx = {m: i for i, m in enumerate(mois)}
    lo, hi = serie["prix_m2_median"].min(), serie["prix_m2_median"].max()
    marge = max((hi - lo) * 0.1, 1)
    lo, hi = lo - marge, hi + marge
    L, H, g, d, b = 600, 230, 48, 10, 28

    def x(m):
        return g + (L - g - d) * (idx[m] / max(len(mois) - 1, 1))

    def y(v):
        return H - b - (H - b - 10) * (v - lo) / (hi - lo)

    out = [f"<svg viewBox='0 0 {L} {H}' role='img' aria-label='Prix médian au m2 par mois'>"]
    for k in range(4):
        v = lo + (hi - lo) * k / 3
        out.append(f"<line x1='{g}' x2='{L - d}' y1='{y(v):.1f}' y2='{y(v):.1f}' stroke='var(--bord)'/>")
        out.append(f"<text x='{g - 6}' y='{y(v) + 4:.1f}' text-anchor='end'>{v:.0f}</text>")
    pas = max(len(mois) // 6, 1)
    for m in mois[::pas]:
        out.append(f"<text x='{x(m):.1f}' y='{H - 8}' text-anchor='middle'>{e(m[5:7] + '/' + m[2:4])}</text>")
    for t, grp in serie.groupby("type_local"):
        pts = " ".join(f"{x(m):.1f},{y(v):.1f}" for m, v in zip(grp["mois"], grp["prix_m2_median"]))
        out.append(f"<polyline points='{pts}' fill='none' stroke='{COULEURS.get(t, 'var(--txt)')}' stroke-width='2.5' stroke-linejoin='round'/>")
    out.append("</svg>")
    legende = " ".join(f"<span style='color:{COULEURS.get(t, 'inherit')}'>&#9632;</span> {e(t)}" for t in sorted(serie["type_local"].unique()))
    return "".join(out) + f"<p class='doux'>{legende} &middot; prix médian au m² par mois de vente</p>"


def barres(saison: pd.DataFrame, type_local: str) -> str:
    s = saison[saison["type_local"] == type_local] if not saison.empty else saison
    if s.empty:
        return "<p class='doux'>Historique insuffisant.</p>"
    ind = {int(m): float(i) for m, i in zip(s["mois"], s["indice"])}
    amp = max(max(abs(v - 1) for v in ind.values()), 0.01)
    L, H, mid = 600, 170, 85
    larg = (L - 20) / 12
    out = [f"<svg viewBox='0 0 {L} {H}' role='img' aria-label='Saisonnalité {e(type_local)}'>",
           f"<line x1='10' x2='{L - 10}' y1='{mid}' y2='{mid}' stroke='var(--bord)'/>"]
    couleur = COULEURS.get(type_local, "var(--txt)")
    for m in range(1, 13):
        x0 = 10 + (m - 1) * larg + 4
        cx = x0 + (larg - 8) / 2
        if m in ind:
            dev = ind[m] - 1
            h = abs(dev) / amp * 55
            yb = mid - h if dev >= 0 else mid
            out.append(f"<rect x='{x0:.1f}' y='{yb:.1f}' width='{larg - 8:.1f}' height='{max(h, 1):.1f}' fill='{couleur}' rx='2'/>")
            ty = yb - 4 if dev >= 0 else yb + h + 12
            out.append(f"<text x='{cx:.1f}' y='{ty:.1f}' text-anchor='middle'>{fr(dev * 100)}</text>")
        out.append(f"<text x='{cx:.1f}' y='{H - 4}' text-anchor='middle'>{MOIS[m - 1]}</text>")
    out.append("</svg>")
    return "".join(out)


def tableau_communes(stats: pd.DataFrame, type_local: str, limite=20) -> str:
    s = stats[(stats["type_local"] == type_local) & stats["fiable"].astype(bool) & stats["dans_budget"].astype(bool)].head(limite)
    if s.empty:
        return "<p class='doux'>Aucune commune avec un échantillon fiable.</p>"
    lignes = []
    for _, r in s.iterrows():
        lignes.append(
            f"<tr><td>{e(r['nom_commune'])}</td><td>{r['prix_m2_median']:.0f}</td><td>{int(r['n_ventes'])}</td>"
            f"<td class='{classe_evo(r['evolution_12m'])}'>{pct(r['evolution_12m'])}</td>"
            f"<td title='{e(r['loyer_origine'])}'>{fr(r['loyer_m2'])}</td><td>{fr(r['rendement_brut'] * 100)} %</td></tr>")
    return ("<div class='defil'><table><thead><tr><th>Commune</th><th>€/m²</th><th>Ventes</th><th>Évol. 12 m</th>"
            "<th>Loyer €/m²</th><th>Rend. brut</th></tr></thead><tbody>" + "".join(lignes) + "</tbody></table></div>")


def section_opportunites(opp: pd.DataFrame) -> str:
    if opp.empty:
        return "<p class='doux'>Aucune annonce analysée pour le moment.</p>"
    bonnes = opp[opp["opportunite"].astype(str) == "True"]
    if bonnes.empty:
        return f"<p>Aucune opportunité parmi les {len(opp)} annonce(s) analysée(s).</p>"
    lignes = []
    for _, r in bonnes.iterrows():
        url = str(r["url"])
        lien = f"<a href='{e(url)}' rel='noopener noreferrer'>voir</a>" if url.startswith(("http://", "https://")) else ""
        lignes.append(
            f"<tr><td>{e(r['commune'])}</td><td>{e(r['type_local'])}</td><td>{r['surface']:.0f} m²</td><td>{r['prix']:.0f} €</td>"
            f"<td>{pct(r['ecart'])}</td><td>{fr(r['rendement_net'] * 100)} %</td><td>{lien}</td></tr>")
    return (f"<p>{len(bonnes)} opportunité(s) sur {len(opp)} annonce(s) analysée(s).</p><div class='defil'><table><thead><tr>"
            "<th>Commune</th><th>Type</th><th>Surface</th><th>Prix</th><th>Écart DVF</th><th>Rend. net</th><th></th></tr></thead><tbody>"
            + "".join(lignes) + "</tbody></table></div>")


def generer_page(data_dir, sortie) -> str:
    data = Path(data_dir)
    meta = {}
    if (data / "meta.json").exists():
        meta = json.loads((data / "meta.json").read_text(encoding="utf-8"))
    tend, saison = lire(data, "tendance.csv"), lire(data, "saisonnalite.csv")
    serie, stats, opp = lire(data, "tendance_mensuelle.csv"), lire(data, "marche_communes.csv"), lire(data, "opportunites.csv")

    cartes = []
    for _, r in tend.iterrows():
        cartes.append(
            f"<div class='carte'><h3>{e(r['type_local'])}</h3><div class='gros'>{r['prix_m2']:.0f} €/m²</div>"
            f"<div class='doux'>{int(r['n_ventes'])} ventes sur 12 mois</div>"
            f"<p>12 mois : <b class='{classe_evo(r['evo12'])}'>{pct(r['evo12'])}</b> &middot; "
            f"6 mois : <b class='{classe_evo(r['evo6'])}'>{pct(r['evo6'])}</b></p>"
            f"<p class='doux'>{e(r['lecture'])}</p></div>")
    types = [t for t in ("Appartement", "Maison") if not stats.empty and t in set(stats["type_local"])]
    saisons = "".join(f"<div class='carte'><h3>{e(t)}</h3>{barres(saison, t)}</div>" for t in types)
    classements = "".join(f"<h3>{e(t)}</h3>{tableau_communes(stats, t)}" for t in types)
    crit = ""
    if meta.get("budget_max") or meta.get("surface_min"):
        crit = f"<p class='doux'>Critères : budget max {meta.get('budget_max', 0):.0f} €, surface min {meta.get('surface_min', 0):.0f} m².</p>"

    page = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Radar immobilier</title><style>{CSS}</style></head><body><main>
<h1>Radar immobilier</h1>
<p class="doux">{e(meta.get('zone', ''))} &middot; dernière vente DVF : {e(meta.get('derniere_vente', 'n/d'))}</p>
<p class="doux">Indicateurs statistiques calculés sur les ventes réelles (DVF). Ce n'est pas un conseil en investissement.</p>
<h2>Tendance du prix</h2>
<div class="grille">{''.join(cartes) or "<p class='doux'>Pas assez de ventes pour établir une tendance.</p>"}</div>
<div class="carte">{courbe(serie)}</div>
<h2>Saisonnalité</h2>
<p class="doux">Écart moyen, en %, du prix médian de chaque mois par rapport à la médiane de son année. Une barre vers le bas indique un mois historiquement moins cher.</p>
<div class="grille">{saisons or "<p class='doux'>Historique insuffisant.</p>"}</div>
<h2>Classement des communes</h2>
<p class="doux">Par rendement brut indicatif, communes à échantillon fiable. Survole le loyer pour voir son origine.</p>{crit}
<div class="carte">{classements}</div>
<h2>Opportunités en cours</h2>
<div class="carte">{section_opportunites(opp)}</div>
<p class="doux">Données : DVF (Etalab, Licence Ouverte) et carte des loyers ANIL (Licence Ouverte 2.0). Page régénérée à chaque exécution du workflow.</p>
</main></body></html>
"""
    sortie = Path(sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(page, encoding="utf-8")
    return page


if __name__ == "__main__":
    racine = Path(__file__).resolve().parent.parent
    generer_page(racine / "data", racine / "docs" / "index.html")
