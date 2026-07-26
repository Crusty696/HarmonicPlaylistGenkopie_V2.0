# HPG V2.0 — Skill-Team-Audit (Bugs, toter/doppelter/falscher Code, Optimierungen)

**Datum:** 2026-07-24 · **Methode:** 4 parallele Experten-Auditoren (Mix-Points/Phrasing, Harmonic/Scoring, Renderer/Pipeline, Full-Stack/Wiring) auf Basis der HPG-Experten-Skills. Scoring- und Playlist-Befunde wurden durch **echte Ausführung** des Codes belegt (Programmausgaben, keine Vermutungen); Audio-Pfade statisch verifiziert.

**Bilanz:** ~95 Findings · **8 KRITISCH · 21 HOCH** · Rest MITTEL/NIEDRIG. Alle 20 in den Skills dokumentierten Schwachstellen (A/B/C/D/E) wurden gegen den Code verifiziert: 17 bestätigt (teils verschärft), 2 präzisiert/widerlegt (D1 teilweise, D4 → Ersatzbefund F12), 1 mit wichtiger Zusatzerkenntnis (E2: `avg_bass` ist ein relativer Bandanteil, keine absolute Bass-Energie).

> NUR ANALYSE — es wurde kein Code geändert.

---

## TOP-PRIORITÄT: Die 8 kritischen Befunde

### 1. ⚡ R-01 — Time-Stretch ist INVERTIERT (transition_renderer.py:154-159)
`rate = target_bpm_b / bpm_a` — librosa-Semantik ist aber: rate>1 = schneller. Track B wird vom Zieltempo **weggezogen**: A=128, B=140 → B läuft im Preview mit **153 BPM** statt 128. Der Fehler ist immer doppelt so groß wie ganz ohne Stretch und geht in die falsche Richtung. Beleg: Z. 211 rechnet bereits mit der korrekten librosa-Semantik — die Datei widerspricht sich selbst. Half/Double-Fälle (rate≈1.0) maskierten den Bug.
**Fix (1 Zeile):** `rate = bpm_a / target_bpm_b`.

### 2. ⚡ F1 — NameError legt das komplette KI-Feature still (main.py:1307)
`hpg_config` ist nur lokal in `init_ui` importiert; `refresh_ai_providers` referenziert es als Global → `NameError` beim Aktivieren der KI-Checkbox mit leerer Modell-Combo. Folge: „AI erkennen"-Button bleibt für die ganze Session grau, Status hängt auf „suche & starte Provider …", keine KI-Anreicherung.
**Fix (1 Zeile):** Import auf Modulebene.

### 3. ⚡ N1 — `outro_start` wird in die Track-MITTE gezogen (dj_brain.py:531-550 + analysis.py:873-880)
Spiegel-Bug zum dokumentierten B7, aber **ohne Sonderbedingung auslösbar**: Das Head-Fenster (360/600 s) labelt seine letzte Section immer `outro`, ohne zu wissen, dass der Track weitergeht. Der Rückwärts-Scan findet dieses Fenster-Outro → reproduziert: 480-s-Track → Mix-Out bei **34 %** der Tracklänge. Betrifft auf dem Rekordbox-Fastpath **jeden Track > ~6 min** — der Normalfall bei Psytrance/Techno.
**Fix:** Fenster-Grenz-Labels degradieren (`outro`→`main` wenn Head ≠ Track-Ende) + Scanner auf zusammenhängenden Randblock beschränken.

### 4. ⚡ F01 — BPM-Hard-Gate ist bei Half/Double 2× zu lax (models.py:120-131)
`effective_bpm_diff` enthält für dieselbe Relation Kandidaten im schnellen UND langsamen Tempo-Raum; `min()` wählt systematisch die halbierte Differenz. 140 vs. 73 passiert das Gate mit „diff 3", real muss der DJ 6 BPM (4,3 %) schieben. Wirkt auf alle 8 Strategien, das Hard-Gate, predict_transition_type und den Renderer.
**Fix:** Differenz immer im Tempo-Raum von bpm1 messen; gespiegelte Kandidaten streichen.

### 5. ⚡ F02 — Key-Confidence ist fehlkalibriert, „sicher"-Zweig unerreichbar (analysis.py:151-182)
Pearson-Schwellen (margin ≥ 0.05) auf Cosine-Werte angewandt: Selbst eine **perfekte** A-Moll-Chroma erreicht nur margin 0.0366. `key_confidence` ist faktisch dreiwertig (0.9/0.5/0.4), die „Key unsicher"-Risk-Note feuert bei fast jedem Übergang und ist damit wertlos. **Wichtig:** key_confidence ins Scoring aufzunehmen (Skill-Pattern 1) wäre ohne diesen Fix schädlich.
**Fix:** Chroma vor Cosine mean-zentrieren ODER margin-Schwelle auf ~0.005-0.04 neu kalibrieren.

