"""Tests fuer den lokalen Hoertest-Server (tools/hoertest_server.py).

Geprueft werden die reinen Teile: Pfad-Sanitizing der Clip-Auslieferung und
das Zusammenfuehren der Noten in bewertung.csv. Kein Netzwerk, kein Audio.
"""
from pathlib import Path

import pytest

from tools.hoertest_server import (
  BEWERTUNG_SPALTEN,
  lade_uebersicht,
  lies_range,
  merge_bewertungen,
  sichere_clip_datei,
)


# --- sichere_clip_datei ----------------------------------------------------

def test_sichere_clip_datei_gibt_pfad_im_ordner_zurueck(tmp_path: Path):
  clips = tmp_path / "clips"
  clips.mkdir()
  assert sichere_clip_datei(clips, "001.wav") == (clips / "001.wav").resolve()


@pytest.mark.parametrize(
  "name",
  [
    "../geheim.wav",
    "..\\geheim.wav",
    "unter/001.wav",
    "001.mp3",
    "001.wav.exe",
    "",
    "C:\\Windows\\System32\\drivers\\etc\\hosts",
  ],
)
def test_sichere_clip_datei_weist_fremde_namen_ab(tmp_path: Path, name: str):
  clips = tmp_path / "clips"
  clips.mkdir()
  with pytest.raises(ValueError):
    sichere_clip_datei(clips, name)


# --- merge_bewertungen -----------------------------------------------------

def _zeilen():
  return [
    {"pair_id": "001", "clip": "clips/001.wav", "bewertung": ""},
    {"pair_id": "002", "clip": "clips/002.wav", "bewertung": "3"},
  ]


def test_merge_bewertungen_traegt_note_ein():
  ergebnis = merge_bewertungen(_zeilen(), {"001": 5})
  assert ergebnis[0]["bewertung"] == "5"


def test_merge_bewertungen_ueberschreibt_bestehende_note():
  ergebnis = merge_bewertungen(_zeilen(), {"002": 1})
  assert ergebnis[1]["bewertung"] == "1"


def test_merge_bewertungen_laesst_unberuehrte_zeilen_stehen():
  ergebnis = merge_bewertungen(_zeilen(), {"001": 4})
  assert ergebnis[1]["bewertung"] == "3"
  assert ergebnis[1]["clip"] == "clips/002.wav"


def test_merge_bewertungen_ignoriert_unbekannte_pair_id():
  """Eine unbekannte id darf keine Zeile anhaengen — `fit` wuerde sie mitzaehlen."""
  ergebnis = merge_bewertungen(_zeilen(), {"999": 5})
  assert len(ergebnis) == 2
  assert [z["pair_id"] for z in ergebnis] == ["001", "002"]


def test_merge_bewertungen_behaelt_die_erwarteten_spalten():
  ergebnis = merge_bewertungen(_zeilen(), {"001": 2})
  assert tuple(ergebnis[0].keys()) == BEWERTUNG_SPALTEN


# --- lade_uebersicht -------------------------------------------------------

def test_lade_uebersicht_reichert_mit_merkmalen_an():
  merkmale = [
    {
      "pair_id": "001",
      "crossfade_sek": "57.45",
      "track_a": r"d:\musik\alpha.mp3",
      "track_b": r"d:\musik\beta.mp3",
    }
  ]
  bewertung = [{"pair_id": "001", "clip": "clips/001.wav", "bewertung": "4"}]
  (zeile,) = lade_uebersicht(merkmale, bewertung)
  assert zeile["crossfade_sek"] == "57.45"
  assert zeile["track_a"] == "alpha.mp3"
  assert zeile["track_b"] == "beta.mp3"
  assert zeile["bewertung"] == "4"


def test_lade_uebersicht_zeigt_bpm_und_genre_aus_dem_cache():
  merkmale = [{"pair_id": "001", "track_a": r"D:\M\a.mp3", "track_b": r"D:\M\b.mp3"}]
  bewertung = [{"pair_id": "001", "clip": "clips/001.wav", "bewertung": ""}]
  infos = {
    r"d:\m\a.mp3": {"bpm": 124.0, "genre": "Progressive House", "key": "8A"},
    r"d:\m\b.mp3": {"bpm": 128.0, "genre": "Techno", "key": "9A"},
  }
  (zeile,) = lade_uebersicht(merkmale, bewertung, infos)
  assert zeile["bpm_a"] == 124.0
  assert zeile["bpm_b"] == 128.0
  assert zeile["genre_a"] == "Progressive House"
  assert zeile["key_b"] == "9A"


def test_lade_uebersicht_zeigt_keine_faktor_punktzahlen():
  """Die Faktoren sind die zu schaetzende Groesse — sichtbar wuerden sie das Urteil faerben."""
  merkmale = [
    {"pair_id": "001", "groove": "0.9", "bass": "0.1", "timbre": "0.5",
     "mood": "0.4", "harmonic": "1.0", "bpm": "0.8", "energy": "0.2",
     "genre": "0.3", "track_a": "a.mp3", "track_b": "b.mp3"}
  ]
  bewertung = [{"pair_id": "001", "clip": "clips/001.wav", "bewertung": ""}]
  (zeile,) = lade_uebersicht(merkmale, bewertung)
  for faktor in ("groove", "bass", "timbre", "mood", "harmonic", "energy"):
    assert faktor not in zeile


def test_lade_uebersicht_kommt_ohne_cache_infos_aus():
  merkmale = [{"pair_id": "001", "track_a": "a.mp3", "track_b": "b.mp3"}]
  bewertung = [{"pair_id": "001", "clip": "clips/001.wav", "bewertung": ""}]
  (zeile,) = lade_uebersicht(merkmale, bewertung, {})
  assert zeile["bpm_a"] == ""
  assert zeile["genre_b"] == ""


# --- lies_range ------------------------------------------------------------

@pytest.mark.parametrize(
  "kopf,erwartet",
  [
    (None, (0, 99)),
    ("", (0, 99)),
    ("bytes=0-", (0, 99)),
    ("bytes=10-20", (10, 20)),
    ("bytes=50-", (50, 99)),
    ("bytes=0-0", (0, 0)),
  ],
)
def test_lies_range_wertet_gueltige_koepfe_aus(kopf, erwartet):
  assert lies_range(kopf, 100) == erwartet


@pytest.mark.parametrize(
  "kopf",
  ["quatsch", "bytes=abc-def", "bytes=", "items=0-10"],
)
def test_lies_range_faellt_bei_unbrauchbarem_kopf_auf_ganze_datei_zurueck(kopf):
  assert lies_range(kopf, 100) == (0, 99)


def test_lies_range_kappt_hinter_dem_dateiende():
  """Der Server darf nie mehr ankuendigen als er schreiben kann."""
  assert lies_range("bytes=90-500", 100) == (90, 99)
  assert lies_range("bytes=500-600", 100) == (99, 99)


def test_lies_range_kommt_mit_leerer_datei_klar():
  assert lies_range("bytes=0-", 0) == (0, 0)


def test_lade_uebersicht_kommt_ohne_passende_merkmale_aus():
  bewertung = [{"pair_id": "007", "clip": "clips/007.wav", "bewertung": ""}]
  (zeile,) = lade_uebersicht([], bewertung)
  assert zeile["pair_id"] == "007"
  assert zeile["track_a"] == ""
  assert zeile["crossfade_sek"] == ""
