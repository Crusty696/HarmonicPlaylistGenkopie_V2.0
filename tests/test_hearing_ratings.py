"""Gemeinsamer Bewertungsvertrag mit synthetischen Satzdateien."""
import datetime
import csv
import json
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer

import pytest

from tools import hoertest_server as hs
from tests.test_hoertest_server import _dramaturgie_satz, _server_post


def make_session(folder, mode):
    folder.mkdir()
    if mode == "dramaturgie":
        _dramaturgie_satz(folder)
        return
    (folder / "clips").mkdir()
    schema = {"einzel": hs.BEWERTUNG_SPALTEN,
              "kandidaten": hs.BEWERTUNG_KANDIDATEN_SPALTEN,
              "dreinoten": hs.BEWERTUNG_DREINOTEN_SPALTEN}[mode]
    rows, features = [], []
    for cid in ("p_k1", "p_k2"):
        (folder / "clips" / f"{cid}.wav").write_bytes(b"RIFF-synthetic")
        row = dict.fromkeys(schema, "")
        row["pair_id"] = cid if mode == "einzel" else "p"
        row["clip" if mode == "einzel" else "clip_id"] = f"clips/{cid}.wav" if mode == "einzel" else cid
        if mode == "kandidaten":
            row["note"] = "4"
        rows.append(row)
        features.append({"pair_id": row["pair_id"], "clip_id": cid, "clip": f"clips/{cid}.wav"})
    hs.schreibe_csv(folder / "bewertung.csv", schema, rows)
    hs.schreibe_csv(folder / "merkmale.csv", ("pair_id", "clip_id", "clip"), features)
    (folder / "reihenfolge.json").write_text(json.dumps({"p": {"clips": ["p_k2", "p_k1"]}}))


@pytest.fixture
def fixed_clock(monkeypatch):
    class FixedClock(datetime.datetime):
        @classmethod
        def now(cls):
            return cls(2026, 10, 4, 12, 0, 0)
    monkeypatch.setattr(hs.datetime, "datetime", FixedClock)


@pytest.fixture
def transport():
    servers = []
    def start(folder):
        handler = type("RatingHandler", (hs.HoertestHandler,), {"ordner": folder})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return server
    yield start
    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(5)


CASES = [("einzel", "/note", {"pair_id": "p_k1"}, "note")]
CASES += [(mode, "/note", {"pair_id": "p", "clip_id": "p_k1", "dimension": dim}, dim)
          for mode, dims in [("kandidaten", ["note"]), ("dreinoten", ["track_note", "technik_note", "gesamt_note"])] for dim in dims]
CASES += [("dramaturgie", route, {key: value, "dimension": dim}, dim)
          for route, key, value, dims in [
              ("/transition-note", "transition_id", "v01__t001", ["track_note", "technik_note", "gesamt_note"]),
              ("/dramaturgie-note", "variant_id", "v01", ["dramaturgie_gesamt", "energieverlauf", "peak_platzierung", "kohaerenz"])] for dim in dims]


@pytest.mark.parametrize("mode,route,payload,dimension", CASES)
def test_direct_http_all_dimensions_and_null(tmp_path, transport, fixed_clock, mode, route, payload, dimension):
    from hpg_core import hearing_ratings as ratings
    direct, remote = tmp_path / "direct", tmp_path / "remote"
    make_session(direct, mode)
    make_session(remote, mode)
    server = transport(remote)
    file = "dramaturgie_bewertung.csv" if route == "/dramaturgie-note" else "bewertung.csv"
    baseline = hs.lies_csv(direct / file)
    for note in (5, None):
        data = payload | {"note": note}
        ratings.save_rating(direct, route, data)
        assert _server_post(server, route, data) == 200
        for name in ("bewertung.csv", "dramaturgie_bewertung.csv"):
            if (direct / name).exists():
                assert (direct / name).read_bytes() == (remote / name).read_bytes()
        after = hs.lies_csv(direct / file)
        stored_dimension = "bewertung" if mode == "einzel" else dimension
        assert after[0][stored_dimension] == ("" if note is None else "5")
        assert after[1:] == baseline[1:]
        assert {k: v for k, v in after[0].items() if k not in (stored_dimension, "zeit")} == {k: v for k, v in baseline[0].items() if k not in (stored_dimension, "zeit")}
        if mode != "einzel":
            assert after[0]["zeit"] == "2026-10-04T12:00:00"
    session = ratings.load_session(direct)
    assert session["mode"] == mode
    assert session["groups"]
    if mode in ("kandidaten", "dreinoten"):
        assert [c["clip_id"] for c in session["groups"][0]["clips"]] == ["p_k2", "p_k1"]


