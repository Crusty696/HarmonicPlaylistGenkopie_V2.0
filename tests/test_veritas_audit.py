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
    args = argparse.Namespace(
        run_dir=str(run_dir), repo=str(repo), previous=None, force_remerge=True
    )

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
    expected, _, orphans, _konflikte = sync_knowledge.build_expected(
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
    expected, _, orphans, _konflikte = sync_knowledge.build_expected(
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
    expected, _, orphans, _konflikte = sync_knowledge.build_expected(
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


def test_merge_bestaetigt_trotz_abweichender_formulierung() -> None:
    """Zwei unabhaengige Paesse formulieren nie zeichengleich.

    Vor 2026-09-03 verlangte der Merge Gleichheit von claim, impact und
    category. Damit war BESTAETIGT praktisch unerreichbar: im ersten echten
    Lauf wurden drei in beiden Paessen reproduzierte Befunde WIDERSPRUCH,
    einer davon bei 3/3 Paessen, nur weil eine Kategorie "Performance" statt
    "Laufzeit" hiess.
    """
    a = _finding(claim="Der Zaehler laeuft ueber.")
    b = _finding(claim="Ein Ueberlauf des Zaehlers ist moeglich.")
    b["impact"] = "Andere Formulierung derselben Auswirkung."
    b["category"] = "Laufzeit"

    merged = veritas.merge_documents([_pass(1, [a]), _pass(2, [b]), _pass(3, [])])

    finding = merged["findings"][0]
    assert finding["merge_status"] == "BESTAETIGT"
    assert finding["conflicts"] == []
    assert len(finding["varianten"]) == 2
    assert {v["category"] for v in finding["varianten"]} == {"Test", "Laufzeit"}


def test_merge_meldet_zeichengleiche_prosa_als_unabhaengigkeitsverdacht() -> None:
    """Byte-gleiche Prosa ist kein Reproduktionsbeleg.

    Der zurueckgezogene Lauf `veritas-mixanalysis-2026-09-03` hatte ueber 22
    gemeinsame Befunde 22/22 identische claim/impact/category und 0/22
    identische reproduction — Pass 1 und Pass 2 waren nicht unabhaengig.
    Das Werkzeug wertete das als staerkste Bestaetigung.
    """
    merged = veritas.merge_documents(
        [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    )

    finding = merged["findings"][0]
    assert finding["merge_status"] == "BESTAETIGT"
    assert any(
        h["art"] == "prosa-gleichheit" and "nicht unabhaengig" in h["text"]
        for h in finding["hinweise"]
    )


def test_merge_meldet_pass_paar_statt_prosa_verdacht_bei_pass3() -> None:
    """Pass 3 darf A und B kennen und ihre Formulierung uebernehmen.

    Nur Gleichheit zwischen Pass 1 und Pass 2 ist verdaechtig; sonst haette
    der Hinweis im echten playlist-Lauf 13 von 21 Befunden getroffen, in denen
    Pass 3 auftragsgemaess wortgleich bestaetigt hat.
    """
    merged = veritas.merge_documents(
        [
            _pass(1, [_finding(claim="Der Zaehler laeuft ueber.")]),
            _pass(2, []),
            _pass(3, [_finding(claim="Der Zaehler laeuft ueber.")]),
        ]
    )

    finding = merged["findings"][0]
    assert finding["merge_status"] == "BESTAETIGT"
    arten = {h["art"] for h in finding["hinweise"]}
    assert "prosa-gleichheit" not in arten
    assert arten == {"pass-paar"}


def test_merge_ohne_verdacht_bei_eigener_formulierung() -> None:
    merged = veritas.merge_documents(
        [
            _pass(1, [_finding(claim="Der Zaehler laeuft ueber.")]),
            _pass(2, [_finding(claim="Ein Ueberlauf ist moeglich.")]),
            _pass(3, []),
        ]
    )

    assert merged["findings"][0]["hinweise"] == []


def test_report_zaehlt_unabhaengigkeits_hinweise_im_kopf(tmp_path: Path) -> None:
    """Ein Hinweis, den nur der Einzelbefund traegt, wird ueberlesen."""
    repo = _repo(tmp_path)
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)

    bericht = (run_dir / "AUDIT_REPORT_2026-09-01.md").read_text(encoding="utf-8")

    # Seit die Hinweise typisiert sind, zaehlt der Kopf je Art -- ein
    # Sammelzaehler haette Pass-Paar- und Zeilenbereichs-Hinweise als
    # Prosa-Gleichheit ausgegeben und damit etwas Falsches behauptet.
    assert "Gleiche Prosa in Pass 1 und Pass 2: 1" in bericht
    assert "kein Drei-Pass-Audit" in bericht
    assert "Bestaetigt ohne das Paar 1+2: 0" in bericht


def test_report_zeigt_impact_je_variante(tmp_path: Path) -> None:
    """Der Hinweis loest auch bei reiner Impact-Divergenz aus, also muss der
    Bericht den Impact zeigen -- sonst stehen zwei optisch gleiche Zeilen da."""
    repo = _repo(tmp_path)
    a = _finding()
    b = _finding()
    b["impact"] = "Voellig andere Auswirkung als im ersten Pass."
    documents = [_pass(1, [a]), _pass(2, [b]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)

    bericht = (run_dir / "AUDIT_REPORT_2026-09-01.md").read_text(encoding="utf-8")

    assert "Formulierungen je Pass:" in bericht
    assert "Voellig andere Auswirkung als im ersten Pass." in bericht


# --- Fixes aus dem Werkzeug-Audit vom 2026-09-03 ---------------------------


def test_merge_uebernimmt_ids_aus_dem_eigenen_kanon(tmp_path: Path) -> None:
    """IDs wurden bei jedem Merge nach Fingerprint neu vergeben.

    Kam ein Befund dazu, dessen Hash vorne einsortiert, rutschten alle
    folgenden IDs. Ein Verifikatorurteil fuer V-001 traf danach einen anderen
    Befund.
    """
    repo = _repo(tmp_path)
    (repo / "sample.py").write_text("alpha = 1\nbeta = 2\ngamma = 3\n", encoding="utf-8")
    erst = _finding()
    documents = [_pass(1, [erst]), _pass(2, [erst]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    id_vorher = veritas.read_json(run_dir / "findings.json")["findings"][0]["id"]

    zweit = _finding(claim="Gamma ist drei.", context="gamma = 3")
    zweit["line_start"] = zweit["line_end"] = 3
    zweit["evidence"][0].update(line_start=3, line_end=3, quote="gamma = 3")
    paesse = [_pass(1, [erst, zweit]), _pass(2, [erst, zweit]), _pass(3, [])]
    for pass_id, document in enumerate(paesse, start=1):
        veritas.write_json(run_dir / f"pass-{pass_id}" / "findings.json", document)
    args = argparse.Namespace(
        run_dir=str(run_dir), repo=str(repo), previous=None, force_remerge=True
    )
    assert veritas.command_merge(args) == 0

    kanon = veritas.read_json(run_dir / "findings.json")["findings"]
    nach = {f["fingerprint"]: f["id"] for f in kanon}
    assert nach[veritas.finding_fingerprint(erst)] == id_vorher


def test_merge_verweigert_neuen_lauf_ueber_ein_verifikatorurteil(tmp_path: Path) -> None:
    """Ein erneuter Merge loeschte Status, Note und Kontext des Verifikators."""
    repo = _repo(tmp_path)
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    args = argparse.Namespace(run_dir=str(run_dir), repo=str(repo), previous=None)

    with pytest.raises(veritas.VeritasError, match="Verifikatorurteil"):
        veritas.command_merge(args)


def test_merge_fuehrt_alle_zeilenbereiche(tmp_path: Path) -> None:
    """Gleiche Regel und gleicher Kontext an zwei Stellen ergaben EINEN Befund.

    Der Fingerprint kennt bewusst keine Zeile; ohne die Liste der Fundstellen
    verschwand die zweite Stelle spurlos.
    """
    repo = _repo(tmp_path)
    (repo / "sample.py").write_text("beta = 2\nx = 1\nbeta = 2\n", encoding="utf-8")
    a = _finding()
    a["line_start"] = a["line_end"] = 1
    a["evidence"][0].update(line_start=1, line_end=1)
    b = _finding()
    b["line_start"] = b["line_end"] = 3
    b["evidence"][0].update(line_start=3, line_end=3)

    merged = veritas.merge_documents([_pass(1, [a]), _pass(2, [b]), _pass(3, [])])

    finding = merged["findings"][0]
    assert finding["fundstellen"] == [
        {"line_start": 1, "line_end": 1},
        {"line_start": 3, "line_end": 3},
    ]
    assert any(h["art"] == "zeilenbereich" for h in finding["hinweise"])


def test_merge_nimmt_die_schaerfste_severity() -> None:
    """Der Kanon uebernahm Pass 1; ein von Pass 2 gemeldetes P0 verschwand."""
    merged = veritas.merge_documents(
        [
            _pass(1, [_finding(severity="P3")]),
            _pass(2, [_finding(severity="P0")]),
            _pass(3, []),
        ]
    )

    finding = merged["findings"][0]
    assert finding["merge_status"] == "WIDERSPRUCH"
    assert finding["severity"] == "P0"
    assert {v["severity"] for v in finding["varianten"]} == {"P0", "P3"}


def test_merge_erfindet_keine_kombination_aus_severity_und_konfidenz() -> None:
    """Schaerfste Severity mit hoechster Konfidenz war eine Kombination,
    die kein Pass gemeldet hat.

    Pass 1 meldete P3/hoch, Pass 2 P0/niedrig -- der Kanon zeigte P0/hoch und
    behauptete damit einen kritischen Befund mit hoher Sicherheit, den so
    niemand erhoben hatte. Bei Widerspruch sind jetzt beide Achsen
    konservativ.
    """
    a = _finding(severity="P3")
    b = _finding(severity="P0")
    b["confidence"] = "niedrig"

    merged = veritas.merge_documents([_pass(1, [a]), _pass(2, [b]), _pass(3, [])])

    finding = merged["findings"][0]
    assert finding["severity"] == "P0"
    assert finding["confidence"] == "niedrig"
    gemeldet = {(v["severity"], v["confidence"]) for v in finding["varianten"]}
    assert gemeldet == {("P3", "hoch"), ("P0", "niedrig")}


def test_apply_verifier_lehnt_unbekannte_befund_ids_ab(tmp_path: Path) -> None:
    """Verdikte zu unbekannten IDs verschwanden lautlos mit Exit 0."""
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
                {"id": finding_id, "decision": "akzeptiert", "note": "geprueft"},
                {"id": "V-999", "decision": "verworfen", "note": "gibt es nicht"},
            ],
        },
    )
    args = argparse.Namespace(run_dir=str(run_dir), repo=str(repo), input=str(verdict))

    with pytest.raises(veritas.VeritasError, match="unbekannte Befund-IDs"):
        veritas.command_apply_verifier(args)


def test_apply_verifier_prueft_den_fingerprint_im_verdikt(tmp_path: Path) -> None:
    """Ein Verdikt aus einem aelteren Merge darf nicht am falschen Befund landen."""
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
                    "note": "geprueft",
                    "fingerprint": "0" * 64,
                }
            ],
        },
    )
    args = argparse.Namespace(run_dir=str(run_dir), repo=str(repo), input=str(verdict))

    with pytest.raises(veritas.VeritasError, match="fremden Fingerprint"):
        veritas.command_apply_verifier(args)


