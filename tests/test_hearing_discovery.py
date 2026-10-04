"""Discovery liest nur explizit ausgewaehlte Satzmetadaten."""
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from hpg_core.hearing_discovery import SetSummary, discover_sets
from hpg_core.transition_renderer import TransitionClipSpec
from tools.hoertest_launcher import lese_fortschritt


def ratings(path, text):
    path.mkdir(parents=True, exist_ok=True)
    (path / "bewertung.csv").write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("text", [
    "pair_id,clip,bewertung\np,clips/p.wav,\nq,clips/q.wav,4\n",
    "pair_id,clip_id,note,gewaehlt,zeit\np,a,4,1,\np,b,3,0,\nq,c,,,\n",
    "pair_id,clip_id,track_note,technik_note,gesamt_note,gewaehlt,zeit\np,a,4,3,5,,\nq,b,4,,,,\n",
    "pair_id,clip,bewertung\n",
    "pair_id,clip,bewertung\np,clips/p.wav,9\n",
    "wrong,header\np,4\n",
])
def test_launcher_parity(tmp_path, text):
    folder = ratings(tmp_path / "set", text)
    before = (folder / "bewertung.csv").read_bytes()
    row, = discover_sets(tmp_path)
    assert (row.rated, row.total, row.type) == lese_fortschritt(folder)
    assert bool(row.errors) == (row.type == "fehler")
    assert (folder / "bewertung.csv").read_bytes() == before


def test_selected_root_and_immediate_children_only(tmp_path):
    ratings(tmp_path, "pair_id,clip,bewertung\np,x,\n")
    direct = ratings(tmp_path / "direct", "pair_id,clip,bewertung\np,x,5\n")
    ratings(tmp_path / "ordinary" / "nested", "pair_id,clip,bewertung\np,x,5\n")
    rows = discover_sets(tmp_path)
    assert [r.path for r in rows] == [tmp_path.resolve(), direct.resolve()]
    assert [r.status for r in rows] == ["new", "complete"]
    assert isinstance(rows, tuple) and isinstance(rows[0], SetSummary)


def test_missing_ratings_retained(tmp_path):
    folder = tmp_path / "broken"
    folder.mkdir()
    (folder / "kandidaten_manifest.json").write_text("{}")
    row, = discover_sets(tmp_path)
    assert row.status == "error" and row.errors


def source_manifest(folder, mode="einzel"):
    source_root = folder.parent / "offline-originals"
    a, b = str(source_root / "a.wav"), str(source_root / "b.mp3")
    data = dict(format="hpg_hearing_source_refs", format_version=1, mode=mode,
                status="prepared", source_roots=[str(source_root)],
                specs={"clips/p.wav": asdict(TransitionClipSpec(a, b, 20., 0., 8.))},
                sources={p: dict(path=p, root=str(source_root), size=1, sha256="0" * 64) for p in (a, b)},
                immutable_metadata={"merkmale.csv": dict(size=1, sha256="0" * 64)})
    (folder / "hearing_source_manifest.json").write_text(json.dumps(data))
    (folder / "merkmale.csv").write_text("metadata")
    return data


def test_source_metadata_only_offline_originals(tmp_path, monkeypatch):
    folder = ratings(tmp_path / "source", "pair_id,clip,bewertung\np,clips/p.wav,4\n")
    source_manifest(folder)
    import hpg_core.hearing_sources as sources
    monkeypatch.setattr(sources, "_fingerprint", lambda *a: pytest.fail("No hashing during discovery"))
    monkeypatch.setattr(sources, "load_source_session", lambda *a, **k: pytest.fail("No integrity loader"))
    row, = discover_sets(tmp_path)
    assert row.status == "complete" and row.type == "Standard"


@pytest.mark.parametrize("three_notes", [False, True])
def test_source_candidate_schemas_reuse_launcher_counts(tmp_path, monkeypatch, three_notes):
    from tests.test_hearing_sources import make_candidate_metadata
    from hpg_core.hearing_sources import SourceRenderSink, write_source_manifest
    import hpg_core.hearing_sources as sources
    originals = tmp_path / "originals"
    originals.mkdir()
    a, b = originals / "a.wav", originals / "b.mp3"
    a.write_bytes(b"synthetic A")
    b.write_bytes(b"synthetic B")
    folder = tmp_path / "set"
    folder.mkdir()
    sink = SourceRenderSink(folder, (originals,))
    make_candidate_metadata(folder, a, b, sink, three_notes=three_notes)
    write_source_manifest(folder, "kandidaten", sink)
    monkeypatch.setattr(sources, "_fingerprint", lambda *a: pytest.fail("No discovery hashing"))
    row, = discover_sets(folder)
    assert (row.rated, row.total, row.type) == lese_fortschritt(folder)
    assert row.type == ("Dreinoten-Kandidaten" if three_notes else "Standard-Kandidaten")
    assert row.status == "new" and not row.errors


