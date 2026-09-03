# HPG V2.0 — Arbeitsplan (Konsolidierung Audit-Runde 2, 2026-07-26)

Basis: Zweiter Voll-Audit (3 Auditoren) über den gefixten Stand (1319 Tests grün)
+ Consulting-Team-Review. Runde 2 fand **10 neue Regressionen aus der eigenen
Fix-Runde** (3 kritisch) und bestätigte den verbleibenden Backlog per Code-Blick.

Aufwand: S = < 1 h · M = 1-4 h · L = > 4 h (Agenten-Zeit).
Jede Phase endet mit: voller pytest + verify-Suiten + E2E.

---

## PHASE 0 — SOFORT (Regressions-Hotfixes aus Runde 2) · MUSS

Fehler, die WIR in der Fix-Runde eingebaut haben. Vor allem anderen.

| # | ID | Problem | Fix | Aufw. |
|---|----|---------|-----|-------|
| 0.1 | **N-01** 🔴 | `pro_eq_swap` (Default-Modus Techno/Psy/TH): Mids+Highs mit amplituden-komplementären LINEAR-Envelopes → −3,01 dB Loch am Mittelpunkt — genau das Loch, das C3 beseitigen sollte, jetzt im Hauptpfad. | cos/sin-Equal-Power für Mid/High-Envelopes (Bass-Swap bleibt hart). | S |
| 0.2 | **N1/N2/N3** 🔴 | `_PeakWorker` (T2): (a) `old.isRunning()` auf gelöschtem C++-Objekt → RuntimeError-Crash beim zweiten load(); (b) Widget-Parent zerstört laufenden QThread bei START OVER/Reorder → „Destroyed while running"; (c) alter Worker kann frische Peaks überschreiben. | Worker auf Modulebene, `requestInterruption()`, `stop_peaks()` aus cleanup/closeEvent, Generation-Counter statt isRunning-Guard. | M |
| 0.3 | **N-03** 🔴 | Phrasen-Konfidenz skaliert mit phrase_unit: bei 16-Bar-Genres (Psytrance/Trance — Kern-Genres!) erreicht selbst starke 2σ-Struktur nur 49 % Pass-Rate — A1 ist dort praktisch abgeschaltet. | Konfidenz normieren (Margin/Std der Votes o. theoretisches Maximum) ODER Schwelle pro phrase_unit skalieren. | S |
| 0.4 | **N-02** 🟠 | C1-Bar-Alignment verwirft bis zu 2 Beats vom ANFANG von seg_b — genau der Phrasen-/Drop-Einsatz, auf den A1 den Mix-In gelegt hat. | Track B mit 1 Bar Vorlauf laden (`b_start = mix_in − bar`), Cut schneidet nur in den Vorlauf. | S |
| 0.5 | **N-04** 🟠 | BATCH_SIZE 200: Hänger-Deadline wächst auf ~2,8 h; BrokenPool spät im Batch schickt bis 199 Dateien einzeln in den Safe-Mode (je neuer Pool!). | Deadline an worker_count deckeln (~15 min); Recovery-Executor wiederverwenden. | S |
| 0.6 | **R2/R3/R4** 🟡 | Phrase-Anker-Gates: läuft auch bei gescheitertem Downbeat (erfundenes Raster); `min_mix_in = anchor+grid` wandert mit spätem Phrasen-Anker bis ~28 s nach hinten; Sentinel `>0.0` verwirft gültige 0.0-Phase. | Gate auf downbeat_confidence; min_mix_in an first_downbeat binden; Sentinel −1.0. | S |
| 0.7 | **N6/T10** 🟡 | `failed`-Lambda ohne source-Guard: verwaister AI-Worker überschreibt Statuszeile. | Guard wie bei den anderen Slots. | S |
| 0.8 | **N7-Rest** 🟢 | restart_app: progress_widget-Steps/Badges + current_playlist_mode nicht zurückgesetzt. | Reset ergänzen. | S |

