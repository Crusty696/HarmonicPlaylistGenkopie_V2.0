---
name: hpg-rekordbox
description: Use when working on HPG Rekordbox integration — RekordboxImporter, master.db, pyrekordbox, ANLZ/PQTZ-Beatgrid, get_first_downbeat, Cue-Points und Cue-Override, rekordbox_signature, Fast-Path, oder den Rekordbox-XML-Export.
---

# HPG Rekordbox

## Zwei Richtungen

**Import** (`hpg_core/rekordbox_importer.py`): liest die lokale
Rekordbox-`master.db` ueber `pyrekordbox`. Liefert BPM, Key, Genre, Dauer,
Cues und den ANLZ-Beatgrid. Optional — fehlt `pyrekordbox` oder die DB,
laeuft alles ueber librosa weiter.

**Export** (`hpg_core/exporters/rekordbox_xml_exporter.py`): schreibt
Collection + Playlist mit BPM, Key, TEMPO-Beatgrid und POSITION_MARK-Cues.

`get_rekordbox_importer()` [:577] ist ein Singleton — nicht pro Track neu
instanziieren, der Cache-Aufbau scannt die ganze DB.

## Fast-Path

Liefert der Importer BPM, nimmt `analyze_track` den Fast-Path: BPM/Key/Genre
aus der DB, librosa nur `LIBROSA_FAST_PATH_DURATION = 360` s fuer Energy und
Genre-Features, `key_confidence = 1.0`. Rund 12x schneller — beim Optimieren
nicht kaputtmachen.

## Mehrdeutigkeit: lieber nichts als falsch

Die reale lokale `master.db` hatte 2665 Content-Zeilen mit 77 doppelten
normalisierten Pfaden und 60 mehrdeutigen Basenames. Der Importer loest das
so [`_build_track_cache` :143]:

| Fall | Verhalten |
|---|---|
| gleicher Pfad, **widerspruechliche** Felder (`_track_data_conflicts` :274) | Pfad landet in `_ambiguous_paths`, `get_track_data` liefert `None` |
| gleicher Pfad, ein Record klar besser analysiert (`_track_data_quality` :266) | besserer Record gewinnt (z. B. gegen BPM `0`) |
| gleicher Basename, mehrere Dateien | `basename_cache`-Eintrag wird `None` -> Fallback verworfen |

`get_statistics()` und `get_available_count()` zaehlen nur eindeutige Pfade.
**Regel: bei Zweifel `None` zurueckgeben.** Falsche Metadaten sind schlimmer
als gar keine — sie fliessen still in BPM, Key und Mixpoints.

## Zeit-Einheiten — der teuerste Fehler

Rekordbox speichert Beatgrid- und Cue-Zeiten in **Millisekunden**.
`_milliseconds_to_seconds` [:473] ist die einzige Konvertierung
(`/1000.0`, gerundet auf 4 Stellen, negative und nicht-endliche Werte ->
`None`). Eine frueher benutzte Heuristik "Wert > 100 also Millisekunden" hat
`120` als 120 Sekunden interpretiert.

## ANLZ-Beatgrid

`get_first_downbeat(file_path)` [:354] -> `_read_anlz_files(content_id)`
[:447] -> `_extract_first_downbeat_from_anlz`: sucht in den ANLZ-Dateien die
Tags `PQTZ`, `PQT2`, `beat_grid`, `beats` und darin den ersten Tick mit
`beat == 1`. Zwei Tag-Formen werden unterstuetzt (flache Parallel-Listen
`.beats`/`.times` **und** iterierbare Entries mit `.beat`/`.time`) —
pyrekordbox liefert je nach Version unterschiedliche Formen; RB-01 war genau
hier ein still toter Pfad.

`_read_anlz_files` ist der gemeinsame Leser fuer alle ANLZ-Dateien
(DAT/EXT/2EX) eines Tracks — probiert `db.read_anlz_files(content_id)`, dann
`db.read_anlz_file(content_id, "DAT")`; beide `get_first_downbeat` und
`get_phrases` gehen darueber, damit es nur eine robuste Leseroutine gibt.

Treffer -> `downbeat_confidence = 1.0`. Nur damit greift der exakte
Beat-Alignment-Pfad im Renderer (`downbeat_reliable_* = conf >= 0.9`).

**Vertrag:** der Importer liefert ausschliesslich den **Takt**-Anker
`first_downbeat`. Der Phrasen-Anker entsteht downstream — Skill
`hpg-mixpoint-engineering`.

## PSSI-Phrasen (`get_phrases`, [:483])

`get_phrases(file_path)`, memoisiert je `content_id`: holt ueber
`_read_anlz_files` die EXT-Datei mit dem `PSSI`-Tag und die DAT-Datei mit dem
`PQTZ`-Tag, delegiert an `rekordbox_phrases.phrases_from_anlz`. Leer, wenn
kein Rekordbox-Eintrag, keine EXT-Datei oder kein PSSI-Tag vorliegt.

