# Mixpunkt-Kandidaten Teil 4 (App) — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die App benutzt die Paar-Kandidaten: Scoring je Paar ueber den besten `PairCandidate` (lokal an der Naht), Rang 1 bestimmt Mix-Out/Mix-In/Blende fuer Preview, Timeline, Tabelle und Export; das Uebergangs-Panel zeigt alle Kandidaten (Rang, Zeitpunkte, Blende, Schema, Score + Teilwerte, Begruendung), ein Klick macht einen Kandidaten aktiv, die Wahl wird je Paar gespeichert und beim naechsten Lauf bevorzugt; Faktoren-Regler um Lautheit erweitert; Rekordbox-XML schreibt Rang 1 als MIX IN/OUT und alle Kandidaten als Memory-Cues `HPG K1..K6`; App-BPM-Default 2.0. Spec: `docs/superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md`, Abschnitt 4 (Z. 178–212).

**Architecture:** `hpg_core/pair_candidates.py` bekommt `select_pair_candidate` (Wahl aus `candidate_choices.json` > Rang 1; Tiebreak `schema_rang` aus `candidate_preferences`). `hpg_core/candidate_choices.py` (neu) persistiert die Wahl je Paar. `playlist.calculate_enhanced_compatibility` nutzt — wenn beide Tracks Kandidaten tragen — den besten `PairCandidate` (Score, lokale Teilwerte, neue Metrik-Felder `loudness_match`, `structure_match`, `kandidat`); ohne Kandidaten bleibt der heutige Pfad. `compute_transition_recommendations` setzt Mix-Out/Mix-In/Blende aus dem aktiven Kandidaten (nach DJ-Brain, vor Clamp), waehlt `bass_swap` bei `bass_swap_pflicht`, haengt `kandidaten`/`kandidat_aktiv` an `TransitionRecommendation`. `main.py`: Kandidatentabelle in der Uebergangs-Karte, Klick → Wahl speichern + Neuberechnung ueber einen gemeinsamen Pfad (`_verteile_uebergaenge`), Mix-In/Out-Spalten zeigen Rang 1 des Paars, Regler "Lautheit", BPM-Default 2.0. Exporter bekommt optional die Empfehlungen. **Track-Felder `mix_in_point/mix_out_point` bleiben Analyse-Werte (Cache)**; "Rang 1" fliesst ueber `TransitionPlan` in alle Leser (Entscheidung 1).

**Tech Stack:** Python 3.12 (`.\venv312\Scripts\python.exe`), PyQt6, pytest (`--no-cov`), pytest-qt fuer Widget-Tests. Kein neuer Dependency.

**Auflagen:** genau so wie in der Spec, vollstaendig, keine Annahmen; GUI nur das Noetige (Spec: "nur das Noetige"); Waechter an Tor 1 und Tor 2; UI-Updates nur im Main-Thread; HPG-001 (alle fuenf Konsumenten sehen denselben Kontext); keine Rueckfragen (100 % autonom, Entscheidungen hier).

**Grundlagen (verifiziert 2026-08-22, `docs/superpowers/plans/2026-08-22-faktenblatt-kandidaten-teil4.md`, Code auf Branch `kandidaten-teil3`):**
- `playlist.calculate_enhanced_compatibility` :313-493 (Cache-Key mit kwargs :204-224; Scoring-Block :396-449; `ai_bonus` :459-460; Vocal :468-472; Hard-Gate :477-478; `TransitionMetrics` :105-120). `compute_transition_recommendations` :1674-1882 (DJ-Brain-Override :1768-1786, Clamp :1791-1801, `predict_transition_type` :1837-1839, Plan :1852-1861, Recommendation :1862-1880). `_resolve_mix_points` :1220-1250. `TransitionPlan` frozen :146-163, `TransitionRecommendation` :124-143. `compute_adjacent_transition_metrics` :1659-1671, `calculate_playlist_quality` :1885-1955, `resolve_scoring_context` :2149-2169. `_ENHANCED_COMPAT_CACHE`/`_COMPAT_CACHE` Modul-Globals, nur in `generate_playlist` gesetzt.
- `main.py`: `resolve_transition_mix_points` :175-206 (plan zuerst); `TransitionRenderWorker.run` :748 (`from_plan`); `MixTipsPanel` :3426-3914 (`_populate` :3481-3689, Timing-Label :3572-3589, `_card_layouts` :3681, `setup_transition_previews` :3691-3706, `_request_preview` :3708, `_preview_cache` :3443); `PlaylistPanel._populate_table` :3226 (Mix-In/Out :3275-3282), `_update_table_after_reorder` :3371-3423, `set_playlist_data` :3076-3083; `TimelinePanel.set_timeline` :3930; Regler :1549-1676 (`transition_weight_sliders` :1561, Liste :1562-1567, `_on_transition_weight_changed` :1610-1632 → `write_override`, `_lade_transition_regler` :1661-1676); BPM-Slider :2707-2714 (`setValue(3)`, Label "±3", Tooltip "±3 BPM empfohlen"); `current_bpm_tolerance = 3.0` :4299; `AnalysisWorker.__init__ bpm_tolerance=3.0` :504-509; `PlaylistPanel.bpm_tolerance = 3.0` :2933, `set_playlist_data(..., bpm_tolerance=3.0)` :3081; `analysis_finished` :4788-4860 (Verteilung :4842-4855), `_on_playlist_reordered` :5008-5030, `_export_m3u8` :5071, `_export_rekordbox_xml` :5094 (nur `self.playlist`).
- `rekordbox_xml_exporter.py`: `export(playlist, output_path, playlist_name)` :90ff, Schleife :144 → `_add_track_to_collection(xml, track, idx)` :210 → `_add_cue_points(xml, rb_track, track)` :306-346 (MIX IN Num 0/-1, MIX OUT Num 1/-1, DROP/BREAKDOWN Num -1), `_cue_export_allowed` :348-364.
- `tolerances.write_override(gewichte)` :92-113 (summiert alle uebergebenen Schluessel, skaliert nur die vier Alt-Gewichte) — die zehn `kandidaten_*_weight` duerfen nicht in diese Summe.
- `pair_candidates.py`: `build_pair_candidates` :506-540, `dedupe_and_cap` :429 (Sortierung `_sortschluessel` mit `SCHEMA_RANG`), `score_pair` (Flags `bass_swap_pflicht`, `KICK_KONFLIKT_ABZUG` in `_teil_bass`); `candidate_preferences.schema_rangfolge(genre)`.
- Keine Settings-Persistenz in `main.py`; kein `%LOCALAPPDATA%\HPG`-Helfer ausser `caching._default_cache_file`/`tolerances._override_pfad`/`candidate_preferences._override_pfad`.
- Einrueckung: `main.py`, `playlist.py`, `pair_candidates.py`, Exporter, neue Module 4; `tests/test_main_workers.py`, `test_run_lifecycle.py`, `test_playlist_quality.py`, `test_exporters.py`, `test_rekordbox_xml_exporter.py`, `test_transition_weight_ui.py` 2; `tests/test_pair_candidates.py` 4.

