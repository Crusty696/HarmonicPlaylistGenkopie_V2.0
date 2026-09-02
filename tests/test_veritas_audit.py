from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from tools.audit import sync_knowledge, veritas


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "sample.py").write_text("alpha = 1\nbeta = 2\n", encoding="utf-8")
    python = repo / "venv312" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("fixture", encoding="utf-8")
    return repo


def _finding(
    *,
    claim: str = "Beta verwendet den Wert zwei.",
    severity: str = "P2",
    context: str = "beta = 2",
) -> dict[str, object]:
    return {
        "rule": "TEST-001",
        "claim": claim,
        "impact": "Der Test kann den Pfad eindeutig unterscheiden.",
        "severity": severity,
        "category": "Test",
        "path": "sample.py",
        "line_start": 2,
        "line_end": 2,
        "context": context,
        "confidence": "hoch",
        "evidence": [
            {
                "kind": "source",
                "path": "sample.py",
                "line_start": 2,
                "line_end": 2,
                "quote": "beta = 2",
            }
        ],
        "reproduction": {"command": "", "result": "Quellzeile exakt abgeglichen."},
    }


def _pass(pass_id: int, findings: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "pass_id": pass_id,
        "agent_context_id": f"context-{pass_id}",
        "file_order_seed": 100 + pass_id,
        "role": "Statiker",
        "role_results": [
            {
                "role": role,
                "status": "completed",
                "note": "Fixture-Pruefung abgeschlossen.",
                "checked_scope": ["sample.py"],
            }
            for role in veritas.AUDIT_ROLES
        ],
        "findings": findings,
        "learning_applications": [],
    }


def _run_dir(repo: Path, tmp_path: Path, documents: list[dict[str, object]]) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    veritas.write_json(
        run_dir / "contract.json",
        {
            "schema_version": 1,
            "scope": "Fixture",
            "mode": "full",
            "created_at": "2026-09-01T19:37:42+00:00",
        },
    )
    for pass_id, document in enumerate(documents, start=1):
        veritas.write_json(run_dir / f"pass-{pass_id}" / "findings.json", document)
    veritas.write_json(
        run_dir / "learnings.json", {"schema_version": 1, "learnings": []}
    )
    canonical = veritas.merge_documents(documents)
    for finding in canonical["findings"]:
        if finding["merge_status"] == "BESTAETIGT":
            finding["verifier_status"] = "AKZEPTIERT"
            finding["status"] = "BESTAETIGT"
    canonical["verifier_context_id"] = "fixture-verifier"
    canonical["verifier_applied_at"] = "2026-09-01T00:00:00+00:00"
    veritas.save_canonical(run_dir, canonical, documents)
    return run_dir