`phrases_from_anlz` (`hpg_core/rekordbox_phrases.py`) liest die Phrasengrenzen
aus PSSI und die Zeiten aus dem PQTZ-Beatgrid: `entry.beat` ist ein
**1-basierter Index** in die PQTZ-Beatliste (verifiziert an 699 von 2475
EXT-Dateien; 0-basiert passt nie; der erste Eintrag liegt im Vollbestand
(2470 DAT) in 677 Faellen auf beatnum 2, 74x auf 3, 70x auf 4). Zwei
Label-Tabellen je nach PSSI-`mood`:
`PHRASE_LABELS_HIGH` (mood 1: Intro/Up/Down/Chorus/Outro) und
`PHRASE_LABELS_MIDLOW` (mood 2/3: Intro/Verse 1-6/Bridge/Chorus/Outro).
Rohe Beatgrid-Floats, keine Rundung — dieselbe 3-ms-Falle wie beim
Mix-In-Rundungsfehler (`hpg-mixpoint-engineering`).

## Cue-Override (liegt in analysis.py, nicht im Importer)

`analysis.py:1712`. Wortgrenzen-Regex, **nicht** Substring:

```
IN : \b(MIX[- ]?IN|IN|START)\b
OUT: \b(MIX[- ]?OUT|OUT|OUTRO|END)\b
```

`INTRO` markiert den Intro-START und ist bewusst **kein** Mix-In.
`BREAKDOWN` darf kein OUT ausloesen. Erster Treffer gewinnt (deterministisch).
Nur **benannte** Cues (`provenance == "manual"`) zaehlen.

Die Positionsheuristik fuer unbenannte Hot-/Memory-Cues ("2. Cue = Mix-In,
letzter = Mix-Out") ist entfernt (Spec 2026-08-21) — unbenannte Cues sind
jetzt Kandidaten (`mix_candidates.py`), kein Override mehr. Damit entfaellt
auch der zugehoerige Intro-Guard `cue_in_verwerfen`; die Funktion bleibt im
Modul, wird im Produktivpfad aber nicht mehr gerufen.

Uebernommen wird nur bei `0 <= in < out <= duration`, und **immer** durch
`align_ai_mix_points(..., anchor=phrase_anchor)` quantisiert.

## Cache-Invalidierung

`get_track_signature(file_path)` [:521] geht in den Cache-Key ein. Rekordbox-
Metadaten aendern sich ohne Aenderung der Audiodatei — ohne Signatur liefert
der Cache still alte BPM/Key/Cues. Siehe `hpg-cache-persistence`.

## Export

`export()` [:106] legt die Playlist ueber
`add_playlist_folder("HPG Playlists").add_playlist(...)` an — `get_playlist()`
wirft auf frischem XML immer `ValueError`. `_add_beat_grid` [:268] schreibt
`TEMPO` mit `Inizio=first_downbeat`. `_add_cue_points` [:300] schreibt
POSITION_MARKs, aber nur wenn `_cue_export_allowed` [:342] haelt
(`outro_covered` und `duration > 0`).

## Verifikation

`tests/test_rekordbox_importer.py` (62 Tests) deckt Pfadkonflikte,
analysierte-vs-unanalysierte Duplikate und mehrdeutige Basenames ab.
`tests/test_rekordbox_xml_exporter.py` den Export. Fuer echte DB-Laeufe:
`benchmark_rekordbox.py`.

## Common Mistakes

- Zeitwerte ohne `_milliseconds_to_seconds` uebernehmen.
- Bei Mehrdeutigkeit "den ersten Treffer" nehmen.
- Cue-Namen per Substring matchen.
- Cue-Override roh setzen ohne Quantisierung.
- Die entfernte Positionsheuristik ("2. Cue = Mix-In") wiederbeleben statt
  `mix_candidates.py` zu erweitern.
- Neuen Importer pro Track bauen statt `get_rekordbox_importer()`.
- Nur eine ANLZ-Tag-Form unterstuetzen.

## XML-Export mit Kandidaten (Teil 4, gebaut 2026-08-22)

`RekordboxXMLExporter.export(playlist, path, name, transitions=None)`: mit
Empfehlungen schreibt `_kandidaten_punkte` je Playlist-Position MIX OUT aus
`transitions[i].plan.mix_out_a`, MIX IN aus `transitions[i-1].plan.mix_in_b`
(nur bei `kandidat_aktiv > 0`), dazu Memory-Cues `HPG K<n> OUT|IN <schema>`
(`_kandidaten_cues`: n je Seite fortlaufend 1..6 nach Dedupe gleicher
Zeitpunkte — nicht `PairCandidate.rang`). `_cue_export_allowed(track, mix_in,
mix_out)` prueft die effektiven Punkte; Gate `outro_covered` bleibt.
