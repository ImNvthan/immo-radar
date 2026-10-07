# Radar immobilier

Analyse gratuite des ventes réelles (DVF, données publiques) pour savoir **quoi regarder** et **quand acheter**, et pour scorer des annonces. Tout tourne sur GitHub Actions, sans serveur.

## Mise en route (5 minutes)

1. Crée un dépôt GitHub **public** (minutes Actions illimitées) et pousse ce dossier. En privé, le quota gratuit de 2 000 minutes par mois suffit aussi.
2. Ouvre `config.yml` : choisis ton département, ajuste les loyers au m² et les seuils.
3. Onglet **Actions**, workflow `immo-radar`, bouton **Run workflow** pour le premier lancement.
4. Lis `data/rapport.md` (mis à jour chaque jour automatiquement).

## Alertes Telegram (optionnel)

Crée un bot avec @BotFather, puis ajoute dans Settings > Secrets and variables > Actions les secrets `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID`. Tu es alerté uniquement pour les nouvelles opportunités.

## Scorer des annonces

Ajoute des lignes dans `annonces.csv` (colonnes : `url,type_local,commune,surface,prix,titre`, type = `Appartement` ou `Maison`). Un push sur ce fichier relance l'analyse. Une annonce est signalée si sa décote par rapport à la médiane DVF et son rendement net estimé dépassent les seuils de `config.yml`.

## Ce que ça ne fait pas

- Pas de scraping de Le Bon Coin ou SeLoger : bloqué depuis les serveurs GitHub et contraire à leurs conditions d'utilisation. Alimente `annonces.csv` à la main ou depuis tes alertes email.
- Les prix DVF ont environ 6 mois de retard et ce sont des prix signés, pas des prix affichés (d'où `marge_negociation`).
- Les loyers sont des estimations de ta part, le rendement en dépend directement.
- Ce sont des indicateurs statistiques, pas un conseil en investissement.

## Test hors ligne

`python immo/analyse.py --local-dir dossier_csv --annonces annonces.csv` avec des fichiers `{annee}.csv` au format DVF.
