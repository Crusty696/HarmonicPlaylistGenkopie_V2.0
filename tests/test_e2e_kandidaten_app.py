"""Fail-closed CLI-Grenzen des Kandidaten-App-E2E-Tools."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "tools" / "e2e_kandidaten_app.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_verlangt_expliziten_cache_vor_jedem_write(tmp_path):
    out = tmp_path / "neu"
    result = _run("--out", str(out))
    assert result.returncode == 2
    assert "--cache" in result.stderr
    assert not out.exists()


def test_cli_lehnt_vorhandenes_out_byteidentisch_ab(tmp_path):
    out = tmp_path / "vorhanden"
    out.mkdir()
    datei = out / "bleibt.txt"
    vorher = b"nicht anfassen\r\n"
    datei.write_bytes(vorher)
    cache = tmp_path / "fake.db"
    cache.write_bytes(b"kein SQLite noetig")

    result = _run("--out", str(out), "--cache", str(cache))

    assert result.returncode == 2
    assert "frisch" in result.stderr
    assert datei.read_bytes() == vorher
    assert not list(tmp_path.glob(".vorhanden.staging-*"))


def test_ungueltiger_cache_stoppt_vor_parent_und_staging(tmp_path):
    cache = tmp_path / "kaputt.db"
    cache.write_bytes(b"kein SQLite")
    parent = tmp_path / "noch-nicht-vorhanden"
    out = parent / "satz"

    result = _run("--out", str(out), "--cache", str(cache))

    assert result.returncode != 0
    assert not parent.exists()
    assert not out.exists()


def test_pending_wal_stoppt_vor_parent_und_staging(tmp_path):
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"SQLite")
    Path(f"{cache}-wal").write_bytes(b"pending")
    parent = tmp_path / "noch-nicht-vorhanden"
    out = parent / "satz"

    result = _run("--out", str(out), "--cache", str(cache))

    assert result.returncode != 0
    assert "WAL" in result.stderr
    assert not parent.exists()
    assert not out.exists()


def test_neues_wal_waehrend_lauf_verhindert_publish_und_raeumt_staging(tmp_path):
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"stabil")
    out = tmp_path / "satz"
    bootstrap = tmp_path / "bootstrap.py"
    bootstrap.write_text(
        f'''import os, runpy, shutil, sys\n
sys.path.insert(0, {str(ROOT)!r})\n
from pathlib import Path\n
from types import SimpleNamespace as NS\n
import numpy as np\n
import soundfile as sf\n
from tools import rate_transitions as rt\n
from hpg_core import candidate_choices as cc, playlist as pl, tolerances\n
from hpg_core import transition_renderer as tr\n
from hpg_core.exporters import rekordbox_xml_exporter as rx\n
cache = Path({str(cache)!r})\n
track_a = NS(filePath=str(cache.parent / "a.wav"))\n
track_b = NS(filePath=str(cache.parent / "b.wav"))\n
Path(track_a.filePath).write_bytes(b"a")\n
Path(track_b.filePath).write_bytes(b"b")\n
plan = NS(mix_out_a=1.0, mix_in_b=2.0, overlap=0.01, transition_type="pro_eq_swap")\n
k1 = {{"t_out": 1.0, "t_in": 2.0, "blend_bars": 8, "flags": {{}}}}\n
k2 = {{"t_out": 1.5, "t_in": 2.5, "blend_bars": 8, "flags": {{}}}}\n
choice = {{}}\n
forgotten = {{"value": False}}\n
override_written = {{"value": False}}\n
def make_rec():\n
    if choice:\n
        chosen = dict(k2); chosen["flags"] = {{"gespeicherte_wahl": True}}\n
        active_plan = NS(mix_out_a=1.5, mix_in_b=2.5, overlap=0.01, transition_type="pro_eq_swap")\n
        candidates = [chosen, k1]\n
    elif Path(os.environ["HPG_TOLERANCES_FILE"]).exists():\n
        active_plan = NS(mix_out_a=1.5, mix_in_b=2.5, overlap=0.01, transition_type="pro_eq_swap")\n
        candidates = [k2, k1]\n
    else:\n
        active_plan = plan; candidates = [k1, k2]\n
    return NS(index=0, kandidat_aktiv=1, kandidat_konsistent=True, kandidaten=candidates, plan=active_plan, from_track=track_a, to_track=track_b)\n
rt.lade_tracks_aus_cache = lambda _path: [track_a, track_b]\n
rt._algorithm_build_fingerprint = lambda: {{"sha256": "a" * 64}}\n
pl.reset_pair_candidate_cache = lambda: None\n
pl.generate_playlist = lambda *_args, **_kwargs: [track_a, track_b]\n
pl.compute_adjacent_transition_metrics = lambda *_args, **_kwargs: {{}}\n
pl.compute_transition_recommendations = lambda *_args, **_kwargs: [make_rec()]\n
cc.reset_cache = lambda: None\n
cc.merke = lambda *_args, **_kwargs: choice.update(ok=True)\n
cc.hole = lambda *_args, **_kwargs: ({{"ok": True}} if choice else None)\n
cc.vergiss = lambda *_args, **_kwargs: choice.clear()\n
tolerances.reset_cache = lambda: None\n
tolerances.write_override_kandidaten = lambda _data: Path(os.environ["HPG_TOLERANCES_FILE"]).write_text("{{}}", encoding="utf-8")\n
tolerances.get_tolerances = lambda _genre: {{"kandidaten_loudness_weight": 1.0}}\n
tr.TransitionClipSpec.from_plan = classmethod(lambda cls, plan, *_args: NS(pre_roll_sec=0.01, crossfade_sec=0.01, post_roll_sec=0.01, marker=plan.mix_out_a))\n
def render(_spec, path):\n
    sf.write(path, np.ones((300, 2), dtype=np.float32) * (0.01 + _spec.marker * 0.001), 10000)\n
    return path\n
tr.render_transition_clip = render\n
class Exporter:\n
    def export(self, _liste, path, _name, transitions=None):\n
        xml = ('<DJ_PLAYLISTS><COLLECTION>'\n
               '<TRACK Location="' + track_a.filePath + '">'\n
               '<POSITION_MARK Name="MIX OUT" Start="1.0" />'\n
               '<POSITION_MARK Name="HPG K1 OUT" Start="1.0" /></TRACK>'\n
               '<TRACK Location="' + track_b.filePath + '">'\n
               '<POSITION_MARK Name="MIX IN" Start="2.0" />'\n
               '<POSITION_MARK Name="HPG K1 IN" Start="2.0" /></TRACK>'\n
               '</COLLECTION></DJ_PLAYLISTS>')\n
        Path(path).write_text(xml, encoding="utf-8")\n
        Path(f"{{cache}}-wal").write_bytes(b"entstand waehrend lauf")\n
        return NS(status="success", tracks_written=2, cues_written=4, errors=[])\n
rx.RekordboxXMLExporter = Exporter\n
sys.argv = [{str(SCRIPT)!r}, "--out", {str(out)!r}, "--cache", str(cache)]\n
runpy.run_path({str(SCRIPT)!r}, run_name="__main__")\n
''',
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(bootstrap)], cwd=ROOT,
        capture_output=True, text=True, check=False,
    )

    assert result.returncode != 0
    assert "WAL" in result.stderr
    assert not out.exists()
    assert not list(tmp_path.glob(".satz.staging-*"))


def test_tool_nutzt_gemeinsamen_strikten_loader_ohne_impliziten_cache():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "lade_tracks_aus_cache(str(cache))" in source
    assert "_cache_family_fingerprint(cache)" in source
    assert "_algorithm_build_fingerprint()" in source
    assert source.rfind("_reject_pending_wal(cache)") < source.rfind("os.rename(STAGING, ZIEL)")
    assert "caching.CACHE_FILE" not in source
    assert "sqlite3.connect" not in source


def _run_scenario(tmp_path: Path, scenario: str):
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"stabil")
    out = tmp_path / "ausgabe" / "satz"
    bootstrap = tmp_path / f"bootstrap-{scenario}.py"
    bootstrap.write_text(
        f'''import os, runpy, shutil, sys\n
sys.path.insert(0, {str(ROOT)!r})\n
from pathlib import Path\n
from types import SimpleNamespace as NS\n
import numpy as np\n
import soundfile as sf\n
from tools import rate_transitions as rt\n
from hpg_core import candidate_choices as cc, playlist as pl, tolerances\n
from hpg_core import transition_renderer as tr\n
from hpg_core.exporters import rekordbox_xml_exporter as rx\n
scenario = {scenario!r}\n
cache = Path({str(cache)!r})\n
track_a = NS(filePath=str(cache.parent / "a.wav"))\n
track_b = NS(filePath=str(cache.parent / "b.wav"))\n
Path(track_a.filePath).write_bytes(b"a")\n
Path(track_b.filePath).write_bytes(b"b")\n
k1 = {{"t_out": 1.0, "t_in": 2.0, "blend_bars": 8, "flags": {{}}}}\n
k2 = {{"t_out": 1.5, "t_in": 2.5, "blend_bars": 8, "flags": {{}}}}\n
choice = {{}}\n
forgotten = {{"value": False}}\n
override_written = {{"value": False}}\n
def make_plan(t_out=1.0, t_in=2.0, overlap=0.01):\n
    return NS(mix_out_a=t_out, mix_in_b=t_in, overlap=overlap, transition_type="pro_eq_swap")\n
def make_rec():\n
    if scenario == "no_candidates":\n
        return NS(index=0, kandidat_aktiv=0, kandidat_konsistent=True, kandidaten=[], plan=make_plan(), from_track=track_a, to_track=track_b)\n
    if scenario == "one_candidate":\n
        return NS(index=0, kandidat_aktiv=1, kandidat_konsistent=True, kandidaten=[k1], plan=make_plan(), from_track=track_a, to_track=track_b)\n
    candidates = [k1, (dict(k1) if scenario == "no_alternative" else k2)]\n
    overlap = {{"zero_overlap": 0.0, "negative_overlap": -1.0, "nan_overlap": float("nan"), "inf_overlap": float("inf")}}.get(scenario, 0.01)\n
    active_plan = None if scenario == "missing_plan" else make_plan(overlap=overlap)\n
    active_rank = 3 if scenario == "wrong_rank" else (None if scenario == "wrong_rank_type" else 1)\n
    if choice:\n
        chosen = dict(k2); chosen["flags"] = ({{}} if scenario == "missing_choice_flag" else {{"gespeicherte_wahl": True}})\n
        candidates = [chosen, k1]\n
        active_plan = make_plan() if scenario == "plan_not_follow" else make_plan(1.5, 2.5)\n
        active_rank = 1\n
    elif forgotten["value"] and scenario in ("reset_flag", "reset_rank"):\n
        flagged = dict(k1); flagged["flags"] = ({{"gespeicherte_wahl": True}} if scenario == "reset_flag" else {{}})\n
        candidates = [flagged, k2]; active_plan = make_plan(); active_rank = (2 if scenario == "reset_rank" else 1)\n
    elif Path(os.environ["HPG_TOLERANCES_FILE"]).exists() and scenario != "no_rank_change":\n
        candidates = [k2, k1]; active_plan = make_plan(1.5, 2.5); active_rank = 1\n
    elif override_written["value"] and scenario == "incomplete_regler_reset":\n
        candidates = [k2, k1]; active_plan = make_plan(1.5, 2.5); active_rank = 1\n
    return NS(index=0, kandidat_aktiv=active_rank, kandidat_konsistent=True, kandidaten=candidates, plan=active_plan, from_track=track_a, to_track=track_b)\n
rt.lade_tracks_aus_cache = lambda _path: ([] if scenario == "no_tracks" else [track_a, track_b])\n
rt._algorithm_build_fingerprint = lambda: {{"sha256": "a" * 64}}\n
pl.reset_pair_candidate_cache = lambda: None\n
pl.generate_playlist = lambda *_args, **_kwargs: [track_a, track_b]\n
pl.compute_adjacent_transition_metrics = lambda *_args, **_kwargs: {{}}\n
pl.compute_transition_recommendations = lambda *_args, **_kwargs: ([] if scenario == "no_recommendations" else [make_rec()])\n
cc.reset_cache = lambda: None\n
def remember(*_args, **_kwargs):\n
    choice.update(ok=True); forgotten["value"] = False\n
cc.merke = remember\n
cc.hole = lambda *_args, **_kwargs: (None if scenario == "not_persisted" else ({{"ok": True}} if choice else None))\n
def forget(*_args, **_kwargs):\n
    forgotten["value"] = True\n
    if scenario != "reset_persisted": choice.clear()\n
cc.vergiss = forget\n
tolerances.reset_cache = lambda: None\n
def write_override(_data):\n
    override_written["value"] = True\n
    return Path(os.environ["HPG_TOLERANCES_FILE"]).write_text("{{}}", encoding="utf-8")\n
tolerances.write_override_kandidaten = write_override\n
tolerances.get_tolerances = lambda _genre: {{"kandidaten_loudness_weight": 1.0}}\n
tr.TransitionClipSpec.from_plan = classmethod(lambda cls, plan, *_args: NS(pre_roll_sec=0.01, crossfade_sec=0.01, post_roll_sec=0.01, marker=plan.mix_out_a))\n
def render(_spec, path):\n
    if scenario in ("render_error", "cleanup_error"):\n
        Path(path).write_bytes(b"teil")\n
        raise RuntimeError("Render absichtlich fehlgeschlagen")\n
    amplitude = 0.01 if scenario == "identical_audio" else 0.01 + _spec.marker * 0.001\n
    sf.write(path, np.ones((300, 2), dtype=np.float32) * amplitude, 10000)\n
    return path\n
tr.render_transition_clip = render\n
class Exporter:\n
    def export(self, _liste, path, _name, transitions=None):\n
        if scenario == "export_error":\n
            Path(path).write_text("<teil>", encoding="utf-8")\n
            raise RuntimeError("Export absichtlich fehlgeschlagen")\n
        out_start = "ungueltig" if scenario == "invalid_cue_start" else ("9.0" if scenario == "wrong_mix_cue" else "1.0")\n
        out_mark = "" if scenario == "missing_mix_cue" else '<POSITION_MARK Name="MIX OUT" Start="' + out_start + '" />'\n
        in_mark = "" if scenario == "missing_mix_cue" else '<POSITION_MARK Name="MIX IN" Start="2.0" />'\n
        extra_out = '<POSITION_MARK Name="MIX OUT" Start="9.0" />' if scenario == "duplicate_mix_out" else ""\n
        extra_in = '<POSITION_MARK Name="MIX IN" Start="9.0" />' if scenario == "duplicate_mix_in" else ""\n
        hpg_out = "" if scenario == "missing_hpg_cues" else '<POSITION_MARK Name="HPG K1 OUT" Start="1.0" />'\n
        hpg_in = "" if scenario == "missing_hpg_cues" else '<POSITION_MARK Name="HPG K1 IN" Start="2.0" />'\n
        xml = ('<DJ_PLAYLISTS><COLLECTION>'\n
               '<TRACK Location="' + track_a.filePath + '">'\n
               + out_mark + extra_out + hpg_out + '</TRACK>'\n
               '<TRACK Location="' + track_b.filePath + '">'\n
               + in_mark + extra_in + hpg_in + '</TRACK>'\n
               '</COLLECTION></DJ_PLAYLISTS>')\n
        Path(path).write_text(xml, encoding="utf-8")\n
        if scenario == "partial_export":\n
            return NS(status="partial", tracks_written=1, cues_written=2, errors=["Teil-Export"])\n
        if scenario == "success_with_errors":\n
            return NS(status="success", tracks_written=2, cues_written=4, errors=["Fehler trotz success"])\n
        if scenario == "incomplete_report":\n
            return NS(status="success")\n
        return NS(status="success", tracks_written=2, cues_written=4, errors=[])\n
rx.RekordboxXMLExporter = Exporter\n
if scenario == "cleanup_error":\n
    real_rmtree = shutil.rmtree\n
    cleanup_calls = {{"count": 0}}\n
    def flaky_rmtree(path):\n
        cleanup_calls["count"] += 1\n
        if cleanup_calls["count"] == 1:\n
            raise PermissionError("Aufraeumen absichtlich einmal blockiert")\n
        return real_rmtree(path)\n
    shutil.rmtree = flaky_rmtree\n
sys.argv = [{str(SCRIPT)!r}, "--out", {str(out)!r}, "--cache", str(cache)]\n
runpy.run_path({str(SCRIPT)!r}, run_name="__main__")\n
''',
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(bootstrap)], cwd=ROOT,
        capture_output=True, text=True, check=False,
    )
    return result, out


def test_happy_path_publiziert_erst_vollstaendiges_ergebnis(tmp_path):
    result, out = _run_scenario(tmp_path, "happy")

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    assert out.is_dir()
    assert (out / "preview_aktiv.wav").is_file()
    assert (out / "preview_wahl.wav").is_file()
    assert (out / "export.xml").is_file()
    assert (out / "e2e_ergebnis.json").is_file()
    assert not list(out.parent.glob(".satz.staging-*"))


@pytest.mark.parametrize(
    ("scenario", "meldung"),
    [
        ("no_tracks", "Mindestens zwei Tracks"),
        ("no_recommendations", "Keine Uebergangsempfehlung"),
        ("no_candidates", "Keine Empfehlung mit aktivem Kandidaten"),
        ("one_candidate", "mindestens zwei Varianten"),
        ("missing_plan", "TransitionPlan"),
        ("zero_overlap", "positivem Overlap"),
        ("negative_overlap", "positivem Overlap"),
        ("nan_overlap", "positivem Overlap"),
        ("inf_overlap", "positivem Overlap"),
        ("wrong_rank", "Kandidatenrang 3"),
        ("wrong_rank_type", "Kandidatenrang muss ganzzahlig sein"),
        ("no_alternative", "Kein zeitlich alternativer Kandidat"),
    ],
)
def test_unzureichende_daten_stoppen_kontrolliert_vor_publish(
    tmp_path, scenario, meldung,
):
    result, out = _run_scenario(tmp_path, scenario)
    assert result.returncode != 0, scenario
    assert meldung in result.stderr, (scenario, result.stderr)
    assert "Traceback" not in result.stderr, scenario
    assert not out.exists(), scenario
    assert not list(out.parent.glob(".satz.staging-*")), scenario


@pytest.mark.parametrize(
    ("scenario", "meldung"),
    [
        ("render_error", "Preview Paar 0 fehlgeschlagen"),
        ("identical_audio", "Preview folgt der anderen Wahl nicht"),
        ("not_persisted", "Wahl wurde nicht persistiert"),
        ("missing_choice_flag", "gespeicherte Wahl ist nicht markiert"),
        ("plan_not_follow", "TransitionPlan folgt der Wahl nicht"),
        ("reset_persisted", "vergessene Wahl ist weiterhin persistiert"),
        ("reset_flag", "Flag gespeicherte_wahl blieb"),
        ("reset_rank", "aktiven Rang nicht wieder her"),
        ("export_error", "Rekordbox-Export fehlgeschlagen"),
        ("partial_export", "Exportstatus"),
        ("success_with_errors", "Export meldete Fehler"),
        ("missing_mix_cue", "genau ein MIX OUT erwartet, gefunden: 0"),
        ("wrong_mix_cue", "MIX OUT entspricht nicht"),
        ("duplicate_mix_out", "genau ein MIX OUT erwartet, gefunden: 2"),
        ("duplicate_mix_in", "genau ein MIX IN erwartet, gefunden: 2"),
        ("missing_hpg_cues", "keine HPG-K-Cues"),
        ("invalid_cue_start", "Rekordbox-Cue-Pruefung MIX OUT fehlgeschlagen"),
        ("incomplete_report", "Rekordbox-Report-Pruefung fehlgeschlagen"),
        ("no_rank_change", "aenderte keinen Rang 1"),
        ("incomplete_regler_reset", "Regler-Reset stellte Rangfolge nicht"),
        ("cleanup_error", "E2E-Aufraeumen fehlgeschlagen"),
    ],
)
def test_laufzeitfehler_und_fail_open_ergebnisse_werden_nicht_publiziert(
    tmp_path, scenario, meldung,
):
    result, out = _run_scenario(tmp_path, scenario)
    assert result.returncode != 0, scenario
    assert meldung in result.stderr, (scenario, result.stderr)
    assert "Traceback" not in result.stderr, scenario
    assert not out.exists(), scenario
    assert not list(out.parent.glob(".satz.staging-*")), scenario
