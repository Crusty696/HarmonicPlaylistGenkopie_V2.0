from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from hpg_core.caching import CACHE_VERSION, track_to_dict
from hpg_core.mix_candidates import MixCandidate
from hpg_core.models import Track
from hpg_core.pair_candidates import PairCandidate
from tools import audit_candidate_set as audit
from tools.rate_transitions import (
    BEWERTUNG_KANDIDATEN_SPALTEN,
    MERKMALE_KANDIDATEN_SPALTEN,
)


def _write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def candidate_set(tmp_path):
    set_dir = tmp_path / "set"
    clips = set_dir / "clips"
    clips.mkdir(parents=True)
    track_a = tmp_path / "a.wav"
    track_b = tmp_path / "b.wav"
    signal = np.zeros((800, 2), dtype=np.float32)
    signal[::100] = 0.5
    sf.write(track_a, signal, 8000, subtype="PCM_16")
    sf.write(track_b, signal, 8000, subtype="PCM_16")

    merkmale, bewertung, order = [], [], {}
    for number in range(1, 31):
        pair_id = f"{number:03d}"
        cid = f"{pair_id}_k1"
        sf.write(clips / f"{cid}.wav", signal, 8000, subtype="PCM_16")
        row = {field: "" for field in MERKMALE_KANDIDATEN_SPALTEN}
        row.update({
            "pair_id": pair_id, "clip_id": cid, "clip": f"clips/{cid}.wav",
            "score": "0.8", "blend_bars": "8", "t_out": "10.0",
            "t_in": "12.0", "confidence_out": "1", "confidence_in": "1",
            "crossfade_sek": "16.0", "bpm_a": "120", "bpm_b": "122",
            "bpm_toleranz": "2.0", "energy_direction": "auto",
            "rendered_transition_type": "pro_eq_swap",
            "transition_type_mode": "kontrolliert",
            "track_a": str(track_a), "track_b": str(track_b),
            "schema_out": "pssi_phrase", "schema_in": "analyzer",
            "schemata_out": "pssi_phrase", "schemata_in": "analyzer",
            "provenance_out": "rekordbox_pssi", "provenance_in": "hpg_analyzer",
            "bpm_relation": "direct", "genre_a": "Psytrance", "genre_b": "Psytrance",
            "key_a": "8A", "key_b": "8A",
        })
        for factor in audit.FAKTOREN:
            row[factor] = "0.8" if factor in {"harmonic", "groove"} else "0.5"
        merkmale.append(row)
        bewertung.append({field: "" for field in BEWERTUNG_KANDIDATEN_SPALTEN} | {
            "pair_id": pair_id, "clip_id": cid,
        })
        order[pair_id] = {"seed": number, "clips": [cid]}
    _write_csv(set_dir / "merkmale.csv", MERKMALE_KANDIDATEN_SPALTEN, merkmale)
    _write_csv(set_dir / "bewertung.csv", BEWERTUNG_KANDIDATEN_SPALTEN, bewertung)
    (set_dir / "reihenfolge.json").write_text(json.dumps(order), encoding="utf-8")
    (set_dir / "LIESMICH-kandidaten.txt").write_text("Testvertrag\n", encoding="utf-8")

    cache = tmp_path / "cache.db"
    conn = sqlite3.connect(cache)
    conn.execute("CREATE TABLE cache (key TEXT, filepath TEXT, version INTEGER, data TEXT)")
    conn.execute("INSERT INTO cache VALUES ('version', 'system', ?, 'metadata')", (CACHE_VERSION,))
    for key, path, bpm in (("a", track_a, 120.0), ("b", track_b, 122.0)):
        track = Track(
            str(path), path.name, duration=100.0, bpm=bpm, outro_covered=True,
            detected_genre="Psytrance", camelotCode="8A",
            sections=[{
                "label": "main", "start_time": 0.0, "end_time": 100.0,
                "start_bar": 0, "end_bar": 50, "avg_energy": 50.0,
                "analysis_status": "analyzed",
            }],
            analysis_coverage=[{"start": 0.0, "end": 100.0}],
        )
        conn.execute(
            "INSERT INTO cache VALUES (?, ?, ?, ?)",
            (key, str(path), CACHE_VERSION, json.dumps(track_to_dict(track))),
        )
    conn.commit()
    conn.close()
    profile = {
        **{key: 0.1 for key in audit.KANDIDATEN_GEWICHT_SCHLUESSEL},
        "groove_sim_floor": 0.5,
        "bass_delta_max": 6.0,
        "brightness_delta_max": 1200.0,
    }
    size, digest = audit._fingerprint_file(cache)
    manifest = {
        "format_version": 1,
        "app_version": audit.APP_VERSION,
        "algorithm_build": audit._algorithm_build_fingerprint(),
        "hearing_test_contract": {
            "harmonic_gate_scope": audit.HARMONIC_GATE_SCOPE,
            "minimum_harmonic_score": audit.MIN_HARMONIC_SCORE,
        },
        "cache": {"version": CACHE_VERSION, "size": size, "sha256": digest},
        "render_args": {
            "anzahl": 30, "max_versionen_pro_paar": 1, "nur_genre": "Psytrance",
            "transition_type_mode": "kontrolliert", "seed": 0,
        },
        "scoring_snapshot": {
            "rank_args": {
                "bpm_tolerance": 2.0, "energy_direction": "auto",
                "harmonic_strictness": 7, "allow_experimental": True,
            },
            "candidate_tolerances_by_genre": {
                genre: dict(profile) for genre in audit.CANONICAL_GENRES
            },
            "candidate_tolerances_fallback": dict(profile),
            "candidate_schema_ranks_by_genre": {
                genre: [] for genre in audit.CANONICAL_GENRES
            },
            "candidate_schema_rank_fallback": [],
            "candidate_choices": {},
        },
        "pairs": [
            {
                "pair_id": f"{number:03d}", "track_a": str(track_a), "track_b": str(track_b),
                "clips": [{
                    "clip_id": f"{number:03d}_k1", "rank": 1,
                    "t_out": 10.0, "t_in": 12.0, "blend_bars": 8,
                    "overlap_sec": 16.0, "rendered_transition_type": "pro_eq_swap",
                }],
            }
            for number in range(1, 31)
        ],
    }
    (set_dir / "kandidaten_manifest.json").write_text(
        json.dumps(manifest, allow_nan=False), encoding="utf-8"
    )
    return set_dir, cache, merkmale, bewertung


