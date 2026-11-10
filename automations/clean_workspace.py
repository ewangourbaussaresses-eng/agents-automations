#!/usr/bin/env python3
"""Automatisation : nettoyage des artefacts d'un dépôt.

Supprime les dossiers/caches connus (`__pycache__`, `.pytest_cache`,
`node_modules/.cache`, fichiers `*.pyc`, `*.log`, `Thumbs.db`…).
Les éléments supprimés vont dans la corbeille applicative `out/trash/`
(ou sont listés en `--dry-run`), jamais d'effacement silencieux.

Exemples
--------
    python automations/clean_workspace.py --root . --dry-run
    python automations/clean_workspace.py --root . --aggressive
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.utils import get_logger, human_date, size_human, stamp, write_text  # noqa: E402

LOG = get_logger("clean")

DIR_PATTERNS = ["__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                ".ipynb_checkpoints", ".DS_Store"]
AGGRESSIVE_DIRS = ["node_modules", ".venv", "venv", "dist", "build", ".next"]
FILE_PATTERNS = ["*.pyc", "*.pyo", "*.log", "Thumbs.db", "*.tmp", "*.swp", ".DS_Store"]


def find_targets(root: Path, aggressive: bool = False) -> list[Path]:
    targets: set[Path] = set()
    names = DIR_PATTERNS + (AGGRESSIVE_DIRS if aggressive else [])
    for name in names:
        targets.update(p for p in root.rglob(name) if p.is_dir() or p.name == ".DS_Store")
    for pattern in FILE_PATTERNS:
        targets.update(root.rglob(pattern))

    # On garde le plus haut dans l'arborescence pour éviter les doublons parents/enfants.
    ordered = sorted(targets, key=lambda p: len(p.parts))
    kept: list[Path] = []
    for path in ordered:
        if not any(path.is_relative_to(parent) for parent in kept):
            kept.append(path)
    return kept


def dir_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def run(root: str, dry_run: bool = False, aggressive: bool = False,
        trash_dir: str = "out/trash") -> dict:
    base = Path(root).resolve()
    targets = find_targets(base, aggressive)
    total = sum(dir_size(p) for p in targets)

    LOG.info("%d élément(s) à nettoyer (%s)", len(targets), size_human(total))

    moved = []
    for path in targets:
        if dry_run:
            LOG.info("[dry-run] supprimerait %s", path.relative_to(base))
            continue
        trash = Path(trash_dir) / stamp()
        trash.mkdir(parents=True, exist_ok=True)
        destination = trash / path.name
        counter = 1
        while destination.exists():
            destination = trash / f"{path.stem}_{counter}{path.suffix}"
            counter += 1
        try:
            shutil.move(str(path), str(destination))
            moved.append(str(path.relative_to(base)))
        except OSError as exc:  # fichier verrouillé
            LOG.warning("Impossible de déplacer %s : %s", path, exc)

    if not dry_run and moved:
        report = ["# Rapport de nettoyage", "", f"*{human_date()}*", "",
                  f"- Éléments déplacés : **{len(moved)}**",
                  f"- Espace libéré : **{size_human(total)}**", "", "## Détail", ""]
        report += [f"- `{m}`" for m in moved]
        write_text(Path(trash_dir) / "rapport_nettoyage.md", "\n".join(report) + "\n")

    return {"found": len(targets), "moved": moved, "bytes": total, "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nettoyage des artefacts d'un dépôt.")
    parser.add_argument("--root", default=".", help="Racine à nettoyer")
    parser.add_argument("--dry-run", action="store_true", help="Liste sans rien déplacer")
    parser.add_argument("--aggressive", action="store_true",
                        help="Inclut node_modules, .venv, dist, build…")
    parser.add_argument("--trash", default="out/trash", help="Dossier de quarantaine")
    args = parser.parse_args(argv)

    result = run(args.root, args.dry_run, args.aggressive, args.trash)
    action = "à nettoyer" if result["dry_run"] else "déplacé(s)"
    print(f"✔ {result['found']} élément(s) {action}, {size_human(result['bytes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
