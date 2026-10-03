"""Sicherheitsvertraege des optionalen Hoertest-Launchers."""

from __future__ import annotations

import threading
import json

import pytest

from tools import hoertest_launcher


def test_launcher_waehlt_einen_anderen_port_wenn_standardport_belegt(monkeypatch):
    monkeypatch.setattr(hoertest_launcher, "DEFAULT_PORT", 8767)
    monkeypatch.setattr(
        hoertest_launcher,
        "_port_frei",
        lambda port: port != 8767,
    )

    assert hoertest_launcher.finde_freien_port() == 8768


def test_launcher_beendet_nur_seinen_eigenen_server(monkeypatch, tmp_path):
    (tmp_path / "bewertung.csv").write_text("pair_id,note\n", encoding="utf-8")
    class Process:
        def __init__(self, _command):
            self.terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            assert timeout == 3
            return 0

    started = []

    def popen(command):
        process = Process(command)
        started.append((process, command))
        return process

    monkeypatch.setattr(hoertest_launcher, "finde_freien_port", lambda _port=8767: 8768)
    monkeypatch.setattr(hoertest_launcher, "_server_bereit", lambda _port, _token: True)
    monkeypatch.setattr(hoertest_launcher.subprocess, "Popen", popen)
    monkeypatch.setattr(hoertest_launcher.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(hoertest_launcher.webbrowser, "open", lambda _url: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")

    assert hoertest_launcher.starte_server(tmp_path, port=8767) is True

    process, command = started[0]
    assert command[command.index("--port") + 1] == "8768"
    assert command[command.index("--launch-token") + 1]
    assert process.terminated is True
    assert "taskkill" not in " ".join(command).lower()


def test_launcher_meldet_serverstartfehler_ohne_browserstart(
    monkeypatch, tmp_path, capsys
):
    (tmp_path / "bewertung.csv").write_text("pair_id,note\n", encoding="utf-8")
    class FailedProcess:
        def poll(self):
            return 2

        def terminate(self):
            raise AssertionError("Ein bereits beendeter Prozess wird nicht terminiert")

    browser_calls = []
    monkeypatch.setattr(hoertest_launcher, "finde_freien_port", lambda _port=8767: 8769)
    monkeypatch.setattr(
        hoertest_launcher.subprocess,
        "Popen",
        lambda _command: FailedProcess(),
    )
    monkeypatch.setattr(hoertest_launcher.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        hoertest_launcher.webbrowser,
        "open",
        lambda url: browser_calls.append(url),
    )

    assert hoertest_launcher.starte_server(tmp_path, port=8767) is False

    assert browser_calls == []
    assert "konnte nicht gestartet werden" in capsys.readouterr().out.lower()


def test_launcher_faengt_popen_fehler_ab(monkeypatch, tmp_path, capsys):
    (tmp_path / "bewertung.csv").write_text("pair_id,note\n", encoding="utf-8")
    monkeypatch.setattr(hoertest_launcher, "finde_freien_port", lambda _port=8767: 8768)
    monkeypatch.setattr(
        hoertest_launcher.subprocess,
        "Popen",
        lambda _cmd: (_ for _ in ()).throw(OSError("Start blockiert")),
    )
    browser_calls = []
    monkeypatch.setattr(
        hoertest_launcher.webbrowser, "open", lambda url: browser_calls.append(url)
    )

    assert hoertest_launcher.starte_server(tmp_path) is False

    assert browser_calls == []
    assert "Start blockiert" in capsys.readouterr().out


def test_launcher_oeffnet_browser_erst_nach_serverbereitschaft(
    monkeypatch, tmp_path, capsys
):
    (tmp_path / "bewertung.csv").write_text("pair_id,note\n", encoding="utf-8")

    class Process:
        terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            assert timeout == 3
            return 0

    process = Process()
    browser_calls = []
    monkeypatch.setattr(hoertest_launcher, "finde_freien_port", lambda _port=8767: 8768)
    monkeypatch.setattr(hoertest_launcher, "_server_bereit", lambda _port, _token: False)
    monkeypatch.setattr(hoertest_launcher.subprocess, "Popen", lambda _cmd: process)
    monkeypatch.setattr(hoertest_launcher.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        hoertest_launcher.webbrowser, "open", lambda url: browser_calls.append(url)
    )

    assert hoertest_launcher.starte_server(tmp_path) is False

    assert browser_calls == []
    assert process.terminated is True
    assert "keine Bereitschaft" in capsys.readouterr().out


def test_launcher_meldet_serverabsturz_nach_bereitschaft(monkeypatch, tmp_path, capsys):
    (tmp_path / "bewertung.csv").write_text("pair_id,note\n", encoding="utf-8")

    class Process:
        exited = False

        def poll(self):
            return 2 if self.exited else None

        def terminate(self):
            raise AssertionError("Ein beendeter Prozess darf nicht terminiert werden")

    process = Process()
    monkeypatch.setattr(hoertest_launcher, "finde_freien_port", lambda _port=8767: 8768)
    monkeypatch.setattr(hoertest_launcher, "_server_bereit", lambda _port, _token: True)
    monkeypatch.setattr(hoertest_launcher.subprocess, "Popen", lambda _cmd: process)
    monkeypatch.setattr(hoertest_launcher.webbrowser, "open", lambda _url: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: setattr(process, "exited", True))

    assert hoertest_launcher.starte_server(tmp_path) is False
    assert "unerwartet beendet" in capsys.readouterr().out


def test_launcher_erkennt_serverabsturz_waehrend_eingabe(monkeypatch, tmp_path):
    (tmp_path / "bewertung.csv").write_text("pair_id,note\n", encoding="utf-8")

    class Process:
        polls = 0

        def poll(self):
            self.polls += 1
            return 2 if self.polls >= 3 else None

        def terminate(self):
            raise AssertionError("Abgestuerzter Server darf nicht terminiert werden")

    process = Process()
    eingabe_freigeben = threading.Event()
    monkeypatch.setattr(hoertest_launcher, "finde_freien_port", lambda _port=8767: 8768)
    monkeypatch.setattr(hoertest_launcher, "_server_bereit", lambda _port, _token: True)
    monkeypatch.setattr(hoertest_launcher.subprocess, "Popen", lambda _cmd: process)
    monkeypatch.setattr(hoertest_launcher.webbrowser, "open", lambda _url: True)
    monkeypatch.setattr(
        "builtins.input", lambda _prompt: eingabe_freigeben.wait(timeout=2)
    )

    try:
        assert hoertest_launcher.starte_server(tmp_path) is False
    finally:
        eingabe_freigeben.set()


@pytest.mark.parametrize("browser_result", [False, OSError("Browser blockiert")])
def test_launcher_meldet_browserfehler_und_stoppt_eigenen_server(
    monkeypatch, tmp_path, browser_result
):
    (tmp_path / "bewertung.csv").write_text("pair_id,note\n", encoding="utf-8")

    class Process:
        terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            assert timeout == 3
            return 0

    process = Process()

    def browser(_url):
        if isinstance(browser_result, Exception):
            raise browser_result
        return browser_result

    monkeypatch.setattr(hoertest_launcher, "finde_freien_port", lambda _port=8767: 8768)
    monkeypatch.setattr(hoertest_launcher, "_server_bereit", lambda _port, _token: True)
    monkeypatch.setattr(hoertest_launcher.subprocess, "Popen", lambda _cmd: process)
    monkeypatch.setattr(hoertest_launcher.webbrowser, "open", browser)
    monkeypatch.setattr(
        "builtins.input", lambda _prompt: (_ for _ in ()).throw(AssertionError("keine Eingabe"))
    )

    assert hoertest_launcher.starte_server(tmp_path) is False
    assert process.terminated is True


def test_launcher_laesst_manuelle_wahl_ohne_automatische_saetze_zu(monkeypatch):
    monkeypatch.setattr(hoertest_launcher, "finde_hoertest_ordner", lambda: [])
    monkeypatch.setattr(hoertest_launcher, "zeige_menue", lambda ordner: None)

    assert hoertest_launcher.main() == 0


def test_launcher_gibt_startfehler_an_bat_weiter(monkeypatch, tmp_path):
    monkeypatch.setattr(hoertest_launcher, "finde_hoertest_ordner", lambda: [tmp_path])
    monkeypatch.setattr(hoertest_launcher, "zeige_menue", lambda _ordner: tmp_path)
    monkeypatch.setattr(hoertest_launcher, "starte_server", lambda _ordner: False)

    assert hoertest_launcher.main() == 1


def test_launcher_liest_unvollstaendige_csv_ohne_menueabbruch(tmp_path):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip,bewertung\n001,001.wav,\n", encoding="utf-8"
    )
    assert hoertest_launcher.lese_fortschritt(tmp_path) == (0, 1, "Standard")

    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip_id,track_note,technik_note,gesamt_note,gewaehlt,zeit\n"
        "001,001_k1,4,,,,\n", encoding="utf-8"
    )
    assert hoertest_launcher.lese_fortschritt(tmp_path) == (0, 1, "Dreinoten-Kandidaten")


