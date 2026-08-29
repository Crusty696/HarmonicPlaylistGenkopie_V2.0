"""Tests fuer die Persistenz der Kandidaten-Wahl je Paar (Teil 4)."""
import json
import math
import multiprocessing
import os
from unittest.mock import Mock

import pytest

from hpg_core import candidate_choices as cc
from hpg_core.config import (
    MAX_TRANSITION_OVERLAP_SECONDS,
    MIN_TRANSITION_BARS,
    SECURITY_MAX_TRACK_DURATION,
)


def _prozess_schreibt_wahl(datei, start, ergebnis, suffix):
    os.environ["HPG_CANDIDATE_CHOICES_FILE"] = str(datei)
    from hpg_core import candidate_choices

    candidate_choices.reset_cache()
    start.wait(10)
    try:
        candidate_choices.merke(
            f"a-{suffix}.mp3",
            f"b-{suffix}.mp3",
            t_out=10.0 + suffix,
            t_in=2.0,
            blend_bars=8,
        )
        ergebnis.put(None)
    except Exception as exc:  # pragma: no cover - Fehler wird im Elternprozess gemeldet
        ergebnis.put(repr(exc))


@pytest.fixture(autouse=True)
def _datei(monkeypatch, tmp_path):
    monkeypatch.setenv("HPG_CANDIDATE_CHOICES_FILE", str(tmp_path / "choices.json"))
    cc.reset_cache()
    yield
    cc.reset_cache()


def test_schluessel_ist_pfadnormiert_und_gerichtet():
    k1 = cc.schluessel("C:/Musik/A.mp3", "c:\\musik\\b.mp3")
    k2 = cc.schluessel("c:\\MUSIK\\a.mp3", "C:/Musik/B.mp3")
    assert k1 == k2
    assert cc.schluessel("a.mp3", "b.mp3") != cc.schluessel("b.mp3", "a.mp3")


def test_merke_und_hole_roundtrip(tmp_path):
    assert cc.hole("a.mp3", "b.mp3") is None
    cc.merke("a.mp3", "b.mp3", t_out=160.0, t_in=80.0, blend_bars=16)
    w = cc.hole("a.mp3", "b.mp3")
    assert w["t_out"] == 160.0 and w["t_in"] == 80.0 and w["blend_bars"] == 16 and w["zeit"]
    daten = json.loads((tmp_path / "choices.json").read_text(encoding="utf-8"))
    assert len(daten) == 1
    cc.reset_cache()
    assert cc.hole("a.mp3", "b.mp3")["t_out"] == 160.0        # neu geladen


def test_neue_wahl_speichert_vollstaendigen_audit_snapshot():
    cc.merke(
        "a.mp3", "b.mp3",
        t_out=160.0, t_in=80.0, blend_bars=16,
        bpm_a=138.0, bpm_b=139.0, overlap_sec=27.826,
    )

    wahl = cc.hole("a.mp3", "b.mp3")

    assert wahl["version"] == 2
    assert wahl["bpm_a"] == 138.0
    assert wahl["bpm_b"] == 139.0
    assert wahl["overlap_sec"] == 27.826


def test_auditfelder_muessen_gemeinsam_gesetzt_werden():
    with pytest.raises(ValueError, match="gemeinsam"):
        cc.merke(
            "a.mp3", "b.mp3",
            t_out=1.0, t_in=2.0, blend_bars=8,
            bpm_a=138.0,
        )


@pytest.mark.parametrize(
    "overlap",
    [True, False, 0.0, -0.01, math.nan, math.inf,
     MAX_TRANSITION_OVERLAP_SECONDS + 0.01],
)
def test_overlap_sec_muss_im_harten_rendererintervall_liegen(overlap):
    with pytest.raises(ValueError, match="overlap_sec"):
        cc.merke(
            "a.mp3", "b.mp3",
            t_out=10.0, t_in=2.0, blend_bars=8,
            bpm_a=138.0, bpm_b=139.0, overlap_sec=overlap,
        )


