---
name: hpg-cache-persistence
description: Use when an HPG code change has no visible effect, or when working on caching.py — CACHE_VERSION, Cache-Key, hpg_cache_v*.db, SQLite/WAL, file_lock, Quarantaene korrupter Zeilen, rekordbox_signature oder Track-Serialisierung.
---

# HPG Cache & Persistence

## Erste Frage bei "mein Fix wirkt nicht"

**Cache-Hit.** `analyze_track` fragt den Cache vor Decode und Audio-Features,
aber nach Pfad-/Ressourcenpruefung, echter Audiodauer und Ermittlung der
Rekordbox-Daten samt Signatur in `analyze_track` [hpg_core/analysis.py]. Ein geaenderter
Algorithmus liefert weiter die alten Werte, solange Cache-Key und Version
passen.

## CACHE_VERSION — wo und wann

`CACHE_VERSION = 104` in **`hpg_core/caching.py`** — nicht in `config.py`. Cache 85 umfasst die bestätigte reine Rekordbox-Phasenoffset-Korrektur ohne Bar-Rotation. Cache 86 verwirft Rotation-0-Korrekturen, die den Anker über eine Bar-Grenze wickeln würden. Cache 87 berücksichtigt die wirksame Phrase-Unit bereits in der internen Mix-In/Out-Kandidatensuche und deren Guards. Cache 88 verwendet den Median aller sechs konsistenten Tempoausgaben statt des ersten Werts. Cache 89 persistiert strukturierte Tempoentscheidungsdiagnosen im Messschema v7. Cache 90 erhält alle sechs Modell-BPM-Werte samt Modell-ID und Fensterstart; die v7-Validierung leitet bei sechs Werten Median und Spread daraus neu ab, verwirft widersprüchliche Payloads und bindet akzeptierte Tempi an die bestehende 2%-Grenze.
Das ist ein haeufiger Fehlgriff.

Die Version steckt im **Dateinamen**: `hpg_cache_v96.db`. Ein Bump erzeugt
also eine neue DB; zusaetzlich filtert der Read auf die Version und raeumt
stale Rows auf.

**Stand 34 (2026-08-21):** fuenf neue Listenfelder auf `Track` —
`phrases`, `cue_points`, `phrase_grid`, `mix_in_candidates`,
`mix_out_candidates` — alle in `TRACK_LIST_FIELDS`. Alte Rows kennen die
Felder nicht und lieferten stillschweigend leere Listen statt der
Kandidaten; erst eine Neuanalyse (durch den Bump erzwungen) fuellt sie.

**Stand 37 (2026-08-25):** persistierter Beatgrid-Pruefstatus, vollstaendige
Rekordbox-PQTZ-Signatur und strenge `None`-Semantik fuer unbekannte lokale
Kick-, Vocal- und Strukturmessungen. Cache 34–36 ist dafuer veraltet.

**Stand 38 (2026-08-26):** BPM-lose Rekordbox-Eintraege behalten nach der
Librosa-Tempoermittlung validierte RB-Keys, Cues und PSSI-Phrasen. Die
Rekordbox-Signatur umfasst auch die daraus abgeleiteten PSSI-Phrasen. Cache 37
darf diesen geaenderten Analysevertrag nicht maskieren.

**Stand 39 (2026-08-26):** Jede Cache-Zeile muss den expliziten Vertrag aus
60 `Track`-Feldern und je 28 Feldern pro Mix-Kandidat vollstaendig erfuellen.
Vor dem Schreiben entsteht ein tiefer, vom lebenden `Track` losgeloester
Snapshot; NaN/Inf werden feldabhaengig als `None`, leerer lokaler Vektor oder
`0.0` nur fuer die beiden Top-Level-Fingerprints normalisiert. Harte
Pflichtmessungen bleiben ungueltig statt stillschweigend repariert zu werden.
Fast-Path und BPM-loser Vollpfad bestimmen Analyse-Phrasenenden mit der echten
endlichen Dateidauer. Der parameterlose Signaturaufruf verwendet weiterhin die
endliche positive Rekordbox-Dauer beziehungsweise `0.0`; diese RB-Phrasen
bleiben Teil der Signatur. Dauerabhaengige Memo-Keys trennen beide Verwendungen.
Cache 38 erfuellt diesen Vertrag nicht sicher.

**Stand 40 (2026-08-26):** Im Rekordbox-Fast-Path ist die framegenaue
Audiodauer autoritativ. Ganzzahlig gekuerzte Rekordbox-Dauern duerfen gueltige
Cues nicht hinter das Trackende verschieben; Cues werden vor Kandidatenbildung
und Persistenz gegen die echte Dateidauer geprueft. Alte v39-Zeilen koennen
abweichende Dauern sowie Cue- und Kandidatenwerte enthalten.

