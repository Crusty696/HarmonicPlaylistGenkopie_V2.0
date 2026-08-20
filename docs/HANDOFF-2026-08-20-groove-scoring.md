# Handoff — Groove-Scoring, Stand 2026-08-20

Branch `feature/groove-scoring`, 47 Commits ueber `main`. Suite **1658 gruen**,
Coverage-Gate gehalten. Arbeitsbaum sauber.

Wer hier weitermacht, liest zuerst `CLAUDE.md` (Waechter-Pflicht) und den
fachlich passenden Agenten unter `.agents/agents/`.

## Worum es ging

Die Playlist-Reihenfolge entstand aus vier Faktoren: Camelot-Harmonik, BPM,
Energie, Genre. Der Nutzer — DJ, 2480 Tracks in Rekordbox — nannte vier Dinge,
die dabei fehlen: Groove, Bassdruck, Klangfarbe, Stimmung. Ziel war, diese
Faktoren zu ergaenzen und ihre Gewichte **aus echten DJ-Mixen zu lernen**
statt sie zu raten.

## Was gebaut wurde

| Datei | Zweck |
|---|---|
| `hpg_core/groove.py` | Onset-Huellkurve auf einen Takt falten (16 Slots, am `first_downbeat` verankert), Synkopierung, Bass-Kennwerte |
| `hpg_core/transition_features.py` | vier paarweise Vergleiche, je `float` oder `None` |
| `hpg_core/tolerances.py` | Gewichte als Daten laden: Defaults, mitgeliefertes JSON, Nutzer-Override |
| `hpg_core/mix_analysis.py` | Uebergaenge in Mixen finden, AUC, Cluster-Bootstrap, Gewichtsableitung |
| `tools/mix_mining.py` | Kalibrierung aus DJ-Mixen |
| `tools/rate_transitions.py` | Hoertest: Clips erzeugen, Bewertungen fitten |

Dazu: fuenf Track-Felder, beide Analysepfade verdrahtet, Score-Integration
hinter `TRANSITION_FEATURES_ENABLED`, GUI-Regler, Tooltip-Aufschluesselung.

**Der Schalter steht auf `False`.** Bei `False` ist das Scoring bit-identisch
zum Stand davor; die Analyse rechnet die Groove-Felder trotzdem mit (bewusst,
damit ein spaeteres Einschalten keine Neuanalyse braucht).

## Was die Messungen ergaben

**Die Kalibrierung ist gescheitert, und das ist ein Ergebnis.** Nach Korrektur
von vier methodischen Fehlern — Negativpaare nur noch innerhalb eines Mixes,
Groove phasenrichtig und rotationsinvariant, Unsicherheit ueber Mixe
geclustert, Budget an die untere Konfidenzgrenze gekoppelt — blieb:

| Genre | Uebergaenge | gelerntes Budget |
|---|---|---|
| Psytrance | 99 aus 6 eigenen Sets | 0,0121 |
| Techno | 101 aus 8 eigenen Sets | **0,0000** |

Die bindende Grenze ist die **Zahl unabhaengiger Mixe** (6-8), nicht die Zahl
der Uebergaenge. Fuer belastbare Aussagen braeuchte es grob 25-30 je Genre.
`hpg_core/data/transition_tolerances.json` steht deshalb auf `{}` — es gelten
die ungemessenen Defaults.

**Nebenbefund, der wichtiger ist als das Vorhaben selbst:** die Zahlen, die
die Reihenfolge heute tatsaechlich bestimmen, sind nie gemessen worden —
`0.44 / 0.28 / 0.28` in der Gewichtssumme und `GENRE_WEIGHT_WITH_DJ_BRAIN =
0.2`, multipliziert mit 36 handgesetzten Genre-Kompatibilitaetswerten. Fast
alle *gemessenen* Zahlen des Repos liegen dagegen hinter dem ausgeschalteten
Schalter.

## Der Fehler, den das Ohr gefunden hat

