"""Formaler Fail-Closed-Validator fuer Berichte von hpg-waechter."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

VALID_VERDICTS = {"DURCHGEWUNKEN", "MIT AUFLAGEN", "ZURUECKGEWIESEN"}
COMMON_CONTRACT_FIELDS = (
    "tor", "auftrag", "akzeptanzkriterien", "erlaubte_dateien",
    "verbotene_dateien", "referenzen", "invarianten", "testbelege",
)
TOR_2_CONTRACT_FIELDS = ("tor_1_urteil", "diff_bereich")
REQUIRED_SECTIONS = (
    "Pruefvertrag", "Urteil", "Vertragspruefung", "Belegmatrix", "Befunde",
    "Nicht geprueft",
)
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
FIELD_RE = re.compile(r"^-\s*([a-z0-9_]+):\s*(\S.*)$", re.MULTILINE)
EVIDENCE_RE = re.compile(
    r"^-\s*Pruefpunkt:\s*\S.+?\s*\|\s*Beleg:\s*[^|\n]+:\d+\s*"
    r"\|\s*Ergebnis:\s*(erfuellt|nicht erfuellt)$",
    re.MULTILINE,
)
FINDING_RE = re.compile(
    r"^###\s+Befund\s+\d+\s*$.*?^-\s*Schwere:\s*\S.+$.*?"
    r"^-\s*Beleg:\s*[^\n]+:\d+\s*$.*?^-\s*Szenario:\s*\S.+$.*?"
    r"^-\s*Korrektur:\s*(?:\S.+|keine)\s*$",
    re.MULTILINE | re.DOTALL,
)
DIFF_BEREICH_RE = re.compile(
    r"^(?:[A-Za-z0-9][A-Za-z0-9_./~^:-]*\.\.[A-Za-z0-9][A-Za-z0-9_./~^:-]*"
    r"|WORKING TREE:\s+\S.+)$"
)


def _sections(text: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(text))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        name = match.group(1).strip().replace("ü", "ue").replace("Ü", "Ue")
        stop = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result[name] = text[match.end():stop].strip()
    return result


def validate_report(text: str) -> list[str]:
    """Liefert alle formalen Verstoesse; leer bedeutet formell gueltig."""
    errors: list[str] = []
    sections = _sections(text)
    missing = [name for name in REQUIRED_SECTIONS if not sections.get(name)]
    if missing:
        return [f"Fehlende oder leere Pflichtabschnitte: {', '.join(missing)}"]

    contract = dict(FIELD_RE.findall(sections["Pruefvertrag"]))
    missing_fields = [field for field in COMMON_CONTRACT_FIELDS if not contract.get(field)]
    tor = contract.get("tor", "")
    if tor not in {"TOR 1", "TOR 2"}:
        errors.append("Pruefvertrag: tor muss exakt TOR 1 oder TOR 2 sein")
    if tor == "TOR 2":
        missing_fields.extend(field for field in TOR_2_CONTRACT_FIELDS if not contract.get(field))
        tor_1_urteil = contract.get("tor_1_urteil", "")
        if tor_1_urteil != "DURCHGEWUNKEN":
            errors.append("Pruefvertrag: TOR 2 verlangt ein DURCHGEWUNKENES Tor-1-Urteil")
        diff_bereich = contract.get("diff_bereich", "")
        if diff_bereich and not DIFF_BEREICH_RE.fullmatch(diff_bereich):
            errors.append("Pruefvertrag: diff_bereich muss Git-Range oder 'WORKING TREE: <Beschreibung>' sein")
    if missing_fields:
        errors.append("Pruefvertrag: fehlende Pflichtfelder: " + ", ".join(sorted(set(missing_fields))))

    verdicts = re.findall(r"^\s*(DURCHGEWUNKEN|MIT AUFLAGEN|ZURUECKGEWIESEN)\s*$", sections["Urteil"], re.MULTILINE)
    if len(verdicts) != 1 or verdicts[0] not in VALID_VERDICTS:
        errors.append("Urteil: exakt ein gueltiges Urteil erforderlich")
        verdict = ""
    else:
        verdict = verdicts[0]

    evidence = EVIDENCE_RE.findall(sections["Belegmatrix"])
    if not evidence:
        errors.append("Belegmatrix: mindestens ein Pruefpunkt mit datei:zeile erforderlich")
    if not FINDING_RE.search(sections["Befunde"]) and sections["Befunde"].strip() != "- keine":
        errors.append("Befunde: '- keine' oder vollstaendige Befundbloecke erforderlich")

    untested = sections["Nicht geprueft"].strip()
    if verdict == "DURCHGEWUNKEN":
        if untested != "- keine":
            errors.append("DURCHGEWUNKEN unzulaessig: Nicht geprueft muss '- keine' sein")
        if sections["Befunde"].strip() != "- keine":
            errors.append("DURCHGEWUNKEN unzulaessig: Befunde muss '- keine' sein")
        if any(result != "erfuellt" for result in evidence):
            errors.append("DURCHGEWUNKEN unzulaessig: Belegmatrix enthaelt offenen Pruefpunkt")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Markdown-Bericht des Waechters")
    args = parser.parse_args(argv)
    try:
        text = args.report.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Waechterbericht nicht lesbar: {exc}", file=sys.stderr)
        return 2
    errors = validate_report(text)
    if errors:
        print("Waechterbericht UNGUELTIG:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Waechterbericht formal gueltig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
