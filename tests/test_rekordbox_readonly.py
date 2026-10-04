"""Isolierte Adapterpruefung; ausschliesslich selbst erzeugte Temp-Dateien."""
import importlib
import os
import sqlite3
import logging
from pathlib import Path

import pytest
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Parent(Base):
    __tablename__ = "parent"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    children = relationship("Child")
    spare = relationship("Spare")


class Child(Base):
    __tablename__ = "child"
    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("parent.id"))
    name = Column(String)


class Spare(Base):
    __tablename__ = "spare"
    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("parent.id"))


@pytest.fixture
def adapter():
    return importlib.import_module("hpg_core.rekordbox_readonly")


@pytest.fixture(params=[False, True], ids=["sqlite", "sqlcipher"])
def database(tmp_path, request):
    encrypted = request.param
    if encrypted:
        from sqlcipher3 import dbapi2 as driver
    else:
        driver = sqlite3
    path = tmp_path / "fixture.db"
    key = "opaque-sensitive-token-7816"
    connection = driver.connect(str(path))
    if encrypted:
        connection.execute("PRAGMA key='" + key + "'")
    connection.executescript(
        "CREATE TABLE parent(id INTEGER PRIMARY KEY, name TEXT);"
        "CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER, name TEXT);"
        "CREATE TABLE spare(id INTEGER PRIMARY KEY, parent_id INTEGER);"
        "INSERT INTO parent VALUES(1, 'alpha');"
        "INSERT INTO child VALUES(2, 1, 'beta');"
    )
    connection.commit()
    connection.close()
    return path, key, encrypted


def test_factory_available():
    # Fehlender Adapter muss als explizites RED sichtbar werden.
    import importlib.util
    assert importlib.util.find_spec("hpg_core.rekordbox_readonly") is not None


def test_rows_relations_detached_and_close(adapter, database):
    from sqlalchemy import inspect
    from sqlalchemy.orm import selectinload
    path, key, encrypted = database
    reader = adapter.open_rekordbox_readonly(path, key=key, unlock=encrypted)
    query = reader.query(Parent).options(selectinload(Parent.children))
    rows = list(query)
    assert [(row.name, row.children[0].name) for row in rows] == [("alpha", "beta")]
    assert inspect(rows[0]).detached
    assert inspect(rows[0].children[0]).detached
    # Nach abgeschlossener Abfrage darf kein dauerhaftes Handle sperren.
    renamed = path.with_suffix(".moved")
    path.rename(renamed)
    renamed.rename(path)
    reader.close()
    reader.close()
    with pytest.raises(adapter.ReadOnlyRekordboxError):
        list(query)
    assert not any(hasattr(reader, name) for name in ("commit", "add", "delete", "session", "engine"))


@pytest.mark.skipif(os.name != "nt", reason="Windows-Dateisperren")
def test_guard_blocks_real_write_delete_rename_and_releases(adapter, database):
    path, key, encrypted = database
    sidecars = [Path(str(path) + suffix) for suffix in ("-wal", "-journal", "-shm")]
    for sidecar in sidecars:
        sidecar.touch()
    targets = [path, *sidecars]
    with adapter._guard(path):
        for target in targets:
            with pytest.raises(OSError):
                with target.open("r+b"):
                    pass
            with pytest.raises(OSError):
                target.unlink()
            with pytest.raises(OSError):
                target.rename(target.with_name(target.name + ".moved"))
    for target in targets:
        with target.open("r+b") as stream:
            stream.write(b"x")
        renamed = target.with_name(target.name + ".released")
        target.rename(renamed)
        renamed.unlink()


@pytest.mark.parametrize("suffix", ["-wal", "-journal"])
def test_nonempty_sidecar_rejected_cleanup(adapter, database, suffix):
    path, key, encrypted = database
    Path(str(path) + suffix).write_bytes(b"persistent-data")
    reader = adapter.open_rekordbox_readonly(path, key=key, unlock=encrypted)
    with pytest.raises(adapter.ReadOnlyRekordboxError):
        list(reader.query(Parent))
    path.rename(path.with_suffix(".released"))


