# Faktenblatt fuer Plan "Mixpunkt-Kandidaten Teil 3 — Hoertest: Kandidaten vergleichen"

Stand 2026-08-22, verifiziert am Branch `kandidaten-teil2` (enthaelt Teil 2) durch
Lese-Subagent `hpg-statistik`. Spec: `docs/superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md:143-177`.
**Vor Gebrauch jede Zeile erneut pruefen.**

## Spec Abschnitt 3 verlangt — und NICHTS davon existiert heute

`prepare --modus kandidaten`, `fit --modus kandidaten`, Server-Modus Kandidaten
mit Seed je Paar, `bewertung.csv (pair_id, clip_id, note, gewaehlt, zeit)`,
Dateiname `<pair_id>_k<n>.wav`, `merkmale.csv` mit Teilwerten + `schema,
blend_bars, t_out, t_in, provenance, confidence`, Seite je Paar, "bester"-Wahl,
Paarvergleich/Bradley-Terry bzw. konditionale Logistik, Holdout nach Tracks,
AUC/Trefferquote im Fit-Bericht, `hpg_core/data/candidate_preferences.json`
samt Lader, Mobil-Start fuer einen weiteren Satz.

## 1. `tools/rate_transitions.py` (1080 Z., 4 Leerzeichen)

- CLI `main` :1048-1077, `add_subparsers(dest="befehl", required=True)` :1051.
  `prepare` :1053-1066: `--anzahl` (Default `STANDARD_ANZAHL`=100 :130), `--out`
  (Pflicht), `--bpm-toleranz` (2.0 :81), `--cache`, `--seed` (20260820 :110),
  `--nur-genre` (choices `CANONICAL_GENRES`). `fit` :1068-1072: `--dir`, `--seed`,
  `--genre` (append). **Kein `--modus`.**
- Konstanten: `NEUE_FAKTOREN` :67, `KLASSISCHE_FAKTOREN` :70, `ALLE_FAKTOREN` :71,
  `ZUSATZ_SPALTEN=("overall_score","lufs_delta")` :73; `STANDARD_BPM_TOLERANZ=2.0`
  :81, `SCORING_BPM_TOLERANZ=3.0` :86, `MIN_HARMONIC_SCORE=60` :87,
  `MIN_OVERALL_SCORE=0.70` :99, `MIN_GROOVE=0.5` :102,
  `HOERTEST_TRANSITION_TYPE="pro_eq_swap"` :108, `CROSSFADE_SEK=32.0` :121,
  `PRE_ROLL_SEK=8.0` :122, `POST_ROLL_SEK=8.0` :123, `RESERVE_FAKTOR=4` :126,
  `L2_STAERKE=1.0` :139, `BOOTSTRAP_ZIEHUNGEN=500` :140, `BUDGET_MAX=0.30` :141,
  `KOEFFIZIENT_VOLLAUSSCHLAG=1.0` :144, `MIN_EREIGNISSE_JE_MERKMAL=10` :147,
  `MIN_KONTROLL_STREUUNG=0.05` :158, `BEWERTUNG_MIN/MAX=1/5` :160-161, `GUT_AB=4` :163.
- "Altnoten verworfen": Kommentar :103-107; `docs/HANDOFF-2026-08-21-fixes-und-hoertest-mobil.md:8-14`.
- `sammle_kandidaten(tracks, bpm_toleranz=2.0) -> list[dict]` :650-699 (Gates:
  gleicher Pfad :672, BPM fehlt :674, `effective_bpm_diff > tol` :676-678,
  `calculate_enhanced_compatibility(a,b,3.0)` :679, harmonic < 60 :680,
  overall < 0.70 :682, `_faktoren_vollstaendig` :622-647/:684, groove < 0.5 :687);
  Dict `{"track_a","track_b","merkmale","zusatz"}` :696-698. `filtere_nach_genre` :702-720.
- `geplanter_overlap(a, b, mix_out_a, mix_in_b) -> float` :723-769 (Sekunden; Rueckfall `CROSSFADE_SEK`).
- `rendere_paar(kandidat, pair_id, clips_dir) -> (rel_pfad, crossfade)` :772-842:
  Mixpunkte `calculate_paired_mix_points` :783; `crossfade_reserve` :213-243 →
  `ValueError` = Paar verworfen :787-797; **baut `TransitionClipSpec(...)` direkt**
  (nicht `from_plan`) :798-839 mit `transition_type=HOERTEST_TRANSITION_TYPE`,
  `pre_roll_sec/post_roll_sec`, `bpm_a/b`, `first_downbeat_a/b`,
  `downbeat_reliable_*`, `bar_phase_reliable_*`; `lufs_a/b` bewusst ungesetzt
  :826-828; Datei `clips_dir / f"{pair_id}.wav"` :840.
- pair_id `f"{nummer:03d}"` :896 (kein `_k<n>`).
- `befehl_prepare` :861-953: Maximin ueber `NEUE_FAKTOREN` :880-885 (`maximin_auswahl` :170);
  `bewertung.csv` Spalten `("pair_id","clip","bewertung")` :926; `merkmale.csv`
  `("pair_id", *ALLE_FAKTOREN, "crossfade_sek", *ZUSATZ_SPALTEN, "track_a", "track_b")` :928-932;
  `schreibe_csv(pfad, spalten, zeilen)` :850-855, `lies_csv` :845.
