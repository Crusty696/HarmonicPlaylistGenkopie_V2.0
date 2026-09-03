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


SCHEMA_VERSION = 2
# Laeufe mit Schema 1 bleiben lesbar; neue Felder werden defensiv gelesen.
READABLE_SCHEMA_VERSIONS = (1, 2)
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


def _ist_zeilennummer(wert: Any) -> bool:
    """Echter Integer -- bool ist in Python ein int und waere sonst Zeile 1."""
    return isinstance(wert, int) and not isinstance(wert, bool)


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
            if not _ist_zeilennummer(start) or not _ist_zeilennummer(end):
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
            for key in ("command", "cwd", "output_sha256", "timestamp"):
                _required_string(item, key, item_prefix, errors)
            if not isinstance(item.get("output"), str):
                errors.append(f"{item_prefix}.output: String erforderlich")
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
    if document.get("schema_version") not in READABLE_SCHEMA_VERSIONS:
        errors.append(
            "schema_version: erwartet eine von "
            + ", ".join(str(x) for x in READABLE_SCHEMA_VERSIONS)
        )
    pass_id = document.get("pass_id")
    if pass_id not in {1, 2, 3}:
        errors.append("pass_id: 1, 2 oder 3 erforderlich")
    if expected_pass is not None and pass_id != expected_pass:
        errors.append(f"pass_id: erwartet {expected_pass}")
    _required_string(document, "agent_context_id", "pass", errors)
    if not isinstance(document.get("file_order_seed"), int):
        errors.append("pass.file_order_seed: Integer erforderlich")
    rolle = _required_string(document, "role", "pass", errors)
    if rolle and rolle not in AUDIT_ROLES:
        errors.append("pass.role: unbekannte Fachrolle")
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
        if not _ist_zeilennummer(start) or not _ist_zeilennummer(end) or start < 1 or end < start:
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
    try:
        result = subprocess.run(
            ["git", *args], cwd=repo, text=True, capture_output=True, check=False
        )
    except OSError:
        return None
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
    # Umgebung VOR dem ersten Schreibvorgang pruefen: sonst bleibt ein halb
    # angelegter Laufordner liegen, der sich nicht mehr initialisieren laesst.
    snapshot = environment_snapshot(repo, args.seed)
    umgebungsfehler = validate_toolchain(snapshot)
    if umgebungsfehler and not getattr(args, "ignore_toolchain", False):
        raise VeritasError(
            "Umgebung erfuellt den Laufvertrag nicht:\n- "
            + "\n- ".join(umgebungsfehler)
            + "\nMit --ignore-toolchain trotzdem initialisieren; der Lauf gilt"
            " dann als unter fremder Toolchain erhoben."
        )
    snapshot["toolchain_errors"] = umgebungsfehler
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
    write_json(run_dir / "environment.json", snapshot)
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
    if learning_data.get("schema_version") not in READABLE_SCHEMA_VERSIONS or not isinstance(
        learning_data.get("learnings"), list
    ):
        raise VeritasError(f"Ungueltiger Learning-Speicher: {learning_source}")
    for learning in learning_data["learnings"]:
        if not isinstance(learning, dict):
            continue
        anwendungen = learning.get("applications", [])
        if isinstance(anwendungen, list) and learning.get("applied") not in (
            None, len(anwendungen)
        ):
            raise VeritasError(
                f"{learning_source}: {learning.get('id')} meldet applied="
                f"{learning.get('applied')}, fuehrt aber {len(anwendungen)} "
                "Anwendungen. Der Merge leitet den Zaehler aus den Anwendungen "
                "ab und wuerde die Angabe stillschweigend ueberschreiben."
            )
    learning_data["schema_version"] = SCHEMA_VERSION
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
    alle_kontexte = [document.get("agent_context_id") for document in documents]
    alle_seeds = [document.get("file_order_seed") for document in documents]
    if len(set(alle_kontexte)) != len(alle_kontexte):
        errors.append("Alle drei Paesse brauchen verschiedene agent_context_id")
    if len(set(alle_seeds)) != len(alle_seeds):
        errors.append("Alle drei Paesse brauchen verschiedene file_order_seed")
    for index, kontext in enumerate(alle_kontexte, start=1):
        if str(kontext).startswith("AUSFUELLEN"):
            errors.append(f"Pass {index} enthaelt noch den Kontext-Platzhalter")
    for index, document in enumerate(documents, start=1):
        if str(document.get("role", "")).startswith("AUSFUELLEN"):
            errors.append(f"Pass {index} enthaelt noch den Rollen-Platzhalter")
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
        severities = {finding["severity"] for _, finding in occurrences}
        confidences = {finding["confidence"] for _, finding in occurrences}
        # Zwei unabhaengige Paesse formulieren denselben Sachverhalt nie
        # zeichengleich. Uebereinstimmung wird deshalb nur auf den
        # geschlossenen Vokabularen verlangt -- severity und confidence;
        # rule, path und context stecken bereits im Fingerprint. Abweichende
        # Formulierung ist Variante, kein Widerspruch.
        merge_status = "UNBESTAETIGT"
        conflicts: list[str] = []
        hinweise: list[dict[str, str]] = []
        # B1: der Fingerprint kennt bewusst keinen Zeilenbereich, damit
        # Verschiebungen denselben Befund ergeben. Der Preis: zwei echte
        # Fundstellen mit gleicher Regel und gleichem Kontext verschmelzen.
        # Deshalb werden alle vorkommenden Bereiche gefuehrt.
        fundstellen = sorted(
            {(int(f["line_start"]), int(f["line_end"])) for _, f in occurrences}
        )
        if len(fundstellen) > 1:
            hinweise.append({
                "art": "zeilenbereich",
                "text": "Die Paesse nennen verschiedene Zeilenbereiche: "
                        + ", ".join(f"{a}-{b}" for a, b in fundstellen)
                        + " -- moeglicherweise zwei verschiedene Fundstellen",
            })
        if len(passes) >= 2:
            if len(severities) == 1 and len(confidences) == 1:
                merge_status = "BESTAETIGT"
            else:
                merge_status = "WIDERSPRUCH"
                if len(severities) > 1:
                    conflicts.append("Severity unterscheidet sich zwischen Paessen")
                if len(confidences) > 1:
                    conflicts.append("Konfidenz unterscheidet sich zwischen Paessen")
            # Gleiche Prosa nach Normalisierung (Whitespace, Gross-/Klein-
            # schreibung) ist kein Reproduktionsbeleg, sondern ein Hinweis auf
            # nicht unabhaengiges Arbeiten -- aber nur zwischen Pass 1 und
            # Pass 2. Pass 3 darf A und B kennen und deren Formulierung
            # uebernehmen, das ist sein Auftrag.
            texte = {
                pass_id: (normalized(finding["claim"]), normalized(finding["impact"]))
                for pass_id, finding in occurrences
            }
            if 1 in texte and 2 in texte and texte[1] == texte[2]:
                hinweise.append({
                    "art": "prosa-gleichheit",
                    "text": "Claim und Impact sind in Pass 1 und Pass 2 zeichengleich"
                            " -- die beiden Paesse waren nicht unabhaengig",
                })
            # B4: Pass 3 darf A und B kennen. Ruht eine Bestaetigung allein
            # auf einem Paar mit Pass 3, ist sie keine unabhaengige
            # Reproduktion.
            if 3 in passes and not (1 in passes and 2 in passes):
                hinweise.append({
                    "art": "pass-paar",
                    "text": f"Bestaetigt durch die Paesse {passes} -- Pass 3 kennt"
                            " Pass 1 und Pass 2, das Paar 1+2 fehlt",
                })
        finding_id = old_ids.get(fingerprint)
        if finding_id is None:
            maximum += 1
            finding_id = f"V-{maximum:03d}"
        _, primary = occurrences[0]
        # Bei WIDERSPRUCH ist die schaerfste Meldung massgeblich, sonst
        # sortiert ein von Pass 2 gemeldetes P0 als P3 ans Ende.
        kanon_severity = min(severities)
        kanon_confidence = (
            primary["confidence"] if len(confidences) == 1
            else min(confidences, key=lambda c: ("niedrig", "mittel", "hoch").index(c))
        )
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
                "severity": kanon_severity,
                "category": primary["category"],
                "path": primary["path"],
                "line_start": primary["line_start"],
                "line_end": primary["line_end"],
                "context": primary["context"],
                "confidence": kanon_confidence,
                "fundstellen": [
                    {"line_start": a, "line_end": b} for a, b in fundstellen
                ],
                "evidence": [
                    {"pass_id": pass_id, "items": finding["evidence"]}
                    for pass_id, finding in occurrences
                ],
                "reproductions": [
                    {"pass_id": pass_id, **finding["reproduction"]}
                    for pass_id, finding in occurrences
                ],
                "conflicts": conflicts,
                "hinweise": hinweise,
                "varianten": [
                    {
                        "pass_id": pass_id,
                        "claim": finding["claim"],
                        "impact": finding["impact"],
                        "category": finding["category"],
                        "severity": finding["severity"],
                        "confidence": finding["confidence"],
                    }
                    for pass_id, finding in occurrences
                ],
            }
        )
    def _sortierschluessel(finding: dict[str, Any]) -> tuple[str, int, str]:
        treffer = re.fullmatch(r"V-(\d+)", str(finding["id"]))
        return (finding["severity"], int(treffer.group(1)) if treffer else 0, str(finding["id"]))

    merged.sort(key=_sortierschluessel)
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
    bloecke: list[str] = []
    for gruppe in finding.get("evidence", []):
        if not isinstance(gruppe, dict):
            continue
        for item in gruppe.get("items", []):
            if not isinstance(item, dict):
                continue
            if item.get("kind") == "source":
                ort = f"{item.get('path', '?')}:{item.get('line_start', '?')}"
                zitat = item.get("quote", "(kein Zitat gespeichert)")
                block = f"`{ort}`\n\n```text\n{zitat}\n```"
            else:
                output = str(item.get("output", ""))
                block = (
                    f"`{item.get('command', '')}` (Exit {item.get('exit_code')})"
                    f"\n\n```text\n{output}\n```"
                )
            bloecke.append(f"Pass {gruppe.get('pass_id', '?')}: {block}")
    return "\n\n".join(bloecke) if bloecke else "Keine Evidenz gespeichert."


