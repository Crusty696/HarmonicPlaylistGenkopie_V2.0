# HPG: Quellen und dauerhaftes Wissen

Konsolidierung vom 04.10.2026. Diese Datei trennt Nutzervertraege, statisch
gepruefte Codefakten und offene Prueffragen. Sie ist keine Produktabnahme.

## Zuerst lesen

1. Aktueller Auftrag und AGENTS.md bestimmen Scope, Schutz und Nachweise.
2. MEMORY.md enthaelt Produktleitlinie und Quellen des Nutzers.
3. hpg-orientation und der passende Fachskill fuehren zum Code.
4. Fuer Implementierungsbehauptungen den aktuellen Code lesen. Fuer
   Laufzeitbehauptungen den passenden datierten Rohbeleg lesen.
5. docs/HOERTEST_NATIVE_2026-10-04.md ist ein datierter Bericht, kein
   automatisch gueltiger Nachweis fuer jeden spaeteren Build.
6. docs/SESSION_HANDOFF_2026-10-04.md ist der neueste Session-Zwischenstand
   mit aktiver Aufgabenliste und Beleggrenzen; vor Fortsetzung lesen.

Historische Auftraege wie Rendern, Pushen, pausierte Analysen oder /goal
werden niemals durch Lesen einer alten Datei wieder zu aktiven Auftraegen.
Auslagerungen sind im Bereinigungsmanifest dokumentiert. Alte Originaltexte
liegen ausserhalb des Workspace in der lokalen Recovery-Sicherung; deren
Wiederherstellung macht ihre Aussagen nicht zu aktuellen Fakten.

## Erhaltene Nutzervertraege: Soll, kein Implementierungsbeweis

Aus den historischen Handoffs, docs/agent-memory und dem Session-Corpus vom
25.08. wurden folgende Anforderungen erhalten:

- HPG dient der Auswahl passender Trackpaarungen und Playlist-Reihenfolgen.
  Kernarbeit gehoert in die App; Hoertests und Training ergaenzen sie.
- Trackmerkmale individuell analysieren oder auslesen. Paarbewertung nutzt
  lokale Fensterwerte; keine globalen Track-Ersatzmesswerte unterschieben.
  Gemeinsame Gewichte und Toleranzen duerfen zentral sein.
- Musikalische Kompatibilitaet bedeutet nicht numerische Gleichheit.
  Unterschiedliche kompatible Rhythmen sind erlaubt; echte Groove-Konflikte
  sollen sperren. Fehlende erforderliche lokale Messungen nicht durch
  Gewichtsumverteilung kaschieren. Aktuelle ausdrueckliche Ausnahme:
  Unbekannte Vocals allein duerfen kein Paar sperren.
- Vor erneutem Rendern eine nachvollziehbare Uebersicht aller relevanten
  Parameter, Gewichte, Gates und Kriterien vorlegen.
- Individuelle Mixpunkt-Kandidaten statt universeller Cue-Positionen.
  Groove, Rhythmus, Harmonie, Bass/Subbass, Klangfarbe, Lautheit und weitere
  vereinbarte Faktoren beruecksichtigen. Praezision nicht still vereinfachen.
- Tatsaechliche Tempo- und Kick-/Beatphasensynchronitaet pruefen. Das
  Rekordbox-Grid allein beweist sie nicht. Eine Grenze vor dem Outro beweist
  nicht, in welcher realen Tracksektion der Mix-Out liegt.
- Hoertests: hoechstens fuenf Varianten pro Paar. Ein Einzelclip benoetigt
  eine Note, keinen relativen Gewinner. Note 1 darf nie bester Clip sein.
  Auch bei mehreren Clips muss kein bester moeglich bleiben.
- Startgewichte als Startgewichte kennzeichnen. Gescheiterter Holdout ist
  keine Kalibrierfreigabe. Neue Scores muessen keine Reihenfolge aendern.
- Originalmusik bleibt am Quellort, ausschliesslich lesend. Keine Kopien in
  Projekt, Git oder Sicherungen. Bestehende Bewertungen bewahren.
- Implementierung, automatischer Test, nativer Originaltrack-Ablauf und
  musikalische Bewertung sind getrennte Nachweise. EXE-Pfad und SHA-256
  muessen zum getesteten Build passen; frische Analyse und Cache getrennt.
