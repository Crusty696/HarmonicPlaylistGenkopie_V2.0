# Handoff 2026-08-21 — Blenden-Fix und Hoertest

Stand: `main` und `feature/groove-scoring` beide auf `1ebaa96`, gepusht,
Arbeitsbaum sauber. Suite 1740 gruen.

## Was heute passiert ist

### Zwei Fehler an der Blende gefunden und behoben (`1ebaa96`)

**Die Blende lief ins Outro von A.** Der Mix-OUT liegt per dj_brain-Guard
immer vor dem Outro — die Blende laeuft aber vorwaerts ab diesem Punkt
(`transition_renderer.py:159-160`, `:322-324`), und ihre Laenge kam aus dem
Genre-Mittel, das den Punkt gar nicht kennt. Gemessen an 160 gerenderten
Uebergaengen: **109 liefen ins Outro**, Median 17.3 s, max 48.5 s. Die
Intro-Seite war in **0 von 280** Faellen verletzt — der Intro-Guard greift.

`_outro_overlap_limit` (`hpg_core/playlist.py`) begrenzt die Blende jetzt auf
den Kopfraum zwischen Mix-Out und Outro-Beginn, abgerundet auf ganze TAKTE.
Nicht auf Phrasen: simuliert warf Phrasen-Rundung die Streuung wieder weg
(49 von 120 Psy-Clips auf demselben Wert). Unter `MIN_TRANSITION_BARS` (8)
Kopfraum wird nicht gekuerzt — dort waere die Alternative ein harter Schnitt.

Wirkung: Outro-Verletzungen 109 -> 18 (160er) und 47 -> 4 (Psy),
Blendenlaengen bei Psytrance 25 -> 31 verschiedene Werte, haeufigster
Einzelwert 41x -> 25x.

**Die Blende wurde rueckwaerts gerechnet.** `playlist.py` setzte
`fade_out_start = mix_out - overlap`, `fade_out_end = mix_out`; der Renderer
blendet vorwaerts. Die Anzeige lag um die volle Blendenlaenge daneben und
behauptete, die Blende ende am Mix-Out — **deshalb fiel der erste Fehler nie
auf.** Jetzt beginnt sie am Mix-Out und endet bei `mix_out + overlap`,
begrenzt auf die Trackdauer. Zwei Tests, die die alte Konvention festhielten,
wurden nach Ruecksprache auf `fade_out_start` umgestellt.

### Hoertest-Werkzeug (`1a427f5`)

`tools/hoertest_server.py` — lokale Bewertungsseite, nur Standardbibliothek,
127.0.0.1. Noten gehen per Klick direkt nach `bewertung.csv`. Bereichsanfragen
(206) und blockweises Ausliefern, sonst bricht der Player beim Spulen ab.
Zeigt Tempo, Genre, Camelot und einen Balken mit Beginn/Ende der Blende —
bewusst NICHT die Faktor-Punktzahlen, deren Gewicht der Test schaetzen soll.

`prepare --nur-genre NAME` zieht nur Paare, bei denen beide Tracks dieses
Genre tragen.

Aufruf:
```
.\venv312\Scripts\python.exe tools/hoertest_server.py --dir C:\Users\david\Music\HPG-Psytrance --port 8766
.\venv312\Scripts\python.exe tools/hoertest_server.py --dir C:\Users\david\Music\HPG-Hoertest   --port 8765
```

## Daten

| Satz | Ort | Clips | bewertet |
|---|---|---|---|
| Mischsatz | `Music\HPG-Hoertest` | 160 | 84 |
| Psytrance | `Music\HPG-Psytrance` | 120 (nach Fix neu gerendert) | 4 |

