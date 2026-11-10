#!/usr/bin/env python3
"""Automatisation : sauvegarde d'un dossier avec rotation et vérification.

Crée une archive ZIP horodatée, vérifie son intégrité, supprime les archives
les plus anciennes au-delà de `--keep`, et écrit un manifeste JSON.

Exemples
--------
    python automations/backup_rotation.py --source ./notes --dest ./backups --keep 5
    python automations/backup_rotation.py --source ./notes --dest ./backups --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.utils import (  # noqa: E402
    get_logger, human_date, read_json, size_human, stamp, write_json,
)

LOG = get_logger("backup")


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def create_archive(source: Path, dest_dir: Path, dry_run: bool = False) -> Path:
    name = f"{source.resolve().name}_{stamp()}.zip"
    target = dest_dir / name
    if dry_run:
        LOG.info("[dry-run] créerait %s", target)
        return target

    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file() and not path.name.endswith(".zip"):
                archive.write(path, path.relative_to(source.parent))
    LOG.info("Archive créée : %s (%s)", target.name, size_human(target.stat().st_size))
    return target


def verify_archive(archive: Path) -> bool:
    """Teste l'intégrité de l'archive (CRC de chaque entrée)."""
    try:
        with zipfile.ZipFile(archive) as zf:
            return zf.testzip() is None
    except zipfile.BadZipFile:
        return False


def rotate(dest_dir: Path, keep: int, dry_run: bool = False) -> list[Path]:
    """Supprime les archives les plus anciennes en gardant les `keep` dernières."""
    archives = sorted(dest_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = []
    for old in archives[keep:]:
        removed.append(old)
        if dry_run:
            LOG.info("[dry-run] supprimerait %s", old.name)
        else:
            old.unlink()
            LOG.info("Supprimée : %s", old.name)
    return removed


def run(source: str, dest: str, keep: int = 7, dry_run: bool = False) -> dict:
    src, dst = Path(source), Path(dest)
    if not src.is_dir():
        raise NotADirectoryError(f"Dossier source invalide : {src}")

    archive = create_archive(src, dst, dry_run=dry_run)
    integrity = None if dry_run else verify_archive(archive)

    if integrity is False:
        LOG.error("Archive corrompue : %s", archive)
        return {"archive": str(archive), "ok": False}

    removed = rotate(dst, keep, dry_run=dry_run)

    if not dry_run:
        manifest_path = dst / "manifest.json"
        manifest = read_json(manifest_path, default={"history": []}) or {"history": []}
        manifest["history"].insert(0, {
            "archive": archive.name,
            "date": human_date(),
            "size": archive.stat().st_size,
            "sha256": sha256_of(archive),
            "verified": integrity,
        })
        manifest["history"] = manifest["history"][:50]
        write_json(manifest_path, manifest)

    return {
        "archive": str(archive),
        "verified": integrity,
        "removed": [p.name for p in removed],
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sauvegarde avec rotation et vérification.")
    parser.add_argument("--source", required=True, help="Dossier à sauvegarder")
    parser.add_argument("--dest", default="backups", help="Dossier des archives")
    parser.add_argument("--keep", type=int, default=7, help="Nombre d'archives à conserver")
    parser.add_argument("--dry-run", action="store_true", help="Simulation, n'écrit rien")
    args = parser.parse_args(argv)

    try:
        result = run(args.source, args.dest, args.keep, args.dry_run)
    except NotADirectoryError as exc:
        LOG.error("%s", exc)
        return 2

    state = "vérifiée" if result.get("verified") else ("simulation" if result["dry_run"] else "ÉCHEC")
    print(f"✔ {Path(result['archive']).name} — intégrité : {state}, "
          f"{len(result['removed'])} archive(s) retirée(s)")
    return 0 if result.get("verified") is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
