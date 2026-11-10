"""Petites briques réutilisables : logs, écriture de fichiers, dates, chemins.

Tout repose sur la bibliothèque standard pour que les scripts tournent partout
sans installation.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def get_logger(name: str) -> logging.Logger:
    """Logger coloré-lisible sur stderr, configuré une seule fois."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)-7s %(name)s: %(message)s",
                              datefmt="%H:%M:%S")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def stamp(dt: datetime | None = None, fmt: str = "%Y-%m-%d_%H%M%S") -> str:
    """Horodatage utilisable dans un nom de fichier."""
    return (dt or now_utc()).strftime(fmt)


def human_date(dt: datetime | None = None) -> str:
    return (dt or now_utc()).strftime("%d/%m/%Y à %H:%M UTC")


def ensure_dir(path: os.PathLike | str) -> Path:
    """Crée le dossier parent d'un fichier (ou le dossier lui-même) si besoin."""
    p = Path(path)
    if p.suffix:  # c'est un fichier -> on crée son parent
        p = p.parent
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_text(path: os.PathLike | str, content: str) -> Path:
    p = Path(path)
    ensure_dir(p)
    p.write_text(content, encoding="utf-8")
    return p


def write_json(path: os.PathLike | str, data: Any) -> Path:
    p = Path(path)
    ensure_dir(p)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def read_json(path: os.PathLike | str, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def iter_files(root: os.PathLike | str,
               suffixes: Iterable[str] = (".md", ".txt", ".json", ".csv"),
               skip_hidden: bool = True) -> Iterable[Path]:
    """Parcourt récursivement un dossier en filtrant par extension."""
    root = Path(root)
    wanted = {s.lower() for s in suffixes}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if skip_hidden and any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() in wanted:
            yield path


def size_human(num_bytes: int) -> str:
    """1 234 567 -> '1.2 Mo'."""
    value = float(num_bytes)
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if value < 1024 or unit == "To":
            return f"{value:.0f} {unit}" if unit == "o" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} To"


def truncate(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
