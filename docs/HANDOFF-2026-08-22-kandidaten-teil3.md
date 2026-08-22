# Handoff 2026-08-22: Mixpunkt-Kandidaten Teil 3 — Hoertest Kandidatenmodus gebaut

Vorheriger Stand: `docs/HANDOFF-2026-08-22-kandidaten-teil2.md`. Plan:
`docs/superpowers/plans/2026-08-22-mixpunkt-kandidaten-teil3-hoertest.md` (Waechter
Tor 1: MIT AUFLAGEN, eingearbeitet; Tor 2 vor dem Merge). Spec Abschnitt 3.

**Nutzer-Anweisung 2026-08-22 (`/goal`, Wortlaut):** „Audio-Tests: Alle Aufgaben,
die eine menschliche Hörprobe erfordern, überspringst du. Dokumentiere sie für mich
auf einer finalen Checkliste und arbeite sofort am nächsten Punkt weiter." — Der
Hoertest selbst wurde deshalb NICHT durchgefuehrt; die Werkzeuge sind gebaut,
getestet und mit synthetischen Noten einmal durchlaufen. Checkliste unten.

## Was gebaut wurde (Branch `kandidaten-teil3`)

- `hpg_core/candidate_preferences.py` (neu) + `hpg_core/data/candidate_preferences.json`
  (`{}`): Lader mit Override; `pair_candidates.score_pair` nimmt die Praeferenz-
  Gewichte, wenn kein explizites `tolerances` uebergeben ist (explizit gewinnt).
  `tests/conftest.py`: Autouse-Fixture koppelt alle Tests von der Datei ab.
- `tools/rate_transitions.py`: `prepare --modus kandidaten` (`rendere_kandidat`,
  `kandidaten_zeilen`, `reihenfolge_fuer_paar`, `LIESMICH-kandidaten.txt`),
  `fit --modus kandidaten` (`verbinde_bewertungen_kandidaten`, `nur_mit_note`,
  `holdout_nach_tracks`, `_kennzahlen`/`_standardisiere_mit`, `auc`,
  `paarvergleich_daten`, `identifizierbare_merkmale`, `fit_paarvergleich`,
  `bootstrap_paarvergleich`, `trefferquote_paarvergleich`,
  `gewichte_aus_paarvergleich`, `schema_rangfolge`, `baue_candidate_preferences`,
  `uebernahme_erlaubt`, `befehl_fit_kandidaten`); `--modus einzel` (Default) ist
  der heutige Pfad, unveraendert. Neue Konstanten `BEWERTUNG_KANDIDATEN_SPALTEN`,
  `MERKMALE_KANDIDATEN_SPALTEN`, `HOLDOUT_ANTEIL = 0.30` (Startwert),
  `PAAR_STREUUNG_MIN = 0.05` (Startwert).
- `tools/hoertest_server.py`: Moduserkennung (`ist_kandidatensatz`), Seite je Paar
  (`SEITE_KANDIDATEN`), `/daten` (Gruppen, Clips in gespeicherter Reihenfolge,
  verdeckt: nur `clip_id, clip, note, gewaehlt, crossfade_sek`), `/reihenfolge`,
  POST `/note` und `/bester` mit Zeitstempel (`merge_kandidaten_bewertung`);
  Kontext (Tempo/Genre/Camelot) aus Cache oder `merkmale.csv` (Mobil).
- Tests: `tests/test_candidate_preferences.py` (3), `tests/test_rate_transitions.py`
  (+15), `tests/test_hoertest_server.py` (+3), `tests/test_pair_candidates.py` (+1).
- Doku: `CLAUDE.md`, `.agents/skills/hpg-testing-verification/SKILL.md`,
  `.agents/skills/hpg-mixpoint-engineering/SKILL.md` (nach Merge nach `.claude/` spiegeln).

Suite im Worktree (HEAD `b716e19`): **1836 passed, 25 warnings, 88 s, Exit 0**
(Coverage-Gate 70 bestanden).

## Die 14 Entscheidungen (Plan, Spec offen) — Kurzfassung

`--modus {einzel,kandidaten}`; Server-Moduserkennung an `clip_id`; Reihenfolge je
Paar mit Seed `seed_satz + pair_id` in `reihenfolge.json`; `bewertung.csv`
`pair_id, clip_id, note, gewaehlt, zeit`; `merkmale.csv` mit Teilwerten, Score
(nie angezeigt), Schemata, Blende, Kontext; `--anzahl` = Paare; Blende ueber
Renderer-Deckel 64 s oder Restlaenge → Kandidat faellt weg; Zielgroesse 1 Note
(L2-Logistik), Zielgroesse 2 Bradley-Terry ohne Spiegelung, unstandardisiert;
keine Imputation (leeres Merkmal → Clip raus), Clips ohne Note bleiben fuer den
Paarvergleich; Identifizierbarkeit (Innerhalb-Paar-Streuung ≥ 0.05) — nicht
identifizierbare Merkmale (bpm, genre, oft harmonic/energy) behalten ihr
Toleranz-Gewicht; Holdout nach Tracks 30 % (≈ 50–60 % der Clips); Uebernahme nur
ueber `uebernahme_erlaubt` (Datenlage Note, Paare ≥ 10 × identifizierbare
Merkmale, Holdout mit beiden Klassen, AUC > 0.5, Trefferquote > Zufallsbasis,
mindestens ein gesichert positives Merkmal), sonst Entwurfsdatei; Gewichte aus
positiver unterer Bootstrap-Grenze (Cluster = Paar) auf das Restbudget;
Schema-Rangfolge je Genre ueber alle Schemata des Kandidaten (Laplace);
`candidate_preferences.json` Format `{_diagnose, <Genre>: {kandidaten_*_weight,
schema_rang}}`; explizites `tolerances` gewinnt; Mobil: Server kopieren, Modus
automatisch; Satz 1 unberuehrt.