def test_cancel_before_any_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "iterdir", lambda *a: pytest.fail("Cancellation before scanning"))
    def cancel():
        raise InterruptedError("cancel")
    with pytest.raises(InterruptedError): discover_sets(tmp_path, cancel)


@pytest.mark.parametrize("change", ["version", "format", "spec", "source", "nonfinite", "duplicate"])
def test_corrupt_source_manifest_retained(tmp_path, change):
    folder = ratings(tmp_path / "source", "pair_id,clip,bewertung\np,clips/p.wav,\n")
    data = source_manifest(folder)
    if change == "version": data["format_version"] = True
    if change == "format": data["format"] = "unknown"
    if change == "spec": data["specs"]["clips/p.wav"].pop("target_sr")
    if change == "source": data["sources"] = {}
    raw = json.dumps(data)
    if change == "nonfinite": raw = raw.replace('"mix_out_sec": 20.0', '"mix_out_sec": 1e999')
    if change == "duplicate": raw = raw.replace('"format_version": 1', '"format_version": 1, "format_version": 1')
    (folder / "hearing_source_manifest.json").write_text(raw)
    row, = discover_sets(tmp_path)
    assert row.status == "error" and row.errors


def test_cancel_propagates_without_partial_result(tmp_path):
    ratings(tmp_path / "set", "pair_id,clip,bewertung\np,x,\n")
    calls = 0
    def cancel():
        nonlocal calls
        calls += 1
        if calls == 3: raise InterruptedError("cancel")
    with pytest.raises(InterruptedError): discover_sets(tmp_path, cancel)


def test_root_invalid(tmp_path):
    with pytest.raises((ValueError, OSError)): discover_sets(tmp_path / "missing")


def test_junction_root_and_child_rejected_without_following(tmp_path, monkeypatch):
    child = tmp_path / "link"
    child.mkdir()
    original = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda p: p == child or original(p))
    row, = discover_sets(tmp_path)
    assert row.path == child and row.status == "error"
    with pytest.raises(ValueError): discover_sets(child)


def test_linked_root_ancestor_rejected(tmp_path, monkeypatch):
    child = tmp_path / "child"
    child.mkdir()
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda p: p == tmp_path or original(p))
    with pytest.raises(ValueError): discover_sets(child)


def test_metadata_link_rejected(tmp_path, monkeypatch):
    folder = ratings(tmp_path / "set", "pair_id,clip,bewertung\np,x,\n")
    original = Path.is_symlink
    target = folder / "bewertung.csv"
    monkeypatch.setattr(Path, "is_symlink", lambda p: p == target or original(p))
    row, = discover_sets(tmp_path)
    assert row.status == "error" and "link" in row.errors[0].lower()


@pytest.mark.parametrize("text,expected", [
    ("pair_id,clip_id,note,gewaehlt,zeit\np,a,4,,\np,b,3,,\n", (0, 1, "new")),
    ("pair_id,clip_id,note,gewaehlt,zeit\np,a,1,0,\np,b,1,0,\n", (1, 1, "complete")),
    ("pair_id,clip_id,note,gewaehlt,zeit\np,a,1,1,\np,b,1,0,\n", (0, 0, "error")),
    ("pair_id,clip,bewertung\np,x,4\nq,y,\n", (1, 2, "in_progress")),
    ("pair_id,clip,bewertung\np,x\n", (0, 0, "error")),
    ("pair_id,clip,bewertung\np,x,4,extra\n", (0, 0, "error")),
])
def test_resume_decisions_and_row_shape(tmp_path, text, expected):
    ratings(tmp_path / "set", text)
    row, = discover_sets(tmp_path)
    assert (row.rated, row.total, row.status) == expected


def test_unreadable_csv_retained(tmp_path, monkeypatch):
    import builtins
    folder = ratings(tmp_path / "set", "pair_id,clip,bewertung\np,x,\n")
    original = builtins.open
    def denied(path, *args, **kwargs):
        if Path(path) == folder / "bewertung.csv": raise PermissionError("denied")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", denied)
    row, = discover_sets(tmp_path)
    assert row.status == "error" and row.errors


def test_child_escape_retained(tmp_path, monkeypatch):
    child = ratings(tmp_path / "child", "pair_id,clip,bewertung\np,x,\n")
    original = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda p, **kw: tmp_path.parent / "outside" if p == child else original(p, **kw))
    row, = discover_sets(tmp_path)
    assert row.status == "error" and "escapes" in row.errors[0]


