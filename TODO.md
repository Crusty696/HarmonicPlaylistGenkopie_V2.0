# TODO: Advanced Audio Analysis Integration

- [x] **Phase 1: Datenmodell-Erweiterung** [backend]
  - [x] TrackSection Dataclass in `hpg_core/models.py` erweitern
    - [x] vg_bass: float = 0.0 hinzufuegen
    - [x] vg_mids: float = 0.0 hinzufuegen
    - [x] vg_highs: float = 0.0 hinzufuegen
    - [x] percussive_ratio: float = 0.0 hinzufuegen
    - [x] spectral_flatness: float = 0.0 hinzufuegen
  - [x] Track Dataclass in `hpg_core/models.py` erweitern
    - [x] 	imbre_fingerprint: list = field(default_factory=list) hinzufuegen

- [x] **Phase 2: Core Analyse-Engine** [backend] [parallel]
  - [x] **Frequenz-Baender Implementierung**
    - [x] STFT-Logik in `hpg_core/analysis.py` integrieren
    - [x] Frequenz-Bins fuer Bass (20-200Hz), Mitten, Hoehen definieren
    - [x] Energie-Integration pro Band und Sektion berechnen
  - [x] **Rhythmische Komplexitaet**
    - [x] HPSS-Trennung (Harmonic/Percussive) integrieren
    - [x] Berechnung der `percussive_ratio` pro Sektion
    - [x] `spectral_flatness` Metrik hinzufuegen
  - [x] **Timbre-Fingerprinting**
    - [x] MFCC-Berechnung ueber den gesamten Track
    - [x] Kompakter Fingerabdruck-Vektor (Mean MFCC) generieren

- [x] **Phase 3: DJ Brain Integration & Scoring** [backend]
  - [x] **Verfeinerung des Mix-Scorings**
    - [x] Bass-Energie in `calculate_paired_mix_points` einbeziehen
    - [x] Warnungen bei Bass-Kollisionen in `DJRecommendation` hinzufuegen
  - [x] **Klangfarben-Abgleich**
    - [x] Aehnlichkeits-Berechnung (Cosine Similarity) fuer Timbre-Fingerprints
    - [x] Texture-Match-Bonus im Playlist-Algorithmus implementieren

- [x] **Phase 4: Validierung & Tests** [test]
  - [x] Unittests fuer Frequenz-Extraktion erstellen
  - [x] Vergleichstest mit realen Tracks aus `D:\beatport_tracks_2025-08` durchfuehren
  - [x] Performance-Impact der erweiterten Analyse messen

