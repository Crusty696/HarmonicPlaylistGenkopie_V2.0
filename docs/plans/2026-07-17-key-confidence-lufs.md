# Plan: Key-Confidence + LUFS-Loudness (Gain-Matching)

**Datum:** 2026-07-17
**Research:** Web-Recherche mit Quellcode-/Paper-Verifikation (Essentia key.cpp, Sha'ath-Thesis/KeyFinder, MIREX-Fehlerklassen, EBU R128/BS.1770, pyloudnorm-Compliance-Paper, ReplayGain 2.0/Mixxx).

## Feature 1: Key-Confidence

**Erkenntnis:** Essentia ist die einzige quellcode-belegte Referenz und liefert ZWEI Metriken: `strength` (absolute Pearson-Korrelation des Gewinners) und `firstToSecondRelativeStrength` = (max−max2)/max (Marge). Kommerzielle DJ-Tools (MIK, rekordbox) zeigen keinerlei Konfidenz — Feature ist ein Differenzierungsmerkmal. MIREX-Fehlerklassen: Quint- (±1 Camelot) und relative-Dur/Moll-Fehler (gleiche Nummer) sind fürs Harmonic Mixing harmlos; nur parallele/entfernte Fehler schaden.

**Umsetzung:**
- `analysis.get_key_with_confidence()` → (note, mode, strength, margin, second_note, second_mode); `get_key()` delegiert (API stabil).
- `analysis.key_confidence_score()`: strength ≥ 0.6 UND margin ≥ 0.05 → sicher; sonst Zweitkandidaten-Check — ist er Camelot-Nachbar (Quinte/relative), quasi-sicher (≥ 0.5); sonst unsicher (≤ 0.4). Schwellwerte heuristisch (offiziell existieren keine — explizit dokumentiert).
- `Track.key_confidence` (0.0 = unbekannt/Alt-Cache; 1.0 = Key aus Rekordbox-DB).
- Risk-Note in `_assess_transition_risks` bei Konfidenz < `KEY_CONFIDENCE_UNCERTAIN` (0.5).
- Bewusst KEINE Ranking-Änderung in calculate_compatibility (Konfidenz informiert, verzerrt aber nicht die Sortierung — separat evaluierbar).

## Feature 2: LUFS-Loudness

**Erkenntnis:** pyloudnorm (MIT, nur numpy/scipy, py3.12-ok) ist mit `filter_class="DeMan"` laut Paper voll BS.1770-konform bei jeder Samplerate (gegen ITU-BS.2217-Material validiert). Referenzwert: **−18 LUFS** (ReplayGain 2.0, Mixxx) — rekordbox-Zielwert ist unveröffentlicht. JND ≈ 1 dB, korrekturbedürftig ≥ 3 dB.

**Umsetzung:**
- Neue Dependency `pyloudnorm>=0.1.1` (requirements.txt; verifiziert: −18 dBFS-997-Hz-Sinus → −21,01 LKFS = exakter BS.1770-Sollwert).
- `analysis.calculate_lufs(y, sr)` → Integrated LUFS, Sentinel 0.0 (kommt bei Musik nicht vor).
- `Track.lufs`; gemessen in beiden Analyse-Pfaden (Fast-Path: 360-s-Ausschnitt — für Gain-Matching ausreichend, dokumentiert).
- `DJRecommendation.gain_advice` via `_gain_advice()`: Anzeige ab 1 dB (JND), Warnhinweis ab 3 dB; Risk-Note bei ≥ 3 dB.
- Config: `LUFS_REFERENCE = -18.0`, `GAIN_DIFF_SHOW_DB = 1.0`, `GAIN_DIFF_WARN_DB = 3.0`.

**Bewusste Entscheidung Renderer:** Der Transition-Preview normalisiert bereits beide Crossfade-SEGMENTE per RMS aufeinander — das entspricht dem von der Praxis empfohlenen Mix-Moment-Matching (lautester Abschnitt zählt, nicht der Track-Durchschnitt). Integrated-LUFS-Gain obendrauf wäre eine Doppel-Korrektur → Renderer bleibt unverändert; LUFS dient Advice, Risiko-Warnung und künftigem Auto-Gain/Export.

## Cache & Tests

- `CACHE_VERSION` 16 → 17 (neue Felder werden bei Analyse gefüllt).
- tests/test_key_confidence_lufs.py: eindeutige vs. mehrdeutige Chroma-Vektoren, Nachbar-Logik (relative/Quinte), LUFS-Sinus-Referenzwert (±0,5 LU), Stille/kurz → Sentinel, gain_advice-Schwellen.
