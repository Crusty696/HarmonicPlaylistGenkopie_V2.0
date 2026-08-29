# Handoff 2026-08-21 (spaet) — Scoring eingeschaltet, Hoertest-Saetze bereinigt

Stand: `main` auf `7caf50e`, gepusht, Arbeitsbaum sauber, Suite 1740 gruen.
Fortsetzung von `HANDOFF-2026-08-21-blende-und-hoertest.md` (gleicher Tag,
frueher). Dort steht der Blenden-Fix; hier steht, was danach kam.

## Regel fuer die naechste Session (vom Nutzer, gilt weiter)

Jede Aenderung VOR der Umsetzung durch `hpg-waechter` (Tor 1), vor dem
Commit nochmal (Tor 2). Subagenten-Berichte sind Hypothesen — nachpruefen.
Heute hat das dreimal den Unterschied gemacht: ein Scoring-Spezialist hat
die falsche Variante geprueft, ein Waechter eine erfundene Zahl (0.95) in
einem Kommentar gefunden, und eine Testzahl (75) war nach dem naechsten Fix
schon wieder falsch. Python ausschliesslich `.\venv312\Scripts\python.exe`.

## Was passiert ist (`7caf50e`)

**`TRANSITION_FEATURES_ENABLED = True`** (config.py:130). Die vier Faktoren
Groove/Bass/Timbre/Mood wirken jetzt im Scoring. Anlass: der Nutzer hoert,
dass die App Paare mit unpassendem Rhythmus waehlt — die Faktoren waren
seit 2026-08-19 gebaut und gecacht, aber wirkungslos.

**Gewichte** (`genres.py` `_TOLERANCE_DEFAULTS`): groove 0.12 -> **0.30**,
verteilt aus harmonic (0.246 -> 0.16), bpm/energy (0.157 -> 0.12), genre
(0.14 -> 0.12). Summe 1.0, beim Import validiert. Gemessen an je einer
Playlist (Harmonic Flow, eingebauter Stand):

| Genre | groove Median | Uebergaenge <0.7 | Camelot>=80 | Harm-Median |
|---|---|---|---|---|
| Psytrance 60 | 0.90 -> 0.93 | 9 -> 4 | 40/59 -> 35/59 | 90 -> 80 |
| Progressive 53 | 0.89 -> 0.87 | 10 -> 7 | 31/52 -> 33/52 | 80 -> 80 |
| Melodic Techno 23 (n=22) | 0.86 -> 0.90 | 7 -> 3 | **14/22 -> 7/22** | 80 -> 70 |

Verworfen wurde "0.30 allein aus harmonic" (harmonic 0.066): gewann bei
groove staerker, kostete aber ein Drittel der guten Tonart-Uebergaenge. Der
Scoring-Spezialist rechnete vor, dass Harmonik bei 0.066 zum reinen
Tiebreaker wird (ein Key-Clash kostet dann 6 Punkte, soviel wie ein
normales Groove-Delta).

**Das sind Startwerte, keine bewiesenen.** Die Hoertest-Noten sollen sie
ersetzen. `datenlage_urteil` verlangt 10 Faelle je Merkmal und Klasse.

**Genre-Halbierung in den neuen Pfad uebernommen** (`playlist.py`
`calculate_enhanced_compatibility`): der Altpfad halbierte das
Genre-Gewicht fuer "Unknown" (GENRE_WEIGHT_WITHOUT_DJ_BRAIN); der
Acht-Faktoren-Pfad kannte das nicht. Jetzt als Verhaeltnis drin, casefold
wie `get_genre_compatibility`, und zusaetzlich fuer nicht-kanonische Tags
("House"), die denselben 0.5-Fallback bekommen. Gemessen an zwei
identischen Tracks mit Tag "House": Altpfad 0.90, neu ohne Halbierung
0.88, mit 0.93.