@pytest.mark.parametrize("mode", ["kandidaten", "dreinoten"])
def test_winner_and_no_winner(tmp_path, transport, fixed_clock, mode):
    from hpg_core.hearing_ratings import save_rating, RatingError
    direct, remote = tmp_path / "a", tmp_path / "b"
    make_session(direct, mode)
    make_session(remote, mode)
    server = transport(remote)
    for cid in ("p_k1", "p_k2", ""):
        payload = {"pair_id": "p", "clip_id": cid}
        save_rating(direct, "/bester", payload)
        assert _server_post(server, "/bester", payload) == 200
        assert (direct / "bewertung.csv").read_bytes() == (remote / "bewertung.csv").read_bytes()
        rows = hs.lies_csv(direct / "bewertung.csv")
        assert [r["gewaehlt"] for r in rows] == (["0", "0"] if not cid else ["1" if r["clip_id"] == cid else "" for r in rows])
    if mode == "kandidaten":
        save_rating(direct, "/note", {"pair_id": "p", "clip_id": "p_k1", "note": 1})
        with pytest.raises(RatingError) as error:
            save_rating(direct, "/bester", {"pair_id": "p", "clip_id": "p_k1"})
        assert error.value.status == 400
        assert _server_post(server, "/note", {"pair_id": "p", "clip_id": "p_k1", "note": 1}) == 200
        before = (remote / "bewertung.csv").read_bytes()
        assert _server_post(server, "/bester", {"pair_id": "p", "clip_id": "p_k1"}) == 400
        assert (remote / "bewertung.csv").read_bytes() == before


@pytest.mark.parametrize("mode,route,payload,dimension", CASES)
@pytest.mark.parametrize("bad", [True, False, 1.0, "1", 0, 6, "omitted", "unknown_id", "unknown_dimension"])
def test_invalid_request_no_writes(tmp_path, transport, mode, route, payload, dimension, bad):
    from hpg_core.hearing_ratings import RatingError, save_rating
    folder = tmp_path / "session"
    make_session(folder, mode)
    data = payload | {"note": bad}
    expected = 400
    if bad == "omitted":
        del data["note"]
    elif bad == "unknown_id":
        data.update(note=3)
        data[next(k for k in payload if k.endswith("_id"))] = "missing"
        expected = 404
    elif bad == "unknown_dimension":
        data.update(note=3, dimension="missing")
    before = {p.name: p.read_bytes() for p in folder.glob("*.csv")}
    with pytest.raises(RatingError) as error:
        save_rating(folder, route, data)
    assert error.value.status == expected
    assert _server_post(transport(folder), route, data) == expected
    assert before == {p.name: p.read_bytes() for p in folder.glob("*.csv")}


@pytest.mark.parametrize("name", ["bewertung.csv", "merkmale.csv", "reihenfolge.json", "dramaturgie_manifest.json", "dramaturgie_bewertung.csv"])
def test_metadata_symlink_no_writes(tmp_path, transport, name):
    from hpg_core.hearing_ratings import RatingError, save_rating
    folder = tmp_path / "session"
    make_session(folder, "dramaturgie" if "dramaturgie" in name else "kandidaten")
    target = folder / name
    outside = tmp_path / "external"
    outside.write_bytes(target.read_bytes())
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Symlinks unavailable: {exc}")
    before = {p.name: p.read_bytes() for p in folder.glob("*.csv")}
    route, payload = ("/dramaturgie-note", {"variant_id": "v01", "dimension": "energieverlauf", "note": 3}) if "dramaturgie" in name else ("/note", {"pair_id": "p", "clip_id": "p_k1", "note": 3})
    with pytest.raises(RatingError):
        save_rating(folder, route, payload)
    assert _server_post(transport(folder), route, payload) == 400
    assert before == {p.name: p.read_bytes() for p in folder.glob("*.csv")}