def test_launcher_standard_zeigt_bewertungen_statt_paare(monkeypatch, tmp_path, capsys):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip,bewertung\n001,001_a.wav,4\n001,001_b.wav,\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(hoertest_launcher.os, "system", lambda _cmd: 0)
    monkeypatch.setattr("builtins.input", lambda _prompt: "q")

    assert hoertest_launcher.zeige_menue([tmp_path]) is None
    assert "1 von 2 Bewertungen" in capsys.readouterr().out


def test_launcher_dreinoten_fortschritt_braucht_alle_drei_noten(tmp_path):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip_id,track_note,technik_note,gesamt_note,gewaehlt,zeit\n"
        "001,001_k1,4,5,,,\n"
        "002,002_k1,4,5,3,,\n",
        encoding="utf-8",
    )

    assert hoertest_launcher.lese_fortschritt(tmp_path) == (1, 2, "Dreinoten-Kandidaten")


def test_launcher_ungueltige_note_ist_keine_vollstaendige_bewertung(tmp_path, capsys, monkeypatch):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip,bewertung\n001,001.wav,abc\n", encoding="utf-8"
    )
    monkeypatch.setattr(hoertest_launcher.os, "system", lambda _cmd: 0)
    monkeypatch.setattr("builtins.input", lambda _prompt: "q")

    assert hoertest_launcher.lese_fortschritt(tmp_path) == (0, 0, "fehler")
    assert hoertest_launcher.zeige_menue([tmp_path]) is None
    assert "BEWERTUNGSDATEN FEHLERHAFT" in capsys.readouterr().out


