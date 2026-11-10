"""Lecture minimale de flux RSS/Atom, sans dépendance externe.

Suffisant pour les cas courants (RSS 2.0 et Atom). Pour des flux exotiques,
installez `feedparser` et remplacez `fetch_feed`.
"""
from __future__ import annotations

import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Iterable

ATOM = "{http://www.w3.org/2005/Atom}"
USER_AGENT = "agents-automations/1.0 (+https://github.com)"


@dataclass
class FeedItem:
    title: str
    link: str
    summary: str = ""
    published: datetime | None = None
    source: str = ""
    tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "link": self.link,
            "summary": self.summary,
            "published": self.published.isoformat() if self.published else None,
            "source": self.source,
            "tags": self.tags,
        }


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        return parsedate_to_datetime(raw).replace(tzinfo=None)
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=None)
        except ValueError:
            continue
    return None


def parse_feed(xml_text: str, source: str = "") -> list[FeedItem]:
    """Transforme un XML RSS ou Atom en liste de FeedItem."""
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)

    # Atom
    if root.tag == ATOM + "feed" or root.findall(ATOM + "entry"):
        feed_title = (root.findtext(ATOM + "title") or source).strip()
        items = []
        for entry in root.findall(ATOM + "entry"):
            link_el = entry.find(ATOM + "link")
            items.append(FeedItem(
                title=(entry.findtext(ATOM + "title") or "").strip(),
                link=(link_el.get("href") if link_el is not None else "").strip(),
                summary=(entry.findtext(ATOM + "summary")
                         or entry.findtext(ATOM + "content") or "").strip(),
                published=_parse_date(entry.findtext(ATOM + "updated")
                                      or entry.findtext(ATOM + "published")),
                source=feed_title,
                tags=[c.get("term", "") for c in entry.findall(ATOM + "category")],
            ))
        return items

    # RSS 2.0
    channel = root.find("channel")
    if channel is None:
        channel = root
    feed_title = (channel.findtext("title") or source).strip()
    items = []
    for item in channel.findall("item"):
        items.append(FeedItem(
            title=(item.findtext("title") or "").strip(),
            link=(item.findtext("link") or "").strip(),
            summary=(item.findtext("description") or "").strip(),
            published=_parse_date(item.findtext("pubDate")),
            source=feed_title,
            tags=[c.text.strip() for c in item.findall("category") if c.text],
        ))
    return items


def fetch_feed(url: str, timeout: int = 15) -> list[FeedItem]:
    """Télécharge puis parse un flux. Lève une exception en cas d'échec réseau."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    return parse_feed(payload.decode("utf-8", errors="replace"), source=url)


def fetch_all(urls: Iterable[str], timeout: int = 15) -> list[FeedItem]:
    """Agrège plusieurs flux ; un flux en erreur est ignoré."""
    collected: list[FeedItem] = []
    for url in urls:
        try:
            collected.extend(fetch_feed(url, timeout=timeout))
        except Exception:  # noqa: BLE001 - un flux cassé ne doit pas bloquer le reste
            continue
    return collected
