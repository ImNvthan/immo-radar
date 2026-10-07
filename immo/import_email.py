#!/usr/bin/env python3
"""Importe dans annonces.csv les annonces trouvées dans les e-mails d'alerte d'une boîte dédiée (IMAP).

Aucun scraping : on lit uniquement les e-mails que les sites envoient eux-mêmes à l'utilisateur.
Variables d'environnement : IMAP_HOST, IMAP_USER, IMAP_PASSWORD (mot de passe d'application),
et en option IMAP_FOLDER (INBOX par défaut) et IMAP_PORT (993 par défaut).
Le script ne plante jamais : sans identifiants il s'arrête proprement, et toute erreur est journalisée.
"""
import csv
import email
import imaplib
import logging
import os
import re
import sys
from email import policy
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
COLONNES = ["url", "type_local", "commune", "surface", "prix", "titre"]
DOMAINES = ("leboncoin.fr", "seloger.com", "pap.fr", "bienici.com", "logic-immo.com", "ouestfrance-immo.com", "paruvendu.fr", "superimmo.com")
CHEMINS = ("/ad/", "/annonces/", "/annonce", "/detail", "/vente", "/ventes/", "/classified", "/immobilier")

log = logging.getLogger("immo")

RE_PRIX = re.compile(r"(?<![\w.,])(\d{1,3}(?:[\s  .]\d{3})+|\d{4,8})\s*(?:€|euros?\b|eur\b)", re.I)
RE_SURFACE = re.compile(r"(\d{1,4}(?:[.,]\d{1,2})?)\s*m(?:²|2)", re.I)
# Nom de commune : éventuel article ou "Saint", puis un mot capitalisé, puis des segments reliés par des tirets.
NOM = r"((?:(?:Le|La|Les|Saint|Sainte|St|Ste)[ \-])?[A-ZÀ-Ý][\wÀ-ÿ'’]+(?:-[A-Za-zÀ-ÿ'’]+){0,4})"
RE_COMMUNE_CP = re.compile(NOM + r"\s*\(\s*\d{5}\s*\)")
RE_CP_COMMUNE = re.compile(r"\b\d{5}\s+" + NOM)
RE_COMMUNE_A = re.compile(r"\b(?:à|a|sur)\s+" + NOM)


def url_annonce(url: str) -> str:
    """Normalise un lien d'annonce (sans paramètres de suivi) ou renvoie '' si ce n'est pas une annonce."""
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return ""
    hote = (p.hostname or "").lower()
    if p.scheme not in ("http", "https") or not any(hote == d or hote.endswith("." + d) for d in DOMAINES):
        return ""
    if not any(c in p.path.lower() for c in CHEMINS) or p.path.strip("/") == "":
        return ""
    return urlunsplit((p.scheme, hote, p.path.rstrip("/"), "", ""))


class _Blocs(HTMLParser):
    """Découpe un e-mail HTML en blocs : un bloc par lien d'annonce, avec le texte qui le suit."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocs = []  # liste de [url, [textes]]
        self.courant = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            url = url_annonce(dict(attrs).get("href") or "")
            if url and (self.courant is None or self.courant[0] != url):
                self.courant = [url, []]
                self.blocs.append(self.courant)

    def handle_data(self, data):
        if self.courant is not None and data.strip():
            self.courant[1].append(data.strip())


def type_depuis_texte(texte: str) -> str:
    t = texte.lower()
    if re.search(r"\b(appartement|appart|studio|duplex|loft|t[1-6]\b|f[1-6]\b)", t):
        return "Appartement"
    if re.search(r"\b(maison|pavillon|villa|longère|longere|propriété|fermette)", t):
        return "Maison"
    return ""


def _nombre(s: str) -> float:
    return float(re.sub(r"[\s  ]", "", s).replace(",", ".")) if re.search(r"[,.]\d{1,2}$", s) else float(re.sub(r"[\s  .]", "", s))


def extraire_champs(texte: str) -> dict:
    """Extrait type, commune, surface et prix d'un bloc de texte. Les champs introuvables restent vides."""
    texte = re.sub(r"\s+", " ", texte)
    prix = [_nombre(m.group(1)) for m in RE_PRIX.finditer(texte)]
    prix = [p for p in prix if 10_000 <= p <= 10_000_000]
    surf = [float(m.group(1).replace(",", ".")) for m in RE_SURFACE.finditer(texte)]
    surf = [s for s in surf if 9 <= s <= 1000]
    commune = ""
    for rx in (RE_COMMUNE_CP, RE_CP_COMMUNE, RE_COMMUNE_A):
        m = rx.search(texte)
        if m:
            commune = m.group(m.lastindex).strip(" -,")
            break
    return {
        "type_local": type_depuis_texte(texte), "commune": commune,
        "surface": surf[0] if surf else "", "prix": prix[0] if prix else "", "titre": texte[:120],
    }