def _candidate():
    out_a = MixCandidate(
        t=10.0, schema=["pssi_phrase"], provenance="rekordbox_pssi",
        confidence=1.0, energy_lokal=50,
    )
    in_b = MixCandidate(
        t=12.0, schema=["analyzer"], provenance="hpg_analyzer",
        confidence=1.0, energy_lokal=50,
    )
    return PairCandidate(
        out_a, in_b, blend_bars=8, overlap_sec=16.0, score=0.8,
        teilwerte={
            factor: 0.8 if factor in {"harmonic", "groove"} else 0.5
            for factor in audit.FAKTOREN
        },
        flags={}, bpm_relation="direct",
    )


def _copy_render(set_dir, seen=None):
    def render(a, b, pc, pair_id, n, out_dir, **kwargs):
        if seen is not None:
            seen.append((a.bpm, b.bpm, pc, kwargs))
        source = set_dir / "clips" / f"{pair_id}_k{n}.wav"
        data, sr = sf.read(source, dtype="int16", always_2d=True)
        target = out_dir / source.name
        sf.write(target, data, sr, subtype="PCM_16")
        return target, [0.0, 0.0, 0.0]
    return render


def _manifest(set_dir: Path) -> dict:
    return json.loads((set_dir / "kandidaten_manifest.json").read_text(encoding="utf-8"))


def _write_manifest(set_dir: Path, manifest: dict) -> None:
    (set_dir / "kandidaten_manifest.json").write_text(
        json.dumps(manifest, allow_nan=False), encoding="utf-8"
    )


