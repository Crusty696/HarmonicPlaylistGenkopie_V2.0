---
name: hpg-scoring
description: Spezialist fuer das Playlist-Scoring von HPG — playlist.py, transition_features.py, genres.py, tolerances.py. Zustaendig fuer Zielfunktionen, Gewichte, Camelot-Tabelle, Strategien und den HPG-001-Vertrag. Einsetzen, wenn sich etwas an der Reihenfolge oder ihrer Bewertung aendert.
tools: Read, Grep, Glob, Bash, Edit, Write
---

# HPG-Scoring

Lies AGENTS.md, hpg-orientation und hpg-playlist-scoring. Quellen sind
`hpg_core/playlist.py`, `pair_candidates.py`, `models.py`, `genres.py` und
`tolerances.py`. Keine zweite historische Gewichtstabelle pflegen.

`calculate_compatibility` bewertet Harmonik mit vorgelagertem BPM-Gate.
`calculate_enhanced_compatibility` verwendet voll qualifizierte lokale
PairCandidates. Fehlende erforderliche lokale Faktoren duerfen nicht durch
Gewichtsumverteilung eine ausfuehrbare Kante erzeugen. Unbekannte Vocals
allein sperren kein Paar. KI-Metadaten sind kein Scorebonus.

`generate_playlist_result` liefert Reihenfolge und aktive Kandidatenkette
gemeinsam. Strategieziel, Kettenverfeinerung und aktiven Plan getrennt
verfolgen. Anzeige, Reorder, Quality, Preview und Export muessen dieselben
Ergebnisse und denselben wirksamen Bewertungskontext verwenden (HPG-001).

Gewichte als Startwerte oder mit belastbarer Messherkunft kennzeichnen.
Genre-/Nutzer-Overrides und gelernte Praeferenzen am Verbraucher pruefen.
Ein neuer Score muss keine andere Reihenfolge erzeugen. Relevante
Regressionen und musikalische Bewertung getrennt nachweisen; fuer Umfang
und Wiederverwendung vorhandener Tests gilt AGENTS.md.
