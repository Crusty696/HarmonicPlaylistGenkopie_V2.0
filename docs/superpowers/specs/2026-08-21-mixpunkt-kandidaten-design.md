# Mixpunkt-Kandidaten — Design (2026-08-21)

Status: vom Nutzer abschnittsweise genehmigt (Abschnitte 1–4, 2026-08-21).
Auflage des Nutzers: **genau so umsetzen, alles fertig bauen bis zum letzten
Teil, nicht von den Anweisungen abweichen, 100 % ehrlich, keine Annahmen.**

## Anlass

1. Der Nutzer hoert in den Hoertest-Clips Mixpunkte, die musikalisch im
   Intro/Outro liegen, obwohl der Intro/Outro-Guard formal haelt (280 Paare,
   0 Verletzungen). Ursache: der Struktur-Analyzer schaetzt Intro/Outro zu
   kurz (Psytrance: Intro-Ende Median 28 s, Outro 22 s; real 2–4 Phrasen).
2. Nutzer-Regel: **Wo gemischt wird, ist pro Track individuell, pro Paar gibt
   es mehrere gute Moeglichkeiten. Keine Einheitsregel, Kandidaten anbieten.**
3. Rekordbox liefert bei den 77 analysierten Psy-Tracks je 6–11 Cues
   (Chorus/Drop-Starts) und
   PSSI-Phrasen (Intro/Up/Chorus/Down/Bridge/Verse/Outro) — HPG liest bisher
   nur das Beatgrid (PQTZ) und deutet Cues per Positionsheuristik.
4. Nutzer-Regel: **In Auswahl und Bewertung muss ausnahmslos alles gewichtet
   einfliessen** — Groove, Rhythmus, Harmonie, Lautheit, BPM (max. 2),
   Bassdruck, Bass-/Subbass-Rhythmus, Klangfarbe, Energie, Genre, Stimmung.

## Entscheidungen aus der Design-Runde

| Frage | Entscheidung |
|---|---|
| Wo wirken Kandidaten? | C: Hoertest **und** App |
| Quellen | B: Rekordbox-Cues + PSSI-Phrasen + HPG-Analyzer |
| Benennung | A+B: benannte Schemata, dazu Kontrast/Dedupe |
| Blendenlaenge | C: beide Genre-Blendenlaengen als eigene Kandidaten |
| Lernen | C: Genre-Rangfolge der Schemata lernen **und** Wahl pro Paar merken |
| Architektur | Weg 2: Kandidaten pro Track vorberechnen (Cache, CACHE_VERSION-Bump) |

Nicht gewaehlt (und nicht wieder vorschlagen): Fallback-Ketten, feste 3
Kandidaten, Kandidaten on-the-fly, Teilmengen der Faktoren.

---

## Abschnitt 1 — Datenmodell

### Pro Track (vorberechnet, Cache, CACHE_VERSION 33 → 34)

| Feld | Inhalt | Quelle |
|---|---|---|
| `phrases` | Liste (start_s, end_s, label ∈ Intro/Up/Chorus/Down/Bridge/Verse/Outro laut pyrekordbox-PSSI-Schema — in eigenen Daten bisher nur Intro/Up/Chorus/Down/Outro gesehen, mood) | Rekordbox PSSI aus `ANLZ0000.EXT` (neu; `pyrekordbox.anlz.AnlzFile`) |
| `phrase_grid` | Gitterpunkte aus PSSI-Phrasengrenzen; Fallback `phrase_anchor` + `phrase_unit` | PSSI vor Analyzer |
| `cue_points` | (t_s, name, typ, provenance ∈ manual/auto/leer) — Positionsheuristik "2. Cue = In, letzter = Out" **entfaellt** | Rekordbox |
| `mix_in_candidates` | 3–8 `MixCandidate` | s. u. |
| `mix_out_candidates` | 3–8 `MixCandidate` | s. u. |

