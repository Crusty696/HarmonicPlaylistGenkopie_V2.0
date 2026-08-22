# Handoff — Groove-Scoring und Uebergaenge, Stand 2026-08-20 (abends)

Branch `feature/groove-scoring`. Suite **1690 gruen**, `verify_wave4.py`
6 von 6.

Zur Testzahl, weil sie in der Vorfassung dieses Dokuments nicht stimmte:
dort stand „1658 gruen“. Nachgemessen am Branch-Kopf ohne die heutigen
Aenderungen waren es **1654**. Woher die 1658 kamen, ist nicht
rekonstruierbar — moeglicherweise ein Lauf mit anderen Optionen. Die 36
neuen Tests dieser Sitzung verteilen sich auf 7 fuer das Hoertest-Werkzeug,
14 fuer das EQ-Messwerkzeug und 15 fuer den Cue-Guard.

Wer hier weitermacht, liest zuerst `CLAUDE.md` (Waechter-Pflicht an zwei
Toren) und den fachlich passenden Skill unter `.claude/skills/`.

**Regel, die sich heute mehrfach bewaehrt hat:** jede Zahl vor dem Gebrauch
nachrechnen — auch die eigene, auch die aus einem Subagenten-Bericht. Drei
Befunde dieser Sitzung sind daran gestorben, zwei davon erst nach der
Umsetzung.

## Was heute entstanden ist

### A — Hoertest-Werkzeug (`tools/rate_transitions.py`)

Drei Aenderungen, alle gemessen begruendet:

| Aenderung | Anlass |
|---|---|
| Individuelle Blendenlaenge je Paar statt fester 32 s | die App plant Median 46,1 s (min 17,3, max 64,0, gemessen an 148 Paaren); der Hoertest bewertete eine Laenge, die so nie gebaut wird |
| `crossfade_reserve` misst die richtige Region | die A-Seite prueft jetzt `duration_a - mix_out_a` statt `mix_out_a - PRE_ROLL`; bei fester 32-s-Blende waeren 12 von 148 Clips mitten in die Stille gelaufen, bis 14,7 s |
| Rekordbox-Beatgrid wird durchgereicht | 199 von 200 Tracks tragen `downbeat_confidence 1.0`, das Werkzeug warf es weg und liess den Renderer schaetzen |

Der Beatgrid-Fix ist der einzige, dessen Wirkung gehoert wurde: drei
Probeclips gingen von „alle schlecht" auf 3 / 1 / 4. Das Alignment
korrigiert jetzt auf Taktebene (gemessen 1860 ms bei 129 BPM = exakt ein
Takt) statt auf Bruchteile eines Beats.

### B — Renderer: ein Befund, kein Eingriff

`hpg_core/transition_renderer.py` traegt **nur einen Kommentar**, kein
geaendertes Verhalten. Eine Mitten-Mulde wurde gebaut und wieder
zurueckgebaut.

Die Messung dazu ist neu und bleibt: `tools/eq_verlauf_messen.py` (14 Tests).
Sie misst den Baenderverlauf um Uebergaenge in echten DJ-Mixen, mit
Kontrollgruppe aus demselben Material und nach Mix geclustert.

Ergebnis ueber 275 Uebergaenge aus 13 Mixen:

```
sub     AUC 0.426 [0.380, 0.477]   kein Beleg
mitten  AUC 0.655 [0.601, 0.715]   trennt
hoehen  AUC 0.608 [0.551, 0.665]   trennt
```

Das Mittenband liegt waehrend eines Uebergangs also tiefer als davor und
danach. Aber **gleichmaessig**, nicht als Mulde: die Differenz zwischen
Blendenmitte und Blendenrand enthaelt in allen Laengengruppen die Null
(kurz +0.015 [-0.022, +0.049], mittel +0.022 [-0.007, +0.073], lang
+0.066 [-0.015, +0.134]).

**Warum das erst im zweiten Anlauf sichtbar wurde:** die erste Messung nahm
das Mittenband als 250-2500 Hz und lieferte fuer lange Blenden scheinbar
klare +0.151 [+0.090, +0.205]. Der Renderer trennt aber bei **120** Hz. Die
Oktave 120-250 Hz — Kick-Body und untere Bassline — traegt keine Mulde,
waere aber mit abgesenkt worden. Mit korrigierten Bandgrenzen halbiert sich
der Effekt und verliert die Signifikanz.

Lehre fuer den naechsten Versuch: **Messbaender muessen die Crossover des
Renderers treffen.** Eine gleichmaessige Absenkung waere zwar belegt, sie
ist an den Blendenraendern aber nicht neutral — das ist ein groesserer
Eingriff als eine Mulde und braucht ein eigenes Vorhaben.

