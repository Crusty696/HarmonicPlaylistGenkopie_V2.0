# HPG-Testfixtures

Quellenabgleich 26.10.2026 mit audio_generators.py, track_factories.py,
camelot_test_data.py, tests/conftest.py und pytest.ini.

## Synthetische Signale

Die Generatoren in `audio_generators.py` liefern NumPy-Arrays, kein
`(audio, sr)`-Tupel. Die Samplerate wird als Parameter mitgegeben;
DEFAULT_SR ist 22050. Beispiel:

```python
from tests.fixtures import generate_click_track

sr = 22050
audio = generate_click_track(bpm=128.0, duration=10.0, sr=sr)
assert audio.shape == (10 * sr,)
```

Sinus-, Akkord- und Strukturgeneratoren liefern kontrollierte Testsignale.
Sie beweisen keine Erkennungsqualitaet an echter Musik. Funktionssignaturen
und Rueckgaben im jeweiligen Generator lesen; keine fiktiven detect_* APIs.

## Track-Factories

`track_factories.make_track` erzeugt Track-Datensaetze mit synthetischen
lokalen Kandidaten. Defaults: 128 BPM, 300 Sekunden, camelotCode='8A',
energy=70. Tonart steht in keyNote/keyMode/camelotCode, nicht in `key`.

```python
from tests.fixtures import make_track

track = make_track(bpm=140.0, camelotCode='5A', energy=95)
assert track.bpm == 140.0
assert track.camelotCode == '5A'
```

`make_house_track`, `make_techno_track`, `make_dnb_track`,
`make_compatible_pair` und `make_playlist_set` sind Hilfen fuer isolierte
Tests. Kandidaten und Herkunft sind synthetisch; keine Originaltrack-Abnahme.
Camelot-Testdaten sind Testvorgaben, kein Ersatz fuer den aktuellen Vertrag
in `hpg_core/models.py` und die Regressionen in test_compatibility.py.

## Pytest

Audio-, Track- und Datenfixtures stehen in `tests/conftest.py`.
Mixpunktpruefungen verwenden `assert_mix_points_valid` und
`assert_phrase_aligned`. Produktivcache, Nutzerpraeferenzen und Originalmusik
bleiben geschuetzt. Projektinterpreter: `venv312\Scripts\python.exe`.

Die registrierten Marker stehen in pytest.ini: unit, integration,
performance_test, acceptance, regression, slow, requires_audio, gui,
exporter. Ein Marker `audio` ist nicht registriert. Keine automatische
Klassifizierung anhand einer gemessenen Ein-Sekunden-Laufzeit behaupten.
Der Standardlauf waehlt `slow` ab. Abschlussumfang und Testausnahmen stehen
in AGENTS.md und im Skill hpg-testing-verification.