**Stand 41 (2026-08-26):** Die ID3-BPM-Faktorpruefung erkennt auch 3/4- und
4/3-Fehltaggings. Korrekturen sind strikt an ein bekanntes kanonisches
ID3-Genre gebunden; einen genreuebergreifenden Union-Fallback gibt es nicht.
Alte v40-Zeilen koennen falsche BPM, Phrasenraster, Mixpunkte und Kandidaten
enthalten. Artist, Titel und Genre werden fuer AIFF feldweise aus Easy-Tags und
bei fehlenden Werten aus rohen `TPE1`-/`TIT2`-/`TCON`-Frames ergaenzt.

**Stand 42 (2026-08-26):** Gerichtete manuelle Rekordbox-Cues behalten ihre
Provenienz und Prioritaet, duerfen aber weder Track-Mixpunkte noch lokale
Kandidaten oder Paar-Gates ueber Intro-/Outro-Grenzen hinwegsetzen. Alte
v41-Zeilen koennen grenzverletzende Mixpunkte und Kandidaten enthalten.

**Stand 43 (2026-08-27):** Mehrdeutige Audio-Keys werden vollstaendig geleert;
Rekordbox-Beatgrids brauchen fuer Persistenz und Export den verifizierten
Referenzvertrag. PSSI-Grenzen und KI-Metadaten werden strikt validiert.

**Stand 45 (2026-09-04):** gemeinsames Merkmalsfenster fuer acht
Track-Merkmale (D8) — Fast-Path und Vollpfad messen sie ueber dieselben
360 Sekunden.

**Stand 44 (2026-08-27):** Ein nicht erfuellbares Phrasenraster liefert fuer
Mix-In und Mix-Out den expliziten Sentinel statt eines Bar-Fallbacks. Alte
v43-Zeilen koennen semantisch veraltete Fallback-Mixpunkte enthalten.

**Bump ist Pflicht, wenn sich der Analyse-Output aendert:** Mixpoint-Formel,
Quantisierung, Sektions-Labeling, Genre-Regeln, neue/geaenderte Track-Felder,
Downbeat-/Phrase-Schaetzung. Ohne Bump maskieren alte Werte den Fix — und ein
Reviewer sieht gruene Tests bei kaputtem Produktivverhalten.

Die Kommentarhistorie ueber der Konstante dokumentiert jeden Bump mit Grund.
Neue Bumps in diesem Stil ergaenzen.

**Stand 58 (2026-10-14):** Rekordbox-Metadaten ohne exakten Pfadtreffer werden
nicht mehr per eindeutigem Basename in die Analyse uebernommen. Aeltere
Fallback-Zeilen koennen falsche BPM, Keys und Cues enthalten.

**Stand 59 (2026-10-14):** Bei belastbarer Fold-Phase wird ein widerspruechliches
oder unvollstaendiges internes Beat-Alignment verworfen; alte ungleichphasige
Trackerzeiten duerfen keinen Downbeat-Anker mehr erzeugen.

**Stand 60 (2026-10-14):** Mixpunkte und Mix-Kandidaten werden nur ausgegeben,
wenn die Taktphase belastbar ist. Alte Cache-Zeilen mit Mix-Ausgaben auf einem
Fallback-Anker muessen neu analysiert werden.

**Stand 61 (2026-10-14):** Abgeleitete Phrase-, Struktur-, Groove- und
Mixwerte werden nur mit ausreichender Konfidenz und bestaetigter Beatgridphase
erzeugt. Alte Zeilen koennen solche Rasterwerte trotz unbestaetigtem Gesamtgrid
enthalten.

**Stand 62 (2026-10-14):** `Track.phrase_anchor` liefert bei Konfidenz unter
der Mindestschwelle oder nicht verifiziertem Beatgrid keinen rohen
`first_downbeat` an Pairing und Uebergangsplanung.

**Stand 65 (2026-10-14):** Bei schwacher Phrase-Konfidenz darf die vorhandene
Audio-Beatmodell-Arbitration eine verifizierte DSP-Baseline herausfordern.
Verifizierte Rekordbox-Referenzen bleiben priorisiert; bei Modellablehnung
werden Baseline-Anker und -Phrasenpaar wiederverwendet.

**Stand 66 (2026-10-14):** Eine abgewiesene Fixed-BPM-Downbeatkorrektur behaelt
ihren primaeren Diagnosegrund und speichert den Retrygrund separat. Das macht
Beattracking- und Fold/Grid-Ablehnungen in der RAM-Messansicht unterscheidbar.