### C — Cue-Heuristik umgeht den Intro-Guard

Der einzige echte Eingriff in die Analyse. `CACHE_VERSION` **32 → 33**.

Invariante 5 (Mix-In nie im Intro) war nur in
`calculate_genre_aware_mix_points` gesichert. Die Uebernahme von
Rekordbox-Cues umging sie vollstaendig: bei unbeschrifteten Cues nimmt
`analysis.py` blind `dedup_positions[1]`, also den zweiten Hot Cue — und
DJs setzen den typisch bei rund 30 s, also im Intro. Danach folgte nur
`0 <= in < out <= duration`, kein Intro-Guard.

Gemessen an 231 Tracks: **24 mit Mix-In im fuehrenden Intro**, bis 56,5 s
tief, Median 29,0 s. Herkunft geprueft gegen die Rekordbox-Cues: **alle 24
aus dem Heuristik-Zweig, kein einziger aus einem benannten Cue.**

Nach der Neuanalyse zeigte sich, dass die Wirkung groesser ist: **35 von 231
Tracks** haben einen anderen Mix-In als vorher. Die 11 zusaetzlichen hatten
einen rohen Cue im Intro, den `align_ai_mix_points` per ceil auf die
Intro-Kante hob — im Cache sahen sie deshalb sauber aus (Beispiel
„Firedance": roher Cue 30,3 s bei Intro-Ende 34,0 s, gespeichert 34,0 s).
Die Quantisierung kaschierte das Problem, sie behob es nicht. Wirkungs-
nachweis: Mix-In im fuehrenden Intro **24 -> 0**, Mix-Out bei allen 231
Tracks unveraendert.

Der Guard gilt deshalb nur fuer die Heuristik. Ein benannter Cue
(`MIX IN`, `IN`, `START`) bleibt unangetastet — der Nutzer kennt seinen
Track besser als die Sektionsanalyse. Diese Ausnahme steht als Nachtrag in
`docs/superpowers/specs/2026-03-11-mix-point-intro-outro-guard-design.md`.

Der falsche Wert ging bis dahin ueber
`exporters/rekordbox_xml_exporter.py` als Cue „MIX IN" **zurueck in die
Rekordbox-Datenbank** und in die Bass-Nahtstellenmessung
(`transition_features.py`).

## Was gemessen und verworfen wurde

| Behauptung | Warum sie fiel |
|---|---|
| „Der Renderer fuehrt den EQ-Tausch nicht aus" | er tut es, baendergetrennt nachgemessen: Bass springt am Mittelpunkt hart um, Mitten equal-power, Hoehen asymmetrisch 1/4..3/4 |
| „Die App plant 16 s Overlap" | das ist der Feld-Default von `TransitionPlan`; der Funktionsparameter `default_overlap` steht sogar auf 12 s. Beide greifen im Regelfall nicht — real Median 46,1 s aus `transition_bars` |
| „Du mischst nie im Einbruch" | galt bei 73 Stellen aus einem Set, fiel bei 805 aus 13 Sets in sich zusammen (18,6 % gegen 17,0 % bei Zufall) |
| „Du steigst zu 50 % in einem Drop ein" | die Sektionsstatistik ist mit diesen Mitteln unentscheidbar; Wilson-95 % fuer „drop" reicht von 14 bis 50 %, und die Basisrate liegt schon bei 37 % |
| „HPG steigt eine Phrase zu frueh ein" | zwei schwellenfreie Schaetzer widersprechen sich (-6 s gegen +19 s); die Datenlage traegt keine Aenderung an den Mixpunkten |
| „Die Mitten-Mulde ist belegt" | nur mit falschen Bandgrenzen, siehe B |

Der Mixpunkt-Guard, der urspruenglich beauftragt war, **findet nicht
statt**. Das ist das Ergebnis der Analyse, nicht ihr Scheitern.

## Offene Punkte, nach Wichtigkeit

1. **Neuanalyse nach dem CACHE_VERSION-Bump.** Ohne sie behalten die 24
   Tracks ihren falschen Mix-In und Vorhaben C sieht wirkungslos aus.
   Rekordbox schliessen. Skript mit `__main__`-Guard verwenden, sonst
   stuerzt der Prozesspool ab und faellt still auf einen Worker zurueck.
2. **160 Hoertest-Clips neu rendern**, erst nach der Neuanalyse:
   `python tools/rate_transitions.py prepare --anzahl 160 --out <dir>`.
   Die Bewertungsseite schreibt inzwischen direkt in `bewertung.csv`
   (kleiner lokaler Server, liegt beim Clip-Satz).
3. **Energy Wave: BPM-Naehe eingezogen — erledigt.** Die Strategie
   sortierte ausschliesslich nach `track.energy` und nahm `bpm_tolerance`
   entgegen, ohne sie zu benutzen; gemessen an 80 Tracks mit 93-146 BPM
   waren 63 % der Nachbarpaare unmixbar.

   Jetzt wird innerhalb der naechsten `ENERGY_WAVE_FENSTER = 8` Kandidaten
   einer Seite nach BPM-Naehe gewaehlt. Der Wert ist eine Abwaegung, und die
   Messung dazu steht im Code: freie Wahl haette 14 % unmixbar erreicht,
   aber den Amplitudenaufbau der Welle zerstoert (Korrelation zwischen
   Position und Abstand zur Startenergie faellt von 0,819 auf -0,071). Mit
   Fenster 8 liegt sie bei 0,599 bis 0,742 je nach Pool, unmixbar bei
   23-28 %.

   Die erste Fassung dieser Aenderung waehlte frei ueber die ganze Seite und
   wurde verworfen, nachdem der Amplitudenaufbau gemessen war — die
   urspruengliche Behauptung "die Wellenform bleibt erhalten" galt nur fuer
   Alternation und Spannweite, nicht fuer den Verlauf.

4. **Spiegelbildliche Luecke bei `cue_out` — gemessen, kein Handlungsbedarf.**
   `dedup_positions[-1]` hat am Track-Ende keinen Guard gegen `outro_start`.
   Gemessen an 231 Tracks: **0** haben einen Mix-Out im Outro, Invariante 1
   haelt im Bestand. Die Luecke besteht strukturell weiter, ist aber nicht
   wirksam.
5. **Rekordbox-Track ohne BPM, aber mit Cues** landet im Voll-Path, und
   dort werden Cues kommentarlos verworfen. Vorbestehend.
6. **LUFS-Abschnitt im Renderer-Skill ist veraltet** — er beschreibt den
   Doppelzaehlungs-Defekt als offen, im Code ist er behoben.

## Was der Hoertest noch messen koennte

Der gebaute Satz beantwortet mehr als die vier neuen Faktoren: dieselben
Bewertungen lassen sich gegen **alle acht** rechnen, also auch gegen die
vier ungemessenen, die heute sortieren (`0.44 / 0.28 / 0.28` und
`GENRE_WEIGHT_WITH_DJ_BRAIN = 0.2` mal 36 handgesetzte Genre-Werte).

Der groessere Hebel waere ein **paarweiser Vergleich**: dasselbe Trackpaar
zweimal rendern, mit unterschiedlicher Blendenlaenge oder unterschiedlichem
Einstiegspunkt, und den Nutzer A gegen B stellen. Weil beide Varianten
dieselben Tracks enthalten, kuerzen sich Tonart, BPM, Energie, Genre und
Geschmack vollstaendig heraus — uebrig bleibt genau die variierte Groesse.
Das ist mit ein paar hundert Vergleichen schaetzbar und braucht keine
unabhaengigen Mixe, nur Ohren. Der Nutzer hat es als Ziel benannt
(„ein Modell, das es individuell anwenden kann"), aber bis zur Fertigstellung
des Laufenden zurueckgestellt.

## Datenlage, ehrlich

- 13 DJ-Mixe, 17,1 h, 275 bis 805 Uebergaenge je nach Erkennungsschwelle.
  Fuer Aussagen ueber **diesen** Nutzer reicht das; fuer allgemeine
  Aussagen ueber ein Genre nicht.
- Das Set mit bekannter Trackliste („Studio 54 Schlaflos OffBeat", 33
  Tracks, 26 im Bestand wiedergefunden) ist die einzige Quelle, die
  Ein- und Ausstiegspunkte **im Track** zeigt. Ein Set, ein Abend, ein
  Cluster — eine Zwischen-Set-Varianz laesst sich damit nicht schaetzen.
- Die frueheren Kalibrierungs-Grenzen gelten unveraendert: fuer belastbare
  Gewichte braeuchte es grob 25-30 unabhaengige Mixe je Genre.
  `hpg_core/data/transition_tolerances.json` steht weiter auf `{}`,
  `TRANSITION_FEATURES_ENABLED` weiter auf `False`.
  **Nachtrag 2026-08-23:** seit 2026-08-21 steht `TRANSITION_FEATURES_ENABLED`
  in `hpg_core/config.py` auf `True` (Startwerte, Groove 0.30 verteilt — Memory
  `hpg-scoring-an-2026-08-21`); die Mixpunkt-Kandidaten (Teil 1–4, Handoff
  `docs/HANDOFF-2026-08-22-kandidaten-teil4.md`) bewerten seither lokal am
  Mixpunkt. `transition_tolerances.json` bleibt `{}`.
