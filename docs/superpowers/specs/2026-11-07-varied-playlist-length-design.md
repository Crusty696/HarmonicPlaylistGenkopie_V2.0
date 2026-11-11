# Playlist-Länge und abwechslungsreiche Trackauswahl

## Ziel

Der Nutzer kann für eine Playlist eine gewünschte Trackzahl festlegen. Wenn aus
derselben Sammlung mehrere Playlists erstellt werden, soll HPG jeweils eine
variierte Teilmenge auswählen und Tracks bevorzugen, deren letzter erfolgreicher
Export länger zurückliegt. Gute ältere Tracks sollen dadurch wieder Chancen
erhalten.

## Umfang und Verhalten

- Pro Erzeugungsdurchlauf wird eine Playlist erzeugt. Mehrere Playlists entstehen
  durch erneutes Erzeugen und Exportieren; „fünf“ war ein Variationsbeispiel,
  kein eigener Batch-Auftrag oder Mehrfach-Export.
- Die gewünschte Länge wird in der Bibliotheksansicht eingestellt. `Alle` ist
  Standard und erhält die bisherige Nutzung aller verfügbaren Tracks; Zahlen
  von 1 bis 1000 begrenzen die Playlist auf diese Zahl.
- HPG wählt bis zur gewünschten Zahl ohne Zurücklegen aus den analysierten,
  für die Playlist gültigen Tracks. Das Kandidaten-Gate entspricht mindestens
  dem bestehenden Generator-Gate für endliche, positive BPM-Werte. Reicht die
  Sammlung nicht aus, werden alle gültigen Tracks verwendet und die Anzeige
  nennt die gewünschte und die tatsächlich erreichbare Länge.
- Die Auswahl verbindet Zufallsvariation mit einer Rotation nach dem letzten
  erfolgreichen Export. Tracks, die länger nicht exportiert wurden, erhalten
  eine höhere Auswahlchance; die Historie sperrt keinen Track dauerhaft aus.
- Dieselbe Track-Zusammenstellung wie beim letzten erfolgreichen Export wird
  vermieden, sofern genügend unterschiedliche Track-IDs für eine Alternative
  vorhanden sind.
- Die gewählte HPG-Strategie sortiert anschließend die ausgewählte Teilmenge.
  Playlist, Übergangspläne, Vorschau, Timeline, Qualitätsanzeige und Export
  bleiben Teil desselben `PlaylistGenerationResult`-Vertrags.
- Die zufällige Teilmengenauswahl erfolgt nur bei einer ausdrücklich neuen
  Playlist-Erzeugung. Neubewertung nach Hörtest, manuelles Umsortieren und
  Kandidaten-/Übergangsaktualisierung behalten die aktuelle Track-Mitgliedschaft.
- Die Exporthistorie wird je Track erst aktualisiert, wenn der Exportbericht
  `status == "success"` meldet. Abbruch, Ausnahme und `partial` ändern sie
  nicht. M3U8 und Rekordbox XML verwenden denselben Vertrag. Ein erfolgreicher
  M3U8-Fallback nach fehlendem Rekordbox-Backend zählt als Export.
- Historie und Wunschlänge bleiben lokal auf dem Gerät. Die Wunschlänge wird
  als GUI-Einstellung, die Historie separat im App-Datenverzeichnis gespeichert.

## Ansätze

1. **Auswahl nach Historie variieren, danach Strategie sortieren (gewählt):**
   erfüllt faire Wiederberücksichtigung und Variation, während die bestehende
   Strategie und gemeinsame Übergangsplanung erhalten bleiben.
2. Zuerst alle Tracks sortieren und dann eine Teilmenge ziehen: einfacher, kann
   aber Übergangsgüte und Dramaturgie der ausgewählten Teilmenge verschlechtern.

## Grenzen

- Ein erfolgreicher Export ist das messbare Nutzungssignal. HPG kann nicht
  feststellen, ob der Nutzer die exportierte Playlist tatsächlich gespielt hat.
- Ein `partial`-Export zählt gemäß Nutzerentscheidung nicht, auch wenn eine
  Datei angelegt wurde.
- Nur erfolgreich exportierte Zusammenstellungen zählen für die Rotationsfolge und
  den Vergleich mit der letzten exportierten Track-Zusammenstellung.
- Die bestätigte Fairnessmetrik ist die Rotation nach dem letzten erfolgreichen
  Export, nicht die lebenslange Exportanzahl.
- Eine ungültige oder unlesbare Historie wird nicht stillschweigend
  überschrieben. Die Playlist-Erzeugung kann mit neutraler Zufallsauswahl
  weiterlaufen; persistente Fairness setzt eine reparierbare Historie voraus.
- Die Auswahlhistorie ist keine musikalische Bewertung und darf bestehende
  Paar-Gates oder Qualitätsbedingungen nicht umgehen.
- Die Trackauswahl garantiert nicht, dass jedes Trackpaar einen qualifizierten
  Übergang besitzt; dafür bleiben die vorhandenen HPG-Gates und Ergebnisanzeigen
  maßgeblich.
- Der Umfang beschränkt sich auf Playlist-Erzeugung und Exporthistorie; keine
  Änderungen an Audioanalyse, Cache, Mixpoint-Bewertung oder Exportformaten.

## Umsetzung — abgeglichen 11.11.2026

Die Umsetzung liegt jetzt im Hauptcheckout auf `codex/gesamtrefaktorierung`:
`hpg_core/playlist_selection.py` enthält Auswahl, Historienvalidierung und
atomare Speicherung; `main.py` verbindet UI, neuen Playlistlauf, Ranking-Refresh
und erfolgreiche Exporte. `tests/test_playlist_selection.py` sowie fokussierte
`tests/test_main_workers.py`-Fälle prüfen die Verträge. Die Referenz unter
`E:/AI/.codex/worktrees/playlist-length-rotation/HarmonicPlaylistGenerator_V2.0`
enthält in der aktuellen Dateiansicht keine Quell- oder Plan-Dateien und keine
.git-Verknüpfung; ihr Branch und Commit sind deshalb nicht belegbar und wurden
nicht als Implementierungsquelle verwendet. Die Änderung hat gezielte
`--no-cov`-Tests bestanden; Vollsuite, aktueller Frozen-Build und
Originalmusik-Abnahme bleiben separate Nachweise.