def test_report_zeigt_alle_evidenz_und_die_verifikatornote(tmp_path: Path) -> None:
    """Nur das erste Item des ersten Passes war sichtbar, die Note gar nicht."""
    repo = _repo(tmp_path)
    finding = _finding()
    ausgabe = "AssertionError: erwartet 4, gefunden 7"
    finding["evidence"].append(
        {
            "kind": "test",
            "command": "pytest -q",
            "cwd": str(repo),
            "exit_code": 1,
            "output": ausgabe,
            "output_sha256": veritas.sha256_text(ausgabe),
            "timestamp": "2026-09-03T00:00:00+00:00",
        }
    )
    documents = [_pass(1, [finding]), _pass(2, [finding]), _pass(3, [])]
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
                    "decision": "verworfen",
                    "note": "Kein Produktivaufrufer erreichbar.",
                }
            ],
        },
    )
    args = argparse.Namespace(run_dir=str(run_dir), repo=str(repo), input=str(verdict))
    assert veritas.command_apply_verifier(args) == 0

    bericht = (run_dir / "AUDIT_REPORT_2026-09-01.md").read_text(encoding="utf-8")
    assert ausgabe in bericht
    assert "Kein Produktivaufrufer erreichbar." in bericht


def test_leerer_kommando_output_ist_gueltige_evidenz(tmp_path: Path) -> None:
    """Ein sauberes `git status --short` konnte nichts belegen."""
    repo = _repo(tmp_path)
    finding = _finding()
    finding["evidence"].append(
        {
            "kind": "command",
            "command": "git status --short",
            "cwd": str(repo),
            "exit_code": 0,
            "output": "",
            "output_sha256": veritas.sha256_text(""),
            "timestamp": "2026-09-03T00:00:00+00:00",
        }
    )

    assert veritas.validate_pass_document(_pass(1, [finding]), repo, 1) == []


def test_load_passes_prueft_auch_pass_drei(tmp_path: Path) -> None:
    """Pass 3 war von jeder Unabhaengigkeits- und Platzhalterpruefung ausgenommen."""
    repo = _repo(tmp_path)
    run_dir = tmp_path / "run"
    dritter = _pass(3, [])
    dritter["agent_context_id"] = "AUSFUELLEN-FRISCHER-KONTEXT-P3"
    for pass_id, document in enumerate([_pass(1, []), _pass(2, []), dritter], start=1):
        veritas.write_json(run_dir / f"pass-{pass_id}" / "findings.json", document)
    veritas.write_json(run_dir / "learnings.json", {"schema_version": 2, "learnings": []})

    with pytest.raises(veritas.VeritasError, match="Kontext-Platzhalter"):
        veritas.load_passes(run_dir, repo)