def test_overlap_sec_akzeptiert_exakte_obergrenze():
    cc.merke(
        "a.mp3", "b.mp3",
        t_out=10.0, t_in=2.0, blend_bars=8,
        bpm_a=138.0, bpm_b=139.0,
        overlap_sec=MAX_TRANSITION_OVERLAP_SECONDS,
    )
    assert cc.hole("a.mp3", "b.mp3")["overlap_sec"] == 64.0


def test_zu_grosses_overlap_im_store_blockiert_snapshot_und_mutation_bytegleich(
    tmp_path,
):
    datei = tmp_path / "choices.json"
    key = cc.schluessel("a.mp3", "b.mp3")
    datei.write_text(
        json.dumps({
            key: {
                "t_out": 10.0,
                "t_in": 2.0,
                "blend_bars": 8,
                "version": 2,
                "bpm_a": 138.0,
                "bpm_b": 139.0,
                "overlap_sec": MAX_TRANSITION_OVERLAP_SECONDS + 0.01,
            }
        }),
        encoding="utf-8",
    )
    vorher = datei.read_bytes()

    assert cc.hole("a.mp3", "b.mp3") is None
    with pytest.raises(ValueError, match="overlap_sec"):
        cc.snapshot()
    with pytest.raises(ValueError, match="overlap_sec"):
        cc.merke(
            "a.mp3", "c.mp3", t_out=20.0, t_in=3.0, blend_bars=8
        )
    assert datei.read_bytes() == vorher


def test_echter_nichtleerer_snapshot_durchlaeuft_generate_playlist_result():
    cc.merke(
        "a.mp3", "b.mp3",
        t_out=10.0, t_in=2.0, blend_bars=8,
        bpm_a=138.0, bpm_b=139.0, overlap_sec=16.0,
    )
    from hpg_core.playlist import generate_playlist_result

    result = generate_playlist_result([], "Warm-Up")

    assert result.mode == "Warm-Up"
    assert result.tracks == ()


def test_snapshot_ist_tief_getrennt_und_deepcopy_kompatibel(tmp_path):
    key = cc.schluessel("a.mp3", "b.mp3")
    (tmp_path / "choices.json").write_text(
        json.dumps({
            key: {
                "t_out": 1.0, "t_in": 2.0, "blend_bars": 8,
                "extra": {"liste": [1, 2]},
            }
        }),
        encoding="utf-8",
    )
    cc.reset_cache()

    stand = cc.snapshot()
    kopie = __import__("copy").deepcopy(stand)
    stand[key]["t_out"] = 3.0
    stand[key]["extra"]["liste"][0] = 9
    kopie[key]["extra"]["liste"].append(3)

    frisch = cc.snapshot()
    assert frisch[key]["t_out"] == 1.0
    assert frisch[key]["extra"]["liste"] == [1, 2]


def test_exakter_restore_stellt_auditfelder_oder_nichtexistenz_wieder_her():
    erster_commit = cc.merke(
        "a.mp3", "b.mp3",
        t_out=1.0, t_in=2.0, blend_bars=8,
        bpm_a=138.0, bpm_b=139.0, overlap_sec=13.913,
    )
    vorher = cc.hole("a.mp3", "b.mp3")
    zweiter_commit = cc.merke(
        "a.mp3", "b.mp3",
        t_out=3.0, t_in=4.0, blend_bars=16,
        bpm_a=140.0, bpm_b=141.0, overlap_sec=27.429,
    )

    cc.stelle_wieder_her(zweiter_commit)
    assert cc.hole("a.mp3", "b.mp3") == vorher

    cc.stelle_wieder_her(erster_commit)
    assert cc.hole("a.mp3", "b.mp3") is None


def test_vergiss_entfernt_nur_das_paar():
    cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=8)
    cc.merke("a.mp3", "c.mp3", t_out=3.0, t_in=4.0, blend_bars=8)
    cc.vergiss("a.mp3", "b.mp3")
    assert cc.hole("a.mp3", "b.mp3") is None and cc.hole("a.mp3", "c.mp3")["t_out"] == 3.0