**Gate:** pytest 100 % + verify_wave4 (neuer Check: pro_eq-Mittelpunkt-RMS) + E2E.

---

## PHASE 1 — Kern-Präzision (ein Anker, ein Gitter) · MUSS

Der eine strukturelle Rest aus A1: Sections und Mix-Punkte leben auf
verschiedenen Gittern.

| # | ID | Problem | Fix | Aufw. |
|---|----|---------|-----|-------|
| 1.1 | **R1/A3/C6** 🟠 | Sections: anchor=first_downbeat, Halb-Phrasen-Gitter. Mix-Punkte: phrase_anchor, Ganz-Phrasen-Gitter. Drop-Grenze kann bis 1 volle Phrase (15-30 s) vom Mix-Gitter wegdriften. | Reihenfolge umbauen: phrase_unit (Genre) → estimate_first_phrase → analyze_structure(anchor=phrase_anchor) mit GANZEN Phrasen. Behebt R1+A3 in einem Zug. | M |
| 1.2 | **B3** 🟠 | Drei konkurrierende Overlap-Werte; `overlap = duration_a − mix_out_a` wird RÜCKWÄRTS angewandt → Übergang liegt eine Overlap-Länge zu früh; `_dynamic_transition_bars` nur noch Anzeige-Text. | EINE Overlap-Quelle: `_dynamic_transition_bars` → clampen gegen Intro/Outro-Fenster → konsistent in Plan+Anzeige. | M |
| 1.3 | **N2(Kern)** 🟡 | `_assess_transition_risks` bewertet Track- statt Paar-Punkte (Bass-Kollisions-Check prüft nie gemixte Stelle). | Paar-Punkte durchreichen. | S |
| 1.4 | **R9/N15** 🟡 | `round(x,2)` nach Quantisierung: bis 5 ms off-grid; E2E musste Toleranz auf 11 ms aufweiten. | Ungerundet zurückgeben, nur Anzeige rundet; E2E-Toleranz auf 1e-3 senken. | S |
| 1.5 | **R5** 🟡 | bar_len aus ganzzahliger Tag-BPM driftet übers Voting-Fenster (~0,4 Bar bei 0,3 BPM Fehler). | Median-IBI aus estimate_first_downbeat wiederverwenden. | S-M |
| 1.6 | **R7/B2** 🟡 | Overlap-Logik für Track B + M1-Clamp nachweislich toter Code. | Entscheiden: „in-das-Intro-mixen" implementieren ODER Code entfernen (mit B3 zusammen). | S |
| 1.7 | **R8/B8** 🟢 | Bar-Anzeige: 2 Rundungskonventionen, ignoriert Anker → liest sich als „off-phrase". | `seconds_to_bars(..., floor)` überall + Phrasennummer relativ zum Anker anzeigen (C9). | S |
| 1.8 | **R10/N6** 🟢 | GENRE_PHRASE_UNITS ohne casefold vs. get_mix_profile; dritte Inline-Quantisierung. | Eine Quelle für phrase_unit; quantize_to_grid überall. | S |

---

## PHASE 2 — Performance & Stabilität · SOLL