def test_vollstaendiger_stretch_fall_ist_read_only(candidate_set, monkeypatch):
    set_dir, cache, _, _ = candidate_set
    rank_calls = []

    def rank(_a, _b, **kwargs):
        rank_calls.append(kwargs)
        return [_candidate()]

    monkeypatch.setattr(audit, "rank_pair_candidates", rank)
    before_set = audit._fingerprint_tree(set_dir)
    before_cache = audit._fingerprint_file(cache)
    seen = []
    result = audit.audit_set(set_dir, cache, render=_copy_render(set_dir, seen))
    assert result["ok"] and result["clips"] == 30
    assert result["format_version"] == 1 and result["status"] == "passed"
    assert result["set"] == {
        "path": str(set_dir),
        "manifest_sha256": hashlib.sha256(
            (set_dir / "kandidaten_manifest.json").read_bytes()
        ).hexdigest(),
        **audit._fingerprint_kandidatensatz(set_dir),
    }
    assert result["cache"] == _manifest(set_dir)["cache"]
    assert result["algorithm_build"] == _manifest(set_dir)["algorithm_build"]
    assert len(rank_calls) == 30
    assert all(set(kwargs) == {
        "bpm_tolerance", "energy_direction", "harmonic_strictness",
        "allow_experimental", "tolerances", "schema_rang", "wahl",
    } for kwargs in rank_calls)
    assert all((a, b) == (120.0, 122.0) for a, b, _, _ in seen)
    assert all(item[3]["rendered_transition_type"] == "pro_eq_swap" for item in seen)
    assert audit._fingerprint_tree(set_dir) == before_set
    assert audit._fingerprint_file(cache) == before_cache
    assert not Path(f"{cache}-wal").exists()
    assert not Path(f"{cache}-shm").exists()


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra_root", "bool_int", "nan", "bad_mode", "bad_type", "bad_profile"],
)
def test_manifest_strikt_fail_closed(candidate_set, mutation):
    set_dir, _, _, _ = candidate_set
    path = set_dir / "kandidaten_manifest.json"
    manifest = _manifest(set_dir)
    if mutation == "missing":
        path.unlink()
        with pytest.raises(audit.AuditError, match="Satzwurzel muss exakt"):
            audit._parse_set(set_dir)
        return
    if mutation == "extra_root":
        manifest["extra"] = 1
    elif mutation == "bool_int":
        manifest["render_args"]["seed"] = True
    elif mutation == "nan":
        path.write_text(path.read_text(encoding="utf-8").replace('"seed": 0', '"seed": NaN'), encoding="utf-8")
        with pytest.raises(audit.AuditError, match="nicht-endliche"):
            audit._parse_set(set_dir)
        return
    elif mutation == "bad_mode":
        manifest["render_args"]["transition_type_mode"] = "frei"
    elif mutation == "bad_type":
        manifest["pairs"][0]["clips"][0]["rendered_transition_type"] = "unbekannt"
    else:
        manifest["scoring_snapshot"]["candidate_tolerances_fallback"][
            audit.KANDIDATEN_GEWICHT_SCHLUESSEL[0]
        ] = 0.2
    _write_manifest(set_dir, manifest)
    with pytest.raises(audit.AuditError):
        audit._parse_set(set_dir)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("harmonic_strictness", 1),
        ("harmonic_strictness", 10),
        ("allow_experimental", False),
    ],
)
def test_manifest_akzeptiert_validierte_variable_harmonieoptionen(
    candidate_set, field, value
):
    set_dir, _, _, _ = candidate_set
    manifest = _manifest(set_dir)
    manifest["scoring_snapshot"]["rank_args"][field] = value
    _write_manifest(set_dir, manifest)
    assert audit._parse_set(set_dir)[3]["scoring_snapshot"]["rank_args"][field] == value


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("harmonic_strictness", 0),
        ("harmonic_strictness", 11),
        ("harmonic_strictness", True),
        ("allow_experimental", 1),
        ("allow_experimental", "false"),
    ],
)
def test_manifest_lehnt_ungueltige_harmonieoptionen_ab(candidate_set, field, value):
    set_dir, _, _, _ = candidate_set
    manifest = _manifest(set_dir)
    manifest["scoring_snapshot"]["rank_args"][field] = value
    _write_manifest(set_dir, manifest)
    with pytest.raises(audit.AuditError):
        audit._parse_set(set_dir)


def test_audit_leitet_paar_ids_dynamisch_aus_render_anzahl_ab(candidate_set):
    set_dir, _, merkmale, bewertung = candidate_set
    keep_ids = {"001_k1", "002_k1"}
    merkmale[:] = [row for row in merkmale if row["clip_id"] in keep_ids]
    bewertung[:] = [row for row in bewertung if row["clip_id"] in keep_ids]
    _write_csv(set_dir / "merkmale.csv", MERKMALE_KANDIDATEN_SPALTEN, merkmale)
    _write_csv(set_dir / "bewertung.csv", BEWERTUNG_KANDIDATEN_SPALTEN, bewertung)
    order = json.loads((set_dir / "reihenfolge.json").read_text(encoding="utf-8"))
    (set_dir / "reihenfolge.json").write_text(
        json.dumps({key: order[key] for key in ("001", "002")}), encoding="utf-8"
    )
    for path in (set_dir / "clips").glob("*.wav"):
        if path.stem not in keep_ids:
            path.unlink()
    manifest = _manifest(set_dir)
    manifest["render_args"]["anzahl"] = 2
    manifest["pairs"] = manifest["pairs"][:2]
    _write_manifest(set_dir, manifest)

    parsed = audit._parse_set(set_dir)
    assert [pair["pair_id"] for pair in parsed[3]["pairs"]] == ["001", "002"]

    merkmale[0], merkmale[1] = merkmale[1], merkmale[0]
    _write_csv(set_dir / "merkmale.csv", MERKMALE_KANDIDATEN_SPALTEN, merkmale)
    with pytest.raises(audit.AuditError, match=r"001\.\.002/k1\.\.kN"):
        audit._parse_set(set_dir)


@pytest.mark.parametrize("extra_kind", ["file", "directory"])
def test_satzwurzel_lehnt_jeden_fremden_eintrag_ab(candidate_set, extra_kind):
    set_dir, _, _, _ = candidate_set
    extra = set_dir / "fremd"
    if extra_kind == "file":
        extra.write_text("nicht erlaubt", encoding="utf-8")
    else:
        extra.mkdir()
    with pytest.raises(audit.AuditError, match="Satzwurzel muss exakt"):
        audit._parse_set(set_dir)


def test_build_provenienz_wird_vor_kandidaten_neuberechnung_geprueft(
    candidate_set, monkeypatch
):
    set_dir, cache, _, _ = candidate_set
    manifest = _manifest(set_dir)
    manifest["algorithm_build"]["sha256"] = "0" * 64
    _write_manifest(set_dir, manifest)
    monkeypatch.setattr(
        audit,
        "rank_pair_candidates",
        lambda *_args, **_kwargs: pytest.fail("Ranking darf nicht starten"),
    )

    with pytest.raises(audit.AuditError, match="Build-Digest"):
        audit.audit_set(set_dir, cache, render=_copy_render(set_dir))