def test_validate_pass_accepts_exact_source_evidence(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    errors = veritas.validate_pass_document(_pass(1, [_finding()]), repo, 1)

    assert errors == []


def test_validate_pass_rejects_quote_drift_and_assumption_word(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    finding = _finding(claim="Beta ist wahrscheinlich falsch.")
    finding["evidence"][0]["quote"] = "beta = 3"  # type: ignore[index]

    errors = veritas.validate_pass_document(_pass(1, [finding]), repo, 1)

    assert any("Annahme-Wort" in error for error in errors)
    assert any("stimmt nicht exakt" in error for error in errors)


def test_validate_pass_requires_every_role_and_nonempty_checked_scope(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    document = _pass(1, [])
    document["role_results"][0]["checked_scope"] = []  # type: ignore[index]
    document["role_results"].pop()  # type: ignore[union-attr]

    errors = veritas.validate_pass_document(document, repo)

    assert any("checked_scope" in error for error in errors)
    assert any("Rollen fehlen" in error for error in errors)


def test_learning_hit_requires_fingerprint_from_same_pass(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    document = _pass(1, [])
    document["learning_applications"] = [
        {
            "application_id": "p1-static-L-001",
            "id": "L-001",
            "pass_id": 1,
            "role": "Statiker",
            "location": "sample.py",
            "result": "treffer",
            "finding_fingerprints": [],
        }
    ]

    errors = veritas.validate_pass_document(document, repo)

    assert any("treffer braucht" in error for error in errors)


def test_validate_command_evidence_checks_output_hash(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    finding = _finding()
    finding["evidence"] = [
        {
            "kind": "test",
            "command": "pytest fixture",
            "cwd": str(repo),
            "exit_code": 1,
            "output": "failed",
            "output_sha256": "0" * 64,
            "timestamp": "2026-09-01T00:00:00+00:00",
        }
    ]

    errors = veritas.validate_pass_document(_pass(1, [finding]), repo)

    assert any("Hash passt nicht" in error for error in errors)


def test_validate_source_evidence_must_anchor_finding_location(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "other.py").write_text("beta = 2\n", encoding="utf-8")
    finding = _finding()
    finding["evidence"][0]["path"] = "other.py"  # type: ignore[index]
    finding["evidence"][0]["line_start"] = 1  # type: ignore[index]
    finding["evidence"][0]["line_end"] = 1  # type: ignore[index]

    errors = veritas.validate_pass_document(_pass(1, [finding]), repo)

    assert any("Source-Anker" in error for error in errors)


def test_merge_requires_two_passes_and_verifier_before_confirmation() -> None:
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]

    canonical = veritas.merge_documents(documents)

    assert len(canonical["findings"]) == 1
    finding = canonical["findings"][0]
    assert finding["merge_status"] == "BESTAETIGT"
    assert finding["status"] == "UNBESTAETIGT"
    assert finding["passes"] == [1, 2]


def test_merge_keeps_single_pass_unconfirmed_and_exposes_conflict() -> None:
    single = veritas.merge_documents([_pass(1, [_finding()]), _pass(2, []), _pass(3, [])])
    conflict = veritas.merge_documents(
        [
            _pass(1, [_finding(severity="P1")]),
            _pass(2, [_finding(severity="P2")]),
            _pass(3, []),
        ]
    )

    assert single["findings"][0]["status"] == "UNBESTAETIGT"
    assert conflict["findings"][0]["status"] == "WIDERSPRUCH"
    assert "Severity unterscheidet" in conflict["findings"][0]["conflicts"][0]


def test_merge_reuses_previous_finding_id(tmp_path: Path) -> None:
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    first = veritas.merge_documents(documents)
    first["findings"][0]["id"] = "V-042"
    previous = tmp_path / "previous.json"
    veritas.write_json(previous, first)

    second = veritas.merge_documents(documents, previous)

    assert second["findings"][0]["id"] == "V-042"


def test_merge_updates_learning_counters_idempotently(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    documents = [_pass(1, [_finding()]), _pass(2, []), _pass(3, [])]
    fingerprint = veritas.finding_fingerprint(_finding())
    for pass_id, document in enumerate(documents, start=1):
        document["learning_applications"] = [
            {
                "application_id": f"run-1-pass-{pass_id}-{role}-L-001",
                "id": "L-001",
                "pass_id": pass_id,
                "role": role,
                "location": "sample.py",
                "result": "treffer" if pass_id == 1 and role == "Statiker" else "sauber",
                "finding_fingerprints": (
                    [fingerprint] if pass_id == 1 and role == "Statiker" else []
                ),
            }
            for role in veritas.AUDIT_ROLES
        ]
    run_dir = _run_dir(repo, tmp_path, documents)
    veritas.write_json(
        run_dir / "learnings.json",
        {
            "schema_version": 1,
            "learnings": [
                {
                    "id": "L-001",
                    "sources": ["V-999"],
                    "situation": "Fixture",
                    "tags": ["test"],
                    "rule": "Fixture pruefen.",
                    "counterexample": "sample.py",
                    "status": "aktiv",
                    "applied": 0,
                    "hits": 0,
                    "applications": [],
                }
            ],
        },
    )
    args = argparse.Namespace(run_dir=str(run_dir), repo=str(repo), previous=None)

    assert veritas.command_merge(args) == 0
    assert veritas.command_merge(args) == 0
    learning = veritas.read_json(run_dir / "learnings.json")["learnings"][0]
    assert learning["applied"] == 15
    assert learning["hits"] == 1
    assert learning["applications"][0]["finding_ids"] == ["V-001"]


def test_merge_requires_every_active_learning_for_every_role_and_pass(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    documents = [_pass(1, []), _pass(2, []), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    veritas.write_json(
        run_dir / "learnings.json",
        {
            "schema_version": 1,
            "learnings": [
                {
                    "id": "L-001",
                    "status": "aktiv",
                    "applications": [],
                }
            ],
        },
    )

    with pytest.raises(veritas.VeritasError, match="nicht durch Rolle"):
        veritas.load_passes(run_dir, repo)


def test_apply_verifier_requires_fresh_context_and_accepts_finding(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    finding_id = veritas.read_json(run_dir / "findings.json")["findings"][0]["id"]
    verdict = tmp_path / "verdict.json"
    veritas.write_json(
        verdict,
        {
            "agent_context_id": "fresh-verifier",
            "decisions": [
                {
                    "id": finding_id,
                    "decision": "akzeptiert",
                    "note": "Quelle und Claim wurden unabhaengig abgeglichen.",
                }
            ],
        },
    )
    args = argparse.Namespace(run_dir=str(run_dir), repo=str(repo), input=str(verdict))

    assert veritas.command_apply_verifier(args) == 0
    updated = veritas.read_json(run_dir / "findings.json")
    assert updated["findings"][0]["status"] == "BESTAETIGT"


def _sync_config(repo: Path, vault: Path, tmp_path: Path) -> Path:
    config = tmp_path / "sync.json"
    veritas.write_json(
        config,
        {
            "schema_version": 1,
            "vault_root": str(vault),
            "vault_audit_dir": "10_Projects/HPG/_wiki/audit",
            "project_lessons": "tools/audit/LESSONS.md",
            "project_learnings": "tools/audit/learnings.json",
            "active_learnings": [
                ".agents/skills/hpg-veritas/references/active-learnings.md",
                ".claude/skills/hpg-veritas/references/active-learnings.md",
            ],
            "max_active_learning_lines": 20,
        },
    )
    (repo / "tools" / "audit").mkdir(parents=True)
    for mirror in (".agents", ".claude"):
        (repo / mirror / "skills" / "hpg-veritas" / "references").mkdir(parents=True)
    return config


def test_sync_is_dry_run_by_default_and_apply_reaches_zero_difference(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    config = _sync_config(repo, vault, tmp_path)
    finding_id = veritas.read_json(run_dir / "findings.json")["findings"][0]["id"]
    note = vault / "10_Projects" / "HPG" / "_wiki" / "audit" / "Befunde" / f"{finding_id}.md"
    dry_args = argparse.Namespace(
        run_dir=str(run_dir), repo=str(repo), apply=False
    )

    assert sync_knowledge.command_sync(dry_args, config_path=config) == 0
    assert not note.exists()

    apply_args = argparse.Namespace(
        run_dir=str(run_dir), repo=str(repo), apply=True
    )
    assert sync_knowledge.command_sync(apply_args, config_path=config) == 0
    assert note.is_file()
    expected, _, orphans = sync_knowledge.build_expected(
        run_dir, repo, veritas.read_json(config)
    )
    assert sync_knowledge.diff_plan(expected, orphans)["sync_difference_count"] == 0


def test_sync_preserves_user_status_and_comment(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    config = _sync_config(repo, vault, tmp_path)
    args = argparse.Namespace(run_dir=str(run_dir), repo=str(repo), apply=True)
    assert sync_knowledge.command_sync(args, config_path=config) == 0
    finding_id = veritas.read_json(run_dir / "findings.json")["findings"][0]["id"]
    note = vault / "10_Projects" / "HPG" / "_wiki" / "audit" / "Befunde" / f"{finding_id}.md"
    changed = note.read_text(encoding="utf-8").replace("status: offen", "status: behoben")
    changed = changed.replace(
        "## Nutzerkommentar\n",
        "## Nutzerkommentar\n\nMein manueller Hinweis.\n\n### Eigene Unterueberschrift\n\nBleibt erhalten.\n",
        1,
    )
    note.write_text(changed, encoding="utf-8")

    assert sync_knowledge.command_sync(args, config_path=config) == 0
    synced = note.read_text(encoding="utf-8")
    assert "status: behoben" in synced
    assert "Mein manueller Hinweis." in synced
    assert "### Eigene Unterueberschrift" in synced
    assert "Bleibt erhalten." in synced


def test_sync_reports_orphan_without_deleting_it(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    documents = [_pass(1, []), _pass(2, []), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    config = _sync_config(repo, vault, tmp_path)
    orphan = vault / "10_Projects" / "HPG" / "_wiki" / "audit" / "Befunde" / "V-999.md"
    orphan.parent.mkdir(parents=True)
    orphan.write_text("user note", encoding="utf-8")
    expected, _, orphans = sync_knowledge.build_expected(
        run_dir, repo, veritas.read_json(config)
    )

    plan = sync_knowledge.diff_plan(expected, orphans)

    assert str(orphan) in plan["orphans"]
    assert plan["sync_difference_count"] >= 1
    assert orphan.read_text(encoding="utf-8") == "user note"


def test_safe_vault_dir_rejects_raw_target(tmp_path: Path) -> None:
    config = {
        "vault_root": str(tmp_path),
        "vault_audit_dir": "10_Projects/HPG/_raw/audit",
    }

    with pytest.raises(veritas.VeritasError, match="Geschuetztes Vault-Ziel"):
        sync_knowledge.safe_vault_dir(config)


def test_safe_vault_dir_rejects_protected_absolute_root() -> None:
    config = {
        "vault_root": "C:/Users/david/Brain/_raw",
        "vault_audit_dir": "audit",
    }

    with pytest.raises(veritas.VeritasError, match="Geschuetztes Vault-Ziel"):
        sync_knowledge.safe_vault_dir(config)


def test_sync_rejects_missing_verifier_gate(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    canonical = veritas.read_json(run_dir / "findings.json")
    canonical.pop("verifier_context_id")
    veritas.write_json(run_dir / "findings.json", canonical)
    config = _sync_config(repo, vault, tmp_path)

    with pytest.raises(veritas.VeritasError, match="Verifikatorurteil fehlt"):
        sync_knowledge.build_expected(run_dir, repo, veritas.read_json(config))


def test_sync_writes_every_active_learning_mirror(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    config = _sync_config(repo, vault, tmp_path)
    args = argparse.Namespace(run_dir=str(run_dir), repo=str(repo), apply=True)

    assert sync_knowledge.command_sync(args, config_path=config) == 0

    mirrors = [
        repo / ".agents" / "skills" / "hpg-veritas" / "references" / "active-learnings.md",
        repo / ".claude" / "skills" / "hpg-veritas" / "references" / "active-learnings.md",
    ]
    contents = [mirror.read_text(encoding="utf-8") for mirror in mirrors]
    assert all(mirror.is_file() for mirror in mirrors)
    assert contents[0] == contents[1]
    expected, _, orphans = sync_knowledge.build_expected(
        run_dir, repo, veritas.read_json(config)
    )
    assert sync_knowledge.diff_plan(expected, orphans)["sync_difference_count"] == 0


def test_sync_rejects_active_learning_target_outside_allowlist(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(veritas.VeritasError):
        sync_knowledge.safe_project_target(repo, "docs/active-learnings.md")
    assert sync_knowledge.safe_project_target(
        repo, ".claude/skills/hpg-veritas/references/active-learnings.md"
    ).is_absolute()


def test_sync_rejects_learning_source_without_finding(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    config = _sync_config(repo, vault, tmp_path)
    veritas.write_json(
        run_dir / "learnings.json",
        {
            "schema_version": 1,
            "learnings": [
                {
                    "id": "L-001",
                    "sources": ["V-999"],
                    "situation": "Fixture-Situation.",
                    "rule": "Fixture-Regel.",
                    "counterexample": "Fixture-Gegenbeispiel.",
                    "tags": ["test"],
                    "status": "aktiv",
                    "applied": 0,
                    "hits": 0,
                    "applications": [],
                }
            ],
        },
    )
    args = argparse.Namespace(run_dir=str(run_dir), repo=str(repo), apply=False)

    with pytest.raises(veritas.VeritasError, match="Quellen ohne Befund"):
        sync_knowledge.command_sync(args, config_path=config)


def test_report_filename_stays_stable_across_merge_and_verifier(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    finding_id = veritas.read_json(run_dir / "findings.json")["findings"][0]["id"]
    verdict = tmp_path / "verdict.json"
    veritas.write_json(
        verdict,
        {
            "agent_context_id": "fresh-verifier",
            "decisions": [
                {
                    "id": finding_id,
                    "decision": "akzeptiert",
                    "note": "Quelle und Claim wurden unabhaengig abgeglichen.",
                }
            ],
        },
    )
    args = argparse.Namespace(run_dir=str(run_dir), repo=str(repo), input=str(verdict))

    assert veritas.command_apply_verifier(args) == 0

    reports = sorted(run_dir.glob("AUDIT_REPORT_*.md"))
    assert [report.name for report in reports] == ["AUDIT_REPORT_2026-09-01.md"]
    assert sync_knowledge.report_path(run_dir) == reports[0]


def test_report_date_rejects_contract_without_timestamp() -> None:
    with pytest.raises(veritas.VeritasError, match="created_at"):
        veritas.run_report_date({"schema_version": 1})
