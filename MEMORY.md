# MEMORY.md

Quellenwegweiser: [docs/PROJECT_KNOWLEDGE.md](docs/PROJECT_KNOWLEDGE.md).
Historische Arbeitsstaende und automatische Promotions wurden extrahiert.
Die folgenden Nutzerleitlinien sind Anforderungen, keine Implementierungsabnahme.

## Dauerhafte Projektfakten

- OpenClaw-Agent: `hpg`; Workspace ist dieses Repository. Die Coding-Runtime
  muss bei Bedarf direkt geprueft werden; alte Modellangaben sind kein Iststand.
- Vor Facharbeit `hpg-orientation`, danach den passenden Skill aus
  `.agents/skills/` laden. Die Rollen liegen in `.agents/agents/`.
- Pflichtinterpreter: `venv312\Scripts\python.exe` mit Python 3.12.
  Python 3.13+ ist wegen numba nicht zulaessig.
- Abschlussbeleg:
  `venv312\Scripts\python.exe -m pytest tests/ --tb=short -q`.
  Die Suite verwendet bereits `-n auto`; keine parallelen vollen Testlaeufe.
- Geschuetzt sind Cache-/DB-/Lock-/Coverage-Dateien, reale Musikbibliotheken,
  Rekordbox-Daten und vorhandene `Claude-Autopilot-*`-Artefakte.

## Produktleitlinie des Nutzers (2026-09-27)

- HPG soll grosse Musiksammlungen analysieren und die bestmoegliche Playlist-
  Reihenfolge fuer die vom Nutzer ausgewaehlten Tracks finden. Ziel ist, nicht
  alle moeglichen Paare und Reihenfolgen manuell testen zu muessen.
- Die Suche und Bewertung soll passende Track-Paarungen und Reihenfolgen anhand
  der verfuegbaren Analysewerte finden: Klang, Harmonie, Groove, Rhythmus,
  Energie, BPM und weitere relevante Audio-/Track-Merkmale. Sie soll neue
  musikalische Verbindungen und Kombinationen aus alter und neuer Musik
  auffindbar machen. Uebergaenge und Mixpunkte sind Teil dieser Bewertung und
  Playlist-Erstellung, nicht der alleinige Produktzweck.
- Vorhandene Hoertest-/Trainingswerkzeuge sind Zusatzwege, um parallel Daten
  und Nutzerbewertungen zu sammeln. Sie duerfen keine notwendige
  Kernfunktion aus der App auslagern; zentrale Such-, Bewertungs- und
  Playlist-Arbeit muss in der App verfuegbar sein.
- Ollama-/LM-Studio-Anbindung ist bereits vorbereitet. Der Nutzer sucht noch
  ein lokal betreibbares LLM, das Audio/Musik wirklich hoeren und verstehen
  kann. Ein solches Audio-LLM ist eine moegliche Ergaenzung, nicht der
  vorausgesetzte Kern der Playlist-Suche. Vor Aussagen zum Ist-Stand Code und
  GUI pruefen; Soll-Leitlinie nie als implementierte Faehigkeit ausgeben.

## Reale Musikquellen fuer kuenftige HPG-Arbeit

Vom Nutzer am 2026-09-27 ausdruecklich zum dauerhaften Merken genannt;
alle drei Verzeichnisse waren an diesem Tag vorhanden:

- Techno / Beatport: `F:\neue techno sammlung nur beatport musik`
- Psy-Trance und Progressive / Beatport:
  `F:\neue Psy-Trance, Progressive nur Beatport musik`
- Melodic-Techno / Analysebestand:
  `F:\HPG-Melodic-Techno-v45-Analyse-2026-09-14`
- DJ-Set-Aufnahmen und Audio-Clips:
  `E:\02_Musik_&_Medien\Musik_&_Audio\Audio_Clips`

Bei spaeteren Tests mit echtem Audio zuerst diese Quellen heranziehen und
die Verfuegbarkeit erneut pruefen. Der DJ-Set-Ordner enthielt am 27.09.2026
25 Dateien, darunter 12 WAV-, 7 MP3- und 2 M4A-Dateien; mehrere Aufnahmen
sind gross (bis mehrere GB). Daher Metadaten zuerst und Audio nur gezielt
streamen. Originaldateien unveraendert lassen;
Versuchsergebnisse separat speichern. Die Pfade bezeichnen vom Nutzer
genanntes reales Musikmaterial, keine unabhaengig annotierten Kick-Onset-
Referenzen. Vor einer solchen Verwendung die vorhandenen Inhalte pruefen.