**Drei Beifaenge aus der Suche nach totem/abgeschaltetem Code:**
- `rhythm_advice` (dj_brain.py:537-544) wurde berechnet und gesetzt, aber
  nie in die Notes uebernommen. Jetzt drin; landet in der GUI in der grauen
  Meta-Zeile (wie "Gain:"), nicht im DJ-Brain-Block — Praefixliste bewusst
  nicht angefasst.
- `ai_engine.py` verwarf bei fehlendem `outro_covered` das GESAMTE
  KI-Ergebnis, auch sub_genre/moods, die im KI-Bonus wirken — wegen
  Mixpunkten, die kein Produktivpfad liest. Jetzt nur Mixpunkte -> None.
  Nutzer hat die Lockerung ausdruecklich freigegeben; Test umbenannt.
- GUI: Tooltip "Genre wird ignoriert" korrigiert (der Schalter aendert nur
  die Sortierstrategie); Button "Auf gelernte Werte zuruecksetzen" ->
  "Eigene Werte verwerfen" (`transition_tolerances.json` ist `{}`, gelernte
  Werte gibt es nicht); `_lade_transition_regler` wird jetzt beim Aufbau
  gerufen, nicht nur im Reset.

Tests: vier Vertragswechsel mit Begruendung (`test_ai_schema`,
`test_scoring_contract` — Zahl bleibt 78, nachgemessen —,
`test_transition_weight_ui` zweimal, jetzt gegen `HPG_TOLERANCES_FILE`
isoliert). Kein CACHE_VERSION-Bump: Analyse-Output unveraendert.

## Hoertest-Saetze bereinigt (ausserhalb des Repos)

Beide Saetze wurden vom Nutzer beanstandet: "du suchst Paare aus, die
nicht aehnliche Rhythmen haben — das macht ein DJ nicht." Gemessen: der
Kandidatenpool hat groove-Median 0.89, der Hoertest-Satz zog per Maximin
gezielt die Raender (20 % unter 0.5, im Pool nur 2 %).

| Satz | Ort | Port | getauscht | Stand jetzt | Noten |
|---|---|---|---|---|---|
| Psytrance | `Music\HPG-Psytrance` | 8766 | 13 (BPM>=5) + 24 (groove<0.5) | groove min 0.50 / Median 0.81, BPM-Abstand max 4, 120 eindeutige Paare | **3** von 120 |
| Mischsatz | `Music\HPG-Hoertest` | 8765 | 69 (groove<0.5 oder BPM>=5) | groove min 0.50 / Median 0.81, BPM max 4, 90 Genrewechsel bleiben | **46** von 160 |