| # | ID | Problem | Fix | Aufw. |
|---|----|---------|-----|-------|
| 2.1 | **CH-01/P-02/R11** 🟠 | HPSS+STFT 7-11× pro Track, MFCC 3-4×, chroma 3×; A1 addiert einen weiteren vollen Pass. | FeatureCache-Dataclass: einmal rechnen, Sections slicen, an downbeat/phrase/structure/genre durchreichen. Erwartung: Analyse 3-5× schneller. | M |
| 2.2 | **CH-02/A-01** 🟠 | LUFS-Full-Decode: bis ~1,5 GB pro Worker (float64-Kopie + Filterpuffer), 6 Worker kippen 16-GB-RAM. | Blockweise BS.1770-Messung via sf.blocks; Guard entfällt. | M |
| 2.3 | **A-05** 🟡 | 3 Decodes + get_duration pro Track. | soundfile.info + Decode-Konsolidierung (fällt teils mit 2.2 zusammen). | S-M |
| 2.4 | **C-01** 🟡 | Cache-Quarantäne race-anfällig; unter Windows PermissionError aus laufenden Workern. | Lock um alle Cache-Zugriffe ODER neue DB unter neuem Namen statt move. | S |
| 2.5 | **CH-08/F19/F16** 🟠 | Strategien komplett ungecacht (O(n²) enhanced-Aufrufe, ~8-13 s bei 120 Tracks); Track.__eq__ deep-compare macht remove() O(n²). | Cache auf calculate_enhanced_compatibility (Key track_id), `@dataclass(eq=False)` + hash über track_id. | S |
| 2.6 | **CH-07** 🟢 | `scored.sort()` statt Top-K. | heapq.nlargest(LOOKAHEAD_TOP_K). | S |
| 2.7 | **T3** 🟠 | Blockierender requests.get im MainWindow-Konstruktor. | In Worker/QTimer verlagern. | S |
| 2.8 | **T5** 🟠 | Hard-terminate lässt Render-Subprozess als Zombie zurück. | Executor-Terminate vor thread.terminate. | M |
| 2.9 | **T7** 🟠 | AI-Worker-Lifecycle: kein deleteLater, keine isRunning-Guards bei Test/Pull, falscher Modellname bei Doppel-Pull. | Einheitliches Worker-Pattern (Guard + finished→deleteLater + Referenz nullen). | M |
| 2.10 | **T8** 🟡 | Verwaiste Preview-Widgets mit lebendem QMediaPlayer; _preview_buttons nicht bereinigt. | deleteLater im Fehlerpfad + Buttons-Dict leeren. | S |
| 2.11 | **T12** 🟡 | Nackte Ziffern-Shortcuts 1-5 fensterweit. | Ctrl+1..5 (+ C4-Chance: Space-Shortcut implementieren oder aus Hilfe entfernen). | S |
| 2.12 | **N4(GUI)/F14** 🟡 | Checkbox „Cue-Heuristik erzwingen" setzt env-Var, die NIEMAND liest — funktionslose UI. | Entweder in analysis.py auswerten oder Checkbox entfernen. | S |
| 2.13 | **N5(GUI)/F15/D3** 🟢 | validate_playlist_security nach sanitize strukturell nie False; Namenslüge „security". | Doppelprüfung entfernen; Umbenennung resource_limits (mit Tests). | S |
| 2.14 | **F13/F14/F17** 🟡 | StrategyConfig.overlap/target_energy tot; default_overlap wirkungslos — UI verspricht Wirkung ohne Wirkung. | Verdrahten oder aus UI/Config entfernen (ehrlich machen). | S-M |
| 2.15 | **F18** 🟡 | Warm-Up/Cool-Down: reine BPM-Sortierung ohne Harmonik. | BPM-Richtung als Constraint, Harmonik als Tiebreaker (Lookahead light). | M |
| 2.16 | **N-05** 🟡 | LUFS-Ziel-Semantik: −14 als dBRMS UND LUFS benutzt → Previews je nach Pfad 2-3 dB verschieden; Track-LUFS auf leisen Segment-Ausschnitt angewandt. | LUFS nur als Delta A↔B verwenden, Absolutpegel weiter aus Segment-RMS. | S |
| 2.17 | **N-07** 🟢 | Limiter ohne Channel-Link (Stereo-Verzug), NaN-Durchfall. | max(|L|,|R|)-Maske; nan_to_num vor Export. | S |

---

## PHASE 3 — Qualitätssprünge (DJ-Präzision) · KANN, hoher Hörwert