def test_sql_write_authorizer_and_error_secrets(adapter, database, caplog):
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="sqlalchemy.engine")
    path, key, encrypted = database
    reader = adapter.open_rekordbox_readonly(path, key=key, unlock=encrypted)
    from sqlalchemy import text
    statements = [
        "DELETE FROM parent", "CREATE TABLE evil(x)",
        "ATTACH DATABASE ':memory:' AS evil", "VACUUM",
        "PRAGMA query_only=OFF", "PRAGMA user_version=42",
        "SELECT load_extension('" + key + "')",
    ]
    for sql in statements:
        with pytest.raises(adapter.ReadOnlyRekordboxError) as error:
            reader._run(lambda session: session.execute(text(sql)).all())
        assert key not in str(error.value)
        assert sql not in str(error.value)
        assert error.value.__suppress_context__
    assert key not in caplog.text
    assert list(reader.query(Parent))[0].name == "alpha"


def test_real_persistent_wal_rejected(adapter, database):
    path, key, encrypted = database
    if encrypted:
        from sqlcipher3 import dbapi2 as driver
    else:
        driver = sqlite3
    connection = driver.connect(str(path))
    if encrypted:
        connection.execute("PRAGMA key='" + key + "'")
    assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    connection.execute("PRAGMA wal_autocheckpoint=0")
    connection.execute("UPDATE parent SET name='wal-value'")
    connection.commit()
    # Echte WAL-Datei nach Prozessende ohne SQLite-close/Checkpoint erhalten.
    # Hier wird der echte SQLITE_FCNTL_PERSIST_WAL Mechanismus separat nicht
    # vorausgesetzt: ein Kindprozess beendet sich nach seinem Commit abrupt.
    connection.close()
    import subprocess
    import sys
    code = (
        "import os,sys,sqlite3; "
        + ("from sqlcipher3 import dbapi2 as d; " if encrypted else "d=sqlite3; ")
        + "c=d.connect(sys.argv[1]); "
        + ("c.execute(\"PRAGMA key='\"+sys.stdin.read()+\"'\"); " if encrypted else "")
        + "c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA wal_autocheckpoint=0'); "
        + "c.execute(\"UPDATE parent SET name='uncheckpointed'\"); c.commit(); os._exit(0)"
    )
    subprocess.run([sys.executable, "-B", "-c", code, str(path)],
                   input=key if encrypted else "", text=True, check=True, capture_output=True)
    assert Path(str(path) + "-wal").stat().st_size > 32
    reader = adapter.open_rekordbox_readonly(path, key=key, unlock=encrypted)
    with pytest.raises(adapter.ReadOnlyRekordboxError):
        list(reader.query(Parent))
    path.rename(path.with_suffix(".released"))


def test_guard_live_during_query_and_released_after(adapter, database):
    from sqlalchemy import text
    path, key, encrypted = database
    reader = adapter.open_rekordbox_readonly(path, key=key, unlock=encrypted)
    def inside(session):
        assert session.execute(text("SELECT name FROM parent")).scalar() == "alpha"
        with pytest.raises(OSError):
            path.open("r+b")
        with pytest.raises(OSError):
            path.rename(path.with_suffix(".forbidden"))
        return "materialized"
    assert reader._run(inside) == "materialized"
    with path.open("r+b"):
        pass


def test_writer_already_open_rejected_and_cleanup(adapter, database):
    path, key, encrypted = database
    reader = adapter.open_rekordbox_readonly(path, key=key, unlock=encrypted)
    with path.open("r+b"):
        with pytest.raises(adapter.ReadOnlyRekordboxError):
            list(reader.query(Parent))
    assert list(reader.query(Parent))[0].name == "alpha"