def test_lock_and_parallel_merge(tmp_path):
    from hpg_core import hearing_ratings as ratings
    assert ratings.CSV_SCHREIB_LOCK is hs.CSV_SCHREIB_LOCK
    folder = tmp_path / "session"
    make_session(folder, "dreinoten")
    with ThreadPoolExecutor(3) as pool:
        list(pool.map(lambda dim: ratings.save_rating(folder, "/note", {"pair_id": "p", "clip_id": "p_k1", "dimension": dim, "note": 4}), ["track_note", "technik_note", "gesamt_note"]))
    assert all(hs.lies_csv(folder / "bewertung.csv")[0][dim] == "4" for dim in ["track_note", "technik_note", "gesamt_note"])


@pytest.mark.parametrize("mode", ["einzel", "kandidaten", "dreinoten", "dramaturgie"])
@pytest.mark.parametrize("defect", ["duplicate_id", "schema", "missing_cell", "extra_cell"])
def test_malformed_ratings_no_writes(tmp_path, transport, mode, defect):
    from hpg_core.hearing_ratings import RatingError, load_session, save_rating
    folder = tmp_path / "session"
    make_session(folder, mode)
    path = folder / "bewertung.csv"
    lines = path.read_text().splitlines()
    if defect == "duplicate_id":
        lines.append(lines[1])
    elif defect == "schema":
        lines[0] += ",unknown"
    elif defect == "missing_cell":
        lines[1] = lines[1].rsplit(",", 1)[0]
    else:
        lines[1] += ",unknown"
    path.write_text("\n".join(lines) + "\n")
    before = path.read_bytes()
    route, payload = next((route, payload | {"note": 3}) for m, route, payload, _ in CASES if m == mode)
    with pytest.raises(RatingError):
        save_rating(folder, route, payload)
    with pytest.raises(RatingError):
        load_session(folder)
    assert _server_post(transport(folder), route, payload) == 400
    assert path.read_bytes() == before


@pytest.mark.parametrize("mode", ["einzel", "kandidaten", "dreinoten", "dramaturgie"])
def test_loader_no_audio_reads_and_missing_clip(tmp_path, monkeypatch, mode):
    from pathlib import Path
    from hpg_core.hearing_ratings import RatingError, load_session
    folder = tmp_path / "session"
    make_session(folder, mode)
    original = Path.open
    def guarded(path, *args, **kwargs):
        assert path.suffix != ".wav", "Loader darf WAV-Inhalte nicht lesen"
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded)
    session = load_session(folder)
    session["groups"][0]["clips"][0]["path"].unlink()
    with pytest.raises(RatingError):
        load_session(folder)


@pytest.mark.parametrize("mode", ["kandidaten", "dramaturgie"])
def test_loader_clip_symlink_containment(tmp_path, mode):
    from hpg_core.hearing_ratings import RatingError, load_session
    folder = tmp_path / "session"
    make_session(folder, mode)
    path = load_session(folder)["groups"][0]["clips"][0]["path"]
    outside = tmp_path / "external.wav"
    outside.write_bytes(b"RIFF-synthetic")
    path.unlink()
    try:
        path.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Symlinks unavailable: {exc}")
    with pytest.raises(RatingError):
        load_session(folder)


def test_transaction_reads_and_writes_hold_existing_lock(tmp_path, monkeypatch):
    from hpg_core.hearing_ratings import save_rating
    folder = tmp_path / "session"
    make_session(folder, "kandidaten")
    reads, writes = hs.lies_csv, hs.schreibe_csv
    called = []
    def read(path):
        assert hs.CSV_SCHREIB_LOCK._is_owned()
        called.append("read")
        return reads(path)
    def write(*args):
        assert hs.CSV_SCHREIB_LOCK._is_owned()
        called.append("write")
        return writes(*args)
    monkeypatch.setattr(hs, "lies_csv", read)
    monkeypatch.setattr(hs, "schreibe_csv", write)
    save_rating(folder, "/note", {"pair_id": "p", "clip_id": "p_k1", "note": 5})
    assert called == ["read", "write"]


