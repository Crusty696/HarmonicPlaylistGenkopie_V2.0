import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from tools import analyze_library
from hpg_core.models import Track


def _args(root, cache, expected=1, minimum=1, workers=4, log=None, timeout=None):
    result = [
        "--root", str(root), "--cache", str(cache),
        "--expected-files", str(expected), "--min-success", str(minimum),
        "--workers", str(workers),
    ]
    if log is not None:
        result.extend(["--progress-log", str(log)])
    if timeout is not None:
        result.extend(["--task-timeout", str(timeout)])
    return result


def _gueltiger_cache(pfad: Path):
    from hpg_core.caching import CACHE_VERSION

    conn = sqlite3.connect(pfad)
    try:
        conn.execute(
            "CREATE TABLE cache (key TEXT PRIMARY KEY, filepath TEXT, version INTEGER, data TEXT)"
        )
        conn.execute(
            "INSERT INTO cache (key, filepath, version, data) VALUES ('version', 'system', ?, 'metadata')",
            (CACHE_VERSION,),
        )
        conn.commit()
    finally:
        conn.close()


def _track(pfad: Path) -> Track:
    return Track(
        filePath=str(pfad.resolve()),
        fileName=pfad.name,
        duration=1.0,
        bpm=120.0,
        analysis_mode="librosa_full_or_tail",
    )


def _cachezeile(pfad: Path, track: Track, *, key: str | None = None, version=None):
    from hpg_core.caching import (
        CACHE_VERSION,
        generate_cache_key,
        track_to_dict,
        validate_track_dict,
    )

    if not pfad.exists():
        _gueltiger_cache(pfad)
    cache_key = key or generate_cache_key(track.filePath, track.rekordbox_signature)
    data = json.dumps(validate_track_dict(track_to_dict(track)), allow_nan=False)
    conn = sqlite3.connect(pfad)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, filepath, version, data) VALUES (?, ?, ?, ?)",
            (cache_key, track.filePath, CACHE_VERSION if version is None else version, data),
        )
        conn.commit()
    finally:
        conn.close()


def test_entdecke_audio_rekursiv_deterministisch_und_case_insensitive(tmp_path):
    (tmp_path / "z").mkdir()
    (tmp_path / "a").mkdir()
    for relative in ("z/C.WAV", "a/b.AiFf", "a/a.mp3"):
        (tmp_path / relative).write_bytes(b"audio")
    (tmp_path / "a" / "ignoriert.txt").write_text("x", encoding="utf-8")

    dateien, fehler = analyze_library.entdecke_audio(tmp_path.resolve())

    assert fehler == []
    assert dateien == [
        str((tmp_path / "a" / "a.mp3").resolve()),
        str((tmp_path / "a" / "b.AiFf").resolve()),
        str((tmp_path / "z" / "C.WAV").resolve()),
    ]


def test_entdecke_audio_ueberspringt_dateilink(tmp_path):
    echt = tmp_path / "echt.wav"
    echt.write_bytes(b"audio")
    link = tmp_path / "link.wav"
    try:
        link.symlink_to(echt)
    except OSError:
        pytest.skip("Dateisymlinks sind auf diesem Windows-Konto nicht erlaubt")
    dateien, fehler = analyze_library.entdecke_audio(tmp_path.resolve())

    assert fehler == []
    assert dateien == [str(echt.resolve())]


def test_entdecke_audio_ueberspringt_junction_ordner(tmp_path, monkeypatch):
    echt = tmp_path / "echt.wav"
    echt.write_bytes(b"audio")
    junction = tmp_path / "junction"
    junction.mkdir()
    (junction / "innen.wav").write_bytes(b"audio")
    monkeypatch.setattr(
        analyze_library.os.path,
        "isjunction",
        lambda path: Path(path).name == "junction",
        raising=False,
    )

    dateien, fehler = analyze_library.entdecke_audio(tmp_path.resolve())

    assert fehler == []
    assert dateien == [str(echt.resolve())]