def render_report(
    canonical: dict[str, Any], contract: dict[str, Any], documents: list[dict[str, Any]]
) -> str:
    findings = canonical.get("findings", [])
    reproduced = sum(1 for finding in findings if len(finding.get("passes", [])) >= 2)
    # Hinweise sind typisiert; der Kopf darf nicht jede Art als Prosa-
    # Gleichheit ausgeben, sonst behauptet der Bericht etwas Falsches.
    nach_art: dict[str, int] = defaultdict(int)
    for finding in findings:
        for hinweis in finding.get("hinweise", []):
            # Schema 1 kannte nur Strings, und nur die Prosa-Gleichheit.
            art = hinweis.get("art", "unbekannt") if isinstance(hinweis, dict) else "prosa-gleichheit"
            nach_art[str(art)] += 1
    # Quote ohne Befunde ist keine 100 % -- es gibt nichts zu reproduzieren.
    quote = (100.0 * reproduced / len(findings)) if findings else 0.0
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
        f"- Quote: {quote:.2f} %"
        + ("  <- keine Befunde, es gibt nichts zu reproduzieren" if not findings else ""),
        f"- Gleiche Prosa in Pass 1 und Pass 2: {nach_art['prosa-gleichheit']}"
        + (
            "  <- die beiden Paesse waren nicht unabhaengig; der Lauf ist kein"
            " Drei-Pass-Audit, solange das nicht geklaert ist"
            if nach_art["prosa-gleichheit"]
            else ""
        ),
        f"- Bestaetigt ohne das Paar 1+2: {nach_art['pass-paar']}"
        + (
            "  <- Pass 3 kennt die Vorgaenger, das ist keine unabhaengige"
            " Reproduktion"
            if nach_art["pass-paar"]
            else ""
        ),
        f"- Abweichende Zeilenbereiche: {nach_art['zeilenbereich']}"
        + (
            "  <- moeglicherweise zwei verschiedene Fundstellen unter einem Befund"
            if nach_art["zeilenbereich"]
            else ""
        ),
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
                ]
            )
            if finding.get("verifier_note"):
                lines.append(f"- Verifikator-Begruendung: {finding['verifier_note']}")
            lines.extend(
                [
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
            if finding.get("hinweise"):
                lines.extend(["Hinweise:", ""])
                for hinweis in finding["hinweise"]:
                    if isinstance(hinweis, dict):
                        lines.append(f"- [{hinweis.get('art')}] {hinweis.get('text')}")
                    else:  # Laeufe mit Schema 1 fuehrten reine Strings
                        lines.append(f"- {hinweis}")
                lines.append("")
            varianten = finding.get("varianten", [])
            formulierungen = {
                (
                    normalized(str(v.get("claim", ""))),
                    normalized(str(v.get("impact", ""))),
                    normalized(str(v.get("category", ""))),
                )
                for v in varianten
            }
            if len(formulierungen) > 1:
                lines.extend(["Formulierungen je Pass:", ""])
                for variante in varianten:
                    lines.extend(
                        [
                            f"- Pass {variante.get('pass_id')} [{variante.get('category')}]: "
                            f"{variante.get('claim')}",
                            f"  Auswirkung: {variante.get('impact')}",
                        ]
                    )
                lines.append("")
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
            neu_id = application["application_id"]
            for index, vorhanden in enumerate(stored):
                if isinstance(vorhanden, dict) and vorhanden.get("application_id") == neu_id:
                    stored[index] = application  # korrigierte Fassung ersetzt die alte
                    break
            else:
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
    # Datum zuerst aufloesen: sonst laege findings.json neu vor, waehrend der
    # Report an einem kaputten created_at scheitert.
    report_path = run_dir / f"AUDIT_REPORT_{run_report_date(contract)}.md"
    bericht = render_report(canonical, contract, documents)
    write_json(run_dir / "findings.json", canonical)
    write_text(report_path, bericht)
    return report_path


def command_merge(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    repo = Path(args.repo).resolve()
    eigener_kanon = run_dir / "findings.json"
    # A5: merge_documents kennt die Verifikatorfelder nicht und wuerde sie
    # ersatzlos ueberschreiben. Ein bereits beurteilter Lauf wird deshalb
    # nicht stillschweigend neu gemergt.
    if eigener_kanon.is_file() and not getattr(args, "force_remerge", False):
        vorhanden = read_json(eigener_kanon)
        if vorhanden.get("verifier_context_id"):
            raise VeritasError(
                f"{eigener_kanon} traegt bereits ein Verifikatorurteil "
                f"({vorhanden['verifier_context_id']}). Ein erneuter Merge "
                "loescht Status, Note und Kontext. Mit --force-remerge "
                "erzwingen, nachdem der Laufordner gesichert wurde."
            )
    documents = load_passes(run_dir, repo)
    # A1: ohne Vorgaenger vergibt merge_documents IDs nach Fingerprint-
    # Sortierung neu; ein Verdikt fuer V-001 traefe danach einen anderen
    # Befund. Der eigene Kanon ist die Vorgabe, --no-previous erzwingt
    # bewusste Neunummerierung.
    if args.previous:
        previous = Path(args.previous).resolve()
    elif getattr(args, "no_previous", False) or not eigener_kanon.is_file():
        previous = None
    else:
        previous = eigener_kanon
    canonical = merge_documents(documents, previous)
    update_learning_counters(run_dir, documents, canonical)
    report_path = save_canonical(run_dir, canonical, documents)
    nach_art: dict[str, int] = defaultdict(int)
    for f in canonical["findings"]:
        for hinweis in f.get("hinweise", []):
            art = hinweis.get("art", "unbekannt") if isinstance(hinweis, dict) else "prosa-gleichheit"
            nach_art[str(art)] += 1
    summary = {
        "status": "merged_pending_verifier",
        "findings": len(canonical["findings"]),
        "hinweise": dict(sorted(nach_art.items())),
        "previous": str(previous) if previous else None,
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
    bekannte_ids = {
        finding.get("id") for finding in canonical.get("findings", [])
    }
    unbekannt = sorted(str(k) for k in by_id if k not in bekannte_ids)
    if unbekannt:
        raise VeritasError(
            "Verifikatorentscheidungen fuer unbekannte Befund-IDs: "
            + ", ".join(unbekannt)
        )
    # Entscheidungen zu nicht bestaetigten Befunden werden nicht angewendet --
    # das ist gewollt, muss aber sichtbar sein statt lautlos zu verschwinden.
    nicht_angewendet = sorted(
        str(finding["id"])
        for finding in canonical.get("findings", [])
        if finding.get("merge_status") != "BESTAETIGT" and finding.get("id") in by_id
    )
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
        gemeldeter_fp = decision.get("fingerprint")
        if gemeldeter_fp is not None and gemeldeter_fp != finding.get("fingerprint"):
            raise VeritasError(
                f"Verdikt fuer {finding['id']} traegt einen fremden Fingerprint - "
                "die Befund-IDs des Laufs haben sich seit dem Urteil verschoben"
            )
        finding["verifier_status"] = value.upper()
        finding["verifier_note"] = note
        finding["status"] = "BESTAETIGT" if value == "akzeptiert" else "UNBESTAETIGT"
    canonical["verifier_context_id"] = context
    canonical["verifier_applied_at"] = utc_now()
    report_path = save_canonical(run_dir, canonical, documents)
    print(json.dumps({
        "status": "verifier_applied",
        "nicht_angewendet": nicht_angewendet,
        "report": str(report_path),
    }, ensure_ascii=False))
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
    # Dieselbe Funktion wie der Sync, nicht dieselbe Regel zweimal: sonst
    # meldet self-test gruen, waehrend --apply abbricht.
    try:
        from .sync_knowledge import safe_vault_dir

        safe_vault_dir(config)
    except ImportError:  # direkter Aufruf aus tools/audit
        from sync_knowledge import safe_vault_dir  # type: ignore[no-redef]

        safe_vault_dir(config)
    except VeritasError as exc:
        errors.append(f"sync_targets.json: {exc}")
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
    init_parser.add_argument(
        "--ignore-toolchain",
        action="store_true",
        help="Lauf trotz nicht erfuellter Pflichtwerkzeuge initialisieren",
    )
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
    merge_parser.add_argument(
        "--no-previous",
        action="store_true",
        help="Befund-IDs bewusst neu vergeben statt aus findings.json zu uebernehmen",
    )
    merge_parser.add_argument(
        "--force-remerge",
        action="store_true",
        help="Neu mergen, obwohl ein Verifikatorurteil vorliegt (loescht es)",
    )
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