| # | ID | Chance | Aufw. |
|---|----|--------|-------|
| 3.1 | **A2/C1** | phrase_unit MESSEN (Autokorrelation der Bar-Novelty, Genre als Prior) statt Genre-Konstante — speist Voting UND Gitter. Größter verbleibender Präzisions-Hebel. | M |
| 3.2 | **E4/C2** | Novelty-Kurve: Chroma-SSM + Bass/Perkussions-Kanal ergänzen → bessere Drop/Break-Grenzen. | M |
| 3.3 | **B6/C3** | Absolute Bass-RMS (dBFS ≤160 Hz) als Section-Feld + Bandanalyse VOR die Mix-Punkt-Wahl ziehen → „Kick läuft"-Erkennung wird physikalisch echt. | M |
| 3.4 | **C4(Kalibrierung)** | PHRASE_CONFIDENCE_MIN nach 0.3-Normierung an 10-20 gelabelten Tracks deiner Library kalibrieren (Hör-Ground-Truth). | M |
| 3.5 | **CH-03/A-03** | sr=44100-Analysepfad (Höhenband bis 22 kHz, Downbeat-Frame 11,6 ms) — NACH 2.1, sonst zu teuer. Cache-Bump. | M |
| 3.6 | **CH-04** | Billig-Variante zuerst: ab \|rate−1\|>3 % Camelot-Code von B transponieren vor dem Scoring (S). Voll: Key-Lock via pyrubberband (M). | S/M |
| 3.7 | **CH-05/C5** | Tempo-Ramp im Crossfade (blockweiser Stretch, tempo_ratio-Feld als Vertrag → löst R-08 mit). | L |
| 3.8 | **CH-06** | chroma_cqt statt chroma_stft (+ evtl. Essentia edma als Backend-Flag). | S/L |
| 3.9 | **N-06** | Filter-Rampen statt Filter-Schalter bei smooth_blend/filter_ride/breakdown_bridge. | M |
| 3.10 | **N-09/D2** | Vocal-Penalty kontextsensitiv (nur wenn Overlap in Mids-lastigen Sections); langfristig Vocal-Präsenz pro Section. | S / L |
| 3.11 | **RB-01-Test** | ANLZ-Pfad gegen deine ECHTE Rekordbox-Library testen (Track der in RB ist analysieren, get_first_downbeat != None verifizieren); ms/s-Heuristik `>100` absichern. Danach C2-Schwelle (0.9, hartkodiert) in config.py + neu bewerten. | S-M |
| 3.12 | **E1/E2** | build-Label ohne Drop-Zwang; Intro/Outro-Heuristik über Bass-Einsatz statt Prozente. | S/M |

---

## PHASE 4 — Wartbarkeit & Politur · KANN

