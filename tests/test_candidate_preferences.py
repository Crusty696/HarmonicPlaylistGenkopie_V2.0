"""Tests fuer den Lader der Kandidaten-Praeferenzen (Hoertest Teil 3)."""
import json
import logging
import multiprocessing
import os

import pytest

from hpg_core import candidate_preferences as cp


def _prozess_schreibt_praeferenz(datei, start, ergebnis, genre):
    os.environ["HPG_CANDIDATE_PREFERENCES_FILE"] = str(datei)
    from hpg_core import candidate_preferences

    candidate_preferences.reset_cache()
    start.wait(10)
    try:
        gewichte = {
            key: 0.1 for key in candidate_preferences.GEWICHT_SCHLUESSEL
        }
        candidate_preferences.merge_user_preferences_atomically(
            {genre: gewichte}
        )
        ergebnis.put(None)
    except Exception as exc:  # pragma: no cover - Elternprozess prueft Ergebnis
        ergebnis.put(repr(exc))


def _gewichte(**aenderungen):
    werte = {key: 0.1 for key in cp.GEWICHT_SCHLUESSEL}
    werte.update(aenderungen)
    return werte


def _schreibe(pfad, daten):
    pfad.write_text(json.dumps(daten), encoding="utf-8")


@pytest.fixture(autouse=True)
def _frisch(monkeypatch, tmp_path):
    monkeypatch.setenv("HPG_CANDIDATE_PREFERENCES_FILE", str(tmp_path / "prefs.json"))
    cp.reset_cache()
    yield
    cp.reset_cache()


def test_ohne_datei_leer():
    assert cp.load_candidate_preferences() == {}
    assert cp.kandidaten_gewichte("Psytrance") is None
    assert cp.schema_rangfolge("Psytrance") == []


def test_override_wird_gelesen_und_validiert(tmp_path):
    gewichte = {f"kandidaten_{f}_weight": 0.1 for f in (
        "harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre", "mood", "loudness", "structure")}
    (tmp_path / "prefs.json").write_text(json.dumps({
        "_diagnose": {"quelle": "test"},
        "Psytrance": {**gewichte, "schema_rang": ["pssi_phrase", "auto_cue"]},
        "Unbekanntes Genre": {"kandidaten_bpm_weight": 1.0},
    }), encoding="utf-8")
    cp.reset_cache()
    assert cp.kandidaten_gewichte("Psytrance") == pytest.approx(gewichte)
    assert cp.schema_rangfolge("Psytrance") == ["pssi_phrase", "auto_cue"]
    assert cp.kandidaten_gewichte("Unbekanntes Genre") is None   # nicht kanonisch -> ignoriert
    assert cp.kandidaten_gewichte("Techno") is None


def test_gewichte_mit_falscher_summe_werden_verworfen(tmp_path, caplog):
    (tmp_path / "prefs.json").write_text(json.dumps({
        "Psytrance": {"kandidaten_bpm_weight": 0.5, "kandidaten_groove_weight": 0.2}}), encoding="utf-8")
    cp.reset_cache()
    assert cp.kandidaten_gewichte("Psytrance") is None


def test_user_ueberschreibt_beide_gueltigen_gruppen_unabhaengig(
    tmp_path, monkeypatch
):
    bundled = tmp_path / "bundled.json"
    user = tmp_path / "prefs.json"
    bundled_gewichte = _gewichte()
    user_gewichte = _gewichte(
        kandidaten_harmonic_weight=0.2,
        kandidaten_bpm_weight=0.0,
    )
    _schreibe(bundled, {
        "Psytrance": {**bundled_gewichte, "schema_rang": ["analyzer"]}
    })
    _schreibe(user, {
        "Psytrance": {**user_gewichte, "schema_rang": ["pssi_phrase", "auto_cue"]}
    })
    monkeypatch.setattr(cp, "_MITGELIEFERT", bundled)
    cp.reset_cache()

    assert cp.kandidaten_gewichte("Psytrance") == pytest.approx(user_gewichte)
    assert cp.schema_rangfolge("Psytrance") == ["pssi_phrase", "auto_cue"]