def test_init_run_lehnt_fremde_toolchain_ab(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """init-run pruefte nur, dass die venv312-Datei existiert.

    Der Lauf lief mit fremdem Interpreter durch, environment.json hielt
    `matches: False` fest und wurde danach nie wieder gelesen. Hier wird die
    Verdrahtung geprueft, nicht die echte Umgebung -- die Suite laeuft ja in
    venv312 und waere sonst immer gruen.
    """
    repo = _repo(tmp_path)
    monkeypatch.setattr(
        veritas, "validate_toolchain", lambda snapshot: ["Pflichtwerkzeug pytest fehlt"]
    )
    args = argparse.Namespace(
        repo=str(repo),
        run_dir=str(tmp_path / "neuer-lauf"),
        scope="Test",
        mode="delta",
        seed=1,
        previous_learnings=None,
        ignore_toolchain=False,
    )

    with pytest.raises(veritas.VeritasError, match="Umgebung erfuellt den Laufvertrag nicht"):
        veritas.command_init_run(args)

    args.ignore_toolchain = True
    assert veritas.command_init_run(args) == 0
    umgebung = veritas.read_json(Path(args.run_dir) / "environment.json")
    assert umgebung["toolchain_errors"] == ["Pflichtwerkzeug pytest fehlt"]


def test_vault_schutz_faengt_windows_namensvarianten(tmp_path: Path) -> None:
    """'_raw.' passierte den Schutz und landete beim Aufloesen doch in _raw."""
    vault = tmp_path / "vault"
    vault.mkdir()
    for ziel in ("_raw", "_raw.", "_raw...", "_raw ", "00_Claude_Memory.", "_RAW."):
        with pytest.raises(veritas.VeritasError, match="Geschuetztes Vault-Ziel"):
            sync_knowledge.safe_vault_dir(
                {"vault_root": str(vault), "vault_audit_dir": ziel}
            )


def test_text_hinter_dem_endmarker_bleibt_erhalten() -> None:
    """Alles hinter GENERATED_END gehoert dem Nutzer und bleibt stehen.

    Geprueft wird ueber `render_finding_note`, also den Weg, den der Sync
    tatsaechlich geht -- ein Test direkt auf einer Hilfsfunktion sicherte
    einen Pfad ab, den der Produktivcode gar nicht mehr betritt.
    """
    marker_im_zitat = "marker = " + chr(34) + "## Nutzerkommentar" + chr(34)
    notiz = (
        "---\ntype: audit-finding\nid: V-001\nfingerprint: "
        + "a" * 64
        + "\nstatus: behoben\ntags: [veritas]\n---\n\n"
        + sync_knowledge.GENERATED_START
        + "\n\n## Beweis\n\n"
        + marker_im_zitat
        + "\n\n"
        + sync_knowledge.GENERATED_END
        + "\n\n## Nutzerkommentar\n\nMein echter Text.\n"
    )

    inhalt, _ = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), notiz, "2026-09-03"
    )

    assert inhalt is not None
    assert inhalt.count("## Nutzerkommentar") == 1
    assert inhalt.endswith("Mein echter Text.\n")


def test_frontmatter_liest_status_trotz_bom() -> None:
    """Mit BOM galt das Frontmatter als fehlend und der Status fiel zurueck."""
    mit_bom = "\ufeff---\nstatus: behoben\n---\n\nx"

    assert sync_knowledge.frontmatter_value(mit_bom, "status") == "behoben"


def test_waisen_blockieren_das_abschluss_gate_nicht() -> None:
    """Eine Waise machte sync_difference_count dauerhaft ungleich null."""
    plan = sync_knowledge.diff_plan({}, ["C:/vault/Befunde/V-999.md"])

    assert plan["sync_difference_count"] == 0
    assert plan["orphan_count"] == 1


def test_aktive_learnings_melden_abgeschnittene_regeln() -> None:
    """18 von 25 Regeln wurden geschrieben, ohne Hinweis auf den Rest."""
    viele = [
        {"id": f"L-{i:03d}", "status": "aktiv", "rule": f"Regel {i}"}
        for i in range(1, 26)
    ]

    text = sync_knowledge.render_active_learnings(viele, 20)

    assert "weitere, siehe LESSONS.md" in text


def test_sync_ueberschreibt_keine_fremde_notiz(tmp_path: Path) -> None:
    """Beide Laeufe vergeben ab V-001; Lauf B erbte Status und Kommentar von A."""
    repo = _repo(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    config = _sync_config(repo, vault, tmp_path)
    finding_id = veritas.read_json(run_dir / "findings.json")["findings"][0]["id"]
    note = vault / "10_Projects" / "HPG" / "_wiki" / "audit" / "Befunde" / f"{finding_id}.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\ntype: audit-finding\nid: "
        + finding_id
        + "\nfingerprint: "
        + "f" * 64
        + "\nstatus: behoben\n---\n\n"
        + sync_knowledge.GENERATED_START
        + "\n\nfremd\n\n"
        + sync_knowledge.GENERATED_END
        + "\n\n## Nutzerkommentar\n\nGehoert einem anderen Befund.\n",
        encoding="utf-8",
    )
    vorher = note.read_text(encoding="utf-8")
    args = argparse.Namespace(run_dir=str(run_dir), repo=str(repo), apply=True)

    assert sync_knowledge.command_sync(args, config_path=config) == 1
    assert note.read_text(encoding="utf-8") == vorher


# --- C2 und C3: Datenverlust am Vault und am Wissensspeicher ---------------


def _befund_fuer_notiz() -> dict[str, object]:
    return {
        "id": "V-001",
        "fingerprint": "a" * 64,
        "status": "BESTAETIGT",
        "merge_status": "BESTAETIGT",
        "verifier_status": "AKZEPTIERT",
        "severity": "P2",
        "category": "Scoring",
        "path": "hpg_core/playlist.py",
        "line_start": 42,
        "line_end": 42,
        "pass_quote": "2/3",
        "confidence": "hoch",
        "claim": "Neuer Claim.",
        "impact": "Neue Auswirkung.",
        "rule": "R-1",
        "evidence": [],
    }


def _notiz_mit_eigenem_inhalt() -> str:
    return (
        "---\ntype: audit-finding\nid: V-001\nfingerprint: "
        + "a" * 64
        + "\naliases: [Bug Playlist]\nprioritaet: hoch\nstatus: behoben\n"
        "tags: [veritas, audit, scoring, meins]\n---\n\n"
        "# V-001 - Alter Titel\n\n"
        "## Meine Analyse\n\nWICHTIG: betrifft auch main.py Zeile 42.\n\n"
        + sync_knowledge.GENERATED_START
        + "\n\nALTER GENERIERTER INHALT\n\n"
        + sync_knowledge.GENERATED_END
        + "\n\n## Nutzerkommentar\n\nMein Text.\n\n### Eigene Unterueberschrift\n\nBleibt.\n"
    )


def test_notiz_behaelt_alles_ausserhalb_der_marker() -> None:
    """Frueher wurde die ganze Datei neu geschrieben.

    Eigene Frontmatter-Felder, eigene Tags und eigene Abschnitte verschwanden
    restlos, obwohl die GENERATED-Marker versprechen, nur den Block dazwischen
    zu erzeugen.
    """
    inhalt, _ = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), _notiz_mit_eigenem_inhalt(), "2026-09-03"
    )

    assert "aliases: [Bug Playlist]" in inhalt
    assert "prioritaet: hoch" in inhalt
    assert "meins" in inhalt
    assert "## Meine Analyse" in inhalt
    assert "WICHTIG: betrifft auch main.py Zeile 42." in inhalt
    assert "### Eigene Unterueberschrift" in inhalt