def test_dramaturgy_missing_variant_cell_is_not_repaired_by_write(tmp_path, transport):
    from hpg_core.hearing_ratings import RatingError, load_session, save_rating
    folder = tmp_path / "session"
    make_session(folder, "dramaturgie")
    path = folder / "dramaturgie_bewertung.csv"
    lines = path.read_text().splitlines()
    lines[1] = lines[1].rsplit(",", 1)[0]
    path.write_text("\n".join(lines) + "\n")
    before = path.read_bytes()
    payload = {"variant_id": "v01", "dimension": "energieverlauf", "note": 5}
    with pytest.raises(RatingError):
        save_rating(folder, "/dramaturgie-note", payload)
    with pytest.raises(RatingError):
        load_session(folder)
    assert _server_post(transport(folder), "/dramaturgie-note", payload) == 400
    assert path.read_bytes() == before


@pytest.mark.parametrize("mode", ["kandidaten", "dreinoten"])
@pytest.mark.parametrize("raw", [
    '{"p":{"clips":["p_k1","p_k2"]},"p":{"clips":["p_k2","p_k1"]}}',
    '{"p":{"clips":["p_k1","p_k2"],"clips":["p_k2","p_k1"]}}',
])
def test_duplicate_order_keys_fail_closed_without_writes(tmp_path, monkeypatch, mode, raw):
    from hpg_core.hearing_ratings import RatingError, load_session
    folder = tmp_path / "session"
    make_session(folder, mode)
    (folder / "reihenfolge.json").write_text(raw, encoding="utf-8")
    before = {p.name: p.read_bytes() for p in folder.glob("*.csv")}
    with pytest.raises(RatingError, match="Doppelter JSON-Schluessel"):
        load_session(folder)
    monkeypatch.setattr(hs, "lade_track_infos", lambda *_: {})
    def forbid_server_start(*_args, **_kwargs):
        pytest.fail("Ungueltige Reihenfolge darf keinen HTTP-Server starten")
    monkeypatch.setattr(hs, "ThreadingHTTPServer", forbid_server_start)
    assert hs.main(["--dir", str(folder)]) == 2
    assert before == {p.name: p.read_bytes() for p in folder.glob("*.csv")}


@pytest.mark.parametrize("mode", ["einzel", "kandidaten", "dreinoten", "dramaturgie"])
@pytest.mark.parametrize("error_type", [csv.Error, PermissionError, UnicodeError])
def test_read_failure_propagates_and_http_returns_500(tmp_path, transport, monkeypatch, mode, error_type):
    from hpg_core.hearing_ratings import save_rating
    folder = tmp_path / "session"
    make_session(folder, mode)
    server = transport(folder)
    before = {p.name: p.read_bytes() for p in folder.glob("*.csv")}
    def fail_read(_path):
        raise error_type("synthetic read failure")
    monkeypatch.setattr(hs, "lies_csv", fail_read)
    route, payload = next((route, payload | {"note": 3}) for m, route, payload, _ in CASES if m == mode)
    with pytest.raises(error_type):
        save_rating(folder, route, payload)
    assert _server_post(server, route, payload) == 500
    assert before == {p.name: p.read_bytes() for p in folder.glob("*.csv")}


@pytest.mark.parametrize("mode", ["kandidaten", "dreinoten"])
@pytest.mark.parametrize("route", ["/note", "/bester"])
def test_unknown_clip_never_writes(tmp_path, transport, mode, route):
    from hpg_core.hearing_ratings import RatingError, save_rating
    folder = tmp_path / "session"
    make_session(folder, mode)
    before = (folder / "bewertung.csv").read_bytes()
    payload = {"pair_id": "p", "clip_id": "missing", "note": 3}
    if mode == "dreinoten":
        payload["dimension"] = "track_note"
    with pytest.raises(RatingError) as error:
        save_rating(folder, route, payload)
    assert error.value.status == 404
    assert _server_post(transport(folder), route, payload) == 404
    assert (folder / "bewertung.csv").read_bytes() == before


def test_success_adapter_is_explicitly_typed(tmp_path):
    from typing import get_type_hints
    from hpg_core.hearing_ratings import save_rating
    folder = tmp_path / "session"
    make_session(folder, "einzel")
    assert get_type_hints(save_rating)["return"] == dict[str, bool]
    assert save_rating(folder, "/note", {"pair_id": "p_k1", "note": 4}) == {"ok": True}


from tests.test_hearing_sources import source_fixture