**Stand 67 (2026-10-14):** Diagnose-Schema v4 und Rekordbox-Signatur erfassen
`exact_path` gegen `volume_rebind`; alte Cacheeintraege werden durch den
Versionswechsel getrennt.

**Stand 68 (2026-10-14):** Diagnose-Schema v5 speichert den rein diagnostischen
Modulo-4-Vergleich der PQTZ-Taktpositionen mit vorhandenen Modellbeats. Ein
Modellkandidat ändert weder den aktiven Rekordbox-Anker noch Phrase-/PSSI-
Auswahl oder Freigabegates. Alte Cacheeinträge enthalten diesen Vergleich nicht.

**Stand 69 (2026-10-14):** `audio_confirmation` protokolliert zusätzliche
DSP-Votierungen in sechs Modellfenstern und die abschließende Gridprüfung eines
Rotationskandidaten. Auch `audio_confirmed` ersetzt weder den aktiven
Rekordbox-Anker noch bestehende Freigaben und beweist keine musikalische Takt-1-Wahrheit.

**Stand 71 (2026-10-14):** PSSI/PQTZ-Phrasen werden nur aus eindeutig
zugeordneten ANLZ-Dateigruppen gebildet. Fehlender Dateistamm ist nur bei je
einem passenden EXT- und DAT-Kandidaten zulaessig; Mehrdeutigkeit liefert keine
Phrasen. Alte Phrase-/Mix-Ergebnisse werden durch den Cache-Bump verworfen.

**Stand 72 (2026-10-14):** Bei schwacher Phrasenphasen-Konfidenz darf die
Audio-Novelty-Messung im bestaetigten Beatgrid die Genre-Prior-Phrasenlaenge
bestimmen. Fast- und Vollpfad muessen dieselbe gemessene Einheit bis
Mixpunkten und Kandidaten verwenden; gesperrte oder unbestaetigte Raster
behalten den Genre-Prior.

**Stand 73 (2026-10-15):** `Track.phrase_unit_source` persistiert, ob die
Phrasenlaenge aus Audio-Novelty, dem Genre-Prior oder einer konfigurierten
Vorgabe stammt. Alte Cachezeilen enthalten dieses Provenienzfeld nicht.

**Stand 74 (2026-10-15):** Der beste Novelty-Kandidat, dessen rohe Korrelation
und der prior-adjustierte Abstand zum Zweitkandidaten werden gespeichert.
Die Werte sind keine Wahrscheinlichkeiten. Ungueltige Werte werden vom Cache-
Vertrag abgelehnt.

**Stand 75 (2026-10-15):** Diagnose-Schema v6 bindet Phrasenlaenge, Quelle,
Kandidat, Rohscore und Margin; Cachevalidierung verlangt Gleichheit mit den
entsprechenden Trackfeldern.

**Stand 76 (2026-10-15):** Genreprofil-Phrasenlaengen werden in beiden
Analysepfaden als `genre_prior` gespeichert, auch wenn die interne API sie
explizit weitergibt. Externe explizite Einheiten bleiben `configured`.
Messschema v6 bleibt unveraendert; die Cacheversion verhindert alte
fehlklassifizierte Provenienzwerte.

**Stand 79 (2026-10-15):** Die persistierte Rekordbox-Taktpositionsdiagnose
speichert `reference_constant_offset`, wenn sie einen konstanten Grid-Offset
erkennt. Das ist nur ein Diagnosegrund: Grid und Anker bleiben unveraendert;
Sync-Gates erhalten keine Freigabe. Alte Cachezeilen enthalten diesen Grund
nicht und werden durch den Versionswechsel neu analysiert.

**Stand 70 (2026-10-14):** Ein schema-v5-validierter, einheitlicher
`candidate_rotation`-Befund sperrt vorsorglich PSSI-/Phrasenausgaben,
Mixpunkte und -kandidaten sowie Takt-1-/Cue-Export. Beat-Anker und Beat-Sync
bleiben erhalten. Die Sperre ist eine Nutzungsentscheidung bei widersprüchlichen
Taktpositionshinweisen, kein Nachweis musikalischer Richtigkeit.

## Speicherort

```
CACHE_FILE = HPG_CACHE_FILE                       # Env, hoechste Prioritaet
           | HPG_CACHE_DIR/hpg_cache_v77.db       # Env
           | %LOCALAPPDATA%\HPG\hpg_cache_v77.db  # Standard Windows
           | ~/.hpg/hpg_cache_v77.db              # Fallback
LOCK_FILE  = <cache ohne .db> + ".lock"
```

Alles wird **absolut aufgeloest** — relative Pfade erzeugten sonst
CWD-abhaengige Split-Brain-DBs. Fuer Tests: `HPG_CACHE_FILE` setzen, nie die
Produktiv-DB anfassen.