def annonces_depuis_message(msg) -> list:
    """Renvoie la liste des annonces (dicts) trouvées dans un message e-mail. Ne lève pas d'exception."""
    try:
        sujet = str(msg.get("Subject", ""))
        corps_html, corps_txt = [], []
        for part in msg.walk():
            if part.get_content_maintype() != "text":
                continue
            try:
                contenu = part.get_content()
            except (LookupError, UnicodeDecodeError):
                continue
            (corps_html if part.get_content_subtype() == "html" else corps_txt).append(contenu)
        trouvees = []
        for h in corps_html:
            p = _Blocs()
            p.feed(h)
            for url, textes in p.blocs:
                trouvees.append((url, " ".join(textes)))
        if not trouvees:  # e-mail texte brut : un lien suivi de son contexte
            for t in corps_txt:
                liens = list(re.finditer(r"https?://[^\s<>\"')]+", t))
                for i, m in enumerate(liens):
                    url = url_annonce(m.group(0))
                    if url:
                        fin = liens[i + 1].start() if i + 1 < len(liens) else len(t)
                        debut = liens[i - 1].end() if i > 0 else max(0, m.start() - 300)
                        trouvees.append((url, t[debut:m.start()] + " " + t[m.end():fin]))
        res, vus = [], set()
        for url, texte in trouvees:
            if url in vus:
                continue
            vus.add(url)
            champs = extraire_champs(texte)
            if not champs["type_local"]:
                champs["type_local"] = type_depuis_texte(sujet)
            if not champs["titre"]:
                champs["titre"] = sujet[:120]
            res.append({"url": url, **champs})
        return res
    except Exception as e:  # noqa: BLE001 - l'import ne doit jamais faire échouer le workflow
        log.warning("E-mail ignoré (analyse impossible) : %s", e)
        return []


def lire_annonces_csv(path: Path) -> list:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def fusionner(path: Path, nouvelles: list) -> int:
    """Ajoute à annonces.csv les annonces dont l'URL est nouvelle. Renvoie le nombre d'ajouts."""
    existantes = lire_annonces_csv(path)
    urls = {r.get("url", "") for r in existantes}
    ajouts = []
    for a in nouvelles:
        if a["url"] in urls or not (a["prix"] and a["surface"] and a["commune"] and a["type_local"]):
            continue  # incomplète : inutilisable pour le scoring
        urls.add(a["url"])
        ajouts.append(a)
    if ajouts:
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLONNES, extrasaction="ignore")
            w.writeheader()
            w.writerows(existantes + ajouts)
    return len(ajouts)


def recuperer_messages(host, user, password, dossier="INBOX", port=993, jours=None):
    """Itère sur les messages non lus. Utilise BODY.PEEK puis marque comme lu après lecture."""
    with imaplib.IMAP4_SSL(host, port, timeout=60) as imap:
        imap.login(user, password)
        imap.select(dossier)
        _, data = imap.search(None, "UNSEEN")
        for num in data[0].split():
            _, rep = imap.fetch(num, "(BODY.PEEK[])")
            if rep and isinstance(rep[0], tuple):
                yield email.message_from_bytes(rep[0][1], policy=policy.default)
                imap.store(num, "+FLAGS", "\\Seen")


def main(annonces_path=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S", stream=sys.stdout)
    host, user, mdp = os.environ.get("IMAP_HOST"), os.environ.get("IMAP_USER"), os.environ.get("IMAP_PASSWORD")
    if not (host and user and mdp):
        log.info("Import e-mail désactivé (secrets IMAP_HOST, IMAP_USER et IMAP_PASSWORD absents)")
        return 0
    path = Path(annonces_path or ROOT / "annonces.csv")
    try:
        nouvelles = []
        nb = 0
        for msg in recuperer_messages(host, user, mdp, os.environ.get("IMAP_FOLDER", "INBOX"), int(os.environ.get("IMAP_PORT", "993"))):
            nb += 1
            nouvelles += annonces_depuis_message(msg)
        ajoutees = fusionner(path, nouvelles)
        log.info("Import e-mail : %d message(s) lu(s), %d annonce(s) trouvée(s), %d ajoutée(s)", nb, len(nouvelles), ajoutees)
    except Exception as e:  # noqa: BLE001
        log.warning("Import e-mail interrompu : %s", type(e).__name__)  # pas de détail : il pourrait contenir l'identifiant
    return 0


if __name__ == "__main__":
    sys.exit(main())