def test_priority_and_no_launcher_automatic_roots(tmp_path, monkeypatch):
    import tools.hoertest_launcher as launcher
    monkeypatch.setattr(launcher, "finde_hoertest_ordner", lambda: pytest.fail("No implicit roots"))
    for name in ("other", "psytrance", "psytrance-90-v3", "techno-prog-melodic"):
        ratings(tmp_path / name, "pair_id,clip,bewertung\np,x,\n")
    assert [r.path.name for r in discover_sets(tmp_path)] == ["techno-prog-melodic", "psytrance-90-v3", "psytrance", "other"]


@pytest.fixture
def dramaturgy_source(tmp_path, monkeypatch):
    # Reale Produzentenmetadaten, ausschliesslich synthetische Eingaben.
    from types import SimpleNamespace
    from tools import rate_transitions as rt
    from hpg_core.hearing_workflow import PrepareConfig, create_set
    from hpg_core.models import Track
    from hpg_core.playlist import TransitionPlan
    originals = tmp_path / "originals"
    originals.mkdir()
    tracks = []
    for index in range(12):
        path = originals / f"{index}.wav"
        path.write_bytes(b"synthetic")
        tracks.append(Track(str(path), path.name, duration=100., bpm=120., energy=index,
                            analysis_mode="librosa_full_or_tail"))
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda *_: tracks)
    def playlist(pool, strategy, **options):
        occurrences = [SimpleNamespace(occurrence_id=("fixture", i)) for i in range(len(pool))]
        recommendations = [SimpleNamespace(index=i, from_occurrence_id=occurrences[i].occurrence_id,
            to_occurrence_id=occurrences[i+1].occurrence_id,
            plan=TransitionPlan(20., 0., 20., 28., 8., "smooth_blend")) for i in range(len(pool)-1)]
        return SimpleNamespace(tracks=pool, occurrences=occurrences, recommendations=recommendations,
            scoring_context_dict=lambda: options["scoring_context"],
            candidate_choice_snapshot_dict=lambda: options["candidate_choice_snapshot"])
    monkeypatch.setattr(rt, "generate_playlist_result", playlist)
    monkeypatch.setattr(rt, "_rendere_atomar", lambda *a, **k: pytest.fail("No audio render"))
    cache = tmp_path / "synthetic-cache.db"
    cache.write_bytes(b"not a database")
    result = create_set(PrepareConfig("dramaturgie", tmp_path / "set", cache,
        sequence_tracks=12, transitions_per_variant=4, source_roots=(originals,)))
    return result.output_dir


def test_source_dramaturgy_progress_and_legacy_parity(dramaturgy_source, monkeypatch):
    folder = dramaturgy_source
    import hpg_core.hearing_sources as sources
    monkeypatch.setattr(sources, "_fingerprint", lambda *a: pytest.fail("Discovery must not hash"))
    # Resume: genau eine Transition und eine Gesamtbewertung abgeschlossen.
    transition = folder / "bewertung.csv"
    raw = transition.read_text()
    lines = raw.splitlines()
    cells = lines[1].split(",")
    cells[2:5] = ["4", "3", "5"]
    lines[1] = ",".join(cells)
    transition.write_text("\n".join(lines) + "\n")
    overall = folder / "dramaturgie_bewertung.csv"
    lines = overall.read_text().splitlines()
    cells = lines[1].split(",")
    cells[1:5] = ["4"] * 4
    lines[1] = ",".join(cells)
    overall.write_text("\n".join(lines) + "\n")
    row, = discover_sets(folder)
    assert row.type == "Dramaturgie" and row.rated == 2 and row.status == "in_progress"
    # Nur synthetische Metadaten in alten WAV-Vertrag umstellen; keine WAVs.
    manifest_file = folder / "dramaturgie_manifest.json"
    data = json.loads(manifest_file.read_text())
    for variant in data["variants"]:
        for entry in variant["transitions"]:
            entry["clip"] = dict(path=entry["clip"]["path"], sha256="0" * 64, size_bytes=1)
    manifest_file.write_text(json.dumps(data))
    (folder / "hearing_source_manifest.json").unlink()
    legacy, = discover_sets(folder)
    assert (legacy.rated, legacy.total, legacy.type) == lese_fortschritt(folder)
    assert (legacy.rated, legacy.total, legacy.type) == (row.rated, row.total, row.type)
    assert not list(folder.rglob("*.wav"))


def test_corrupt_dramaturgy_retained(dramaturgy_source):
    folder = dramaturgy_source
    manifest = folder / "dramaturgie_manifest.json"
    data = json.loads(manifest.read_text())
    data["variants"][0]["transitions"][0]["clip"]["representation"] = "wav"
    manifest.write_text(json.dumps(data))
    row, = discover_sets(folder)
    assert row.status == "error" and row.errors
