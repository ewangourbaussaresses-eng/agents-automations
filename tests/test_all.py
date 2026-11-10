"""Tests des agents et automatisations. Lancer : python -m pytest -q"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(ROOT / "automations"))

import backup_rotation  # noqa: E402
import clean_workspace  # noqa: E402
import rapport_agent  # noqa: E402
import triage_agent  # noqa: E402
import veille_agent  # noqa: E402
from common import feeds, utils  # noqa: E402

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Mon flux</title>
  <item><title>Premier article</title><link>https://exemple.com/1</link>
        <description>Résumé du premier</description>
        <pubDate>Mon, 03 Nov 2026 10:00:00 GMT</pubDate>
        <category>tech</category></item>
  <item><title>Deuxième article</title><link>https://exemple.com/2</link></item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Flux Atom</title>
  <entry><title>Entrée A</title><link href="https://exemple.com/a"/>
         <summary>Résumé A</summary>
         <updated>2026-11-04T08:00:00Z</updated></entry>
</feed>"""


# --------------------------------------------------------------------------- #
# utils
# --------------------------------------------------------------------------- #
def test_size_human():
    assert utils.size_human(512) == "512 o"
    assert utils.size_human(2048) == "2.0 Ko"
    assert utils.size_human(5 * 1024 * 1024) == "5.0 Mo"


def test_truncate():
    assert utils.truncate("abc", 10) == "abc"
    assert utils.truncate("a" * 20, 10).endswith("…")
    assert len(utils.truncate("a" * 20, 10)) == 10


def test_write_and_read_json(tmp_path):
    path = tmp_path / "sub" / "data.json"
    utils.write_json(path, {"a": 1})
    assert utils.read_json(path) == {"a": 1}
    assert utils.read_json(tmp_path / "absent.json", default={}) == {}


# --------------------------------------------------------------------------- #
# feeds
# --------------------------------------------------------------------------- #
def test_parse_rss():
    items = feeds.parse_feed(RSS)
    assert len(items) == 2
    assert items[0].title == "Premier article"
    assert items[0].source == "Mon flux"
    assert items[0].published is not None
    assert items[0].tags == ["tech"]


def test_parse_atom():
    items = feeds.parse_feed(ATOM)
    assert len(items) == 1
    assert items[0].link == "https://exemple.com/a"
    assert items[0].source == "Flux Atom"
    assert items[0].published is not None


def test_fetch_all_ignore_les_flux_casses():
    assert feeds.fetch_all(["http://127.0.0.1:9/inexistant"], timeout=1) == []


# --------------------------------------------------------------------------- #
# veille_agent
# --------------------------------------------------------------------------- #
def test_dedupe_et_selection():
    items = feeds.parse_feed(RSS)
    assert len(veille_agent.dedupe(items + items)) == 2

    new = veille_agent.select_new(items, seen={"https://exemple.com/1"})
    assert [i.title for i in new] == ["Deuxième article"]


def test_select_new_limite_par_source():
    items = feeds.parse_feed(RSS)
    assert len(veille_agent.select_new(items, seen=set(), max_per_feed=1)) == 1


def test_render_markdown_vide():
    md = veille_agent.render_markdown([], 3)
    assert "Aucune nouveauté" in md
    assert "3 article(s) déjà connus" in md


def test_agent_veille_bout_en_bout(tmp_path):
    feed_file = tmp_path / "feed.xml"
    feed_file.write_text(RSS, encoding="utf-8")
    sources = tmp_path / "feeds.txt"
    sources.write_text(f"# commentaire\n{feed_file}\n", encoding="utf-8")

    # un fichier local n'est pas une URL : on court-circuite le réseau
    items = feeds.parse_feed(RSS)
    state = tmp_path / "state.json"
    out = tmp_path / "veille.md"

    new = veille_agent.select_new(items, set())
    utils.write_text(out, veille_agent.render_markdown(new, 0))
    utils.write_json(state, {"seen": [veille_agent.item_key(i) for i in items]})

    assert "Premier article" in out.read_text(encoding="utf-8")
    assert utils.read_json(state)["seen"]