def test_user_ueberschreibt_nur_deklarierte_gueltige_gruppe(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled.json"
    user = tmp_path / "prefs.json"
    bundled_gewichte = _gewichte()
    _schreibe(bundled, {
        "Psytrance": {**bundled_gewichte, "schema_rang": ["analyzer"]}
    })
    _schreibe(user, {"Psytrance": {"schema_rang": []}})
    monkeypatch.setattr(cp, "_MITGELIEFERT", bundled)
    cp.reset_cache()

    assert cp.kandidaten_gewichte("Psytrance") == pytest.approx(bundled_gewichte)
    assert cp.schema_rangfolge("Psytrance") == []


def test_ungueltige_user_gewichte_lassen_bundled_aktiv_und_warnen_einmal(
    tmp_path, monkeypatch, caplog
):
    bundled = tmp_path / "bundled.json"
    user = tmp_path / "prefs.json"
    bundled_gewichte = _gewichte()
    _schreibe(bundled, {"Psytrance": bundled_gewichte})
    _schreibe(user, {"Psytrance": {"kandidaten_bpm_weight": 1.0}})
    monkeypatch.setattr(cp, "_MITGELIEFERT", bundled)
    caplog.set_level(logging.WARNING, logger=cp.__name__)
    cp.reset_cache()

    assert cp.kandidaten_gewichte("Psytrance") == pytest.approx(bundled_gewichte)
    warnungen = [r.getMessage() for r in caplog.records if "Gruppe gewichte" in r.getMessage()]
    assert len(warnungen) == 1
    assert str(user) in warnungen[0]
    assert "Psytrance" in warnungen[0]
    assert "vorherige gueltige Gruppe bleibt aktiv" in warnungen[0]
    assert "1.0" not in warnungen[0]


def test_ungueltiges_user_schema_laesst_bundled_schema_aktiv(
    tmp_path, monkeypatch, caplog
):
    bundled = tmp_path / "bundled.json"
    user = tmp_path / "prefs.json"
    _schreibe(bundled, {"Psytrance": {"schema_rang": []}})
    _schreibe(user, {"Psytrance": {"schema_rang": ["analyzer", "analyzer"]}})
    monkeypatch.setattr(cp, "_MITGELIEFERT", bundled)
    caplog.set_level(logging.WARNING, logger=cp.__name__)
    cp.reset_cache()

    assert cp.schema_rangfolge("Psytrance") == []
    warnungen = [r.getMessage() for r in caplog.records if "Gruppe schema_rang" in r.getMessage()]
    assert len(warnungen) == 1
    assert "vorherige gueltige Gruppe bleibt aktiv" in warnungen[0]


def test_ungueltige_bundled_gewichte_zerstoeren_gueltiges_bundled_schema_nicht(
    tmp_path, monkeypatch, caplog
):
    bundled = tmp_path / "bundled.json"
    _schreibe(bundled, {
        "Psytrance": {
            "kandidaten_bpm_weight": 1.0,
            "schema_rang": ["pssi_phrase"],
        }
    })
    monkeypatch.setattr(cp, "_MITGELIEFERT", bundled)
    caplog.set_level(logging.WARNING, logger=cp.__name__)
    cp.reset_cache()

    assert cp.kandidaten_gewichte("Psytrance") is None
    assert cp.schema_rangfolge("Psytrance") == ["pssi_phrase"]
    warnungen = [r.getMessage() for r in caplog.records if "Gruppe gewichte" in r.getMessage()]
    assert len(warnungen) == 1
    assert "kein gueltiger Fallback vorhanden" in warnungen[0]


@pytest.mark.parametrize(
    "aenderung",
    [
        {"kandidaten_harmonic_weight": True},
        {"kandidaten_harmonic_weight": float("nan")},
        {"kandidaten_harmonic_weight": float("inf")},
        {"kandidaten_harmonic_weight": -0.1, "kandidaten_bpm_weight": 0.3},
        {"kandidaten_harmonic_weight": 0.2},
    ],
)
def test_gewichtsgruppe_verwirft_bool_nicht_endlich_negativ_und_falsche_summe(
    aenderung
):
    assert cp._gueltige_gewichte(_gewichte(**aenderung)) is None


def test_gewichtsgruppe_verlangt_exakt_zehn_schluessel():
    fehlend = _gewichte()
    fehlend.pop("kandidaten_bpm_weight")
    zusaetzlich = _gewichte()
    zusaetzlich["kandidaten_falsch_weight"] = 0.0

    assert cp._gueltige_gewichte(fehlend) is None
    assert cp._gueltige_gewichte(zusaetzlich) is None


def test_schema_erlaubt_leere_und_partielle_liste_aber_keine_duplikate_oder_fremde():
    assert cp._gueltige_schema_rangfolge([]) == []
    assert cp._gueltige_schema_rangfolge(["sektion", "analyzer"]) == [
        "sektion", "analyzer"
    ]
    assert cp._gueltige_schema_rangfolge(["sektion", "sektion"]) is None
    assert cp._gueltige_schema_rangfolge(["unbekannt"]) is None
    assert cp._gueltige_schema_rangfolge("sektion") is None


def test_fehlende_gruppen_diagnose_und_unbekannte_genres_bleiben_still(
    tmp_path, caplog
):
    _schreibe(tmp_path / "prefs.json", {
        "_diagnose": {"quelle": "test"},
        "Unbekannt": {"schema_rang": ["analyzer"]},
        "Psytrance": {"metadaten": True},
    })
    caplog.set_level(logging.WARNING, logger=cp.__name__)
    cp.reset_cache()

    assert cp.load_candidate_preferences()["Psytrance"] == {
        "gewichte": None, "schema_rang": []
    }
    assert caplog.records == []


@pytest.mark.parametrize("daten", [["kein", "objekt"], 7, None])
def test_nicht_objekt_wurzel_warnt_mit_pfad_ohne_crash(tmp_path, caplog, daten):
    pfad = tmp_path / "prefs.json"
    _schreibe(pfad, daten)
    caplog.set_level(logging.WARNING, logger=cp.__name__)
    cp.reset_cache()

    assert cp.load_candidate_preferences() == {}
    assert len(caplog.records) == 1
    assert str(pfad) in caplog.records[0].getMessage()
    assert "Wurzel ist kein Objekt" in caplog.records[0].getMessage()


def test_nicht_objekt_genre_warnt_mit_pfad_ohne_crash(tmp_path, caplog):
    pfad = tmp_path / "prefs.json"
    _schreibe(pfad, {"Psytrance": ["kein", "objekt"]})
    caplog.set_level(logging.WARNING, logger=cp.__name__)
    cp.reset_cache()

    assert cp.load_candidate_preferences() == {}
    assert len(caplog.records) == 1
    meldung = caplog.records[0].getMessage()
    assert str(pfad) in meldung
    assert "Psytrance" in meldung
    assert "ist kein Objekt" in meldung


def test_lesefehlerwarnung_bleibt_erhalten(tmp_path, caplog):
    pfad = tmp_path / "prefs.json"
    pfad.write_text("{ungueltiges json", encoding="utf-8")
    caplog.set_level(logging.WARNING, logger=cp.__name__)
    cp.reset_cache()

    assert cp.load_candidate_preferences() == {}
    assert len(caplog.records) == 1
    meldung = caplog.records[0].getMessage()
    assert str(pfad) in meldung
    assert "nicht lesbar" in meldung


def test_override_path_nutzt_localappdata_wenn_env_fehlt(tmp_path, monkeypatch):
    monkeypatch.delenv("HPG_CANDIDATE_PREFERENCES_FILE", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert cp.override_path() == tmp_path / "HPG" / "candidate_preferences.json"


def test_atomare_merge_erhaelt_fremde_daten_und_andere_genres(tmp_path):
    ziel = tmp_path / "prefs.json"
    vorher = {
        "_diagnose": {"fremd": {"bleibt": True}},
        "Psytrance": {"schema_rang": ["analyzer"], "notiz": "behalten"},
        "Techno": {"fremdes_feld": 7},
        "plugin_metadaten": {"version": 3},
    }
    _schreibe(ziel, vorher)

    result = cp.merge_user_preferences_atomically(
        {"Psytrance": _gewichte()},
        diagnose={"genres": {"Psytrance": {"uebernommen": True}}},
    )

    assert result == ziel
    daten = json.loads(ziel.read_text(encoding="utf-8"))
    assert daten["Psytrance"]["notiz"] == "behalten"
    assert daten["Psytrance"]["schema_rang"] == ["analyzer"]
    assert daten["Techno"] == {"fremdes_feld": 7}
    assert daten["plugin_metadaten"] == {"version": 3}
    assert daten["_diagnose"]["fremd"] == {"bleibt": True}
    assert daten["_diagnose"]["fit_kandidaten"]["genres"]["Psytrance"]["uebernommen"] is True
    assert cp.kandidaten_gewichte("Psytrance") == pytest.approx(_gewichte())


def test_atomare_merge_erhaelt_tiefe_diagnose_geschwister(tmp_path):
    ziel = tmp_path / "prefs.json"
    _schreibe(ziel, {
        "_diagnose": {
            "fit_kandidaten": {
                "genres": {
                    "Techno": {
                        "uebernommen": True,
                        "messung": {"auc": 0.72, "stichprobe": 18},
                    }
                },
                "lauf": {"seed": 41, "quelle": {"name": "alt"}},
            },
            "plugin": {"tief": {"bleibt": True}},
        }
    })

    cp.merge_user_preferences_atomically(
        {"Psytrance": _gewichte()},
        diagnose={
            "genres": {
                "Psytrance": {"uebernommen": True},
                "Techno": {"messung": {"auc": 0.75}},
            },
            "lauf": {"quelle": {"version": 2}},
        },
    )

    diagnose = json.loads(ziel.read_text(encoding="utf-8"))["_diagnose"]
    assert diagnose["plugin"] == {"tief": {"bleibt": True}}
    assert diagnose["fit_kandidaten"]["genres"]["Psytrance"] == {
        "uebernommen": True
    }
    techno = diagnose["fit_kandidaten"]["genres"]["Techno"]
    assert techno == {
        "uebernommen": True,
        "messung": {"auc": 0.75, "stichprobe": 18},
    }
    assert diagnose["fit_kandidaten"]["lauf"] == {
        "seed": 41,
        "quelle": {"name": "alt", "version": 2},
    }


def test_atomare_merge_schema_allein_erhaelt_bestehende_gewichte(tmp_path):
    ziel = tmp_path / "prefs.json"
    _schreibe(ziel, {"Psytrance": _gewichte()})

    cp.merge_user_preferences_atomically(
        {"Psytrance": {"schema_rang": ["pssi_phrase"]}}
    )

    assert cp.kandidaten_gewichte("Psytrance") == pytest.approx(_gewichte())
    assert cp.schema_rangfolge("Psytrance") == ["pssi_phrase"]


@pytest.mark.parametrize("inhalt", [b"{ kaputt", b"[]", b"null"])
def test_atomare_merge_verweigert_ungueltigen_altstand_ohne_write(tmp_path, inhalt):
    ziel = tmp_path / "prefs.json"
    ziel.write_bytes(inhalt)

    with pytest.raises(ValueError):
        cp.merge_user_preferences_atomically({"Psytrance": _gewichte()})

    assert ziel.read_bytes() == inhalt
    assert list(tmp_path.glob(".prefs.json.*.tmp")) == []


def test_atomare_merge_erstellt_fehlende_datei_und_fsynct(
    tmp_path, monkeypatch
):
    ziel = tmp_path / "prefs.json"
    aufrufe = []
    monkeypatch.setattr(cp.os, "fsync", aufrufe.append)

    cp.merge_user_preferences_atomically({"Psytrance": _gewichte()})

    assert ziel.is_file()
    assert len(aufrufe) == 1
    assert list(tmp_path.glob(".prefs.json.*.tmp")) == []


def test_atomare_merge_schreibt_mitgelieferte_datei_nie(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled.json"
    bundled.write_bytes(b'{"basis": true}\n')
    vorher = bundled.read_bytes()
    monkeypatch.setattr(cp, "_MITGELIEFERT", bundled)

    cp.merge_user_preferences_atomically({"Psytrance": _gewichte()})

    assert bundled.read_bytes() == vorher


@pytest.mark.parametrize("fehlerstelle", ["load", "mismatch"])
def test_atomare_merge_belaesst_gueltigen_commit_bei_reload_fehler(
    tmp_path, monkeypatch, fehlerstelle
):
    ziel = tmp_path / "prefs.json"
    vorher = b'{"Psytrance": {"schema_rang": ["analyzer"]}}\r\n'
    ziel.write_bytes(vorher)
    echtes_load = cp._lade_praeferenzen_unter_lock

    def load_spy():
        if fehlerstelle == "load":
            raise RuntimeError("load kaputt")
        if fehlerstelle == "mismatch":
            return {}
        return echtes_load()

    monkeypatch.setattr(cp, "_lade_praeferenzen_unter_lock", load_spy)

    with pytest.raises(RuntimeError):
        cp.merge_user_preferences_atomically({"Psytrance": _gewichte()})

    nachher = json.loads(ziel.read_text(encoding="utf-8"))
    assert nachher["Psytrance"]["schema_rang"] == ["analyzer"]
    assert {key: nachher["Psytrance"][key] for key in cp.GEWICHT_SCHLUESSEL} == pytest.approx(
        _gewichte()
    )
    assert ziel.read_bytes() != vorher
    assert list(tmp_path.glob(".prefs.json.*.tmp")) == []


def test_atomare_merge_belaesst_neue_datei_bei_reload_mismatch(
    tmp_path, monkeypatch
):
    ziel = tmp_path / "prefs.json"
    monkeypatch.setattr(cp, "_lade_praeferenzen_unter_lock", lambda: {})

    with pytest.raises(RuntimeError, match="weicht ab"):
        cp.merge_user_preferences_atomically({"Psytrance": _gewichte()})

    assert ziel.is_file()
    assert json.loads(ziel.read_text(encoding="utf-8"))["Psytrance"]


def test_pair_cache_wird_unmittelbar_nach_commit_trotz_reload_fehler_geleert(
    tmp_path, monkeypatch
):
    ziel = tmp_path / "prefs.json"
    ereignisse = []
    echtes_schreiben = cp._schreibe_bytes_atomar

    def schreiben(*args):
        echtes_schreiben(*args)
        ereignisse.append("commit")

    def cache_leeren():
        ereignisse.append("cache")

    monkeypatch.setattr(cp, "_schreibe_bytes_atomar", schreiben)
    monkeypatch.setattr(cp, "_leere_paar_cache", cache_leeren)
    monkeypatch.setattr(
        cp,
        "_lade_stabile_praeferenzen_unter_lock",
        lambda: (_ for _ in ()).throw(RuntimeError("reload kaputt")),
    )

    with pytest.raises(RuntimeError, match="reload kaputt"):
        cp.merge_user_preferences_atomically({"Psytrance": _gewichte()})

    assert ereignisse == ["commit", "cache"]
    assert ziel.is_file()


def test_reload_fehler_ueberschreibt_nach_digestpruefung_keinen_fremden_commit(
    tmp_path, monkeypatch
):
    ziel = tmp_path / "prefs.json"
    vorher = b'{"alt": true}\n'
    fremd = b'{"fremd": {"bleibt": true}}\n'
    ziel.write_bytes(vorher)
    monkeypatch.setattr(
        cp,
        "_lade_praeferenzen_unter_lock",
        lambda: (_ for _ in ()).throw(RuntimeError("reload kaputt")),
    )
    echter_digest = cp._digest
    digest_aufrufe = 0

    def fremder_write_nach_erfolgreicher_digestpruefung(daten):
        nonlocal digest_aufrufe
        digest_aufrufe += 1
        ergebnis = echter_digest(daten)
        if digest_aufrufe == 2:
            ziel.write_bytes(fremd)
        return ergebnis

    monkeypatch.setattr(cp, "_digest", fremder_write_nach_erfolgreicher_digestpruefung)

    with pytest.raises(RuntimeError, match="reload kaputt"):
        cp.merge_user_preferences_atomically({"Psytrance": _gewichte()})

    assert ziel.read_bytes() == fremd


def test_externer_write_ist_ohne_reset_sofort_sichtbar(tmp_path):
    ziel = tmp_path / "prefs.json"
    assert cp.load_candidate_preferences() == {}

    _schreibe(ziel, {"Psytrance": _gewichte()})

    assert cp.kandidaten_gewichte("Psytrance") == pytest.approx(_gewichte())


def test_externer_replace_zwischen_read_und_signatur_cached_nur_neustand(
    tmp_path, monkeypatch
):
    ziel = tmp_path / "prefs.json"
    _schreibe(ziel, {"Psytrance": {"schema_rang": ["analyzer"]}})
    echtes_laden = cp._lade_praeferenzen_unter_lock
    aufrufe = 0

    def laden_mit_externem_replace():
        nonlocal aufrufe
        aufrufe += 1
        ergebnis = echtes_laden()
        if aufrufe == 1:
            temp = tmp_path / "prefs.extern.tmp"
            _schreibe(temp, {"Psytrance": {"schema_rang": ["pssi_phrase"]}})
            os.replace(temp, ziel)
        return ergebnis

    monkeypatch.setattr(cp, "_lade_praeferenzen_unter_lock", laden_mit_externem_replace)

    geladen = cp.load_candidate_preferences()

    assert aufrufe == 2
    assert geladen["Psytrance"]["schema_rang"] == ["pssi_phrase"]
    assert cp.schema_rangfolge("Psytrance") == ["pssi_phrase"]
    assert cp._cache_signature == cp._quell_signatur()


def test_externer_replace_nach_stabilem_commit_reload_bindet_keine_neue_signatur_an_altstand(
    tmp_path, monkeypatch
):
    ziel = tmp_path / "prefs.json"
    echtes_stabiles_laden = cp._lade_stabile_praeferenzen_unter_lock
    aufrufe = 0

    def stabiles_laden_mit_replace_nach_rueckgabe():
        nonlocal aufrufe
        aufrufe += 1
        ergebnis, signatur = echtes_stabiles_laden()
        if aufrufe == 1:
            temp = tmp_path / "prefs.nach-reload.extern.tmp"
            _schreibe(temp, {
                "Psytrance": {"schema_rang": ["pssi_phrase"]}
            })
            os.replace(temp, ziel)
        return ergebnis, signatur

    monkeypatch.setattr(
        cp,
        "_lade_stabile_praeferenzen_unter_lock",
        stabiles_laden_mit_replace_nach_rueckgabe,
    )

    cp.merge_user_preferences_atomically(
        {"Psytrance": {"schema_rang": ["analyzer"]}}
    )

    assert cp._cache["Psytrance"]["schema_rang"] == ["analyzer"]
    assert cp._cache_signature != cp._quell_signatur()
    assert cp.schema_rangfolge("Psytrance") == ["pssi_phrase"]
    assert aufrufe == 2
    assert cp._cache_signature == cp._quell_signatur()


def test_wiederholt_instabiler_candidate_read_schlaegt_begrenzt_fehl(
    monkeypatch
):
    zaehler = 0

    def wechselnde_signatur():
        nonlocal zaehler
        zaehler += 1
        return (zaehler,)

    monkeypatch.setattr(cp, "_quell_signatur", wechselnde_signatur)

    with pytest.raises(RuntimeError, match="wiederholt veraendert"):
        cp.load_candidate_preferences()

    assert zaehler == cp._STABILE_LESEVERSUCHE * 2 + 1
    assert cp._cache is None


def test_zwei_spawn_prozesse_verlieren_keine_unabhaengigen_genres(tmp_path):
    ziel = tmp_path / "prefs.json"
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    ergebnis = context.Queue()
    prozesse = [
        context.Process(
            target=_prozess_schreibt_praeferenz,
            args=(ziel, start, ergebnis, genre),
        )
        for genre in ("Psytrance", "Techno")
    ]
    for prozess in prozesse:
        prozess.start()
    start.set()
    for prozess in prozesse:
        prozess.join(20)
        assert prozess.exitcode == 0
    assert [ergebnis.get(timeout=2) for _ in prozesse] == [None, None]

    daten = json.loads(ziel.read_text(encoding="utf-8"))
    assert set(("Psytrance", "Techno")).issubset(daten)


def test_atomare_merge_replace_fehler_belaesst_altstand(tmp_path, monkeypatch):
    ziel = tmp_path / "prefs.json"
    vorher = b'{"alt": true}\n'
    ziel.write_bytes(vorher)
    monkeypatch.setattr(
        cp.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("gesperrt")),
    )

    with pytest.raises(OSError, match="gesperrt"):
        cp.merge_user_preferences_atomically({"Psytrance": _gewichte()})

    assert ziel.read_bytes() == vorher
    assert list(tmp_path.glob(".prefs.json.*.tmp")) == []


def test_atomare_schreibfunktion_wiederholt_transiente_windows_sperre(
    tmp_path, monkeypatch
):
    ziel = tmp_path / "prefs.json"
    echtes_replace = cp.os.replace
    aufrufe = 0

    def einmal_gesperrt(quelle, senke):
        nonlocal aufrufe
        aufrufe += 1
        if aufrufe == 1:
            raise PermissionError(5, "kurz gesperrt")
        echtes_replace(quelle, senke)

    monkeypatch.setattr(cp.os, "replace", einmal_gesperrt)

    cp._schreibe_bytes_atomar(ziel, b"stabil")

    assert aufrufe == 2
    assert ziel.read_bytes() == b"stabil"


@pytest.mark.parametrize(
    "updates",
    [
        {"Unbekannt": _gewichte()},
        {"Psytrance": {"fremd": True}},
        {"Psytrance": {**_gewichte(), "kandidaten_falsch_weight": 0.0}},
        {"Psytrance": {"schema_rang": ["fremd"]}},
    ],
)
def test_atomare_merge_validiert_updates_vor_dateizugriff(tmp_path, updates):
    ziel = tmp_path / "prefs.json"

    with pytest.raises(ValueError):
        cp.merge_user_preferences_atomically(updates)

    assert not ziel.exists()