`Track.mix_in_point` / `mix_out_point` bleiben bestehen und tragen Rang 1
(Kompatibilitaet zu allen Lesern, Invarianten 1–6 unveraendert).

### `MixCandidate` — ein Zeitpunkt plus lokale Messwerte (Fenster ±1 Phrase)

| Gruppe | Felder | Heute vorhanden |
|---|---|---|
| Position | `t` (Sekunden, auf Gitter), `schema` ∈ {benannter Cue, Auto-Cue, PSSI-Phrasengrenze, Sektionsgrenze, Energie-Neuheit}, `provenance`, `confidence` (aus `downbeat_confidence`, `phrase_confidence`, `key_confidence`, Coverage) | nur Sektion + Cue-Heuristik |
| Struktur | `section_label`, `phrase_label`, `neuheit` (Sprung in Rhythmusdichte/Lautheit/Timbre/Harmonie an t), `traegt_allein` (Kick + Bass nach t aktiv) | nur Label |
| Rhythmus | `groove_pattern_lokal`, `bass_pattern_lokal` (16 Slots), `syncopation_lokal`, `percussive_ratio_lokal` | nur trackweit |
| Bass | `sub_energy`, `bass_punch`, `bass_rms_dbfs` (absolut, ≤160 Hz), `kick_aktiv` | sub/punch je Sektion |
| Harmonie | `camelot_lokal` (Chroma ±1 Phrase), `key_confidence_lokal` | nur trackweit |
| Klangfarbe | `timbre_fingerprint_lokal` (MFCC), `brightness_lokal`, `flatness_lokal`, `avg_mids_lokal`, `avg_highs_lokal` | nur trackweit |
| Energie/Lautheit | `energy_lokal`, `energy_trend`, `lufs_lokal` (Short-Term, native Samplerate, Stereo) | nur Trackmittel |
| Stimmung | `mood` (brightness/flatness/Dur-Moll), PSSI-mood | trackweit |
| Vocals | `vocal_aktiv_lokal` | trackweit |

### Harte Gates (Kandidat wird nicht erzeugt)

- Intro/Outro-Guard fuer Punkt **und** Blende (Spec 2026-03-11 inkl. Erweiterung)
- `unanalysed` / fehlende Coverage; Mix-Out nur bei `outro_covered`
- auf Gitter, `QUANTIZE_TOLERANCE_SEC` 0.05
- `mix_out − mix_in ≥ 2 Phrasen`
- BPM-Paarfilter ≤ 2.0 (Half/Double bleibt erkannt: kurzer Cut ≤ 16 Bars, Penalty 0.85)
- Pitch-Bedarf ≤ 4 % (neues Design-Gate; heute nur `half_double_tolerance`
  im Renderer und DJ-Praxis-Notiz, kein Gate im Code)
- Ausnahme: benannter Cue (MIX IN / IN / START) schlaegt den Guard

### Ausdruecklich nicht enthalten (widerlegt, nicht wieder einbauen)

Blendenlaenge als Qualitaetsmerkmal (rho −0.08), Bassloch/Pegeleinbruch als
Ausschluss (haette 4 von 11 guten verworfen), "nie im Einbruch mischen"
(18,6 % vs. 17,0 % Zufall), Mitten-Mulde, Bandgain, Mix-Mining-Gewichte
(Holdout nie bestanden), Cue-Positionsheuristik als Wahrheit,
LLM-Mixpoints als Ground Truth.

---

## Abschnitt 2 — Paarung und Bewertung

Eingabe: Track A (`mix_out_candidates`), Track B (`mix_in_candidates`).
Ausgabe: Liste `PairCandidate(out_A, in_B, blend_bars, score, teilwerte,
begruendung)`, sortiert.

### Schritt 1 — harte Gates auf Paar-Ebene