def test_entdecke_audio_meldet_walk_fehler(tmp_path, monkeypatch):
    def kaputter_walk(*args, onerror, **kwargs):
        onerror(PermissionError("Zugriff verweigert"))
        return []

    monkeypatch.setattr(analyze_library.os, "walk", kaputter_walk)

    dateien, fehler = analyze_library.entdecke_audio(tmp_path.resolve())

    assert dateien == []
    assert len(fehler) == 1
    assert "Zugriff verweigert" in fehler[0]


def test_count_mismatch_erzeugt_nichts_und_baut_keinen_analyzer(tmp_path):
    root = tmp_path / "musik"
    root.mkdir()
    (root / "eins.wav").write_bytes(b"audio")
    cache = tmp_path / "work" / "cache.db"
    log = tmp_path / "work" / "progress.log"
    gebaut = []

    code = analyze_library.main(
        _args(root, cache, expected=2, log=log),
        analyzer_factory=lambda **kwargs: gebaut.append(kwargs),
    )

    assert code == 2
    assert gebaut == []
    assert not cache.exists()
    assert not cache.with_suffix(".lock").exists()
    assert not log.exists()
    assert not cache.parent.exists()


def test_count_mismatch_importiert_parallel_analyzer_nicht(tmp_path):
    root = tmp_path / "musik"
    root.mkdir()
    (root / "eins.wav").write_bytes(b"audio")
    cache = tmp_path / "work" / "cache.db"
    log = tmp_path / "work" / "progress.log"
    args = _args(root, cache, expected=2, log=log)
    code = (
        "import sys\n"
        "from tools import analyze_library as a\n"
        f"rc=a.main({args!r})\n"
        "assert rc==2\n"
        "assert 'hpg_core.parallel_analyzer' not in sys.modules\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parent.parent,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not cache.parent.exists()


@pytest.mark.parametrize("ziel", ["cache", "log"])
def test_schreibpfade_innerhalb_musikwurzel_werden_abgelehnt(tmp_path, ziel):
    root = tmp_path / "musik"
    root.mkdir()
    (root / "eins.wav").write_bytes(b"audio")
    cache = root / "cache.db" if ziel == "cache" else tmp_path / "cache.db"
    log = root / "progress.log" if ziel == "log" else tmp_path / "progress.log"

    assert analyze_library.main(_args(root, cache, log=log), analyzer_factory=None) == 2


@pytest.mark.parametrize(
    "extra",
    [
        ["--expected-files", "0"],
        ["--min-success", "-1"],
        ["--workers", "0"],
        ["--workers", "5"],
        ["--task-timeout", "59"],
        ["--task-timeout", "901"],
        ["--task-timeout", "nan"],
        ["--task-timeout", "inf"],
    ],
)
def test_numerische_cli_grenzen_enden_mit_zwei(tmp_path, extra):
    root = tmp_path / "musik"
    root.mkdir()
    args = _args(root, tmp_path / "cache.db")
    option = extra[0]
    if option in args:
        index = args.index(option)
        args[index:index + 2] = extra
    else:
        args.extend(extra)

    with pytest.raises(SystemExit) as exc:
        analyze_library.main(args, analyzer_factory=lambda **kwargs: None)

    assert exc.value.code == 2


def test_min_success_darf_expected_nicht_uebersteigen(tmp_path):
    root = tmp_path / "musik"
    root.mkdir()
    assert analyze_library.main(
        _args(root, tmp_path / "cache.db", expected=1, minimum=2),
        analyzer_factory=lambda **kwargs: None,
    ) == 2


def test_cache_resolve_fehler_endet_kontrolliert_mit_zwei(tmp_path, monkeypatch):
    root = tmp_path / "musik"
    root.mkdir()
    cache = tmp_path / "cache.db"
    original_resolve = Path.resolve

    def resolve(self, *args, **kwargs):
        if self == cache:
            raise OSError("resolve kaputt")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)

    assert analyze_library.main(
        _args(root, cache, expected=1), analyzer_factory=lambda **kwargs: None
    ) == 2