Beim ersten Clip des Hoertests hoerte der Nutzer sofort, dass an falschen
Stellen gemischt wird. Ursache: Sektionsgrenzen kommen gerundet aus der
Analyse; lag eine Grenze 3 ms hinter einem Rasterpunkt, schob `ceil` den
Mix-In eine **ganze Phrase** weiter — 27 s bei 16-Bar-Phrasen, vom Intro-Ende
mitten in den Drop. Zwei volle Tracks liefen dann 32 s uebereinander.

Kein Test war rot. Behoben ueber `QUANTIZE_TOLERANCE_SEC` in `models.py`
(Commit `839ba41`).

## Offene Punkte, nach Wichtigkeit

1. **Neuanalyse mit CACHE_VERSION 32.** Der Cache traegt noch v31; die
   Sektions-Schluessel `sub_energy`/`bass_punch` und die auf Beat-Sektionen
   eingeschraenkte Groove-Faltung fehlen darin. Rund 40 Tracks/min bei
   funktionierendem Pool, geschlossenes Rekordbox empfohlen.
   Skript: `scratchpad/teilanalyse.py` (mit `__main__`-Guard, ohne den
   stuerzt der Pool ab und faellt auf einen Worker zurueck).
2. **160 Hoertest-Clips neu rendern.** Die vorhandenen unter
   `C:\Users\david\Music\HPG-Hoertest\` stammen von vor dem Rundungsfix.
   `python tools/rate_transitions.py prepare --anzahl 160 --out <dir>`.
   Die Bewertungsseite `bewerten.html` liegt dort und funktioniert weiter.
3. **Mix-In liegt bei 57 von 200 Tracks in einer Intro-Sektion** — entgegen
   Invariante 5. Vorbestehend, nicht von diesem Vorhaben verursacht, aber
   ungeprueft. Betrifft die Funktion, die der Nutzer als die wichtigste
   bezeichnet: wo gemischt wird.
4. **„Nur eine Einblendung, kein richtiger Mix."** Der Nutzer hoerte das beim
   ersten Clip; der Uebergangstyp war `pro_eq_swap`. Ob der Renderer den
   EQ-Tausch wirklich ausfuehrt oder auf eine Lautstaerkeblende zurueckfaellt,
   ist **nicht geprueft**. Wenn er es nicht tut, ist das fuer den Klang
   wichtiger als jede Gewichtung.
5. **Spec meldet zwei gebaute Mechanismen als „nicht umgesetzt"** —
   `docs/superpowers/specs/2026-08-19-*`, Abschnitte 5.1 und 5.3. Seit
   `c4bba95` und `0c48b21` erledigt.
6. **Energy Wave und Context Flow** sortieren ueber reine Harmonik, waehrend
   die Anzeige einen Acht-Faktoren-Score zeigt. Bei Context Flow ist das
   Absicht (Kommentar im Code). Produktentscheidung, keine technische.

## Wie es weitergehen koennte

Der Hoertest ist das schaerfste vorhandene Werkzeug, und er kann mehr als
urspruenglich gedacht: dieselben Bewertungen lassen sich gegen **alle acht**
Faktoren rechnen, also auch gegen die vier ungemessenen, die heute sortieren.
Das braucht keine zusaetzliche Arbeit vom Nutzer, nur einen zweiten Durchlauf
derselben Zahlen.

Faustregel aus `tools/rate_transitions.py`: 10 Ereignisse je Merkmal **und
Klasse**. Bei vier Merkmalen also rund 40 „gut" und 40 „nicht gut".

## Was diese Sitzung gelehrt hat

Sechs Fehler sind entstanden, an denen **kein Test rot wurde**: drei erfundene
Code-Referenzen in einem Plan, eine Toleranzkonstante um Faktor drei daneben,
eine Schleifenvariable statt der zusammengefuehrten Liste, eine
zurueckgestellte und dann vergessene Aufgabe, ausgelieferte Gewichte trotz
rotem Freigabe-Gate, und ein von einem Subagenten behaupteter Bug, den es
nicht gab.

Daraus entstand `hpg-waechter` — ein Pruefer ohne Schreibwerkzeug, an zwei
Toren, wobei das **vor** der Umsetzung das wichtigere ist. Bei seinem ersten
Einsatz hat er eine Aenderung des Autors zurueckgewiesen und dabei mit Zahlen
belegt, dass sowohl die neue als auch die alte Variante falsch war.