- Unabhaengiger Waechter vor Umsetzung und vor Commit. Skill-Spiegel pflegen.
- Historisch dokumentierte Kommunikationspraeferenz: Antworten mit :-) enden.

Die ausfuehrlichen genehmigten Kandidatenanforderungen bleiben in
`superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md`; der native
Hoertestvertrag bleibt in `superpowers/plans/2026-09-27-hoertest-werkzeuge-in-app.md`.
Die Entscheidungen vom 19.09. und Musikquellen bleiben in MEMORY.md.

## Am 04.10. statisch geprueft

- app_metadata.py: APP_VERSION 3.7.2, MIN_PYTHON 3.12.1.
- caching.py: CACHE_VERSION 46 nach Diagnose-Erweiterung. playlist.py
  registriert acht Strategien. Alte Cache-45-Belege bleiben historisch.
- transition_features.mood_match verarbeitet brightness. Lokale Kandidaten
  verwenden in pair_candidates._teil_timbre avg_mids_lokal/avg_highs_lokal
  und in _teil_mood lokale Helligkeit. Die alte pauschale Aussage, diese
  Merkmale seien nur Diagnosewerte, darf nicht fortgeschrieben werden.
- rekordbox_phrases.phrases_from_anlz verarbeitet PSSI. Alte Aussage
  PSSI ungenutzt ist keine aktuelle Implementierungsbeschreibung.
- tests/test_release_metadata.py liest PRODUCTION_STATUS.md. Dieser Pfad
  bleibt erhalten, statt durch Bereinigung einen Testvertrag zu brechen.
- Zwei Dateien mit Endung .exe im Projektroot enthielten Textprotokolle,
  keine Programme. Historische Analyseausgaben und AI-Timeouts darin
  belegen weder den aktuellen Build noch einen vollstaendigen App-Ablauf.

Diese Fakten wurden durch Quellenlesen festgestellt, nicht durch einen neuen
Produktlauf. Exakte Entfernungen und Originalhashes: cleanup-manifest-2026-10-04.json.

## Offene Fragen und Grenzen

- Historische Berichte nennen Bugs und Tests. Ihre Entfernung erklaert
  keinen Bug fuer behoben. Wiederaufnahme nur mit aktueller Reproduktion.
- Historische Aussagen zur Mindestlaufzeit von zwei Phrasen widersprechen
  einander. Dies wird nicht durch Dokumentationsbereinigung entschieden:
  aktuellen Auftrag, Fachvertrag und betroffenen Code gemeinsam pruefen.
- Fehlen einer Datei namens test_ai_engine.py beweist keine fehlende
  AI-Testabdeckung. Abdeckung waere am konkreten Verhalten zu untersuchen.
- Historische Modellbenchmarks, Hardwareempfehlungen, Serverzustaende,
  Trackzahlen, Git-Hashes und Testzahlen sind keine heutigen Messungen.
- Fast-Path-Vergleiche mit Rekordbox-Metadaten beweisen keine unabhaengige
  Eigenanalyse-Genauigkeit. Doppelte Basenames/abweichende Pfade koennen
  absichtlich ohne Zuordnung bleiben; tatsaechliche Records pruefen.
- Alte Kritik an einem 30-Paare-Hoertestsatz ist eine historische Warnung:
  vorhandene Bewertungen nicht ungeprueft als Trainingsgrundlage behandeln.
- Transformationsstabilitaet eines Kickdetektors beweist keine Kick-Ground-
  Truth. Vorhandene validation-Rohbelege bleiben erhalten; keine Neuabnahme.
- Der zurueckgezogene VERITAS-Lauf vom 03.09. bleibt mitsamt UNGUELTIG.md
  als historische Evidenz erhalten. Seine Befunde sind keine bestaetigten
  aktuellen Fehler und duerfen nicht als solche synchronisiert werden.
- Generierte No-update-Erinnerungen liefern keine neue Fachinformation.
  Beschraenkter Sessionzugriff (sessions.visibility=tree) beweist keine
  vollstaendige Chatabdeckung. Automatisch erzeugte Reflexionen sind keine
  primaere Quelle und duerfen diese Regeln nicht ueberschreiben.