- `befehl_fit` :960-1041: `verbinde_bewertungen` :261-298, `waehle_merkmale` :301-321,
  `zu_zielgroesse` :324-332 (binaer Note >= 4), `fit_logistic` :396-402 (eigene
  L2-Logistik, `scipy.optimize.minimize`, kein sklearn), `bootstrap_intervalle`
  :405-442 (Einzelzeilen, kein Cluster), `datenlage_urteil` :448-465,
  `leite_gewichte_ab` :468-501, `baue_genre_gewichte` :504-532,
  `baue_ausgabe_json` :535-574 → `<dir>/gewichte.json` :996-998. **Kein Holdout,
  keine AUC, kein Paarvergleich, kein `write_override`-Aufruf.**
- `write_override` nur `hpg_core/tolerances.py:92-113`; Aufrufer `main.py:1618-1625`, `tests/test_tolerances.py:54-59`.
- Ordner (auf Platte, nicht im Repo): `C:\Users\david\Music\HPG-Hoertest\`
  (`bewertung.csv, clips\, merkmale.csv, mixpunkte.json, pegel.json, dip.json,
  server.log`), `C:\Users\david\Music\HPG-Hoertest-Mobil\` (`hoertest_server.py,
  Psytrance\, Mischsatz\, Start.bat, Stop.bat, LIESMICH.txt`); Mobil-`Start.bat`
  startet fest zwei Server (Psytrance 8766, Mischsatz 8765) — kein Mechanismus
  fuer einen weiteren Satz.

## 2. `tools/hoertest_server.py` (633 Z.; Python 4, CSS/JS 2)

`BEWERTUNG_SPALTEN=("pair_id","clip","bewertung")` :35, `CLIP_NAME=^[0-9A-Za-z_-]{1,32}\.wav$`
:38 (`_k1`-Suffix passt), `NOTEN` :40, `NACHLAUF_SEK=8.0` :53. Routen
`HoertestHandler` :480-605: GET `/` (SEITE :214-477), `/noten` :510-521,
`/daten` (`lade_uebersicht` :119-165, Track-Infos aus Cache :168-193) :523-531,
`/clips/<name>` mit Range/206 :532-580; POST `/note` `{pair_id, note|null}` →
`merge_bewertungen` + `schreibe_csv` :582-605. **Eine Seite fuer alle Paare**;
keine Seite je Paar, keine "bester"-Wahl, keine Zeitspalte, **kein Zufall/Seed**.
`main` :608-630 (`--dir`, `--port` 8765, 127.0.0.1). Stdlib-only (Mobil).

## 3. `hpg_core/data/`

Nur `transition_tolerances.json` (Lader `tolerances.py:18`). **`candidate_preferences.json` existiert nicht.**

## 4. `hpg_core/transition_renderer.py` (1052 Z., 4 Leerzeichen)

`render_transition_clip(spec, output_path) -> str` :138; Layout `[pre_roll | crossfade | post_roll]` :10.
`TransitionClipSpec` :51-96: `track_a_path, track_b_path, mix_out_sec, mix_in_sec,
crossfade_sec` (Sekunden), `transition_type="smooth_blend"`, `pre_roll_sec/post_roll_sec=30.0`,
`bass_cutoff_hz=200.0`, `target_sr=44100`, `bpm_a/bpm_b`, `first_downbeat_a/b`,
`downbeat_reliable_a/b`, `bar_phase_reliable_a/b`, `normalize_rms=True`,
`normalize_target_db=-14.0`, `use_compressor=False`, `lufs_a/lufs_b=0.0`;
`from_plan(plan, from_track, to_track)` :99-134. Blende in **Sekunden**, Deckel
`MAX_TRANSITION_OVERLAP_SECONDS=64.0` (:154). `pro_eq_swap` nicht parametrisierbar
(`_apply_eq_crossfade` :837ff, `fc1=120`, `fc2=2500`, Bass-Swap bei der Haelfte
:858-869). Pegelfix: `_rms_normalize` Solo-Teile :310-313, `_apply_lufs_delta`
gemessen :325-330 (±6 dB :706), Soft-Limiter :714-731, PCM_16 :365.

## 5. Tests

`tests/test_rate_transitions.py` (4 Leerzeichen; Fakes `_FakeTrack` :354,
`_FakePlan` :428, `_FakeEmpfehlung` :434, `_GenreTrack` :510, `_GateTrack` :557,
`_Metrik` :565; kein Audio/Cache), `tests/test_hoertest_server.py` (**2 Leerzeichen**;
Import :10-16; kein HTTP-Test), `tests/test_transition_renderer.py` (73 Tests).

## 6. Nutzer-Doku

`docs/HANDOFF-2026-08-21-blende-und-hoertest.md:52-62` (Saetze, Sicherung),
`docs/HANDOFF-2026-08-21-fixes-und-hoertest-mobil.md:8-24, 88-90` (feste Blende,
Altnoten verworfen, Mobil mit zwei Servern, Ziel je Satz 40/40 Noten).

## Statistischer Hinweis

Bootstrap :405-442 zieht Einzelzeilen; fuer Kandidaten desselben Paars
(geschachtelt) ist die Cluster-Ebene Paar bzw. Track.