@pytest.mark.parametrize("target", ["app_version", "scope", "threshold"])
def test_manifest_verlangt_exakte_app_und_hoertest_gate_provenienz(candidate_set, target):
    set_dir, _, _, _ = candidate_set
    manifest = _manifest(set_dir)
    if target == "app_version":
        manifest["app_version"] = "0.0.0"
    elif target == "scope":
        manifest["hearing_test_contract"]["harmonic_gate_scope"] = "production"
    else:
        manifest["hearing_test_contract"]["minimum_harmonic_score"] -= 1
    _write_manifest(set_dir, manifest)
    with pytest.raises(audit.AuditError):
        audit._parse_set(set_dir)


@pytest.mark.parametrize("field", ["version", "size", "sha256"])
def test_manifest_cache_fingerprint_muss_exakt_stimmen(candidate_set, field):
    set_dir, cache, _, _ = candidate_set
    manifest = _manifest(set_dir)
    manifest["cache"][field] = (
        CACHE_VERSION - 1 if field == "version" else
        manifest["cache"][field] + 1 if field == "size" else "0" * 64
    )
    _write_manifest(set_dir, manifest)
    with pytest.raises(audit.AuditError, match="cache|Cache"):
        audit._parse_set(set_dir, cache)


def test_manifest_seed_und_shuffle_werden_reproduziert(candidate_set):
    set_dir, _, _, _ = candidate_set
    order_path = set_dir / "reihenfolge.json"
    order = json.loads(order_path.read_text(encoding="utf-8"))
    order["001"]["seed"] += 1
    order_path.write_text(json.dumps(order), encoding="utf-8")
    with pytest.raises(audit.AuditError, match="Seed oder Shuffle"):
        audit._parse_set(set_dir)


def test_manifest_csv_transition_type_muss_1_zu_1_sein(candidate_set):
    set_dir, _, merkmale, _ = candidate_set
    merkmale[0]["rendered_transition_type"] = "filter_sweep"
    _write_csv(set_dir / "merkmale.csv", MERKMALE_KANDIDATEN_SPALTEN, merkmale)
    with pytest.raises(audit.AuditError, match="Transition-Type"):
        audit._parse_set(set_dir)


@pytest.mark.parametrize("datei", ["merkmale.csv", "bewertung.csv"])
def test_csv_reihenfolge_muss_exakt_kanonisch_sein(candidate_set, datei):
    set_dir, _, merkmale, bewertung = candidate_set
    rows = merkmale if datei == "merkmale.csv" else bewertung
    rows[0], rows[1] = rows[1], rows[0]
    fields = MERKMALE_KANDIDATEN_SPALTEN if datei == "merkmale.csv" else BEWERTUNG_KANDIDATEN_SPALTEN
    _write_csv(set_dir / datei, fields, rows)
    with pytest.raises(audit.AuditError, match="Reihenfolge|geordnet"):
        audit._parse_set(set_dir)


def test_produktion_rerendert_exakt_gespeicherten_erlaubten_typ(candidate_set, monkeypatch):
    set_dir, cache, merkmale, _ = candidate_set
    manifest = _manifest(set_dir)
    manifest["render_args"]["transition_type_mode"] = "produktion"
    for pair in manifest["pairs"]:
        pair["clips"][0]["rendered_transition_type"] = "filter_ride"
    for row in merkmale:
        row["transition_type_mode"] = "produktion"
        row["rendered_transition_type"] = "filter_ride"
    _write_manifest(set_dir, manifest)
    _write_csv(set_dir / "merkmale.csv", MERKMALE_KANDIDATEN_SPALTEN, merkmale)
    monkeypatch.setattr(audit, "rank_pair_candidates", lambda _a, _b, **_kw: [_candidate()])
    monkeypatch.setattr(audit, "_transition_type_fuer", lambda *a, **k: "filter_ride")
    seen = []
    audit.audit_set(set_dir, cache, render=_copy_render(set_dir, seen))
    assert seen[0][3]["rendered_transition_type"] == "filter_ride"


def test_produktion_verwirft_typ_der_nicht_app_entscheidung_entspricht(
    candidate_set, monkeypatch
):
    set_dir, cache, merkmale, _ = candidate_set
    manifest = _manifest(set_dir)
    manifest["render_args"]["transition_type_mode"] = "produktion"
    manifest["pairs"][0]["clips"][0]["rendered_transition_type"] = "filter_ride"
    for row in merkmale:
        row["transition_type_mode"] = "produktion"
    merkmale[0]["rendered_transition_type"] = "filter_ride"
    _write_manifest(set_dir, manifest)
    _write_csv(set_dir / "merkmale.csv", MERKMALE_KANDIDATEN_SPALTEN, merkmale)
    monkeypatch.setattr(audit, "rank_pair_candidates", lambda _a, _b, **_kw: [_candidate()])
    monkeypatch.setattr(audit, "_transition_type_fuer", lambda *a, **k: "pro_eq_swap")

    with pytest.raises(audit.AuditError, match="App-Entscheidung"):
        audit.audit_set(set_dir, cache, render=_copy_render(set_dir))