- |BPM_A − BPM_B| ≤ 2.0 effektiv (Half/Double: kurzer Cut ≤ 16 Bars, Penalty 0.85)
- Pitch-Bedarf ≤ 4 %
- `out_A + overlap ≤ outro_start_A` und `in_B ≥ intro_end_B`
- Coverage: kein Kandidat in `unanalysed`, Mix-Out nur bei `outro_covered`
- beide auf Gitter (PSSI-Gitter bzw. Phrasen-Anker, 0.05 s Toleranz)

### Schritt 2 — Score je Kombination, alle Faktoren lokal an der Naht

| Faktor | Vergleich out_A ↔ in_B | Startgewicht | Heute |
|---|---|---|---|
| Harmonie | Camelot-Tabelle auf `camelot_lokal`, Gewicht × `key_confidence_lokal` | 0.16 | Tabelle vorhanden |
| BPM | exp(−diff/1.0) innerhalb des 2-BPM-Gates | 0.12 | vorhanden |
| Energie | Richtung UP/DOWN/MAINTAIN auf `energy_lokal`, `energy_trend` | 0.12 | vorhanden |
| Genre | `GENRE_COMPATIBILITY`, Unknown × 0.5 | 0.12 | vorhanden |
| Groove/Rhythmus | 0.6·cos(bass_pattern_lokal) + 0.4·cos(groove_pattern_lokal); `syncopation`-Delta; `percussive_ratio` beide > 0.7 → Abzug, < 0.3 → lange Blende erlaubt | 0.30 | trackweit vorhanden |
| Bassdruck + Bass/Subbass-Rhythmus | 0.6·sub_sim + 0.4·punch_sim; `bass_rms_dbfs`-Delta; **nie zwei Kicks**: `kick_aktiv` beidseitig im Blendfenster → Bass-Swap-Punkt Pflicht, sonst Abzug | 0.08 | teilweise |
| Klangfarbe | cos(timbre_lokal); `avg_mids`/`avg_highs`-Delta | 0.05 | trackweit |
| Stimmung | brightness/flatness, Dur/Moll −0.15, PSSI-mood gleich | 0.05 | vorhanden |
| **Lautheit (neu)** | abs(lufs_lokal_A − lufs_lokal_B): 0 dB → 1.0, ≥ 3 dB → 0 | neu | nur Text |
| Struktur (neu) | `neuheit`, `traegt_allein` von in_B; Label-Paar (z. B. Outro → Chorus-Start) | neu | — |
| Vocals | beide `vocal_aktiv_lokal` → −0.06 | additiv | vorhanden |

Gewichte: Startwerte, Summe 1.0, je Genre in `GENRE_TRANSITION_TOLERANCES`,
per JSON ueberschreibbar. **Keiner dieser Werte ist gemessen; der Hoertest
(Abschnitt 3) ersetzt sie.** Fehlender Wert → Umverteilung, nie 0.

### Schritt 3 — Blendenlaengen

Jede Kombination × 2: `transition_bars[0]` und `[1]` des Genres (Psytrance
16 und 32), beide durch den Outro-Deckel auf ganze Takte geklemmt. Eigene
`PairCandidate`s.

### Schritt 4 — Kontrast/Dedupe

Kandidaten mit |Δt| < 1 Phrase und gleichem Schema zusammenlegen (bester
Score bleibt, Schemata als Liste). Ausgabe max. 6 Zeitpunkt-Kombinationen
je Paar (× 2 Blendenlaengen = max. 12 `PairCandidate`s), mindestens ein
Kandidat je vorhandenem Schema.

### Schritt 5 — Ausgabe

Rang, Score, alle Teilwerte (App sichtbar, Hoertest verdeckt),
Begruendungstext aus den Teilwerten (kein freier Text).

---

## Abschnitt 3 — Hoertest (T3): Kandidaten vergleichen

Prinzip: dasselbe Trackpaar, mehrere Kandidaten → paarweiser Vergleich.
Tonart, BPM, Genre, Geschmack kuerzen sich heraus.

