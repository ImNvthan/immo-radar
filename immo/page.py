"""Génère docs/index.html : page statique autonome (aucune ressource externe) à partir de data/.

Direction visuelle : un radar. Hero bleu Klein aux chiffres géants, saisonnalité tracée en radar polaire
à 12 branches (un mois par branche), classement des communes en barres de rendement.
"""
import html
import json
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from immo.departements import NOMS  # noqa: E402

MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
TYPES = ("Appartement", "Maison")

CSS = """
:root{--papier:#eef1f8;--carte:#fff;--encre:#0c1030;--doux:#575d85;--trait:#d9deee;--bleu:#1b2bff;--ligne:#1b2bff;
--signal:#ff5b2e;--menthe:#0b8f6f;--menthe-fond:#c6f2e2;--signal-fond:#ffe0d6;
--display:"Segoe UI Variable Display","SF Pro Display","Helvetica Neue",Inter,"Segoe UI",system-ui,sans-serif;
--mono:ui-monospace,"SF Mono","Cascadia Mono",Consolas,monospace}
@media (prefers-color-scheme:dark){:root{--papier:#0a0d26;--carte:#12163a;--encre:#edefff;--doux:#98a0d0;--trait:#262c5e;
--ligne:#7f8bff;--menthe:#4fe0b8;--menthe-fond:#0e3b34;--signal-fond:#4a1f14}}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--papier);color:var(--encre);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
.mono{font-family:var(--mono);font-size:.76rem;letter-spacing:.08em;text-transform:uppercase}
a{color:inherit}
:focus-visible{outline:3px solid var(--signal);outline-offset:3px;border-radius:4px}
.wrap{max-width:1040px;margin:0 auto;padding:0 20px}

/* hero */
.hero{position:relative;overflow:hidden;background:var(--bleu);color:#fff;padding:28px 0 56px;isolation:isolate}
.hero .radar-bg{position:absolute;right:-18vmin;top:-14vmin;width:78vmin;height:78vmin;z-index:-1;opacity:.55}
.hero .radar-bg .sweep{transform-origin:50% 50%;animation:tour 9s linear infinite}
@keyframes tour{to{transform:rotate(360deg)}}
.hero .haut{display:flex;flex-wrap:wrap;gap:12px 24px;justify-content:space-between;align-items:center;margin-bottom:clamp(36px,9vw,84px)}
.marque{font-family:var(--display);font-weight:800;letter-spacing:-.02em;font-size:1.1rem;display:flex;align-items:center;gap:10px}
.marque i{width:14px;height:14px;border-radius:50%;background:var(--signal);box-shadow:0 0 0 5px rgba(255,255,255,.25)}
.commutateur{display:inline-flex;background:rgba(255,255,255,.16);border-radius:999px;padding:4px}
.commutateur[hidden]{display:none}
.commutateur button{font:inherit;font-weight:700;border:0;background:transparent;color:#fff;padding:8px 18px;border-radius:999px;cursor:pointer}
.commutateur button[aria-pressed=true]{background:#fff;color:var(--bleu)}
.zone{opacity:.85;margin:0 0 14px}
.hero h1{font-family:var(--display);font-weight:800;letter-spacing:-.045em;line-height:.95;font-size:clamp(2.6rem,9vw,5.8rem);margin:0 0 .25em;max-width:12em}
.prix{font-family:var(--display);font-weight:800;letter-spacing:-.06em;line-height:.85;font-size:clamp(4.4rem,22vw,11.5rem);font-variant-numeric:tabular-nums;margin:.1em 0 .05em}
.prix small{font-size:.22em;letter-spacing:-.02em;font-weight:700;margin-left:.15em;opacity:.8}
.puces{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0}
.puce{border:1.5px solid rgba(255,255,255,.55);border-radius:999px;padding:6px 14px;font-weight:700;font-variant-numeric:tabular-nums}
.puce em{font-style:normal;font-weight:500;opacity:.8;margin-right:.4em}
.puce.hausse{background:var(--signal);border-color:var(--signal)}
.puce.baisse{background:#c6f2e2;border-color:#c6f2e2;color:#06503e}
.lecture{max-width:34em;font-size:1.1rem;opacity:.92;margin:0}

/* sections */
section.bloc{padding:clamp(44px,8vw,84px) 0 0}
h2{font-family:var(--display);font-weight:800;letter-spacing:-.035em;line-height:1;font-size:clamp(1.9rem,5vw,3rem);margin:.15em 0 .3em}
.intro{color:var(--doux);max-width:36em;margin:0 0 28px}
.carte{background:var(--carte);border:1px solid var(--trait);border-radius:24px;padding:clamp(16px,3vw,32px)}
svg{display:block;width:100%;height:auto}
svg text{font-family:var(--mono);font-size:13px;fill:var(--doux)}
.legende{color:var(--doux);font-size:.9rem;margin:10px 0 0}

/* radar de saisonnalité */
.saison{display:grid;gap:24px;grid-template-columns:1fr;align-items:center}
@media(min-width:800px){.saison{grid-template-columns:1.1fr 1fr}}
.radar .anneau{fill:none;stroke:var(--trait);stroke-width:1}
.radar .base{fill:none;stroke:var(--doux);stroke-width:1.2;stroke-dasharray:4 5}
.radar .branche{stroke:var(--trait);stroke-width:1}
.radar .forme{fill:var(--bleu);fill-opacity:.16;stroke:var(--ligne);stroke-width:3;stroke-linejoin:round}
.radar .balai{transform-origin:50% 50%;transform-box:view-box;animation:tour 14s linear infinite}
.radar .bas{fill:var(--menthe)}.radar .haut{fill:var(--signal)}
.radar .pt{fill:var(--ligne)}
.radar text.m{font-size:14px}
.radar text.fort{fill:var(--encre);font-weight:700}
.mois-cles{display:grid;gap:12px}
.mois-cle{border-radius:18px;padding:16px 18px}
.mois-cle.achat{background:var(--menthe-fond)}
.mois-cle.cher{background:var(--signal-fond)}
.mois-cle b{font-family:var(--display);font-weight:800;font-size:1.8rem;letter-spacing:-.03em;display:block;line-height:1.1}
.mois-cle p{margin:.2em 0 0;color:var(--doux)}

/* communes */
.communes{list-style:none;margin:0;padding:0}
.commune{display:grid;grid-template-columns:1fr auto;gap:4px 16px;padding:14px 0;border-bottom:1px solid var(--trait)}
.commune:last-child{border-bottom:0}
.commune .nom{font-weight:700;font-size:1.05rem}
.commune .rend{font-family:var(--display);font-weight:800;font-size:1.5rem;letter-spacing:-.03em;text-align:right;font-variant-numeric:tabular-nums}
.commune .barre{grid-column:1/-1;height:10px;border-radius:99px;background:var(--trait);overflow:hidden}
.commune .barre i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,var(--bleu),var(--ligne))}
.commune .det{grid-column:1/-1;color:var(--doux);font-size:.88rem;display:flex;flex-wrap:wrap;gap:2px 16px;font-variant-numeric:tabular-nums}
.tag{font-weight:700}.tag.hausse{color:var(--signal)}.tag.baisse{color:var(--menthe)}

/* opportunités */
.opps{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.opp{background:var(--carte);border:1px solid var(--trait);border-radius:22px;padding:20px;display:flex;flex-direction:column;gap:6px}
.opp .decote{font-family:var(--display);font-weight:800;font-size:3rem;letter-spacing:-.05em;line-height:1;color:var(--menthe)}
.opp .lieu{font-weight:700}
.opp a.voir{margin-top:auto;font-weight:700;text-decoration:none;background:var(--bleu);color:#fff;border-radius:999px;padding:10px 18px;text-align:center}
.vide{border:2px dashed var(--trait);border-radius:22px;padding:28px;color:var(--doux)}
.vide b{color:var(--encre);display:block;font-size:1.15rem;margin-bottom:4px}

footer{padding:56px 0 48px;color:var(--doux);font-size:.88rem}
footer p{max-width:46em}

/* commutateur : sans JavaScript, tout reste visible */
body[data-type="Appartement"] [data-for]:not([data-for="Appartement"]),
body[data-type="Maison"] [data-for]:not([data-for="Maison"]){display:none}

/* interactivité (visible uniquement avec JavaScript) */
.js-only{display:none}.js .js-only{display:block}.js .statique{display:none}
.criteres{margin-top:-28px;position:relative;z-index:2}
.champs{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.champ{display:flex;flex-direction:column;gap:6px}
.champ label{font-family:var(--mono);font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--doux)}
.champ input,.champ select{font:inherit;font-size:1.05rem;color:var(--encre);background:var(--papier);border:1.5px solid var(--trait);border-radius:14px;padding:12px 14px;width:100%;min-height:48px}
.champ input:focus,.champ select:focus{border-color:var(--bleu);outline:none;box-shadow:0 0 0 3px rgba(27,43,255,.25)}
.champ.case{flex-direction:row;align-items:center;gap:10px;min-height:48px;align-self:end}
.champ.case input{width:22px;min-height:22px;height:22px;accent-color:var(--bleu)}
.champ.case label{text-transform:none;font-family:inherit;font-size:1rem;letter-spacing:0;color:var(--encre)}
.actions{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-top:18px}
button.btn{font:inherit;font-weight:700;border:0;background:var(--bleu);color:#fff;padding:13px 24px;border-radius:999px;cursor:pointer;min-height:48px}
button.btn:disabled{opacity:.4;cursor:not-allowed}
button.btn.sec{background:transparent;color:var(--encre);border:1.5px solid var(--trait)}
.note{color:var(--doux);font-size:.88rem;margin:12px 0 0}
.etoile{border:0;background:transparent;color:var(--signal);font-size:1.3rem;line-height:1;cursor:pointer;padding:2px 8px;margin-left:4px;min-width:36px;min-height:36px}
#compte-communes{color:var(--doux);margin:0 0 6px}
.resultat{margin-top:22px}
.verdict{border-radius:18px;padding:16px 20px;background:var(--trait);margin-bottom:14px;font-size:1.1rem}
.verdict.oui{background:var(--menthe-fond)}.verdict.non{background:var(--signal-fond)}
.chiffres{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:0}
.chiffres div{background:var(--papier);border-radius:16px;padding:14px 16px}
.chiffres dt{font-family:var(--mono);font-size:.7rem;letter-spacing:.06em;text-transform:uppercase;color:var(--doux)}
.chiffres dd{margin:6px 0 0;font-family:var(--display);font-weight:800;font-size:1.6rem;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.chiffres dd small{display:block;font-family:system-ui,sans-serif;font-size:.75rem;font-weight:500;letter-spacing:0;color:var(--doux)}
.chiffres dd.hausse{color:var(--signal)}.chiffres dd.baisse{color:var(--menthe)}
.opp.top{border:2px solid var(--menthe)}
.opp .decote.cher{color:var(--signal)}
.opp .suppr{font:inherit;font-size:.85rem;background:transparent;border:0;color:var(--doux);text-decoration:underline;cursor:pointer;padding:6px 0;text-align:left}
.sous-titre{font-family:var(--display);font-weight:800;letter-spacing:-.03em;font-size:1.5rem;margin:40px 0 14px}
.reglages-sec{margin-top:14px}
.reglages summary{cursor:pointer;font-weight:700;font-size:1.1rem;min-height:32px}
.reglages .sous-titre{margin:24px 0 12px;font-size:1.2rem}
.champ .aide{line-height:1.35}
.ovl{grid-column:1/-1;display:flex;align-items:center;gap:10px;color:var(--doux);font-size:.85rem;flex-wrap:wrap}
.ovl input{width:110px;font:inherit;color:var(--encre);background:var(--papier);border:1.5px solid var(--trait);border-radius:10px;padding:6px 10px}
.coller{margin-top:14px}
.aide{color:var(--doux);font-size:.85rem}
.coller summary{cursor:pointer;font-weight:700;font-size:1.1rem;min-height:32px}
.coller[open] summary{margin-bottom:12px}
.champ textarea{font:inherit;color:var(--encre);background:var(--papier);border:1.5px solid var(--trait);border-radius:14px;padding:12px 14px;width:100%;resize:vertical}
.champ textarea:focus{border-color:var(--bleu);outline:none;box-shadow:0 0 0 3px rgba(27,43,255,.25)}
@media (prefers-reduced-motion:reduce){.hero .radar-bg .sweep,.radar .balai{animation:none}html{scroll-behavior:auto}}
"""