def test_nur_genre_muss_fuer_beide_cache_tracks_gelten(candidate_set, monkeypatch):
    set_dir, cache, _, _ = candidate_set
    monkeypatch.setattr(
        audit,
        "loese_genre_auf",
        lambda track: "Psytrance" if track.fileName == "a.wav" else "Techno",
    )

    with pytest.raises(audit.AuditError, match="nur_genre"):
        audit.audit_set(set_dir, cache, render=_copy_render(set_dir))


@pytest.mark.parametrize(
    ("gate", "message"),
    [("harmonic", "Harmonie"), ("overall", "Gesamtscore"), ("groove", "Groove")],
)
def test_audit_reproduziert_harte_producer_gates(candidate_set, monkeypatch, gate, message):
    set_dir, cache, _, _ = candidate_set
    candidate = _candidate()
    if gate == "harmonic":
        candidate.teilwerte["harmonic"] = 0.59
    elif gate == "overall":
        candidate.score = 0.69
    else:
        candidate.teilwerte["groove"] = 0.49
    monkeypatch.setattr(audit, "rank_pair_candidates", lambda _a, _b, **_kw: [candidate])

    with pytest.raises(audit.AuditError, match=message):
        audit.audit_set(set_dir, cache, render=_copy_render(set_dir))


def test_audit_cache_loader_verlangt_kanonisches_tabellenschema(candidate_set):
    _, cache, _, _ = candidate_set
    conn = sqlite3.connect(cache)
    conn.execute("ALTER TABLE cache ADD COLUMN extra TEXT")
    conn.commit()
    conn.close()

    with pytest.raises(audit.AuditError, match="Schema|Spalten"):
        audit._load_tracks_immutable(cache)


def test_audit_cache_loader_vergleicht_db_und_json_pfad(candidate_set):
    _, cache, _, _ = candidate_set
    conn = sqlite3.connect(cache)
    conn.execute("UPDATE cache SET filepath = ? WHERE key = 'a'", ("anderer-pfad.wav",))
    conn.commit()
    conn.close()

    with pytest.raises(audit.AuditError, match="filepath"):
        audit._load_tracks_immutable(cache)


@pytest.mark.parametrize("target", ["missing", "extra", "duplicate"])
def test_clip_mengenfehler(candidate_set, target):
    set_dir, _, merkmale, _ = candidate_set
    if target == "missing":
        (set_dir / "clips" / "001_k1.wav").unlink()
    elif target == "extra":
        sf.write(set_dir / "clips" / "extra.wav", np.zeros((10, 2)), 8000)
    else:
        merkmale.append(dict(merkmale[0]))
        _write_csv(set_dir / "merkmale.csv", MERKMALE_KANDIDATEN_SPALTEN, merkmale)
    with pytest.raises((audit.AuditError, FileNotFoundError)):
        audit._parse_set(set_dir)


def test_nonfinite_teilwert_wird_abgelehnt(candidate_set):
    set_dir, _, merkmale, _ = candidate_set
    merkmale[0][audit.FAKTOREN[0]] = "nan"
    _write_csv(set_dir / "merkmale.csv", MERKMALE_KANDIDATEN_SPALTEN, merkmale)
    with pytest.raises(audit.AuditError, match="nicht endlich"):
        audit._parse_set(set_dir)


def test_pcm_mismatch_wird_abgelehnt(candidate_set, monkeypatch):
    set_dir, cache, _, _ = candidate_set
    monkeypatch.setattr(audit, "rank_pair_candidates", lambda _a, _b, **_kw: [_candidate()])

    def changed(_a, _b, _pc, pair_id, n, out_dir, **_kwargs):
        target = out_dir / f"{pair_id}_k{n}.wav"
        sf.write(target, np.ones((800, 2), dtype=np.float32) * 0.25, 8000, subtype="PCM_16")
        return target, [0.0, 0.0, 0.0]

    with pytest.raises(audit.AuditError, match="PCM/Samplerate/Form"):
        audit.audit_set(set_dir, cache, render=changed)


def test_wal_wird_kontrolliert_abgelehnt(candidate_set):
    _, cache, _, _ = candidate_set
    Path(f"{cache}-wal").write_bytes(b"pending")
    with pytest.raises(audit.AuditError, match="WAL"):
        audit._load_tracks_immutable(cache)


def test_report_muss_ausserhalb_des_sets_liegen(candidate_set):
    set_dir, cache, _, _ = candidate_set
    with pytest.raises(audit.AuditError, match="separat"):
        audit.validate_paths(set_dir, cache, set_dir / "report.json")


def test_cli_schreibt_fehlerreport_atomar_und_liefert_nonzero(candidate_set, tmp_path):
    set_dir, cache, _, _ = candidate_set
    (set_dir / "clips" / "001_k1.wav").unlink()
    report = tmp_path / "report.json"
    assert audit.main(["--set-dir", str(set_dir), "--cache", str(cache), "--report", str(report)]) == 1
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert not list(tmp_path.glob(".report.json.*.tmp"))


