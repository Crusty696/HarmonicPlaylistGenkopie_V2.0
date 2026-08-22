# Handoff 2026-08-22: Mixpunkt-Kandidaten Teil 4 — Anbindung in der App gebaut

Vorheriger Stand: `docs/HANDOFF-2026-08-22-kandidaten-teil3.md`. Plan:
`docs/superpowers/plans/2026-08-22-mixpunkt-kandidaten-teil4-app.md` (Waechter
Tor 1: MIT AUFLAGEN, eingearbeitet; Entscheidungen 1–20; Tor 2: MIT AUFLAGEN,
eingearbeitet — siehe unten).
Spec Abschnitt 4 (`docs/superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md`).

**Nutzer-Anweisung 2026-08-22 (`/goal`):** Hoerproben werden uebersprungen und
unten auf der Checkliste gesammelt. Alles andere ist gebaut, gemessen, getestet.

## Was gebaut wurde (Branch `kandidaten-teil4`, 16 Commits `e738836..86e61ad`)

- `hpg_core/candidate_choices.py` (neu): Wahl je Paar persistieren
  (`hole`, `merke`, `vergiss`, `reset_cache`; Datei
  `%LOCALAPPDATA%\HPG\candidate_choices.json`, Env `HPG_CANDIDATE_CHOICES_FILE`,
  Schluessel `normcase(abspath A)||normcase(abspath B)`, atomar via `os.replace`).
  `merke/vergiss/reset_cache` leeren lazy den Paar-Cache der Playlist.
- `hpg_core/pair_candidates.py`: `score_pair(..., bass_swap_geplant=False)` — bei
  True entfaellt `KICK_KONFLIKT_ABZUG` (Flag `bass_swap_pflicht` bleibt);
  `schema_rang` (Teil-3-Praeferenz) als Tiebreak vor `SCHEMA_PRIORITAET`, auch
  fuer `_hauptschema`; `rank_pair_candidates` / `select_pair_candidate`
  (gespeicherte Wahl → Rang 1, Flag `flags["gespeicherte_wahl"]`); neues Gate
  `blende_ueber_b_ende` (Reihenfolge `pair_gate_reasons`: bpm, pitch, coverage,
  outro_covered, blende_im_outro, blende_ueber_b_ende, in_im_intro,
  in_ausserhalb, gitter_out, gitter_in); Score/Gates einmal je (Out, In),
  flache Kopien statt `asdict`.
- `hpg_core/playlist.py`: `_kandidaten_fuer_paar` + dauerhafter
  `_PAIR_CANDIDATE_CACHE` + `reset_pair_candidate_cache()`; Kandidatenpfad in
  `calculate_enhanced_compatibility` nur im BPM-Gate (`bpm_diff <= bpm_tolerance`):
  `overall_score = kandidat.score`, lokale Teilwerte, `TransitionMetrics`
  +`loudness_match/structure_match/kandidat`; `TransitionRecommendation`
  +`kandidaten/kandidat_aktiv/kandidat_konsistent`; Kettenwahl `_kette_waehlen`
  (DP ueber die Paare, Konsistenz je Track: Mix-Out von Paar i mindestens zwei
  Phrasen hinter dem Mix-In aus Paar i−1, Toleranz `QUANTIZE_TOLERANCE_SEC`,
  `_WAHL_BONUS = 10` fuer gespeicherte Wahl, Neustart-Flag);
  `transition_type = "bass_swap"` bei `bass_swap_pflicht`; `_outro_overlap_limit`
  mit `headroom + QUANTIZE_TOLERANCE_SEC` vor dem Floor.
- `hpg_core/tolerances.py`: `write_override_kandidaten(gewichte)` (Summe 1.0 ueber
  die zehn `kandidaten_*_weight`, Rest proportional), `write_override` erhaelt
  vorhandene Kandidaten-Schluessel, `reset_cache` leert den Paar-Cache.
- `hpg_core/exporters/rekordbox_xml_exporter.py`: `export(..., transitions=None)` — Mix-Out/
  Mix-In aus dem Plan (aktiver Kandidat), Memory-Cues `HPG K<n> OUT <schema>` /
  `HPG K<n> IN <schema>` (n je Seite 1..6 nach Dedupe gleicher Zeitpunkte, nur bei
  `_cue_export_allowed`; Dedupe-Toleranz `QUANTIZE_TOLERANCE_SEC`).