def test_mkdir_fehler_endet_kontrolliert_mit_eins(tmp_path, monkeypatch):
    root = tmp_path / "musik"
    root.mkdir()
    (root / "eins.wav").write_bytes(b"audio")
    cache = tmp_path / "work" / "cache.db"
    original_mkdir = Path.mkdir

    def mkdir(self, *args, **kwargs):
        if self == cache.parent:
            raise OSError("mkdir kaputt")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)

    assert analyze_library.main(
        _args(root, cache), analyzer_factory=lambda **kwargs: None
    ) == 1


def test_progresslog_close_fehler_endet_mit_eins(tmp_path, monkeypatch):
    root = tmp_path / "musik"
    root.mkdir()
    (root / "eins.wav").write_bytes(b"audio")
    cache = tmp_path / "work" / "cache.db"
    log = tmp_path / "work" / "progress.log"
    original_open = Path.open

    class KaputtesLog:
        def write(self, _text):
            return None

        def flush(self):
            return None

        def close(self):
            raise OSError("close kaputt")

    def open_file(self, *args, **kwargs):
        if self == log:
            return KaputtesLog()
        return original_open(self, *args, **kwargs)

    class FakeAnalyzer:
        def __init__(self, max_workers):
            pass

        def analyze_files(self, paths, progress_callback):
            progress_callback(1, 1, "fertig")
            return [object()]

    monkeypatch.setattr(Path, "open", open_file)

    assert analyze_library.main(
        _args(root, cache, log=log), analyzer_factory=FakeAnalyzer
    ) == 1


@pytest.mark.skipif(os.name != "nt", reason="Windows-Pfadsemantik")
def test_innerhalb_ist_auf_windows_case_insensitive(tmp_path):
    root = tmp_path.resolve()
    anders_geschrieben = Path(str(root / "unterordner").swapcase())

    assert analyze_library._innerhalb(anders_geschrieben, root)


@pytest.mark.parametrize(
    "core_status,erwarteter_status",
    [
        ("Analyzed: eins.wav", "Analysiert (Persistenz ungeprueft): eins.wav"),
        (
            "Analyzed (Safe Mode): eins.wav",
            "Analysiert (Safe Mode; Persistenz ungeprueft): eins.wav",
        ),
    ],
)
def test_analyzer_einmal_worker_und_eindeutiger_progressstatus(
    tmp_path, core_status, erwarteter_status,
):
    root = tmp_path / "musik"
    root.mkdir()
    (root / "eins.wav").write_bytes(b"audio")
    cache = tmp_path / "work" / "cache.db"
    cache.parent.mkdir()
    _gueltiger_cache(cache)
    track = _track(root / "eins.wav")
    _cachezeile(cache, track)
    log = tmp_path / "work" / "progress.log"
    erzeugt = []

    class FakeAnalyzer:
        def __init__(self, max_workers):
            erzeugt.append(max_workers)

        def analyze_files(self, paths, progress_callback):
            erzeugt.append(tuple(paths))
            progress_callback(1, 1, core_status)
            return [track]

    assert analyze_library.main(
        _args(root, cache, workers=4, log=log), analyzer_factory=FakeAnalyzer
    ) == 0
    assert erzeugt == [4, (str((root / "eins.wav").resolve()),)]
    assert f"1/1 {erwarteter_status}" in log.read_text(encoding="utf-8")


def test_bestehende_fremddatei_wird_vor_analyzer_abgelehnt(tmp_path):
    root = tmp_path / "musik"
    root.mkdir()
    (root / "eins.wav").write_bytes(b"audio")
    cache = tmp_path / "fremd.db"
    cache.write_text("keine Datenbank", encoding="utf-8")
    gebaut = []

    assert analyze_library.main(
        _args(root, cache), analyzer_factory=lambda **kwargs: gebaut.append(kwargs)
    ) == 2
    assert gebaut == []


def test_cache_mit_falscher_version_wird_abgelehnt(tmp_path):
    root = tmp_path / "musik"
    root.mkdir()
    (root / "eins.wav").write_bytes(b"audio")
    cache = tmp_path / "alt.db"
    _gueltiger_cache(cache)
    conn = sqlite3.connect(cache)
    try:
        conn.execute("UPDATE cache SET version = version - 1 WHERE key = 'version'")
        conn.commit()
    finally:
        conn.close()

    assert analyze_library.main(
        _args(root, cache), analyzer_factory=lambda **kwargs: None
    ) == 2