Sicherung aller CSVs: `Music\HPG-Hoertest-Sicherung\` (Stand 2026-08-21).
Die 21 Psy-Noten von vor dem Outro-Fix liegen dort als
`bewertung_vor_outrofix_20260821_0103.csv` — sie gehoeren zu Clips mit
anderen Blendenlaengen und duerfen nicht in die Auswertung.

## Was die 84 Noten zeigen (nicht ueberinterpretieren: 11 Positivfaelle)

Verteilung 45/17/11/9/2 — nur 13 % gut.

| Faktor | rho | p |
|---|---|---|
| groove | +0.53 | <0.001 |
| bpm | +0.28 | 0.009 |
| Blendenlaenge | -0.08 | 0.46 |
| mood, bass, timbre, energy | ~0 | n.s. |

Groove haelt stand, bereinigt um BPM-Differenz und Genre-Gleichheit (+0.46).
Der BPM-Faktor bricht bereinigt zusammen (-0.06).

Kontext: gleiches Genre 2.39 gegen Wechsel 1.58. Melodic Techno 36
Uebergaenge, Mittel 1.31, **kein einziger gut**. Ab 5-6 BPM Abstand
praktisch nur Ausschuss. Einser gegen Gute: groove 0.61/0.94,
Genrewechsel 76 %/36 %.

**Pegel-Einbrueche erklaeren die Einser NICHT.** Gemessen (400-ms-Fenster,
Mix gegen den leiseren der beiden Raender): 45 % der Clips werden im Mix
leiser, ein Bassloch unter -3 dB haben 71 % der Einser — aber auch 10 von 11
Guten. Tiefere Basloecher gehoeren eher zu den besseren Uebergaengen
(Median -20.9 dB gegen -9.7 dB, p=0.048). Kein Ausschlusskriterium daraus
bauen: eine Schwelle von 2 dB haette 4 der 11 guten verworfen.

## Naechster Schritt (mit dem Nutzer abgestimmt)

**Psy-Satz zu Ende hoeren, dann gewichten.** Nicht: Blendenlaengen-Varianten
rendern. Begruendung: die Blendenlaenge korreliert als einzige gepruefte
Groesse nicht mit den Noten (rho -0.08), und der Engpass ist die Hoerzeit des
Nutzers. Die vier nie gemessenen Zahlen (0.44/0.28/0.28 in playlist.py,
`GENRE_WEIGHT_WITH_DJ_BRAIN = 0.2`) bestimmen die Reihenfolge — das ist die
Kernfunktion.

Vor dem Anpassen: **einen Teil der Noten nach TRACKS getrennt zuruecklegen**
(nicht nach Clips — sonst tauchen dieselben Tracks in beiden Haelften auf).
Sonst bestaetigt die Pruefung ihre eigene Anpassung.

Datenlage-Regel im Code (`datenlage_urteil`): 10 Faelle je Merkmal **und
Klasse**. Vier neue Faktoren -> 40 gute noetig; alle acht -> 80.

## Offen

1. **Set-Timeline widerspricht der neuen Konvention.**
   `_calculate_timeline_entries` (`playlist.py:2344`, `:2359`) rechnet
   `playing_duration = dauer - overlap`, modelliert den Overlap also weiter am
   Track-ENDE. Die Set-Gesamtlaenge in der GUI ist dadurch vermutlich falsch.
   Eigener Anlass, eigener Fix.
2. **Blendenlaenge individualisieren — Versuch gescheitert, dokumentiert.**
   Ein Entwurf "Blende endet an der naechsten Sektionsgrenze" wurde simuliert
   und **verworfen**: er macht die Laenge einheitlicher statt individueller
   (Psy 19 statt 31 verschiedene Werte, haeufigster 51x statt 25x), weil
   Sektionsgrenzen oft kurz hinter dem Mixpunkt liegen und der Wert dann auf
   die Genre-Untergrenze geklemmt wird. Lehre: jede Regel klemmt am Ende auf
   dieselben Grenzen. Ohne Hoerdaten dazu ist jede Formel geraten.
3. `_rms_normalize` normalisiert `seg_a` (Vorlauf + Blende) und `seg_b`
   getrennt auf -14 dBRMS. Duennt A in der Blende aus, hebt die Normalisierung
   das ganze Segment — der Vorlauf wird lauter, die Blende relativ leiser.
   Waere ein Artefakt des Hoertest-Clips, nicht der App. Ungeprueft.
4. 64 analysierte Tracks sind in keinem Hoertest-Satz verwendet
   (Progressive 21, Psytrance 21, Melodic Techno 7, Techno 6, Trance 4,
   Tech House 3, Deep House 2). Von 2476 Tracks der Rekordbox-Sammlung sind
   231 analysiert; der Rest waere grob 4 h Rechenzeit.
5. Der LUFS-Doppelzaehlungs-Defekt aus dem Skill `hpg-transition-render` ist
   im Code bereits behoben (AUDIT-FIX 2026-08-14, `_measure_segment_loudness`).
   Der Skilltext ist an der Stelle veraltet.
