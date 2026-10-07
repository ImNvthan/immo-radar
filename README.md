# Radar immobilier

Analyse 100 % gratuite des ventes réelles (DVF, données publiques) pour savoir **quoi regarder** et **quand acheter**, et pour scorer des annonces. Tout tourne sur GitHub Actions, sans serveur ni service payant.

> **Avertissement.** Ce sont des indicateurs statistiques calculés sur des données publiques, pas un conseil en investissement. Vérifie toujours un bien sur place, son état, sa copropriété et sa fiscalité avant de décider.

Chaque jour, le workflow `immo-radar` :

1. télécharge les ventes DVF du ou des départements choisis (`files.data.gouv.fr`) et la carte officielle des loyers (ANIL, `data.gouv.fr`) ;
2. calcule le prix médian au m² par commune et type de bien, la tendance sur 12 et 6 mois et la saisonnalité ;
3. score les annonces de `annonces.csv` (décote par rapport à la médiane DVF, rendement net estimé) ;
4. écrit `data/rapport.md`, les CSV de `data/` et la page `docs/index.html`, puis commite le résultat uniquement si quelque chose a changé ;
5. envoie une alerte Telegram pour les nouvelles opportunités, si les secrets Telegram existent.

## Mise en route

1. Fork ou clone ce dépôt en **public** (minutes GitHub Actions illimitées). En privé, les 2 000 minutes gratuites par mois suffisent largement : un run dure environ une minute.
2. Ouvre `config.yml` et **change le département** : `49` (Maine-et-Loire) n'est qu'un exemple. Ajuste aussi le budget, la surface minimale et les seuils.
3. Onglet **Actions**, workflow `immo-radar`, bouton **Run workflow** pour le premier lancement.
4. Lis `data/rapport.md` (mis à jour chaque jour) ou la page de suivi décrite plus bas.

## Configuration (`config.yml`)

| Clé | Rôle |
|---|---|
| `zone.departements` | Liste de codes département (`["44", "49"]`, `"2A"`, `"974"` acceptés). L'ancien format `departement: "49"` fonctionne toujours. **Valeur par défaut `49` : à changer.** |
| `zone.communes` | Optionnel. Restreint l'analyse à ces communes (nom ou code INSEE). Sans département, il est déduit des codes INSEE. Vide : tout le département. |
| `zone.nb_annees` | Nombre d'années DVF chargées (les plus récentes disponibles, 3 par défaut). |
| `min_ventes` | Nombre minimal de ventes pour qu'une commune soit jugée fiable (15). |
| `budget_max` | Budget maximal en euros. Écarte les annonces plus chères. Avec `surface_min`, le classement des communes ne garde que celles où un bien de cette surface au prix médian reste dans le budget. `0` : pas de limite. |
| `surface_min` | Surface minimale en m². Écarte les annonces plus petites. `0` : pas de limite. |
| `loyer_m2_defaut` | Loyers de secours par type de bien, utilisés seulement si ni la surcharge ni la carte officielle n'ont de valeur. |
| `loyers_communes` | Surcharge manuelle par nom ou code INSEE, valeur unique ou par type (`{Appartement: 13.5, Maison: 11}`). |
| `loyer_officiel.actif` / `.coefficient` | Utilisation de la carte officielle et part retenue de ses loyers (0,9 par défaut, voir plus bas). |
| `annonces.*` | Marge de négociation, décote minimale, rendement net minimal, part du loyer perdue en charges et vacance. |

### Origine des loyers

Pour chaque commune, le loyer au m² vient dans cet ordre de :