- `main.py`: Kandidatentabelle je Uebergangs-Karte im `MixTipsPanel`
  (`KANDIDATEN_SPALTEN = Rang, Mix-Out A, Mix-In B, Blende, Schema, Score,
  Teilwerte, Begruendung`; aktive Zeile markiert; Signal `candidate_chosen`),
  `_berechne_uebergaenge` / `_verteile_uebergaenge` / `_on_candidate_chosen`
  (Wahl speichern → Metriken, Quality, Empfehlungen neu → Panels; Preview des
  Paars verworfen), Tabelle Mix-In/Out aus dem Plan (auch `on_ai_finished`,
  Tooltip "Kandidat Rang n" / "Analyse"), Regler "Lautheit (Kandidaten)" via
  `write_override_kandidaten` mit Statuszeile zur Hoertest-Praeferenz,
  BPM-Default 2.0 (Slider, Label "±2", `current_bpm_tolerance`, Worker, Panel),
  Rekordbox-Export uebergibt `transition_recommendations`.
- `tools/playlist_kandidaten_messen.py` (neu): App-Regression (Generierung +
  Empfehlungen auf allen gecachten Tracks; `--ohne-kandidaten` fuer den Vergleich).
- `tools/rate_transitions.py prepare --modus kandidaten` scort mit
  `bass_swap_geplant=True` (Nachtrag im Teil-3-Handoff).
- Doku: `CLAUDE.md`, `.agents/skills/hpg-playlist-scoring`, `hpg-qt-gui`,
  `hpg-rekordbox`, `hpg-mixpoint-engineering`, `hpg-testing-verification`
  (nach Merge nach `.claude/` spiegeln).
- Tests: `tests/test_candidate_choices.py` (neu), `tests/test_playlist_kandidaten.py`
  (neu, inkl. Kette/DP, Outro-Limit-Toleranz), `tests/test_tools_playlist_kandidaten_messen.py`
  (neu), ergaenzt: `test_pair_candidates.py`, `test_tolerances.py`,
  `test_rekordbox_xml_exporter.py` (`TestKandidatenCues`), `test_main_workers.py`,
  `test_transition_weight_ui.py`, `test_rate_transitions.py`.

Suite im Worktree (HEAD `7b5befb`, vor dem Werkzeug-Fix `86e61ad`): **1869 passed,
25 warnings, Exit 0** (Coverage-Gate 70 bestanden). Endstand nach Merge steht im
Gesamt-Handoff.

## Messung (2026-08-22, `hpg_cache_v34.db`, 231 Tracks, Harmonic Flow, ±2 BPM)

`tools/playlist_kandidaten_messen.py --cache --strategie "Harmonic Flow" --bpm 2.0`
(Endlauf mit `86e61ad`, Ergebnis `app_v34_final.json` im Scratchpad):

| Kennzahl | mit Kandidaten | ohne Kandidaten (`--ohne-kandidaten`) |
|---|---|---|
| Paare / mit Kandidat | 230 / **220** | 230 / 0 |
| Schema Out (aktiver Kandidat) | pssi_phrase 204, sektion 11, analyzer 5 | — |
| Schema In (aktiver Kandidat) | pssi_phrase 203, sektion 14, analyzer 3 | — |
| `bass_swap`-Anteil | 0,9 % (2 Paare) | — |
| Intro/Outro-Verletzungen der Plan-Punkte | **0** | — |
| Plan-Overlap ≠ Kandidaten-Blende | **0** | — |
| Cue-Gate-Verletzungen (Mix-In i−1 ≥ Mix-Out i) | **2** = Ketten-Neustarts 2 | — |
| Score-Median | 79 | 83 |
| Generierung | 51,4 s (Endlauf; Laeufe zuvor 42–56 s) | 2 s |
| Empfehlungen | 1,1–1,5 s | — |

Laufzeit je Paar (`build_pair_candidates`, 500 Zufallspaare im Gate): 8,7 ms →
**3,3 ms Median** nach Optimierung (Entscheidung 16); Generierung 123 s → ~52 s.