def test_launcher_unvollstaendiges_dramaturgie_manifest_ist_fehler(tmp_path):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip_id,track_note,technik_note,gesamt_note,gewaehlt,zeit\n"
        "t1,t1,5,4,3,,\n", encoding="utf-8"
    )
    (tmp_path / "dramaturgie_manifest.json").write_text(
        json.dumps({"variants": [{"variant_id": "v1"}]}), encoding="utf-8"
    )
    bewertung = tmp_path / "dramaturgie_bewertung.csv"
    bewertung.write_text(
        "variant_id,dramaturgie_gesamt,energieverlauf,peak_platzierung,kohaerenz,zeit\n"
        "v1,5,4,3,,\n", encoding="utf-8"
    )
    assert hoertest_launcher.lese_fortschritt(tmp_path) == (0, 0, "fehler")

    bewertung.write_text(
        "variant_id,dramaturgie_gesamt,energieverlauf,peak_platzierung,kohaerenz,zeit\n"
        "v1,5,4,3,2,\n", encoding="utf-8"
    )
    assert hoertest_launcher.lese_fortschritt(tmp_path) == (0, 0, "fehler")


def test_launcher_kandidaten_zeigt_unentschiedene_paare(monkeypatch, tmp_path, capsys):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip_id,note,gewaehlt,zeit\n"
        "001,001_k1,4,,\n"
        "001,001_k2,3,,\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(hoertest_launcher.os, "system", lambda _cmd: 0)
    monkeypatch.setattr("builtins.input", lambda _prompt: "q")

    assert hoertest_launcher.lese_fortschritt(tmp_path) == (0, 1, "Standard-Kandidaten")
    assert hoertest_launcher.zeige_menue([tmp_path]) is None
    assert "0 von 1 Paare" in capsys.readouterr().out


def test_launcher_kandidatenpaar_erst_mit_entscheidung_fertig(tmp_path):
    bewertung = tmp_path / "bewertung.csv"
    bewertung.write_text(
        "pair_id,clip_id,note,gewaehlt,zeit\n"
        "001,001_k1,4,1,\n"
        "001,001_k2,3,,\n", encoding="utf-8"
    )
    assert hoertest_launcher.lese_fortschritt(tmp_path) == (1, 1, "Standard-Kandidaten")


def test_launcher_dreinoten_kandidatenpaar_braucht_keine_entscheidung(tmp_path):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip_id,track_note,technik_note,gesamt_note,gewaehlt,zeit\n"
        "001,001_k1,4,5,3,,\n"
        "001,001_k2,4,5,2,,\n", encoding="utf-8"
    )
    assert hoertest_launcher.lese_fortschritt(tmp_path) == (1, 1, "Dreinoten-Kandidaten")


@pytest.mark.parametrize("wahl", [("0", ""), ("1", "1")])
def test_launcher_inkonsistente_kandidatenwahl_ist_fehler(tmp_path, wahl):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip_id,note,gewaehlt,zeit\n"
        f"001,001_k1,4,{wahl[0]},\n"
        f"001,001_k2,3,{wahl[1]},\n", encoding="utf-8"
    )
    assert hoertest_launcher.lese_fortschritt(tmp_path) == (0, 0, "fehler")


def test_launcher_verkuerztes_schema_ist_fehler(tmp_path):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip_id,note,gewaehlt\n001,001_k1,4,1\n",
        encoding="utf-8",
    )
    assert hoertest_launcher.lese_fortschritt(tmp_path) == (0, 0, "fehler")


def test_launcher_ueberzaehlige_csv_zelle_ist_fehler(tmp_path):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip,bewertung\n001,001.wav,4,ueberschuss\n",
        encoding="utf-8",
    )
    assert hoertest_launcher.lese_fortschritt(tmp_path) == (0, 0, "fehler")