## Technische Invarianten

- Cache-Lookup vor der Audioanalyse. Rekordbox-Fast-Path und Vollanalyse bei
  relevanten Aenderungen gemeinsam betrachten.
- Mixpunkte: `0 <= mix_in < mix_out <= duration`; Phrasenraster und mindestens
  den aktuellen Fachvertrag beachten. Historische Aussagen zur Mindestlaufzeit
  widersprechen einander; siehe docs/PROJECT_KNOWLEDGE.md.
  `MIX_POINT_UNSET = -1.0`; `0.0` ist gueltig.
- Aenderungen am Analyse-Output erfordern eine begruendete Pruefung der
  `CACHE_VERSION`.
- `main.py` enthaelt die PyQt6-GUI; UI-Updates nur im Main-Thread.

## Betriebswissen

- Vor und nach nichttrivialen Aenderungen prueft `hpg-waechter` unabhaengig
  und schreibgeschuetzt. Nur mit `DURCHGEWUNKEN` abschliessen; Auflagen zuerst
  erledigen.
- In Memory gehoeren nur stabile, wiederverwendbare Fakten, Entscheidungen und
  bewaehrte Reparaturwege. Keine Zugangsdaten, personenbezogenen Details oder
  fluechtigen Debug-Ausgaben speichern.

## Dauerhafte fachliche Entscheidungen (David, 2026-09-19)

Historisch dokumentierter Nutzervertrag. Die konkreten DSP-Werte und
Wirkungsbehauptungen unten wurden in dieser Bereinigung nicht neu getestet.
Sie sind kein Beweis fuer den aktuellen Renderer.

- **Uebergangsausfuehrung, EQ-Pegel und konstante Lautstaerke**:
  Uebergaenge muessen nicht nur technisch (Timing, Beatgrid, Phasen) stimmen, sondern in der Ausfuehrung zwingend harmonisch und ausgeglichen klingen. Die Pegel der EQ-Baender (Bass, Mitten, Hoehen) und die Gesamtlautstaerke muessen durch den gesamten Mix vollstaendig angeglichen sein.
  1. **Mixpunkte individuell und dynamisch setzen**: Ein DJ mixt NICHT starr Intro auf Outro — das wuerde die Energie und Tanzflaechen-Stimmung toeten. Intro und Outro werden zu 90 % ignoriert/uebersprungen; Mixpunkte in und out sind von Track zu Track immer individuell dynamisch zu suchen und festzulegen (Phrasen- und Energie-basiert davor/danach).
  2. **Volle Laenge messen und analysieren**: Der gesamte Mix ueber die volle Laenge (Vorlauf, Crossfade, Nachlauf) muss lueckenlos gemessen und analysiert werden. Keine Normalisierung an isolierten 8s-Schnipseln (die in Intros/Breakdowns liegen koennen), sondern am vollstaendigen aktiven Audiomaterial. Kontinuierliche Lautheitsglaettung (_level_mix_loudness) mit erweitertem Regelbereich (+-8.0 dB) und Silence-Gate bei -32 dBFS haelt den gesamten Verlauf homogen auf -14.0 LUFS.
  3. **Ausschliesslich 3-Band-EQ-Swap fuer Psytrance**: Fuer Psytrance gilt ausnahmslos der 3-Band-EQ-Swap (`pro_eq_swap`) — keine Filter Rides (die bei 800 Hz den Bass toeten) und keine Echo Outs (die 60 % Lautstaerkeeinbruch erzeugen). Im 3-Band-EQ-Swap muessen Bass, Mitten und Hoehen harmonisch und pegeltreu angeglichen uebergehen.
  4. **Server-Caching**: Audio-Clips werden mit Cache-Control no-cache ausgeliefert, damit der Browser nie veraltete Audio-Dateien abspielt.
  - Diese Regel gilt ausnahmslos fuer alle Hoerproben und Produktions-Renders.