def source_rating_session(source_fixture, mode):
    from hpg_core.hearing_sources import SourceRenderSink, write_source_manifest
    from tests.test_hearing_sources import make_candidate_metadata, make_dramaturgy_metadata
    stage, _, sink, a, b = source_fixture
    if mode != "einzel":
        (stage / "merkmale.csv").unlink()
        (stage / "bewertung.csv").unlink()
        sink = SourceRenderSink(stage, (a.parent,))
        if mode == "dramaturgie":
            paths = [a, b] + [a.parent / f"extra{i}.wav" for i in range(10)]
            for path in paths[2:]:
                path.write_bytes(b"synthetic extra source")
            make_dramaturgy_metadata(stage, paths, sink)
        else:
            make_candidate_metadata(stage, a, b, sink, three_notes=mode == "dreinoten")
    write_source_manifest(stage, "kandidaten" if mode == "dreinoten" else mode, sink)
    return stage


@pytest.mark.parametrize("mode", ["einzel", "kandidaten", "dreinoten", "dramaturgie"])
def test_source_session_virtual_playback_contract(source_fixture, mode, monkeypatch):
    from dataclasses import asdict
    import numpy as np
    import soundfile as sf
    from hpg_core import hearing_playback as playback
    from hpg_core.hearing_ratings import load_session
    stage = source_rating_session(source_fixture, mode)
    session = load_session(stage)
    assert session["mode"] == mode
    clip = session["groups"][0]["clips"][0]
    assert clip["path"] is None
    assert len(clip["sources"]) == 2
    assert {s["path"] for s in clip["sources"]} == {clip["spec"]["track_a_path"], clip["spec"]["track_b_path"]}
    assert all(s["size_bytes"] == Path(s["path"]).stat().st_size for s in clip["sources"])
    seen = []
    def render(spec, buffer):
        seen.append(asdict(spec))
        sf.write(buffer, np.zeros((441, 2)), 44100, format="WAV", subtype="PCM_16")
    monkeypatch.setattr("hpg_core.transition_renderer.render_transition_clip", render)
    assert playback.render_wav_bytes(clip["spec"], clip["sources"]).startswith(b"RIFF")
    assert seen == [clip["spec"]]
    assert not list(stage.rglob("*.wav"))


@pytest.mark.parametrize("mode,route,payload,dimension", CASES)
def test_source_save_dimensions_and_null(source_fixture, fixed_clock, mode, route, payload, dimension):
    from hpg_core.hearing_ratings import load_session, save_rating
    stage = source_rating_session(source_fixture, mode)
    session = load_session(stage)
    group = session["groups"][0]
    clip = group["clips"][0]
    data = dict(payload)
    for key in ("pair_id", "clip_id", "transition_id", "variant_id"):
        if key in data:
            data[key] = group["id"] if key == "variant_id" else clip["pair_id" if key == "pair_id" else "clip_id"]
    file = stage / ("dramaturgie_bewertung.csv" if route == "/dramaturgie-note" else "bewertung.csv")
    before = hs.lies_csv(file)
    for note in (5, None):
        assert save_rating(stage, route, data | {"note": note}) == {"ok": True}
        after = hs.lies_csv(file)
        assert after[0]["bewertung" if mode == "einzel" else dimension] == ("" if note is None else "5")
        assert after[1:] == before[1:]
        assert load_session(stage)["mode"] == mode
    assert not list(stage.rglob("*.wav"))


@pytest.mark.parametrize("mode", ["kandidaten", "dreinoten"])
def test_source_winner_semantics(source_fixture, mode):
    from hpg_core.hearing_ratings import RatingError, save_rating
    stage = source_rating_session(source_fixture, mode)
    payload = {"pair_id": "001", "clip_id": "001_k1"}
    if mode == "kandidaten":
        with pytest.raises(RatingError):
            save_rating(stage, "/bester", payload)
        save_rating(stage, "/note", payload | {"note": 2})
    save_rating(stage, "/bester", payload)
    assert hs.lies_csv(stage / "bewertung.csv")[0]["gewaehlt"] == "1"
    save_rating(stage, "/bester", payload | {"clip_id": ""})
    assert hs.lies_csv(stage / "bewertung.csv")[0]["gewaehlt"] == "0"