def test_load_sources_fichier(tmp_path):
    path = tmp_path / "f.txt"
    path.write_text("# c\nhttps://a.com/rss\n\nhttps://b.com/rss\n", encoding="utf-8")
    assert veille_agent.load_sources(path) == ["https://a.com/rss", "https://b.com/rss"]
    assert veille_agent.load_sources("https://c.com/rss") == ["https://c.com/rss"]


def test_load_sources_absent(tmp_path):
    with pytest.raises(FileNotFoundError):
        veille_agent.load_sources(tmp_path / "nope.txt")


# --------------------------------------------------------------------------- #
# rapport_agent
# --------------------------------------------------------------------------- #
def test_collect_dossier_et_todos(tmp_path):
    (tmp_path / "2026-11-03-a.md").write_text("# Réunion\nTODO: faire X\n", encoding="utf-8")
    entries = rapport_agent.collect(tmp_path)
    assert len(entries) == 1
    assert entries[0].title == "Réunion"
    assert entries[0].todos == ["faire X"]
    assert entries[0].date.year == 2026


def test_collect_json(tmp_path):
    path = tmp_path / "a.json"
    path.write_text('{"entries":[{"title":"T","body":"b","date":"2026-11-06T09:00:00"}]}',
                    encoding="utf-8")
    entries = rapport_agent.collect(path)
    assert entries[0].title == "T"
    assert entries[0].date.day == 6