def test_notiz_aktualisiert_den_generierten_block() -> None:
    """Der Bereich zwischen den Markern muss trotzdem neu geschrieben werden.

    Die Zusicherung auf genau ein Markerpaar erfuellt nur der chirurgische
    Pfad: wer den Block anhaengt statt ersetzt, laesst die Notiz wachsen.
    """
    inhalt, _ = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), _notiz_mit_eigenem_inhalt(), "2026-09-03"
    )

    assert "ALTER GENERIERTER INHALT" not in inhalt
    assert "severity: P2" in inhalt
    assert "updated: 2026-09-03" in inhalt
    assert inhalt.count(sync_knowledge.GENERATED_START) == 1
    assert inhalt.count(sync_knowledge.GENERATED_END) == 1
    kern = inhalt.split(sync_knowledge.GENERATED_START)[1].split(
        sync_knowledge.GENERATED_END
    )[0]
    assert "Neue Auswirkung." in kern


def test_notiz_ohne_marker_wird_nicht_ueberschrieben() -> None:
    """Von Hand angelegte Notizen sind kein Ziel des Generators."""
    inhalt, konflikt = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), "---\nstatus: offen\n---\n\nHandarbeit.\n", "2026-09-03"
    )

    assert inhalt is None
    assert konflikt["grund"] == "Notiz ohne VERITAS-Marker"


def test_learnings_werden_vereinigt_statt_ersetzt(tmp_path: Path) -> None:
    """Der lauf-lokale Stand ersetzte die persistente Datei komplett.

    Ein Learning aus einem frueheren Lauf verschwand damit, sobald ein neuer
    Lauf synchronisierte.
    """
    ziel = tmp_path / "learnings.json"
    veritas.write_json(
        ziel,
        {
            "schema_version": 2,
            "learnings": [
                {"id": "L-001", "rule": "Altes Wissen", "status": "aktiv"},
                {"id": "L-002", "rule": "Wird ueberschrieben", "status": "aktiv"},
            ],
        },
    )
    lauf = {
        "schema_version": 2,
        "learnings": [
            {"id": "L-002", "rule": "Neue Fassung", "status": "aktiv"},
            {"id": "L-003", "rule": "Neu in diesem Lauf", "status": "aktiv"},
        ],
    }

    vereinigt = sync_knowledge.vereinige_learnings(ziel, lauf)

    nach_id = {x["id"]: x["rule"] for x in vereinigt["learnings"]}
    assert nach_id == {
        "L-001": "Altes Wissen",
        "L-002": "Neue Fassung",
        "L-003": "Neu in diesem Lauf",
    }


def test_learning_aus_dem_bestand_behaelt_fremde_quellen(tmp_path: Path) -> None:
    """Sonst koennte akkumuliertes Wissen strukturell nie mitgefuehrt werden."""
    daten = {
        "schema_version": 2,
        "learnings": [
            {
                "id": "L-001",
                "sources": ["V-999"],
                "situation": "s",
                "rule": "r",
                "counterexample": "g",
                "tags": [],
                "status": "aktiv",
                "applied": 0,
                "hits": 0,
                "applications": [],
            }
        ],
    }

    # Aus dem Bestand: genau diese Quelle ist Historie, kein Tippfehler.
    assert sync_knowledge.validate_learnings(daten, set(), {"L-001": {"V-999"}})

    # Neu in diesem Lauf: V-999 muss auffallen.
    with pytest.raises(veritas.VeritasError, match="Quellen ohne Befund"):
        sync_knowledge.validate_learnings(daten, set(), {})


def test_bekanntes_learning_schuetzt_nur_seine_eigenen_altquellen(
    tmp_path: Path,
) -> None:
    """Sonst waere ein bekanntes Learning dauerhaft ohne Tippfehlerschutz.

    Haengt die Freigabe an der Learning-ID statt an der einzelnen Quelle, dann
    laesst sich an L-001 jede erfundene Quelle nachtragen, sobald es einmal im
    persistenten Speicher steht.
    """
    daten = {
        "schema_version": 2,
        "learnings": [
            {
                "id": "L-001",
                "sources": ["V-888"],
                "situation": "s",
                "rule": "r",
                "counterexample": "g",
                "tags": [],
                "status": "aktiv",
                "applied": 0,
                "hits": 0,
                "applications": [],
            }
        ],
    }

    with pytest.raises(veritas.VeritasError, match="Quellen ohne Befund"):
        sync_knowledge.validate_learnings(daten, set(), {"L-001": {"V-999"}})


def test_vereinigung_lehnt_bestand_ohne_id_und_mit_doppelter_id_ab(
    tmp_path: Path,
) -> None:
    """Ein Eintrag ohne id liesse sich nie wieder aktualisieren.

    Eine doppelte id wurde von der Vereinigung zweimal ausgegeben.
    """
    ziel = tmp_path / "learnings.json"
    veritas.write_json(
        ziel,
        {"schema_version": 2, "learnings": [{"rule": "ohne id"}]},
    )
    with pytest.raises(veritas.VeritasError, match="ohne id"):
        sync_knowledge.vereinige_learnings(ziel, {"schema_version": 2, "learnings": []})

    veritas.write_json(
        ziel,
        {
            "schema_version": 2,
            "learnings": [{"id": "L-001", "rule": "a"}, {"id": "L-001", "rule": "b"}],
        },
    )
    with pytest.raises(veritas.VeritasError, match="doppelte Learning-ID"):
        sync_knowledge.vereinige_learnings(ziel, {"schema_version": 2, "learnings": []})


def test_sync_traegt_bestands_learning_in_alle_ziele(tmp_path: Path) -> None:
    """End-to-End ueber eine bereits gefuellte learnings.json.

    Nur hier faellt auf, wenn der vereinigte Bestand ungeprueft in die
    Renderer laeuft: die greifen per Index auf `sources`, `applied` und `hits`
    zu und brechen sonst mit KeyError statt mit einer Meldung ab.
    """
    repo = _repo(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    config = _sync_config(repo, vault, tmp_path)
    bestand = repo / "tools" / "audit" / "learnings.json"
    bestand.parent.mkdir(parents=True, exist_ok=True)
    veritas.write_json(
        bestand,
        {
            "schema_version": 2,
            "learnings": [
                {
                    "id": "L-042",
                    "sources": ["V-777"],
                    "situation": "Aus einem frueheren Lauf.",
                    "rule": "Alte Regel bleibt gueltig.",
                    "counterexample": "Alter Gegenbeleg.",
                    "tags": ["alt"],
                    "status": "aktiv",
                    "applied": 0,
                    "hits": 0,
                    "applications": [],
                }
            ],
        },
    )
    args = argparse.Namespace(run_dir=str(run_dir), repo=str(repo), apply=True)

    assert sync_knowledge.command_sync(args, config_path=config) == 0

    assert "L-042" in [
        eintrag["id"] for eintrag in veritas.read_json(bestand)["learnings"]
    ]
    assert "Alte Regel bleibt gueltig." in (
        repo / "tools" / "audit" / "LESSONS.md"
    ).read_text(encoding="utf-8")
    # Die aktiven Regeln sind ein eigenes Ziel: faellt jemand dort auf den
    # Lauf zurueck, bliebe die Suite ohne diese Zeile gruen.
    assert "L-042" in (
        repo / ".claude" / "skills" / "hpg-veritas" / "references" / "active-learnings.md"
    ).read_text(encoding="utf-8")


def test_notiz_mit_tags_im_blockstil_behaelt_gueltiges_frontmatter() -> None:
    """Eine Inline-Liste ueber den Blockstil zu schreiben zerstoert das YAML.

    Obsidian verliert dann das gesamte Frontmatter, nicht nur die Tags.
    """
    notiz = _notiz_mit_eigenem_inhalt().replace(
        "tags: [veritas, audit, scoring, meins]\n",
        "tags:\n  - veritas\n  - meins\n",
    )

    inhalt, _ = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), notiz, "2026-09-03"
    )

    assert inhalt is not None
    assert "tags:\n  - veritas\n  - meins\n" in inhalt
    assert "tags: [" not in inhalt