def test_cli_ueberschreibt_vorhandenen_report_nie(candidate_set, tmp_path):
    set_dir, cache, _, _ = candidate_set
    report = tmp_path / "report.json"
    vorher = b'{"fremd":true}\r\n'
    report.write_bytes(vorher)
    assert audit.main([
        "--set-dir", str(set_dir), "--cache", str(cache), "--report", str(report),
    ]) == 1
    assert report.read_bytes() == vorher


def test_atomare_report_publikation_ueberschreibt_auch_im_race_nicht(tmp_path):
    report = tmp_path / "report.json"
    vorher = b'{"race":true}\n'
    report.write_bytes(vorher)
    with pytest.raises(FileExistsError):
        audit._atomic_report(report, {"ok": True})
    assert report.read_bytes() == vorher
    assert not list(tmp_path.glob(".report.json.*.tmp"))


def test_clip_pfad_darf_nicht_ausbrechen(candidate_set):
    set_dir, _, merkmale, _ = candidate_set
    merkmale[0]["clip"] = "../a.wav"
    _write_csv(set_dir / "merkmale.csv", MERKMALE_KANDIDATEN_SPALTEN, merkmale)
    with pytest.raises(audit.AuditError, match="Clip-Pfad"):
        audit._parse_set(set_dir)


@pytest.mark.parametrize("bad_id", ["001_k01", "001_k+1", "001_k1 "])
def test_clip_id_muss_exakt_kanonisch_sein(candidate_set, bad_id):
    set_dir, _, merkmale, _ = candidate_set
    merkmale[0]["clip_id"] = bad_id
    _write_csv(set_dir / "merkmale.csv", MERKMALE_KANDIDATEN_SPALTEN, merkmale)
    with pytest.raises(audit.AuditError, match="ID"):
        audit._parse_set(set_dir)


@pytest.mark.parametrize(
    ("field", "value"),
    [("harmonic", "1.01"), ("score", "-0.1"), ("confidence_out", "2"),
     ("blend_bars", "1.5"), ("blend_bars", "0"), ("bpm_a", "0"),
     ("crossfade_sek", "-1"), ("t_in", "-0.1")],
)
def test_numerische_domaenen(candidate_set, field, value):
    set_dir, _, merkmale, _ = candidate_set
    merkmale[0][field] = value
    _write_csv(set_dir / "merkmale.csv", MERKMALE_KANDIDATEN_SPALTEN, merkmale)
    with pytest.raises(audit.AuditError):
        audit._parse_set(set_dir)


@pytest.mark.parametrize(("field", "changed"), [
    *((factor, "0.6") for factor in audit.FAKTOREN),
    ("score", "0.6"), ("confidence_out", "0.6"), ("confidence_in", "0.6"),
    ("bpm_a", "121.0"), ("bpm_b", "121.0"), ("t_out", "10.0005"),
    ("t_in", "12.0005"), ("crossfade_sek", "16.005"), ("blend_bars", "9"),
    ("bpm_relation", "manipuliert"), ("schema_out", "manipuliert"),
    ("schema_in", "manipuliert"), ("schemata_out", "manipuliert"),
    ("schemata_in", "manipuliert"), ("provenance_out", "manipuliert"),
    ("provenance_in", "manipuliert"), ("genre_a", "manipuliert"),
    ("genre_b", "manipuliert"), ("key_a", "manipuliert"), ("key_b", "manipuliert"),
    ("bpm_toleranz", "1.5"), ("energy_direction", "up"),
])
def test_csv_manipulation_gegen_cache_kandidat(candidate_set, monkeypatch, field, changed):
    set_dir, cache, merkmale, _ = candidate_set
    merkmale[0][field] = changed
    _write_csv(set_dir / "merkmale.csv", MERKMALE_KANDIDATEN_SPALTEN, merkmale)
    monkeypatch.setattr(audit, "rank_pair_candidates", lambda _a, _b, **_kw: [_candidate()])
    with pytest.raises(audit.AuditError):
        audit.audit_set(set_dir, cache, render=_copy_render(set_dir))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bpm_toleranz", ""),
        ("bpm_toleranz", "nan"),
        ("bpm_toleranz", "0"),
        ("bpm_toleranz", str(audit.PAAR_BPM_MAX + 0.1)),
        ("energy_direction", ""),
        ("energy_direction", "build up"),
    ],
)
def test_scoring_vertrag_fail_closed(candidate_set, field, value):
    set_dir, _, merkmale, _ = candidate_set
    merkmale[0][field] = value
    _write_csv(set_dir / "merkmale.csv", MERKMALE_KANDIDATEN_SPALTEN, merkmale)
    with pytest.raises(audit.AuditError):
        audit._parse_set(set_dir)


@pytest.mark.parametrize("field,value", [("bpm_toleranz", "1.5"), ("energy_direction", "up")])
def test_scoring_vertrag_muss_satzweit_identisch_sein(candidate_set, field, value):
    set_dir, _, merkmale, _ = candidate_set
    merkmale[-1][field] = value
    _write_csv(set_dir / "merkmale.csv", MERKMALE_KANDIDATEN_SPALTEN, merkmale)
    with pytest.raises(audit.AuditError, match="nicht einheitlich"):
        audit._parse_set(set_dir)


