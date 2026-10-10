# HPG Repository-Dateiinventar und sichere Bereinigung

Statischer GitHub-Quellenstand: 10.10.2026. Die Bestandszahlen beziehen sich
auf `main` vor dieser Bereinigungsrunde (Commit `63ea758a`).
Dies ist ein Inventar, **keine Laufzeit-, Funktions- oder Vollabnahme**.

## Gepruefter Bestand

- 428 versionierte Dateien in 497 Git-Baumeintraegen (Ordner eingeschlossen).
- 59 Gruppen identischer Git-Blobs. Davon 58 bewusste Spiegelpaare
  `.agents/` und `.claude/` fuer unterschiedliche Agenten.
- Die zwei bytegleichen leeren JSON-Grundlagen
  `hpg_core/data/candidate_preferences.json` und
  `hpg_core/data/transition_tolerances.json` haben verschiedene Verbraucher.
  **Nicht deduplizieren**.
- `docs/`: 30 Dateien mit ca. 5,5 MB. Die grossen visuellen Hilfen
  `hpg-trackauswahl-mixpoints.html` und `trackauswahl-mixpoints-systemkarte.png`
  sind nicht allein wegen ihrer Groesse entbehrlich.
- `tests/`: 132 Dateien, `hpg_core/`: 61 Dateien, `tools/`: 31 Dateien;
  diese Zahlen schliessen jeweilige Unterordner ein.
- `memory/`, `docs/audit/`, `docs/superpowers/` und
  `validation/` enthalten historische Nachweise, Anforderungen oder Vorlagen,
  keine bewiesenen Wegwerfdateien.

## Sofortige, begruendete Bereinigung

- `benchmark_rekordbox.py` war ein altes synthetisches Dictionary-Timing.
  Es ersetzte Cache-Eintraege durch Dummy-Strings und lieferte **keinen**
  Nachweis ueber reale Rekordbox-DB- oder Audio-Performance. Aus dem aktiven
  Baum entfernt; im Git-Commitverlauf wiederherstellbar. Die vier Referenzen
  in den beiden gespiegelten Skills sind aktualisiert.
- Zwei ungesammelte Dateien unter `tests/` entfernt:
  `example_cached_fixture_tests.py` hatte einen nicht registrierten `fast`-Marker
  und fachlich inkonsistente Beispielerwartungen; `verify_m3u8_logic.py` lief
  nur als ad-hoc-Skript. Sein Schutz gegen M3U8-Zeileneinschleusung wurde als
  regulaerer Regressionstest in `tests/test_exporters.py` uebernommen.
- `.gitignore` schliesst neu SQLite-WAL/SHM/Journal-Nebendateien und
  kurzlebige `.tmp`/`.temp` aus, damit sie nicht versehentlich versioniert
  werden. Bereits versionierte Dateien und lokale Daten bleiben unangetastet.
- Neues Lesewerkzeug: `tools/repo_inventory.py`. Es liest Git-Metadaten und
  Dateigroessen, zeigt unversionierte/ignorierte Eintraege sowie echte
  Blob-Duplikate. **Keine Loesch- oder Schreibfunktion.**

## Bewusst nicht automatisch geloescht

- Gespiegelte Agenten-Skills/Agenten: eigenstaendige Zielpfade fuer Codex und
  Claude; ihre Gleichheit ist ein gepflegter Vertrag.
- `openclaw-workspace-state.json`: ein kleiner, getrackter Setupmarker.
  Die Wirkung des Entfernens auf lokale Agenten muss vor Migration geklaert
  sein. Keine automatische Loeschung oder Aenderung.
- Alte Designbilder, HTML-Prototypen, Audits, Handoffs, Trainingsbewertungen,
  Benutzer-Memory, Testdaten und Vorlagen: Referenzen und Wiederherstellungswert
  sind vor Loeschung zu bewerten.
- `tools/manual_test.py` verwendet einen historischen Standardordner
  `D:\beatport_tracks_2025-08`. Vor Aenderung den tatsaechlich gewuenschten
  lokalen Standard klaeren; kein Eingriff in Musikordner.
- Cache-/DB-Dateien, Arbeitslogs, nicht getrackte Builds, virtuelle Umgebungen
  und alle Originalmusikquellen: niemals blind mit `git clean`, `rmdir`
  oder `del` entfernen.

## Vollstaendige lokale Bestandsaufnahme auf Windows

GitHub kann **keine lokalen unversionierten oder ignorierten Ordner sehen**.
Ein lokaler Agent kann den folgenden rein lesenden Bericht im bestehenden
Projektordner ausfuehren:

```powershell
.\venv312\Scripts\python.exe tools\repo_inventory.py --json > "$env:TEMP\hpg-repo-inventory.json"
```

Ohne `--json` wird eine kurze Liste ausgegeben. Die Inventar-Funktion
liest keine Audiodateien, loescht nichts und folgt keinen Dateisystemlinks.
Unversionierte/ignorierte Verzeichnisse werden zur Begrenzung des Aufwands
als Verzeichniseintraege gemeldet; ihr innerer Inhalt wird noch nicht geprueft.
Erst nach Sichtung und Sicherung der wertvollen Daten ist eine gezielte
Bereinigung einzelner lokaler Artefakte vertretbar.

## Gueltige Schutzregeln und Testgrenzen

Die fruehere Bereinigung vom 04.10.2026 ist unter
`docs/CLEANUP_2026-10-04.md` und
`docs/cleanup-manifest-2026-10-04.json` dokumentiert.
Sie wird nicht rueckgaengig gemacht. Musik, Rekordbox-Datenbank, Cache,
Benutzerbewertungen und bestehende Sicherungen bleiben unveraendert.
Die GitHub-CI-Gesamtsuite war vor dieser Runde fehlgeschlagen;
Dokumentations- und Dateiorganisationsarbeit wird nicht als gruene
Produktions- oder musikalische Abnahme ausgegeben.