**Prepare** (`tools/rate_transitions.py prepare --modus kandidaten`):
Paare wie heute (BPM ≤ 2, overall ≥ 0.70, groove ≥ 0.5, Genre-Filter); je
Paar alle `PairCandidate`s (max. 6 × 2 Blendenlaengen), jeder als Clip mit
`pro_eq_swap`, 8 s Vorlauf / Blende / 8 s Nachlauf (wie heute,
`PRE_ROLL_SEK`/`POST_ROLL_SEK` in `tools/rate_transitions.py`), Pegelfix aktiv. Dateiname
`<pair_id>_k<n>.wav`. `merkmale.csv` je Clip: alle Teilwerte aus Abschnitt 2
+ `schema`, `blend_bars`, `t_out`, `t_in`, `provenance`, `confidence`.
Anzeige verdeckt: kein Score, kein Schema-Name; nur Tempo, Genre, Camelot,
Blendenbalken.

**Server** (`tools/hoertest_server.py`, Modus Kandidaten): pro Paar eine
Seite mit allen Kandidaten, Reihenfolge zufaellig (Seed je Paar gespeichert).
Zwei Eingaben: Note 1–5 je Kandidat und Wahl "bester" (ein Klick); beides
sofort in `bewertung.csv` (`pair_id, clip_id, note, gewaehlt, zeit`).

**Fit** (`rate_transitions.py fit --modus kandidaten`): Zielgroesse 1 Note
(logistisch, gut ≥ 4); Zielgroesse 2 Paarvergleich (Sieger gegen Verlierer,
Merkmals-Differenzen innerhalb des Paars, Bradley-Terry / konditionale
Logistik). Datenlage-Gate 10 Ereignisse je Merkmal und Klasse. Ergebnis:
Gewichte fuer Abschnitt 2 und Rangfolge der Schemata je Genre →
`hpg_core/data/candidate_preferences.json`. Holdout nach **Tracks**; Bericht
zeigt AUC/Trefferquote auf Holdout, sonst Werte nicht uebernehmen.

**Mobil**: gleicher Ordner-Mechanismus (Start.bat), neuer Modus automatisch.

Hoerzeit ist der Engpass: 12 Clips je Paar → weniger Paare je Satz, jedes
vollstaendig. Die bestehenden 280 Clips (Einzelnoten) bleiben Satz 1.

---

## Abschnitt 4 — App (T4)

**Analyse/Cache**: `analyze_track` berechnet Kandidaten in beiden Pfaden
(Rekordbox-Fast-Path + Voll-Pfad). PSSI-Phrasen + Cues im Rekordbox-Pfad;
Voll-Pfad ohne Rekordbox → nur Analyzer-Schemata. Serialisierung in
`caching.py`, CACHE_VERSION 34, Neuanalyse noetig.

**Playlist/Scoring**: `calculate_enhanced_compatibility` bekommt je Paar den
besten `PairCandidate`; `Track.mix_in_point/mix_out_point` = Rang 1.
`scoring_context` (HPG-001) um die Kandidaten-Wahl erweitert; alle fuenf
Konsumenten sehen dasselbe. App-BPM-Default 3.0 → **2.0** (Slider bleibt).

**GUI (main.py)**, nur das Noetige: Uebergangs-Panel mit Tabelle der
Kandidaten (Rang, t_out/t_in, Blende, Schema, Score + Teilwerte,
Begruendung); Klick = Kandidat aktiv → Preview, Timeline, Export folgen.
Wahl pro Paar gespeichert in `%LOCALAPPDATA%\HPG\candidate_choices.json`,
beim naechsten Lauf bevorzugt. Faktoren-Regler um Lautheit erweitert.

**Renderer**: unveraendert (`from_plan`), bekommt Zeitpunkte + Blende des
aktiven Kandidaten.