Verlauf der Konsistenz-Kennzahl: Cue-Gate-Verletzungen 73 (Einzelpaar-Rang 1) →
23 (Greedy, Entscheidung 15) → 2 (Kette per DP, Entscheidung 17). Die zwei
verbleibenden sind Paare ohne konsistenten Anschluss (kein Kandidat von Track i
liegt zwei Phrasen hinter seinem Mix-In aus dem vorigen Paar); dort beginnt die
Kette neu, `kandidat_konsistent = False`, die Tabelle zeigt es, der Export laesst
diesen Track wie bisher mit Meldung aus (`_cue_export_allowed`).

Overlap-Abweichungen: 27 (Plan-Clamp kuerzte Blenden, die ueber das Ende von B
liefen) → Gate `blende_ueber_b_ende` (Entscheidung 18) → 12 aus
`_outro_overlap_limit` (1-ms-Rundungsrest kostete einen Takt, Entscheidung 19;
die 12 stammen aus einer Ad-hoc-Diagnose im Scratchpad und stehen nur im
Commit-Text `7b5befb`, nicht in einer Ergebnisdatei — die gespeicherten Laeufe
mit dem damaligen Werkzeug zeigen 25 bzw. 18) → 0. Die 18 waren ein Messfehler
des Werkzeugs (es verglich Rang 1 statt des aktiven Ketten-Kandidaten) —
behoben in `86e61ad` (Entscheidung 20), Kennzahl `kette_neustarts` ergaenzt.

Score-Median 79 vs. 83: der Kandidaten-Score misst lokal am Mixpunkt (Groove,
Bass, Lautheit, Struktur, Kick-Konflikt) und ist strenger als der trackweite
Altpfad — Startwerte, der Hoertest ersetzt sie (Teil 3).

## Die 20 Entscheidungen (Plan, Spec offen) — Kurzfassung

1 Track-Felder `mix_in_point/mix_out_point` bleiben Analyse-Werte, `TransitionPlan`
traegt den aktiven Kandidaten fuer alle Leser (Abweichung vom Spec-Wortlaut);
2 Kandidaten-Score ersetzt die Faktor-Kombination nur, wenn ein Kandidat existiert;
3 `select_pair_candidate`/`rank_pair_candidates` mit gespeicherter Wahl und
`schema_rang`-Tiebreak; 4 `bass_swap_geplant` (App und Hoertest-prepare True,
`paar_kandidaten_messen` False); 5 `transition_type = bass_swap` bei Pflicht;
6 `candidate_choices.json`; 7 Wahl in Datei statt im `scoring_context`
(Abweichung, gleiche Wirkung in allen Konsumenten, HPG-001); 8 GUI-Tabelle mit
Begruendungsspalte, Berechnung/Verteilung getrennt; 9 Tabelle Mix-In/Out aus dem
Plan mit Quelle-Tooltip (Zugabe); 10 Regler Lautheit, `write_override_kandidaten`,
Statuszeile (Zugabe), `write_override` erhaelt Kandidaten-Schluessel; 11 Export
`HPG K<n>` je Seite 1..6 nach Dedupe, nicht `PairCandidate.rang`; 12 BPM-Default
2.0 — kein Bestandstest prueft den alten Default 3, neuer Test fuer 2;
13 dauerhafter Paar-Cache mit Reset-Hooks, Kandidatenpfad nur im BPM-Gate;
14 Regressionswerkzeug; 15 sequentielle Konsistenz je Playlist; 16 Laufzeit-
Optimierung; 17 Kettenwahl per DP; 18 Gate `blende_ueber_b_ende`;
19 `_outro_overlap_limit` mit Gitter-Toleranz; 20 Messwerkzeug vergleicht den
aktiven Kandidaten (`kette_neustarts`).

## Benannte Abweichungen vom Spec-Wortlaut

- Entscheidung 1 (Track-Felder nicht mutiert, Plan traegt Rang 1).
- Entscheidung 7 (Wahl in `candidate_choices.json` statt im `scoring_context`).
- Entscheidungen 9/10 (Quelle-Tooltips, Regler-Statuszeile, `write_override`
  erhaelt Kandidaten-Schluessel — Zugaben).
- Entscheidung 11 (`HPG K<n>` je Seite fortlaufend nach Dedupe).
- Entscheidung 4: `prepare --modus kandidaten` scort seit Teil 4 ohne Kick-Abzug
  (Teil-3-Verhalten geaendert, dort nachgetragen).
