# Plan: Echte Downbeat-Erkennung (Phrase-Anker)

**Datum:** 2026-07-17
**Ziel:** Neues Track-Feld `first_downbeat` (Sekunden, Zeitpunkt der ersten „1") verankert das gesamte Takt-/Phrasen-Raster — heute rastern alle Quantisierungen arithmetisch ab t=0, was bei Tracks, die nicht exakt auf der 1 starten, alle Mixpoints und den Preview-Beat-Versatz verfälscht.

## Recherche-Grundlage (Web-Recherche 2026-07-17, Quellen im Bericht)

- **librosa hat keine Downbeat-Erkennung** (nur beat_track). madmom (Standard-Tool) ist auf Python ≥3.10 **kaputt** (letztes Release 2018); `madmom-prebuilt`-Fork ungeprüft. „Beat This!" (ISMIR 2024, SOTA: Harmonix Downbeat-F1 90,7) zieht PyTorch (~200 MB) — als Pflicht-Dependency ungeeignet.
- **Gewählter Ansatz: leichtgewichtige Eigenimplementierung nach Vande Veire (EURASIP 2018)** — dort 98,1 % korrekte Downbeat-Phase auf elektronischer Musik mit demselben Prinzip: Beat-Raster + **Phase-Voting über den ganzen Track** (4 Hypothesen). Features: Low-Frequency-Onsets (Hockman ISMIR 2012: allein 72,8 %), spektrale/Chroma-Novelty an Taktgrenzen (Davies/Plumbley-Prinzip: Harmoniewechsel auf der 1), Loudness-Akzent. Leise Passagen (Intro/Breakdown) werden vor dem Voting getrimmt.
- **Rekordbox-Bonus:** Die ANLZ-Analysedateien (.DAT) enthalten im **PQTZ-Tag** den echten Beatgrid (`AnlzQuantizeTick`: beat 1..4 + Zeit in ms). Erster Eintrag mit `beat == 1` = exakter first_downbeat — für Rekordbox-Tracks genauer und billiger als jede eigene Erkennung.
- Erwartete Genauigkeit Eigenimplementierung auf Four-on-the-floor: ~80–90 % (Schätzung); mit Konfidenz-Ausgabe, damit unsichere Fälle erkennbar bleiben. Wichtigste Eigenschaft laut Praxis-Recherche: EINE konsistente Phase pro Track (kein Springen) — genau was track-weites Voting liefert.

## Design

### Neues Modul `hpg_core/downbeat.py`
`estimate_first_downbeat(y, sr, bpm) -> (first_downbeat, confidence)`:
1. `librosa.beat.beat_track(start_bpm=bpm)` → Beat-Raster
2. Trim: Beats mit Beat-RMS < 0,3 × Max ausschließen (Vande-Veire `trimAudio`)
3. Pro Beat 3 z-normierte Scores: Bass-Onset (Mel ≤ 160 Hz), Chroma-Novelty an der Beatgrenze, Loudness-Akzent
4. Voting über 4 Phasen-Hypothesen (Gewichte 1,0 / 1,0 / 0,5), argmax = Phase
5. `first_downbeat` = erster Beat der Gewinner-Phase; `confidence = (V1 − V2) / Σ|V|`
6. Fehler/zu kurz → `(0.0, 0.0)` = Verhalten wie heute

### Datenfluss
- `Track.first_downbeat: float = 0.0` + `Track.downbeat_confidence: float = 0.0` (Cache round-trippt generisch; alte Einträge → Default 0.0)
- **Fast-Path:** zuerst ANLZ-PQTZ versuchen (rekordbox_importer liest AnalysisDataPath, lazy geparst; Konfidenz 1.0), sonst eigene Schätzung
- **Full-Path:** eigene Schätzung nach finaler BPM-Bestimmung
- `CACHE_VERSION` 15 → 16

### Anker-Verkabelung (zentraler Helper statt 10 Einzel-Edits)
`models.quantize_to_grid(t, grid, anchor=0.0, mode="round"|"ceil"|"floor")` — Formel `(t − anchor)/grid → quantisieren → + anchor`. Bei `anchor=0.0` bit-identisch zu heute (Backward-Compat, alle Bestandstests bleiben gültig). Migrierte Stellen:
- `calculate_genre_aware_mix_points` (+ Helfer, Re-Quantisierung, min_mix_in = max(intro_end, anchor + grid))
- `align_ai_mix_points` (Cue-/AI-Override)
- `calculate_paired_mix_points` (Bar-Guards, nutzt `track.first_downbeat` direkt)
- `structure_analyzer._quantize_to_bars` / `analyze_structure` (Anker-Parameter)
- `transition_renderer`: `TransitionClipSpec.first_downbeat_a/b`; `_align_beat_phase` nutzt bekannte Downbeats (Bar-Phase statt Beat-Phase), Laufzeit-Schätzung nur noch als Fallback
- `rekordbox_xml_exporter`: `Inizio=track.first_downbeat` (war hartkodiert 0.0)

### Semantik-Entscheidung: Bar-Anzeige
`mix_in_bars`/`mix_out_bars` zählen weiterhin ab Track-Start (t=0) — konsistent mit Waveform-Anzeige. Der Anker verschiebt nur das RASTER der Punktwahl. Dokumentiert in models.py.

## Tests
- Neu `tests/test_downbeat.py`: synthetischer 128-BPM-Track mit akzentuierter „1" bei bekanntem Offset → Erkennung ±1 Beat-Toleranz; Stille/zu kurz → (0,0); Konfidenz-Verhalten
- Neu: anchored-Quantisierungs-Tests für `quantize_to_grid` und `calculate_genre_aware_mix_points(anchor≠0)`
- Bestandstests: bleiben unverändert grün (anchor-Default 0.0)

## Verifikation
Volle Suite + Import-Smoke + synthetische Downbeat-Matrix (mehrere BPM × Offsets).