**Entscheidungen an Stellen, die die Spec offen laesst (Waechter Tor 1 vorlegen):**
1. **Abweichung vom Spec-Wortlaut** "Track.mix_in_point/mix_out_point = Rang 1" (Abschnitt 1 Z. 50-52, Abschnitt 4 Z. 186-187): der Paar-Rang 1 haengt vom Partner ab (Teil-1-Plan: "Rang-1-Zuweisung aus der Paar-Bewertung ist Teil 2/4"), gecachte Track-Objekte zu mutieren waere falsch. Umsetzung: `TransitionPlan.mix_out_a/mix_in_b/overlap` tragen den aktiven Kandidaten, und **alle** Leser lesen den Plan — vollstaendige Leserliste: Preview (`resolve_transition_mix_points` bevorzugt plan — heute schon), `TransitionRenderWorker.run` (`from_plan` — heute schon), Timeline (`rec.plan` — heute schon), Karten-Text im `MixTipsPanel` (liest `dj_rec.adjusted_*` → werden mitgezogen), Tabelle Mix-In/Out in `PlaylistPanel._populate_table` (neu) **und** `MainWindow.on_ai_finished` :4723-4730 (neu — schreibt die Spalten nach dem KI-Lauf erneut), Export (neu: Empfehlungen werden uebergeben), `dj_rec.adjusted_mix_out_a/in_b` (werden auf die Kandidaten-Zeitpunkte gesetzt). Track-Felder bleiben die Analyse-Werte.
2. Scoring: wenn `TRANSITION_FEATURES_ENABLED` und beide Tracks Kandidaten tragen (`mix_out_candidates` von A, `mix_in_candidates` von B nicht leer) und `select_pair_candidate` einen Kandidaten liefert, ist `overall_score = kandidat.score` (+ `ai_bonus`, BPM-Hard-Gate wie heute; Vocal-Clash und Half/Double stecken im Kandidaten-Score). `groove_match/bass_continuity/timbre_match/mood_match` werden mit den **lokalen** Teilwerten des Kandidaten belegt; neue optionale Felder `loudness_match`, `structure_match`, `kandidat` (Dict `PairCandidate.to_dict()`). Liefert `select_pair_candidate` nichts (keine Kandidaten, alle Kombinationen an Paar-Gates gescheitert), gilt der heutige trackweite Pfad (kein Bruch fuer Bestandsdaten/Tests).
3. `select_pair_candidate(track_a, track_b, *, energy_direction, harmonic_strictness, allow_experimental, tolerances=None, wahl=None) -> PairCandidate | None`: `build_pair_candidates(..., bass_swap_geplant=True)`; eine gespeicherte Wahl (`candidate_choices.hole(track_a, track_b)` = `{"t_out","t_in","blend_bars"}`) wird — falls noch unter den Kandidaten (|dt| <= `QUANTIZE_TOLERANCE_SEC`, gleiche Blende) — nach vorn gezogen (Rang 1), die uebrigen folgen nach Score. Tiebreak bei gleichem Score: `candidate_preferences.schema_rangfolge(genre_a)` (Teil 3) vor `SCHEMA_PRIORITAET`. Rueckgabe = Rang 1; die volle Liste liefert `rank_pair_candidates(...)` (gleiche Logik, fuer Panel/Export).
4. `score_pair(..., bass_swap_geplant: bool = False)`: bei True entfaellt `KICK_KONFLIKT_ABZUG` (der geplante Bass-/EQ-Swap loest den Kick-Konflikt; Flag `bass_swap_pflicht` bleibt gesetzt). Die App ruft mit `bass_swap_geplant=True`, weil sie bei `bass_swap_pflicht` den Uebergangstyp `bass_swap` waehlt (Entscheidung 6 aus Teil 2). `tools/rate_transitions.py prepare --modus kandidaten` ruft ebenfalls mit True (der Hoertest rendert `pro_eq_swap`, also mit Bass-Swap) — sonst wuerde die CSV einen Abzug tragen, den der Clip nicht enthaelt. `tools/paar_kandidaten_messen.py` bleibt bei False (misst den reinen Paar-Score).
5. Uebergangstyp: `bass_swap`, wenn `kandidat.flags["bass_swap_pflicht"]`, sonst `predict_transition_type` wie heute. `eq_mode = transition_type` (wie heute).
6. `candidate_choices.json`: `%LOCALAPPDATA%\HPG\candidate_choices.json` (Env `HPG_CANDIDATE_CHOICES_FILE`), Schluessel `"<normcase(abspath A)>||<normcase(abspath B)>"`, Wert `{"t_out", "t_in", "blend_bars", "zeit"}`; Modul `hpg_core/candidate_choices.py` mit `hole`, `merke`, `vergiss`, `reset_cache`; Schreiben atomar (`tempfile` + `os.replace`).
7. `scoring_context` (HPG-001): **Abweichung vom Spec-Wortlaut** ("scoring_context um die Kandidaten-Wahl erweitert", Z. 187-188): die Wahl liegt **nicht** im Kontext-Dict, sondern wird je Paar aus `candidate_choices.json` gelesen — in allen fuenf Konsumenten auf demselben Weg (`calculate_enhanced_compatibility` → `_kandidaten_fuer_paar` → `rank_pair_candidates` → `candidate_choices.hole`), also mit derselben Wirkung; der Kontext bleibt `harmonic_strictness/allow_experimental/target_energy/overlap`. Begruendung: ein Dict mit bis zu n−1 Wahlen je Lauf wuerde in jeden Cache-Key (`repr(kwargs)`) wandern und jede Sortierung verlangsamen; die Datei ist die eine Quelle. Nach einem Klick wird nicht neu sortiert, nur Metriken + Quality + Empfehlungen + Panels (`_berechne_uebergaenge`/`_verteile_uebergaenge`); `reset_pair_candidate_cache` in `merke` haelt den Cache frisch. Die Sortierung beim **naechsten** Lauf sieht die Wahl — Spec: "beim naechsten Lauf bevorzugt".
8. GUI (nur das Noetige): in jeder Uebergangs-Karte eine `QTableWidget` "Kandidaten" (Spalten: Rang, Mix-Out A [s], Mix-In B [s], Blende [Takte], Schema (out → in), Score, Teilwerte (Kurzform `H .75 T 1.0 E .98 G 1.0 Gr .83 B .60 K .72 S .99 L .77 St .07`), **Begruendung als sichtbare Spalte** (Spec Z. 192-194 zaehlt sie zum Tabelleninhalt; zusaetzlich Tooltip); aktive Zeile markiert; Klick/Enter → Signal `candidate_chosen(index, rang)`. MainWindow trennt **Berechnung** und **Verteilung** (Waechter Tor 1, Auflage 4): `_berechne_uebergaenge(bpm_tolerance, scoring_context) -> (transition_metrics, quality_metrics, transition_plan)` (= die drei Aufrufe aus `analysis_finished` :4820-4829) und `_verteile_uebergaenge(transition_plan)` (= Verteilung :4842-4855 an `playlist_panel`, `mix_tips_panel`, `timeline_panel`, `analytics_panel`, Toolbar). `analysis_finished` ruft beides (Verhalten unveraendert), `_on_playlist_reordered` bleibt **unveraendert** (Quality/Recs rechnet dort schon `PlaylistPanel._update_table_after_reorder`, :3371-3423), `_on_candidate_chosen` ruft beides nach `candidate_choices.merke` (die Wahl aendert den Paar-Score → Metriken, Quality, Empfehlungen neu; `reset_pair_candidate_cache` laeuft in `merke`). Preview-Cache des betroffenen Paars wird verworfen (Clip gehoert zum alten Plan).
9. Tabelle Mix-In/Mix-Out (`PlaylistPanel._populate_table` :3275-3282 **und** `MainWindow.on_ai_finished` :4723-4730 — zweiter Leser, Waechter Tor 1 Auflage 1): zeigt fuer Track i den Mix-In aus der Empfehlung (i−1 → i) und den Mix-Out aus (i → i+1), wenn vorhanden (`rec.plan.mix_in_b`/`mix_out_a`, `kandidat_aktiv > 0`), sonst Track-Wert; Tooltip nennt die Quelle ("Kandidat Rang n" / "Analyse") — Tooltip ist eine kleine Zugabe ueber die Spec hinaus, hier benannt.
10. Regler: neuer Slider "Lautheit (Kandidaten)" mit Schluessel `kandidaten_loudness_weight`; `tolerances.write_override_kandidaten(gewichte)` schreibt die uebergebenen `kandidaten_*_weight` und skaliert die uebrigen neun proportional auf Rest (Summe 1.0; Validierung in der Funktion: bekannte Schluessel, Werte >= 0, Summe < 1); `_on_transition_weight_changed` trennt Schluessel nach Praefix. `candidate_preferences` (Hoertest) hat Vorrang vor Toleranzen in `score_pair` (Teil 3) — der Regler wirkt also nur, solange keine Praeferenz fuer das Genre vorliegt; die Statuszeile sagt das ("Hoertest-Praeferenz aktiv fuer: Psytrance — Regler ohne Wirkung dort") — Zugabe ueber die Spec hinaus, hier benannt. `write_override` (Track-Regler) erhaelt dabei vorhandene `kandidaten_*`-Schluessel (noetig fuer die Koexistenz beider Gruppen in einer Datei).
11. Export: `RekordboxXMLExporter.export(playlist, output_path, playlist_name, transitions=None)`; mit `transitions` (Liste `TransitionRecommendation`, Laenge n−1): MIX OUT von Track i = `transitions[i].plan.mix_out_a`, MIX IN von Track i = `transitions[i-1].plan.mix_in_b` (sonst Track-Wert), zusaetzlich Memory-Cues `HPG K<n> OUT <schema_out>` auf Track A und `HPG K<n> IN <schema_in>` auf Track B — **`n` je Seite fortlaufend 1..k nach Dedupe gleicher Zeitpunkte in Rang-Reihenfolge** (Rang 1 → K1; `PairCandidate.rang` laeuft bis 12 und wird NICHT als Name benutzt — Waechter Tor 1 Auflage 3), hoechstens 6 je Seite (Spec K1..K6), **nur bei `outro_covered`** (Gate `_cue_export_allowed` bleibt, prueft die effektiven Punkte; ein Track, dessen Kandidaten-Mix-In (Paar i−1) nicht vor dem Kandidaten-Mix-Out (Paar i) liegt, faellt wie heute mit Meldung aus — Task 8 zaehlt das). m3u8 unveraendert (kennt keine Cues). `main._export_rekordbox_xml` uebergibt `self.playlist_panel.transition_recommendations`.
12. App-BPM-Default 2.0 (Spec): `main.py` Slider `setValue(2)`, Label "±2", Tooltip "±2 BPM (Hoertest-Gate)"; `current_bpm_tolerance = 2.0`; `AnalysisWorker` Default 2.0; `PlaylistPanel` Defaults 2.0. `playlist.py`-API-Defaults (3.0) bleiben (Bibliotheks-API, nicht App). **Es gibt keinen Bestandstest, der den App-Default 3 prueft** (Grep `setValue(3)`, `.value() == 3`, `current_bpm_tolerance` in `tests/`: 0 Treffer — Waechter Tor 1) — es wird also kein Test umgestellt, sondern ein neuer Test fuer 2 angelegt (Task 7). Hinweis fuers Handoff: bei App-Toleranz > `PAAR_BPM_MAX` (2.0) mischen sich in einer Sortierung Kandidaten-Scores (Paare ≤ 2 BPM) und Altpfad-Scores (Paare > 2 BPM) — das ist Spec-konform (Kandidaten nur im 2-BPM-Gate), steht aber im Handoff.
13. Laufzeit — **gemessen 2026-08-22 (231 Tracks, 500 Zufallspaare im 2-BPM-Gate): `build_pair_candidates` Median 8,7 ms, p90 10,7 ms, max 22 ms je Paar; `rank_pair_candidates` Median 9,6 ms.** Alle 14 186 Paare im Gate waeren ≈ 135 s — zu viel, um je Leser neu zu rechnen. Deshalb: (a) `_PAIR_CANDIDATE_CACHE` ist **dauerhaft** aktiv (Modul-Dict, Schluessel wie `_enhanced_cache_key`: Track-Identitaet + `energy_direction` + kwargs), nicht nur waehrend `generate_playlist` (nur `generate_playlist` schaltet heute die anderen Caches; `benchmark_algorithms` nicht); `playlist.reset_pair_candidate_cache()` leert ihn und wird von `candidate_choices.merke/vergiss/reset_cache`, `candidate_preferences.reset_cache` und `tolerances.reset_cache` lazy aufgerufen (Wahl, Praeferenz oder Gewichte aendern die Rangfolge); (b) im Scoring wird der Kandidatenpfad **nur** betreten, wenn `bpm_diff <= bpm_tolerance` (sonst ist der Score ohnehin 0 — spart das Gros der 231²-Paare bei grossen Sammlungen); (c) `compute_transition_recommendations`, `compute_adjacent_transition_metrics`, `_populate_table`, Preview lesen denselben Cache. Task 9 misst Generierung + Empfehlungen an den 231 Tracks mit/ohne Kandidaten; keine stille Kappung — wird es zu langsam, steht die Zahl im Handoff.
14. Regressionsmessung (Spec Tests): `tools/playlist_kandidaten_messen.py --cache --strategie "Harmonic Flow" --bpm 2.0`: Generierung + Empfehlungen auf allen gecachten Tracks; Zahlen: Dauer, Paare mit Kandidat, Rang-1-Schemata, `bass_swap`-Anteil, Plan-Punkte innerhalb Intro/Outro-Guard (muss 0 Verletzungen sein), Vergleich Score mit/ohne Kandidaten (Median).
15. **Sequentielle Konsistenz je Playlist (Befund der ersten Messung, 2026-08-22: 73 von 230 Tracks hatten Kandidaten-Mix-In (Paar i−1) hinter dem Kandidaten-Mix-Out (Paar i) — Invariante 1 je Track verletzt, der Track wuerde "rueckwaerts" gespielt).** Die Paar-Bewertung ist bewusst unabhaengig je Paar (Spec Abschnitt 2); in `compute_transition_recommendations` wird deshalb je Paar der **erste Kandidat der Rangfolge genommen, dessen `t_out` mindestens zwei Phrasen (`2 · seconds_per_bar · phrase_unit` von Track i, Invariante 3) hinter dem im vorigen Paar festgelegten Mix-In von Track i liegt** (`_konsistenter_kandidat`); gibt es keinen, bleibt Rang 1 und `TransitionRecommendation.kandidat_konsistent = False` (Tabelle markiert die aktive Zeile, Handoff zaehlt). `kandidat_aktiv` ist dann der Rang des konsistenten Kandidaten. Sortierung (`calculate_enhanced_compatibility`) bleibt paarweise — sie bewertet Paare, nicht Ketten; das ist Spec-konform, aber eine benannte Folge (Handoff).
16. **Laufzeit nach Optimierung** (gemessen 2026-08-22, 500 Paare): `build_pair_candidates` 8,7 ms → 3,3 ms Median (Score/Gates einmal je (Out, In), flache Kopien statt `asdict`); App-Messung Generierung Harmonic Flow 231 Tracks: 123 s vor der Optimierung, 42–48 s danach, 2 s ohne Kandidaten — die Endzahl steht im Handoff Teil 4.
17. **Kettenwahl statt Greedy** (Praezisierung von 15): `_kette_waehlen` waehlt je Playlist per dynamischer Programmierung die Kandidatenkette mit maximaler Score-Summe unter der Konsistenzbedingung (gespeicherte Wahl mit Bonus `_WAHL_BONUS` = 10, damit sie gegen jeden Score-Unterschied gewinnt, solange die Kette konsistent bleibt); ist fuer ein Paar kein konsistenter Anschluss moeglich, beginnt die Kette dort neu (`kandidat_konsistent = False`). Messung 231 Tracks: Cue-Gate-Verletzungen 73 (Einzelpaar-Rang-1) → 23 (Greedy) → 2 (Kette). Toleranz der Konsistenzpruefung = `QUANTIZE_TOLERANCE_SEC` (Teil 1 rundet `t` auf 3 Dezimalen).
18. **Gate `blende_ueber_b_ende`** (Praezisierung Spec Schritt 1, wie `crossfade_reserve` im Hoertest und der Playlist-Clamp): die Blende muss ab `in_b` vor dem Ende von Track B enden — sonst kuerzte `_clamp_transition_overlap` den Plan still (27 von 220 Paaren), und die Kandidatentabelle zeigte eine andere Blende als der Renderer spielt.

---

## Dateistruktur

| Datei | Verantwortung |
|---|---|
| Create `hpg_core/candidate_choices.py` | Wahl je Paar persistieren (`hole`, `merke`, `vergiss`, `reset_cache`, Pfad) |
| Modify `hpg_core/pair_candidates.py` | `score_pair(bass_swap_geplant)`, `build_pair_candidates(bass_swap_geplant, schema_rang)`, `rank_pair_candidates`, `select_pair_candidate` |
| Modify `hpg_core/playlist.py` | `TransitionMetrics` (+3 Felder), `calculate_enhanced_compatibility` (Kandidatenpfad), `_PAIR_CANDIDATE_CACHE`, `TransitionRecommendation` (+`kandidaten`, `kandidat_aktiv`), `compute_transition_recommendations` (Kandidaten-Zeitpunkte, `bass_swap`) |
| Modify `hpg_core/tolerances.py` | `write_override_kandidaten` |
| Modify `hpg_core/exporters/rekordbox_xml_exporter.py` | `export(..., transitions=None)`, Rang-1-Cues, `HPG K<n>` Memory-Cues |
| Modify `main.py` | Kandidatentabelle + Signal im `MixTipsPanel`, `_verteile_uebergaenge`, Wahl-Handler, Mix-In/Out-Spalten aus Empfehlung, Regler Lautheit, BPM-Default 2.0, Export mit Empfehlungen |
| Modify `tools/rate_transitions.py` | `build_pair_candidates(..., bass_swap_geplant=True)` im Kandidatenmodus |
| Create `tools/playlist_kandidaten_messen.py` | App-Regressionsmessung |
| Tests | Create `tests/test_candidate_choices.py` (4), `tests/test_playlist_kandidaten.py` (4), `tests/test_tools_playlist_kandidaten_messen.py` (4); Modify `tests/test_pair_candidates.py` (4), `tests/test_tolerances.py` (2), `tests/test_rekordbox_xml_exporter.py` (2), `tests/test_transition_weight_ui.py` (2), `tests/test_main_workers.py` (2), `tests/test_rate_transitions.py` (4) |

---

### Task 0: Waechter Tor 1

- [ ] **Step 1:** Subagent `hpg-waechter` mit Dateitabelle, den 14 Entscheidungen, Spec Abschnitt 4. Ausdruecklich: Entscheidung 1 (Track-Felder nicht mutiert, Plan traegt Rang 1), 2 (Kandidaten-Score ersetzt Faktor-Kombination nur wenn Kandidat vorhanden), 4 (`bass_swap_geplant` auch im Hoertest-prepare — Teil-3-Verhalten aendert sich), 12 (Bestandstests zum BPM-Default werden umgestellt), 13 (Laufzeit gemessen, nicht geschaetzt). Auflagen vor Task 1 einarbeiten.

---

### Task 1: `candidate_choices.py`

**Files:** Create `hpg_core/candidate_choices.py`; Test `tests/test_candidate_choices.py` (4 Leerzeichen)

- [ ] **Step 1: Failing tests**

```python
"""Tests fuer die Persistenz der Kandidaten-Wahl je Paar (Teil 4)."""
import json

import pytest

from hpg_core import candidate_choices as cc


@pytest.fixture(autouse=True)
def _datei(monkeypatch, tmp_path):
    monkeypatch.setenv("HPG_CANDIDATE_CHOICES_FILE", str(tmp_path / "choices.json"))
    cc.reset_cache()
    yield
    cc.reset_cache()


def test_schluessel_ist_pfadnormiert_und_gerichtet():
    k1 = cc.schluessel("C:/Musik/A.mp3", "c:\\musik\\b.mp3")
    k2 = cc.schluessel("c:\\MUSIK\\a.mp3", "C:/Musik/B.mp3")
    assert k1 == k2
    assert cc.schluessel("a.mp3", "b.mp3") != cc.schluessel("b.mp3", "a.mp3")


def test_merke_und_hole_roundtrip(tmp_path):
    assert cc.hole("a.mp3", "b.mp3") is None
    cc.merke("a.mp3", "b.mp3", t_out=160.0, t_in=80.0, blend_bars=16)
    w = cc.hole("a.mp3", "b.mp3")
    assert w["t_out"] == 160.0 and w["t_in"] == 80.0 and w["blend_bars"] == 16 and w["zeit"]
    daten = json.loads((tmp_path / "choices.json").read_text(encoding="utf-8"))
    assert len(daten) == 1
    cc.reset_cache()
    assert cc.hole("a.mp3", "b.mp3")["t_out"] == 160.0        # neu geladen


def test_vergiss_entfernt_nur_das_paar():
    cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=8)
    cc.merke("a.mp3", "c.mp3", t_out=3.0, t_in=4.0, blend_bars=8)
    cc.vergiss("a.mp3", "b.mp3")
    assert cc.hole("a.mp3", "b.mp3") is None and cc.hole("a.mp3", "c.mp3")["t_out"] == 3.0


def test_kaputte_datei_wird_als_leer_behandelt(tmp_path):
    (tmp_path / "choices.json").write_text("{kaputt", encoding="utf-8")
    cc.reset_cache()
    assert cc.hole("a.mp3", "b.mp3") is None
    cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=8)   # ueberschreibt sauber
    assert cc.hole("a.mp3", "b.mp3")["t_out"] == 1.0
```

- [ ] **Step 2: Run → FAIL** (ModuleNotFoundError)

- [ ] **Step 3: Modul**

```python
"""Gespeicherte Kandidaten-Wahl je Trackpaar (Spec 2026-08-21, Abschnitt 4).

Ein Klick im Uebergangs-Panel merkt sich (t_out, t_in, blend_bars) fuer das
Paar (A, B); select_pair_candidate zieht diesen Kandidaten beim naechsten Lauf
nach vorn, wenn er noch unter den Kandidaten ist. Datei
%LOCALAPPDATA%/HPG/candidate_choices.json (oder HPG_CANDIDATE_CHOICES_FILE);
Schreiben atomar. Gerichtet: (A -> B) ist ein anderes Paar als (B -> A).
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)
_cache: dict | None = None


def _pfad() -> Path:
    env = os.environ.get("HPG_CANDIDATE_CHOICES_FILE")
    if env:
        return Path(env)
    basis = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".hpg")
    return Path(basis) / "HPG" / "candidate_choices.json"


def schluessel(pfad_a: str, pfad_b: str) -> str:
    norm = lambda p: os.path.normcase(os.path.abspath(str(p)))
    return f"{norm(pfad_a)}||{norm(pfad_b)}"


def _lade() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    p = _pfad()
    daten: dict = {}
    if p.is_file():
        try:
            roh = json.loads(p.read_text(encoding="utf-8"))
            daten = roh if isinstance(roh, dict) else {}
        except (OSError, ValueError) as exc:
            logger.warning("candidate_choices nicht lesbar (%s): %s — wird als leer behandelt", p, exc)
    _cache = daten
    return daten


def _schreibe(daten: dict) -> None:
    p = _pfad()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="candidate_choices_", suffix=".json", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(daten, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def hole(pfad_a: str, pfad_b: str) -> dict | None:
    w = _lade().get(schluessel(pfad_a, pfad_b))
    return dict(w) if isinstance(w, dict) else None


def merke(pfad_a: str, pfad_b: str, *, t_out: float, t_in: float, blend_bars: int) -> None:
    daten = dict(_lade())
    daten[schluessel(pfad_a, pfad_b)] = {
        "t_out": float(t_out), "t_in": float(t_in), "blend_bars": int(blend_bars),
        "zeit": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    _schreibe(daten)
    global _cache
    _cache = daten


def vergiss(pfad_a: str, pfad_b: str) -> None:
    daten = dict(_lade())
    daten.pop(schluessel(pfad_a, pfad_b), None)
    _schreibe(daten)
    global _cache
    _cache = daten


def reset_cache() -> None:
    global _cache
    _cache = None
```

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** `git add hpg_core/candidate_choices.py tests/test_candidate_choices.py && git commit -m "feat(wahl): candidate_choices — Kandidaten-Wahl je Paar persistieren"`

---

### Task 2: `pair_candidates`: `bass_swap_geplant`, `schema_rang`, `rank_pair_candidates`, `select_pair_candidate`

**Files:** Modify `hpg_core/pair_candidates.py`; Test `tests/test_pair_candidates.py`; Modify `tools/rate_transitions.py` (prepare Kandidaten: `bass_swap_geplant=True`), Test `tests/test_rate_transitions.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_pair_candidates.py — anhaengen
from hpg_core.pair_candidates import rank_pair_candidates, select_pair_candidate


def test_bass_swap_geplant_hebt_kick_abzug_auf():
    a, b = _track(), _track("b.mp3")
    s_ohne, t_ohne, f = score_pair(a, b, _voll(160.0), _voll(80.0), 16)
    s_mit, t_mit, f2 = score_pair(a, b, _voll(160.0), _voll(80.0), 16, bass_swap_geplant=True)
    assert f["bass_swap_pflicht"] and f2["bass_swap_pflicht"]
    assert t_mit["bass"] == pytest.approx(t_ohne["bass"] + 0.15) and s_mit > s_ohne


def test_select_zieht_gespeicherte_wahl_nach_vorn(monkeypatch, tmp_path):
    from hpg_core import candidate_choices as cc
    monkeypatch.setenv("HPG_CANDIDATE_CHOICES_FILE", str(tmp_path / "c.json")); cc.reset_cache()
    g = _grid()
    a = _track_mit_kandidaten("a.mp3", outs=[_voll(round(5 * g, 3), kick_aktiv=False),
                                             _voll(round(6 * g, 3), kick_aktiv=False, schema=["sektion"])])
    b = _track_mit_kandidaten("b.mp3", ins=[_voll(round(3 * g, 3), kick_aktiv=False)])
    erst = select_pair_candidate(a, b)
    assert erst is not None and erst.rang == 1
    # die schlechteste Kombination waehlen
    alle = rank_pair_candidates(a, b)
    letzte = alle[-1]
    cc.merke("a.mp3", "b.mp3", t_out=letzte.t_out, t_in=letzte.t_in, blend_bars=letzte.blend_bars)
    cc.reset_cache()
    gewaehlt = select_pair_candidate(a, b)
    assert (gewaehlt.t_out, gewaehlt.t_in, gewaehlt.blend_bars) == (letzte.t_out, letzte.t_in, letzte.blend_bars)
    assert gewaehlt.rang == 1 and gewaehlt.flags.get("gespeicherte_wahl") is True
    neu = rank_pair_candidates(a, b)
    assert [p.rang for p in neu] == list(range(1, len(neu) + 1))
    # Wahl, die es nicht mehr gibt -> normale Rangfolge
    cc.merke("a.mp3", "b.mp3", t_out=1.0, t_in=2.0, blend_bars=8); cc.reset_cache()
    assert select_pair_candidate(a, b).flags.get("gespeicherte_wahl") is False


def test_select_none_ohne_kandidaten():
    a, b = _track(), _track("b.mp3")
    assert select_pair_candidate(a, b) is None and rank_pair_candidates(a, b) == []


def test_schema_rang_aus_praeferenzen_bricht_gleichstand(monkeypatch):
    from hpg_core import candidate_preferences as cp
    g = _grid()
    o1 = _voll(round(5 * g, 3), kick_aktiv=False)                       # pssi_phrase
    o2 = _voll(round(6 * g, 3), kick_aktiv=False, schema=["sektion"])   # gleicher Score
    a = _track_mit_kandidaten("a.mp3", outs=[o1, o2])
    b = _track_mit_kandidaten("b.mp3", ins=[_voll(round(3 * g, 3), kick_aktiv=False)])
    assert "pssi_phrase" in select_pair_candidate(a, b).out_a.schema
    monkeypatch.setattr(cp, "schema_rangfolge", lambda genre: ["sektion", "pssi_phrase"])
    assert "sektion" in select_pair_candidate(a, b).out_a.schema
```

```python
# tests/test_rate_transitions.py — anhaengen
def test_prepare_kandidaten_ruft_build_mit_bass_swap_geplant(monkeypatch):
    from tools import rate_transitions as rt
    aufrufe = {}
    def fake_build(a, b, **kw):
        aufrufe.update(kw); return []
    monkeypatch.setattr(rt, "build_pair_candidates", fake_build)
    monkeypatch.setattr(rt, "lade_tracks_aus_cache", lambda c: [])
    monkeypatch.setattr(rt, "sammle_kandidaten", lambda t, tol: [{"track_a": _ns_track("a"), "track_b": _ns_track("b"),
                                                                  "merkmale": {n: 0.5 for n in rt.NEUE_FAKTOREN}}])
    args = SimpleNamespace(out=Path("."), cache=None, bpm_toleranz=2.0, nur_genre=None, anzahl=1, seed=1)
    monkeypatch.setattr(rt, "schreibe_csv", lambda *a, **k: None)
    rt.befehl_prepare_kandidaten(args)
    assert aufrufe.get("bass_swap_geplant") is True
```

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: Implementierung** in `pair_candidates.py`:

`_teil_bass(out_a, in_b, tol, flags, bass_swap_geplant)`: `if konflikt and not bass_swap_geplant: wert -= KICK_KONFLIKT_ABZUG`. `score_pair(..., bass_swap_geplant: bool = False)` reicht durch; Docstring: "bass_swap_geplant: der Aufrufer rendert/plant einen Bass-/EQ-Swap — der Kick-Konflikt ist damit geloest, der Abzug entfaellt; das Flag bleibt gesetzt."

`_sortschluessel(p, rang_map)` nimmt ein Mapping Schema → Rang (Default `SCHEMA_RANG`); **`_hauptschema(cand, rang_map)` nutzt dieselbe Map** (Waechter Tor 1, Auflage 9 — sonst bestimmt die Hauptschema-Wahl nach alter, die Sortierung nach neuer Rangfolge); `dedupe_and_cap(paare, grid_a, grid_b, schemata_vorhanden, rang_map=SCHEMA_RANG)`. `build_pair_candidates(..., bass_swap_geplant: bool = False, schema_rang: list[str] | None = None)`: `rang_map = {s: i for i, s in enumerate(schema_rang)} if schema_rang else SCHEMA_RANG`, unbekannte Schemata hinten (`len(rang_map)`).

```python
def rank_pair_candidates(track_a: Track, track_b: Track, *, energy_direction=None,
                         harmonic_strictness: int = 7, allow_experimental: bool = True,
                         tolerances: dict | None = None, wahl: dict | None = None) -> list[PairCandidate]:
    """Kandidaten des Paars in App-Reihenfolge: gespeicherte Wahl (oder
    `wahl`) nach vorn, sonst Score; Tiebreak schema_rang aus dem Hoertest
    (candidate_preferences), sonst SCHEMA_PRIORITAET. Flag
    `gespeicherte_wahl` auf jedem Kandidaten. bass_swap_geplant=True (App)."""
    from . import candidate_choices
    genre_a = _genre(track_a)
    paare = build_pair_candidates(
        track_a, track_b, energy_direction=energy_direction, harmonic_strictness=harmonic_strictness,
        allow_experimental=allow_experimental, tolerances=tolerances, bass_swap_geplant=True,
        schema_rang=candidate_preferences.schema_rangfolge(genre_a) or None)
    if not paare:
        return []
    w = wahl if wahl is not None else candidate_choices.hole(track_a.filePath, track_b.filePath)
    treffer = None
    if w:
        for p in paare:
            if (abs(p.t_out - float(w.get("t_out", -1))) <= QUANTIZE_TOLERANCE_SEC
                    and abs(p.t_in - float(w.get("t_in", -1))) <= QUANTIZE_TOLERANCE_SEC
                    and int(p.blend_bars) == int(w.get("blend_bars", -1))):
                treffer = p
                break
    for p in paare:
        p.flags["gespeicherte_wahl"] = p is treffer
    if treffer is not None:
        paare = [treffer] + [p for p in paare if p is not treffer]
    for rang, p in enumerate(paare, start=1):
        p.rang = rang
    return paare


def select_pair_candidate(track_a: Track, track_b: Track, **kw) -> PairCandidate | None:
    """Rang 1 aus rank_pair_candidates oder None."""
    paare = rank_pair_candidates(track_a, track_b, **kw)
    return paare[0] if paare else None
```

`tools/rate_transitions.py befehl_prepare_kandidaten`: `pcs = build_pair_candidates(a, b, bass_swap_geplant=True)`.

- [ ] **Step 4: Run → PASS** (`tests/test_pair_candidates.py`, `tests/test_rate_transitions.py`, `tests/test_tools_paar_kandidaten_messen.py`)
- [ ] **Step 5: Commit** `git add hpg_core/pair_candidates.py tools/rate_transitions.py tests/test_pair_candidates.py tests/test_rate_transitions.py && git commit -m "feat(paare): bass_swap_geplant, schema_rang-Tiebreak, rank/select_pair_candidate mit gespeicherter Wahl"`

---

### Task 3: Scoring mit Kandidaten (`playlist.calculate_enhanced_compatibility`)

**Files:** Modify `hpg_core/playlist.py`; Test `tests/test_playlist_kandidaten.py` (neu, 4 Leerzeichen)

- [ ] **Step 1: Failing tests**

```python
"""Tests: Kandidaten im Playlist-Scoring und in den Empfehlungen (Spec Abschnitt 4)."""
import pytest

from hpg_core import playlist as pl
from hpg_core.mix_candidates import MixCandidate
from hpg_core.models import Track


def _sections(duration=300.0, intro_end=60.0, outro_start=240.0):
    return [
        {"label": "intro", "start_time": 0.0, "end_time": intro_end, "avg_energy": 30},
        {"label": "main", "start_time": intro_end, "end_time": outro_start, "avg_energy": 70},
        {"label": "outro", "start_time": outro_start, "end_time": duration, "avg_energy": 30},
    ]


def _voll(t, **kw):
    c = MixCandidate(t=t, schema=["pssi_phrase"], section_label="main", phrase_label="Chorus",
                     neuheit=0.6, traegt_allein=True,
                     groove_pattern_lokal=[0.25 if s % 4 == 0 else 0.0 for s in range(16)],
                     bass_pattern_lokal=[0.25 if s % 4 == 0 else 0.0 for s in range(16)],
                     syncopation_lokal=0.2, percussive_ratio_lokal=0.5, sub_energy=0.5, bass_punch=2.0,
                     bass_rms_dbfs=-20.0, kick_aktiv=False, camelot_lokal="8A", key_confidence_lokal=0.9,
                     timbre_fingerprint_lokal=[1.0, 0.5, 0.2], brightness_lokal=50, flatness_lokal=0.1,
                     avg_mids_lokal=40.0, avg_highs_lokal=20.0, energy_lokal=70, energy_trend="rising",
                     lufs_lokal=-10.0, mood={"pssi_mood": 1, "brightness": 50, "flatness": 0.1, "key_mode": "Minor"},
                     vocal_aktiv_lokal=False)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _track(name, bpm=140.0, camelot="8A", outs=(), ins=()):
    g = (60.0 / bpm) * 4 * 16
    t = Track(filePath=name, fileName=name)
    t.bpm = bpm; t.duration = 300.0; t.detected_genre = "Psytrance"; t.phrase_unit = 16
    t.first_downbeat = 0.0; t.downbeat_confidence = 1.0; t.sections = _sections(); t.outro_covered = True
    t.camelotCode = camelot; t.keyNote = "A"; t.keyMode = "Minor"; t.energy = 70
    t.mix_in_point = round(3 * g, 3); t.mix_out_point = round(6 * g, 3)
    t.mix_out_candidates = [c.to_dict() for c in outs]
    t.mix_in_candidates = [c.to_dict() for c in ins]
    return t


def test_enhanced_compatibility_nutzt_kandidat_wenn_vorhanden():
    g = (60.0 / 140.0) * 4 * 16
    a = _track("a.mp3", outs=[_voll(round(5 * g, 3))])
    b = _track("b.mp3", ins=[_voll(round(3 * g, 3))])
    m = pl.calculate_enhanced_compatibility(a, b, 2.0)
    assert m.kandidat is not None and m.kandidat["rang"] == 1
    assert m.loudness_match == pytest.approx(1.0) and m.structure_match is not None
    assert m.groove_match == pytest.approx(m.kandidat["teilwerte"]["groove"])
    assert m.overall_score == pytest.approx(min(1.0, m.kandidat["score"] + m.ai_bonus))


def test_enhanced_compatibility_ohne_kandidaten_wie_bisher():
    a, b = _track("a.mp3"), _track("b.mp3")
    m = pl.calculate_enhanced_compatibility(a, b, 2.0)
    assert m.kandidat is None and m.loudness_match is None and m.structure_match is None


def test_bpm_hard_gate_bleibt_auch_mit_kandidat():
    g = (60.0 / 140.0) * 4 * 16
    a = _track("a.mp3", outs=[_voll(round(5 * g, 3))])
    b = _track("b.mp3", bpm=143.0, ins=[_voll(round(3 * (60.0 / 143.0) * 64, 3))])
    assert pl.calculate_enhanced_compatibility(a, b, 2.0).overall_score == 0.0


def test_recommendations_tragen_kandidaten_und_plan_aus_rang_1():
    g = (60.0 / 140.0) * 4 * 16
    a = _track("a.mp3", outs=[_voll(round(5 * g, 3)), _voll(round(6 * g, 3), schema=["sektion"])])
    b = _track("b.mp3", ins=[_voll(round(3 * g, 3))])
    recs = pl.compute_transition_recommendations([a, b], bpm_tolerance=2.0)
    r = recs[0]
    assert r.kandidaten and r.kandidat_aktiv == 1
    k1 = r.kandidaten[0]
    assert r.plan.mix_out_a == pytest.approx(k1["t_out"]) and r.plan.mix_in_b == pytest.approx(k1["t_in"])
    assert r.plan.overlap == pytest.approx(min(k1["overlap_sec"], 64.0))
    assert r.fade_out_end == pytest.approx(min(r.plan.mix_out_a + r.plan.overlap, 300.0))


def test_bass_swap_pflicht_waehlt_bass_swap():
    g = (60.0 / 140.0) * 4 * 16
    a = _track("a.mp3", outs=[_voll(round(5 * g, 3), kick_aktiv=True)])
    b = _track("b.mp3", ins=[_voll(round(3 * g, 3), kick_aktiv=True)])
    r = pl.compute_transition_recommendations([a, b], bpm_tolerance=2.0)[0]
    assert r.kandidaten[0]["flags"]["bass_swap_pflicht"] is True
    assert r.transition_type == "bass_swap" and r.plan.transition_type == "bass_swap"
```

- [ ] **Step 2: Run → FAIL** (`AttributeError: kandidat`)

- [ ] **Step 3: Implementierung**

`TransitionMetrics` (+ nach `mood_match`): `loudness_match: Optional[float] = None`, `structure_match: Optional[float] = None`, `kandidat: Optional[dict] = None`.

Modul-Global `_PAIR_CANDIDATE_CACHE = None` neben `_ENHANCED_COMPAT_CACHE` (in `generate_playlist`/`benchmark` genauso an-/abgeschaltet wie die anderen; Key `(_track_cache_key(a), _track_cache_key(b), repr(energy_direction), repr(sorted(kwargs.items())))`). Helfer:

```python
def _kandidaten_fuer_paar(track1, track2, energy_direction, kwargs) -> list:
    """rank_pair_candidates mit demselben Cache-Verhalten wie die Metriken."""
    from .pair_candidates import rank_pair_candidates
    if not (getattr(track1, "mix_out_candidates", None) and getattr(track2, "mix_in_candidates", None)):
        return []
    key = (_track_cache_key(track1), _track_cache_key(track2), repr(energy_direction),
           repr(sorted((k, repr(v)) for k, v in kwargs.items())))
    if _PAIR_CANDIDATE_CACHE is not None and key in _PAIR_CANDIDATE_CACHE:
        return _PAIR_CANDIDATE_CACHE[key]
    paare = rank_pair_candidates(
        track1, track2, energy_direction=energy_direction,
        harmonic_strictness=kwargs.get("harmonic_strictness", 7),
        allow_experimental=kwargs.get("allow_experimental", True))
    if _PAIR_CANDIDATE_CACHE is not None:
        _PAIR_CANDIDATE_CACHE[key] = paare
    return paare
```

In `calculate_enhanced_compatibility` nach der Energie-/Genre-Berechnung und **vor** `if TRANSITION_FEATURES_ENABLED:`:

```python
    kandidat = None
    loudness_val = structure_val = None
    if TRANSITION_FEATURES_ENABLED:
        paare = _kandidaten_fuer_paar(track1, track2, energy_direction, kwargs)
        if paare:
            kandidat = paare[0]
    if kandidat is not None:
        # Spec Abschnitt 4: der beste PairCandidate traegt den Paar-Score —
        # alle Faktoren lokal an der Naht (Teil 2), Half/Double und Vocal-Clash
        # stecken bereits darin.
        tw = kandidat.teilwerte
        groove_val, bass_val, timbre_val, mood_val = tw.get("groove"), tw.get("bass"), tw.get("timbre"), tw.get("mood")
        loudness_val, structure_val = tw.get("loudness"), tw.get("structure")
        overall_score = float(kandidat.score)
    elif TRANSITION_FEATURES_ENABLED:
        ... (heutiger Block unveraendert)
    else:
        ... (Altpfad unveraendert)
```
Danach wie heute `ai_bonus`, Vocal-Clash (nur im Nicht-Kandidaten-Pfad — im Kandidaten-Pfad steckt `VOCAL_CLASH_PENALTY` schon in `score_pair`; also `if kandidat is None and ...`), BPM-Hard-Gate. `TransitionMetrics(..., loudness_match=loudness_val, structure_match=structure_val, kandidat=kandidat.to_dict() if kandidat else None)`. `_enhanced_cache_key` unveraendert.

`TransitionRecommendation` (+): `kandidaten: list = field(default_factory=list)`, `kandidat_aktiv: int = 0` (Rang, 0 = keiner). In `compute_transition_recommendations` nach dem DJ-Brain-Block (vor `_clamp_transition_overlap`):

```python
        kandidaten = _kandidaten_fuer_paar(current, upcoming, None, ctx) if metrics.kandidat is not None else []
        kandidat_aktiv = 0
        if kandidaten:
            aktiv = kandidaten[0]
            kandidat_aktiv = aktiv.rang
            current_mix_out = float(aktiv.t_out)
            next_mix_in = float(aktiv.t_in)
            fade_in_start = next_mix_in
            overlap = float(aktiv.overlap_sec)
            if dj_rec is not None:
                dj_rec.adjusted_mix_out_a = current_mix_out
                dj_rec.adjusted_mix_in_b = next_mix_in
```
(dj_rec-Sentinel-Felder werden mitgezogen, damit `resolve_transition_mix_points`-Leser ohne Plan dieselben Werte sehen.) `_clamp_transition_overlap` laeuft danach wie heute (Deckel 64 s, Fenster); `transition_type = "bass_swap" if (kandidaten and kandidaten[0].flags.get("bass_swap_pflicht")) else predict_transition_type(...)`. `TransitionRecommendation(..., kandidaten=[p.to_dict() for p in kandidaten], kandidat_aktiv=kandidat_aktiv)`. **Hinweis:** `metrics.kandidat` ist im Kandidatenpfad gesetzt, deshalb die Abfrage ueber `metrics` (vermeidet doppeltes Rechnen, wenn `transition_metrics` schon uebergeben wurden); die Liste selbst kommt aus dem Cache/`rank_pair_candidates` mit `energy_direction=None` wie die Empfehlungen heute.

- [ ] **Step 4: Run → PASS**; dazu `tests/test_compatibility.py tests/test_scoring_contract.py tests/test_playlist_quality.py tests/test_playlist_strategies.py` gruen (Tracks ohne Kandidaten → alter Pfad).
- [ ] **Step 5: Commit** `git add hpg_core/playlist.py tests/test_playlist_kandidaten.py && git commit -m "feat(scoring): bester PairCandidate traegt Paar-Score, Plan aus Rang 1, bass_swap bei Pflicht"`

---

### Task 4: Toleranzen: `write_override_kandidaten`

**Files:** Modify `hpg_core/tolerances.py`; Test `tests/test_tolerances.py` (2 Leerzeichen)

- [ ] **Step 1: Failing test**

```python
def test_write_override_kandidaten_haelt_summe_eins(tmp_path, monkeypatch):
  monkeypatch.setenv("HPG_TOLERANCES_FILE", str(tmp_path / "tol.json"))
  reset_cache()
  write_override_kandidaten({"kandidaten_loudness_weight": 0.20})
  reset_cache()
  w = get_tolerances("Psytrance")
  keys = [k for k in w if k.startswith("kandidaten_") and k.endswith("_weight")]
  assert w["kandidaten_loudness_weight"] == pytest.approx(0.20)
  assert sum(w[k] for k in keys) == pytest.approx(1.0)
  assert w["groove_weight"] == pytest.approx(0.300)          # Track-Gewichte unberuehrt
  with pytest.raises(ValueError):
    write_override_kandidaten({"kandidaten_loudness_weight": 1.2})
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3:**

```python
KANDIDATEN_GEWICHT_SCHLUESSEL = tuple(
    f"kandidaten_{f}_weight" for f in ("harmonic", "bpm", "energy", "genre", "groove", "bass", "timbre", "mood", "loudness", "structure"))


def write_override_kandidaten(gewichte: dict[str, float]) -> None:
    """Schreibt die uebergebenen kandidaten_*_weight fuer alle Genres in die
    Override-Datei und skaliert die uebrigen Kandidaten-Gewichte proportional
    auf den Rest (Summe 1.0). Die acht Track-Gewichte bleiben unberuehrt —
    sie leben in derselben Datei unter anderen Schluesseln."""
    unbekannt = [k for k in gewichte if k not in KANDIDATEN_GEWICHT_SCHLUESSEL]
    if unbekannt:
        raise ValueError(f"Unbekannte Kandidaten-Gewichte: {unbekannt}")
    neu_summe = sum(float(v) for v in gewichte.values())
    if neu_summe < 0.0 or neu_summe >= 1.0:
        raise ValueError(f"Kandidaten-Gewichte summieren auf {neu_summe}, muss in [0, 1) liegen")
    basis = get_tolerances(CANONICAL_GENRES[0])
    rest_keys = [k for k in KANDIDATEN_GEWICHT_SCHLUESSEL if k not in gewichte]
    rest_summe = sum(float(basis.get(k, 0.0)) for k in rest_keys) or 1.0
    pfad = _override_pfad()
    daten = {}
    if pfad.is_file():
        try:
            daten = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            daten = {}
    for genre in CANONICAL_GENRES:
        eintrag = dict(daten.get(genre, {}))
        eintrag.update({k: float(v) for k, v in gewichte.items()})
        for k in rest_keys:
            eintrag[k] = float(basis.get(k, 0.0)) / rest_summe * (1.0 - neu_summe)
        daten[genre] = eintrag
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, indent=2), encoding="utf-8")
```
(`write_override` bleibt unveraendert; es liest/schreibt die Datei komplett neu — deshalb liest `write_override_kandidaten` die vorhandene Datei ein und ergaenzt, damit beide Regler-Gruppen koexistieren. **Auch `write_override` muss vorhandene `kandidaten_*`-Schluessel erhalten**: dort `daten = {genre: {**vorhanden.get(genre, {}), **eintrag}}` — kleine Anpassung mit Test, dass ein zuvor geschriebenes `kandidaten_loudness_weight` nach `write_override({...})` erhalten bleibt.)

- [ ] **Step 4: Run → PASS** (`tests/test_tolerances.py`)
- [ ] **Step 5: Commit** `git add hpg_core/tolerances.py tests/test_tolerances.py && git commit -m "feat(tolerances): write_override_kandidaten (Summe 1.0 ueber zehn), write_override erhaelt Kandidaten-Schluessel"`

---

### Task 5: Exporter — Rang 1 + Memory-Cues `HPG K<n>`

**Files:** Modify `hpg_core/exporters/rekordbox_xml_exporter.py`; Test `tests/test_rekordbox_xml_exporter.py` (2 Leerzeichen)

- [ ] **Step 1: Failing test** (Muster der bestehenden Tests mit `patch`/Fake-`rb_track` uebernehmen; Kern:)

```python
def test_export_mit_transitions_schreibt_rang1_und_hpg_k_cues(tmp_path):
  from types import SimpleNamespace
  from hpg_core.exporters.rekordbox_xml_exporter import RekordboxXMLExporter
  a = make_track(filePath=str(tmp_path / "a.mp3"), duration=300.0, mix_in_point=60.0, mix_out_point=200.0, outro_covered=True)
  b = make_track(filePath=str(tmp_path / "b.mp3"), duration=300.0, mix_in_point=50.0, mix_out_point=210.0, outro_covered=True)
  plan = SimpleNamespace(mix_out_a=192.0, mix_in_b=82.3, overlap=27.4)
  kand = [{"rang": 1, "t_out": 192.0, "t_in": 82.3, "blend_bars": 16, "out_a": {"schema": ["pssi_phrase"]}, "in_b": {"schema": ["auto_cue"]}},
          {"rang": 2, "t_out": 164.6, "t_in": 82.3, "blend_bars": 16, "out_a": {"schema": ["sektion"]}, "in_b": {"schema": ["auto_cue"]}}]
  rec = SimpleNamespace(plan=plan, kandidaten=kand, kandidat_aktiv=1)
  marks = []
  class FakeRb:
    def add_mark(self, **kw): marks.append(kw)
  exp = RekordboxXMLExporter()
  n, err = exp._add_cue_points(None, FakeRb(), a, mix_out=plan.mix_out_a, extra=exp._kandidaten_cues_out(rec))
  namen = [(m["Name"], round(m["Start"], 1), m["Num"]) for m in marks]
  assert ("MIX OUT", 192.0, 1) in namen and ("HPG K1 OUT pssi_phrase", 192.0, -1) in namen
  assert ("HPG K2 OUT sektion", 164.6, -1) in namen and not err
  marks.clear()
  exp._add_cue_points(None, FakeRb(), b, mix_in=plan.mix_in_b, extra=exp._kandidaten_cues_in(rec))
  namen = [(m["Name"], round(m["Start"], 1), m["Num"]) for m in marks]
  assert ("MIX IN", 82.3, 0) in namen and ("HPG K1 IN auto_cue", 82.3, -1) in namen
  # gleiche t_in bei Rang 2 -> nur einmal als Memory-Cue
  assert sum(1 for n_, s, num in namen if n_.startswith("HPG K") and s == 82.3) == 1