## Synthetischer Ende-zu-Ende-Lauf (Plan Task 5, keine Hoerprobe)

- `prepare --modus kandidaten --anzahl 3 --out <scratchpad>\hoertest_kandidaten_probe`
  gegen `hpg_cache_v34.db` (231 Tracks): **3 Paare, 30 Clips (12 / 6 / 12), 45 s
  gesamt** (≈ 1,5 s je Clip inkl. Laden). Paar 002: 6 von 12 Kandidaten
  verworfen (Blende passt nicht in Restlaenge / ueber 64 s — `ValueError`-Pfad).
  Dateien: `bewertung.csv` (30 Zeilen, Spalten wie Spec), `merkmale.csv`
  (`MERKMALE_KANDIDATEN_SPALTEN`, Teilwerte gefuellt, z. B. Paar 001 Kandidat 1:
  harmonic 0.75, groove 0.83, loudness 0.77, score 0.71, `pssi_phrase|analyzer|sektion`),
  `reihenfolge.json` (Seed 20260821/22/23), `LIESMICH-kandidaten.txt`.
- Server-Rauchtest (`--port 8767`): Seite "HPG Hoertest — Kandidaten" ausgeliefert;
  `/daten` 3 Gruppen mit 12/6/12 Clips in `reihenfolge.json`-Reihenfolge, Clip-Felder
  genau `clip, clip_id, crossfade_sek, gewaehlt, note`; Kontext 140.0 BPM /
  Psytrance / 11A; `POST /note` und `/bester` → `bewertung.csv` (`001_k3`: note 4,
  gewaehlt 1, zeit 2026-08-22T22:48:23, exklusiv je Paar); Clip mit Range → 206.
- `fit --modus kandidaten` auf synthetischen Noten (Note aus Score-Median, bester =
  hoechster Score je Paar — nur Funktionstest): 30 Clips, Holdout 18/30 (60 %),
  Zielgroesse 1 nicht schaetzbar (eine Klasse im Train), Paarvergleich 1 Paar im
  Train, identifizierbar harmonic/bass/timbre/loudness/structure, nicht
  identifizierbar bpm/energy/groove/mood (Toleranz-Gewicht behalten),
  Holdout-Trefferquote 0.5 vs. Zufall 0.125, **NICHT uebernommen** (Grund:
  Datenlage Zielgroesse 1) → `candidate_preferences_entwurf.json` im Satzordner;
  `hpg_core/data/candidate_preferences.json` bleibt `{}`.

## Checkliste Hoerproben (Mensch — vom Agenten uebersprungen)

1. `.\venv312\Scripts\python.exe tools\rate_transitions.py prepare --modus kandidaten
   --anzahl 40 --out %USERPROFILE%\Music\HPG-Hoertest-Kandidaten --nur-genre Psytrance`
   (≈ 1,5 s je Clip, bis 12 Clips je Paar → ca. 10–12 min).
2. Satz in den Mobil-Ordner kopieren, aktuelle `tools/hoertest_server.py` dazu,
   dritten Server mit `--port 8767` starten (`Start.bat` im Mobil-Ordner liegt
   ausserhalb des Repos — Zeile analog 8765/8766 ergaenzen). Der Server erkennt
   den Kandidatenmodus selbst.
3. Je Paar **alle** Clips benoten **und** den besten waehlen (Taste B). Ziel:
   mindestens 10 Paare mit Wahl je identifizierbarem Merkmal im Train (bei 30 %
   Holdout-Tracks ≈ 50–60 % der Clips im Holdout → Satz entsprechend gross) und
   10 Ereignisse je Merkmal und Klasse fuer die Noten.
4. `fit --modus kandidaten --dir <Satz>`; Bericht lesen (Identifizierbarkeit, AUC,
   Trefferquote vs. Zufall). Nur bei "UEBERNOMMEN" wirken die Gewichte in
   `score_pair`; sonst Entwurf pruefen und mehr hoeren.
5. Nach Uebernahme: App-Lauf (Teil 4) und Hoerprobe der Rang-1-Kandidaten.
6. Offen aus Teil 2 (unveraendert): `KICK_AKTIV_*`-Startwerte (Teil 1) markieren
   fast nie einen Kick — im Hoertest pruefen; `percussive_ratio_lokal` liegt zur
   Haelfte unter 0.3.

## Offen fuer Teil 4

Rang-1 → `Track.mix_in_point/mix_out_point`, `calculate_enhanced_compatibility`,
`scoring_context`, GUI-Kandidatentabelle, `schema_rang` aus
`candidate_preferences` als Vorbelegung, Wahl pro Paar (`candidate_choices.json`),
Faktoren-Regler "Lautheit" (die zehn `kandidaten_*_weight` nicht in
`write_override`-Summe), App-BPM-Default 2.0, Export K1..K6, `KICK_KONFLIKT_ABZUG`
bei Bass-/EQ-Swap entfaellt.
