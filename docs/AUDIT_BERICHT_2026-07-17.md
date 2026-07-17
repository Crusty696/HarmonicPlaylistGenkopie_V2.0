# Audit-Bericht HPG V2.0 — Komplettuntersuchung mit Fokus DJ-Fähigkeiten

**Datum:** 2026-07-17 (aktualisiert nach Fix-Runde + Audit Runde 2)
**Methode:** Runde 1: 3 parallele Deep-Audit-Agenten (DJ-Kernlogik, Playlist/Harmonik, Analyse-Pipeline). Danach: alle Findings gefixt. Runde 2: 3 weitere Agenten (adversariale Fix-Verifikation via git diff, main.py/GUI-Tiefenaudit, DJ-Fachsemantik-Tiefe) — deren Findings ebenfalls gefixt.
**Testsuite final:** **1246 passed, 0 failed**, Coverage ~79 % (venv312/Python 3.12). `CACHE_VERSION` auf 14 erhöht.

---

## STATUS: Alle Findings beider Runden gefixt

Jedes unten gelistete Finding aus Runde 1 (C1-C2, H1-H8, M1-M14, LOWs) wurde am 2026-07-17 gefixt und durch die Suite + adversariale Fix-Verifikation (Agent, git-diff-Review) bestätigt. Einzige bewusste Nicht-Änderung: M5 (dj_brain `_find_mix_out_point`) — die Analyse des Agenten war falsch (`min` auf `-end_time` wählt die SPÄTESTE main-Section, musikalisch korrekt).

### Runde-2-Findings (alle gefixt)

**main.py / GUI:**
- **HIGH** `logger`-NameError im TransitionRenderWorker-Fehlerpfad → Modul-Logger ergänzt.
- **HIGH** Kein Doppelstart-Schutz für AnalysisWorker (Ctrl+G umgeht Button-Disable) → isRunning()-Guard.
- **HIGH** Laufender AI-Worker wurde bei Re-Analyse verwaist (`ai_worker = None` vor dem isRunning-Check) → Zuweisung entfernt.
- **HIGH** closeEvent beendete AI-Worker nicht (QThread-Crash beim App-Close) → Cancel+wait+terminate ergänzt.
- **MEDIUM** O(n)-Qualitäts-Neuberechnung pro AI-Ergebnis im UI-Thread → entfernt (Endberechnung genügt).
- **MEDIUM** Offline-Warnung hardcodiert "Ollama Port 11434" auch bei LM Studio → provider-abhängig.
- **LOW** `.replace(".xml", ".m3u8")` ersetzte alle Vorkommen im Pfad → `os.path.splitext`.

**Playlist/Scoring:**
- **HIGH** `calculate_enhanced_compatibility` hatte KEINEN BPM-Hard-Gate — unmixbare Sprünge (128→174) bekamen via Genre+Energie ~42 % → Gate nachgerüstet (overall=0).
- **MEDIUM** kwargs-Kette brach im Enhanced-/Emotional-Journey-Pfad — `harmonic_strictness`/`allow_experimental` aus der UI wirkten dort nicht → durchgereicht.
- **MEDIUM** Context-Flow-Boni (bis +33) überstimmten ganze Camelot-Stufen (Diagonal 60 schlug Adjacent 80) → kalibriert auf max +19 (< eine 20-Punkte-Stufe).
- **MEDIUM** `base_genre_compatibility` war zu ~78 % totes Vokabular (Electronic/Hip Hop/Rock…) → auf kanonische Klassifikator-Labels umgeschrieben.
- **LOW** `peak_count=0`-Edge duplizierte bei Mini-Playlists die ganze Liste → Guard.