def test_export_ohne_outro_covered_schreibt_keine_hpg_cues(tmp_path):
  ... (Track mit outro_covered=False -> `_add_cue_points` liefert 0 und die Meldung wie heute)
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3:** `export(self, playlist, output_path, playlist_name="HPG Playlist", transitions=None)`: `rec_nach = {id(transitions[i].from_track): transitions[i] for i}`/`rec_vor = {id(transitions[i].to_track): ...}` (Zuordnung ueber Index in `unique_tracks`: Tracks der Playlist-Reihenfolge; Duplikate wurden entfernt → Zuordnung ueber die Position im `playlist`-Original, `transitions[i]` gehoert zu `playlist[i]`→`playlist[i+1]`). `_add_track_to_collection(xml, track, idx, mix_in=None, mix_out=None, extra=())` reicht an `_add_cue_points(xml, rb_track, track, mix_in=None, mix_out=None, extra=())`: `mix_in`/`mix_out` ueberschreiben die Track-Werte fuer MIX IN/OUT (Gate `_cue_export_allowed(track, mix_in, mix_out)` prueft die effektiven Werte), `extra` = Liste `(name, start)` Memory-Cues (Num=-1). Helfer `_kandidaten_cues_out(rec) -> list[tuple[str, float]]` (je Kandidat `f"HPG K{rang} OUT {schema_out}"`, `t_out`; gleiche Startzeit nur einmal, erster Rang gewinnt) und `_kandidaten_cues_in(rec)` analog mit `IN`/`t_in`. `main._export_rekordbox_xml`: `exporter.export(self.playlist, file_path, playlist_name, transitions=self.playlist_panel.transition_recommendations)`.
- [ ] **Step 4: Run → PASS** (`tests/test_rekordbox_xml_exporter.py`, `tests/test_exporters.py`)
- [ ] **Step 5: Commit** `git add hpg_core/exporters/rekordbox_xml_exporter.py tests/test_rekordbox_xml_exporter.py && git commit -m "feat(export): Rekordbox-XML schreibt Rang-1-Mixpunkte und HPG K1..K6 Memory-Cues"`

