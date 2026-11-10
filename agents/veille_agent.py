#!/usr/bin/env python3
"""Agent de veille : agrège des flux RSS/Atom et produit un digest Markdown.

Il mémorise les articles déjà vus dans `out/veille_state.json` pour ne
présenter que les nouveautés à chaque exécution — parfait pour un cron
ou un workflow GitHub Actions quotidien.

Exemples
--------
    python agents/veille_agent.py --feeds feeds.example.txt
    python agents/veille_agent.py --feeds https://exemple.com/rss --max-per-feed 5
    python agents/veille_agent.py --feeds feeds.example.txt --reset   # tout revoir
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.feeds import FeedItem, fetch_all  # noqa: E402
from common.utils import (  # noqa: E402
    get_logger, human_date, read_json, truncate, write_json, write_text,
)

LOG = get_logger("veille")


# --------------------------------------------------------------------------- #
# Collecte
# --------------------------------------------------------------------------- #
def load_sources(spec: str | Path) -> list[str]:
    """Lit une liste d'URL depuis un fichier (une par ligne) ou une URL directe."""
    spec = str(spec)
    if spec.startswith(("http://", "https://")):
        return [spec]
    path = Path(spec)
    if not path.exists():
        raise FileNotFoundError(f"Fichier de flux introuvable : {path}")
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


# --------------------------------------------------------------------------- #
# Traitement (fonctions pures, testables)
# --------------------------------------------------------------------------- #
def item_key(item: FeedItem) -> str:
    """Identifiant stable d'un article (le lien, sinon le titre)."""
    return (item.link or item.title).strip().lower()


def dedupe(items: list[FeedItem]) -> list[FeedItem]:
    seen: set[str] = set()
    unique = []
    for item in items:
        key = item_key(item)
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def select_new(items: list[FeedItem], seen: set[str], max_per_feed: int = 10) -> list[FeedItem]:
    """Garde les articles inédits, en limitant par source, du plus récent au plus ancien."""
    fresh = [i for i in dedupe(items) if item_key(i) not in seen]
    fresh.sort(key=lambda i: i.published or datetime.min, reverse=True)

    per_source: dict[str, int] = {}
    selected = []
    for item in fresh:
        count = per_source.get(item.source, 0)
        if count >= max_per_feed:
            continue
        per_source[item.source] = count + 1
        selected.append(item)
    return selected


def render_markdown(items: list[FeedItem], total_seen: int, title: str = "Veille du jour") -> str:
    lines = [
        f"# 🔎 {title}",
        "",
        f"*Généré le {human_date()} — {len(items)} nouveauté(s), "
        f"{total_seen} article(s) déjà connus.*",
        "",
    ]
    if not items:
        lines += ["Aucune nouveauté depuis la dernière exécution. ✨", ""]
        return "\n".join(lines)

    by_source: dict[str, list[FeedItem]] = {}
    for item in items:
        by_source.setdefault(item.source or "Sans source", []).append(item)

    for source, entries in by_source.items():
        lines += [f"## {source}", ""]
        for item in entries:
            date = f" — _{item.published:%d/%m/%Y}_" if item.published else ""
            lines.append(f"- [{item.title or 'Sans titre'}]({item.link}){date}")
            if item.summary:
                lines.append(f"  {truncate(item.summary, 200)}")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(feeds_spec: str, out_path: str, state_path: str,
        max_per_feed: int = 10, reset: bool = False) -> dict:
    urls = load_sources(feeds_spec)
    LOG.info("%d source(s) à interroger", len(urls))

    items = fetch_all(urls)
    LOG.info("%d article(s) récupérés", len(items))

    state = {} if reset else read_json(state_path, default={}) or {}
    seen = set(state.get("seen", []))

    new_items = select_new(items, seen, max_per_feed=max_per_feed)
    LOG.info("%d nouveauté(s) retenue(s)", len(new_items))

    write_text(out_path, render_markdown(new_items, len(seen)))

    seen.update(item_key(i) for i in items)
    write_json(state_path, {"updated": human_date(), "seen": sorted(seen)})

    LOG.info("Digest écrit dans %s", out_path)
    return {"feeds": len(urls), "fetched": len(items), "new": len(new_items), "out": out_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Agent de veille : RSS/Atom -> digest Markdown des nouveautés.")
    parser.add_argument("--feeds", required=True,
                        help="Fichier texte d'URL de flux (une par ligne) ou une URL directe")
    parser.add_argument("--out", default="out/veille.md", help="Fichier Markdown de sortie")
    parser.add_argument("--state", default="out/veille_state.json",
                        help="Fichier d'état des articles déjà vus")
    parser.add_argument("--max-per-feed", type=int, default=10,
                        help="Nombre maximum d'articles retenus par source (défaut : 10)")
    parser.add_argument("--reset", action="store_true",
                        help="Ignore l'état : tous les articles sont considérés comme nouveaux")
    args = parser.parse_args(argv)

    try:
        result = run(args.feeds, args.out, args.state, args.max_per_feed, args.reset)
    except FileNotFoundError as exc:
        LOG.error("%s", exc)
        return 2
    print(f"✔ {result['new']} nouveauté(s) sur {result['fetched']} article(s) "
          f"-> {result['out']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