def test_collect_csv(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("title,body,todo\nTitre,Corps,Tâche\n", encoding="utf-8")
    entries = rapport_agent.collect(path)
    assert entries[0].todos == ["Tâche"]


def test_keywords_ignore_stopwords():
    entries = [rapport_agent.Entry("s", "API", None, "api serveur api le la")]
    words = dict(rapport_agent.keywords(entries))
    assert words["api"] == 3
    assert "le" not in words


def test_build_report_et_markdown(tmp_path):
    entries = rapport_agent.collect(ROOT / "data" / "notes")
    report = rapport_agent.build_report(entries, "Test")
    assert report["counts"]["entries"] == 2
    assert report["counts"]["todos"] == 3
    md = rapport_agent.render_markdown(report)
    assert "# 📊 Test" in md
    assert "- [ ]" in md


def test_rapport_run(tmp_path):
    out = tmp_path / "r.md"
    report = rapport_agent.run(str(ROOT / "data" / "notes"), str(out),
                               str(tmp_path / "r.json"), "Rapport test")
    assert out.exists()
    assert report["title"] == "Rapport test"


def test_rapport_source_absente(tmp_path):
    with pytest.raises(FileNotFoundError):
        rapport_agent.run(str(tmp_path / "absent"), str(tmp_path / "x.md"))


# --------------------------------------------------------------------------- #
# triage_agent
# --------------------------------------------------------------------------- #
def test_score_urgent_et_securite():
    score, priority, category = triage_agent.score_ticket(
        "Fuite d'accès possible, problème de sécurité urgent !")
    assert priority == "critique"
    assert category == "Sécurité"
    assert score >= 7


def test_score_question_basse():
    _, priority, category = triage_agent.score_ticket("Comment changer mon mot de passe ?")
    assert priority in ("basse", "moyenne")
    assert category == "Support"


def test_score_facturation():
    _, _, category = triage_agent.score_ticket("Le montant de la facture est faux")
    assert category == "Facturation"


def test_triage_tri_par_priorite():
    rows = [{"title": "suggestion de documentation"},
            {"title": "panne critique urgente, service indisponible !!!"}]
    result = triage_agent.triage_rows(rows)
    assert result[0]["priority"] == "critique"


def test_triage_run_et_filtre(tmp_path):
    out = tmp_path / "out.csv"
    md = tmp_path / "out.md"
    rows = triage_agent.run(str(ROOT / "data" / "tickets.csv"), str(out), str(md))
    assert len(rows) == 8
    assert out.exists() and md.exists()

    filtered = triage_agent.run(str(ROOT / "data" / "tickets.csv"),
                                str(tmp_path / "f.csv"), None, min_priority="haute")
    assert all(r["priority"] in ("haute", "critique") for r in filtered)
    assert len(filtered) < len(rows)


# --------------------------------------------------------------------------- #
# backup_rotation
# --------------------------------------------------------------------------- #
def test_backup_creation_et_integrite(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("hello", encoding="utf-8")
    dest = tmp_path / "backups"

    result = backup_rotation.run(str(src), str(dest), keep=3)
    assert result["verified"] is True
    assert Path(result["archive"]).exists()
    assert (dest / "manifest.json").exists()


def test_backup_rotation_garde_les_derniers(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x", encoding="utf-8")
    dest = tmp_path / "backups"
    dest.mkdir()
    for i in range(5):
        (dest / f"vieux{i}.zip").write_bytes(b"x")
        (dest / f"vieux{i}.zip").touch()
        import os
        os.utime(dest / f"vieux{i}.zip", (1_600_000_000 + i, 1_600_000_000 + i))

    backup_rotation.run(str(src), str(dest), keep=2)
    assert len(list(dest.glob("*.zip"))) == 2


def test_backup_dry_run_ne_cree_rien(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x", encoding="utf-8")
    dest = tmp_path / "backups"
    result = backup_rotation.run(str(src), str(dest), dry_run=True)
    assert result["dry_run"] is True
    assert not dest.exists()


def test_backup_source_invalide(tmp_path):
    with pytest.raises(NotADirectoryError):
        backup_rotation.run(str(tmp_path / "nope"), str(tmp_path / "b"))


# --------------------------------------------------------------------------- #
# clean_workspace
# --------------------------------------------------------------------------- #
def test_find_targets(tmp_path):
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "a.pyc").write_bytes(b"x")
    (tmp_path / "keep.txt").write_text("ok", encoding="utf-8")
    (tmp_path / "run.log").write_text("log", encoding="utf-8")

    names = {p.name for p in clean_workspace.find_targets(tmp_path)}
    assert "__pycache__" in names
    assert "run.log" in names
    assert "keep.txt" not in names


def test_clean_dry_run_ne_bouge_rien(tmp_path):
    (tmp_path / "a.log").write_text("x", encoding="utf-8")
    result = clean_workspace.run(str(tmp_path), dry_run=True)
    assert result["found"] == 1
    assert (tmp_path / "a.log").exists()


def test_clean_deplace_dans_corbeille(tmp_path):
    (tmp_path / "a.log").write_text("x", encoding="utf-8")
    trash = tmp_path / "trash"
    result = clean_workspace.run(str(tmp_path), dry_run=False, trash_dir=str(trash))
    assert result["moved"] == ["a.log"]
    assert not (tmp_path / "a.log").exists()
    assert list(trash.rglob("a.log"))


# --------------------------------------------------------------------------- #
# watch_folder
# --------------------------------------------------------------------------- #
def test_new_files_detecte_apparition_et_modification():
    previous = {"a.txt": 1.0, "b.txt": 1.0}
    current = {"a.txt": 2.0, "b.txt": 1.0, "c.txt": 1.0}
    assert __import__("watch_folder").new_files(previous, current) == ["a.txt", "c.txt"]


def test_build_command_substitue_les_variables(tmp_path):
    import watch_folder
    cmd = watch_folder.build_command("echo {name} {dir}", tmp_path / "f.txt")
    assert cmd[1] == "f.txt"
    assert cmd[2] == str(tmp_path)


def test_watch_once_execute(tmp_path):
    import watch_folder
    (tmp_path / "new.txt").write_text("x", encoding="utf-8")
    marker = tmp_path / "done.txt"
    count = watch_folder.run(str(tmp_path), f'python -c "print(1)"',
                             interval=0.01, once=True, ignore_existing=False)
    assert count == 1
    assert not marker.exists()
