.PHONY: help install test demo clean

help:
	@echo "make install  — installer les dépendances de test"
	@echo "make test     — lancer la suite de tests"
	@echo "make demo     — exécuter les agents sur les données d'exemple"
	@echo "make clean    — nettoyer les artefacts (simulation)"

install:
	pip install -r requirements.txt

test:
	python -m pytest -q

demo:
	python agents/triage_agent.py --input data/tickets.csv --out out/tickets_tries.csv
	python agents/rapport_agent.py --source data/notes --out out/rapport.md
	python agents/veille_agent.py --feeds feeds.example.txt --out out/veille.md || true

clean:
	python automations/clean_workspace.py --root . --dry-run
