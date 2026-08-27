"""Vertragstests fuer den strikt read-only Analysecache-Validator."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlparse
from urllib.request import url2pathname

import pytest

from hpg_core.caching import CACHE_VERSION, generate_cache_key, track_to_dict
from hpg_core.models import Track
from tools import validate_analysis_cache as validator


_REAL_CONNECT = sqlite3.connect
_SQLITE_TEST_BASIS: Path | None = None


@pytest.fixture(autouse=True)
def _verbiete_produktcache(monkeypatch, tmp_path):
    """Jeder SQLite-Zugriff dieses Moduls bleibt im eindeutigen Testordner."""
    global _SQLITE_TEST_BASIS
    basis = tmp_path.resolve()
    _SQLITE_TEST_BASIS = basis

    def guarded_connect(database, *args, **kwargs):
        raw = os.fspath(database)
        if raw.startswith("file:"):
            path = Path(url2pathname(urlparse(raw).path)).resolve()
        else:
            path = Path(raw).resolve()
        try:
            path.relative_to(basis)
        except ValueError as exc:
            raise AssertionError(f"SQLite-Zugriff ausserhalb tmp_path: {path}") from exc
        return _REAL_CONNECT(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_connect)
    yield
    _SQLITE_TEST_BASIS = None


def _connect_test_db(database: Path) -> sqlite3.Connection:
    """Oeffnet ausschliesslich eine durch das Autouse-Fixture erlaubte Test-DB."""
    assert _SQLITE_TEST_BASIS is not None
    return sqlite3.connect(database)


def _track_data(audio: Path) -> dict:
    track = Track(
        filePath=str(audio.resolve()),
        fileName=audio.name,
        duration=300.0,
        bpm=128.0,
        analysis_mode="librosa_full_or_tail",
    )
    return track_to_dict(track)


def _create_cache(
    cache: Path,
    audio_files: list[Path],
    *,
    version: int = CACHE_VERSION,
    marker=("system", CACHE_VERSION, "metadata"),
) -> None:
    conn = _connect_test_db(cache)
    try:
        conn.execute(
            "CREATE TABLE cache (key TEXT PRIMARY KEY, filepath TEXT, "
            "version INTEGER, data TEXT)"
        )
        conn.execute(
            "INSERT INTO cache(key, filepath, version, data) VALUES "
            "('version', ?, ?, ?)",
            marker,
        )
        for audio in audio_files:
            data = _track_data(audio)
            key = generate_cache_key(str(audio.resolve()), data["rekordbox_signature"])
            conn.execute(
                "INSERT INTO cache(key, filepath, version, data) VALUES (?, ?, ?, ?)",
                (key, data["filePath"], version, json.dumps(data)),
            )
        conn.commit()
    finally:
        conn.close()


def _args(cache: Path, root: Path, *, files=1, minimum=1, version=CACHE_VERSION):
    return [
        "--cache", str(cache),
        "--expected-version", str(version),
        "--root", str(root),
        "--expected-files", str(files),
        "--min-success", str(minimum),
    ]


def _lege_leere_cachefamilie_an(cache: Path) -> None:
    """Ergaenzt jeden nicht-DB-Familieneintrag als leere Testdatei."""
    for path in validator._cachefamilie(cache):
        if path != cache:
            path.write_bytes(b"")


@pytest.fixture
def valid_cache(tmp_path):
    root = tmp_path / "Musik mit % und Leerzeichen"
    root.mkdir()
    audio = root / "track %.wav"
    audio.write_bytes(b"audio")
    cache = tmp_path / "cache mit %.db"
    _create_cache(cache, [audio])
    return cache, root, audio


def test_gueltiger_cache_wird_immutable_gelesen(valid_cache, monkeypatch, capsys):
    cache, root, _audio = valid_cache
    calls = []
    original = validator.sqlite3.connect

    def record(database, *args, **kwargs):
        calls.append((str(database), kwargs.copy()))
        return original(database, *args, **kwargs)

    monkeypatch.setattr(validator.sqlite3, "connect", record)

    assert validator.main(_args(cache, root)) == 0
    out = capsys.readouterr()
    assert out.err == ""
    assert out.out.splitlines()[-1].startswith(
        f"STATUS=OK DB_VERSION={CACHE_VERSION} VALIDATOR_CONTRACT=CURRENT_CODE "
        "TRACKS_VALID=1 TRACKS_EXPECTED=1 "
        "TRACKS_MISSING=0 DB_SIZE="
    )
    assert len(calls) == 1
    assert "mode=ro&immutable=1" in calls[0][0]
    assert calls[0][1]["uri"] is True


def test_sqlite_ist_query_only_geschaltet(valid_cache, monkeypatch):
    cache, root, _ = valid_cache
    original = validator.sqlite3.connect
    statements = []

    class ObserveConnection:
        def __init__(self, connection):
            self._connection = connection

        def execute(self, statement, *args, **kwargs):
            statements.append(statement)
            return self._connection.execute(statement, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._connection, name)

    monkeypatch.setattr(
        validator.sqlite3,
        "connect",
        lambda *args, **kwargs: ObserveConnection(original(*args, **kwargs)),
    )

    assert validator.main(_args(cache, root)) == 0
    assert "PRAGMA query_only=ON" in statements


def test_validator_ruft_keine_cache_core_mutatoren(valid_cache, monkeypatch):
    cache, root, _ = valid_cache
    import hpg_core.caching as caching

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Validator darf keinen Cache-Core-Mutator aufrufen")

    for name in (
        "init_cache",
        "cache_track",
        "get_cached_track",
        "merge_cached_ai_metadata",
        "_reset_cache_rows",
        "_quarantine_cache_row_on_connection",
        "_quarantine_corrupt_cache",
    ):
        if hasattr(caching, name):
            monkeypatch.setattr(caching, name, forbidden)

    assert validator.main(_args(cache, root)) == 0


@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_vollstaendige_cachefamilie_bleibt_bytegleich(outcome, valid_cache):
    cache, root, _ = valid_cache
    _lege_leere_cachefamilie_an(cache)
    if outcome == "failure":
        conn = _connect_test_db(cache)
        conn.execute("UPDATE cache SET data='wrong' WHERE key='version'")
        conn.commit()
        conn.close()
    fingerprint_before = validator._familienfingerprint(cache)

    assert validator.main(_args(cache, root)) == (0 if outcome == "success" else 1)
    assert validator._familienfingerprint(cache) == fingerprint_before


def test_summary_kennzeichnet_erwartete_nichtaktuelle_db_version(tmp_path, capsys):
    root = tmp_path / "music"
    root.mkdir()
    audio = root / "track.wav"
    audio.write_bytes(b"audio")
    cache = tmp_path / "cache.db"
    erwartete_altversion = CACHE_VERSION - 1
    _create_cache(
        cache,
        [audio],
        version=erwartete_altversion,
        marker=("system", erwartete_altversion, "metadata"),
    )

    assert validator.main(_args(cache, root, version=erwartete_altversion)) == 0
    summary = capsys.readouterr().out.splitlines()[-1]
    assert f"DB_VERSION={erwartete_altversion}" in summary
    assert "VALIDATOR_CONTRACT=CURRENT_CODE" in summary


def test_hilfe_benennt_db_version_und_validator_vertrag(capsys):
    with pytest.raises(SystemExit) as exc:
        validator.main(["--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "DB_VERSION=<expected>" in help_text
    assert "VALIDATOR_CONTRACT=CURRENT_CODE" in help_text


@pytest.mark.parametrize(
    "option,value",
    [
        ("--expected-version", "0"),
        ("--expected-files", "0"),
        ("--min-success", "-1"),
    ],
)
def test_numerische_cli_grenzen_sind_argparse_fehler(valid_cache, option, value):
    cache, root, _ = valid_cache
    args = _args(cache, root)
    args[args.index(option) + 1] = value
    with pytest.raises(SystemExit) as exc:
        validator.main(args)
    assert exc.value.code == 2


def test_min_success_darf_expected_files_nicht_uebersteigen(valid_cache):
    cache, root, _ = valid_cache
    with pytest.raises(SystemExit) as exc:
        validator.main(_args(cache, root, files=1, minimum=2))
    assert exc.value.code == 2


@pytest.mark.parametrize("kind", ["wal", "journal"])
def test_nichtleere_transaktionsdatei_sperrt_vor_sqlite_open(
    valid_cache, kind, monkeypatch
):
    cache, root, _ = valid_cache
    Path(f"{cache}-{kind}").write_bytes(b"pending")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("SQLite darf bei pending transaction nicht oeffnen")

    monkeypatch.setattr(validator.sqlite3, "connect", forbidden)
    assert validator.main(_args(cache, root)) == 1


@pytest.mark.parametrize("kind", ["wal", "journal"])
def test_neue_nichtleere_transaktionsdatei_vor_open_sperrt_ohne_sqlite_connect(
    valid_cache, kind, monkeypatch
):
    cache, root, audio = valid_cache

    def discovery_with_race(_root):
        Path(f"{cache}-{kind}").write_bytes(b"race")
        return [str(audio)], []

    def forbidden(*_args, **_kwargs):
        raise AssertionError("SQLite darf nach WAL/Journal-Race nicht oeffnen")

    monkeypatch.setattr(validator, "entdecke_audio", discovery_with_race)
    monkeypatch.setattr(validator.sqlite3, "connect", forbidden)
    assert validator.main(_args(cache, root)) == 1


def test_leere_wal_wird_fingerprinted_aber_blockiert_nicht(valid_cache):
    cache, root, _ = valid_cache
    Path(f"{cache}-wal").write_bytes(b"")
    assert validator.main(_args(cache, root)) == 0


def test_schema_muss_reihenfolge_typen_und_pk_exakt_erfuellen(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    audio = root / "a.wav"
    audio.write_bytes(b"x")
    cache = tmp_path / "wrong.db"
    conn = _connect_test_db(cache)
    conn.execute("CREATE TABLE cache(filepath TEXT, key TEXT, version INTEGER, data TEXT)")
    conn.commit()
    conn.close()
    assert validator.main(_args(cache, root)) == 1


def test_marker_muss_exakt_sein(valid_cache):
    cache, root, _ = valid_cache
    conn = _connect_test_db(cache)
    conn.execute("UPDATE cache SET data='wrong' WHERE key='version'")
    conn.commit()
    conn.close()
    assert validator.main(_args(cache, root)) == 1


@pytest.mark.parametrize("marker_problem", ["fehlend", "falsche_version"])
def test_versionsmarker_muss_vorhanden_und_kanonisch_sein(
    valid_cache, marker_problem
):
    cache, root, _ = valid_cache
    conn = _connect_test_db(cache)
    if marker_problem == "fehlend":
        conn.execute("DELETE FROM cache WHERE key='version'")
    else:
        conn.execute(
            "UPDATE cache SET version=? WHERE key='version'", (CACHE_VERSION + 1,)
        )
    conn.commit()
    conn.close()

    assert validator.main(_args(cache, root)) == 1


def test_trackzeile_mit_falscher_version_wird_abgewiesen(valid_cache):
    cache, root, _ = valid_cache
    conn = _connect_test_db(cache)
    conn.execute(
        "UPDATE cache SET version=? WHERE key <> 'version'", (CACHE_VERSION + 1,)
    )
    conn.commit()
    conn.close()

    assert validator.main(_args(cache, root)) == 1


def test_json_verwirft_nan(valid_cache):
    cache, root, _ = valid_cache
    conn = _connect_test_db(cache)
    row = conn.execute("SELECT key, data FROM cache WHERE key <> 'version'").fetchone()
    payload = json.loads(row[1])
    payload["bpm"] = float("nan")
    conn.execute("UPDATE cache SET data=? WHERE key=?", (json.dumps(payload), row[0]))
    conn.commit()
    conn.close()
    assert validator.main(_args(cache, root)) == 1


def test_db_filepath_muss_json_exakt_gleichen(valid_cache):
    cache, root, _ = valid_cache
    conn = _connect_test_db(cache)
    conn.execute("UPDATE cache SET filepath=filepath || ' ' WHERE key <> 'version'")
    conn.commit()
    conn.close()
    assert validator.main(_args(cache, root)) == 1


def test_normcase_doppelter_trackpfad_ist_bei_sonst_gueltigen_rows_mutationssensitiv(
    valid_cache, monkeypatch
):
    cache, root, audio = valid_cache
    original_path = str(audio.resolve())
    alternate_path = str(audio.resolve()).upper()
    original_data = _track_data(audio)
    alternate_data = _track_data(audio)
    alternate_data["filePath"] = alternate_path
    conn = _connect_test_db(cache)
    conn.execute("UPDATE cache SET key=? WHERE key <> 'version'", ("key-original",))
    conn.execute(
        "INSERT INTO cache(key, filepath, version, data) VALUES (?, ?, ?, ?)",
        ("key-alternate", alternate_path, CACHE_VERSION, json.dumps(alternate_data)),
    )
    conn.commit()
    conn.close()

    def current_key(path, _signature):
        return "key-alternate" if path == alternate_path else "key-original"

    # Beide Rows bestehen jede Einzelpruefung inklusive aktuellem Cache-Key.
    # Nur ihre normcase-Identitaet muss die kombinierte DB abweisen.
    monkeypatch.setattr(validator, "generate_cache_key", current_key)
    monkeypatch.setattr(
        validator,
        "entdecke_audio",
        lambda _root: ([original_path, alternate_path], []),
    )
    args = _args(cache, root, files=2, minimum=1)
    assert validator.main(args) == 1

    # Mutation-Sensitivitaet: Ohne Case-Normalisierung (und damit ohne die
    # Duplikatsemantik) waeren beide einzeln gueltigen Rows ein OK-Ergebnis.
    # Windows-`realpath` normalisiert die Schreibweise bereits, deshalb wird
    # es im kontrollierten Gegenfakt ebenfalls als Identitaet geschaltet.
    monkeypatch.setattr(validator.os.path, "normcase", lambda path: path)
    monkeypatch.setattr(
        validator.os.path, "realpath", lambda path, *_args, **_kwargs: path
    )
    assert validator.main(args) == 0


def test_cache_key_wird_gegen_aktuellen_stat_geprueft(valid_cache):
    cache, root, audio = valid_cache
    audio.write_bytes(b"changed")
    assert validator.main(_args(cache, root)) == 1


def test_cachepfad_ausserhalb_root_wird_abgewiesen(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    inside = root / "inside.wav"
    inside.write_bytes(b"a")
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"b")
    cache = tmp_path / "cache.db"
    _create_cache(cache, [outside])
    assert validator.main(_args(cache, root)) == 1


def test_missing_tracks_werden_deterministisch_gemeldet(tmp_path, capsys):
    root = tmp_path / "music"
    root.mkdir()
    cached = root / "a.wav"
    missing = root / "b.wav"
    cached.write_bytes(b"a")
    missing.write_bytes(b"b")
    cache = tmp_path / "cache.db"
    _create_cache(cache, [cached])
    assert validator.main(_args(cache, root, files=2, minimum=1)) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[-2] == f"FEHLENDER_TRACK: {missing.resolve()}"
    assert "TRACKS_VALID=1" in lines[-1]
    assert "TRACKS_MISSING=1" in lines[-1]


def test_discovery_fehler_und_falsche_anzahl_sind_fehler(valid_cache, monkeypatch):
    cache, root, _ = valid_cache
    monkeypatch.setattr(validator, "entdecke_audio", lambda _root: ([], ["kaputt"]))
    assert validator.main(_args(cache, root)) == 1


def test_reale_discovery_anzahlabweichung_ohne_discovery_fehler_ist_fehler(valid_cache):
    cache, root, _ = valid_cache
    assert validator.main(_args(cache, root, files=2)) == 1


def test_min_success_unterschreitung_ist_nach_erfolgreicher_discovery_fehler(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    cached = root / "cached.wav"
    uncached = root / "uncached.wav"
    cached.write_bytes(b"cached")
    uncached.write_bytes(b"uncached")
    cache = tmp_path / "cache.db"
    _create_cache(cache, [cached])

    assert validator.main(_args(cache, root, files=2, minimum=2)) == 1


def test_familienaenderung_waehrend_pruefung_faellt_geschlossen(
    valid_cache, monkeypatch
):
    cache, root, audio = valid_cache
    original = validator._cache_pruefen

    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        Path(f"{cache}.lock").write_bytes(b"race")
        return result

    monkeypatch.setattr(validator, "_cache_pruefen", mutate)
    assert validator.main(_args(cache, root)) == 1
    assert audio.exists()


def test_cache_und_track_symlinks_werden_abgewiesen(tmp_path):
    if not hasattr(os, "symlink"):
        pytest.skip("Symlinks nicht verfuegbar")
    root = tmp_path / "music"
    root.mkdir()
    real_audio = root / "real.wav"
    real_audio.write_bytes(b"a")
    link_audio = root / "link.wav"
    try:
        link_audio.symlink_to(real_audio)
    except OSError:
        pytest.skip("Symlinks nicht erlaubt")
    cache = tmp_path / "cache.db"
    _create_cache(cache, [real_audio])
    linked_data = track_to_dict(Track(
        filePath=str(link_audio), fileName=link_audio.name,
        duration=300.0, bpm=128.0, analysis_mode="librosa_full_or_tail",
    ))
    linked_key = generate_cache_key(str(link_audio), linked_data["rekordbox_signature"])
    conn = _connect_test_db(cache)
    conn.execute(
        "UPDATE cache SET key=?, filepath=?, data=? WHERE key <> 'version'",
        (linked_key, str(link_audio), json.dumps(linked_data)),
    )
    conn.commit()
    conn.close()
    assert validator.main(_args(cache, root, files=1)) == 1

    cache_link = tmp_path / "cache-link.db"
    cache_link.symlink_to(cache)
    assert validator.main(_args(cache_link, root, files=1)) == 1