**DJ-Brain:**
- **MEDIUM** Half/Double-Übergang bekam +4 Bars MEHR Blend-Zeit (fachlich verkehrt — Half-Time wird kurz gecuttet) → Cap auf 16 Bars.
- **MEDIUM** Toter `elif bass_b > 80`-Zweig im Risk-Assessment → unabhängige Checks.
- **MEDIUM** Cross-Genre-Fallback generisch trotz Kompatibilitäts-Matrix → compat-abhängige Bridge-Warnungen.
- **MEDIUM** Texture-Similarity mass faktisch Lautheit (MFCC-0 dominierte) → MFCC-0 verworfen.
- **LOW** `_key_advice` nannte +4/+7-Techniken "Key-Clash", obwohl die Engine sie belohnt → eigener Zweig.

**Struktur-Analyse:**
- **HIGH** Speicher-Bombe: dense recurrence_matrix O(n²) — 10-Min-Track ≈ 1,3 GB → MFCC-Dezimierung auf max. 3000 Frames (≈72 MB), Zeitachsen konsistent skaliert.
- **MEDIUM** `phrase_unit`-Parameter in `_quantize_to_bars` war ungenutzt (versprochene Phrasen-Quantisierung fand nicht statt) → Sub-Phrasen-Gitter (halbe Phrase: Psy/Trance 8 Bars, sonst 4).

**Rekordbox-Import:**
- **HIGH** Gesperrte/verschlüsselte DB nur generisch geloggt → differenzierte Hinweise ("Rekordbox schließen" vs. "Key via `python -m pyrekordbox download-key`").
- **MEDIUM** BPM/100-Heuristik ohne Sanity-Range (1.36-BPM-Tracks möglich) → Range-Check 40-250 mit Raw-Fallback.
- **MEDIUM** Cues mit `InMsec = -1/None` landeten als Cue bei −0,001 s → gefiltert.
- **LOW** Stille Key-Konvertierungs-Verluste → Debug-Log.

**Sonstiges:**
- Cue-Regex um `OUTRO` erweitert (gängiger Mix-Out-Cue-Name); `INTRO` bewusst NICHT als Mix-In (markiert Intro-START).
- ID3-Map: "afro house"/"organic house" → Deep House (statt Melodic Techno), "breakbeat"-→-DnB-Mapping entfernt (BPM-fachlich falsch).

### Bewusst offen gelassen (kein Fix nötig / Design-Entscheidung)

- Sprachmix (Deutsch/Englisch) in Cross-Genre-Advice-Texten — kosmetisch.
- UI zeigt Enhanced-% während Sortierung 0-100-Score nutzt — Anzeige-Design, dokumentiert.
- Techno-Flat-Energy-Labeling (relative Schwellen finden bei durchgehend lautem Techno kaum Drops) — Heuristik-Grenze, bräuchte anderes Verfahren.
- Basename-Kollision im Rekordbox-Fallback-Lookup bei Duplikat-Dateinamen — selten, dokumentiert.
- `error_reporter.get_recent_errors` ohne UI-Anzeige — halb-totes Feature, Kandidat für Feature-Arbeit.
- Fehlende Profi-Features unverändert (siehe Abschnitt 8): echte Downbeat-Erkennung (persistiert), LUFS-Loudness, Key-Confidence, globaler Playlist-Optimierer. Neu seit heute: Beat-Phase-Alignment im Preview-Renderer + Beatgrid/HotCue-Export als erste Schritte.

---

## Executive Summary

Die Codebasis ist nach den Fix-Runden vom 2026-07-16 in gutem Zustand: Testsuite grün, Camelot-Grundlogik korrekt, Sentinel-Handling sauber, Thread-Sicherheit in der GUI korrekt umgesetzt. **Aber:** Das Audit fand **2 CRITICAL-Bugs im Rekordbox-Fast-Path** (Einrückungsfehler, der Tracks ohne Key still verwirft, plus ein Performance-Killer, der den 12×-Fast-Path-Vorteil zunichtemacht) sowie **6 HIGH-Findings**, davon 3 direkt DJ-relevant (Cue-Override ohne Validierung, fehlendes Beat-Phase-Alignment im Transition-Preview, wirkungsloser `harmonic_strictness`-Regler).