@pytest.mark.parametrize(
    "schema",
    [
        "key TEXT PRIMARY KEY, filepath TEXT, version INTEGER, data TEXT, extra TEXT",
        "filepath TEXT, key TEXT PRIMARY KEY, version INTEGER, data TEXT",
    ],
)
def test_nichtkanonisches_cache_schema_wird_vor_analyse_abgelehnt(
    tmp_path, schema,
):
    from hpg_core.caching import CACHE_VERSION

    root = tmp_path / "musik"
    root.mkdir()
    (root / "eins.wav").write_bytes(b"audio")
    cache = tmp_path / "schema.db"
    conn = sqlite3.connect(cache)
    try:
        conn.execute(f"CREATE TABLE cache ({schema})")
        conn.execute(
            "INSERT INTO cache (key, filepath, version, data) "
            "VALUES ('version', 'system', ?, 'metadata')",
            (CACHE_VERSION,),
        )
        conn.commit()
    finally:
        conn.close()
    gebaut = []

    assert analyze_library.main(
        _args(root, cache),
        analyzer_factory=lambda **kwargs: gebaut.append(kwargs),
    ) == 2
    assert gebaut == []


def test_geerbter_hpg_cache_file_darf_nicht_arbeitscache_werden(
    tmp_path, monkeypatch
):
    root = tmp_path / "musik"
    root.mkdir()
    (root / "eins.wav").write_bytes(b"audio")
    cache = tmp_path / "produkt.db"
    monkeypatch.setenv("HPG_CACHE_FILE", str(cache))
    gebaut = []

    assert analyze_library.main(
        _args(root, cache), analyzer_factory=lambda **kwargs: gebaut.append(kwargs)
    ) == 2
    assert gebaut == []
    assert not cache.exists()


@pytest.mark.parametrize("timeout", [60, 900])
def test_task_timeout_erlaubt_inklusive_grenzen_und_restauriert(tmp_path, timeout):
    from hpg_core import config

    root = tmp_path / "musik"
    root.mkdir()
    (root / "eins.wav").write_bytes(b"audio")
    vorher = config.PARALLEL_ANALYSIS_TIMEOUT
    gesehen = []
    cache = tmp_path / "cache.db"
    track = _track(root / "eins.wav")
    _cachezeile(cache, track)

    class FakeAnalyzer:
        def __init__(self, max_workers):
            gesehen.append(config.PARALLEL_ANALYSIS_TIMEOUT)

        def analyze_files(self, paths, progress_callback):
            gesehen.append(config.PARALLEL_ANALYSIS_TIMEOUT)
            return [track]

    assert analyze_library.main(
        _args(root, cache, timeout=timeout),
        analyzer_factory=FakeAnalyzer,
    ) == 0
    assert gesehen == [timeout, timeout]
    assert config.PARALLEL_ANALYSIS_TIMEOUT == vorher


def test_task_timeout_wird_auch_nach_analyzer_exception_restauriert(tmp_path):
    from hpg_core import config

    root = tmp_path / "musik"
    root.mkdir()
    (root / "eins.wav").write_bytes(b"audio")
    vorher = config.PARALLEL_ANALYSIS_TIMEOUT

    class FakeAnalyzer:
        def __init__(self, max_workers):
            assert config.PARALLEL_ANALYSIS_TIMEOUT == 300

        def analyze_files(self, paths, progress_callback):
            raise RuntimeError("Analyse kaputt")

    assert analyze_library.main(
        _args(root, tmp_path / "cache.db", timeout=300),
        analyzer_factory=FakeAnalyzer,
    ) == 1
    assert config.PARALLEL_ANALYSIS_TIMEOUT == vorher


def test_zu_wenig_erfolge_ergibt_eins(tmp_path):
    root = tmp_path / "musik"
    root.mkdir()
    (root / "eins.wav").write_bytes(b"audio")

    class FakeAnalyzer:
        def __init__(self, max_workers):
            pass

        def analyze_files(self, paths, progress_callback):
            return []

    assert analyze_library.main(
        _args(root, tmp_path / "cache.db"), analyzer_factory=FakeAnalyzer
    ) == 1


