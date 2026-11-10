#!/usr/bin/env python3
"""Automatisation : surveillance d'un dossier et déclenchement de commandes.

Surveille un dossier (sondage, sans dépendance) et lance une commande à chaque
nouveau fichier détecté. La commande peut utiliser les variables `{file}`,
`{name}`, `{dir}`.

Exemples
--------
    python automations/watch_folder.py --folder ./inbox --command "echo Nouveau: {file}"
    python automations/watch_folder.py --folder ./inbox --command "python process.py {file}" --once
    python automations/watch_folder.py --folder ./inbox --command "mv {file} ./done/" --interval 2
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.utils import get_logger, write_json  # noqa: E402

LOG = get_logger("watch")


def snapshot(folder: Path) -> dict[str, float]:
    """Nom -> date de modification, pour les fichiers du dossier (non récursif)."""
    return {p.name: p.stat().st_mtime
            for p in folder.iterdir()
            if p.is_file() and not p.name.startswith(".")}


def new_files(previous: dict[str, float], current: dict[str, float]) -> list[str]:
    """Fichiers apparus ou modifiés depuis le dernier relevé."""
    return sorted(name for name, mtime in current.items()
                  if name not in previous or mtime > previous[name])


def build_command(template: str, path: Path) -> list[str]:
    filled = (template.replace("{file}", str(path))
                      .replace("{name}", path.name)
                      .replace("{dir}", str(path.parent)))
    return shlex.split(filled, posix=sys.platform != "win32")


def handle(path: Path, template: str, dry_run: bool = False) -> bool:
    command = build_command(template, path)
    if dry_run:
        LOG.info("[dry-run] exécuterait : %s", " ".join(command))
        return True
    LOG.info("▶ %s", " ".join(command))
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        LOG.error("Échec de la commande : %s", exc)
        return False
    if result.stdout.strip():
        LOG.info("stdout : %s", result.stdout.strip()[:1000])
    if result.returncode != 0:
        LOG.warning("Code retour %d : %s", result.returncode, result.stderr.strip()[:500])
    return result.returncode == 0


def run(folder: str, command: str, interval: float = 3.0, once: bool = False,
        dry_run: bool = False, ignore_existing: bool = True,
        state_file: str | None = None) -> int:
    base = Path(folder)
    if not base.is_dir():
        raise NotADirectoryError(f"Dossier introuvable : {base}")

    previous = snapshot(base) if ignore_existing else {}
    if ignore_existing:
        LOG.info("État initial : %d fichier(s) ignoré(s)", len(previous))

    processed = 0
    LOG.info("Surveillance de %s (intervalle %.1fs)%s", base, interval,
             " — une seule passe" if once else "")

    try:
        while True:
            time.sleep(interval)
            current = snapshot(base)
            for name in new_files(previous, current):
                if handle(base / name, command, dry_run=dry_run):
                    processed += 1
            previous = current

            if state_file:
                write_json(state_file, {"processed": processed,
                                        "files": sorted(current)})
            if once:
                break
    except KeyboardInterrupt:
        LOG.info("Arrêt demandé.")

    return processed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Surveille un dossier et exécute une commande.")
    parser.add_argument("--folder", required=True, help="Dossier à surveiller")
    parser.add_argument("--command", required=True,
                        help="Commande à lancer ({file}, {name}, {dir} disponibles)")
    parser.add_argument("--interval", type=float, default=3.0, help="Sondage en secondes")
    parser.add_argument("--once", action="store_true", help="Une seule passe puis sortie")
    parser.add_argument("--include-existing", action="store_true",
                        help="Traite aussi les fichiers déjà présents")
    parser.add_argument("--dry-run", action="store_true", help="Affiche sans exécuter")
    parser.add_argument("--state", default=None, help="Fichier JSON d'état (optionnel)")
    args = parser.parse_args(argv)

    try:
        count = run(args.folder, args.command, args.interval, args.once,
                    args.dry_run, not args.include_existing, args.state)
    except NotADirectoryError as exc:
        LOG.error("%s", exc)
        return 2

    print(f"✔ {count} fichier(s) traité(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