JS = (Path(__file__).parent / "page.js").read_text(encoding="utf-8")


def e(x):
    return html.escape(str(x), quote=True)


def fr(x, nd=1):
    return f"{x:.{nd}f}".replace(".", ",")


def entier(x):
    return f"{x:,.0f}".replace(",", " ")


def pct(x):
    return "n/d" if x is None or pd.isna(x) else f"{x * 100:+.1f} %".replace(".", ",")


def classe_evo(x):
    """Une hausse des prix est défavorable à l'acheteur, une baisse lui est favorable."""
    if x is None or pd.isna(x):
        return ""
    return "hausse" if x > 0.02 else "baisse" if x < -0.02 else ""


def verdict(evo12, evo6) -> str:
    if evo12 is None or pd.isna(evo12):
        return "Tendance encore floue."
    if evo12 < -0.02 and (evo6 is None or pd.isna(evo6) or evo6 < 0.01):
        return "Les prix reculent."
    if evo12 > 0.02 and (evo6 is None or pd.isna(evo6) or evo6 > -0.01):
        return "Les prix montent."
    return "Le marché est stable."


def lire(data, nom):
    chemin = Path(data) / nom
    if not chemin.exists() or chemin.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(chemin)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


# ----------------------------------------------------------------------------
# Graphiques SVG
# ----------------------------------------------------------------------------

