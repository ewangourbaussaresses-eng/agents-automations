# 🤖 Agents & Automatisations

Une collection d'agents autonomes et d'automatisations **prêtes à l'emploi**, écrites en
Python standard (aucune dépendance obligatoire) et pensées pour tourner **localement**
ou dans un **workflow GitHub Actions**.

Chaque outil est autonome : un fichier, une CLI, des tests, une doc. Forkez, modifiez,
branchez sur vos propres données.

---

## Sommaire

| # | Outil | Type | Ce qu'il fait |
|---|-------|------|----------------|
| 1 | [`agents/veille_agent.py`](agents/veille_agent.py) | Agent | Surveille des flux RSS / pages web et produit un digest Markdown des nouveautés |
| 2 | [`agents/rapport_agent.py`](agents/rapport_agent.py) | Agent | Génère un rapport d'activité (Markdown + JSON) à partir de fichiers locaux ou d'une API |
| 3 | [`agents/triage_agent.py`](agents/triage_agent.py) | Agent | Classe automatiquement des tickets/tâches par urgence et catégorie |
| 4 | [`automations/backup_rotation.py`](automations/backup_rotation.py) | Automatisation | Sauvegarde + rotation + vérification d'intégrité d'un dossier |
| 5 | [`automations/clean_workspace.py`](automations/clean_workspace.py) | Automatisation | Nettoie les fichiers temporaires/artefacts d'un dépôt |
| 6 | [`automations/watch_folder.py`](automations/watch_folder.py) | Automatisation | Surveille un dossier et déclenche une commande à chaque nouveau fichier |

Tous les scripts :

- fonctionnent **hors ligne** et sans clé API ;
- acceptent `--help`, `--dry-run` quand ils écrivent/suppriment ;
- écrivent leurs résultats dans `out/` (ignoré par git) ;
- sont couverts par `pytest`.

---

## Installation

```bash
git clone https://github.com/<votre-compte>/agents-automations.git
cd agents-automations

python -m venv .venv
# Windows : .venv\Scripts\activate
source .venv/bin/activate

pip install -r requirements.txt   # uniquement pour les tests et le mode web
```

Python **3.9+** requis.

---

## Démarrage rapide

```bash
# 1. Un digest de veille depuis des flux RSS
python agents/veille_agent.py --feeds feeds.example.txt --out out/veille.md

# 2. Un rapport d'activité à partir d'un dossier de notes
python agents/rapport_agent.py --source ./notes --out out/rapport.md

# 3. Trier des tickets depuis un CSV
python agents/triage_agent.py --input data/tickets.csv --out out/tickets_tries.csv

# 4. Sauvegarde avec rotation (simulation d'abord)
python automations/backup_rotation.py --source ./notes --dest ./backups --keep 5 --dry-run

# 5. Nettoyage d'un dépôt
python automations/clean_workspace.py --root . --dry-run

# 6. Surveillance de dossier
python automations/watch_folder.py --folder ./inbox --command "echo Nouveau fichier: {file}"
```

Chaque script affiche un résumé de ce qu'il a fait et où se trouve le résultat.

---

## Tests

```bash
pip install pytest
python -m pytest -q
```

---

## Utilisation dans GitHub Actions

Le dossier [`.github/workflows/`](.github/workflows/) contient des workflows prêts :

- `tests.yml` — lance la suite de tests à chaque push et pull request ;
- `veille.yml` — produit un digest de veille chaque matin et le commit dans `out/` ;
- `backup.yml` — sauvegarde planifiée (cron) vers un artefact de workflow.

Pour activer un workflow planifié, allez dans l'onglet **Actions** du dépôt.
Les secrets éventuels (clés API, tokens) se déclarent dans
**Settings → Secrets and variables → Actions**.

---

## Structure

```
agents-automations/
├── agents/                  # agents autonomes
├── automations/             # tâches d'automatisation
├── common/                  # utilitaires partagés (I/O, logs, dates)
├── data/                    # exemples de données d'entrée
├── tests/                   # tests pytest
├── .github/workflows/       # CI + tâches planifiées
├── Makefile                 # raccourcis (make test, make demo)
└── requirements.txt
```

---

## Personnalisation

Chaque script est structuré en trois blocs :

1. **Collecte** — lire les données (fichier, dossier, flux RSS, API) ;
2. **Traitement** — la logique métier, isolée dans une fonction pure et testable ;
3. **Sortie** — écrire le résultat (Markdown, CSV, JSON) et logger.

Pour adapter un outil à votre cas, remplacez uniquement le bloc *Collecte*.

---

## Licence

MIT — voir [LICENSE](LICENSE). Utilisez, modifiez, partagez librement.