def test_kaputte_datei_ist_nur_fuer_anzeige_leer_und_wird_nie_ueberschrieben(tmp_path):
    datei = tmp_path / "choices.json"
    datei.write_text("{kaputt", encoding="utf-8")
    vorher = datei.read_bytes()
    cc.reset_cache()
    assert cc.hole("a.mp3", "b.mp3") is None
    with pytest.raises(ValueError):
        cc.snapshot()
    with pytest.raises(ValueError):
        cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=8)
    with pytest.raises(ValueError):
        cc.vergiss("a.mp3", "b.mp3")
    assert datei.read_bytes() == vorher


@pytest.mark.parametrize(
    ("feld", "wert"),
    [
        ("t_out", True),
        ("t_in", False),
        ("t_out", float("nan")),
        ("t_in", float("inf")),
        ("t_out", -0.01),
        ("t_in", SECURITY_MAX_TRACK_DURATION + 0.01),
    ],
)
def test_merke_weist_ungueltige_zeiten_ohne_datei_oder_cache_aenderung_ab(
    tmp_path, feld, wert
):
    cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=8)
    datei = tmp_path / "choices.json"
    vorher_datei = datei.read_bytes()
    vorher_cache = cc.hole("a.mp3", "b.mp3")
    kwargs = {"t_out": 3.0, "t_in": 4.0, "blend_bars": 8, feld: wert}

    with pytest.raises(ValueError):
        cc.merke("a.mp3", "b.mp3", **kwargs)

    assert datei.read_bytes() == vorher_datei
    assert cc.hole("a.mp3", "b.mp3") == vorher_cache


def test_merke_akzeptiert_exakte_zeitgrenzen():
    cc.merke(
        "a.mp3", "b.mp3",
        t_out=SECURITY_MAX_TRACK_DURATION, t_in=0,
        blend_bars=MIN_TRANSITION_BARS,
    )
    wahl = cc.hole("a.mp3", "b.mp3")
    assert wahl["t_out"] == float(SECURITY_MAX_TRACK_DURATION)
    assert wahl["t_in"] == 0.0


@pytest.mark.parametrize("blend_bars", [True, 8.0, MIN_TRANSITION_BARS - 1])
def test_merke_weist_ungueltigen_blend_typ_und_untergrenze_ab(blend_bars):
    with pytest.raises(ValueError, match="blend_bars"):
        cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=blend_bars)


def test_blend_obergrenze_kommt_aus_genre_profilen():
    max_bars = max(
        bar
        for profile in cc.GENRE_MIX_PROFILES.values()
        for bar in profile.transition_bars
    )
    cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=max_bars)
    with pytest.raises(ValueError, match=str(max_bars)):
        cc.merke("a.mp3", "c.mp3", t_out=1.0, t_in=2.0, blend_bars=max_bars + 1)


def test_laden_isoliert_ungueltige_eintraege_und_behaelt_extras_tief(tmp_path, caplog):
    key_ok = cc.schluessel("a.mp3", "b.mp3")
    key_bad = cc.schluessel("a.mp3", "c.mp3")
    (tmp_path / "choices.json").write_text(
        json.dumps({
            key_ok: {
                "t_out": 1, "t_in": 2.0, "blend_bars": 8,
                "zeit": "2026-08-26T12:00:00", "extra": {"liste": [1, 2]},
            },
            key_bad: {"t_out": math.nan, "t_in": 2.0, "blend_bars": 8},
            "fehlend": {"t_out": 1.0, "t_in": 2.0},
            "zeit-leer": {"t_out": 1.0, "t_in": 2.0, "blend_bars": 8, "zeit": " "},
        }),
        encoding="utf-8",
    )
    cc.reset_cache()

    wahl = cc.hole("a.mp3", "b.mp3")
    wahl["extra"]["liste"].append(3)

    assert cc.hole("a.mp3", "b.mp3")["extra"] == {"liste": [1, 2]}
    assert cc.hole("a.mp3", "c.mp3") is None
    assert "ungueltig" in caplog.text