@pytest.mark.parametrize("defect", ["source", "metadata", "duplicate_manifest", "unknown_id"])
def test_source_rejection_never_writes(source_fixture, defect):
    from hpg_core.hearing_ratings import RatingError, load_session, save_rating
    stage = source_rating_session(source_fixture, "einzel")
    payload = {"pair_id": "001", "note": 4}
    if defect == "source":
        source_fixture[3].write_bytes(b"changed source")
    elif defect == "metadata":
        (stage / "merkmale.csv").write_bytes((stage / "merkmale.csv").read_bytes() + b"\n")
    elif defect == "duplicate_manifest":
        manifest = stage / "hearing_source_manifest.json"
        manifest.write_text('{"mode":"einzel","mode":"kandidaten"}')
    else:
        payload["pair_id"] = "missing"
    before = (stage / "bewertung.csv").read_bytes()
    with pytest.raises(RatingError):
        save_rating(stage, "/note", payload)
    if defect != "unknown_id":
        with pytest.raises(RatingError):
            load_session(stage)
    assert (stage / "bewertung.csv").read_bytes() == before


def test_source_dramaturgy_uses_its_validated_contract(source_fixture, monkeypatch):
    from hpg_core.hearing_ratings import load_session, save_rating
    stage = source_rating_session(source_fixture, "dramaturgie")
    def forbid_legacy(*args, **kwargs):
        pytest.fail("Source-Dramaturgie darf nicht durch den alten WAV-Vertrag laufen")
    monkeypatch.setattr(hs, "validiere_dramaturgie_satz", forbid_legacy)
    group = load_session(stage)["groups"][0]
    save_rating(stage, "/dramaturgie-note", {"variant_id": group["id"], "dimension": "energieverlauf", "note": 4})


@pytest.mark.parametrize("target", ["root", "hearing_source_manifest.json", "kandidaten_manifest.json"])
def test_source_symlink_escape_no_writes(source_fixture, tmp_path, target):
    from hpg_core.hearing_ratings import RatingError, load_session, save_rating
    stage = source_rating_session(source_fixture, "kandidaten")
    folder = stage
    if target == "root":
        link = tmp_path / "alias"
        destination = stage
        folder = link
    else:
        link = stage / target
        destination = tmp_path / target
        destination.write_bytes(link.read_bytes())
        link.unlink()
    try:
        link.symlink_to(destination, target_is_directory=target == "root")
    except OSError as exc:
        pytest.skip(f"Symlinks unavailable: {exc}")
    before = (stage / "bewertung.csv").read_bytes()
    with pytest.raises(RatingError):
        load_session(folder)
    with pytest.raises(RatingError):
        save_rating(folder, "/note", {"pair_id": "001", "clip_id": "001_k1", "note": 4})
    assert (stage / "bewertung.csv").read_bytes() == before


@pytest.mark.parametrize("mode", ["einzel", "kandidaten", "dreinoten", "dramaturgie"])
def test_source_save_does_not_rehash_originals(source_fixture, monkeypatch, mode):
    from hpg_core.hearing_ratings import load_session, save_rating
    stage = source_rating_session(source_fixture, mode)
    clip = load_session(stage)["groups"][0]["clips"][0]
    original_open = Path.open
    def no_original_read(path, *args, **kwargs):
        assert path.parent != source_fixture[3].parent, "Rating darf keine Originalinhalte lesen"
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", no_original_read)
    if mode == "dramaturgie":
        route, payload = "/transition-note", {"transition_id": clip["clip_id"], "dimension": "gesamt_note"}
    else:
        route, payload = "/note", {"pair_id": clip["pair_id"], "clip_id": clip["clip_id"]}
        if mode == "dreinoten":
            payload["dimension"] = "gesamt_note"
    save_rating(stage, route, payload | {"note": 4})


def test_source_full_load_rejects_same_size_corruption_structural_save_is_not_proof(source_fixture):
    from hpg_core.hearing_ratings import RatingError, load_session, save_rating
    stage = source_rating_session(source_fixture, "einzel")
    source = source_fixture[3]
    source.write_bytes(b"X" * source.stat().st_size)
    # Strukturpruefung ist bewusst kein Integritaetsbeleg fuer Audio-Inhalte.
    save_rating(stage, "/note", {"pair_id": "001", "note": 4})
    with pytest.raises(RatingError, match="veraendert"):
        load_session(stage)
