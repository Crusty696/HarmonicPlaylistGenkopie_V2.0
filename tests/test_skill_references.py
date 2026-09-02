"""Waechter gegen Doku-Drift in den Projekt-Skills.

Die Skills nannten frueher Zeilennummern (`analysis.py:1659`). Die altern mit
jedem Commit und waren zuletzt fast durchgehend falsch. Seit 2026-09-02 nennen
sie nur noch Symbol und Datei; diese Tests halten das durchsetzbar.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILL_ROOTS = (REPO / ".agents" / "skills", REPO / ".claude" / "skills")
# CLAUDE.md und AGENTS.md trugen dieselben veralteten Kennzahlen wie die Skills.
EXTRA_DOCS = (REPO / "CLAUDE.md", REPO / "AGENTS.md")

# `symbol` ... [pfad/zur/datei.py] — der Anker gilt fuer das letzte
# Backtick-Symbol vor der Klammer.
REFERENCE = re.compile(r"\[([A-Za-z_][\w./]*\.py)\]")
BACKTICKED = re.compile(r"`([^`]+)`")
# Verbotene Altform: datei.py:123 oder die dateilose Kurzform [:123]
LINE_REF_LONG = re.compile(r"[A-Za-z_][\w/]*\.py:\d+")
LINE_REF_SHORT = re.compile(r"(?<![\w.]):\d{1,6}\b")
# Zahlen, die mit jedem Commit veralten und deshalb nicht in Skills gehoeren.
VOLATILE = re.compile(
    r"\b\d{3,6} (?:Zeilen\b|Z\.|Tests\b|passed\b|bestanden\b)"
    r"|\b\d{1,3},\d{1,2} % Coverage\b"
)

SYMBOL = re.compile(r"^[A-Za-z_]\w*$")


def _skill_files() -> list[Path]:
    """Alle Markdown-Dateien beider Spiegel plus die beiden Projekt-Anweisungen."""
    files = [path for root in SKILL_ROOTS for path in sorted(root.rglob("*.md"))]
    files.extend(doc for doc in EXTRA_DOCS if doc.is_file())
    assert files, "Keine Skill-Dokumente gefunden — Pfade pruefen"
    return files


def _hpg_files() -> list[Path]:
    """Nur HPG-eigene Dokumente.

    Die Kennzahlen-Regel gilt fuer Aussagen ueber dieses Repo. Fachfremde
    Skills wie `consulting-team` duerfen Beispielzahlen nennen.
    """
    files = [path for path in _skill_files() if "consulting-team" not in path.parts]
    assert files, "Keine HPG-Dokumente gefunden — Pfade pruefen"
    return files


def _defines(source: str, symbol: str) -> bool:
    """Kommt das Symbol in dieser Datei als Definition oder Zuweisung vor?

    Bewusst weit: auch eine lokale Zuweisung zaehlt, damit ein Anker auf eine
    sprechende Variable (z. B. `mixpunkte_gueltig`) erlaubt bleibt. Der Test
    faengt damit Umbenennung und Verschieben, nicht die Sichtbarkeitsebene.
    """
    patterns = (
        rf"^\s*(?:async\s+)?def\s+{re.escape(symbol)}\b",
        rf"^\s*class\s+{re.escape(symbol)}\b",
        rf"^{re.escape(symbol)}\s*[:=]",
        rf"^\s*{re.escape(symbol)}\s*[:=]",
    )
    return any(re.search(p, source, re.MULTILINE) for p in patterns)


@pytest.mark.parametrize("skill", _skill_files(), ids=lambda p: str(p.relative_to(REPO)).replace("\\", "/"))
def test_skill_nennt_keine_zeilennummern(skill: Path) -> None:
    """Zeilennummern veralten schweigend — deshalb sind sie verboten."""
    text = skill.read_text(encoding="utf-8")
    treffer = LINE_REF_LONG.findall(text) + LINE_REF_SHORT.findall(text)
    assert not treffer, (
        f"{skill.relative_to(REPO)} nennt Zeilennummern: {treffer}. "
        "Stattdessen `symbol` [pfad/datei.py] schreiben."
    )


@pytest.mark.parametrize("skill", _hpg_files(), ids=lambda p: str(p.relative_to(REPO)).replace("\\", "/"))
def test_skill_nennt_keine_volatilen_kennzahlen(skill: Path) -> None:
    """Zeilenzahl, Testanzahl und Coverage gehoeren in den Messbefehl, nicht ins Dokument."""
    text = skill.read_text(encoding="utf-8")
    treffer = VOLATILE.findall(text)
    assert not treffer, f"{skill.relative_to(REPO)} nennt volatile Kennzahlen: {treffer}"


@pytest.mark.parametrize("skill", _skill_files(), ids=lambda p: str(p.relative_to(REPO)).replace("\\", "/"))
def test_symbolreferenzen_zeigen_auf_existierende_definition(skill: Path) -> None:
    fehler: list[str] = []
    for zeile_nr, zeile in enumerate(skill.read_text(encoding="utf-8").splitlines(), 1):
        for match in REFERENCE.finditer(zeile):
            rel = match.group(1)
            ziel = REPO / rel
            if not ziel.is_file():
                fehler.append(f"Zeile {zeile_nr}: Datei fehlt: {rel}")
                continue
            davor = zeile[: match.start()]
            kandidaten = [
                token.split("(")[0].split(".")[-1].strip()
                for token in BACKTICKED.findall(davor)
            ]
            kandidaten = [token for token in kandidaten if SYMBOL.match(token)]
            if not kandidaten:
                continue  # reine Dateiangabe ohne Symbol-Anker
            symbol = kandidaten[-1]
            if not _defines(ziel.read_text(encoding="utf-8", errors="replace"), symbol):
                fehler.append(f"Zeile {zeile_nr}: `{symbol}` nicht definiert in {rel}")
    assert not fehler, f"{skill.relative_to(REPO)}:\n  " + "\n  ".join(fehler)


def test_agents_und_claude_spiegel_sind_identisch() -> None:
    """Beide Spiegel muessen bitgleich sein, sonst liest Codex etwas anderes als Claude Code."""
    unterschiede: list[str] = []
    for teil in ("skills", "agents"):
        links, rechts = REPO / ".agents" / teil, REPO / ".claude" / teil
        namen = {p.relative_to(links) for p in links.rglob("*") if p.is_file()}
        namen |= {p.relative_to(rechts) for p in rechts.rglob("*") if p.is_file()}
        for name in sorted(namen):
            a, b = links / name, rechts / name
            if not a.is_file() or not b.is_file():
                unterschiede.append(f"{teil}/{name}: nur auf einer Seite")
            elif a.read_bytes() != b.read_bytes():
                unterschiede.append(f"{teil}/{name}: Inhalt weicht ab")
    assert not unterschiede, "Spiegel driften:\n  " + "\n  ".join(unterschiede)