def test_launcher_einzelner_kandidat_braucht_keine_zusatzwahl(tmp_path):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip_id,note,gewaehlt,zeit\n001,001_k1,4,,\n",
        encoding="utf-8",
    )
    assert hoertest_launcher.lese_fortschritt(tmp_path) == (1, 1, "Standard-Kandidaten")


def test_launcher_doppelte_clip_id_ist_fehler(tmp_path):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip_id,note,gewaehlt,zeit\n"
        "001,doppelt,4,1,\n"
        "001,doppelt,3,,\n", encoding="utf-8"
    )
    assert hoertest_launcher.lese_fortschritt(tmp_path) == (0, 0, "fehler")


def test_launcher_sieger_mit_note_eins_ist_fehler(tmp_path):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip_id,note,gewaehlt,zeit\n"
        "001,001_k1,1,1,\n"
        "001,001_k2,3,,\n", encoding="utf-8"
    )
    assert hoertest_launcher.lese_fortschritt(tmp_path) == (0, 0, "fehler")


def test_launcher_einzelkandidat_mit_note_eins_darf_nicht_sieger_sein(tmp_path):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip_id,note,gewaehlt,zeit\n001,001_k1,1,1,\n",
        encoding="utf-8",
    )

    assert hoertest_launcher.lese_fortschritt(tmp_path) == (0, 0, "fehler")


def test_launcher_sieger_mit_anderem_nullmarker_bleibt_gueltig(tmp_path):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip_id,note,gewaehlt,zeit\n"
        "001,001_k1,4,1,\n"
        "001,001_k2,3,0,\n", encoding="utf-8"
    )
    assert hoertest_launcher.lese_fortschritt(tmp_path) == (1, 1, "Standard-Kandidaten")


def test_launcher_akzeptiert_utf8_bom_in_standard_csv(tmp_path):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip,bewertung\n001,001.wav,4\n", encoding="utf-8-sig"
    )
    assert hoertest_launcher.lese_fortschritt(tmp_path) == (1, 1, "Standard")


def test_launcher_leere_dramaturgie_uebergangstabelle_ist_fehler(tmp_path):
    (tmp_path / "bewertung.csv").write_text(
        "pair_id,clip_id,track_note,technik_note,gesamt_note,gewaehlt,zeit\n",
        encoding="utf-8",
    )
    (tmp_path / "dramaturgie_manifest.json").write_text(
        json.dumps({"variants": [{"variant_id": "v1"}]}), encoding="utf-8"
    )
    assert hoertest_launcher.lese_fortschritt(tmp_path) == (0, 0, "fehler")


def test_launcher_schema_stimmt_mit_server_ueberein():
    from tools import hoertest_server

    assert hoertest_launcher.BEWERTUNG_SCHEMAS == {
        hoertest_server.BEWERTUNG_SPALTEN,
        hoertest_server.BEWERTUNG_KANDIDATEN_SPALTEN,
        hoertest_server.BEWERTUNG_DREINOTEN_SPALTEN,
    }
    assert hoertest_launcher.DRAMATURGIE_SCHEMA == hoertest_server.DRAMATURGIE_BEWERTUNG_SPALTEN


def test_launcher_strg_c_waehrend_bereitschaft_beendet_eigenen_server(monkeypatch, tmp_path):
    (tmp_path / "bewertung.csv").write_text("pair_id,note\n", encoding="utf-8")

    class Process:
        terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            return 0

    process = Process()
    monkeypatch.setattr(hoertest_launcher, "finde_freien_port", lambda _port=8767: 8768)
    monkeypatch.setattr(hoertest_launcher.subprocess, "Popen", lambda _cmd: process)
    monkeypatch.setattr(
        hoertest_launcher, "_server_bereit",
        lambda _port, _token: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    monkeypatch.setattr(
        hoertest_launcher.webbrowser, "open",
        lambda _url: (_ for _ in ()).throw(AssertionError("Browser darf nicht öffnen")),
    )

    assert hoertest_launcher.starte_server(tmp_path) is False
    assert process.terminated is True


def test_launcher_startet_ohne_bewertung_nicht(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        hoertest_launcher.subprocess,
        "Popen",
        lambda _cmd: (_ for _ in ()).throw(AssertionError("kein Serverstart")),
    )

    hoertest_launcher.starte_server(tmp_path)

    assert "Keine bewertung.csv" in capsys.readouterr().out


def test_start_bat_verwendet_den_projektpfad_statt_eines_altpfads():
    from pathlib import Path

    batch = Path(__file__).parents[1] / "Start_Hoertest.bat"
    content = batch.read_text(encoding="utf-8")

    assert "%~dp0" in content
    assert "HarmonicPlaylistGenkopie_V2.0-main" not in content