Die größte fachliche Lücke gegenüber Profi-DJ-Praxis: **keine echte Downbeat-/Beatgrid-Erkennung** — alle Phrasen-Berechnungen rastern arithmetisch ab t=0, und der Transition-Renderer fügt Segmente ohne Beat-Phase-Alignment zusammen.

---

## 1. CRITICAL — sofort fixen

### C1 — Einrückungsfehler im Rekordbox-Fast-Path: Tracks ohne Key verschwinden still
**Ort:** `hpg_core/analysis.py:853-933`
Der Block „Advanced Audio Analysis" + die komplette `track = Track(...)`-Konstruktion (Z. 853–931) liegt durch falsche Einrückung **innerhalb** von `if rekordbox_data.camelot_code:` (Z. 839). Hat ein Rekordbox-Track keinen Camelot-Code, wird `track` nie erzeugt → `cache_track(cache_key, track)` (Z. 933) wirft `UnboundLocalError` → der Worker fängt die Exception und der Track wird **still verworfen** (erscheint nie in der Bibliothek). *Manuell im Code verifiziert.*

### C2 — Fast-Path lädt Audio trotzdem in voller Länge
**Ort:** `hpg_core/analysis.py:856`
Innerhalb des Fast-Path (der eigentlich nur DB-Metadaten + 360 s Audio nutzen soll) lädt die Advanced-Analyse die Datei via `librosa.load(..., duration=LIBROSA_MAX_DURATION)` (600 s) **ein zweites Mal**. Der dokumentierte 12×-Speedup existiert für Tracks mit Key faktisch nicht.

---

## 2. HIGH

| # | Finding | Ort |
|---|---------|-----|
| H1 | **Rekordbox-Cue-Override verletzt alle Mixpoint-Invarianten**: Cue-Positionen werden roh übernommen — kein Ordering-Check (`mix_in < mix_out`), kein Bounds-Check, kein Phrase-Alignment; überschreibt als letzter Schreibzugriff die validierten Werte. Mehrere IN/OUT-Cues → letzter gewinnt, nichtdeterministisch. | `analysis.py:794-805` |
| H2 | **Kein Beat-Phase-Alignment im Transition-Renderer**: Track A und B werden bei Sample 0 des jeweiligen Segments zusammengefügt; selbst bei identischem BPM liegen die Downbeats zufällig zueinander → hörbarer Beat-Versatz im Preview. Zentraler Qualitätsmangel der DJ-Funktion. | `transition_renderer.py:81-88, 141-143` |
| H3 | **Time-Stretch-Clamp verschluckt Tempo-Anpassung ohne Warnung**: `rate = max(0.85, min(1.15, rate))` — bei großem BPM-Delta (z. B. 128→174) läuft der Preview im falschen Tempo, ohne Log-Hinweis. | `transition_renderer.py:113` |
| H4 | **Camelot-Energie-Boost-Regeln sind toter Code**: `A→B = 85` / `B→A = 75` (Z. 281-284) sind unerreichbar, weil Z. 253-254 jeden Dur/Moll-Wechsel bei gleicher Nummer vorher mit 90 abfängt. Die beabsichtigte Richtungs-Asymmetrie (Energie-Boost/-Drop) existiert nicht. | `playlist.py:253, 281-284` |
| H5 | **`harmonic_strictness` praktisch wirkungslos** (bestätigt & präzisiert): wirkt nur auf den Fallback-Score (Range 5–14); alle regulären Kategorien (60–100) ignorieren ihn. UI-Regler erfüllt Nutzererwartung nicht. | `playlist.py:228, 287` |
| H6 | **`_sort_harmonic_flow_enhanced` ist O(n³)**: Lookahead depth=2 ohne Rekursions-Cache; bei bis zu 1000 Tracks (`SECURITY_MAX_PLAYLIST_SIZE`) potenzielle UI-Blockade. | `playlist.py:409-482` |
| H7 | **Cancel wird als Pool-Crash fehlinterpretiert**: `InterruptedError` aus dem Progress-Callback landet im äußeren `except Exception` → löst Safe-Mode-Reanalyse aller offenen Dateien aus statt sauber abzubrechen. | `parallel_analyzer.py:189-198` |
| H8 | **Cache-Key-Mismatch bei Forward-Slash-Pfaden**: Revalidierung nutzt rohen `file_path`, Cache-Key wurde mit `os.path.normpath` erzeugt → False-Cache-Miss, Track wird jedes Mal neu analysiert. | `caching.py:120, 150-152` |