- Entscheidungen 15/17: Sortierung bleibt paarweise (Spec), die Empfehlungen
  waehlen die Kette — die Plan-Punkte koennen daher von Rang 1 abweichen
  (`kandidat_aktiv` nennt den Rang). Der Karten-Score (`compatibility_score`
  aus den Metriken) gehoert dabei zu Rang 1, nicht zum markierten
  Ketten-Kandidaten, wenn `kandidat_aktiv > 1`.

## Hinweise

- App-Toleranz > `PAAR_BPM_MAX` (2.0): in einer Sortierung mischen sich
  Kandidaten-Scores (Paare ≤ 2 BPM) und Altpfad-Scores (Paare > 2 BPM) —
  Spec-konform (Kandidaten nur im 2-BPM-Gate), aber sichtbar im Score-Median.
- Generierung mit Kandidaten dauert ~52 s fuer 231 Tracks (2 s ohne); der Paar-
  Cache haelt die zweite Sortierung, Empfehlungen und Panels bei ~1 s. Keine
  stille Kappung.
- `candidate_preferences.json` ist `{}` (Teil 3 nicht uebernommen) — Regler
  Lautheit wirkt ueberall; `score_pair` nimmt die Toleranz-Gewichte.
- `_PAIR_CANDIDATE_CACHE` ist dauerhaft, Schluessel = Track-Identitaet
  (Dateipfad); Reset-Hooks gibt es fuer Wahl, Praeferenz, Toleranzen — nicht
  fuer eine In-Session-Neuanalyse derselben Datei (aktuell kein solcher Pfad in
  der App; kaeme einer dazu, muss er `reset_pair_candidate_cache()` rufen).

## Waechter Tor 2 (MIT AUFLAGEN, eingearbeitet)

1. Reorder-Pfad (`PlaylistPanel._update_table_after_reorder`) setzt die Spalten
   Mix-In/Out nach der Neuberechnung aus dem Plan (Test
   `test_reorder_setzt_mixpunkt_spalten_aus_neuen_empfehlungen`).
2. Dateiname im Handoff korrigiert (`rekordbox_xml_exporter.py`).
3. Exporter-Dedupe nutzt `QUANTIZE_TOLERANCE_SEC` statt 0.05 hart codiert.
4. Skills (`hpg-playlist-scoring`, `hpg-mixpoint-engineering`), Docstring
   `_kandidaten_fuer_paar` (Cache dauerhaft), Handoff (20 Entscheidungen,
   Tabellenbeschriftung "aktiver Kandidat") berichtigt.
5.–7. Hinweise Karten-Score, Cache-Schluessel, Herkunft der "12" oben eingetragen.

## Checkliste Hoerproben (Mensch — vom Agenten uebersprungen)

1. App starten, 231 Tracks laden (Cache), Harmonic Flow ±2 BPM generieren;
   im Uebergangs-Panel die Kandidatentabelle je Paar pruefen (Rang 1 markiert,
   Begruendung lesbar) und die Preview der Rang-1-Kandidaten hoeren — stimmt
   Mix-Out/Mix-In/Blende mit dem Gehoerten?
2. In mindestens 10 Paaren einen anderen Kandidaten anklicken: Preview neu,
   Tabelle Mix-In/Out, Timeline und Karten-Text muessen dieselben Zeitpunkte
   zeigen; nach Neustart der App muss die Wahl wieder Rang 1 sein
   (`candidate_choices.json`).
3. Paare mit `kandidat_konsistent = False` (2 in der Messung) anhoeren: Kette
   beginnt neu — ist der Bruch hoerbar?
4. Regler "Lautheit (Kandidaten)" bewegen: Rangfolge aendert sich, Preview folgt.
5. Rekordbox-XML exportieren, in Rekordbox importieren: MIX IN/OUT und Memory-
   Cues `HPG K1..K6 OUT|IN <schema>` am richtigen Ort; Tracks mit Export-Meldung
   (Cue-Gate) pruefen.
6. Teil-3-Checkliste (Hoertest Kandidatenmodus, `fit`, Uebernahme) bleibt offen;
   nach Uebernahme App-Lauf wiederholen.
7. Offen aus Teil 2: `KICK_AKTIV_*`-Startwerte markieren fast nie einen Kick;
   `percussive_ratio_lokal` haelftig unter 0.3 — im Hoertest pruefen.