### 6. ⚡ A-01 — LUFS-Messung kann den RAM sprengen (analysis.py:221-230)
Guard rechnet float32, Code erzeugt zwingend float64-Kopie + pyloudnorm-Filterketten → realer Peak ~3-6× der Schätzung. 10-min-WAV ≈ 1-1.5 GB **pro Worker**, × 6-12 parallele Worker → OOM/Swap auf 16-GB-Maschinen.
**Fix:** Limit auf realen Faktor (oder 128 MB) senken; richtig: blockweise BS.1770-Messung via `sf.blocks()`.

### 7. ⚡ PA-01 — Safe-Mode-Recovery kann dauerhaft deadlocken (parallel_analyzer.py:263-282)
Timeout wirft **innerhalb** des `with ProcessPoolExecutor` → `__exit__` = `shutdown(wait=True)` wartet auf den hängenden Worker → GUI friert ein. Exakt der Bug, den der M10-Fix im Hauptpfad behoben hat, lebt in der Recovery weiter.
**Fix:** Executor manuell verwalten (wie main.py:655-665 es korrekt macht).

### 8. ⚡ A-02 — Fehlgeschlagene Analysen werden als Müll-Track DAUERHAFT gecacht (analysis.py:1116-1142)
Ein transienter Fehler (Datei gesperrt, Netzlaufwerk) → Track mit erfundenen Werten (energy=50, mix_in=0.0, mix_out=duration, keine Sections) → wird gecacht und bis zum nächsten mtime-Wechsel für immer zurückgeliefert. Nutzer merkt nichts.
**Fix:** Fehlpfade nicht cachen bzw. `analysis_status="degraded"` + GUI-Markierung.

---

## HOCH (Auswahl der wichtigsten, vollständige Details in den Agenten-Abschnitten)

