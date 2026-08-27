"""Tests fuer den lokalen Hoertest-Server (tools/hoertest_server.py).

Geprueft werden die reinen Teile: Pfad-Sanitizing der Clip-Auslieferung und
das Zusammenfuehren der Noten in bewertung.csv. Kein Netzwerk, kein Audio.
"""
import csv
import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.hoertest_server import (
  BEWERTUNG_SPALTEN,
  HoertestHandler,
  _port,
  lade_track_infos,
  lade_uebersicht,
  lies_range,
  merge_bewertungen,
  schreibe_csv,
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


def test_lade_track_infos_reicht_expliziten_cache_weiter(monkeypatch, tmp_path: Path):
  cache = tmp_path / "test.db"
  aufrufe = []
  track = SimpleNamespace(
    filePath="C:/Musik/a.wav", bpm=140.0, genre="Psytrance",
    detected_genre="", camelotCode="8A",
  )
  monkeypatch.setattr(
    "tools.rate_transitions.lade_tracks_aus_cache",
    lambda db_pfad=None: aufrufe.append(db_pfad) or [track],
  )
  infos = lade_track_infos(str(cache))
  assert aufrufe == [str(cache)]
  assert infos["c:/musik/a.wav"]["bpm"] == 140.0


@pytest.mark.parametrize("wert", ["0", "65536", "-1", "abc"])
def test_port_weist_ungueltige_werte_ab(wert):
  with pytest.raises(Exception):
    _port(wert)


def test_schreibe_csv_belaesst_alte_datei_wenn_replace_scheitert(monkeypatch, tmp_path: Path):
  pfad = tmp_path / "bewertung.csv"
  pfad.write_text("alt\n", encoding="utf-8")
  monkeypatch.setattr("tools.hoertest_server.os.replace", lambda *_: (_ for _ in ()).throw(OSError("gesperrt")))
  with pytest.raises(OSError):
    schreibe_csv(pfad, BEWERTUNG_SPALTEN, _zeilen())
  assert pfad.read_text(encoding="utf-8") == "alt\n"
  assert list(tmp_path.glob(".bewertung.csv.*.tmp")) == []


def _server_post(server, pfad: str, daten: dict) -> int:
  verbindung = http.client.HTTPConnection(*server.server_address, timeout=5)
  koerper = json.dumps(daten).encode("utf-8")
  verbindung.request("POST", pfad, body=koerper, headers={"Content-Type": "application/json"})
  antwort = verbindung.getresponse()
  antwort.read()
  status = antwort.status
  verbindung.close()
  return status


def _server_get(server, pfad: str) -> int:
  verbindung = http.client.HTTPConnection(*server.server_address, timeout=5)
  verbindung.request("GET", pfad)
  antwort = verbindung.getresponse()
  antwort.read()
  status = antwort.status
  verbindung.close()
  return status


@pytest.fixture
def hoertest_server(tmp_path: Path):
  ordner = tmp_path / "satz"
  ordner.mkdir()
  schreibe_csv(ordner / "bewertung.csv", BEWERTUNG_SPALTEN, _zeilen())
  handler = type("TestHoertestHandler", (HoertestHandler,), {})
  handler.ordner = ordner
  handler.track_infos = {}
  handler.reihenfolge = {}
  server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
  thread = threading.Thread(target=server.serve_forever, daemon=True)
  thread.start()
  try:
    yield server, ordner
  finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_post_unbekanntes_paar_ist_keine_falsche_erfolgsmeldung(hoertest_server):
  server, _ = hoertest_server
  assert _server_post(server, "/note", {"pair_id": "999", "note": 5}) == 404


@pytest.mark.parametrize(
  "payload",
  [
    {"pair_id": "001"},
    {"pair_id": "001", "note": True},
    {"pair_id": "001", "note": False},
    {"pair_id": "001", "note": 1.0},
    {"pair_id": "001", "note": "1"},
  ],
)
def test_legacy_note_verwirft_fehlenden_oder_nicht_exakt_ganzzahligen_json_wert_bytegleich(
  hoertest_server, payload
):
  server, ordner = hoertest_server
  vorher = (ordner / "bewertung.csv").read_bytes()
  assert _server_post(server, "/note", payload) == 400
  assert (ordner / "bewertung.csv").read_bytes() == vorher


@pytest.mark.parametrize("note", [1, 5])
def test_legacy_note_akzeptiert_exakte_json_ganzzahlgrenzen(hoertest_server, note):
  server, ordner = hoertest_server
  assert _server_post(server, "/note", {"pair_id": "001", "note": note}) == 200
  with (ordner / "bewertung.csv").open(encoding="utf-8", newline="") as handle:
    row = next(csv.DictReader(handle))
  assert row["bewertung"] == str(note)


def test_legacy_note_loescht_nur_mit_explizitem_json_null(hoertest_server):
  server, ordner = hoertest_server
  assert _server_post(server, "/note", {"pair_id": "002", "note": None}) == 200
  with (ordner / "bewertung.csv").open(encoding="utf-8", newline="") as handle:
    rows = {row["pair_id"]: row for row in csv.DictReader(handle)}
  assert rows["002"]["bewertung"] == ""


def _setze_kandidaten_csv(ordner: Path) -> None:
  schreibe_csv(
    ordner / "bewertung.csv",
    BEWERTUNG_KANDIDATEN_SPALTEN,
    [
      {"pair_id": "001", "clip_id": "001_k1", "note": "4", "gewaehlt": "1", "zeit": "alt"},
      {"pair_id": "001", "clip_id": "001_k2", "note": "3", "gewaehlt": "", "zeit": "alt"},
    ],
  )


@pytest.mark.parametrize(
  "payload",
  [
    {"pair_id": "001", "clip_id": "001_k1"},
    {"pair_id": "001", "clip_id": "001_k1", "note": True},
    {"pair_id": "001", "clip_id": "001_k1", "note": False},
    {"pair_id": "001", "clip_id": "001_k1", "note": 1.0},
    {"pair_id": "001", "clip_id": "001_k1", "note": "1"},
  ],
)
def test_kandidaten_note_verwirft_fehlenden_oder_nicht_exakt_ganzzahligen_json_wert_bytegleich(
  hoertest_server, payload
):
  server, ordner = hoertest_server
  _setze_kandidaten_csv(ordner)
  vorher = (ordner / "bewertung.csv").read_bytes()
  assert _server_post(server, "/note", payload) == 400
  assert (ordner / "bewertung.csv").read_bytes() == vorher


@pytest.mark.parametrize("note", [1, 5])
def test_kandidaten_note_akzeptiert_exakte_json_ganzzahlgrenzen(hoertest_server, note):
  server, ordner = hoertest_server
  _setze_kandidaten_csv(ordner)
  assert _server_post(
    server, "/note", {"pair_id": "001", "clip_id": "001_k2", "note": note}
  ) == 200
  with (ordner / "bewertung.csv").open(encoding="utf-8", newline="") as handle:
    rows = {row["clip_id"]: row for row in csv.DictReader(handle)}
  assert rows["001_k2"]["note"] == str(note)


def test_kandidaten_note_loescht_nur_mit_explizitem_null_und_bereinigt_wahl(
  hoertest_server,
):
  server, ordner = hoertest_server
  _setze_kandidaten_csv(ordner)
  assert _server_post(
    server, "/note", {"pair_id": "001", "clip_id": "001_k1", "note": None}
  ) == 200
  with (ordner / "bewertung.csv").open(encoding="utf-8", newline="") as handle:
    rows = {row["clip_id"]: row for row in csv.DictReader(handle)}
  assert rows["001_k1"]["note"] == ""
  assert rows["001_k1"]["gewaehlt"] == ""


def test_parallele_noten_gehen_nicht_verloren(hoertest_server):
  server, ordner = hoertest_server
  start = threading.Barrier(3)
  ergebnisse = []

  def speichern(pair_id, note):
    start.wait()
    ergebnisse.append(_server_post(server, "/note", {"pair_id": pair_id, "note": note}))

  threads = [
    threading.Thread(target=speichern, args=("001", 4)),
    threading.Thread(target=speichern, args=("002", 5)),
  ]
  for thread in threads:
    thread.start()
  start.wait()
  for thread in threads:
    thread.join(timeout=5)
  with (ordner / "bewertung.csv").open(encoding="utf-8", newline="") as handle:
    noten = {z["pair_id"]: z["bewertung"] for z in csv.DictReader(handle)}
  assert sorted(ergebnisse) == [200, 200]
  assert noten == {"001": "4", "002": "5"}


def test_korrupte_bestehende_note_beendet_request_kontrolliert(hoertest_server):
  server, ordner = hoertest_server
  schreibe_csv(
    ordner / "bewertung.csv",
    BEWERTUNG_KANDIDATEN_SPALTEN,
    [{"pair_id": "001", "clip_id": "001_k1", "note": "kaputt", "gewaehlt": "", "zeit": ""}],
  )
  assert _server_post(server, "/bester", {"pair_id": "001", "clip_id": "001_k1"}) == 400


def test_get_csv_fehler_liefert_kontrollierte_500(monkeypatch, hoertest_server):
  from tools import hoertest_server as hs

  server, _ = hoertest_server
  monkeypatch.setattr(
    hs, "lies_csv", lambda _pfad: (_ for _ in ()).throw(csv.Error("kaputt"))
  )
  assert _server_get(server, "/daten") == 500


def test_post_csv_fehler_liefert_kontrollierte_500(monkeypatch, hoertest_server):
  from tools import hoertest_server as hs

  server, _ = hoertest_server
  monkeypatch.setattr(
    hs, "lies_csv", lambda _pfad: (_ for _ in ()).throw(csv.Error("kaputt"))
  )
  assert _server_post(server, "/note", {"pair_id": "001", "note": 4}) == 500


def test_clip_stat_fehler_liefert_kontrollierte_500(monkeypatch, hoertest_server):
  from tools import hoertest_server as hs

  class NichtLesbarerClip:
    def is_file(self):
      return True

    def stat(self):
      raise OSError("kaputt")

  server, _ = hoertest_server
  monkeypatch.setattr(hs, "sichere_clip_datei", lambda *_args: NichtLesbarerClip())
  assert _server_get(server, "/clips/001.wav") == 500


def test_serverstart_faengt_unlesbare_bewertung_csv_ab(monkeypatch, tmp_path):
  from tools import hoertest_server as hs

  ordner = tmp_path / "satz"
  ordner.mkdir()
  (ordner / "bewertung.csv").write_text("pair_id,clip,bewertung\n", encoding="utf-8")
  monkeypatch.setattr(hs, "lies_csv", lambda _pfad: (_ for _ in ()).throw(PermissionError("gesperrt")))
  assert hs.main(["--dir", str(ordner)]) == 2


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


# Kandidatenmodus (Spec 2026-08-21 Abschnitt 3, Plan Teil 3)
from tools.hoertest_server import (
  BEWERTUNG_KANDIDATEN_SPALTEN, KANDIDAT_ANZEIGE_FELDER, ist_kandidatensatz,
  lade_uebersicht_kandidaten, merge_kandidaten_bewertung,
)


def test_ist_kandidatensatz_an_clip_id_spalte():
  assert ist_kandidatensatz([{"pair_id": "001", "clip_id": "001_k1", "note": "", "gewaehlt": "", "zeit": ""}])
  assert not ist_kandidatensatz([{"pair_id": "001", "clip": "clips/001.wav", "bewertung": ""}])
  assert not ist_kandidatensatz([])
  assert BEWERTUNG_KANDIDATEN_SPALTEN == ("pair_id", "clip_id", "note", "gewaehlt", "zeit")


def test_merge_kandidaten_note_und_bester_exklusiv_mit_zeit():
  zeilen = [
    {"pair_id": "001", "clip_id": "001_k1", "note": "", "gewaehlt": "", "zeit": ""},
    {"pair_id": "001", "clip_id": "001_k2", "note": "", "gewaehlt": "1", "zeit": "alt"},
    {"pair_id": "002", "clip_id": "002_k1", "note": "", "gewaehlt": "", "zeit": ""},
  ]
  neu = merge_kandidaten_bewertung(zeilen, pair_id="001", clip_id="001_k1", note=4, zeit="2026-08-22T20:00:00")
  assert neu[0]["note"] == "4" and neu[0]["zeit"] == "2026-08-22T20:00:00"
  neu = merge_kandidaten_bewertung(neu, pair_id="001", clip_id="001_k1", bester=True, zeit="2026-08-22T20:01:00")
  assert neu[0]["gewaehlt"] == "1" and neu[1]["gewaehlt"] == ""    # exklusiv je Paar
  assert neu[2]["gewaehlt"] == "" and neu[1]["zeit"] == "alt"
  neu = merge_kandidaten_bewertung(neu, pair_id="001", clip_id="001_k1", note=None, zeit="t")
  assert neu[0]["note"] == ""


def test_note_eins_kann_keine_beste_wahl_behalten():
  zeilen = [
    {"pair_id": "001", "clip_id": "001_k1", "note": "4", "gewaehlt": "1", "zeit": "alt"},
    {"pair_id": "001", "clip_id": "001_k2", "note": "3", "gewaehlt": "", "zeit": "alt"},
  ]
  neu = merge_kandidaten_bewertung(
    zeilen, pair_id="001", clip_id="001_k1", note=1, zeit="neu"
  )
  assert neu[0]["note"] == "1"
  assert not any(z["gewaehlt"] == "1" for z in neu)


def test_mehrere_clips_erlauben_explizit_keinen_besten():
  zeilen = [
    {"pair_id": "001", "clip_id": "001_k1", "note": "2", "gewaehlt": "1", "zeit": "alt"},
    {"pair_id": "001", "clip_id": "001_k2", "note": "3", "gewaehlt": "", "zeit": "alt"},
  ]
  neu = merge_kandidaten_bewertung(
    zeilen, pair_id="001", clip_id="", kein_bester=True, zeit="neu"
  )
  assert all(z["gewaehlt"] == "0" for z in neu)


def test_lade_uebersicht_kandidaten_gruppiert_verdeckt_und_in_reihenfolge():
  merk = [
    {"pair_id": "001", "clip_id": "001_k1", "clip": "clips/001_k1.wav", "score": "0.9", "schema_out": "pssi_phrase",
     "crossfade_sek": "27.4", "track_a": "C:/x/a.mp3", "track_b": "C:/x/b.mp3", "harmonic": "0.9",
     "bpm_a": "140.0", "bpm_b": "141.0", "genre_a": "Psytrance", "genre_b": "Psytrance", "key_a": "8A", "key_b": "9A"},
    {"pair_id": "001", "clip_id": "001_k2", "clip": "clips/001_k2.wav", "score": "0.5", "schema_out": "sektion",
     "crossfade_sek": "54.9", "track_a": "C:/x/a.mp3", "track_b": "C:/x/b.mp3", "harmonic": "0.9",
     "bpm_a": "140.0", "bpm_b": "141.0", "genre_a": "Psytrance", "genre_b": "Psytrance", "key_a": "8A", "key_b": "9A"},
  ]
  bew = [
    {"pair_id": "001", "clip_id": "001_k1", "note": "", "gewaehlt": "", "zeit": ""},
    {"pair_id": "001", "clip_id": "001_k2", "note": "3", "gewaehlt": "1", "zeit": "t"},
  ]
  reihenfolge = {"001": {"seed": 1, "clips": ["001_k2", "001_k1"]}}
  infos = {"c:/x/a.mp3": {"bpm": 140.0, "genre": "Psytrance", "key": "8A"}}
  paare = lade_uebersicht_kandidaten(merk, bew, reihenfolge, infos)
  assert [p["pair_id"] for p in paare] == ["001"]
  p = paare[0]
  assert [c["clip_id"] for c in p["clips"]] == ["001_k2", "001_k1"]
  assert p["bpm_a"] == 140.0 and p["genre_a"] == "Psytrance" and p["key_a"] == "8A"
  assert p["bpm_b"] == "141.0" and p["key_b"] == "9A"        # B nicht im Cache -> aus merkmale.csv
  c = p["clips"][0]
  assert c["note"] == "3" and c["gewaehlt"] == "1" and c["crossfade_sek"] == "54.9"
  assert set(c) == set(KANDIDAT_ANZEIGE_FELDER) == {"clip_id", "clip", "note", "gewaehlt", "crossfade_sek"}
  assert "score" not in c and "schema_out" not in c and "harmonic" not in c
  # ganz ohne Cache: Kontext kommt vollstaendig aus merkmale.csv
  p2 = lade_uebersicht_kandidaten(merk, bew, {}, {})[0]
  assert p2["bpm_a"] == "140.0" and p2["genre_a"] == "Psytrance" and p2["key_a"] == "8A"
