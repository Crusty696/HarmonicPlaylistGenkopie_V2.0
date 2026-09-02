"""Deterministischer Kern fuer HPG-VERITAS-Auditlaeufe.

Das Modul fuehrt keine frei formulierten Scannerbefehle aus. Es initialisiert
Laeufe, validiert bereits erhobene Evidenz, merged drei Paesse und bindet ein
unabhaengiges Verifikatorurteil ein.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_SEED = 20260831
REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_ROOT = Path(__file__).resolve().parent
LOCK_FILE = AUDIT_ROOT / "toolchain.lock.json"
SYNC_CONFIG_FILE = AUDIT_ROOT / "sync_targets.json"
PERSISTENT_LEARNINGS_FILE = AUDIT_ROOT / "learnings.json"
PASS_NAMES = ("pass-1", "pass-2", "pass-3")
AUDIT_ROLES = (
    "Statiker",
    "Dynamiker",
    "Audio/DSP",
    "Integration",
    "GUI/Threading",
)
SEVERITIES = {"P0", "P1", "P2", "P3"}
CONFIDENCES = {"hoch", "mittel", "niedrig"}
FORBIDDEN_FACT_WORDS = re.compile(
    r"\b(vermutlich|wahrscheinlich|duerfte|dürfte|scheint)\b", re.IGNORECASE
)
PROTECTED_PARTS = {
    ".git",
    ".pytest_tmp",
    "venv312",
    "claude-autopilot-v5",
    "claude-autopilot-v6",
    "claude-autopilot-v6.zip",
}
PROTECTED_SUFFIXES = {".db", ".db-wal", ".db-shm", ".lock", ".coverage"}


class VeritasError(RuntimeError):
    """Erwarteter, nutzerlesbarer VERITAS-Fehler."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise VeritasError(f"Datei fehlt: {path}") from exc
    except json.JSONDecodeError as exc:
        raise VeritasError(f"Ungueltiges JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise VeritasError(f"JSON-Wurzel muss Objekt sein: {path}")
    return data


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    return " ".join(value.split()).casefold()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_protected_relative(path: Path) -> bool:
    lowered = {part.casefold() for part in path.parts}
    if lowered & PROTECTED_PARTS:
        return True
    name = path.name.casefold()
    return any(name.endswith(suffix) for suffix in PROTECTED_SUFFIXES)


def resolve_repo_path(repo: Path, raw_path: str) -> tuple[Path | None, str | None]:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return None, "Pfad muss relativ zum Repository sein"
    resolved = (repo / candidate).resolve()
    try:
        relative = resolved.relative_to(repo.resolve())
    except ValueError:
        return None, "Pfad verlaesst das Repository"
    if is_protected_relative(relative):
        return None, "Pfad liegt in einem geschuetzten Bereich"
    return resolved, None


def exact_source_quote(path: Path, line_start: int, line_end: int) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    if line_start < 1 or line_end < line_start or line_end > len(lines):
        raise VeritasError(
            f"Ungueltiger Zeilenbereich {line_start}-{line_end} fuer {path}"
        )
    return "\n".join(lines[line_start - 1 : line_end])


def finding_fingerprint(finding: dict[str, Any]) -> str:
    material = "\x1f".join(
        (
            normalized(str(finding.get("path", ""))).replace("\\", "/"),
            normalized(str(finding.get("rule", ""))),
            normalized(str(finding.get("context", ""))),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _required_string(
    container: dict[str, Any], key: str, prefix: str, errors: list[str]
) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{prefix}.{key}: nichtleerer String erforderlich")
        return ""
    return value


def validate_evidence(
    evidence: Any, repo: Path, prefix: str, errors: list[str]
) -> None:
    if not isinstance(evidence, list) or not evidence:
        errors.append(f"{prefix}: mindestens ein Evidenzobjekt erforderlich")
        return
    for index, item in enumerate(evidence):
        item_prefix = f"{prefix}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_prefix}: Objekt erforderlich")
            continue
        kind = item.get("kind")
        if kind == "source":
            raw_path = _required_string(item, "path", item_prefix, errors)
            start = item.get("line_start")
            end = item.get("line_end")
            quote = item.get("quote")
            if not isinstance(start, int) or not isinstance(end, int):
                errors.append(f"{item_prefix}: line_start/line_end muessen Integer sein")
                continue
            resolved, path_error = resolve_repo_path(repo, raw_path)
            if path_error:
                errors.append(f"{item_prefix}.path: {path_error}")
                continue
            if resolved is None or not resolved.is_file():
                errors.append(f"{item_prefix}.path: Datei fehlt")
                continue
            try:
                actual = exact_source_quote(resolved, start, end)
            except (UnicodeDecodeError, VeritasError) as exc:
                errors.append(f"{item_prefix}: {exc}")
                continue
            if quote != actual:
                errors.append(f"{item_prefix}.quote: stimmt nicht exakt mit Quelle ueberein")
        elif kind in {"command", "test"}:
            for key in ("command", "cwd", "output", "output_sha256", "timestamp"):
                _required_string(item, key, item_prefix, errors)
            if not isinstance(item.get("exit_code"), int):
                errors.append(f"{item_prefix}.exit_code: Integer erforderlich")
            output = item.get("output")
            digest = item.get("output_sha256")
            if isinstance(output, str) and isinstance(digest, str):
                if sha256_text(output) != digest.casefold():
                    errors.append(f"{item_prefix}.output_sha256: Hash passt nicht zum Output")
        else:
            errors.append(f"{item_prefix}.kind: nur source, command oder test erlaubt")


def validate_pass_document(
    document: dict[str, Any], repo: Path, expected_pass: int | None = None
) -> list[str]:
    errors: list[str] = []
    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version: erwartet {SCHEMA_VERSION}")
    pass_id = document.get("pass_id")
    if pass_id not in {1, 2, 3}:
        errors.append("pass_id: 1, 2 oder 3 erforderlich")
    if expected_pass is not None and pass_id != expected_pass:
        errors.append(f"pass_id: erwartet {expected_pass}")
    _required_string(document, "agent_context_id", "pass", errors)
    if not isinstance(document.get("file_order_seed"), int):
        errors.append("pass.file_order_seed: Integer erforderlich")
    _required_string(document, "role", "pass", errors)
    role_results = document.get("role_results")
    if not isinstance(role_results, list):
        errors.append("role_results: Liste erforderlich")
    else:
        seen_roles: set[str] = set()
        for index, result in enumerate(role_results):
            prefix = f"role_results[{index}]"
            if not isinstance(result, dict):
                errors.append(f"{prefix}: Objekt erforderlich")
                continue
            role = result.get("role")
            if role not in AUDIT_ROLES:
                errors.append(f"{prefix}.role: unbekannte Fachrolle")
            elif role in seen_roles:
                errors.append(f"{prefix}.role: doppelte Fachrolle")
            else:
                seen_roles.add(role)
            if result.get("status") not in {"completed", "not_applicable"}:
                errors.append(f"{prefix}.status: completed oder not_applicable erforderlich")
            _required_string(result, "note", prefix, errors)
            checked_scope = result.get("checked_scope")
            if (
                not isinstance(checked_scope, list)
                or not checked_scope
                or not all(isinstance(entry, str) and entry.strip() for entry in checked_scope)
            ):
                errors.append(f"{prefix}.checked_scope: nichtleere String-Liste erforderlich")
        missing_roles = sorted(set(AUDIT_ROLES) - seen_roles)
        if missing_roles:
            errors.append("role_results: Rollen fehlen: " + ", ".join(missing_roles))
    findings = document.get("findings")
    if not isinstance(findings, list):
        errors.append("findings: Liste erforderlich")
        return errors
    fingerprints: set[str] = set()
    for index, finding in enumerate(findings):
        prefix = f"findings[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{prefix}: Objekt erforderlich")
            continue
        for key in ("rule", "claim", "impact", "category", "path", "context"):
            value = _required_string(finding, key, prefix, errors)
            if key in {"claim", "impact"} and FORBIDDEN_FACT_WORDS.search(value):
                errors.append(f"{prefix}.{key}: enthaelt unzulaessiges Annahme-Wort")
        if finding.get("severity") not in SEVERITIES:
            errors.append(f"{prefix}.severity: P0, P1, P2 oder P3 erforderlich")
        if finding.get("confidence") not in CONFIDENCES:
            errors.append(f"{prefix}.confidence: hoch, mittel oder niedrig erforderlich")
        start = finding.get("line_start")
        end = finding.get("line_end")
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
            errors.append(f"{prefix}: ungueltiger Zeilenbereich")
        path, path_error = resolve_repo_path(repo, str(finding.get("path", "")))
        if path_error:
            errors.append(f"{prefix}.path: {path_error}")
        elif path is None or not path.is_file():
            errors.append(f"{prefix}.path: Datei fehlt")
        validate_evidence(finding.get("evidence"), repo, f"{prefix}.evidence", errors)
        evidence_items = finding.get("evidence")
        anchor_found = False
        if isinstance(evidence_items, list):
            finding_path = str(finding.get("path", "")).replace("\\", "/").casefold()
            finding_context = normalized(str(finding.get("context", "")))
            for item in evidence_items:
                if not isinstance(item, dict) or item.get("kind") != "source":
                    continue
                item_path = str(item.get("path", "")).replace("\\", "/").casefold()
                if (
                    item_path == finding_path
                    and item.get("line_start") == start
                    and item.get("line_end") == end
                    and finding_context in normalized(str(item.get("quote", "")))
                ):
                    anchor_found = True
                    break
        if not anchor_found:
            errors.append(
                f"{prefix}.evidence: Source-Anker muss Befundpfad, Zeilen und Kontext exakt tragen"
            )
        reproduction = finding.get("reproduction")
        if not isinstance(reproduction, dict):
            errors.append(f"{prefix}.reproduction: Objekt erforderlich")
        else:
            command = reproduction.get("command")
            result = reproduction.get("result")
            if not isinstance(command, str) or not isinstance(result, str):
                errors.append(f"{prefix}.reproduction: command/result muessen Strings sein")
        fingerprint = finding_fingerprint(finding)
        if fingerprint in fingerprints:
            errors.append(f"{prefix}: doppelter Fingerprint im selben Pass")
        fingerprints.add(fingerprint)
    applications = document.get("learning_applications", [])
    if not isinstance(applications, list):
        errors.append("learning_applications: Liste erforderlich")
    else:
        application_ids: set[str] = set()
        for index, application in enumerate(applications):
            prefix = f"learning_applications[{index}]"
            if not isinstance(application, dict):
                errors.append(f"{prefix}: Objekt erforderlich")
                continue
            application_id = _required_string(application, "application_id", prefix, errors)
            if application_id in application_ids:
                errors.append(f"{prefix}.application_id: doppelt im Pass")
            application_ids.add(application_id)
            learning_id = _required_string(application, "id", prefix, errors)
            if not re.fullmatch(r"L-\d{3,}", learning_id):
                errors.append(f"{prefix}.id: Learning-ID L-NNN erforderlich")
            if application.get("pass_id") != pass_id:
                errors.append(f"{prefix}.pass_id: muss Pass-ID entsprechen")
            if application.get("role") not in AUDIT_ROLES:
                errors.append(f"{prefix}.role: unbekannte Fachrolle")
            _required_string(application, "location", prefix, errors)
            if application.get("result") not in {"treffer", "sauber", "nicht_anwendbar"}:
                errors.append(f"{prefix}.result: treffer, sauber oder nicht_anwendbar erforderlich")
            claimed = application.get("finding_fingerprints", [])
            if not isinstance(claimed, list) or not all(
                isinstance(fingerprint, str)
                and re.fullmatch(r"[0-9a-f]{64}", fingerprint)
                for fingerprint in claimed
            ):
                errors.append(f"{prefix}.finding_fingerprints: Liste aus SHA-256-Werten erforderlich")
            if application.get("result") == "treffer":
                pass_fingerprints = {
                    finding_fingerprint(finding)
                    for finding in findings
                    if isinstance(finding, dict)
                }
                if not claimed:
                    errors.append(f"{prefix}: treffer braucht mindestens einen Befund-Fingerprint")
                elif any(fingerprint not in pass_fingerprints for fingerprint in claimed):
                    errors.append(f"{prefix}: treffer verweist auf passfremden Befund-Fingerprint")
            elif claimed:
                errors.append(f"{prefix}: nur treffer darf Befund-Fingerprints tragen")
    return errors


def installed_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def git_value(repo: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def environment_snapshot(repo: Path, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    lock = read_json(LOCK_FILE)
    locked_tools = lock.get("tools", {})
    tool_state: dict[str, Any] = {}
    for name, spec in locked_tools.items():
        if not isinstance(spec, dict):
            continue
        distribution = str(spec.get("distribution", name))
        actual = installed_version(distribution)
        expected = spec.get("version")
        tool_state[name] = {
            "expected": expected,
            "actual": actual,
            "required": bool(spec.get("required", False)),
            "matches": actual == expected if expected is not None else actual is None,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "captured_at": utc_now(),
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "repo": str(repo.resolve()),
        "git_commit": git_value(repo, "rev-parse", "HEAD"),
        "git_status_porcelain": git_value(repo, "status", "--short"),
        "seed": seed,
        "tools": tool_state,
    }


def empty_pass(pass_id: int, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "pass_id": pass_id,
        "agent_context_id": f"AUSFUELLEN-FRISCHER-KONTEXT-P{pass_id}",
        "file_order_seed": seed + pass_id,
        "role": "AUSFUELLEN",
        "role_results": [
            {
                "role": role,
                "status": "AUSFUELLEN",
                "note": "AUSFUELLEN",
                "checked_scope": ["AUSFUELLEN"],
            }
            for role in AUDIT_ROLES
        ],
        "findings": [],
        "learning_applications": [],
    }


def command_init_run(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    run_dir = Path(args.run_dir).resolve()
    if not (repo / "venv312" / "Scripts" / "python.exe").is_file():
        raise VeritasError("HPG venv312 fehlt im angegebenen Repository")
    if run_dir.exists() and any(run_dir.iterdir()):
        raise VeritasError(f"Laufverzeichnis ist nicht leer: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    contract = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "scope": args.scope,
        "repo": str(repo),
        "mode": args.mode,
        "seed": args.seed,
        "project_code_writable": False,
        "excluded": [
            "Claude-Autopilot-v5/",
            "Claude-Autopilot-v6/",
            "Claude-Autopilot-v6.zip",
            "venv312/",
            "*.db*",
            "*.lock",
            "*.coverage",
        ],
        "acceptance": [
            "drei valide, unabhaengige Pass-Dateien",
            "Bestaetigung nur bei mindestens zwei Paessen und Verifikator-Akzeptanz",
            "sync_difference_count gleich null",
        ],
    }
    write_json(run_dir / "contract.json", contract)
    write_json(run_dir / "environment.json", environment_snapshot(repo, args.seed))
    for pass_id, pass_name in enumerate(PASS_NAMES, start=1):
        write_json(run_dir / pass_name / "findings.json", empty_pass(pass_id, args.seed))
    learning_source = (
        Path(args.previous_learnings).resolve()
        if args.previous_learnings
        else PERSISTENT_LEARNINGS_FILE
    )
    learning_data = (
        read_json(learning_source)
        if learning_source.is_file()
        else {"schema_version": SCHEMA_VERSION, "learnings": []}
    )
    if learning_data.get("schema_version") != SCHEMA_VERSION or not isinstance(
        learning_data.get("learnings"), list
    ):
        raise VeritasError(f"Ungueltiger Learning-Speicher: {learning_source}")
    write_json(run_dir / "learnings.json", learning_data)
    print(json.dumps({"status": "initialized", "run_dir": str(run_dir)}, ensure_ascii=False))
    return 0


def command_validate_pass(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    input_path = Path(args.input).resolve()
    document = read_json(input_path)
    errors = validate_pass_document(document, repo, args.expected_pass)
    payload = {"valid": not errors, "errors": errors, "input": str(input_path)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def previous_ids(previous: Path | None) -> tuple[dict[str, str], int]:
    if previous is None:
        return {}, 0
    data = read_json(previous)
    mapping: dict[str, str] = {}
    maximum = 0
    for finding in data.get("findings", []):
        if not isinstance(finding, dict):
            continue
        fingerprint = finding.get("fingerprint")
        finding_id = finding.get("id")
        if isinstance(fingerprint, str) and isinstance(finding_id, str):
            mapping[fingerprint] = finding_id
            match = re.fullmatch(r"V-(\d+)", finding_id)
            if match:
                maximum = max(maximum, int(match.group(1)))
    return mapping, maximum


def load_passes(run_dir: Path, repo: Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    errors: list[str] = []
    for pass_id, pass_name in enumerate(PASS_NAMES, start=1):
        path = run_dir / pass_name / "findings.json"
        document = read_json(path)
        pass_errors = validate_pass_document(document, repo, pass_id)
        errors.extend(f"{pass_name}: {error}" for error in pass_errors)
        documents.append(document)
    contexts = [document.get("agent_context_id") for document in documents[:2]]
    seeds = [document.get("file_order_seed") for document in documents[:2]]
    if len(set(contexts)) != 2:
        errors.append("Pass 1 und Pass 2 brauchen verschiedene agent_context_id")
    if len(set(seeds)) != 2:
        errors.append("Pass 1 und Pass 2 brauchen verschiedene file_order_seed")
    if any(str(context).startswith("AUSFUELLEN") for context in contexts):
        errors.append("Pass 1/2 enthalten noch Kontext-Platzhalter")
    learning_data = read_json(run_dir / "learnings.json")
    raw_learnings = learning_data.get("learnings")
    if not isinstance(raw_learnings, list):
        errors.append("learnings.json: learnings muss Liste sein")
        raw_learnings = []
    active_ids = {
        learning.get("id")
        for learning in raw_learnings
        if isinstance(learning, dict)
        and learning.get("status") == "aktiv"
        and isinstance(learning.get("id"), str)
    }
    global_application_ids: set[str] = set()
    for document in documents:
        pass_id = document.get("pass_id")
        applications = [
            application
            for application in document.get("learning_applications", [])
            if isinstance(application, dict)
        ]
        for application in applications:
            application_id = application.get("application_id")
            if application_id in global_application_ids:
                errors.append(f"Doppelte application_id ueber Paesse: {application_id}")
            if isinstance(application_id, str):
                global_application_ids.add(application_id)
        for learning_id in active_ids:
            for role in AUDIT_ROLES:
                if not any(
                    application.get("id") == learning_id
                    and application.get("role") == role
                    for application in applications
                ):
                    errors.append(
                        f"Pass {pass_id}: aktive Regel {learning_id} nicht durch Rolle {role} quittiert"
                    )
    if errors:
        raise VeritasError("Pass-Validierung fehlgeschlagen:\n- " + "\n- ".join(errors))
    return documents


def merge_documents(
    documents: list[dict[str, Any]], previous: Path | None = None
) -> dict[str, Any]:
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for document in documents:
        pass_id = int(document["pass_id"])
        for finding in document["findings"]:
            grouped[finding_fingerprint(finding)].append((pass_id, finding))
    old_ids, maximum = previous_ids(previous)
    merged: list[dict[str, Any]] = []
    for fingerprint in sorted(grouped):
        occurrences = sorted(grouped[fingerprint], key=lambda item: item[0])
        passes = sorted({pass_id for pass_id, _ in occurrences})
        claims = {normalized(finding["claim"]) for _, finding in occurrences}
        impacts = {normalized(finding["impact"]) for _, finding in occurrences}
        severities = {finding["severity"] for _, finding in occurrences}
        categories = {normalized(finding["category"]) for _, finding in occurrences}
        confidences = {finding["confidence"] for _, finding in occurrences}
        merge_status = "UNBESTAETIGT"
        conflicts: list[str] = []
        if len(passes) >= 2:
            if (
                len(claims) == 1
                and len(impacts) == 1
                and len(severities) == 1
                and len(categories) == 1
                and len(confidences) == 1
            ):
                merge_status = "BESTAETIGT"
            else:
                merge_status = "WIDERSPRUCH"
                if len(claims) > 1:
                    conflicts.append("Claim unterscheidet sich zwischen Paessen")
                if len(severities) > 1:
                    conflicts.append("Severity unterscheidet sich zwischen Paessen")
                if len(impacts) > 1:
                    conflicts.append("Impact unterscheidet sich zwischen Paessen")
                if len(categories) > 1:
                    conflicts.append("Kategorie unterscheidet sich zwischen Paessen")
                if len(confidences) > 1:
                    conflicts.append("Konfidenz unterscheidet sich zwischen Paessen")
        finding_id = old_ids.get(fingerprint)
        if finding_id is None:
            maximum += 1
            finding_id = f"V-{maximum:03d}"
        _, primary = occurrences[0]
        merged.append(
            {
                "id": finding_id,
                "fingerprint": fingerprint,
                "status": "UNBESTAETIGT" if merge_status == "BESTAETIGT" else merge_status,
                "merge_status": merge_status,
                "verifier_status": "AUSSTEHEND",
                "passes": passes,
                "pass_quote": f"{len(passes)}/3",
                "rule": primary["rule"],
                "claim": primary["claim"],
                "impact": primary["impact"],
                "severity": primary["severity"],
                "category": primary["category"],
                "path": primary["path"],
                "line_start": primary["line_start"],
                "line_end": primary["line_end"],
                "context": primary["context"],
                "confidence": primary["confidence"],
                "evidence": [
                    {"pass_id": pass_id, "items": finding["evidence"]}
                    for pass_id, finding in occurrences
                ],
                "reproductions": [
                    {"pass_id": pass_id, **finding["reproduction"]}
                    for pass_id, finding in occurrences
                ],
                "conflicts": conflicts,
            }
        )
    merged.sort(key=lambda finding: (finding["severity"], finding["id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "findings": merged,
    }


def run_report_date(contract: dict[str, Any]) -> str:
    """Lauf-Erstelldatum aus dem Vertrag; nicht das Schreibdatum des Reports."""
    created = str(contract.get("created_at", ""))
    try:
        return datetime.fromisoformat(created).date().isoformat()
    except ValueError as exc:
        raise VeritasError(
            f"contract.json: created_at ist kein ISO-Zeitstempel: {created!r}"
        ) from exc


def evidence_markdown(finding: dict[str, Any]) -> str:
    groups = finding.get("evidence", [])
    if not groups:
        return "Keine Evidenz gespeichert."
    first_group = groups[0]
    items = first_group.get("items", []) if isinstance(first_group, dict) else []
    if not items:
        return "Keine Evidenz gespeichert."
    item = items[0]
    if item.get("kind") == "source":
        return (
            f"`{item['path']}:{item['line_start']}`\n\n"
            f"```text\n{item['quote']}\n```"
        )
    output = str(item.get("output", ""))
    return f"`{item.get('command', '')}` (Exit {item.get('exit_code')})\n\n```text\n{output}\n```"


def render_report(
    canonical: dict[str, Any], contract: dict[str, Any], documents: list[dict[str, Any]]
) -> str:
    findings = canonical.get("findings", [])
    reproduced = sum(1 for finding in findings if len(finding.get("passes", [])) >= 2)
    quote = (100.0 * reproduced / len(findings)) if findings else 100.0
    lines = [
        f"# VERITAS Audit Report {run_report_date(contract)}",
        "",
        "## Auftrags-Kontrakt",
        "",
        f"- Scope: {contract.get('scope', '')}",
        f"- Modus: {contract.get('mode', '')}",
        "- Projektcode: read-only",
        "",
        "## Reproduzierbarkeit",
        "",
        f"- Befunde gesamt: {len(findings)}",
        f"- In mindestens zwei Paessen: {reproduced}",
        f"- Quote: {quote:.2f} %",
        "- Pass-Kontexte: "
        + ", ".join(str(document.get("agent_context_id")) for document in documents),
        "",
    ]
    for status in ("BESTAETIGT", "WIDERSPRUCH", "UNBESTAETIGT"):
        lines.extend([f"## {status}", ""])
        matching = [finding for finding in findings if finding.get("status") == status]
        if not matching:
            lines.extend(["Keine.", ""])
            continue
        for finding in matching:
            lines.extend(
                [
                    f"### {finding['id']} [{finding['pass_quote']}] [{finding['severity']}] [{finding['category']}]",
                    "",
                    f"- Datei: `{finding['path']}:{finding['line_start']}`",
                    f"- Claim: {finding['claim']}",
                    f"- Auswirkung: {finding['impact']}",
                    f"- Konfidenz: {finding['confidence']}",
                    f"- Merge: {finding['merge_status']}; Verifikator: {finding['verifier_status']}",
                    "",
                    "Beweis:",
                    "",
                    evidence_markdown(finding),
                    "",
                ]
            )
            if finding.get("conflicts"):
                lines.extend(
                    ["Widersprueche:", ""]
                    + [f"- {entry}" for entry in finding["conflicts"]]
                    + [""]
                )
    applications = [
        application
        for document in documents
        for application in document.get("learning_applications", [])
        if isinstance(application, dict)
    ]
    lines.extend(["## Angewendete Learnings", ""])
    if applications:
        lines.extend(["| Learning | Pass | Rolle | Ergebnis |", "|---|---:|---|---|"])
        for application in applications:
            lines.append(
                f"| {application.get('id', '')} | {application.get('pass_id', '')} | "
                f"{application.get('role', '')} | {application.get('result', '')} |"
            )
    else:
        lines.append("Keine Anwendungen protokolliert.")
    lines.extend(["", ":-)"])
    return "\n".join(lines)


def update_learning_counters(
    run_dir: Path,
    documents: list[dict[str, Any]],
    canonical: dict[str, Any],
) -> None:
    path = run_dir / "learnings.json"
    data = read_json(path)
    learnings = data.get("learnings")
    if not isinstance(learnings, list):
        raise VeritasError("learnings.json: learnings muss Liste sein")
    by_id: dict[str, dict[str, Any]] = {}
    for learning in learnings:
        if not isinstance(learning, dict) or not isinstance(learning.get("id"), str):
            raise VeritasError("learnings.json: Learning ohne gueltige ID")
        by_id[learning["id"]] = learning
        applications = learning.setdefault("applications", [])
        if not isinstance(applications, list):
            raise VeritasError(f"{learning['id']}: applications muss Liste sein")
    ids_by_fingerprint = {
        finding.get("fingerprint"): finding.get("id")
        for finding in canonical.get("findings", [])
        if isinstance(finding, dict)
    }
    for document in documents:
        for application in document.get("learning_applications", []):
            application = dict(application)
            application["finding_ids"] = [
                ids_by_fingerprint[fingerprint]
                for fingerprint in application.get("finding_fingerprints", [])
                if fingerprint in ids_by_fingerprint
            ]
            learning_id = application["id"]
            if learning_id not in by_id:
                raise VeritasError(f"Unbekanntes angewendetes Learning: {learning_id}")
            stored = by_id[learning_id]["applications"]
            known_ids = {
                item.get("application_id")
                for item in stored
                if isinstance(item, dict)
            }
            if application["application_id"] not in known_ids:
                stored.append(application)
    for learning in by_id.values():
        applications = learning["applications"]
        learning["applied"] = len(applications)
        learning["hits"] = sum(
            1
            for application in applications
            if isinstance(application, dict) and application.get("result") == "treffer"
        )
    write_json(path, data)


def save_canonical(run_dir: Path, canonical: dict[str, Any], documents: list[dict[str, Any]]) -> Path:
    contract = read_json(run_dir / "contract.json")
    write_json(run_dir / "findings.json", canonical)
    report_path = run_dir / f"AUDIT_REPORT_{run_report_date(contract)}.md"
    write_text(report_path, render_report(canonical, contract, documents))
    return report_path


def command_merge(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    repo = Path(args.repo).resolve()
    documents = load_passes(run_dir, repo)
    previous = Path(args.previous).resolve() if args.previous else None
    canonical = merge_documents(documents, previous)
    update_learning_counters(run_dir, documents, canonical)
    report_path = save_canonical(run_dir, canonical, documents)
    summary = {
        "status": "merged_pending_verifier",
        "findings": len(canonical["findings"]),
        "report": str(report_path),
        "canonical": str(run_dir / "findings.json"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def command_apply_verifier(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    repo = Path(args.repo).resolve()
    documents = load_passes(run_dir, repo)
    canonical = read_json(run_dir / "findings.json")
    verdicts = read_json(Path(args.input).resolve())
    context = verdicts.get("agent_context_id")
    pass_contexts = {document.get("agent_context_id") for document in documents}
    if not isinstance(context, str) or not context.strip() or context in pass_contexts:
        raise VeritasError("Verifikator braucht eine eigene, frische agent_context_id")
    decisions = verdicts.get("decisions")
    if not isinstance(decisions, list):
        raise VeritasError("decisions muss eine Liste sein")
    by_id = {decision.get("id"): decision for decision in decisions if isinstance(decision, dict)}
    missing = [
        finding["id"]
        for finding in canonical.get("findings", [])
        if finding.get("merge_status") == "BESTAETIGT" and finding["id"] not in by_id
    ]
    if missing:
        raise VeritasError("Verifikatorentscheidungen fehlen fuer: " + ", ".join(missing))
    for finding in canonical.get("findings", []):
        if finding.get("merge_status") != "BESTAETIGT":
            continue
        decision = by_id[finding["id"]]
        value = decision.get("decision")
        note = decision.get("note")
        if value not in {"akzeptiert", "verworfen", "offen"}:
            raise VeritasError(f"Ungueltige Entscheidung fuer {finding['id']}: {value}")
        if not isinstance(note, str) or not note.strip():
            raise VeritasError(f"Verifikatornote fehlt fuer {finding['id']}")
        finding["verifier_status"] = value.upper()
        finding["verifier_note"] = note
        finding["status"] = "BESTAETIGT" if value == "akzeptiert" else "UNBESTAETIGT"
    canonical["verifier_context_id"] = context
    canonical["verifier_applied_at"] = utc_now()
    report_path = save_canonical(run_dir, canonical, documents)
    print(json.dumps({"status": "verifier_applied", "report": str(report_path)}, ensure_ascii=False))
    return 0


def validate_toolchain(snapshot: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    python_executable = Path(str(snapshot.get("python_executable", "")))
    if python_executable.name.casefold() != "python.exe" or "venv312" not in {
        part.casefold() for part in python_executable.parts
    }:
        errors.append("Aktiver Interpreter ist nicht HPG venv312")
    for name, state in snapshot.get("tools", {}).items():
        if state.get("required") and not state.get("matches"):
            errors.append(
                f"Pflichtwerkzeug {name}: erwartet {state.get('expected')}, gefunden {state.get('actual')}"
            )
    return errors


def command_self_test(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    snapshot = environment_snapshot(repo)
    errors = validate_toolchain(snapshot)
    lock = read_json(LOCK_FILE)
    if snapshot.get("python_version") != lock.get("python"):
        errors.append(
            f"Python-Version: erwartet {lock.get('python')}, gefunden {snapshot.get('python_version')}"
        )
    config = read_json(SYNC_CONFIG_FILE)
    vault_root = Path(str(config.get("vault_root", "")))
    if not vault_root.is_absolute():
        errors.append("sync_targets.json: vault_root muss absolut sein")
    relative_dir = Path(str(config.get("vault_audit_dir", "")))
    lowered = {
        part.casefold()
        for part in (*vault_root.parts, *relative_dir.parts)
    }
    if relative_dir.is_absolute() or "_raw" in lowered or "00_claude_memory" in lowered:
        errors.append("sync_targets.json: unzulaessiges Vault-Ziel")
    payload = {"ok": not errors, "errors": errors, "environment": snapshot}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HPG VERITAS Audit-Kern")
    parser.set_defaults(repo=str(REPO_ROOT))
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-run", help="Frischen Lauf initialisieren")
    init_parser.add_argument("--run-dir", required=True)
    init_parser.add_argument("--scope", required=True)
    init_parser.add_argument("--mode", choices=("full", "delta", "release"), default="full")
    init_parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    init_parser.add_argument("--previous-learnings")
    init_parser.add_argument("--repo", default=str(REPO_ROOT))
    init_parser.set_defaults(func=command_init_run)

    validate_parser = subparsers.add_parser("validate-pass", help="Pass-Evidenz validieren")
    validate_parser.add_argument("--input", required=True)
    validate_parser.add_argument("--expected-pass", type=int, choices=(1, 2, 3))
    validate_parser.add_argument("--repo", default=str(REPO_ROOT))
    validate_parser.set_defaults(func=command_validate_pass)

    merge_parser = subparsers.add_parser("merge", help="Drei valide Paesse mergen")
    merge_parser.add_argument("--run-dir", required=True)
    merge_parser.add_argument("--previous")
    merge_parser.add_argument("--repo", default=str(REPO_ROOT))
    merge_parser.set_defaults(func=command_merge)

    verifier_parser = subparsers.add_parser(
        "apply-verifier", help="Unabhaengige Verifikatorentscheidungen anwenden"
    )
    verifier_parser.add_argument("--run-dir", required=True)
    verifier_parser.add_argument("--input", required=True)
    verifier_parser.add_argument("--repo", default=str(REPO_ROOT))
    verifier_parser.set_defaults(func=command_apply_verifier)

    self_test_parser = subparsers.add_parser("self-test", help="Konfiguration pruefen")
    self_test_parser.add_argument("--repo", default=str(REPO_ROOT))
    self_test_parser.set_defaults(func=command_self_test)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except VeritasError as exc:
        print(f"VERITAS_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
