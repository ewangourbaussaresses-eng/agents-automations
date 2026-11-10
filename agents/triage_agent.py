#!/usr/bin/env python3
"""Agent de triage : classe des tickets / tâches par urgence et catégorie.

Entrée  : un CSV avec au minimum une colonne de texte (`title` ou `titre`).
Sortie  : le même CSV enrichi de `priority`, `category`, `score` + un résumé Markdown.

La logique est **explicite et auditable** (mots-clés pondérés), sans modèle externe :
facile à lire, à modifier et à tester. Pour un triage par LLM, remplacez la
fonction `score_ticket`.

Exemples
--------
    python agents/triage_agent.py --input data/tickets.csv --out out/tickets_tries.csv
    python agents/triage_agent.py --input data/tickets.csv --min-priority haute
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.utils import get_logger, human_date, write_text  # noqa: E402

LOG = get_logger("triage")

URGENCY_WORDS = {
    3: ["urgent", "critique", "bloquant", "panne", "down", "indisponible", "perte de données",
        "securite", "sécurité", "fuite", "incident", "asap", "immédiat", "immediat"],
    2: ["bug", "erreur", "échec", "echec", "lent", "ralenti", "problème", "probleme",
        "ne fonctionne pas", "cassé", "cassee", "cassé"],
    1: ["amélioration", "amelioration", "suggestion", "idée", "idee", "question",
        "documentation", "doute"],
}

CATEGORY_RULES = {
    "Facturation": ["facture", "paiement", "remboursement", "abonnement", "prix", "devis"],
    "Technique": ["bug", "erreur", "api", "serveur", "base de données", "performance",
                  "déploiement", "deploiement", "log"],
    "Sécurité": ["securite", "sécurité", "fuite", "accès", "acces",
                 "authentification", "rgpd"],
    "Commercial": ["client", "prospect", "vente", "contrat", "partenariat"],
    "Support": ["aide", "support", "question", "comment", "assistance",
                "mot de passe", "mdp"],
}

PRIORITIES = [(7, "critique"), (4, "haute"), (2, "moyenne"), (0, "basse")]


# --------------------------------------------------------------------------- #
# Traitement (pur, testable)
# --------------------------------------------------------------------------- #
def score_ticket(text: str) -> tuple[int, str, str]:
    """Retourne (score, priorité, catégorie) pour un texte de ticket."""
    low = text.lower()

    score = 0
    for weight, words in URGENCY_WORDS.items():
        hits = sum(1 for w in words if w in low)
        score += weight * min(hits, 2)

    # Les majuscules et points d'exclamation sont un signal d'urgence réel.
    if re.search(r"\b[A-Z]{4,}\b", text):
        score += 1
    score += min(text.count("!"), 2)

    # Un ticket court et vague n'est pas prioritaire.
    if len(low.split()) < 4:
        score -= 1

    priority = next(label for threshold, label in PRIORITIES if score >= threshold)

    category = "Autre"
    best = 0
    for name, words in CATEGORY_RULES.items():
        hits = sum(1 for w in words if w in low)
        if hits > best:
            best, category = hits, name

    return score, priority, category


def text_of(row: dict) -> str:
    for key in ("title", "titre", "subject", "sujet", "description", "body"):
        if row.get(key):
            return " ".join(str(row[key]) for key in
                            ("title", "titre", "subject", "sujet", "description", "body")
                            if row.get(key))
    return " ".join(str(v) for v in row.values() if v)


def triage_rows(rows: list[dict]) -> list[dict]:
    enriched = []
    for row in rows:
        score, priority, category = score_ticket(text_of(row))
        enriched.append({**row, "score": score, "priority": priority, "category": category})
    order = {label: i for i, (_, label) in enumerate(PRIORITIES)}
    enriched.sort(key=lambda r: (order[r["priority"]], -r["score"]))
    return enriched


def render_summary(rows: list[dict], title: str = "Triage des tickets") -> str:
    lines = [f"# 🎯 {title}", "", f"*Généré le {human_date()} — {len(rows)} ticket(s)*", ""]
    by_priority: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for row in rows:
        by_priority[row["priority"]] = by_priority.get(row["priority"], 0) + 1
        by_category[row["category"]] = by_category.get(row["category"], 0) + 1

    lines += ["## Par priorité", ""]
    for _, label in PRIORITIES:
        if label in by_priority:
            lines.append(f"- **{label}** : {by_priority[label]}")
    lines += ["", "## Par catégorie", ""]
    for name, count in sorted(by_category.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {name} : {count}")

    lines += ["", "## À traiter en premier", ""]
    for row in rows[:10]:
        label = row.get("title") or row.get("titre") or row.get("id") or "(sans titre)"
        lines.append(f"- [{row['priority']}] {label} — _{row['category']}_ (score {row['score']})")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(input_csv: str, out_csv: str, out_md: str | None = None,
        min_priority: str | None = None) -> list[dict]:
    src = Path(input_csv)
    if not src.exists():
        raise FileNotFoundError(f"Fichier introuvable : {src}")

    with src.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    LOG.info("%d ticket(s) lus", len(rows))

    enriched = triage_rows(rows)

    if min_priority:
        allowed = {label for threshold, label in PRIORITIES
                   if threshold >= dict((lbl, thr) for thr, lbl in PRIORITIES)[min_priority]}
        enriched = [r for r in enriched if r["priority"] in allowed]
        LOG.info("%d ticket(s) après filtre '%s'", len(enriched), min_priority)

    dest = Path(out_csv)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fields = list(enriched[0].keys()) if enriched else ["id", "title", "score", "priority", "category"]
    with dest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(enriched)
    LOG.info("CSV trié : %s", dest)

    if out_md:
        write_text(out_md, render_summary(enriched))
        LOG.info("Résumé : %s", out_md)
    return enriched


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent de triage de tickets par urgence.")
    parser.add_argument("--input", required=True, help="CSV d'entrée")
    parser.add_argument("--out", default="out/tickets_tries.csv", help="CSV de sortie")
    parser.add_argument("--summary", default="out/triage.md", help="Résumé Markdown ('' pour désactiver)")
    parser.add_argument("--min-priority", choices=["basse", "moyenne", "haute", "critique"],
                        default=None, help="Ne garder que cette priorité et au-dessus")
    args = parser.parse_args(argv)

    try:
        rows = run(args.input, args.out, args.summary or None, args.min_priority)
    except FileNotFoundError as exc:
        LOG.error("%s", exc)
        return 2

    top = rows[0]["priority"] if rows else "—"
    print(f"✔ {len(rows)} ticket(s) triés, priorité max : {top} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