def test_zweiter_block_hinter_dem_ende_bleibt_nutzerterritorium() -> None:
    """Alles hinter dem Endmarker gehoert dem Nutzer -- auch was wie ein Block aussieht.

    Frueher galt jedes zweite Markerpaar als Konflikt. Das traf aber auch den
    Nutzer, der in seinem Kommentar eine Markerzeile woertlich zitiert: seine
    Notiz war dauerhaft blockiert, ohne dass er den Zusammenhang erkennen
    kann. Ein Block hinter dem Ende wird deshalb wie jeder andere Nutzertext
    unangetastet durchgereicht; einen veralteten Zweitblock raeumt der Sync
    nicht auf, er beschaedigt ihn aber auch nicht.
    """
    zweitblock = (
        sync_knowledge.GENERATED_START
        + "\n\nZWEITER BLOCK\n\n"
        + sync_knowledge.GENERATED_END
        + "\n"
    )
    doppelt = _notiz_mit_eigenem_inhalt() + zweitblock

    inhalt, konflikt = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), doppelt, "2026-09-03"
    )

    assert konflikt is None or isinstance(konflikt, str)
    assert inhalt is not None
    assert inhalt.endswith(zweitblock)
    assert "ALTER GENERIERTER INHALT" not in inhalt


def test_zweiter_startmarker_innerhalb_des_blocks_wird_gemeldet() -> None:
    """Dort wuerde nur bis zum ersten Ende aktualisiert -- der Rest bliebe alt."""
    kaputt = _notiz_mit_eigenem_inhalt().replace(
        "ALTER GENERIERTER INHALT",
        "ALTER GENERIERTER INHALT\n\n" + sync_knowledge.GENERATED_START,
    )

    inhalt, konflikt = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), kaputt, "2026-09-03"
    )

    assert inhalt is None
    assert konflikt["grund"] == "mehrfache VERITAS-Marker"


def test_generierter_titel_wandert_mit_dem_claim() -> None:
    """Der Titel steht ausserhalb der Marker, stammt aber vom Generator.

    Ohne Nachziehen zeigen Obsidian-Titel, Graph und Suche dauerhaft den
    alten Wortlaut. Eine vom Nutzer umbenannte Ueberschrift bleibt stehen.
    """
    inhalt, _ = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), _notiz_mit_eigenem_inhalt(), "2026-09-03"
    )
    assert inhalt is not None
    assert "# V-001 - Neuer Claim." in inhalt
    assert "# V-001 - Alter Titel" not in inhalt

    umbenannt = _notiz_mit_eigenem_inhalt().replace(
        "# V-001 - Alter Titel", "# Mein eigener Titel"
    )
    inhalt2, _ = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), umbenannt, "2026-09-03"
    )
    assert inhalt2 is not None
    assert "# Mein eigener Titel" in inhalt2


def _befund_mit_marker_im_zitat() -> dict[str, object]:
    """Ein Audit ueber sync_knowledge.py selbst zitiert die Markerzeilen."""
    befund = _befund_fuer_notiz()
    befund["path"] = "tools/audit/sync_knowledge.py"
    befund["evidence"] = [
        {
            "pass_id": 1,
            "items": [
                {
                    "kind": "source",
                    "path": "tools/audit/sync_knowledge.py",
                    "line_start": 57,
                    "quote": (
                        f'GENERATED_START = "{sync_knowledge.GENERATED_START}"\n'
                        f'GENERATED_END = "{sync_knowledge.GENERATED_END}"'
                    ),
                }
            ],
        }
    ]
    return befund


def test_marker_im_evidenz_zitat_zerschneidet_die_notiz_nicht() -> None:
    """Der aeussere Marker zaehlt, nicht der erste.

    Ein Audit ueber dieses Modul zitiert die Markerzeilen im Beweis. Wird das
    erste `END` genommen oder blind gezaehlt, meldet der zweite Lauf einen
    Konflikt an einer Notiz, die das Werkzeug selbst geschrieben hat -- das
    Abschluss-Gate waere dauerhaft unerreichbar.
    """
    befund = _befund_mit_marker_im_zitat()
    erst, _ = sync_knowledge.render_finding_note(befund, "", "2026-09-03")

    assert erst is not None
    assert erst.count(sync_knowledge.GENERATED_START) == 2

    zweit, konflikt = sync_knowledge.render_finding_note(befund, erst, "2026-09-03")

    assert konflikt is None or isinstance(konflikt, str)
    assert zweit is not None
    # Zweiter Lauf ohne Aenderung am Befund: die Notiz muss stabil bleiben.
    assert zweit == erst


def test_eigenes_verschachteltes_frontmatter_bleibt_unveraendert() -> None:
    """Eingerueckte Zeilen gehoeren zum Wert darueber, nicht zur obersten Ebene.

    Wurde jede Zeile als Schluessel gelesen, verlor ein eigenes Feld mit einem
    Unterschluessel `status` oder `datei` seinen Wert und seine Einrueckung.
    """
    notiz = _notiz_mit_eigenem_inhalt().replace(
        "prioritaet: hoch\n",
        "meins:\n  status: mein-eigener-wert\n  datei: meine-datei.md\n",
    )

    inhalt, _ = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), notiz, "2026-09-03"
    )

    assert inhalt is not None
    assert "  status: mein-eigener-wert" in inhalt
    assert "  datei: meine-datei.md" in inhalt
    # Der generierte Schluessel derselben Namen steht genau einmal.
    assert inhalt.count("\nstatus: ") == 1
    assert inhalt.count("\ndatei: ") == 1


def test_tags_mit_kommentar_gilt_als_blockstil() -> None:
    """`tags: # Kommentar` mit Eintraegen darunter ist kein Inline-Wert.

    Wurde der Kommentar als Wert gelesen, entstand
    `tags: [# meine Tags, veritas, ...]` mit einer verwaisten Listenzeile
    darunter -- ungueltiges YAML.
    """
    notiz = _notiz_mit_eigenem_inhalt().replace(
        "tags: [veritas, audit, scoring, meins]\n",
        "tags: # meine Tags\n  - eigen\n",
    )

    inhalt, _ = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), notiz, "2026-09-03"
    )

    assert inhalt is not None
    assert "tags: # meine Tags\n  - eigen\n" in inhalt
    assert "tags: [" not in inhalt