---

## 3. MEDIUM (Auswahl, DJ-relevant zuerst)

| # | Finding | Ort |
|---|---------|-----|
| M1 | `overlap_seconds` wird unabhängig vom internen `target_overlap` berechnet; nach Outro-Guard-Verschiebung läuft der Crossfade über `intro_end_b` hinaus in den Body von Track B → genau die Bass-Kollision, die vermieden werden soll. | `dj_brain.py:570` vs. `750-759` |
| M2 | `calculate_paired_mix_points`: kein Lower-Bound auf `adjusted_mix_out_a` — kann bei frühem Outro negativ werden; Sentinel-Check `>= 0.0` behandelt das dann fälschlich als „nicht berechnet". | `dj_brain.py:774-778` |
| M3 | `min_overlap` kann bei Trance (32 Bars ≈ 55 s) + kurzem Intro/Outro einen Overlap erzwingen, der `adjusted_mix_in_b` auf 0 drückt und `adjusted_mix_out_a` tief in den aktiven Track zieht. | `dj_brain.py:747-753` |
| M4 | Pfad A vs. B: divergierende Phrase-Konstanten — Fallback-Pfad nutzt fix 8 Bars statt genre-abhängig 16 (Trance/Psytrance); bekanntes Konsolidierungs-Thema, weiterhin offen. | `dj_brain.py:310` vs. `analysis.py:634` |
| M5 | `_find_mix_out_point`: Label-Priorität schlägt Position — erste „main"-Section gewinnt immer, kann Mix-Out mitten in den Track legen. | `dj_brain.py:445-456` |
| M6 | `bass_swap`-Envelope ist kein echter Bass-Swap: am Crossfade-Mittelpunkt sind beide Bässe gleichzeitig aktiv (A ≈ 0,75, B ≈ 0,25) statt hartem Handover. | `transition_renderer.py:360-363` |
| M7 | Emergency-Fallback (0.15/0.85 prozentual) umgeht den Intro/Outro-Guard. | `dj_brain.py:333-335` |
| M8 | Nur Halftime-Korrektur (40–95 BPM → ×2), **keine Doubletime-Korrektur** (Psytrance 145 → librosa 290 wird nicht halbiert). | `analysis.py:975-978` |
| M9 | Rekordbox-XML-Export: Mixpoints nur als Memory-Cues (`Num=-1`), keine HotCues; Sektions-Cues (Drop/Breakdown) gar nicht exportiert; Docstring verspricht Beatgrid + Rating, beides wird nicht geschrieben. | `rekordbox_xml_exporter.py:130-183` |
| M10 | Hängender C-Level-Worker blockiert ganzen Batch: `future.result(timeout=...)` greift erst nach `as_completed`-Yield. | `parallel_analyzer.py:157-164` |
| M11 | Emotional-Journey-Kurve invertiert das Ende: „resolution" liegt energetisch **über** „building" — Cool-Down fällt nicht unter Build-Niveau. | `playlist.py:802-818` |
| M12 | `energy_flow` bis 2.0 statt [0,1] → `overall_score` komprimiert nahe 1.0, Gewichtung verzerrt. | `playlist.py:111-142` |
| M13 | ID3-Genre-Substring-Matching greedy: generisches Tag „house" → „Tech House", „psy" → „Psytrance". | `genre_classifier.py:422-423` |
| M14 | Cache: kein Korruptions-Handling („malformed" → nur Log, DB bleibt tot); `file_lock` definiert, aber ungenutzt. | `caching.py:73-110, 217-258` |

## 4. LOW (Kurzliste)

- Magic Number `50.0` (Default-Sektions-Energie) **fünffach** hartcodiert — `dj_brain.py:366, 367, 389, 446, 447`.
- Toter Ternary `risk_bpm_delta` (beide Zweige identisch) — `playlist.py:1345`.
- Toter Fallback-Zweig in `_sort_harmonic_flow` (nie erreichbar) — `playlist.py:377-389`.
- `_assign_energy_phases`: Warm-up-Phase de facto nicht modelliert (alle Branches → „build") — `playlist.py:1794-1803`.
- `+7`-Camelot-Regel als „circle of fifths" fehlbenannt (±1 ist bereits die Quinte) — `playlist.py:271-274`.
- Sektions-Energie sättigt bei RMS 0.4 → laut gemasterte Tracks alle auf 100, Drop-Diskriminierung verloren — `structure_analyzer.py:316`.
- Erste Section wird fast immer als „Intro" gelabelt (`trends[0]=="rising"` überinklusiv) — `structure_analyzer.py:396-401`.
- Cue-Namen-Matching per Substring: „BREAK-IN" triggert IN-Override — `analysis.py:794-805`.
- `AI_MODEL = "gemma4:12b"` existiert nicht (vermutlich gemma2 gemeint) — `config.py:95`.
- Leeres/stilles Segment bei Seek jenseits Dateiende ohne Warn-Log — `transition_renderer.py:203-204`.
- Key/Danceability bei Tracks > 10 min nur aus den ersten 600 s — `analysis.py:306, 320`.

---

## 5. Invarianten-Matrix (Mixpoint-Pfade)

| Invariante | A genre-aware | B RMS-Fallback | C Rekordbox-Cue | D AI-Override | paired |
|---|---|---|---|---|---|
| Phrase-Alignment (ceil/floor) | ✅ | ✅ | ❌ | ✅ | teilweise |
| phrase_unit genre-abhängig | ✅ | ❌ (fix 8) | ❌ | ✅ | ✅ |
| 0 ≤ in < out ≤ duration | ✅ | ✅ | ❌ | ✅ | ⚠️ (negativ möglich) |
| Nie in Intro/Outro | ⚠️ (Fallback bricht) | ✅ | ❌ | ⚠️ | ✅ |

**Pfad C ist der schwächste Punkt im Mixpoint-System** — er überschreibt als letzter die validierten Werte, ohne selbst zu validieren.

## 6. GENRE_MIX_PROFILES — Bewertung

9 Genres + DEFAULT abgedeckt (Psytrance, Tech House, Progressive, Melodic Techno, Techno, Deep House, Trance, DnB, Minimal). Werte recherche-konform: Techno (16, 32) Bars ✅, Trance (32, 64) ✅, phrase_unit 16 für Trance/Psytrance ✅. Kompatibilitäts-Matrix symmetrisch und fachlich vertretbar.
**Fehlend:** House (generisch), Hardstyle/Hardtechno, Dubstep, Breakbeat, Afro/Organic House, Ambient — fallen alle auf DEFAULT (8-Bar-Phrasen, 16–32 Bars Transition).

---

## 7. Stärken (verifiziert)

- **Camelot-Fundament korrekt**: CAMELOT_MAP alle 24 Keys, Wraparound 1↔12 mathematisch verifiziert, BPM-Hard-Gate vor jeder Harmonik-Bewertung.
- **Key-Detection nach Krumhansl-Schmuckler** (Korrelation über 12 Rotationen) — Standardverfahren, korrekt implementiert.
- **Half/Double-Time-Erkennung konsistent** in dj_brain, Risk-Assessment und Renderer (relative 4-%-Toleranz statt absolutem Fenster) — musikalisch korrekt.
- **`align_ai_mix_points`** mit Epsilon + gracefully degradierendem Bar-Fallback — vorbildlich.
- **RMS-Normalisierung vor Crossfade** (Perzentil aktiver Frames, Gain-Clamp +12/−20 dB) — echte DJ-Praxis.
- **Robuste Fehlerpfade**: Subprozess-Isolation gegen C-Crashes, BrokenProcessPool-Recovery mit Einzeldatei-Isolation, durchgängige `nan_to_num`/`clip`-Guards.
- **Thread-Sicherheit korrekt**: alle UI-Updates via pyqtSignals, keine Widget-Zugriffe aus Workern.
- **Context Flow verifiziert**: Set-Phasen-Zielenergie, Trend-Fortführung, Genre-Fatigue, Repetition-/Cliff-Penalty, BPM-Hard-Gate mit Halftime-Durchlass — alle wie dokumentiert vorhanden.
- **Sentinel-Design (−1.0 / ≥ 0.0)** konsistent ausgewertet.
- **M3U8-Export** sauber (UTF-8, Newline-Injection-Sanitizing).
- ID3-BPM-Priorität vor librosa vermeidet Halftime-Fehler bei Beatport-Exporten.

## 8. Fehlende DJ-Features (gegenüber Profi-Praxis)

1. **Beatgrid-/Downbeat-Erkennung** — größte Einzellücke. Phrasen werden arithmetisch ab t=0 gerastert; ohne Downbeat-Anker driften alle Bar-Angaben. Direkte Ursache von H2.
2. **Beat-Phase-Alignment im Preview** (H2).
3. **Key-Shift-Vorschläge** — `_key_advice` bewertet nur Ist-Distanz, schlägt keinen Pitch-Shift vor, obwohl Time-Stretch-Infrastruktur existiert.
4. **LUFS-Loudness (EBU R128)** — nur RMS-„Energy" 0–100; kein Gain-Matching pro Deck.
5. **Vocal-Clash-Warnung** — `detect_vocal_instrumental` existiert, wird aber im Risk-Assessment nicht genutzt; keine Vocal-Zeitbereiche.
6. **Key-Confidence** — Korrelationsabstand major/minor wird verworfen; unsichere Keys nicht filterbar.
7. **Echter Bass-Swap-Handover** (M6) statt überlappendem Sub-Fenster.
8. **Loop-/Roll-Empfehlungen, Filter-Automation** — nur statische EQ-Textstrings.
9. **Globaler Playlist-Optimierer** — alle Strategien greedy; kein Beam-Search/TSP-Ansatz.
10. **Cue-Export-Tiefe** — erkannte Drops/Breakdowns werden nicht als HotCues exportiert (M9).

---

## 9. Empfohlene Reihenfolge

1. **C1 fixen** (Einrückung analysis.py:853-931 — Track-Konstruktion aus dem `if camelot_code`-Block ziehen). Danach `CACHE_VERSION` bumpen.
2. **C2 fixen** (Advanced-Analyse im Fast-Path auf bereits geladene 360-s-Daten umstellen oder bewusst als Option deklarieren).
3. **H1**: Cue-Override durch Validierung + Phrase-Alignment schicken (gleiche Pipeline wie AI-Override / `align_ai_mix_points`).
4. **H7/H8** (Cancel-Fehlinterpretation, Cache-Key-Mismatch) — kleine Fixes, großer Alltagsnutzen.
5. **H4/H5** (Camelot-Boost-Regeln, harmonic_strictness) — Kern des Produktversprechens „Harmonic".
6. **H2** (Beat-Phase-Alignment) — größter hörbarer Qualitätssprung, benötigt Downbeat-Detektion (librosa.beat / madmom) als Vorarbeit.
7. Mittelfristig: Pfad-A/B-Konsolidierung (bekannt, M4), Doubletime-Korrektur (M8), Rekordbox-HotCue-Export (M9).

---

*Erstellt durch 3 parallele Audit-Agenten + manuelle Code-Verifikation der CRITICAL-Findings. Testsuite-Stand: 1243 passed / 77,9 % Coverage (2026-07-17).*
