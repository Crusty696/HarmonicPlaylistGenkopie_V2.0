# HPG Fixlog — A1 Phrasen-Phase + Restarbeiten (2026-07-26, autonom)

Abschluss-Runde nach den Wellen 1-4. Alle Aenderungen mit `AUDIT-FIX`/`AUDIT-FEATURE`-Markern.

## A1 — Phrasen-Phase (das fehlende DJ-Fundament)

- **`downbeat.estimate_first_phrase()`** (neu): Bar-Level-Voting analog zur
  Downbeat-Erkennung — pro Bar-Grenze Bass-Onset, Chroma-Novelty und positiver
  RMS-Sprung (Element-Einsatz), z-normiert, Voting ueber `bar_index % phrase_unit`.
  Liefert `(first_phrase, confidence)`; Mindestlaenge 2 Phrasen.
- **`Track.first_phrase` / `Track.phrase_confidence`** (neu) +
  **`Track.phrase_anchor`**-Property mit Konfidenz-Gate
  (`config.PHRASE_CONFIDENCE_MIN = 0.25`; darunter Fallback `first_downbeat`
  = exakt das bisherige Verhalten, Alt-Caches bleiben gueltig).
- **Verdrahtung**: `analysis.analyze_track` (beide Pfade) schaetzt die Phase
  nach Downbeat+Struktur und verwendet den Phrasen-Anker fuer
  `calculate_genre_aware_mix_points`, den RMS-Fallback und den
  Rekordbox-Cue-Override (`align_ai_mix_points`).
  `dj_brain.calculate_paired_mix_points` quantisiert seine Endwerte jetzt auf
  den Phrasen-Anker beider Tracks.
- **Cache 19 → 20**: alle Tracks werden mit Phrasen-Anker neu analysiert.

## Renderer-Feinschliff

- **C1**: Exakt-Pfad (beide Downbeats verlaesslich) aligned jetzt auf
  TAKT-Phase (Modulo Bar) statt nur Beat-Phase — Beat 1 auf Beat 1, nicht nur
  Kick auf Kick. Schaetz-Pfad bleibt bewusst auf Beat-Ebene.
- **C4**: Stretch-Clamp ±15 % → ±8 % (DJ-realistisch; ±15 % ohne Key-Lock
  waren ~2,4 Halbtoene Verstimmung).
- **R-07**: `TransitionClipSpec.lufs_a/lufs_b` (aus `Track.lufs`, pyloudnorm/
  BS.1770). Liegen beide Messwerte vor, wird der Normalisierungs-Gain direkt
  daraus berechnet statt aus ungewichtetem RMS (2-4 LUFS Restfehler je nach
  Spektrum); Fallback bleibt RMS.

## Scoring / GUI

- **D2-light**: Vocal-Clash — `VOCAL_CLASH_PENALTY = 0.06` auf den
  Overall-Score, wenn BEIDE Tracks als "vocal" erkannt sind ("unknown" wird
  nie bestraft), plus Risk-Note in `_assess_transition_risks`. Damit hat
  `vocal_instrumental` erstmals einen Consumer.
- **T2**: Preview-Waveform-Peaks (bis ~22 MB WAV-Decode) laufen jetzt in einem
  QThread statt im GUI-Thread — kein UI-Freeze mehr bei jedem Preview;
  Fehler werden geloggt statt stumm geschluckt (F9-Teilfix).
- **F5**: START OVER setzt jetzt wirklich alles zurueck (Playlist-Tabelle,
  Mix-Tips inkl. Preview-Cleanup, Timeline, Analytics, analyzed_raw_tracks,
  scoring_context, RunState).

## Verifikation

- Lokale Stub-Checks: A1-Property, Vocal-Penalty, Paar-Punkte auf
  Phrasen-Anker — gruen. Regressions-Suites Welle 1/2/4 (37 Checks) — gruen.
- Auf dem Zielrechner: voller pytest + `e2e_check.py` (echte Analyse →
  A1-Gitter-Invarianten → Playlist → Empfehlungen → Render → Clipping-/
  Pegel-Checks → Rekordbox-Verfuegbarkeit). Ergebnisse siehe Chat-Protokoll.

## Bewusst offen (dokumentiert, kein Korrektheitsrisiko)

- Key-Lock beim Time-Stretch (pyrubberband) und Tempo-Ramp (C5) — Feature.
- Vocal-Praesenz PRO SECTION (D2 voll) — braucht Stem-/VAD-Analyse.
- allin1/Beat-This-Backends — optionale Modell-Upgrades (siehe Skills).
- Toter Code, der von Tests abgedeckt ist (get_key, calculate_lufs, ...) —
  Entfernung wuerde Tests brechen; bei Gelegenheit gemeinsam mit Tests.