def test_anlz_traversal_and_parser(adapter, database, monkeypatch):
    from types import SimpleNamespace
    import struct
    path, key, encrypted = database
    root = path.parent / "share"
    root.mkdir()
    directory = root / "nested"
    directory.mkdir()
    anlz = directory / "ANLZ0000.DAT"
    anlz.write_bytes(b"PMAI" + struct.pack(">II", 28, 28) + b"\0" * 16)
    reader = adapter.open_rekordbox_readonly(path, key=key, unlock=encrypted)
    row = SimpleNamespace(AnalysisDataPath="/nested/ANLZ0000.DAT")
    monkeypatch.setattr(reader, "get_content", lambda **kwargs: row)
    parsed = reader.read_anlz_file("1", "DAT")
    assert parsed is not None and parsed.num_tags == 0
    for unsafe in ("../outside/ANLZ0000.DAT", "C:/outside/ANLZ0000.DAT",
                   "\\\\server\\share\\ANLZ0000.DAT"):
        row.AnalysisDataPath = unsafe
        with pytest.raises(adapter.ReadOnlyRekordboxError):
            reader.read_anlz_files("1")
    reader.close()
    with pytest.raises(adapter.ReadOnlyRekordboxError):
        reader.read_anlz_files("1")


def _importer_using_reader(reader, rows, monkeypatch):
    """Nur Metadaten-Stubs, ANLZ-Leser bleibt echte gesicherte Implementierung."""
    from hpg_core import rekordbox_importer as importer_module

    class Database:
        def get_content(self):
            return rows

        def read_anlz_files(self, content_id):
            return reader.read_anlz_files(content_id)

        def read_anlz_file(self, content_id, kind):
            return reader.read_anlz_file(content_id, kind)

        def close(self):
            reader.close()

    monkeypatch.setattr(importer_module, "REKORDBOX_AVAILABLE", True)
    monkeypatch.setattr(importer_module, "Rekordbox6Database", Database)
    return importer_module.RekordboxImporter()


def _content(identifier, anlz):
    from types import SimpleNamespace
    return SimpleNamespace(
        ID=identifier, AnalysisDataPath=anlz, FolderPath=f"C:/fixture/{identifier}.aiff",
        FileNameL=f"{identifier}.aiff", FileNameS=f"{identifier}.aiff", BPM=12800,
        KeyName="8A", Length=300, Title=identifier, ArtistName="fixture",
        GenreName="Techno", AlbumName="fixture", Rating=0, ColorName=None, Cues=[],
    )


def test_optional_missing_anlz_does_not_discard_other_track_metadata(adapter, database, monkeypatch):
    import struct
    path, key, encrypted = database
    directory = path.parent / "share" / "good"
    directory.mkdir(parents=True)
    (directory / "ANLZ0000.DAT").write_bytes(b"PMAI" + struct.pack(">II", 28, 28) + b"\0" * 16)
    reader = adapter.open_rekordbox_readonly(path, key=key, unlock=encrypted)
    rows = [_content("1", "/missing/ANLZ0000.DAT"), _content("2", "/good/ANLZ0000.DAT")]
    monkeypatch.setattr(reader, "get_content", lambda **kw: next(r for r in rows if r.ID == kw["ID"]))
    importer = _importer_using_reader(reader, rows, monkeypatch)
    assert importer.get_beatgrid(rows[0].FolderPath) == []
    assert importer.is_available()
    assert len(importer.track_cache) == 2
    assert importer.get_track_data(rows[1].FolderPath).bpm == 128.0
    assert reader.read_anlz_file("2", "DAT").num_tags == 0
    importer.close()