@pytest.mark.parametrize(
    ("csv_direction", "expected_direction"),
    [("auto", None), ("up", "up"), ("down", "down"), ("maintain", "maintain")],
)
def test_replay_nutzt_exakten_scoring_vertrag(
    candidate_set, monkeypatch, csv_direction, expected_direction
):
    set_dir, cache, merkmale, _ = candidate_set
    row = merkmale[0]
    manifest = json.loads((set_dir / "kandidaten_manifest.json").read_text(encoding="utf-8"))
    manifest["scoring_snapshot"]["rank_args"]["energy_direction"] = csv_direction
    gesehen = {}

    def rank(_a, _b, **kwargs):
        gesehen.update(kwargs)
        return [_candidate()]

    monkeypatch.setattr(audit, "rank_pair_candidates", rank)
    a = Track(row["track_a"], "a.wav", bpm=120.0, detected_genre="Psytrance", camelotCode="8A")
    b = Track(row["track_b"], "b.wav", bpm=122.0, detected_genre="Psytrance", camelotCode="8A")
    audit._candidate_for(row, a, b, manifest)
    assert gesehen["bpm_tolerance"] == 2.0
    assert gesehen["energy_direction"] == expected_direction
    assert set(gesehen) == {
        "bpm_tolerance", "energy_direction", "harmonic_strictness",
        "allow_experimental", "tolerances", "schema_rang", "wahl",
    }


def test_alter_satz_ohne_scoring_spalten_faellt_im_strengen_audit(candidate_set):
    set_dir, _, merkmale, _ = candidate_set
    alte_felder = tuple(
        feld for feld in MERKMALE_KANDIDATEN_SPALTEN
        if feld not in {"bpm_toleranz", "energy_direction"}
    )
    alte_zeilen = [
        {feld: zeile.get(feld, "") for feld in alte_felder}
        for zeile in merkmale
    ]
    _write_csv(set_dir / "merkmale.csv", alte_felder, alte_zeilen)
    with pytest.raises(audit.AuditError, match="Falsche Spalten"):
        audit._parse_set(set_dir)


@pytest.mark.parametrize("lags", [[], [0.0, None, 0.0], [0.0, float("nan"), 0.0], [0.0, 0.007, 0.0]])
def test_kick_lags_hart_validiert(lags):
    with pytest.raises(audit.AuditError, match="Kick"):
        audit._validate_lags("001_k1", lags)


@pytest.mark.parametrize("marker", ["missing", "wrong", "wrong_data", "duplicate"])
def test_cache_marker_muss_exakt_aktuell_sein(candidate_set, marker):
    _, cache, _, _ = candidate_set
    conn = sqlite3.connect(cache)
    if marker == "missing":
        conn.execute("DELETE FROM cache WHERE key='version'")
    elif marker == "wrong":
        conn.execute("UPDATE cache SET version=? WHERE key='version'", (CACHE_VERSION - 1,))
    elif marker == "wrong_data":
        conn.execute("UPDATE cache SET data='wrong' WHERE key='version'")
    else:
        conn.execute("INSERT INTO cache VALUES ('version', 'system', ?, 'metadata')", (CACHE_VERSION,))
    conn.commit()
    conn.close()
    with pytest.raises(audit.AuditError, match="Cache-Marker"):
        audit._load_tracks_immutable(cache)


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal", ".lock", "-lock"])
def test_report_darf_keinen_cache_begleitpfad_treffen(candidate_set, suffix):
    set_dir, cache, _, _ = candidate_set
    with pytest.raises(audit.AuditError, match="separat"):
        audit.validate_paths(set_dir, cache, Path(f"{cache}{suffix}"))


def test_report_darf_exakten_caching_lock_file_nicht_treffen(candidate_set):
    set_dir, cache, _, _ = candidate_set
    lock_file = Path(str(cache.with_suffix("")) + ".lock")
    with pytest.raises(audit.AuditError, match="separat"):
        audit.validate_paths(set_dir, cache, lock_file)


def test_wal_entstehung_waehrend_render_verhindert_ok(candidate_set, monkeypatch):
    set_dir, cache, _, _ = candidate_set
    monkeypatch.setattr(audit, "rank_pair_candidates", lambda _a, _b, **_kw: [_candidate()])
    base_render = _copy_render(set_dir)
    created = False

    def render(*args, **kwargs):
        nonlocal created
        result = base_render(*args, **kwargs)
        if not created:
            Path(f"{cache}-wal").write_bytes(b"waehrend-render")
            created = True
        return result

    with pytest.raises(audit.AuditError, match="WAL"):
        audit.audit_set(set_dir, cache, render=render)


def test_cache_begleitdatei_entstehung_verhindert_ok(candidate_set, monkeypatch):
    set_dir, cache, _, _ = candidate_set
    monkeypatch.setattr(audit, "rank_pair_candidates", lambda _a, _b, **_kw: [_candidate()])
    base_render = _copy_render(set_dir)
    created = False

    def render(*args, **kwargs):
        nonlocal created
        result = base_render(*args, **kwargs)
        if not created:
            Path(f"{cache}-shm").write_bytes(b"waehrend-render")
            created = True
        return result

    with pytest.raises(audit.AuditError, match="Cache oder Begleitdatei"):
        audit.audit_set(set_dir, cache, render=render)