| # | ID | Inhalt | Aufw. |
|---|----|--------|-------|
| 4.1 | **D2-D15** | 15 Funktionen ohne Aufrufer entfernen — GEMEINSAM mit den Tests, die sie abdecken (get_key, calculate_lufs, ...). | M |
| 4.2 | **K1-K9/C2-C3(GUI)** | Format-Helfer (mm:ss 9×, Score-Zelle 4×, Pfad-Norm 4×, AI-Status 13×), 32 Hex-Farben nach theme.COLORS, score_color vs get_7_scale_color vereinheitlichen (liefern heute widersprüchliche Farben!). | M |
| 4.3 | **C1(GUI)** | main.py (4553 Zeilen) in hpg_gui/-Module schneiden (workers/preview/panels) — reine Verschiebung. | L |
| 4.4 | **C5(GUI)** | Error-Reporter-UI (Fehlerprotokoll-Dialog) — macht log_error-Sinks erstmals sichtbar. | M |
| 4.5 | **F6** | m3u8: relativer Pfad-Modus für USB-Export. | M |
| 4.6 | **F7/F8/F13(GUI)** | QLabel-PlainText-Format an 5 Stellen; Progress-Format vereinheitlichen; LOG_DIR/error_reporter-Divergenz. | S |
| 4.7 | **D1 — erledigt** | AI-Auto-Apply-Block entfernt; AI bleibt advisory. | S |
| 4.8 | **Doku** | CLAUDE.md-Drift (Zeilenzahlen, „Cyberpunk"-Theme-Doku), N10(GUI) Waveform-Preroll-Klemmung, Skill-Landkarten-Update (hpg-sota-updater-Lauf). | S |
| 4.9 | **N-08 klären** | from_plan nutzt first_downbeat fürs Bar-Alignment — für BAR-Phase äquivalent zum Phrasen-Anker (Differenz = ganze Bars). Kein Fix nötig, aber Kommentar + Test dokumentieren. | S |

---

## Empfohlene Reihenfolge & Meilensteine

1. **Phase 0 komplett** (1 Sitzung) → pytest + E2E + Hör-Check `pro_eq_swap`.
2. **Phase 1** (1-2 Sitzungen) → danach ist „ein Track = ein Anker = ein Gitter" wahr; E2E-Invarianten verschärfen (C8: Section-vs-Gitter-Check, 1e-3).
3. **DANN DU: Hör-Session.** 10-15 Übergänge aus deiner echten Library anhören, Notizen. Ohne dieses Feedback ist Phase 3 Kalibrierung ins Blaue.
4. **Phase 2** (2-3 Sitzungen) parallel zu deiner Hör-Session möglich.
5. **Phase 3** priorisiert nach deinen Hör-Notizen (3.1-3.4 zuerst, wenn Phrasen „nicht sitzen"; 3.6/3.9 wenn Übergänge „verstimmt/hart" klingen).
6. **Phase 4** opportunistisch.

**Nicht tun:** Phase 3/4 vor Phase 0 — die 3 kritischen Regressionen entwerten
jeden Feinschliff darüber.

---

## ABSCHLUSSSTATUS — 2026-07-26

Der Plan ist im Repository umgesetzt und verifiziert. Die zuvor offenen
Vertrags-/Wartbarkeitspunkte wurden im autonomen Restlauf ebenfalls erledigt:

- echter per-Task-Timeout mit begrenztem In-Flight-Fenster im Parallel-Analyzer;
- identischer erweiterter Transition-Score für Empfehlungen und Playlist-Qualität;
- expliziter Mixpoint-Sentinel `-1.0` mit Cache-Version 24, `0.0` bleibt gültig;
- nachgewiesen toter Code entfernt (AI-Auto-Apply-Block, ungenutzte Profil-/Konfigurationssymbole);
- aktive Dokumentation, Pfade und Produktionsstatus synchronisiert;
- historische Dokumente als Snapshots gekennzeichnet, ohne ihre Ergebnisse umzuschreiben.

Die abschließenden Test-, Coverage-, E2E- und Integritätswerte stehen in
`PRODUCTION_STATUS.md` und `AUDIT_REPORT_2026-07-26_FULLSTACK.md`.

## REALE ABSCHLUSSABNAHME - 2026-07-26

Der zuvor externe Restpunkt ist mit realen lokalen Daten geschlossen:

- **Rekordbox-ANLZ-Ground-Truth:** Content `254580025` aus der lokalen
  Rekordbox-Datenbank; `ANLZ0000.DAT/PQTZ` liefert roh `0,0017 s`. Der Importer
  liefert exakt denselben Wert; `analyze_track()` uebernimmt ihn mit
  `downbeat_confidence=1,0`. Rekordbox-BPM `138,0` und Camelot `4A` bleiben
  ebenfalls identisch.
- **Audio-/Uebergangspruefung:** zwei reale lokale Rekordbox-Tracks analysiert
  und als 60-s-Stereo-Render ausgegeben. Peak `0,515`, finite Samples,
  Mitte-vs.-Anfang `-2,19 dB`, Mitte-vs.-Ende `+2,08 dB`, Kanalabweichung
  `0,06 dB`; alle Akzeptanzkriterien bestanden.

Damit sind keine technischen Planpunkte mehr offen. Eine subjektive Hoersession
ueber laengere reale Sets bleibt optional, weil musikalische Praeferenz nicht
vollstaendig automatisiert verifizierbar ist.