def test_dat_only_read_and_importer_fallback_ignore_corrupt_ext(adapter, database, monkeypatch):
    import struct
    path, key, encrypted = database
    directory = path.parent / "share" / "good"
    directory.mkdir(parents=True)
    (directory / "ANLZ0000.DAT").write_bytes(b"PMAI" + struct.pack(">II", 28, 28) + b"\0" * 16)
    (directory / "ANLZ0000.EXT").write_bytes(b"CORRUPT EXT TEXT FIXTURE")
    reader = adapter.open_rekordbox_readonly(path, key=key, unlock=encrypted)
    row = _content("1", "/good/ANLZ0000.DAT")
    monkeypatch.setattr(reader, "get_content", lambda **kw: row)
    assert reader.read_anlz_file("1", "DAT").num_tags == 0
    with pytest.raises(adapter.RekordboxAnlzReadError) as error:
        reader.read_anlz_files("1")
    assert error.value.__context__ is None
    importer = _importer_using_reader(reader, [row], monkeypatch)
    assert importer._read_anlz_files("1")[0].num_tags == 0
    assert importer.is_available()
    importer.close()


def test_no_error_context_secret(adapter, database):
    path, key, encrypted = database
    reader = adapter.open_rekordbox_readonly(path, key=key, unlock=encrypted)
    with pytest.raises(adapter.ReadOnlyRekordboxError) as error:
        reader._run(lambda session: (_ for _ in ()).throw(RuntimeError(key)))
    # Auch versehentliche Weitergabe von __context__ soll keine Geheimnisse tragen.
    assert error.value.__context__ is None


def test_rekordbox_schema_content_id_and_relations(adapter, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from pyrekordbox.db6.tables import Base as RBBase, DjmdContent, DjmdArtist
    path = tmp_path / "rekordbox-fixture.db"
    engine = create_engine("sqlite:///" + str(path))
    RBBase.metadata.create_all(engine)
    def required(model, **overrides):
        import datetime
        values = {}
        for column in model.__table__.columns:
            if not column.nullable and column.default is None:
                python_type = column.type.python_type
                values[column.name] = (datetime.datetime(2020, 1, 1) if python_type is datetime.datetime
                                       else 0 if python_type in (int, float) else "")
        return model(**{**values, **overrides})
    with Session(engine) as session:
        session.add(required(DjmdArtist, ID="2", Name="Fixture Artist"))
        session.add(required(DjmdContent, ID="1", Title="Fixture", ArtistID="2"))
        session.commit()
    engine.dispose()
    reader = adapter.open_rekordbox_readonly(path, unlock=False)
    row = reader.get_content(ID="1")
    assert row.Title == "Fixture"
    assert row.Artist.Name == "Fixture Artist"
    assert reader.get_content(ID="missing") is None
    assert [row.ID for row in reader.get_content(Title="Fixture")] == ["1"]


def test_anlz_junction_escape(adapter, database, monkeypatch, tmp_path):
    from types import SimpleNamespace
    import subprocess
    path, key, encrypted = database
    root = path.parent / "share"
    root.mkdir()
    outside = path.parent / "outside"
    outside.mkdir()
    junction = root / "escape"
    # Fixe, von pytest kontrollierte Temp-Pfade; keine Quellmedien.
    subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
                   check=True, capture_output=True)
    reader = adapter.open_rekordbox_readonly(path, key=key, unlock=encrypted)
    monkeypatch.setattr(reader, "get_content", lambda **kwargs:
                        SimpleNamespace(AnalysisDataPath="escape/ANLZ0000.DAT"))
    try:
        with pytest.raises(adapter.ReadOnlyRekordboxError):
            reader.read_anlz_files("1")
    finally:
        junction.rmdir()


def test_query_failure_releases_handles(adapter, database):
    path, key, encrypted = database
    reader = adapter.open_rekordbox_readonly(path, key=key, unlock=encrypted)
    with pytest.raises(adapter.ReadOnlyRekordboxError):
        reader._run(lambda session: (_ for _ in ()).throw(RuntimeError(key)))
    renamed = path.with_suffix(".released")
    path.rename(renamed)
    renamed.rename(path)
    assert list(reader.query(Parent))[0].name == "alpha"