---

### Task 6: `main.py` — Kandidatentabelle, Wahl, gemeinsamer Verteilpfad, Tabelle Mix-In/Out

**Files:** Modify `main.py`; Test `tests/test_main_workers.py` (2 Leerzeichen; GUI-frei ueber Funktionen/`SimpleNamespace`), `tests/test_gui_display.py` (falls Kandidatentabelle mit `qtbot` pruefbar)

- [ ] **Step 1: Failing tests** (GUI-frei, reine Helfer, die Task 6 in `main.py` anlegt):

```python
def test_kandidaten_teilwerte_kurzform():
  from main import kandidat_teilwerte_kurz
  txt = kandidat_teilwerte_kurz({"harmonic": 0.75, "bpm": 1.0, "energy": 0.98, "genre": 1.0, "groove": 0.83,
                                 "bass": 0.6, "timbre": 0.72, "mood": 0.99, "loudness": None, "structure": 0.07})
  assert txt == "H .75 T 1.0 E .98 G 1.0 Gr .83 B .60 K .72 S .99 L - St .07"


def test_mixpunkt_quelle_aus_empfehlungen():
  from types import SimpleNamespace
  from main import mixpunkte_fuer_tabelle
  recs = [SimpleNamespace(plan=SimpleNamespace(mix_out_a=192.0, mix_in_b=82.3), kandidat_aktiv=1)]
  t0 = SimpleNamespace(mix_in_point=60.0, mix_out_point=200.0)
  t1 = SimpleNamespace(mix_in_point=50.0, mix_out_point=210.0)
  assert mixpunkte_fuer_tabelle(0, t0, recs) == (60.0, "Analyse", 192.0, "Kandidat Rang 1")
  assert mixpunkte_fuer_tabelle(1, t1, recs) == (82.3, "Kandidat Rang 1", 210.0, "Analyse")
  assert mixpunkte_fuer_tabelle(1, t1, []) == (50.0, "Analyse", 210.0, "Analyse")
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implementierung in `main.py`** (4 Leerzeichen):
  - Modulfunktionen `kandidat_teilwerte_kurz(teilwerte: dict) -> str` (Reihenfolge `pair_candidates.FAKTOREN`, Kuerzel H/T/E/G/Gr/B/K/S/L/St, `".75"`-Format, `1.0`, None → `-`) und `mixpunkte_fuer_tabelle(index, track, recs) -> (mix_in, quelle_in, mix_out, quelle_out)` (Empfehlung `recs[index-1].plan.mix_in_b` bzw. `recs[index].plan.mix_out_a`, wenn `kandidat_aktiv > 0`, sonst Track-Wert; Quelle "Kandidat Rang n"/"Analyse").
  - `MixTipsPanel`: Signal `candidate_chosen = pyqtSignal(int, int)`; in `_populate` nach dem Timing-Label, wenn `getattr(rec, "kandidaten", [])`: `QTableWidget(len(kandidaten), 7)` mit Spalten `["Rang", "Mix-Out A", "Mix-In B", "Blende", "Schema", "Score", "Teilwerte"]`, Zeilen-Tooltip = `begruendung`, Zeile `rang == kandidat_aktiv` selektiert, `setSelectionBehavior(SelectRows)`, `setEditTriggers(NoEditTriggers)`, Hoehe auf Zeilen begrenzt (`min(6, n)` sichtbar), `itemSelectionChanged` → `self.candidate_chosen.emit(card_index, rang)` nur bei Benutzeraktion (Guard-Flag `_tabelle_fuellt`). Stil ueber `COLORS`, `FONT_FAMILY`, `FONT_SIZE` aus `hpg_core/theme.py` (:29-40; ein `FONTS` gibt es dort nicht) wie die Karten (keine neuen Hex-Werte).
  - `MixTipsPanel.verwerfe_preview(index)`: entfernt `index` aus `_preview_cache` (Datei loeschen ueber `_remove_preview_path`), setzt den Knopf zurueck.
  - `MainWindow._berechne_uebergaenge(bpm_tolerance, scoring_context) -> (transition_metrics, quality_metrics, transition_plan)`: genau die drei Aufrufe aus `analysis_finished` (:4820-4829: `compute_adjacent_transition_metrics`, `calculate_playlist_quality`, `compute_transition_recommendations`), setzt `self.quality_metrics`, `playlist_panel.quality_metrics/transition_recommendations`. `MainWindow._verteile_uebergaenge(transition_plan)`: Verteilung wie :4842-4855 (`playlist_panel.set_playlist_data(... transition_recommendations=transition_plan ...)`, `mix_tips_panel.set_recommendations` + `setup_transition_previews`, `timeline_panel.set_timeline`, `analytics_panel.set_analytics`, Toolbar-Quality). `analysis_finished` ruft beide (Verhalten unveraendert); `_on_playlist_reordered` (:5008-5030) bleibt unveraendert.
  - `MainWindow._on_candidate_chosen(index, rang)`: `rec = self.playlist_panel.transition_recommendations[index]`; `k = next(d for d in rec.kandidaten if d["rang"] == rang)`; `candidate_choices.merke(rec.from_track.filePath, rec.to_track.filePath, t_out=k["t_out"], t_in=k["t_in"], blend_bars=k["blend_bars"])` (leert den Paar-Cache); `mix_tips_panel.verwerfe_preview(index)`; `_, _, plan = self._berechne_uebergaenge(self.current_bpm_tolerance, self.current_scoring_context)`; `self._verteile_uebergaenge(plan)`; Status "Kandidat Rang n fuer Uebergang i→i+1 gewaehlt — Preview, Timeline und Export folgen." Verbindung `self.mix_tips_panel.candidate_chosen.connect(self._on_candidate_chosen)` im Aufbau.
  - `PlaylistPanel._populate_table` **und** `MainWindow.on_ai_finished` (:4723-4730): Mix-In/Out-Spalten ueber `mixpunkte_fuer_tabelle(i, track, recs)`; Tooltip Quelle; Bars-Anzeige ueber `seconds_to_bars(sekunden, track.bpm)` (vorhanden in `models`) — `mix_in_bars`/`mix_out_bars` nur als Fallback.
- [ ] **Step 4: Run → PASS** (`tests/test_main_workers.py`, `tests/test_run_lifecycle.py`, `tests/test_gui_display.py`, `tests/test_transition_weight_ui.py`)
- [ ] **Step 5: Commit** `git add main.py tests/test_main_workers.py && git commit -m "feat(gui): Kandidatentabelle im Uebergangs-Panel, Wahl je Paar, Rang 1 in Tabelle/Preview/Timeline/Export"`

---

### Task 7: `main.py` — Regler "Lautheit", BPM-Default 2.0, Export mit Empfehlungen

**Files:** Modify `main.py`; Tests `tests/test_transition_weight_ui.py` (2), `tests/test_main_workers.py`/`tests/test_run_lifecycle.py` (BPM-Default)

- [ ] **Step 1: Failing tests**
```python
# tests/test_transition_weight_ui.py — anhaengen (qtbot-Muster der Datei)
def test_lautheit_regler_schreibt_kandidaten_gewicht(qtbot, monkeypatch, tmp_path):
  ... Widget bauen wie in den bestehenden Tests; Slider "kandidaten_loudness_weight" existiert;
  ... setValue(20) + sliderReleased -> get_tolerances("Psytrance")["kandidaten_loudness_weight"] == 0.20,
  ... Summe der zehn == 1.0, "groove_weight" unveraendert 0.30.
