"""Deterministische Wissenssynchronisation fuer HPG-VERITAS.

Ohne ``--apply`` wird ausschliesslich ein Plan ausgegeben. Das Skript loescht
nie Dateien und schreibt nie in ``_raw`` oder ``00_Claude_Memory``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from tools.audit.veritas import (
        AUDIT_ROOT,
        REPO_ROOT,
        READABLE_SCHEMA_VERSIONS,
        SCHEMA_VERSION,
        VeritasError,
        evidence_markdown,
        read_json,
    )
except ModuleNotFoundError:  # direkter Aufruf aus tools/audit
    from veritas import (  # type: ignore[no-redef]
        AUDIT_ROOT,
        REPO_ROOT,
        READABLE_SCHEMA_VERSIONS,
        SCHEMA_VERSION,
        VeritasError,
        evidence_markdown,
        read_json,
    )


FINDING_ID = re.compile(r"V-\d{3,}")
LEARNING_ID = re.compile(r"L-\d{3,}")
USER_STATUSES = {
    "offen",
    "behoben",
    "falsch-positiv",
    "akzeptiert",
    "unbestaetigt",
    "widerspruch",
}
PROTECTED_VAULT_PARTS = {
    "_raw",
    "00_claude_memory",
    "claude-autopilot-v5",
    "claude-autopilot-v6",
    "claude-autopilot-v6.zip",
}
GENERATED_START = "<!-- VERITAS:GENERATED:START -->"
GENERATED_END = "<!-- VERITAS:GENERATED:END -->"


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = content.rstrip() + "\n"
    handle, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(normalized)
        os.replace(temp_name, path)
    except BaseException:
        try:
            Path(temp_name).unlink(missing_ok=True)
        finally:
            raise


def _windows_name(part: str) -> str:
    """Windows ignoriert Punkte und Leerzeichen am Namensende.

    Ohne das Abstreifen passiert '_raw.' die Schutzliste und landet beim
    Aufloesen doch in '_raw'.
    """
    return part.rstrip(". ").casefold()


def frontmatter_value(text: str, key: str) -> str | None:
    # Notepad und PowerShell 5.1 schreiben UTF-8 mit BOM; ohne das Abstreifen
    # galt das Frontmatter als nicht vorhanden und der Nutzerstatus fiel
    # stillschweigend auf den Vorgabewert zurueck.
    text = text.lstrip("﻿")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    pattern = re.compile(rf"^{re.escape(key)}:\s*[\"']?([^\n\"']+)[\"']?\s*$", re.MULTILINE)
    match = pattern.search(text[4:end])
    return match.group(1).strip() if match else None


def user_comment(text: str) -> str:
    """Nutzerkommentar hinter dem generierten Block.

    Die Suche beginnt erst nach GENERATED_END: sonst trifft sie die
    Zeichenfolge in einem Evidenz-Zitat, und die Notiz waechst bei jedem
    Lauf um einen weiteren Block.
    """
    marker = "## Nutzerkommentar"
    ende = text.find(GENERATED_END)
    ab = (ende + len(GENERATED_END)) if ende >= 0 else 0
    start = text.find(marker, ab)
    if start < 0:
        return ""
    body_start = start + len(marker)
    return text[body_start:].lstrip("\r\n").rstrip()


def safe_vault_dir(config: dict[str, Any]) -> Path:
    root = Path(str(config.get("vault_root", "")))
    relative = Path(str(config.get("vault_audit_dir", "")))
    if not root.is_absolute():
        raise VeritasError("vault_root muss absolut sein")
    if relative.is_absolute() or ".." in relative.parts:
        raise VeritasError("vault_audit_dir muss sicher relativ sein")
    resolved = (root / relative).resolve()
    # Roh UND aufgeloest pruefen: '_raw.' passiert sonst die Liste und landet
    # beim Aufloesen doch in '_raw'.
    lowered = {
        _windows_name(part)
        for part in (*root.parts, *relative.parts, *resolved.parts)
    }
    if lowered & PROTECTED_VAULT_PARTS:
        raise VeritasError("Geschuetztes Vault-Ziel ist verboten")
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise VeritasError("Vault-Ziel verlaesst vault_root") from exc
    return resolved


def safe_project_target(repo: Path, raw: str) -> Path:
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise VeritasError(f"Unsicheres Projektziel: {raw}")
    resolved = (repo / relative).resolve()
    try:
        rel = resolved.relative_to(repo.resolve())
    except ValueError as exc:
        raise VeritasError(f"Projektziel verlaesst Repository: {raw}") from exc
    allowed = (
        Path("tools/audit"),
        Path(".agents/skills/hpg-veritas"),
        Path(".claude/skills/hpg-veritas"),
    )
    if not any(rel == prefix or prefix in rel.parents for prefix in allowed):
        raise VeritasError(f"Projektziel nicht freigegeben: {raw}")
    return resolved


def canonical_user_status(finding: dict[str, Any]) -> str:
    status = finding.get("status")
    if status == "BESTAETIGT":
        return "offen"
    if status == "WIDERSPRUCH":
        return "widerspruch"
    return "unbestaetigt"


def render_finding_note(
    finding: dict[str, Any], existing: str, generated_at: str
) -> tuple[str | None, str | dict[str, Any] | None]:
    """Notizinhalt und Drift, ODER (None, Konflikt).

    Ein Konflikt bedeutet: die vorhandene Notiz gehoert dem Nutzer und wird
    nicht angefasst -- fremder Fingerprint oder unbekannter Statuswert.
    """
    default_status = canonical_user_status(finding)
    saved_status = frontmatter_value(existing, "status") if existing else None
    alter_fp = frontmatter_value(existing, "fingerprint") if existing else None
    fingerprint = str(finding.get("fingerprint", ""))
    # Fremde Notiz unter derselben ID: nichts uebernehmen, sonst erbt ein
    # offener Befund den Status "behoben" eines ganz anderen.
    fremde_notiz = bool(existing) and alter_fp is not None and alter_fp != fingerprint
    if fremde_notiz:
        return None, {
            "id": finding["id"],
            "grund": "fremder Fingerprint",
            "notiz_fingerprint": alter_fp,
            "befund_fingerprint": fingerprint,
        }
    normalisiert = saved_status.casefold() if isinstance(saved_status, str) else None
    schreibweise_geaendert = (
        isinstance(saved_status, str)
        and normalisiert in USER_STATUSES
        and saved_status != normalisiert
    )
    if normalisiert in USER_STATUSES:
        status = normalisiert
    elif saved_status is not None and existing:
        # C6: ein unbekannter Wert wurde bisher kommentarlos ersetzt.
        return None, {
            "id": finding["id"],
            "grund": "unbekannter Statuswert",
            "vorgefunden": saved_status,
        }
    else:
        status = default_status
    comment = user_comment(existing) if existing else ""
    drift = status if status != default_status else None
    if schreibweise_geaendert:
        # Nutzertext wird kleingeschrieben zurueckgeschrieben -- das ist eine
        # Aenderung an seiner Datei und gehoert gemeldet.
        drift = drift or status
    if existing and alter_fp is None:
        # Erstmigration: die Notiz stammt aus der Zeit ohne Fingerprint.
        drift = drift or status
    tags = f"[veritas, audit, {str(finding.get('category', '')).casefold().replace(' ', '-')}]"
    content = f"""---
