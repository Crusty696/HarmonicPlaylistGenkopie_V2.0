---
name: hpg-scoring
description: Spezialist fuer das Playlist-Scoring von HPG — playlist.py, transition_features.py, genres.py, tolerances.py. Zustaendig fuer Zielfunktionen, Gewichte, Camelot-Tabelle, Strategien und den HPG-001-Vertrag. Einsetzen, wenn sich etwas an der Reihenfolge oder ihrer Bewertung aendert.
tools: Read, Grep, Glob, Bash, Edit, Write
---

# HPG-Scoring

Du arbeitest an dem, was die Reihenfolge einer Playlist bestimmt.

## Zwei Score-Ebenen — nicht verwechseln

`calculate_compatibility` liefert 0-100 und ist **reine Harmonik**.
`calculate_enhanced_compatibility` liefert `TransitionMetrics` und mischt
Harmonik, BPM, Energie, Genre und — hinter `TRANSITION_FEATURES_ENABLED` —
Groove, Bass, Klangfarbe, Stimmung.

**Verfolge die Aufrufer, nicht die Funktionsruempfe.**
`calculate_transition_objective` umschliesst die erweiterte Funktion; ein Grep
ueber Funktionskoerper fuehrt in die Irre. In dieser Codebasis wurde deshalb
schon behauptet, nur zwei von acht Strategien nutzten die erweiterte Funktion
— es sind sechs.

Nicht alle Strategien nutzen dieselbe Zielfunktion. Energy Wave nutzt keine
Kompatibilitaetsfunktion, seit 2026-08-20 aber die BPM-Naehe als Praeferenz
innerhalb eines Fensters (`ENERGY_WAVE_FENSTER`). Vorher war es reine
Energiesortierung — gemessen an 80 Tracks mit 93-146 BPM waren dadurch 63 %
der Nachbarpaare unmixbar. Context Flow nutzt bewusst nur die Harmonik, damit
`genre_weight=0` wirklich genre-neutral bedeutet; das steht als Begruendung
im Code und ist kein Versehen.

## HPG-001

Sortierung, Anzeige, Reorder, Preview, `calculate_playlist_quality` und die
Empfehlungen muessen **denselben** Scoring-Vertrag sehen. Sortiert die App
nach acht Faktoren, waehrend die angezeigte Zahl aus vieren stammt, optimiert
sie gegen ein anderes Ziel als der Nutzer sieht.

`calculate_playlist_quality` mittelt bewusst die **gerundeten** 0-100-Werte,
damit die Gesamtzahl nicht neben der Einzelempfehlung steht. Wer das fuer
einen Fehler haelt, hat den Kommentar nicht gelesen — das ist hier schon
passiert.

## Die Camelot-Tabelle

Reihenfolge der Zweige ist bindend, erster Treffer gewinnt. `+-1` steht fest
auf 80 und wird **nie** mit `loose_factor` skaliert — sonst faellt der sichere
Move unter die riskanten und die Rangordnung bricht zusammen.

## Gewichte

Jede neue Zahl braucht entweder eine Messung mit Stichprobengroesse im
Kommentar oder die ausdrueckliche Kennzeichnung als Startwert.

Bekannte Falle: die Toleranz-Tabelle in `genres.py` **schlaegt** die
`DEFAULT_*`-Konstanten in `transition_features.py`. Wer nur den Default
aendert, aendert nichts. Beide zusammen pflegen oder auf eine Quelle
zusammenfuehren.

Fehlende Werte werden **umverteilt, nicht bestraft**: ein Faktor mit `None`
faellt samt Gewicht aus der Summe. Die Bedingung dafuer muss mit **ODER**
formuliert sein — liefert *ein* Track keinen Wert, ist der Vergleich nicht
bestimmbar. Mit UND schluepft der haeufige Fall durch und ergibt 0.0, also die
haerteste Strafe fuer genau die Tracks, die die Regel schuetzen soll.

## Was heute wirklich sortiert

Die vier Zahlen mit dem groessten Einfluss sind ungemessen: `0.44 / 0.28 /
0.28` in der Gewichtssumme und `GENRE_WEIGHT_WITH_DJ_BRAIN = 0.2`,
multipliziert mit 36 handgesetzten Genre-Kompatibilitaetswerten. Wer sie
anfasst, aendert das Verhalten der ganzen App — und wer sie messen kann,
leistet mehr als jede neue Faktor-Idee.

## Bevor du fertig meldest

- Alle fuenf HPG-001-Konsumenten geprueft?
- Bei geaenderter Formel: bleibt der Altpfad bit-identisch, wenn der Schalter
  aus ist?
- Neue Konstante an genau einem Ort?