Genrewechsel im Mischsatz bewusst NICHT entfernt — dass sie schlechter
abschneiden (1.58 gegen 2.39) ist ein Ergebnis, das ohne sie nicht mehr
pruefbar waere. Verworfene Noten liegen in `Music\HPG-Hoertest-Sicherung\`
(Snapshot vor dem Tausch: 84 bzw. 4 Noten).

Server starten:
```
.\venv312\Scripts\python.exe tools\hoertest_server.py --dir C:\Users\david\Music\HPG-Psytrance --port 8766
.\venv312\Scripts\python.exe tools\hoertest_server.py --dir C:\Users\david\Music\HPG-Hoertest --port 8765
```
Am Ende dieser Session liefen beide (pythonw, PIDs 3320 / 4432); nach einem
Reboot sind sie weg.

## Naechster Schritt (mit dem Nutzer abgestimmt: "Weg 3")

**Psy-Satz hoeren, dann Gewichte aus den Noten schaetzen.** Vorher einen
Teil nach TRACKS getrennt zuruecklegen. Die eingebauten 0.30 sind der
Platzhalter, bis das da ist. Nicht: Blendenlaengen-Varianten rendern
(Blendenlaenge korrelierte als einziger Faktor nicht mit den Noten,
rho -0.08).

## Offen (zusaetzlich zum vorigen Handoff)

> Stand 2026-08-21 (spaet): Punkt 2 (Set-Timeline) ist erledigt (e946080),
> Punkt 3 teilweise (dj_report.py, __init__-Re-Exporte, Genre-Resolver;
> Rest bewusst belassen) und Punkt 4 teilweise (CLAUDE.md, hpg-orientation,
> Skill-Spiegel; PLAYLIST_ALGORITHMEN_ERKLAERUNG und groove-scoring:189
> offen) — Details und
> Begruendungen in `HANDOFF-2026-08-21-fixes-und-hoertest-mobil.md`.

1. **Melodic Techno** verliert mit den neuen Gewichten die Haelfte der
   Camelot-Treffer. Es war im Hoertest die Problemgruppe (36 Uebergaenge,
   keiner gut). Ob dort Tonart oder Rhythmus wichtiger ist, muessen die
   Noten zeigen; `GENRE_TRANSITION_TOLERANCES` ist je Genre ein eigener
   Dict, ein abweichender Eintrag braucht keine neue Mechanik.
2. **Set-Timeline** (`playlist.py` `_calculate_timeline_entries`,
   `playing_duration = dauer - overlap`): ignoriert mix_in und mix_out. An
   231 echten Tracks gemessen: Fehler je Track Median +123 s, ein Set aus
   10 Tracks wird **21 Minuten zu lang** angezeigt. Peak-Position haengt
   daran. Alter Fehler, nicht vom Blenden-Fix verursacht; eigener Anlass.
3. **Toter Code** (aus der Suche, alle verifiziert): `tools/dj_report.py`
   (164 Z., null Referenzen, hartkodierter D:-Pfad); 15 Funktionen nur von
   Tests gerufen (~179 Z., u.a. `calculate_lufs`, `get_key`,
   `bars_to_seconds`, beide `get_format_info`); 7 Track-Felder ohne Leser
   (`avg_mids`, `avg_highs`, vier `lufs_*`, `danceability`);
   `hpg_core/__init__.py` re-exportiert sieben ungenutzte Namen und zieht
   librosa bei jedem Import. `BARS_PER_PHRASE` hat keinen Produktivnutzer,
   aber fuenf Tests schreiben damit 8 Takte fest. Drei identische
   Genre-Resolver in playlist.py (360, 1475, 2031) — nicht tot, aber
   dreifach.
4. **Doku veraltet:** CLAUDE.md sagt 1690 Tests / main.py 4900 Zeilen (real
   1740 / 5336) und listet groove.py, transition_features.py,
   mix_analysis.py, tolerances.py nicht. Skill `hpg-orientation` hat
   durchgehend falsche Zeilennummern; `.claude/skills/` und
   `.agents/skills/` divergieren bei 13 von 14. `docs/PLAYLIST_ALGORITHMEN_
   ERKLAERUNG.md` beschreibt 10 Strategien (es sind 8).
   `HANDOFF-2026-08-20-groove-scoring.md:189` sagt "Flag auf False" —
   ueberholt.
5. Weitere abgeschaltete/halbfertige Stellen, verifiziert:
   `use_compressor` im Renderer wird von keinem Produktivpfad gesetzt (die
   App meldet trotzdem "ohne Pedalboard inaktiv"); `DJRecommendation.
   bass_match_advice` und `.transition_type` werden nie gesetzt;
   `target_energy`/`overlap` als Strategie-Parameter haben keinen
   UI-Anschluss; `LUFS_REFERENCE = -18.0` hat keinen Konsumenten (Renderer
   arbeitet mit -14).

## Scratchpad-Messskripte (ausserhalb Repo, Temp)

`mess_schalter.py`, `mess_groove_gewicht.py`, `mess_verteilung.py`,
`mess_final.py` unter `%TEMP%\claude\hpg_mess\` bzw. dem
Session-Scratchpad. Achtung: im Scratchpad liegt eine fremde `numbers.py`,
die Pythons stdlib-Modul ueberdeckt — Skripte von dort nicht direkt
starten, sondern nach `hpg_mess\` kopieren.