1. `loyers_communes` de `config.yml` (surcharge manuelle, origine `config.yml`) ;
2. la **carte des loyers ANIL** (origine `ANIL 2025`, ou `ANIL 2025 (maille)` quand la commune a trop peu d'annonces et que le loyer est estimé à partir des communes voisines) ;
3. `loyer_m2_defaut` (origine `défaut config.yml`).

Chaque ligne du rapport et de `data/marche_communes.csv` (colonne `loyer_origine`) indique l'origine utilisée. La carte des loyers est publiée sous Licence Ouverte 2.0 par le ministère chargé du logement et l'ANIL. Ce sont des loyers d'annonce **charges comprises** : le radar en retient 90 % (`loyer_officiel.coefficient`). Ajuste ce coefficient ou surcharge une commune si tu connais mieux le marché local.

## Scorer des annonces

Ajoute des lignes dans `annonces.csv` (colonnes : `url,type_local,commune,surface,prix,titre`, type = `Appartement` ou `Maison`). Un push sur ce fichier relance l'analyse. Une annonce est signalée comme opportunité si sa décote par rapport à la médiane DVF et son rendement net estimé dépassent les seuils de `config.yml`, et si elle respecte le budget et la surface minimale. Les résultats sont dans `data/opportunites.csv` (colonne `note` pour les cas écartés).

## Alertes Telegram (optionnel)

Crée un bot avec @BotFather, puis ajoute dans **Settings > Secrets and variables > Actions** les secrets `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID`. Tu es alerté pour les nouvelles opportunités, et aussi si le workflow échoue.

## Import d'annonces par e-mail (optionnel, sans scraping)

Le script `immo/import_email.py` lit une **boîte mail dédiée** et ajoute à `annonces.csv` les annonces trouvées dans les e-mails d'alerte que Le Bon Coin, SeLoger, PAP, Bien'ici et d'autres t'envoient eux-mêmes. Il ne visite aucun site. Il est désactivé tant que les trois secrets ci-dessous n'existent pas, et une erreur d'import ne fait jamais échouer le workflow.

1. Crée une adresse dédiée (par exemple un nouveau compte Gmail) et inscris-la aux alertes e-mail des sites d'annonces.
2. Crée un **mot de passe d'application** pour cette adresse. Pour Gmail : active la validation en deux étapes sur le compte, ouvre <https://myaccount.google.com/apppasswords>, crée un mot de passe nommé « immo-radar » et copie les 16 caractères. N'utilise jamais le mot de passe principal. Active aussi IMAP dans les réglages Gmail.
3. Ajoute dans **Settings > Secrets and variables > Actions** : `IMAP_HOST` (`imap.gmail.com`), `IMAP_USER` (l'adresse) et `IMAP_PASSWORD` (le mot de passe d'application). Variables facultatives : `IMAP_FOLDER` (`INBOX` par défaut) et `IMAP_PORT` (993).

Seuls les e-mails non lus sont traités, puis marqués comme lus. Les annonces sont dédoublonnées par lien. Une annonce dont le prix, la surface, la commune ou le type n'est pas reconnu est ignorée plutôt qu'ajoutée de travers. Les liens de suivi qui redirigent (par exemple `click.exemple.com`) ne sont pas suivis : seuls les liens directs vers les sites d'annonces sont retenus.

## Page de suivi (GitHub Pages)

À chaque run, `docs/index.html` est régénéré : tendance du prix, saisonnalité, classement des communes et opportunités en cours. C'est un fichier HTML unique, sans dépendance externe, lisible sur téléphone. Il est publié sur `https://<ton-compte>.github.io/immo-radar/`.

Pour l'activer à la main : **Settings > Pages > Build and deployment > Source : Deploy from a branch**, branche `main`, dossier `/docs`.

## Fiabilité et exploitation

- Les téléchargements sont refaits jusqu'à 4 fois avec attente croissante, et gardés en cache (`data/cache`, non versionné) puis mis en cache par GitHub Actions (clé hebdomadaire).
- Si l'analyse échoue, le workflow devient rouge et, si Telegram est configuré, une alerte est envoyée.
- Un commit n'est créé que si les données changent. Sinon, un commit vide est fait tous les 25 jours pour que GitHub ne désactive pas le workflow planifié après 60 jours d'inactivité.
- Tests : `pip install -r requirements-dev.txt` puis `python -m pytest`. Le workflow `tests` les lance à chaque push et pull request. Le jeu de données synthétique est dans `tests/data` (régénérable avec `tests/generer_dvf.py`).
- Test hors ligne : `python immo/analyse.py --local-dir dossier_csv --annonces annonces.csv` avec des fichiers `{annee}.csv` (ou `{annee}_{departement}.csv`) au format DVF.

## Méthode de nettoyage DVF

Ne sont gardées que les mutations de nature « Vente » portant sur un seul logement (appartement ou maison). Sont exclues les ventes multi lots, celles qui incluent un local commercial ou plus de 10 000 m² de terrain, les surfaces inférieures à 9 m² ou supérieures à 300 m² (appartement) et 500 m² (maison), les prix au m² hors de 300 à 20 000 €, puis les 2 % extrêmes par commune, type et année quand l'échantillon dépasse 20 ventes. Une maison vendue sur plusieurs parcelles n'est comptée qu'une fois, et une dépendance (garage, cave) incluse dans la vente est acceptée.

## Limites connues

- Pas de scraping de Le Bon Coin, SeLoger ou PAP : bloqué depuis les serveurs GitHub et contraire à leurs conditions d'utilisation. Alimente `annonces.csv` à la main ou avec l'import e-mail.
- Les prix DVF ont plusieurs mois de retard (la dernière vente connue est indiquée en tête du rapport) et ce sont des prix signés, pas des prix affichés (d'où `marge_negociation`). Les ventes en l'état futur d'achèvement (neuf) sont exclues.
- Le fichier DVF ne contient ni l'état du bien, ni l'étage, ni le DPE : une médiane communale ne remplace pas une estimation du bien.
- Les loyers de la carte ANIL sont des estimations de loyers d'annonce, et les petites communes reposent sur une estimation de maille. Le rendement en dépend directement.
- Les rendements ne tiennent pas compte de la fiscalité, du financement, des travaux ni de la vacance réelle (approchée par `charges_et_vacance`).
- Le DVF ne couvre pas l'Alsace-Moselle (départements 57, 67 et 68) ni Mayotte.
- La tendance et la saisonnalité sont calculées sur toute la zone configurée : avec plusieurs départements, elles mélangent les marchés.