## Cache-Key

`generate_cache_key(file_path, source_signature)` [hpg_core/caching.py]:

```
normcase(abspath(normpath(pfad))) - st_size - st_mtime - st_mtime_ns - st_ctime_ns
[ - source-<rekordbox_signature> ]
```

`rekordbox_signature` ist wichtig: Rekordbox-BPM/Key/Cues koennen sich
**ohne** Aenderung der Audiodatei aendern. Deshalb wird die Signatur *vor* dem
Cache-Lookup geholt: `rekordbox_signature` entsteht in `analyze_track`
[hpg_core/analysis.py], erst danach greift `get_cached_track`
[hpg_core/caching.py].

Der Key enthaelt **keinen** Algorithmus-Hash. Deshalb ist der `CACHE_VERSION`-
Bump der einzige Weg, Code-Aenderungen zu invalidieren.

## Robustheit

- SQLite mit WAL, `PRAGMA foreign_keys=ON`, Retry auf BUSY/LOCKED
  (`SQLITE_RETRY_DELAYS`), `file_lock` mit `CACHE_LOCK_TIMEOUT = 15.0`
- `validate_track_dict` prueft alle 60 Pflichtfelder; jeder Mix-Kandidat muss
  alle 28 Vertragsfelder mit gueltigen Typen, Wertebereichen und Listen haben
- `track_to_dict` erstellt ausschliesslich den tief losgeloesten Snapshot
- `cache_track` ruft danach `_normalize_cache_snapshot` fuer die explizit
  tolerierte feldabhaengige NaN/Inf-Semantik und `validate_track_dict` fuer
  alle harten Vertragspruefungen auf; Fehler werden als
  `CacheValidationError` abgewiesen
- ungueltige Zeile beim Lesen -> `_quarantine_cache_row_on_connection`,
  Zeile wird aus `cache` entfernt, Funktion liefert `None` (= Miss,
  Neuanalyse)
- bestaetigt korrupte DB -> `_quarantine_corrupt_cache` [hpg_core/caching.py]

## Geschuetzte Dateien

`hpg_cache_v*.db`, `*.db-wal`, `*.db-shm`, `*.lock`, `track_cache.*` — **nie
editieren oder loeschen ohne Ankuendigung**. Zum Inspizieren gibt es
`tools/_inspect_cache.py` und `tools/_check_cache.py` (read-only).

## Neues Track-Feld hinzufuegen

1. Feld in `models.Track` mit sinnvollem Sentinel (`-1.0` wenn `0.0` gueltig
   waere)
2. `track_to_dict` / `dict_to_track` [hpg_core/caching.py] pruefen — sie sind die
   Serialisierungsgrenze
3. `validate_track_dict` erweitern, falls numerisch/endlich
4. `CACHE_VERSION` bumpen + Kommentar
5. Alt-Cache-Verhalten testen: was liefert das Feld fuer Rows ohne den Wert?

## Common Mistakes

- `CACHE_VERSION` in `config.py` suchen.
- Bump vergessen -> "Fix wirkt nicht", stundenlanges Falschdebuggen.
- Produktiv-DB im Test benutzen statt `HPG_CACHE_FILE`.
- Sentinel `0.0` waehlen fuer ein Feld, bei dem `0.0` ein gueltiger Wert ist.

Cache 100 behaelt die Cache99-Rasterrettung bei. Vorhandene erfolgreiche Modell-Decoderfenster werden auch bei hoher DSP-Phrasenkonfidenz gegen Audio geprueft; der bisherige vorzeitige baseline_preferred-Abbruch gilt nur noch ohne solche Kandidaten. Uebernahme weiterhin nur mit allen bestehenden Konsistenz-/Audiogates. Alte Analysewerte werden nicht als neu geprueft wiederverwendet.

Cache 101: nativer Rekordbox-Beatdecoder mit eigenem Herkunftsvertrag; alte HPG-Rotationsscores werden nicht als native Ergebnisse gelesen.

Cache 102: native Beatzeiten aus Samplepositionen statt nativen msec-Hilfsfeldern; diese können bei nativen Endergänzungen widersprüchlich sein. Produktivcache nicht manuell ändern.

Cache 103: native_beat_analysis speichert den vollständigen nativen Modell-/Endgrid-Lauf samt Herkunft. Aktive Übernahme verlangt unveränderte BPM/Takt-Eins und bestätigte Audio-Synchronität.

Version104: native Rohgrids unverändert; optionale Audio-Zeitkorrektur mit sechs disjunkten Messfenstern und eigener Ankerherkunft persistieren.