type: audit-finding
project: HarmonicPlaylistGenerator
id: {finding['id']}
fingerprint: {fingerprint}
status: {status}
severity: {finding['severity']}
kategorie: {finding['category']}
datei: {finding['path']}
pass_quote: {finding['pass_quote']}
konfidenz: {finding['confidence']}
updated: {generated_at}
tags: {tags}
---

# {finding['id']} - {finding['claim']}

{GENERATED_START}

## Befund

- Status im Merge: {finding['merge_status']}
- Status nach Verifikator: {finding['verifier_status']}
- Datei: `{finding['path']}:{finding['line_start']}`
- Regel: `{finding['rule']}`
- Auswirkung: {finding['impact']}
- Reproduziert: {finding['pass_quote']}

## Beweis

{evidence_markdown(finding)}

{GENERATED_END}

## Nutzerkommentar

{comment}
"""
    return content, drift


def validate_learnings(data: dict[str, Any], finding_ids: set[str]) -> list[dict[str, Any]]:
    if data.get("schema_version") not in READABLE_SCHEMA_VERSIONS:
        raise VeritasError("learnings.json: falsche schema_version")
    raw = data.get("learnings")
    if not isinstance(raw, list):
        raise VeritasError("learnings.json: learnings muss Liste sein")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, learning in enumerate(raw):
        if not isinstance(learning, dict):
            raise VeritasError(f"learnings[{index}] muss Objekt sein")
        learning_id = learning.get("id")
        if not isinstance(learning_id, str) or not LEARNING_ID.fullmatch(learning_id):
            raise VeritasError(f"learnings[{index}].id ungueltig")
        if learning_id in seen:
            raise VeritasError(f"Doppelte Learning-ID: {learning_id}")
        seen.add(learning_id)
        sources = learning.get("sources")
        if not isinstance(sources, list) or not sources:
            raise VeritasError(f"{learning_id}: sources fehlen")
        invalid_sources = [
            source
            for source in sources
            if not isinstance(source, str) or not FINDING_ID.fullmatch(source)
        ]
        if invalid_sources:
            raise VeritasError(f"{learning_id}: ungueltige Quellen {invalid_sources}")
        unknown_sources = [source for source in sources if source not in finding_ids]
        if unknown_sources:
            raise VeritasError(
                f"{learning_id}: Quellen ohne Befund im Lauf {sorted(unknown_sources)}"
            )
        for key in ("situation", "rule", "counterexample"):
            if not isinstance(learning.get(key), str) or not learning[key].strip():
                raise VeritasError(f"{learning_id}: {key} fehlt")
        tags = learning.get("tags")
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise VeritasError(f"{learning_id}: tags muss String-Liste sein")
        if learning.get("status") not in {"aktiv", "review", "archiviert"}:
            raise VeritasError(f"{learning_id}: status ungueltig")
        for key in ("applied", "hits"):
            if not isinstance(learning.get(key), int) or learning[key] < 0:
                raise VeritasError(f"{learning_id}: {key} muss nichtnegativer Integer sein")
        if learning["hits"] > learning["applied"]:
            raise VeritasError(f"{learning_id}: hits darf applied nicht uebersteigen")
        applications = learning.get("applications", [])
        if not isinstance(applications, list):
            raise VeritasError(f"{learning_id}: applications muss Liste sein")
        application_ids = [
            application.get("application_id")
            for application in applications
            if isinstance(application, dict)
        ]
        if len(application_ids) != len(applications) or len(set(application_ids)) != len(
            application_ids
        ):
            raise VeritasError(f"{learning_id}: applications ungueltig oder doppelt")
        if learning["applied"] != len(applications):
            raise VeritasError(f"{learning_id}: applied stimmt nicht mit applications ueberein")
        counted_hits = sum(
            1
            for application in applications
            if application.get("result") == "treffer"
        )
        if learning["hits"] != counted_hits:
            raise VeritasError(f"{learning_id}: hits stimmt nicht mit applications ueberein")
        result.append(learning)
    return result


def render_learning_note(learning: dict[str, Any], generated_at: str) -> str:
    sources = ", ".join(f"[[../Befunde/{source}|{source}]]" for source in learning["sources"])
    tags = ", ".join(learning["tags"])
    return f"""---
