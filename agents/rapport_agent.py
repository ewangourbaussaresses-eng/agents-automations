#!/usr/bin/env python3
"""Agent de rapport : transforme un dossier de notes (ou des données JSON)
en rapport d'activité Markdown + JSON.

Il détecte automatiquement les titres, les TODO, les mots-clés et la période
couverte, puis produit un résumé structuré prêt à être envoyé.

Exemples
--------
    python agents/rapport_agent.py --source ./notes --out out/rapport.md
    python agents/rapport_agent.py --source data/activite.json --title "Semaine 45"
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.utils import (  # noqa: E402
    get_logger, human_date, iter_files, now_utc, truncate, write_json, write_text,
)

LOG = get_logger("rapport")

STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "à", "au", "aux",
    "en", "dans", "sur", "pour", "par", "avec", "sans", "que", "qui", "quoi", "est",
    "sont", "a", "ont", "ce", "cette", "ces", "son", "sa", "ses", "il", "elle", "on",
    "nous", "vous", "ils", "elles", "the", "and", "for", "with", "from", "this", "that",
    "plus", "pas", "ne", "se", "si", "mais", "comme", "tout", "tous", "être", "avoir",
}


@dataclass
class Entry:
    source: str
    title: str
    date: datetime | None
    body: str
    todos: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Collecte
# --------------------------------------------------------------------------- #
def parse_date_from_name(name: str) -> datetime | None:
    for pattern, fmt in (
        (r"(\d{4}-\d{2}-\d{2})", "%Y-%m-%d"),
        (r"(\d{4}_\d{2}_\d{2})", "%Y_%m_%d"),
        (r"(\d{2}-\d{2}-\d{4})", "%d-%m-%Y"),
    ):
        match = re.search(pattern, name)
        if match:
            try:
                return datetime.strptime(match.group(1), fmt)
            except ValueError:
                continue
    return None


def collect_from_folder(folder: Path) -> list[Entry]:
    entries: list[Entry] = []
    for path in iter_files(folder):
        text = path.read_text(encoding="utf-8", errors="replace")
        first_line = next((ln.strip("# ").strip() for ln in text.splitlines() if ln.strip()), "")
        todos = re.findall(r"(?:TODO|FIXME|À FAIRE|A FAIRE)\s*[:：-]?\s*(.+)", text,
                           flags=re.IGNORECASE)
        entries.append(Entry(
            source=str(path.relative_to(folder)),
            title=first_line or path.stem,
            date=parse_date_from_name(path.name),
            body=text,
            todos=[t.strip() for t in todos],
        ))
    return entries


def collect_from_json(path: Path) -> list[Entry]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("entries", data.get("items", [data]))
    entries = []
    for raw in data:
        date = None
        for key in ("date", "created_at", "created", "updated"):
            if raw.get(key):
                try:
                    date = datetime.fromisoformat(str(raw[key]).replace("Z", "+00:00"))
                    date = date.replace(tzinfo=None)
                    break
                except ValueError:
                    continue
        body = raw.get("body") or raw.get("description") or raw.get("content") or ""
        entries.append(Entry(
            source=raw.get("source", path.name),
            title=raw.get("title") or raw.get("name") or "(sans titre)",
            date=date,
            body=body,
            todos=raw.get("todos", []),
        ))
    return entries


def collect_from_csv(path: Path) -> list[Entry]:
    entries = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            entries.append(Entry(
                source=row.get("source", path.name),
                title=row.get("title") or row.get("titre") or "(sans titre)",
                date=parse_date_from_name(row.get("date", "")),
                body=row.get("body") or row.get("description") or "",
                todos=[row["todo"]] if row.get("todo") else [],
            ))
    return entries


def collect(source: Path) -> list[Entry]:
    if source.is_dir():
        return collect_from_folder(source)
    if source.suffix.lower() == ".json":
        return collect_from_json(source)
    if source.suffix.lower() == ".csv":
        return collect_from_csv(source)
    return [Entry(source=source.name, title=source.stem,
                  date=parse_date_from_name(source.name),
                  body=source.read_text(encoding="utf-8", errors="replace"))]


# --------------------------------------------------------------------------- #
# Traitement
# --------------------------------------------------------------------------- #
def keywords(entries: list[Entry], top: int = 8) -> list[tuple[str, int]]:
    words: Counter[str] = Counter()
    for entry in entries:
        text = (entry.title + " " + entry.body).lower()
        for word in re.findall(r"[a-zA-Zà-ÿ]{3,}", text):
            if word not in STOPWORDS:
                words[word] += 1
    return words.most_common(top)


def period(entries: list[Entry]) -> tuple[datetime | None, datetime | None]:
    dates = sorted(e.date for e in entries if e.date)
    return (dates[0], dates[-1]) if dates else (None, None)


def build_report(entries: list[Entry], title: str) -> dict:
    start, end = period(entries)
    todos = [t for e in entries for t in e.todos]
    return {
        "title": title,
        "generated_at": human_date(),
        "period": {
            "from": start.strftime("%d/%m/%Y") if start else None,
            "to": end.strftime("%d/%m/%Y") if end else None,
        },
        "counts": {
            "entries": len(entries),
            "todos": len(todos),
            "sources": len({e.source for e in entries}),
        },
        "keywords": [{"word": w, "count": c} for w, c in keywords(entries)],
        "todos": todos,
        "entries": [
            {
                "source": e.source,
                "title": e.title,
                "date": e.date.strftime("%d/%m/%Y") if e.date else None,
                "excerpt": truncate(e.body, 220),
            }
            for e in entries
        ],
    }


def render_markdown(report: dict) -> str:
    p = report["period"]
    c = report["counts"]
    lines = [f"# 📊 {report['title']}", "", f"*Généré le {report['generated_at']}*", ""]

    lines += ["## Chiffres clés", "",
              f"- **{c['entries']}** entrée(s) analysée(s) depuis **{c['sources']}** source(s)",
              f"- **{c['todos']}** action(s) en attente"]
    if p["from"]:
        lines.append(f"- Période couverte : du **{p['from']}** au **{p['to']}**")
    lines.append("")

    if report["keywords"]:
        lines += ["## Thèmes dominants", ""]
        lines += [f"- `{k['word']}` — {k['count']} occurrence(s)" for k in report["keywords"]]
        lines.append("")

    if report["todos"]:
        lines += ["## À faire", ""]
        lines += [f"- [ ] {todo}" for todo in report["todos"]]
        lines.append("")

    lines += ["## Détail des entrées", ""]
    for entry in report["entries"]:
        when = f" — _{entry['date']}_" if entry["date"] else ""
        lines += [f"### {entry['title']}{when}", f"`{entry['source']}`", "",
                  entry["excerpt"] or "*(vide)*", ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(source: str, out_md: str, out_json: str | None = None,
        title: str | None = None) -> dict:
    src = Path(source)
    if not src.exists():
        raise FileNotFoundError(f"Source introuvable : {src}")

    entries = collect(src)
    LOG.info("%d entrée(s) collectée(s)", len(entries))

    report = build_report(entries, title or f"Rapport d'activité — {now_utc():%d/%m/%Y}")
    write_text(out_md, render_markdown(report))
    LOG.info("Rapport Markdown : %s", out_md)

    if out_json:
        write_json(out_json, report)
        LOG.info("Rapport JSON : %s", out_json)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent de rapport : notes -> rapport d'activité.")
    parser.add_argument("--source", required=True, help="Dossier, fichier .json, .csv ou .md")
    parser.add_argument("--out", default="out/rapport.md", help="Rapport Markdown de sortie")
    parser.add_argument("--json", dest="out_json", default="out/rapport.json",
                        help="Rapport JSON de sortie ('' pour désactiver)")
    parser.add_argument("--title", default=None, help="Titre du rapport")
    args = parser.parse_args(argv)

    try:
        report = run(args.source, args.out, args.out_json or None, args.title)
    except FileNotFoundError as exc:
        LOG.error("%s", exc)
        return 2

    print(f"✔ {report['counts']['entries']} entrée(s), {report['counts']['todos']} TODO "
          f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