def test_subprozess_setzt_cache_vor_hpg_caching_import(tmp_path):
    root = tmp_path / "musik"
    root.mkdir()
    (root / "eins.wav").write_bytes(b"audio")
    cache = (tmp_path / "work" / "cache.db").resolve()
    log = (tmp_path / "work" / "progress.log").resolve()
    code = (
        "from tools import analyze_library as a\n"
        "class F:\n"
        " def __init__(self,max_workers):\n"
        "  from hpg_core.caching import CACHE_FILE\n"
        "  assert str(CACHE_FILE)==r'" + str(cache) + "'\n"
        " def analyze_files(self,paths,progress_callback):\n"
        "  from hpg_core.caching import init_cache\n"
        "  init_cache()\n"
        "  return []\n"
        "raise SystemExit(a.main(" + repr(_args(root, cache, minimum=0, log=log)) + ", analyzer_factory=F))\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parent.parent,
        text=True,
        capture_output=True,
        env={**os.environ, "HPG_CACHE_FILE": str(tmp_path / "falsch.db")},
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_analyseobjekt_ohne_cachezeile_zaehlt_nicht_als_erfolg(tmp_path, capsys):
    root = tmp_path / "musik"
    root.mkdir()
    audio = root / "eins.wav"
    audio.write_bytes(b"audio")
    cache = tmp_path / "cache.db"
    log = tmp_path / "progress.log"
    _gueltiger_cache(cache)
    track = _track(audio)

    class FakeAnalyzer:
        def __init__(self, max_workers):
            pass

        def analyze_files(self, paths, progress_callback):
            progress_callback(1, 1, "Analyzed: eins.wav")
            return [track]

    assert analyze_library.main(
        _args(root, cache, log=log), analyzer_factory=FakeAnalyzer
    ) == 1
    output = capsys.readouterr()
    assert "0/1 Tracks erfolgreich persistiert" in output.out
    assert str(audio.resolve()) in output.err
    log_text = log.read_text(encoding="utf-8")
    assert "Analysiert (Persistenz ungeprueft): eins.wav" in log_text
    assert "Persistiert: 0/1 Analyseerfolge" in log_text


def test_vorbefuelltes_progresslog_kann_resume_nicht_vortaeuschen(tmp_path):
    root = tmp_path / "musik"
    root.mkdir()
    (root / "eins.wav").write_bytes(b"audio")
    cache = tmp_path / "cache.db"
    log = tmp_path / "progress.log"
    _gueltiger_cache(cache)
    log.write_text(
        "2026-08-26T00:00:00 1/1 Analyzed: eins.wav\n",
        encoding="utf-8",
    )
    aufrufe = []

    class FakeAnalyzer:
        def __init__(self, max_workers):
            pass

        def analyze_files(self, paths, progress_callback):
            aufrufe.append(tuple(paths))
            return []

    assert analyze_library.main(
        _args(root, cache, log=log), analyzer_factory=FakeAnalyzer
    ) == 1
    assert aufrufe == [(str((root / "eins.wav").resolve()),)]


@pytest.mark.parametrize("defekt", ["key", "version", "json"])
def test_falsche_cachezeile_zaehlt_nicht(tmp_path, defekt):
    root = tmp_path / "musik"
    root.mkdir()
    audio = root / "eins.wav"
    audio.write_bytes(b"audio")
    cache = tmp_path / "cache.db"
    track = _track(audio)
    if defekt == "key":
        _cachezeile(cache, track, key="falscher-key")
    elif defekt == "version":
        _cachezeile(cache, track, version=0)
    else:
        _gueltiger_cache(cache)
        from hpg_core.caching import CACHE_VERSION, generate_cache_key
        conn = sqlite3.connect(cache)
        try:
            conn.execute(
                "INSERT INTO cache (key, filepath, version, data) VALUES (?, ?, ?, ?)",
                (generate_cache_key(track.filePath), track.filePath, CACHE_VERSION, "kaputt"),
            )
            conn.commit()
        finally:
            conn.close()

    class FakeAnalyzer:
        def __init__(self, max_workers):
            pass

        def analyze_files(self, paths, progress_callback):
            return [track]

    assert analyze_library.main(
        _args(root, cache), analyzer_factory=FakeAnalyzer
    ) == 1


def test_min_success_verwendet_eindeutige_persistierte_pfade(tmp_path):
    root = tmp_path / "musik"
    root.mkdir()
    first = root / "eins.wav"
    second = root / "zwei.wav"
    first.write_bytes(b"audio-1")
    second.write_bytes(b"audio-2")
    cache = tmp_path / "cache.db"
    first_track = _track(first)
    second_track = _track(second)
    _cachezeile(cache, first_track)

    class FakeAnalyzer:
        def __init__(self, max_workers):
            pass

        def analyze_files(self, paths, progress_callback):
            return [first_track, first_track, second_track]

    assert analyze_library.main(
        _args(root, cache, expected=2, minimum=1), analyzer_factory=FakeAnalyzer
    ) == 0
    assert analyze_library.main(
        _args(root, cache, expected=2, minimum=2), analyzer_factory=FakeAnalyzer
    ) == 1


def test_neuer_cache_ohne_kanonischen_marker_kann_nicht_erfolgreich_sein(tmp_path):
    root = tmp_path / "musik"
    root.mkdir()
    audio = root / "eins.wav"
    audio.write_bytes(b"audio")
    cache = tmp_path / "cache.db"
    track = _track(audio)

    class FakeAnalyzer:
        def __init__(self, max_workers):
            pass

        def analyze_files(self, paths, progress_callback):
            _cachezeile(cache, track)
            conn = sqlite3.connect(cache)
            try:
                conn.execute("DELETE FROM cache WHERE key='version'")
                conn.commit()
            finally:
                conn.close()
            return [track]

    assert analyze_library.main(
        _args(root, cache), analyzer_factory=FakeAnalyzer
    ) == 1


def test_cache_uri_akzeptiert_prozent_und_leerzeichen(tmp_path):
    cache = tmp_path / "cache 100% echt.db"
    _gueltiger_cache(cache)

    from hpg_core.caching import CACHE_VERSION

    assert analyze_library._pruefe_bestehenden_cache(cache, CACHE_VERSION) is None


@pytest.mark.parametrize("vorher", [None, "", "   ", "  C:\\alt.db  "])
def test_cache_environment_wird_nach_vorbereitungsfehler_exakt_restauriert(
    tmp_path, monkeypatch, vorher,
):
    root = tmp_path / "musik"
    root.mkdir()
    (root / "eins.wav").write_bytes(b"audio")
    if vorher is None:
        monkeypatch.delenv("HPG_CACHE_FILE", raising=False)
    else:
        monkeypatch.setenv("HPG_CACHE_FILE", vorher)
    monkeypatch.setattr(
        analyze_library,
        "_produktcache_pfad",
        lambda version: (_ for _ in ()).throw(RuntimeError("vorbereitung kaputt")),
    )

    assert analyze_library.main(
        _args(root, tmp_path / "cache.db"), analyzer_factory=lambda **kwargs: None
    ) == 1
    if vorher is None:
        assert "HPG_CACHE_FILE" not in os.environ
    else:
        assert os.environ["HPG_CACHE_FILE"] == vorher


def test_persistenzfehler_steht_als_finaler_status_im_progresslog(tmp_path):
    root = tmp_path / "musik"
    root.mkdir()
    audio = root / "eins.wav"
    audio.write_bytes(b"audio")
    log = tmp_path / "progress.log"
    track = _track(audio)

    class FakeAnalyzer:
        def __init__(self, max_workers):
            pass

        def analyze_files(self, paths, progress_callback):
            return [track]

    assert analyze_library.main(
        _args(root, tmp_path / "fehlt.db", log=log),
        analyzer_factory=FakeAnalyzer,
    ) == 1
    assert "[FAILED] Persistenznachweis:" in log.read_text(encoding="utf-8")