def test_titel_im_codeblock_wird_nicht_fuer_die_ueberschrift_gehalten() -> None:
    """Eine gleich aussehende Zeile in einem Zitat darf nicht getroffen werden.

    Frueher suchte die Funktion die erste Ueberschrift ausserhalb eines
    Codeblocks. Dieser Zustandsautomat haengt an fremdem Text: ein einzelner
    nicht geschlossener Codeblock liesse ihn nie zum Ende kommen und froere
    den Titel dauerhaft ein, ohne dass es auffiele. Jetzt zaehlt nur die erste
    nicht leere Zeile -- steht dort etwas anderes als die erzeugte Form,
    gehoert der Kopf dem Nutzer und der Titel bleibt bewusst stehen.
    """
    notiz = _notiz_mit_eigenem_inhalt().replace(
        "# V-001 - Alter Titel",
        "```text\n# V-001 - Zitat aus dem alten Bericht\n```\n\n# V-001 - Alter Titel",
    )

    inhalt, _ = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), notiz, "2026-09-03"
    )

    assert inhalt is not None
    # Das Zitat bleibt unangetastet -- das ist der Kern.
    assert "# V-001 - Zitat aus dem alten Bericht" in inhalt
    # Und der echte Titel wird eingefroren statt falsch getroffen.
    assert "# V-001 - Alter Titel" in inhalt
    assert "# V-001 - Neuer Claim." not in inhalt


def test_zweiter_apply_lauf_aendert_keine_einzige_datei(tmp_path: Path) -> None:
    """Idempotenz ueber zwei echte Laeufe, nicht nur aus dem Code geschlossen.

    Nur hier faellt auf, wenn das Werkzeug seine eigene Ausgabe im zweiten
    Lauf nicht mehr wiedererkennt.
    """
    repo = _repo(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    config = _sync_config(repo, vault, tmp_path)
    # Ein LEERER Bestand wuerde die Vereinigung gar nicht auf die Probe
    # stellen -- der interessante Fall ist ein Learning aus einem frueheren
    # Lauf, das beide Laeufe unveraendert ueberstehen muss.
    bestand = repo / "tools" / "audit" / "learnings.json"
    bestand.parent.mkdir(parents=True, exist_ok=True)
    veritas.write_json(
        bestand,
        {
            "schema_version": 2,
            "learnings": [
                {
                    "id": "L-042",
                    "sources": ["V-777"],
                    "situation": "Aus einem frueheren Lauf.",
                    "rule": "Alte Regel bleibt gueltig.",
                    "counterexample": "Alter Gegenbeleg.",
                    "tags": ["alt"],
                    "status": "aktiv",
                    "applied": 0,
                    "hits": 0,
                    "applications": [],
                }
            ],
        },
    )
    args = argparse.Namespace(run_dir=str(run_dir), repo=str(repo), apply=True)

    assert sync_knowledge.command_sync(args, config_path=config) == 0
    vorher = {
        pfad: pfad.read_bytes() for pfad in vault.rglob("*.md")
    }
    assert vorher
    # Die C2-Ziele liegen im Repository, nicht im Vault -- einschliesslich der
    # beiden Spiegel fuer die aktiven Regeln. Ohne sie belegt der Test die
    # Idempotenz der Vereinigung nicht.
    def _repo_ziele() -> dict[Path, bytes]:
        wurzeln = (
            repo / "tools" / "audit",
            repo / ".claude" / "skills" / "hpg-veritas",
            repo / ".agents" / "skills" / "hpg-veritas",
        )
        return {
            pfad: pfad.read_bytes()
            for wurzel in wurzeln
            if wurzel.is_dir()
            for pfad in wurzel.rglob("*")
            if pfad.is_file()
        }

    vor_repo = _repo_ziele()
    assert vor_repo

    assert sync_knowledge.command_sync(args, config_path=config) == 0

    nach_repo = _repo_ziele()
    nachher = {pfad: pfad.read_bytes() for pfad in vault.rglob("*.md")}
    assert nachher == vorher
    assert nach_repo == vor_repo


def test_ungerade_fence_im_zitat_verschiebt_die_marker_nicht() -> None:
    """Ein Zitat mit einer einzelnen ```-Zeile kippte die Fence-Zaehlung.

    Der zweite Lauf hielt dann die eigene Endmarke fuer Teil eines
    Codeblocks und meldete "Notiz ohne VERITAS-Marker" an einer Notiz, die
    das Werkzeug selbst geschrieben hatte -- das Abschluss-Gate war fuer
    diesen Lauf unerreichbar.
    """
    befund = _befund_fuer_notiz()
    befund["path"] = "docs/beispiel.md"
    befund["evidence"] = [
        {
            "pass_id": 1,
            "items": [
                {
                    "kind": "source",
                    "path": "docs/beispiel.md",
                    "line_start": 1,
                    "quote": "Beispiel:\n```python\nprint(1)",
                }
            ],
        }
    ]

    erst, _ = sync_knowledge.render_finding_note(befund, "", "2026-09-03")
    assert erst is not None

    zweit, konflikt = sync_knowledge.render_finding_note(befund, erst, "2026-09-03")

    assert konflikt is None or isinstance(konflikt, str)
    assert zweit == erst


def test_mehrzeilige_inline_liste_bleibt_unangetastet() -> None:
    """Schliesst die Klammer erst in der Folgezeile, ist es kein Inline-Wert.

    Wurde trotzdem eine Inline-Liste darueber geschrieben, blieb die zweite
    Zeile als verwaister Rest stehen und Obsidian verlor das gesamte
    Frontmatter -- also auch Status und eigene Felder.
    """
    notiz = _notiz_mit_eigenem_inhalt().replace(
        "tags: [veritas, audit, scoring, meins]\n",
        "tags: [veritas,\n  meins]\n",
    )

    inhalt, _ = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), notiz, "2026-09-03"
    )

    assert inhalt is not None
    assert "tags: [veritas,\n  meins]\n" in inhalt
    assert inhalt.count("tags:") == 1