def test_teilungueltige_datei_blockiert_snapshot_und_mutationen_ohne_datenverlust(
    tmp_path,
):
    key_ok = cc.schluessel("a.mp3", "b.mp3")
    datei = tmp_path / "choices.json"
    datei.write_text(
        json.dumps({
            key_ok: {"t_out": 1.0, "t_in": 2.0, "blend_bars": 8},
            "defekt": {"t_out": 3.0, "t_in": 4.0},
        }),
        encoding="utf-8",
    )
    vorher = datei.read_bytes()

    assert cc.hole("a.mp3", "b.mp3")["t_out"] == 1.0
    with pytest.raises(ValueError, match="defekt"):
        cc.snapshot()
    with pytest.raises(ValueError, match="defekt"):
        cc.merke("a.mp3", "c.mp3", t_out=3.0, t_in=4.0, blend_bars=8)
    with pytest.raises(ValueError, match="defekt"):
        cc.vergiss("a.mp3", "b.mp3")
    assert datei.read_bytes() == vorher


def test_hole_und_snapshot_sehen_externen_write_ohne_reset(tmp_path):
    datei = tmp_path / "choices.json"
    key = cc.schluessel("a.mp3", "b.mp3")
    assert cc.hole("a.mp3", "b.mp3") is None
    datei.write_text(
        json.dumps({key: {"t_out": 5.0, "t_in": 2.0, "blend_bars": 8}}),
        encoding="utf-8",
    )

    assert cc.hole("a.mp3", "b.mp3")["t_out"] == 5.0
    assert cc.snapshot()[key]["t_out"] == 5.0


def test_rollback_stellt_exakte_bytes_und_nichtexistenz_wieder_her(tmp_path):
    datei = tmp_path / "choices.json"
    key = cc.schluessel("a.mp3", "b.mp3")
    vorher = (
        '{\n  "' + key.replace("\\", "\\\\") + '": '
        '{"t_out": 1.0, "t_in": 2.0, "blend_bars": 8, "extra": "x"}\n}\n'
    ).encode("utf-8")
    datei.write_bytes(vorher)

    token = cc.merke("a.mp3", "b.mp3", t_out=3.0, t_in=4.0, blend_bars=16)
    cc.stelle_wieder_her(token)
    assert datei.read_bytes() == vorher

    datei.unlink()
    token = cc.merke("a.mp3", "b.mp3", t_out=3.0, t_in=4.0, blend_bars=16)
    cc.stelle_wieder_her(token)
    assert not datei.exists()


def test_rollback_cas_ueberschreibt_keinen_fremden_zwischenstand(tmp_path):
    datei = tmp_path / "choices.json"
    token = cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=8)
    fremd = b'{"fremd":{"t_out":3.0,"t_in":4.0,"blend_bars":8}}\n'
    datei.write_bytes(fremd)

    with pytest.raises(RuntimeError, match="veraendert"):
        cc.stelle_wieder_her(token)

    assert datei.read_bytes() == fremd


def test_unlesbare_datei_blockiert_strikte_pfade_ohne_schreibversuch(
    monkeypatch, tmp_path
):
    datei = tmp_path / "choices.json"
    datei.write_text("{}", encoding="utf-8")
    vorher = datei.read_bytes()
    original = cc._lese_bytes

    def fehler(path):
        if path == datei:
            raise OSError("nicht lesbar")
        return original(path)

    monkeypatch.setattr(cc, "_lese_bytes", fehler)
    assert cc.hole("a.mp3", "b.mp3") is None
    with pytest.raises(OSError, match="nicht lesbar"):
        cc.snapshot()
    with pytest.raises(OSError, match="nicht lesbar"):
        cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=8)
    with pytest.raises(OSError, match="nicht lesbar"):
        cc.vergiss("a.mp3", "b.mp3")
    assert datei.read_bytes() == vorher