def test_echter_cache_lock_entstehung_verhindert_ok(candidate_set, monkeypatch):
    set_dir, cache, _, _ = candidate_set
    monkeypatch.setattr(audit, "rank_pair_candidates", lambda _a, _b, **_kw: [_candidate()])
    base_render = _copy_render(set_dir)
    lock = cache.with_suffix(".lock")
    created = False

    def render(*args, **kwargs):
        nonlocal created
        result = base_render(*args, **kwargs)
        if not created:
            lock.write_bytes(b"waehrend-render")
            created = True
        return result

    with pytest.raises(audit.AuditError, match="Cache oder Begleitdatei"):
        audit.audit_set(set_dir, cache, render=render)


def test_jede_cache_trackzeile_braucht_aktuelle_version(candidate_set):
    _, cache, _, _ = candidate_set
    conn = sqlite3.connect(cache)
    conn.execute("UPDATE cache SET version=? WHERE key='a'", (CACHE_VERSION - 1,))
    conn.commit()
    conn.close()
    with pytest.raises(audit.AuditError, match="Cache-Zeile.*Version"):
        audit._load_tracks_immutable(cache)


def test_erfolgsreportfehler_ist_kontrollierter_exit1(candidate_set, tmp_path, monkeypatch, capsys):
    set_dir, cache, _, _ = candidate_set
    monkeypatch.setattr(audit, "audit_set", lambda *_args, **_kwargs: {"ok": True, "pairs": 30, "clips": 30})
    monkeypatch.setattr(audit, "_atomic_report", lambda *_args: (_ for _ in ()).throw(OSError("voll")))
    result = audit.main(["--set-dir", str(set_dir), "--cache", str(cache), "--report", str(tmp_path / "r.json")])
    assert result == 1
    assert "Report konnte nicht geschrieben" in capsys.readouterr().err


def _kick_track(path: Path, bpm: float, duration: float = 24.0, sr: int = 22050):
    audio = np.zeros((int(duration * sr), 2), dtype=np.float32)
    pulse_len = int(0.18 * sr)
    t = np.arange(pulse_len, dtype=np.float64) / sr
    pulse = (0.8 * np.sin(2 * np.pi * 60.0 * t) * np.exp(-24.0 * t)).astype(np.float32)
    for start_sec in np.arange(0.0, duration, 60.0 / bpm):
        start = int(round(start_sec * sr))
        stop = min(len(audio), start + pulse_len)
        audio[start:stop, 0] += pulse[:stop - start]
        audio[start:stop, 1] += pulse[:stop - start]
    sf.write(path, audio, sr, subtype="PCM_16")


@pytest.mark.parametrize("bpm_b", [120.0, 122.0], ids=["direct", "stretch"])
def test_echter_strict_neurender_mit_drei_kick_lags_und_pcm(tmp_path, bpm_b):
    path_a, path_b = tmp_path / "real-a.wav", tmp_path / "real-b.wav"
    _kick_track(path_a, 120.0)
    _kick_track(path_b, bpm_b)
    a = Track(
        str(path_a), path_a.name, duration=24.0, bpm=120.0,
        first_downbeat=0.0, downbeat_confidence=1.0, outro_covered=True,
        detected_genre="Psytrance", camelotCode="8A", energy=50,
    )
    b = Track(
        str(path_b), path_b.name, duration=24.0, bpm=bpm_b,
        first_downbeat=0.0, downbeat_confidence=1.0, outro_covered=True,
        detected_genre="Psytrance", camelotCode="8A", energy=50,
    )
    pc = PairCandidate(
        MixCandidate(t=8.0, schema=["analyzer"], provenance="hpg_analyzer", confidence=1.0,
                     energy_lokal=50, camelot_lokal="8A"),
        MixCandidate(t=8.0, schema=["analyzer"], provenance="hpg_analyzer", confidence=1.0,
                     energy_lokal=50, camelot_lokal="8A"),
        blend_bars=3, overlap_sec=6.0, score=0.8,
        teilwerte={factor: 0.8 for factor in audit.FAKTOREN}, flags={}, bpm_relation="direct",
    )
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    render_kwargs = {
        "rendered_transition_type": "pro_eq_swap",
        "transition_type_mode": "kontrolliert", "bpm_toleranz": 2.0,
        "energy_direction": None,
    }
    first, first_lags = audit._render_with_diagnostics(
        a, b, pc, "001", 1, first_dir, **render_kwargs
    )
    second, second_lags = audit._render_with_diagnostics(
        a, b, pc, "001", 1, second_dir, **render_kwargs
    )
    assert len(audit._validate_lags("001_k1", first_lags)) == 3
    assert len(audit._validate_lags("001_k1", second_lags)) == 3
    metadata = audit._compare_wav(first, second, "001_k1")
    assert metadata["samplerate"] == 44100
    assert metadata["channels"] == 2