def test_defekter_bestandseintrag_meldet_statt_abzustuerzen(tmp_path: Path) -> None:
    """Der vereinigte Bestand geht durch dieselbe Pruefung wie der Lauf.

    Vorher lief ein unvollstaendiger Alteintrag ungeprueft in die Renderer
    und brach dort mit KeyError ab statt mit einer Meldung.
    """
    repo = _repo(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    config = _sync_config(repo, vault, tmp_path)
    bestand = repo / "tools" / "audit" / "learnings.json"
    bestand.parent.mkdir(parents=True, exist_ok=True)
    veritas.write_json(
        bestand,
        {
            "schema_version": 2,
            "learnings": [{"id": "L-042", "rule": "Ohne sources und status."}],
        },
    )
    args = argparse.Namespace(run_dir=str(run_dir), repo=str(repo), apply=False)

    with pytest.raises(veritas.VeritasError, match="L-042"):
        sync_knowledge.command_sync(args, config_path=config)


def _befund_mit_zitat(quote: str) -> dict[str, object]:
    befund = _befund_fuer_notiz()
    befund["path"] = "tools/audit/sync_knowledge.py"
    befund["evidence"] = [
        {
            "pass_id": 1,
            "items": [
                {
                    "kind": "source",
                    "path": "tools/audit/sync_knowledge.py",
                    "line_start": 57,
                    "quote": quote,
                }
            ],
        }
    ]
    return befund


def test_markerzeile_im_zitat_wird_entschaerft() -> None:
    """Ein Audit ueber dieses Modul zitiert die Markerzeilen selbst.

    Stand die Zeile unveraendert im Beweis, fand der naechste Lauf in seiner
    eigenen Notiz mehrere Marker und meldete einen Konflikt, den niemand
    aufloesen kann. Entschaerft wird nur eine Zeile, die dem Marker EXAKT
    gleicht.
    """
    befund = _befund_mit_zitat(
        f"```\n{sync_knowledge.GENERATED_END}\n```"
    )

    erst, _ = sync_knowledge.render_finding_note(befund, "", "2026-09-03")

    assert erst is not None
    assert erst.count(sync_knowledge.GENERATED_END) == 1
    assert "-- >" in erst

    zweit, konflikt = sync_knowledge.render_finding_note(befund, erst, "2026-09-03")

    assert konflikt is None or isinstance(konflikt, str)
    assert zweit == erst


def test_offener_codeblock_im_nutzertext_versteckt_die_marker_nicht() -> None:
    """Ein nicht geschlossener Codeblock ist in Obsidian ein haeufiger Tippfehler.

    Solange die Marker-Erkennung ```-Zeilen mitzaehlte, galten die echten
    Marker danach als "im Codeblock" -- der Sync meldete "Notiz ohne
    VERITAS-Marker" an seiner eigenen Notiz und nannte einen Grund, der
    nachweislich falsch war.
    """
    notiz = _notiz_mit_eigenem_inhalt().replace(
        "## Meine Analyse\n\nWICHTIG:",
        "## Meine Analyse\n\n```python\nvergessen = True\n\nWICHTIG:",
    )

    inhalt, konflikt = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), notiz, "2026-09-03"
    )

    assert konflikt is None or isinstance(konflikt, str)
    assert inhalt is not None
    assert "vergessen = True" in inhalt
    assert "Mein Text." in inhalt


def test_bestand_mit_learnings_null_meldet_statt_abzustuerzen(tmp_path: Path) -> None:
    """Eine von Hand editierte Datei endete in einem TypeError statt in einer Meldung."""
    repo = _repo(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    config = _sync_config(repo, vault, tmp_path)
    bestand = repo / "tools" / "audit" / "learnings.json"
    bestand.parent.mkdir(parents=True, exist_ok=True)
    veritas.write_json(bestand, {"schema_version": 2, "learnings": None})
    args = argparse.Namespace(run_dir=str(run_dir), repo=str(repo), apply=False)

    with pytest.raises(veritas.VeritasError, match="learnings muss Liste sein"):
        sync_knowledge.command_sync(args, config_path=config)


def test_vereinigung_hebt_die_schema_version_nicht_still_an(tmp_path: Path) -> None:
    """Ein Sync ist keine Migration.

    Blind SCHEMA_VERSION zu schreiben hob eine Bestandsdatei an, obwohl der
    Lauf selbst noch die aeltere Fassung lieferte. Herabgestuft wird trotzdem
    nie.
    """
    ziel = tmp_path / "learnings.json"
    veritas.write_json(
        ziel, {"schema_version": 1, "learnings": [{"id": "L-001", "rule": "alt"}]}
    )

    gleich = sync_knowledge.vereinige_learnings(
        ziel, {"schema_version": 1, "learnings": []}
    )
    assert gleich["schema_version"] == 1

    hoeher = sync_knowledge.vereinige_learnings(
        ziel, {"schema_version": 2, "learnings": []}
    )
    assert hoeher["schema_version"] == 2


def test_markerzeile_in_der_auswirkung_wird_entschaerft() -> None:
    """Nicht nur das Zitat wird roh interpoliert.

    `impact`, `claim`, `rule` und `path` sind auf keine Zeile beschraenkt.
    Lag die Entschaerfung nur um den Beweis, konnte ein Audit ueber dieses
    Modul die Markerzeile ueber die Auswirkung einschleusen -- der naechste
    Lauf fand dann mehrere Marker in seiner eigenen Notiz.
    """
    befund = _befund_fuer_notiz()
    befund["impact"] = f"Die Zeile\n{sync_knowledge.GENERATED_END}\nsteht im Block."

    erst, _ = sync_knowledge.render_finding_note(befund, "", "2026-09-03")

    assert erst is not None
    assert erst.count(sync_knowledge.GENERATED_END) == 1

    zweit, konflikt = sync_knowledge.render_finding_note(befund, erst, "2026-09-03")

    assert konflikt is None or isinstance(konflikt, str)
    assert zweit == erst


def test_markerzeile_im_claim_wird_entschaerft() -> None:
    """Der Titel steht ausserhalb der Marker und wird ebenfalls roh gesetzt."""
    befund = _befund_fuer_notiz()
    befund["claim"] = f"Kaputt\n{sync_knowledge.GENERATED_START}\nEnde."

    erst, _ = sync_knowledge.render_finding_note(befund, "", "2026-09-03")

    assert erst is not None
    assert erst.count(sync_knowledge.GENERATED_START) == 1


def test_entschaerfung_wird_in_der_notiz_ausgewiesen() -> None:
    """Sonst stuende dort ein als woertlich ausgewiesenes Zitat, das es nicht ist."""
    ohne = _befund_fuer_notiz()
    mit = _befund_fuer_notiz()
    mit["impact"] = f"x\n{sync_knowledge.GENERATED_END}\ny"

    schlicht, _ = sync_knowledge.render_finding_note(ohne, "", "2026-09-03")
    entschaerft, _ = sync_knowledge.render_finding_note(mit, "", "2026-09-03")

    assert sync_knowledge.HINWEIS_ENTSCHAERFT not in schlicht
    assert sync_knowledge.HINWEIS_ENTSCHAERFT in entschaerft


def test_bom_der_notiz_bleibt_erhalten() -> None:
    """Notepad und PowerShell 5.1 schreiben UTF-8 mit BOM.

    Der byteerhaltende Pfad streifte es beim Lesen ab und setzte es nie
    zurueck -- eine stille Formataenderung an einer Nutzerdatei bei jedem Sync.
    """
    inhalt, _ = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), "\ufeff" + _notiz_mit_eigenem_inhalt(), "2026-09-03"
    )

    assert inhalt is not None
    assert inhalt.startswith("\ufeff---\n")


def test_markerzeile_im_claim_auch_beim_aktualisieren_entschaerft() -> None:
    """Der Neuanlage-Pfad entschaerfte, der Aktualisierungs-Pfad nicht.

    `_titel_aktualisieren` bekam den ROHEN Claim und schrieb die Markerzeile
    damit VOR den Startmarker: Lauf 2 wuchs, Lauf 3 meldete dauerhaft
    "mehrfache VERITAS-Marker" -- an einer Notiz, die das Werkzeug selbst
    erzeugt hatte. Alle bisherigen Entschaerfungs-Tests starteten mit einer
    leeren Notiz und konnten das nicht sehen.
    """
    befund = _befund_fuer_notiz()
    befund["claim"] = f"Kaputt\n{sync_knowledge.GENERATED_START}\nEnde."

    erst, _ = sync_knowledge.render_finding_note(befund, "", "2026-09-03")
    assert erst is not None

    zweit, konflikt = sync_knowledge.render_finding_note(befund, erst, "2026-09-03")

    assert konflikt is None or isinstance(konflikt, str)
    assert zweit is not None
    assert zweit.count(sync_knowledge.GENERATED_START) == 1
    assert zweit == erst

    dritt, konflikt3 = sync_knowledge.render_finding_note(befund, zweit, "2026-09-03")
    assert konflikt3 is None or isinstance(konflikt3, str)
    assert dritt == erst