| ID | Bereich | Befund |
|---|---|---|
| RB-01 | Rekordbox | **ANLZ-Downbeat-Pfad ist still tot** (falsche pyrekordbox-API + falsche Attributnamen + DEBUG-Log). Dadurch gibt es NIE `downbeat_confidence=1.0` → der exakte Beat-Alignment-Pfad im Renderer läuft auch mit perfekter Rekordbox-Library nie. Das ist die eigentliche Ursache von C2. |
| N2 | DJ Brain | `_assess_transition_risks` bewertet die Track-Mix-Punkte statt der paarspezifischen — der Bass-Kollisions-Check prüft eine Stelle, die nie gemixt wird. |
| N3/B2/B3 | DJ Brain | Der komplette Overlap-Mechanismus ist eine Kette toten Codes: `target_overlap` für B wirkungslos, `_dynamic_transition_bars` wird überschrieben, der „M1-Fix"-Deckel greift nie. |
| N5 | DJ Brain | Notfall-Fallback setzt `duration*0.15/0.85` roh — off-grid und mitten im Intro, obwohl `intro_end` bekannt ist. |
| N10 | Downbeat | Der Anker wird aus einem der ersten 4 Beats gezogen — genau dem Bereich, der zuvor als zu leise vom Voting ausgeschlossen wurde. Fehler propagiert in JEDE Quantisierung. |
| F03/F04 | Scoring | `loose_factor` bis 1.2 lässt +4 (84) den klassischen ±1-Move (80) überholen; +2 „Energy Boost" fehlt komplett und scort wie ein Key-Clash (8). |
| F05 | Scoring | AI-Bonus wird doppelt gezählt: `calculate_compatibility` addiert ihn in die Harmonik-Skala, der Enhanced-Pfad separat aufs Overall → `predict_transition_type` entscheidet über einen bis zu 14 Punkte aufgeblähten Wert. |
| F06 | Scoring | `energy_direction`-Preset („Build Up"/„Cool Down") kommt als **String** an einem **Enum-Parameter** an → alle Vergleiche still False; `EnergyDirection` wird nirgends konstruiert = totes Feature. |
| F07 | Perf | `_COMPAT_CACHE` ist vollständig tot: 0 Treffer während der Generierung (instrumentiert belegt); ~11.500 uncachte Score-Aufrufe bei n=120. |
| F08 | Scoring | `_apply_harmonic_smoothing` verschlechtert Playlists nachweislich (Gegenbeispiele: Gesamtscore 265→250), weil die Anschluss-Transition fehlt (= dokumentiertes D5, jetzt mit Beweis). |
| F09/F13/F14 | UI-Lüge | Context Flow ignoriert 3 von 6 beworbenen Parametern; `StrategyConfig.overlap`/`target_energy` werden validiert aber nie zugestellt; `default_overlap` ist wirkungslos. |
| F10 | Timeline | Plan-Overlap ungeklemmt → negative Spieldauern („Zeit läuft rückwärts") bei kurzen Tracks. |
| F12 | Genre | `detected_genre`-Default „Unknown" ist truthy → ID3-Genre-Fallback ist toter Code → konstant 0.5-Kompatibilität für die ganze Library ohne DJ-Brain-Klassifikation. |
| F15 | Key | Fehlgeschlagene Key-Detection hat kein Sentinel → alle Fehlschläge landen auf **5A** und scoren untereinander 100 → falsche „perfekt harmonische" Blöcke. |
| R-02/R-03/R-04 | Renderer | pro_eq_swap summiert Höhenband auf 2.0 (+6 dB); der „Soft-Limiter" ist eine globale Peak-Normalisierung über den ganzen Clip; echo_out baut Pegel 1.74× auf und ist nicht beat-synchron (0.5 s hartkodiert). |
| P-01 | Perf | Prozess-Pool wird **pro Batch** neu erzeugt: 1000 Tracks → ~252 Prozess-Starts mit je librosa-Import + komplettem Rekordbox-DB-Scan ≈ ~21 min reine Anlaufzeit. |
| P-02 | Perf | HPSS (teuerste librosa-Op) läuft **7-11× pro Track** (1× Track + 1× pro Section); MFCC 4-5×, STFT-Familie mehrfach. Fix halbiert grob die Analysezeit. |
| T1 | GUI | `AnalysisWorker` überschreibt das eingebaute `QThread.finished` → `deleteLater()` auf laufendem Thread möglich → „Destroyed while thread is still running"-Crash-Race. |
| T2 | GUI | Preview-WAV (bis ~124 s) wird komplett im GUI-Thread gelesen → sichtbarer Freeze bei jedem Preview. |
| F2/F3 | Export | Rekordbox-Export ohne .xml-Endungs-Ergänzung (Datei für Rekordbox unsichtbar); Vollständigkeits-Check macht den Partial-Export-Mechanismus zunichte: 1 defekter Track verwirft 199 gute. |
| R1/R3 | Deps | `soundfile` (3 direkte Imports!) und die komplette Test-Toolchain (pytest/-cov/-xdist) fehlen in requirements; `pytest.ini` zeigt auf nicht existentes `tests/` → Testlauf auf frischem Klon garantiert rot. |
| A-03 | Analyse | Analyse @ 22050 Hz Mono vs. Render @ 44100 Stereo: „Höhenband" endet bei 11 kHz, Brightness-Skala unerreichbar, Downbeat-Frame-Auflösung 46 ms (= Großteil des dokumentierten Phasenfehlers). |

---

## Toter Code (konsolidiert, per AST/Grep verifiziert — 0 Aufrufer)

`analysis.get_key` · `analysis.calculate_lufs` (ersetzt durch calculate_file_lufs) · `analysis.analyze_structure_and_mix_points`-Parameter `energy_level` · `models.bars_to_seconds` · `models.ANALYSIS_FIELD_CONSUMERS` (Doku als Dict) · `config.BARS_PER_PHRASE` · `structure_analyzer.ENERGY_BUILD_THRESHOLD` · `GenreMixProfile.intro_bars` (nirgends gelesen — obwohl genau das die Mix-In-Größe wäre!) · `dj_brain._get_section_at_mix_out/_in` · `playlist.EnergyDirection`-Zweige (F06) · `_COMPAT_CACHE`-Block inkl. try/finally (F07) · `StrategyConfig.overlap`/`target_energy` · `TransitionPlan.curve`/`eq_mode`/`tempo_ratio` (gesetzt, nie gelesen) · main.py: KI-Mixpoint-Block hinter `AI_AUTO_APPLY_MIXPOINTS=False` (~40 Z.) · main.py:1342-1355 (unerreichbarer „keine Modelle"-Zweig, D2) · `validate_playlist_security`-Aufruf (D3) · `app_metadata.py` komplett (Konflikt mit `__init__.__version__`) · `error_reporter.get_recent_errors/clear_errors` · `logging_config.set_module_level/get_debug_logger` · beide `get_format_info()` der Exporter · `base_exporter._sanitize_filename` · `ExportReport.success` · `theme.FONT_SIZE_HEADER` · `main.QPolygonF`-Import · `main._close_pending` · caching.py-Migrationspfad (Version steckt im Dateinamen) · Space-Shortcut (beworben, existiert nicht).

## Doppelter Code (konsolidiert)

Pfad-Normalisierung 4× (models/main/caching/exporter — Exporter weicht ab!) · mm:ss-Formatierung 9× in 2 Varianten · Score-Zellen-Block 4× · AI-Statuszeile+Port-Regex 3× · Mix-Zellenformat 2× · `seconds_per_bar`-Formel: zentrale Funktion + **14 Inline-Kopien** (teils ohne bpm>0-Guard) · Section-Anreicherung 2× divergiert (A-04/N7: Fallback nur im Rekordbox-Pfad) · `generate_timbre_fingerprint` ≡ `calculate_mfcc_fingerprint` · Worker-Formel 2× · `score_color` vs `get_7_scale_color` · melodic/hard/pro_eq-Genre-Sets 2× in predict_transition_type · playlist_security: Track-Check dupliziert im Playlist-Check · 3 Quantisierungs-Implementierungen (models.quantize_to_grid + structure_analyzer-Eigenbau + Cue-Override-Trunkierung) · 3 Rundungskonventionen für mix_*_bars · 0.9-Schwelle dupliziert (renderer + main).

---

## Empfohlene Sanierungs-Reihenfolge (Wirkung ÷ Aufwand)

**Sofort (je ≤ 5 Zeilen, hörbar/sichtbar):**
1. R-01 Stretch-Rate invertieren ← größter Einzelgewinn im Preview
2. F1 hpg_config-Import ← KI-Feature wiederbeleben
3. F2 .xml-Endung, F3 Partial-Export, R1 soundfile in requirements

**Welle 1 — Mix-Punkte sitzen (DJ-Kern):**
4. N1 + B7 Fenster-Label-Degradierung + Randblock-Scanner
5. B4/B5 Positionsterm in Mix-In/Out-Wahl
6. B1 + N4 + N5 Paar-Punkte & Fallbacks quantisieren + Guards
7. N10 Downbeat-Anker robust rückrechnen

**Welle 2 — Scoring ehrlich machen:**
8. F01 BPM-Gate, F02 Key-Confidence-Kalibrierung (VOR key_confidence-Nutzung!)
9. F05 AI-Bonus-Doppelzählung, F06 EnergyDirection-Mapping, F12 Genre-Fallback
10. F03/F04 Scoring-Tabelle (+2 einführen, loose_factor auf ≤1.0 klemmen) — Tests zuerst lesen
11. F08 Smoothing-Ungleichung vervollständigen, F10 Overlap klemmen

**Welle 3 — Stabilität & Performance:**
12. PA-01 Deadlock, A-02 Müll-Cache, C-01/C-02 Cache-Races/Logging, T1/T2 GUI
13. P-01 Pool einmal erzeugen (+30-60 % Batch-Speed), P-02 HPSS/MFCC-Wiederverwendung (≈ Analysezeit halbieren), A-01 LUFS blockweise
14. RB-01 ANLZ-API fixen → A-03 sr/hop → dann erst C2-Schwelle senken (in DIESER Reihenfolge)

**Welle 4 — Renderer-Qualität:** R-02/R-03/R-04 Pegelfehler → C3 Equal-Power (+ curve-Feld verdrahten, R-08) → R-06 Mikro-Fades → R-07 LUFS statt RMS → C4/C5 Stretch-Clamp ±8 % + Ramp.

**Danach:** Toter-Code-Sweep (−~300 Zeilen), Duplikat-Refactor (−~200 Zeilen), Magic Numbers nach config.py (F28/D6), Requirements-Pinning vereinheitlichen (R5), pytest-Toolchain (R3) + tests/ wiederherstellen.

---

## Wichtige Korrekturen an den Skill-Landkarten (beim nächsten SOTA-Update einpflegen)

- E2-Zusatz: `avg_bass` = relativer Bandanteil, NICHT absolute Bass-Energie → Fix-Pattern B6 braucht vorher eine absolute Bass-RMS-Metrik.
- D4 präzisieren: Gewicht fällt korrekt auf 0.1; das echte Problem ist F12 (truthy „Unknown").
- D1 präzisieren: Peak-Time HAT einen Arc — Problem ist: 6/8 Strategien ohne Arc + zwei inkompatible Arc-Modelle.
- C2 erweitern: 3 Blocker (Konfidenz-Formel max ~0.4-0.67, 46-ms-Frame-Auflösung, RB-01) — Schwellen-Senkung allein ist falsch.
- C4 ergänzen: R-01 (Inversion) hat Vorrang vor der Clamp-Diskussion.

*Vollständige Einzel-Findings mit Code-Zitaten und Fixes: siehe die vier Agenten-Berichte (auf Anfrage als Anhang exportierbar).*
# Historischer Audit-Snapshot vom 2026-07-24

> Die Befunde und Symbolnamen in diesem Dokument beziehen sich auf den damaligen
> Stand. Für den aktuellen Status gilt `AUDIT_REPORT_2026-07-26_FULLSTACK.md`.