type: learning
project: HarmonicPlaylistGenerator
id: {learning['id']}
status: {learning['status']}
sources: [{', '.join(learning['sources'])}]
tags: [{tags}]
applied: {learning['applied']}
hits: {learning['hits']}
updated: {generated_at}
---

# {learning['id']}

## Situation

{learning['situation']}

## Regel

{learning['rule']}

## Gegenbeispiel

{learning['counterexample']}

## Quellen

{sources}
"""


def render_moc(
    findings: list[dict[str, Any]], learnings: list[dict[str, Any]], generated_at: str
) -> str:
    lines = [
        "---",
        "type: map-of-content",
        "project: HarmonicPlaylistGenerator",
        "tags: [veritas, audit]",
        f"updated: {generated_at}",
        "---",
        "",
        "# VERITAS Audit MOC",
        "",
        "## Befunde",
        "",
        "| ID | Status | Severity | Kategorie | Datei | Paesse |",
        "|---|---|---|---|---|---:|",
    ]
    for finding in findings:
        lines.append(
            f"| [[Befunde/{finding['id']}|{finding['id']}]] | {finding['status']} | "
            f"{finding['severity']} | {finding['category']} | `{finding['path']}` | {finding['pass_quote']} |"
        )
    lines.extend(["", "## Learnings", ""])
    if learnings:
        lines.extend(f"- [[Learnings/{learning['id']}|{learning['id']}]]" for learning in learnings)
    else:
        lines.append("Keine.")
    return "\n".join(lines)


def render_lessons(learnings: list[dict[str, Any]]) -> str:
    lines = ["# VERITAS Lessons", "", "Generiert aus validiertem `learnings.json`.", ""]
    active = [learning for learning in learnings if learning["status"] in {"aktiv", "review"}]
    if not active:
        lines.append("Noch keine bestaetigten Learnings.")
    for learning in active:
        lines.extend(
            [
                f"## {learning['id']} [{learning['status']}]",
                "",
                f"- Regel: {learning['rule']}",
                f"- Quellen: {', '.join(learning['sources'])}",
                f"- Anwendungen/Treffer: {learning['applied']}/{learning['hits']}",
                "",
            ]
        )
    return "\n".join(lines)


def render_active_learnings(learnings: list[dict[str, Any]], max_lines: int) -> str:
    lines = ["# Aktive VERITAS-Learnings", ""]
    active = [learning for learning in learnings if learning["status"] == "aktiv"]
    if not active:
        lines.append("Noch keine bestaetigten Learnings.")
    else:
        # Die zwei Kopfzeilen zaehlten im Limit mit: von 25 aktiven Regeln
        # landeten 18 in der Datei, ohne jeden Hinweis auf den Rest.
        geschrieben = 0
        for learning in active:
            if len(lines) >= max_lines - 1:
                break
            lines.append(f"- {learning['id']}: {learning['rule']}")
            geschrieben += 1
        if geschrieben < len(active):
            lines.append(
                f"- ... {len(active) - geschrieben} weitere, siehe LESSONS.md"
            )
    return "\n".join(lines)


def report_path(run_dir: Path) -> Path:
    reports = sorted(run_dir.glob("AUDIT_REPORT_*.md"))
    if len(reports) != 1:
        raise VeritasError("Lauf braucht genau einen AUDIT_REPORT_*.md")
    return reports[0]


def active_learning_targets(config: dict[str, Any]) -> list[str]:
    """Ein Ziel oder mehrere Spiegel; jeder Eintrag bekommt denselben Inhalt."""
    raw = config.get("active_learnings")
    targets = [raw] if isinstance(raw, str) else raw
    if not isinstance(targets, list) or not targets:
        raise VeritasError("active_learnings: String oder nichtleere Liste erforderlich")
    if not all(isinstance(target, str) and target.strip() for target in targets):
        raise VeritasError("active_learnings: nur nichtleere Pfad-Strings erlaubt")
    if len(set(targets)) != len(targets):
        raise VeritasError("active_learnings: doppelte Ziele")
    return targets


def build_expected(
    run_dir: Path, repo: Path, config: dict[str, Any]
) -> tuple[
    dict[Path, str], list[dict[str, Any]], list[str], list[dict[str, Any]]
]:
    canonical = read_json(run_dir / "findings.json")
    verifier_context = canonical.get("verifier_context_id")
    if not isinstance(verifier_context, str) or not verifier_context.strip():
        raise VeritasError("Unabhaengiges Verifikatorurteil fehlt")
    generated_at = str(
        canonical.get("verifier_applied_at")
        or canonical.get("generated_at")
        or "UNKNOWN"
    )
    findings = canonical.get("findings")
    if not isinstance(findings, list):
        raise VeritasError("findings.json: findings muss Liste sein")
    pending_verifier = [
        finding.get("id", "UNBEKANNT")
        for finding in findings
        if isinstance(finding, dict)
        and finding.get("merge_status") == "BESTAETIGT"
        and (
            finding.get("verifier_status") != "AKZEPTIERT"
            or finding.get("status") != "BESTAETIGT"
        )
    ]
    if pending_verifier:
        raise VeritasError(
            "Bestaetigte Merge-Kandidaten ohne Verifikator-Akzeptanz: "
            + ", ".join(str(value) for value in pending_verifier)
        )
    ids = {finding.get("id") for finding in findings if isinstance(finding, dict)}
    if len(ids) != len(findings) or not all(isinstance(value, str) and FINDING_ID.fullmatch(value) for value in ids):
        raise VeritasError("findings.json: ungueltige oder doppelte IDs")
    learning_data = read_json(run_dir / "learnings.json")
    learnings = validate_learnings(learning_data, set(ids))
    report = report_path(run_dir)
    report_text = report.read_text(encoding="utf-8")
    missing_report_ids = sorted(value for value in ids if value not in report_text)
    if missing_report_ids:
        raise VeritasError("Bericht enthaelt IDs nicht: " + ", ".join(missing_report_ids))

    vault_dir = safe_vault_dir(config)
    expected: dict[Path, str] = {}
    status_drifts: list[dict[str, Any]] = []
    konflikte: list[dict[str, Any]] = []
    for finding in findings:
        target = vault_dir / "Befunde" / f"{finding['id']}.md"
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
        content, drift = render_finding_note(finding, existing, generated_at)
        if content is None:
            # Fremder Fingerprint oder unbekannter Statuswert: die Notiz
            # gehoert dem Nutzer und wird nicht angefasst.
            konflikte.append({**drift, "pfad": str(target)})
            continue
        expected[target] = content
        if drift:
            status_drifts.append(
                {"id": finding["id"], "vault_status": drift, "audit_status": finding["status"]}
            )
    for learning in learnings:
        expected[vault_dir / "Learnings" / f"{learning['id']}.md"] = render_learning_note(
            learning, generated_at
        )
    expected[vault_dir / "AUDIT-MOC.md"] = render_moc(findings, learnings, generated_at)
    expected[safe_project_target(repo, str(config["project_lessons"]))] = render_lessons(learnings)
    expected[safe_project_target(repo, str(config["project_learnings"]))] = (
        json.dumps(learning_data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    max_lines = int(config.get("max_active_learning_lines", 20))
    active_text = render_active_learnings(learnings, max_lines)
    for raw_target in active_learning_targets(config):
        expected[safe_project_target(repo, raw_target)] = active_text

    orphans: list[str] = []
    for directory, pattern, known in (
        (vault_dir / "Befunde", "V-*.md", set(ids)),
        (vault_dir / "Learnings", "L-*.md", {learning["id"] for learning in learnings}),
    ):
        if directory.is_dir():
            for path in directory.glob(pattern):
                if path.stem not in known:
                    orphans.append(str(path))
    return expected, status_drifts, sorted(orphans), konflikte


def diff_plan(expected: dict[Path, str], orphans: list[str]) -> dict[str, Any]:
    changes: list[dict[str, str]] = []
    for path, content in expected.items():
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        normalized = content.rstrip() + "\n"
        if current != normalized:
            changes.append({"action": "create" if current is None else "update", "path": str(path)})
    return {
        "changes": changes,
        "orphans": orphans,
        # Waisen zaehlen NICHT mit: --apply entfernt sie nie, der Zaehler
        # koennte sonst nie 0 werden und das Abschluss-Gate waere mit einer
        # einzigen Waise dauerhaft unerreichbar. Sie bleiben als eigener
        # Posten sichtbar und sind Handarbeit.
        "sync_difference_count": len(changes),
        "orphan_count": len(orphans),
    }


def command_sync(
    args: argparse.Namespace, config_path: Path | None = None
) -> int:
    run_dir = Path(args.run_dir).resolve()
    repo = Path(args.repo).resolve()
    # Das CLI bietet bewusst keinen Konfigurationsschalter (siehe SKILL.md);
    # ein abweichendes Profil kann nur programmatisch uebergeben werden.
    resolved = config_path if config_path is not None else AUDIT_ROOT / "sync_targets.json"
    config = read_json(Path(resolved).resolve())
    expected, status_drifts, orphans, konflikte = build_expected(run_dir, repo, config)
    before = diff_plan(expected, orphans)
    geschrieben: list[str] = []
    if args.apply:
        # Nicht transaktional ueber mehrere Dateien: bricht ein Schreibvorgang
        # ab, muss der Teilzustand sichtbar sein statt still zu bleiben.
        try:
            for path, content in expected.items():
                atomic_write(path, content)
                geschrieben.append(str(path))
        except OSError as exc:
            print(json.dumps({
                "mode": "apply",
                "abgebrochen_nach": geschrieben,
                "fehler": str(exc),
            }, ensure_ascii=False, indent=2))
            raise VeritasError(
                f"Sync nach {len(geschrieben)} von {len(expected)} Dateien "
                f"abgebrochen: {exc}"
            ) from exc
    after = diff_plan(expected, orphans)
    payload = {
        "mode": "apply" if args.apply else "dry-run",
        "planned": before,
        "after": after,
        "user_status_pending_verification": status_drifts,
        # Notizen, die dem Nutzer gehoeren und deshalb nicht angefasst wurden.
        "konflikte": konflikte,
        "complete": bool(
            args.apply
            and after["sync_difference_count"] == 0
            and not konflikte
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.apply and (after["sync_difference_count"] != 0 or konflikte):
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HPG VERITAS Wissens-Sync")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--repo", default=str(REPO_ROOT))
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return command_sync(args)
    except VeritasError as exc:
        print(f"VERITAS_SYNC_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