def test_doppeltes_bom_verliert_kein_zeichen() -> None:
    """`lstrip` entfernte beliebig viele BOMs, zurueck kam genau eines."""
    inhalt, _ = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), "\ufeff\ufeff" + _notiz_mit_eigenem_inhalt(), "2026-09-03"
    )

    assert inhalt is None or not inhalt.startswith("\ufeff---")


@pytest.mark.parametrize(
    "feld,wert",
    [
        ("category", "Scoring\n<!-- VERITAS:GENERATED:START -->\nX"),
        ("pass_quote", "2/3\n---\nX"),
        ("severity", "P2\nzweite Zeile"),
    ],
)
def test_mehrzeilige_frontmatter_werte_lassen_die_notiz_nicht_wachsen(
    feld: str, wert: str
) -> None:
    """Frontmatter-Werte werden roh interpoliert und sind nicht einzeilig.

    Eine Markerzeile ist dort schlimmer als im Rumpf: `_marker_positionen`
    liest nur den Rumpf und meldet deshalb KEINEN Konflikt -- die Notiz wuchs
    bei jedem Lauf um einen Marker, und `--apply` endete fuer immer mit einer
    Differenz, ohne dass irgendwo stand warum. Eine `---`-Zeile schnitt
    zusaetzlich das Frontmatter ab, schlichte Mehrzeiligkeit liess die Notiz
    ebenfalls wachsen.
    """
    befund = _befund_fuer_notiz()
    befund[feld] = wert

    notiz = ""
    laengen: list[int] = []
    for _ in range(4):
        notiz, konflikt = sync_knowledge.render_finding_note(
            befund, notiz, "2026-09-03"
        )
        assert notiz is not None, konflikt
        laengen.append(len(notiz))

    assert len(set(laengen)) == 1
    assert notiz.count(sync_knowledge.GENERATED_START) == 1
    assert notiz.count(sync_knowledge.GENERATED_END) == 1


def test_voller_claim_steht_im_block() -> None:
    """Der Titel wird zusammengezogen -- der Wortlaut darf nicht verloren gehen.

    Sonst stuende ein mehrzeiliger Claim nach dem Sync nirgends mehr
    vollstaendig in der Notiz, ohne jeden Hinweis darauf.
    """
    befund = _befund_fuer_notiz()
    befund["claim"] = "Erste Zeile.\nZweite Zeile."

    inhalt, _ = sync_knowledge.render_finding_note(befund, "", "2026-09-03")

    assert inhalt is not None
    assert "# V-001 - Erste Zeile. Zweite Zeile." in inhalt
    kern = inhalt.split(sync_knowledge.GENERATED_START)[1]
    assert "- Claim: Erste Zeile.\nZweite Zeile." in kern


def test_bestands_learning_steht_im_moc_und_ist_keine_waise(tmp_path: Path) -> None:
    """Alle Ziele beschreiben den GESAMTEN Wissensstand, nicht nur den Lauf.

    Solange Vault-Notizen, MOC und Waisenerkennung nur den Lauf sahen, stand
    ein akkumuliertes Learning zwar in LESSONS.md, fehlte aber im MOC und galt
    als Waise -- seine Notiz wurde nie wieder aktualisiert. Genau in dem Fall,
    fuer den die Vereinigung gebaut wurde.
    """
    repo = _repo(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    documents = [_pass(1, [_finding()]), _pass(2, [_finding()]), _pass(3, [])]
    run_dir = _run_dir(repo, tmp_path, documents)
    config = _sync_config(repo, vault, tmp_path)
    bestand = repo / "tools" / "audit" / "learnings.json"
    bestand.parent.mkdir(parents=True, exist_ok=True)
    veritas.write_json(
        bestand,
        {
            "schema_version": 2,
            "learnings": [
                {
                    "id": "L-042",
                    "sources": ["V-777"],
                    "situation": "Aus einem frueheren Lauf.",
                    "rule": "Alte Regel bleibt gueltig.",
                    "counterexample": "Alter Gegenbeleg.",
                    "tags": ["alt"],
                    "status": "aktiv",
                    "applied": 0,
                    "hits": 0,
                    "applications": [],
                }
            ],
        },
    )
    args = argparse.Namespace(run_dir=str(run_dir), repo=str(repo), apply=True)
    assert sync_knowledge.command_sync(args, config_path=config) == 0

    expected, _, orphans, _konflikte = sync_knowledge.build_expected(
        run_dir, repo, veritas.read_json(config)
    )

    audit_dir = vault / "10_Projects" / "HPG" / "_wiki" / "audit"
    assert (audit_dir / "Learnings" / "L-042.md").is_file()
    assert "L-042" in (audit_dir / "AUDIT-MOC.md").read_text(encoding="utf-8")
    assert not any("L-042" in pfad for pfad in orphans)
    assert sync_knowledge.diff_plan(expected, orphans)["sync_difference_count"] == 0


def test_leere_kategorie_erzeugt_keine_scheindifferenz() -> None:
    """`[veritas, audit, ]` raeumte der naechste Lauf auf.

    Das meldete eine Aenderung an einer Datei, die niemand angefasst hat.
    """
    befund = _befund_fuer_notiz()
    befund["category"] = ""

    erst, _ = sync_knowledge.render_finding_note(befund, "", "2026-09-03")
    assert erst is not None
    assert "tags: [veritas, audit]" in erst

    zweit, _ = sync_knowledge.render_finding_note(befund, erst, "2026-09-03")
    assert zweit == erst


def test_zitierter_endmarker_oberhalb_versteckt_die_marker_nicht() -> None:
    """Nutzerterritorium gilt in BEIDE Richtungen, nicht nur hinter dem Block.

    Wurde der erste Endmarker der ganzen Notiz mit dem ersten Startmarker
    verglichen, galt eine Notiz mit einem woertlich zitierten Endmarker
    OBERHALB des Blocks als "Notiz ohne VERITAS-Marker" -- und zwar dauerhaft,
    mit einer Meldung, die dem Nutzer den Zusammenhang gerade nicht verraet,
    weil die Marker ja sichtbar dastehen.
    """
    notiz = _notiz_mit_eigenem_inhalt().replace(
        "## Meine Analyse\n",
        "## Meine Analyse\n\nSo sieht die Endmarke aus:\n\n"
        + sync_knowledge.GENERATED_END
        + "\n",
    )

    inhalt, konflikt = sync_knowledge.render_finding_note(
        _befund_fuer_notiz(), notiz, "2026-09-03"
    )

    assert konflikt is None or isinstance(konflikt, str)
    assert inhalt is not None
    assert "So sieht die Endmarke aus:" in inhalt
    assert "ALTER GENERIERTER INHALT" not in inhalt
    assert "Mein Text." in inhalt