def test_zwei_prozesse_verlieren_keinen_unabhaengigen_write(tmp_path):
    datei = tmp_path / "choices.json"
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    ergebnis = context.Queue()
    prozesse = [
        context.Process(
            target=_prozess_schreibt_wahl,
            args=(datei, start, ergebnis, suffix),
        )
        for suffix in (1, 2)
    ]
    for prozess in prozesse:
        prozess.start()
    start.set()
    for prozess in prozesse:
        prozess.join(20)
        assert prozess.exitcode == 0
    assert [ergebnis.get(timeout=2) for _ in prozesse] == [None, None]

    cc.reset_cache()
    assert cc.hole("a-1.mp3", "b-1.mp3") is not None
    assert cc.hole("a-2.mp3", "b-2.mp3") is not None


def test_merke_erhaelt_unbekannte_extras_tief(tmp_path):
    key = cc.schluessel("a.mp3", "b.mp3")
    (tmp_path / "choices.json").write_text(
        json.dumps({
            key: {
                "t_out": 1.0, "t_in": 2.0, "blend_bars": 8,
                "extra": {"liste": [1, {"wert": 2}]},
            }
        }),
        encoding="utf-8",
    )
    cc.reset_cache()

    cc.merke("a.mp3", "b.mp3", t_out=3.0, t_in=4.0, blend_bars=16)

    assert cc.hole("a.mp3", "b.mp3")["extra"] == {"liste": [1, {"wert": 2}]}
    gespeichert = json.loads((tmp_path / "choices.json").read_text(encoding="utf-8"))
    assert gespeichert[key]["extra"] == {"liste": [1, {"wert": 2}]}


def test_schreiben_flush_fsync_replace_newline_und_striktes_json(monkeypatch, tmp_path):
    fsync = Mock(wraps=cc.os.fsync)
    replace = Mock(wraps=cc.os.replace)
    monkeypatch.setattr(cc.os, "fsync", fsync)
    monkeypatch.setattr(cc.os, "replace", replace)

    cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=8)

    assert fsync.call_count == 1
    assert replace.call_count == 1
    assert replace.call_args.args[1] == tmp_path / "choices.json"
    roh = (tmp_path / "choices.json").read_text(encoding="utf-8")
    assert roh.endswith("\n")
    assert "NaN" not in roh and "Infinity" not in roh


def test_schreibfehler_laesst_datei_und_cache_unveraendert(monkeypatch, tmp_path):
    cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=8)
    datei = tmp_path / "choices.json"
    vorher_datei = datei.read_bytes()
    vorher_cache = cc.hole("a.mp3", "b.mp3")
    monkeypatch.setattr(cc.os, "replace", Mock(side_effect=OSError("gesperrt")))

    with pytest.raises(OSError, match="gesperrt"):
        cc.merke("a.mp3", "b.mp3", t_out=3.0, t_in=4.0, blend_bars=16)

    assert datei.read_bytes() == vorher_datei
    assert cc.hole("a.mp3", "b.mp3") == vorher_cache
    assert not list(tmp_path.glob("candidate_choices_*.json"))


def test_commit_bleibt_erfolgreich_wenn_paar_cache_nicht_leerbar(monkeypatch, caplog):
    from hpg_core import playlist
    with monkeypatch.context() as context:
        context.setattr(
            playlist, "reset_pair_candidate_cache",
            Mock(side_effect=RuntimeError("cache kaputt")),
        )
        cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=8)

    assert cc.hole("a.mp3", "b.mp3")["t_out"] == 1.0
    assert "cache kaputt" in caplog.text


def test_vergiss_fehlendes_paar_ist_echter_noop(monkeypatch, tmp_path):
    cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=8)
    vorher = (tmp_path / "choices.json").read_bytes()
    schreibe = Mock(wraps=cc._schreibe)
    leere = Mock(wraps=cc._leere_paar_cache)
    monkeypatch.setattr(cc, "_schreibe", schreibe)
    monkeypatch.setattr(cc, "_leere_paar_cache", leere)

    cc.vergiss("nicht.mp3", "vorhanden.mp3")

    schreibe.assert_not_called()
    leere.assert_not_called()
    assert (tmp_path / "choices.json").read_bytes() == vorher