def fond_radar() -> str:
    """Anneaux concentriques et faisceau tournant, décor du hero."""
    anneaux = "".join(f"<circle cx='200' cy='200' r='{r}' fill='none' stroke='#fff' stroke-opacity='.35'/>" for r in (50, 100, 150, 195))
    axes = "<path d='M200 5V395M5 200H395' stroke='#fff' stroke-opacity='.25'/>"
    return (f"<svg class='radar-bg' viewBox='0 0 400 400' aria-hidden='true'><defs><linearGradient id='faisceau' x1='0' y1='0' x2='1' y2='0'>"
            f"<stop offset='0' stop-color='#fff' stop-opacity='0'/><stop offset='1' stop-color='#fff' stop-opacity='.55'/></linearGradient></defs>"
            f"{anneaux}{axes}<g class='sweep'><path d='M200 200L395 200A195 195 0 0 0 331 62Z' fill='url(#faisceau)' transform='rotate(-35 200 200)'/></g></svg>")


def courbe(serie: pd.DataFrame, type_local: str, idx: int) -> str:
    s = serie[serie["type_local"] == type_local].sort_values("mois") if not serie.empty else serie
    if s.empty or len(s) < 2:
        return "<p class='legende'>Pas assez de ventes pour tracer la courbe.</p>"
    L, H, g, d, b = 640, 270, 56, 16, 34
    mois = list(s["mois"])
    vals = list(s["prix_m2_median"])
    lo, hi = min(vals), max(vals)
    marge = max((hi - lo) * 0.15, 1)
    lo, hi = lo - marge, hi + marge

    def x(i):
        return g + (L - g - d) * i / (len(mois) - 1)

    def y(v):
        return H - b - (H - b - 14) * (v - lo) / (hi - lo)

    pts = [(x(i), y(v)) for i, v in enumerate(vals)]
    ligne = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    aire = f"{pts[0][0]:.1f},{H - b} {ligne} {pts[-1][0]:.1f},{H - b}"
    out = [f"<svg viewBox='0 0 {L} {H}' role='img' aria-label='Prix médian au m² par mois, {e(type_local)}'>",
           f"<defs><linearGradient id='aire{idx}' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='var(--ligne)' stop-opacity='.35'/>"
           f"<stop offset='1' stop-color='var(--ligne)' stop-opacity='0'/></linearGradient></defs>"]
    for k in range(4):
        v = lo + (hi - lo) * k / 3
        out.append(f"<line x1='{g}' x2='{L - d}' y1='{y(v):.1f}' y2='{y(v):.1f}' stroke='var(--trait)'/>")
        out.append(f"<text x='{g - 8}' y='{y(v) + 4:.1f}' text-anchor='end'>{entier(v)}</text>")
    pas = max(len(mois) // 6, 1)
    for i in range(0, len(mois), pas):
        m = mois[i]
        out.append(f"<text x='{x(i):.1f}' y='{H - 10}' text-anchor='middle'>{e(m[5:7] + '/' + m[2:4])}</text>")
    out.append(f"<polygon points='{aire}' fill='url(#aire{idx})'/>")
    out.append(f"<polyline points='{ligne}' fill='none' stroke='var(--ligne)' stroke-width='3.5' stroke-linejoin='round' stroke-linecap='round'/>")
    out.append(f"<circle cx='{pts[-1][0]:.1f}' cy='{pts[-1][1]:.1f}' r='6' fill='var(--signal)'/>")
    out.append("</svg>")
    return "".join(out)


def radar_saison(saison: pd.DataFrame, type_local: str):
    """Radar polaire à 12 branches : distance au centre = indice de prix du mois. Renvoie (svg, mois_bas, mois_haut)."""
    s = saison[saison["type_local"] == type_local] if not saison.empty else saison
    if s.empty:
        return "<p class='legende'>Historique insuffisant pour la saisonnalité.</p>", None, None
    ind = {int(m): float(i) for m, i in zip(s["mois"], s["indice"])}
    amp = max(max(abs(v - 1) for v in ind.values()), 0.01)
    C, R = 210, 150
    base = 0.55

    def pol(m, rayon):
        a = -math.pi / 2 + (m - 1) * math.pi / 6
        return C + rayon * math.cos(a), C + rayon * math.sin(a)

    def rayon(i):
        return R * (base + 0.42 * (i - 1) / amp)

    bas, haut = min(ind, key=ind.get), max(ind, key=ind.get)
    out = [f"<svg class='radar' viewBox='0 0 {2 * C} {2 * C}' role='img' aria-label='Saisonnalité des prix, {e(type_local)}'>"]
    for f in (0.25, 0.55, 1.0):
        out.append(f"<circle class='{'base' if f == 0.55 else 'anneau'}' cx='{C}' cy='{C}' r='{R * f:.1f}'/>")
    for m in range(1, 13):
        x2, y2 = pol(m, R)
        out.append(f"<line class='branche' x1='{C}' y1='{C}' x2='{x2:.1f}' y2='{y2:.1f}'/>")
    out.append(f"<g class='balai'><path d='M{C} {C}L{C + R} {C}A{R} {R} 0 0 0 {C + R * math.cos(-0.5):.1f} {C + R * math.sin(-0.5):.1f}Z' fill='var(--bleu)' fill-opacity='.10'/></g>")
    pts = [pol(m, rayon(ind[m])) for m in sorted(ind)]
    if len(pts) >= 3:
        out.append("<polygon class='forme' points='" + " ".join(f"{px:.1f},{py:.1f}" for px, py in pts) + "'/>")
    for m in range(1, 13):
        lx, ly = pol(m, R + 24)
        fort = "m fort" if m in (bas, haut) else "m"
        out.append(f"<text class='{fort}' x='{lx:.1f}' y='{ly + 5:.1f}' text-anchor='middle'>{MOIS[m - 1]}</text>")
        if m in ind:
            px, py = pol(m, rayon(ind[m]))
            cls = "bas" if m == bas else "haut" if m == haut else "pt"
            out.append(f"<circle class='{cls}' cx='{px:.1f}' cy='{py:.1f}' r='{8 if m in (bas, haut) else 4.5}'/>")
    out.append("</svg>")
    return "".join(out), (bas, ind[bas] - 1), (haut, ind[haut] - 1)


# ----------------------------------------------------------------------------
# Blocs de page
# ----------------------------------------------------------------------------

def bloc_hero(tend, meta, types) -> str:
    boutons = "".join(f"<button type='button' data-type='{e(t)}' aria-pressed='false'>{e(t)}s</button>" for t in types)
    blocs = []
    for t in types:
        r = tend[tend["type_local"] == t]
        if r.empty:
            blocs.append(f"<div data-for='{e(t)}'><h1>Pas assez de ventes.</h1><p class='lecture'>Le {e(t.lower())} n'a pas assez de ventes dans la zone pour établir une tendance.</p></div>")
            continue
        r = r.iloc[0]
        blocs.append(
            f"<div data-for='{e(t)}'><h1>{e(verdict(r['evo12'], r['evo6']))}</h1>"
            f"<div class='prix'>{entier(r['prix_m2'])}<small>€/m²</small></div>"
            f"<p class='mono zone'>prix médian du {e(t.lower())} &middot; {int(r['n_ventes'])} ventes sur 12 mois</p>"
            f"<div class='puces'><span class='puce {classe_evo(r['evo12'])}'><em>12 mois</em>{pct(r['evo12'])}</span>"
            f"<span class='puce {classe_evo(r['evo6'])}'><em>6 mois</em>{pct(r['evo6'])}</span></div>"
            f"<p class='lecture'>{e(r['lecture'])}</p></div>")
    return (f"<header class='hero'>{fond_radar()}<div class='wrap'><div class='haut'><div class='marque'><i></i>Radar immobilier</div>"
            f"<div class='commutateur' role='group' aria-label='Type de bien' hidden>{boutons}</div></div>"
            f"<p class='mono zone'>{e(meta.get('zone', ''))} &middot; dernière vente connue {e(meta.get('derniere_vente', 'n/d'))}</p>"
            f"{''.join(blocs)}</div></header>")


def bloc_courbe(serie, types) -> str:
    cartes = "".join(f"<div class='carte' data-for='{e(t)}'>{courbe(serie, t, i)}</div>" for i, t in enumerate(types))
    return ("<section class='bloc'><div class='wrap'><p class='mono'>Tendance</p><h2>Le prix, mois après mois</h2>"
            "<p class='intro'>Prix médian au m² des ventes signées, regroupées par mois de vente sur les trois dernières années. Le point orange marque le dernier mois connu.</p>"
            f"{cartes}</div></section>")


def bloc_saison(saison, types) -> str:
    cartes = []
    for t in types:
        svg, bas, haut = radar_saison(saison, t)
        if bas is None:
            cartes.append(f"<div class='carte' data-for='{e(t)}'>{svg}</div>")
            continue
        cartes.append(
            f"<div class='carte saison' data-for='{e(t)}'><div>{svg}</div><div class='mois-cles'>"
            f"<div class='mois-cle achat'><span class='mono'>Mois le moins cher</span><b>{e(MOIS[bas[0] - 1])}</b><p>{fr(bas[1] * 100)} % par rapport à la médiane de l'année.</p></div>"
            f"<div class='mois-cle cher'><span class='mono'>Mois le plus cher</span><b>{e(MOIS[haut[0] - 1])}</b><p>+{fr(haut[1] * 100)} % par rapport à la médiane de l'année.</p></div>"
            f"<p class='legende'>Plus un mois s'éloigne du centre, plus les prix y sont élevés. Le cercle en pointillés marque la médiane annuelle.</p></div></div>")
    return ("<section class='bloc'><div class='wrap'><p class='mono'>Saisonnalité</p><h2>Le bon mois pour acheter</h2>"
            "<p class='intro'>Écart moyen du prix médian de chaque mois à celui de son année, calculé sur plusieurs années de ventes.</p>"
            f"{''.join(cartes)}</div></section>")


def liste_communes(stats, t, limite=15) -> str:
    if stats.empty:
        return "<p class='legende'>Aucune donnée.</p>"
    s = stats[(stats["type_local"] == t) & stats["fiable"].astype(bool) & stats["dans_budget"].astype(bool)].head(limite)
    if s.empty:
        return "<p class='legende'>Aucune commune avec un échantillon fiable.</p>"
    mx = max(float(s["rendement_brut"].max()), 0.0001)
    lignes = []
    for _, r in s.iterrows():
        lignes.append(
            f"<li class='commune'><span class='nom'>{e(r['nom_commune'])}</span><span class='rend'>{fr(r['rendement_brut'] * 100)}&nbsp;%</span>"
            f"<span class='barre'><i style='width:{r['rendement_brut'] / mx * 100:.0f}%'></i></span>"
            f"<span class='det'><span>{entier(r['prix_m2_median'])} €/m²</span><span>{int(r['n_ventes'])} ventes</span>"
            f"<span class='tag {classe_evo(r['evolution_12m'])}'>{pct(r['evolution_12m'])} sur 12 mois</span>"
            f"<span>loyer {fr(r['loyer_m2'])} €/m² ({e(r['loyer_origine'])})</span></span></li>")
    return f"<ol class='communes'>{''.join(lignes)}</ol>"


def bloc_communes(stats, types, meta) -> str:
    crit = ""
    if meta.get("budget_max") or meta.get("surface_min"):
        crit = f" Critères appliqués : budget maximum {entier(meta.get('budget_max', 0))} €, surface minimale {entier(meta.get('surface_min', 0))} m²."
    cartes = "".join(f"<div class='carte statique' data-for='{e(t)}'>{liste_communes(stats, t)}</div>" for t in types)
    return ("<section class='bloc' id='communes'><div class='wrap'><p class='mono'>Communes</p><h2>Où le rendement est le plus fort</h2>"
            "<p class='intro'>Classement par rendement brut indicatif, communes à échantillon fiable uniquement. La barre compare les communes entre elles. "
            f"Ajuste tes critères en haut de page : la liste se met à jour tout de suite.{e(crit)}</p>{cartes}"
            "<div class='carte js-only'><p id='compte-communes' aria-live='polite'></p><div id='liste-communes'></div></div></div></section>")


def bloc_criteres(meta) -> str:
    return ("<section class='criteres js-only' aria-label='Mes critères'><div class='wrap'><div class='carte'>"
            "<p class='mono'>Mes critères</p>"
            "<div class='champs'>"
            "<div class='champ'><label for='c-budget'>Budget maximum (€)</label><input id='c-budget' type='number' inputmode='numeric' min='0' step='any' placeholder='Sans limite'></div>"
            "<div class='champ'><label for='c-surface'>Surface minimale (m²)</label><input id='c-surface' type='number' inputmode='numeric' min='0' step='any' placeholder='Sans minimum'></div>"
            "<div class='champ'><label for='c-q'>Chercher une commune</label><input id='c-q' type='search' autocomplete='off' placeholder='Le Mans, La Flèche…'></div>"
            "<div class='champ'><label for='c-tri'>Trier par</label><select id='c-tri'><option value='rendement'>Rendement brut</option>"
            "<option value='prix'>Prix au m² le plus bas</option><option value='evolution'>Baisse de prix sur 12 mois</option><option value='ventes'>Nombre de ventes</option></select></div>"
            "<div class='champ case'><input id='c-fav' type='checkbox'><label for='c-fav'>Mes favoris seulement</label></div>"
            "</div><div class='actions'><button type='button' class='btn sec' id='c-reset'>Effacer les critères</button></div>"
            "<p class='note'>Avec un budget et une surface minimale, seules les communes où un tel bien reste dans ton budget sont gardées. "
            "Tes critères, tes favoris et tes annonces restent sur cet appareil : rien n'est envoyé.</p></div></div></section>")


def champ_reglage(ident, libelle, aide, pas="any", mini="0"):
    return (f"<div class='champ'><label for='{ident}'>{libelle}</label>"
            f"<input id='{ident}' type='number' inputmode='decimal' min='{mini}' step='{pas}'><small class='aide'>{aide}</small></div>")


def bloc_reglages(meta, prefixe="") -> str:
    courant = (meta.get("departements") or [""])[0]
    options = "".join(f"<option value='{e(c)}'{' selected' if c == courant else ''}>{e(n)} ({e(c)})</option>" for c, n in sorted(NOMS.items(), key=lambda kv: kv[1]))
    return ("<section class='reglages-sec js-only' aria-label='Réglages'><div class='wrap'><details class='carte reglages'>"
            "<summary>Tous les réglages</summary>"
            "<p class='intro'>Chaque réglage s'applique tout de suite au classement et à l'analyse d'annonces, et reste mémorisé sur cet appareil. "
            "Les valeurs de départ viennent de la configuration du radar.</p>"
            "<h3 class='sous-titre'>Zone</h3><div class='champs'>"
            f"<div class='champ'><label for='r-dep'>Département</label><select id='r-dep' data-prefixe='{e(prefixe)}'>{options}</select>"
            "<small class='aide'>Ouvre la page du département choisi (prix, tendance et saisonnalité propres).</small></div></div>"
            "<h3 class='sous-titre'>Fiabilité et loyers</h3><div class='champs'>"
            + champ_reglage("r-min", "Ventes minimales par commune", "En dessous, la commune est jugée peu fiable et masquée.", "1", "1")
            + champ_reglage("r-coef", "Part du loyer officiel retenue (%)", "La carte ANIL donne des loyers charges comprises : 90 % par défaut.", "1")
            + champ_reglage("r-lapp", "Loyer par défaut, appartement (€/m²)", "Utilisé si la carte officielle n'a pas la commune.", "0.1")
            + champ_reglage("r-lmai", "Loyer par défaut, maison (€/m²)", "Même usage pour les maisons.", "0.1")
            + "</div><h3 class='sous-titre'>Annonces</h3><div class='champs'>"
            + champ_reglage("r-marge", "Marge de négociation (%)", "Remise moyenne supposée entre prix affiché et prix signé.", "0.5")
            + champ_reglage("r-decote", "Décote minimale (%)", "Écart sous la médiane pour parler d'opportunité.", "0.5")
            + champ_reglage("r-rend", "Rendement net minimal (%)", "Rendement net estimé minimal pour une opportunité.", "0.1")
            + champ_reglage("r-charges", "Charges et vacance (%)", "Part du loyer perdue en charges, taxe foncière et vacance.", "1")
            + "</div><div class='actions'><button type='button' class='btn sec' id='r-reset'>Revenir aux valeurs de départ</button></div>"
            "<p class='note'>Pas modifiables ici : les alertes Telegram et l'import e-mail. Ils utilisent des secrets qui doivent rester privés et se règlent dans GitHub.</p>"
            "</details></div></section>")


def bloc_analyseur() -> str:
    return ("<section class='bloc js-only' id='analyseur'><div class='wrap'><p class='mono'>Annonce</p><h2>Teste une annonce</h2>"
            "<p class='intro'>Recopie le prix et la surface d'une annonce vue ailleurs. Le radar la compare aux ventes réelles de la commune et estime le rendement net.</p>"
            "<div class='carte'><form id='form-annonce' autocomplete='off'><div class='champs'>"
            "<div class='champ'><label for='a-type'>Type de bien</label><select id='a-type'></select></div>"
            "<div class='champ'><label for='a-commune'>Commune</label><input id='a-commune' list='liste-noms' placeholder='Commence à taper…'></div>"
            "<div class='champ'><label for='a-surface'>Surface (m²)</label><input id='a-surface' type='number' inputmode='decimal' min='0' step='any'></div>"
            "<div class='champ'><label for='a-prix'>Prix affiché (€)</label><input id='a-prix' type='number' inputmode='numeric' min='0' step='any'></div>"
            "<div class='champ'><label for='a-loyer'>Loyer visé (€/m², facultatif)</label><input id='a-loyer' type='number' inputmode='decimal' min='0' step='any' placeholder='Loyer du marché'></div>"
            "<div class='champ'><label for='a-url'>Lien de l'annonce</label><input id='a-url' type='url' placeholder='https://…'><small id='url-aide' class='aide' aria-live='polite'></small></div>"
            "</div><datalist id='liste-noms'></datalist>"
            "<div id='resultat' class='resultat' aria-live='polite'></div>"
            "<div class='actions'><button type='submit' class='btn' id='a-enreg' disabled>Enregistrer l'annonce</button></div></form></div>"
            "<details class='carte coller'><summary>Coller plusieurs annonces d'un coup</summary>"
            "<p class='intro'>Copie le texte d'une page de résultats ou d'un e-mail d'alerte reçu des sites d'annonces, puis colle-le ici. "
            "Le radar repère les prix, surfaces et communes de la zone et classe les annonces de la plus forte décote à la plus faible.</p>"
            "<div class='champ'><label for='p-texte'>Texte copié</label><textarea id='p-texte' rows='8' placeholder='Maison 4 pièces, Sablé-sur-Sarthe, 95 m², 189 000 €&#10;https://…'></textarea></div>"
            "<div class='actions'><button type='button' class='btn' id='p-analyser'>Analyser le texte</button></div>"
            "<div id='p-resultats' class='resultat' aria-live='polite'></div></details>"
            "<h3 class='sous-titre'>Mes annonces enregistrées <span id='nb-annonces'></span></h3><div id='mes-annonces'></div></div></section>")


def bloc_opportunites(opp) -> str:
    if opp.empty:
        corps = ("<div class='vide'><b>Aucune annonce suivie automatiquement.</b>Teste une annonce plus haut : elle s'enregistre sur ton appareil. "
                 "L'import par e-mail alimente cette section une fois activé.</div>")
    else:
        bonnes = opp[opp["opportunite"].astype(str) == "True"]
        if bonnes.empty:
            corps = f"<div class='vide'><b>Aucune opportunité pour l'instant.</b>{len(opp)} annonce(s) analysée(s), aucune ne passe les seuils de décote et de rendement.</div>"
        else:
            cartes = []
            for _, r in bonnes.iterrows():
                url = str(r["url"])
                lien = f"<a class='voir' href='{e(url)}' rel='noopener noreferrer'>Voir l'annonce</a>" if url.startswith(("http://", "https://")) else ""
                cartes.append(
                    f"<article class='opp'><span class='decote'>{pct(r['ecart'])}</span><span class='mono'>sous la médiane DVF</span>"
                    f"<span class='lieu'>{e(r['commune'])}</span><span>{e(r['type_local'])} &middot; {r['surface']:.0f} m² &middot; {entier(r['prix'])} €</span>"
                    f"<span>Rendement net estimé {fr(r['rendement_net'] * 100)} %</span>{lien}</article>")
            corps = f"<div class='opps'>{''.join(cartes)}</div>"
    return ("<section class='bloc'><div class='wrap'><p class='mono'>Annonces</p><h2>Annonces suivies par le radar</h2>"
            f"<p class='intro'>Annonces de annonces.csv ou de l'import e-mail dont le prix ressort nettement sous la médiane des ventes de la commune.</p>{corps}</div></section>")


def donnees_js(stats, meta, types) -> dict:
    """Données embarquées pour le filtrage et l'analyse d'annonces côté navigateur."""
    def v(x, nd):
        return None if x is None or pd.isna(x) else round(float(x), nd)

    coef = float(meta.get("loyer_coef") or 1) or 1.0
    communes = []
    if not stats.empty:
        for _, r in stats.iterrows():
            communes.append({
                "c": str(r["nom_commune"]), "k": str(r.get("code_commune", r["nom_commune"])), "t": r["type_local"], "p": v(r["prix_m2_median"], 0),
                "n": int(r["n_ventes"]), "e": v(r["evolution_12m"], 4), "l": v(r["loyer_m2"], 2), "o": str(r["loyer_origine"]),
                "r": v(r["rendement_brut"], 4), "f": bool(r["fiable"]),
                "b": v(float(r["loyer_m2"]) / coef, 3) if str(r["loyer_origine"]).startswith("ANIL") else None,
            })
    seuils = {"marge_negociation": 0.05, "decote_min": 0.08, "rendement_net_min": 0.045, "charges_et_vacance": 0.25}
    seuils.update(meta.get("seuils") or {})
    return {"types": types, "communes": communes, "seuils": seuils,
            "budget_max": meta.get("budget_max", 0) or 0, "surface_min": meta.get("surface_min", 0) or 0,
            "min_ventes": meta.get("min_ventes", 15), "loyer_coef": coef,
            "loyer_defaut": meta.get("loyer_defaut") or {"Appartement": 12.0, "Maison": 10.0}}


def generer_page(data_dir, sortie, prefixe="") -> str:
    data = Path(data_dir)
    meta = {}
    if (data / "meta.json").exists():
        meta = json.loads((data / "meta.json").read_text(encoding="utf-8"))
    tend, saison = lire(data, "tendance.csv"), lire(data, "saisonnalite.csv")
    serie, stats, opp = lire(data, "tendance_mensuelle.csv"), lire(data, "marche_communes.csv"), lire(data, "opportunites.csv")
    if tend.empty:
        tend = pd.DataFrame(columns=["type_local", "prix_m2", "n_ventes", "evo12", "evo6", "lecture"])
    presents = set(tend["type_local"]) | (set(stats["type_local"]) if not stats.empty else set())
    types = [t for t in TYPES if t in presents] or list(TYPES)

    donnees = json.dumps(donnees_js(stats, meta, types), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    page = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="theme-color" content="#1b2bff">
<title>Radar immobilier</title><style>{CSS}</style></head><body>
{bloc_hero(tend, meta, types)}
<main>{bloc_criteres(meta)}{bloc_reglages(meta, prefixe)}{bloc_courbe(serie, types)}{bloc_saison(saison, types)}{bloc_communes(stats, types, meta)}{bloc_analyseur()}{bloc_opportunites(opp)}</main>
<footer><div class="wrap"><p><b>Indicateurs statistiques, pas un conseil en investissement.</b> Les prix viennent des ventes réelles (DVF, Etalab, Licence Ouverte) et les loyers de la carte des loyers ANIL (Licence Ouverte 2.0) ou de config.yml. Page régénérée à chaque exécution du workflow. Tes critères et tes annonces restent dans ton navigateur.</p></div></footer>
<script type="application/json" id="donnees">{donnees}</script>
<script>{JS}</script></body></html>
"""
    sortie = Path(sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(page, encoding="utf-8")
    return page


if __name__ == "__main__":
    racine = Path(__file__).resolve().parent.parent
    generer_page(racine / "data", racine / "docs" / "index.html")