**Export**: m3u8 / Rekordbox-XML schreiben Rang 1; XML zusaetzlich alle
Kandidaten als Memory-Cues `HPG K1..K6` (Name mit Schema), nur bei
`outro_covered`.

**Tests**: je Modul RED → GREEN; `assert_mix_points_valid`,
`assert_phrase_aligned` auf alle Kandidaten; Regressionsmessung an den 231
analysierten Tracks (Intro/Outro-Verletzungen = 0, Kandidatenzahl,
Schemaverteilung) vor/nach.

**Offen, ehrlich**: Analysezeit je Track steigt (wird gemessen, nicht
geschaetzt). Melodic-Techno-Gewichte bleiben offen bis Noten vorliegen.

---

## Anhang A — Kriterien-Katalog (Quelle der Vollstaendigkeit)

Konsolidiert aus vier parallelen Suchen (Code, Repo-Docs/Archive, Vault,
Skills/Memory) am 2026-08-21. Status: S = im Score · G = Gate · T = nur Text ·
M = gemessen ohne Leser · D = nur Doku · N = Nutzer-Vorgabe · X = widerlegt.

**Im Score heute (S):** harmonic 0.16, bpm 0.12, energy 0.12, genre 0.12,
groove 0.30, bass 0.08, timbre 0.05, mood 0.05, KI-Bonus ≤ 0.14,
Vocal-Clash −0.06; Umverteilung bei None.

**Nutzer-Vorgaben (N):** alles gewichtet; BPM ≤ 2 (App-Default noch 3.0);
Lautheit als Faktor (heute nur Text: `GAIN_DIFF_WARN_DB` 3.0); Kandidaten
statt Einheitsregel; Cues + PSSI-Phrasen; kein DJ mischt im Intro/Outro;
beide Blendenlaengen; paarweiser A/B als Lernverfahren.

**Gemessen, ohne Score-Wirkung (M/T):** `lufs` (+status/coverage),
`key_confidence`, `percussive_ratio`/`rhythm_advice`, `syncopation`,
`danceability`, `avg_bass`/`avg_mids`/`avg_highs`, `bass_intensity`
(71/71 = 100, unbrauchbar), `downbeat_confidence`, `phrase_confidence`,
`outro_covered`/`unanalysed`/`analysis_coverage`, `texture_score`,
`bass_match_advice`/`transition_type` (nie gesetzt).

**Harte Regeln (G):** Invarianten 1–6 (Skill hpg-mixpoint-engineering);
Guard fuer Punkt und Blende; benannter Cue schlaegt Guard; ceil/floor mit
0.05 s; phrase_unit 16 (Psy/Trance) sonst 8; Half/Double kurzer Cut;
nie zwei Basslines (harter Bass-Swap 120/2500 Hz); unanalysed nie Kandidat;
Pitch ±4 %.

**Ereignismodell (D, Forensik 2026-07-20):** Audible-in · Switch/Bass-
Handover · Fade-out-Ende (+ Start-Cue); `transition_intent`
safe_intro_outro | rolling | drop_swap | break_exit; Switch-Regeln Neuheit /
Downbeat / traegt allein (30 % → 85 % Praezision); Rueckwaerts-Ableitung
Start = Switch − N Bars; Quellenprioritaet benannte Cues > Hot-Cues >
CUE(Auto) mit Provenienz > Audioanalyse > LLM advisory.

**Widerlegt (X):** siehe Abschnitt 1, "Ausdruecklich nicht enthalten".

**Hoertest-Evidenz:** 84 Noten 45/17/11/9/2; groove +0.53 (bereinigt
+0.46); bpm roh +0.28, bereinigt −0.06; uebrige ≈ 0; Genrewechsel 1.58 vs.
gleich 2.39; Melodic Techno 1.31, kein einziger gut; Datenlage-Gate 10 je
Merkmal und Klasse; Holdout nach Tracks.