```
```python
# tests/test_run_lifecycle.py — anhaengen (qtbot, MainWindow wie :64-66)
def test_app_bpm_default_ist_zwei(qtbot, monkeypatch):
  ... MainWindow() -> window.library_panel.bpm_tolerance_slider.value() == 2 und window.current_bpm_tolerance == 2.0
```
- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3:** Regler-Liste :1562-1567 um `("kandidaten_loudness_weight", "Lautheit (Kandidaten)", 6)` ergaenzen; `_on_transition_weight_changed`: Schluessel mit Praefix `kandidaten_` an `write_override_kandidaten`, die uebrigen an `write_override` (beide aufrufen, Fehler je Gruppe melden); Statuszeile ergaenzt "Hoertest-Praeferenz aktiv fuer: <Genres>" aus `candidate_preferences.load_candidate_preferences()` (nur Genres mit Gewichten); `_lade_transition_regler` liest generisch (funktioniert schon). BPM: :2708 `setValue(2)`, :2710-2713 Tooltip "±2 BPM (Gate des Hoertests); Half/Double wird erkannt", :2714 "±2", :508 `bpm_tolerance=2.0`, :2933 `2.0`, :3081 `2.0`, :4299 `2.0`. Export: `_export_rekordbox_xml` uebergibt `transitions=self.playlist_panel.transition_recommendations`. Bestandstests, die 3 erwarten (grep `bpm_tolerance_slider.value() == 3|current_bpm_tolerance == 3`), auf 2 umstellen — Liste im Handoff.
- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** `git add main.py tests/ && git commit -m "feat(gui): Regler Lautheit (Kandidaten), App-BPM-Default 2.0, XML-Export mit Empfehlungen"`

---

### Task 8: Werkzeug `tools/playlist_kandidaten_messen.py`

**Files:** Create `tools/playlist_kandidaten_messen.py`; Test `tests/test_tools_playlist_kandidaten_messen.py` (4)

- [ ] **Step 1: Failing test** (reine `zusammenfassung(recs, tracks, dauer)`: zaehlt Paare, Paare mit Kandidat, Rang-1-Schemata, `bass_swap`-Anteil, Verletzungen = Plan-Punkte vor `intro_end` von B bzw. Blende ueber `outro_start` von A (Toleranz `QUANTIZE_TOLERANCE_SEC`, benannte Cues ausgenommen), **`overlap_abweichungen` = Paare, deren `plan.overlap` von der Kandidaten-Blende `overlap_sec` abweicht (Clamp nach Kandidat, Ziel 0 — Waechter Tor 1 Auflage 8)**, **`cue_gate_verletzungen` = Tracks, deren Kandidaten-Mix-In (Paar i−1) nicht vor dem Kandidaten-Mix-Out (Paar i) liegt (Export-Gate wuerde die Cues still weglassen)**, Median Score).
- [ ] **Step 2–3:** Werkzeug: `--cache`, `--strategie` (Default "Harmonic Flow"), `--bpm` (Default 2.0), `--json`; laedt Tracks (`caching.dict_to_track`), `t0`; `generate_playlist(tracks, mode=..., bpm_tolerance=...)`; `compute_adjacent_transition_metrics`, `compute_transition_recommendations`; `zusammenfassung`; druckt JSON (Dauer Generierung, Dauer Empfehlungen, Zahlen). Vergleich "ohne Kandidaten": gleicher Lauf mit `monkeypatch`-artigem Schalter `--ohne-kandidaten` (setzt `playlist._kandidaten_fuer_paar` auf `lambda *a, **k: []`) → Score-Median beider Laeufe.
- [ ] **Step 4–5:** PASS, Commit `tools: playlist_kandidaten_messen (App-Regression Kandidaten)`.

---

### Task 9: Doku, Messung, Waechter Tor 2, Merge

- [ ] **Step 1: Messung** `tools/playlist_kandidaten_messen.py --cache --strategie "Harmonic Flow" --bpm 2.0 --json <scratchpad>\app_v34.json` und `--ohne-kandidaten`: Dauer (Generierung, Empfehlungen), Paare mit Kandidat, Rang-1-Schemata, `bass_swap`-Anteil, **Verletzungen = 0**, Score-Median mit/ohne. Bei Generierung > 60 s fuer 231 Tracks: Zahl ins Handoff, keine stille Kappung.
- [ ] **Step 2: App-Start-Rauchtest** ohne Hoerprobe: `.\venv312\Scripts\python.exe -c "import main"`; `tests/test_run_lifecycle.py` gruen (MainWindow baut auf).
- [ ] **Step 3: Volle Suite** gruen inkl. Coverage-Gate.
- [ ] **Step 4: Doku**: `CLAUDE.md` (Baum: `candidate_choices.py`, `tools/playlist_kandidaten_messen.py`; Pipeline-Punkt 6 → "App: bester PairCandidate traegt Paar-Score und Plan"), `.agents/skills/hpg-playlist-scoring/SKILL.md` (+`.claude`: Kandidatenpfad in `calculate_enhanced_compatibility`, neue Metrik-Felder, `TransitionRecommendation.kandidaten`, sechster Konsument = Kandidatentabelle, BPM-Default 2.0), `.agents/skills/hpg-qt-gui/SKILL.md` (Kandidatentabelle, Signal, `_verteile_uebergaenge`), `.agents/skills/hpg-rekordbox/SKILL.md` (HPG K-Cues, `transitions`), `.agents/skills/hpg-mixpoint-engineering/SKILL.md` (Entscheidung 1: Plan traegt Rang 1, Track-Felder = Analyse), `.agents/skills/hpg-testing-verification/SKILL.md` + `docs/HANDOFF-2026-08-22-kandidaten-teil3.md` (Nachtrag: `prepare --modus kandidaten` scort seit Teil 4 mit `bass_swap_geplant=True`, d. h. ohne Kick-Abzug — Waechter Tor 1 Auflage 7); Handoff `docs/HANDOFF-<Datum>-kandidaten-teil4.md` mit Zahlen (inkl. Laufzeit je Paar 8,7 ms Median), den 14 Entscheidungen und den benannten Abweichungen vom Spec-Wortlaut (Entscheidungen 1, 7, Begruendung/Tooltips, Statuszeile, `write_override`), Hinweis Kandidaten-/Altpfad-Mischung bei Toleranz > 2 BPM, **Checkliste Hoerproben** (App-Preview der Rang-1-Kandidaten, Wahl-Klick, Export in Rekordbox pruefen).
- [ ] **Step 5: Waechter Tor 2**, Auflagen einarbeiten.
- [ ] **Step 6: Merge** auf `main` (finishing-a-development-branch, Option 1), Push, `.claude`-Spiegel.

---

## Self-Review (Spec Abschnitt 4 gegen Tasks)

| Spec-Punkt | Task |
|---|---|
| Analyse/Cache beide Pfade, CACHE_VERSION 34 | Teil 1 (gebaut) |
| `calculate_enhanced_compatibility` bekommt je Paar den besten `PairCandidate` | 3 |
| `Track.mix_in_point/mix_out_point` = Rang 1 | 3 + 6 + 5 (Entscheidung 1: Plan traegt Rang 1 fuer alle Leser) |
| `scoring_context` erweitert, fuenf Konsumenten sehen dasselbe | 3 (Entscheidung 7), 6 (`_verteile_uebergaenge`) |
| App-BPM-Default 3.0 → 2.0, Slider bleibt | 7 |
| GUI: Uebergangs-Panel mit Kandidatentabelle (Rang, t_out/t_in, Blende, Schema, Score + Teilwerte, Begruendung) | 6 |
| Klick = Kandidat aktiv → Preview, Timeline, Export folgen | 6 (Plan neu, Preview verworfen), 5 |
| Wahl pro Paar in `candidate_choices.json`, beim naechsten Lauf bevorzugt | 1, 2 |
| Faktoren-Regler um Lautheit erweitert | 4, 7 |
| Renderer unveraendert (`from_plan`) | — (Plan traegt Kandidaten-Zeitpunkte) |
| Export m3u8/XML Rang 1; XML Memory-Cues HPG K1..K6, nur `outro_covered` | 5, 7 |
| Tests RED→GREEN je Modul; `assert_mix_points_valid`/`assert_phrase_aligned` auf Kandidaten; Regressionsmessung 231 Tracks | alle Tasks; 8, 9 |
| Analysezeit gemessen | Teil 1 Handoff (42 s/Track); Generierungszeit Task 9 |
| Melodic-Techno-Gewichte offen bis Noten | Handoff |
| Lernen: Schema-Rangfolge je Genre (Teil 3) + Wahl pro Paar | 2 |
| `KICK_KONFLIKT_ABZUG` entfaellt bei Bass-Swap (Teil-2-Entscheidung 6) | 2 |

**Benannte Abweichungen vom Spec-Wortlaut (Waechter Tor 1):** Entscheidung 1 (Track-Felder nicht mutiert, Plan traegt Rang 1), Entscheidung 7 (Wahl in Datei statt im `scoring_context`), Entscheidung 9/10 (Quelle-Tooltips, Regler-Statuszeile, `write_override` erhaelt Kandidaten-Schluessel — Zugaben), Entscheidung 11 (`HPG K<n>` je Seite fortlaufend nach Dedupe, nicht `PairCandidate.rang`). Begruendung ist sichtbare Spalte (Spec-konform).

Placeholder-Scan: keine TBD/TODO; Task 6/7/8 nennen die Helfer und Signaturen, der GUI-Feincode (Qt-Aufbau) folgt den in `main.py` vorhandenen Mustern (Karten :3481ff, Regler :1549ff) und wird an Tor 2 gegen diese Vorgaben geprueft. Pflicht fuer Tor 2 (Waechter Tor 1 Auflage 11): mindestens ein `qtbot`-Test der Kandidatentabelle (Zeilenzahl, aktive Zeile, `candidate_chosen`-Signal) und ein Test fuer `_on_candidate_chosen` (`merke` gerufen, Preview verworfen, Panels neu) in `tests/test_gui_display.py` bzw. `tests/test_run_lifecycle.py`.
