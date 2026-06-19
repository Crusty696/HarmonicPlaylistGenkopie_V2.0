# Plan: Advanced Audio Analysis Integration

## Ziel
Implementierung von Frequenz-Bändern, rhythmischer Komplexität und Timbre-Alignment zur Steigerung der Mix-Qualität.

## Phasen

### Phase 1: Datenmodell ([backend])
- [ ] Neue Felder in hpg_core/models.py hinzufügen.
  - TrackSection: avg_bass, avg_mids, avg_highs, percussive_ratio, spectral_flatness.
  - Track: timbre_fingerprint.

### Phase 2: Analyse-Logik ([backend] [test])
- [ ] Frequenz-Band-Extraktion in hpg_core/analysis.py implementieren (STFT).
- [ ] HPSS-basierte Perkussions-Analyse implementieren.
- [ ] MFCC-Fingerprinting für Timbre integrieren.
- [ ] Tests für die neue Analyse-Pipeline erstellen.

### Phase 3: DJ Brain Upgrade ([backend])
- [ ] Scoring-Algorithmus in hpg_core/dj_brain.py aktualisieren.
- [ ] Bass-Kollisions-Warnungen implementieren.
- [ ] Texture-Match-Score basierend auf MFCCs einführen.