@pytest.mark.parametrize("suffix", ["-wal", "-journal", "-shm"])
def test_new_sidecar_during_guard_rejected(adapter, database, suffix):
    path, key, encrypted = database
    with pytest.raises(adapter.ReadOnlyRekordboxError):
        with adapter._guard(path):
            Path(str(path) + suffix).touch()
    # Fehlerpfad muss ebenfalls alle Handles freigeben.
    path.rename(path.with_suffix(".released"))


def test_reads_preserve_bytes_timestamps_and_no_sidecars(adapter, database):
    import hashlib
    path, key, encrypted = database
    before = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
    reader = adapter.open_rekordbox_readonly(path, key=key, unlock=encrypted)
    assert list(reader.query(Parent))[0].name == "alpha"
    after = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
    assert before == after
    assert not any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal"))


def test_config_default_and_internal_key_without_base_constructor(adapter, database, monkeypatch, caplog):
    import pyrekordbox.config as config
    import pyrekordbox.utils as utils
    from pyrekordbox.db6.database import Rekordbox6Database
    path, key, encrypted = database
    def forbidden(*args, **kwargs):
        pytest.fail("Basiskonstruktor wurde aufgerufen")
    monkeypatch.setattr(Rekordbox6Database, "__init__", forbidden)
    monkeypatch.setattr(config, "get_config", lambda section:
                        {} if section == "rekordbox7" else {"db_path": path})
    monkeypatch.setattr(utils, "deobfuscate", lambda blob: key)
    caplog.set_level(logging.DEBUG)
    reader = adapter.open_rekordbox_readonly(unlock=encrypted)
    assert list(reader.query(Parent))[0].name == "alpha"
    assert key not in caplog.text


@pytest.mark.parametrize("database", [True], indirect=True, ids=["sqlcipher"])
def test_key_setup_failure_cleanup(adapter, database):
    path, key, encrypted = database
    reader = adapter.open_rekordbox_readonly(path, key="\0" + key)
    with pytest.raises(adapter.ReadOnlyRekordboxError) as error:
        list(reader.query(Parent))
    assert error.value.__context__ is None
    assert key not in str(error.value)
    path.rename(path.with_suffix(".released"))


def test_partial_sidecar_guard_failure_cleanup(adapter, database):
    path, key, encrypted = database
    wal = Path(str(path) + "-wal")
    wal.touch()
    shm = Path(str(path) + "-shm")
    shm.touch()
    reader = adapter.open_rekordbox_readonly(path, key=key, unlock=encrypted)
    with shm.open("r+b"):
        with pytest.raises(adapter.ReadOnlyRekordboxError):
            list(reader.query(Parent))
    path.rename(path.with_suffix(".released"))
    wal.unlink()


def test_explicit_eager_options_no_unrequested_queries(adapter, database):
    from sqlalchemy import event, inspect
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import joinedload
    path, key, encrypted = database
    if encrypted:
        from sqlcipher3 import dbapi2 as driver
    else:
        driver = sqlite3
    with driver.connect(str(path)) as connection:
        if encrypted:
            connection.execute("PRAGMA key='" + key + "'")
        connection.executemany("INSERT INTO parent VALUES(?, 'extra')", [(n,) for n in range(2, 10)])
        connection.commit()
    connection.close()
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(Engine, "before_cursor_execute", record)
    try:
        reader = adapter.open_rekordbox_readonly(path, key=key, unlock=encrypted)
        rows = list(reader.query(Parent).options(joinedload(Parent.children)))
    finally:
        event.remove(Engine, "before_cursor_execute", record)
    assert len(rows) == 9
    assert len(statements) == 1
    assert rows[0].children[0].name == "beta"
    assert all(inspect(row).detached and "spare" in inspect(row).unloaded for row in rows)
