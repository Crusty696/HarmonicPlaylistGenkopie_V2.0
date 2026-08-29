# Codex-Uebergabe: lokaler Paarvertrag und neue Hoerproben

Stand: 2026-08-25, Python 3.12.10

## Auftrag und verbindlicher Nutzervertrag

David verlangt fuer die App und die Hoerproben:

- Kein globaler oder pauschaler Ersatzwert fuer Groove, Bass, Klangfarbe,
  Stimmung, Lautheit, Energie, Harmonie, Struktur oder andere Mixfaktoren.
- Jeder Track und jedes konkrete Mix-Out-/Mix-In-Fenster traegt seine eigenen
  analysierten oder ausgelesenen Messwerte.
- Track A und B muessen nicht gleich sein. Die Richtung, Ergaenzung und
  musikalische Vertraeglichkeit der beiden lokalen Fenster wird bewertet.
- Fehlende lokale Messungen sind "nicht bewertbar". Andere Faktoren duerfen
  sie nicht durch Gewichts-Renormierung retten.
- Groove-Konflikte muessen ein Paar sperren. Unterschiedliche, aber
  kompatible Rhythmen sind ausdruecklich erlaubt.
- Fuer Hoerproben werden Tempo und echte Kick-/Taktschlaege der beiden Audios
  phasengenau synchronisiert. Das Rekordbox-Beatgrid ist dabei nur Hilfsmittel.
- Pro Trackpaar maximal fuenf Clipversionen.
- Ein Einzelclip braucht nur eine Note, keinen "besten" Clip. Note 1 kann nie
  "bester" sein. Bei mehreren Clips muss "kein bester" moeglich sein.

Gemeinsame Gewichte, Toleranzen und Mindestwerte sind Regeln und duerfen
zentral sein. Sie sind keine Messwerte eines Tracks.

## Umgesetzter Code

### Lokale Paarqualitaet

- `hpg_core/config.py`: gemeinsame Mindestregeln
  `PAAR_MIN_LOCAL_SCORE = 0.70` und `PAAR_MIN_LOCAL_GROOVE = 0.50`.
- `hpg_core/pair_candidates.py`: `pair_quality_reasons` prueft alle zehn
  aus den lokalen Teilwertfunktionen gelieferten Werte auf endliche
  Messbarkeit. `rank_pair_candidates` gibt nur vollwertig lokale Paare zurueck.
- `hpg_core/playlist.py`: `calculate_enhanced_compatibility` verwendet nur
  lokale PairCandidates. Kein Ganztrack-Feature-Fallback und kein KI-Bonus
  auf den lokalen Paarwert. Ohne lokalen Kandidaten: Score 0, Kandidat `None`,
  lokale Teilwerte `None`.
- `transition_metrics_from_candidate` ist die zentrale Abbildung des aktiven
  lokalen Kandidaten auf sichtbare `TransitionMetrics`.
- Gerichtete manuelle `MIX IN`-/`MIX OUT`-Cues bleiben in Kandidatenbildung
  und Paarbildung als priorisierte Quelle mit ihrer Provenienz erhalten. Sie
  durchlaufen ausnahmslos dieselben Intro-/Outro-, Gitter-, Mindestfenster-,
  Coverage- und Blend-Gates wie alle anderen Quellen. Ein ungueltiger Cue
  verwirft keinen gueltigen Punkt der Gegenseite.

### App-Strategien, Kette und Anzeige

- Genau eine der acht Strategien erzeugt zuerst die Trackreihenfolge. Strategien
  mit lokaler Uebergangszielfunktion duerfen dabei den vollstaendigen
  `PairCandidate`-Objective samt Lookahead verwenden; die Strategie bleibt aber
  allein fuer die Tracksortierung verantwortlich.
- Nach der festen Reihenfolge entstehen genau `N - 1` gerichtete Boundaries.
  Fehlende lokale Kandidaten entfernen keinen Track, sondern bleiben als
  ausdrueckliche Kante `UNGEPLANT` sichtbar.
- Die begrenzte Result-DP waehlt ueber diese festen Boundaries eine konsistente
  Folge aus hoechstens zwoelf Kandidaten-Snapshots plus `UNGEPLANT` je Kante.
  Nur ein gewaehlter Kandidat erzeugt einen ausfuehrbaren `TransitionPlan`.
- Empfehlungen, Qualitaetsanzeige, aktiver Mixpoint und Export/Preview-Vertrag
  verwenden danach denselben immutable `PlaylistGenerationResult` und dessen
  aktiven `TransitionPlan`. `energy_direction` ist Teil des eingefrorenen
  Scoring-Kontexts.
- `calculate_playlist_quality` berechnet Harmonie, Energie und BPM aus den
  lokalen aktiven Fenstern, nicht aus Ganztrack-Differenzen.
- Result und Empfehlungen enthalten immer genau eine Boundary je Nachbarpaar.
  Eine ungueltige Kante bleibt mit echtem Paarindex und ohne Plan als
  `UNGEPLANT` erhalten; andere Kanten bleiben davon unberuehrt.
- Die Result-DP bleibt auch fuer grosse Playlists begrenzt: Pro Boundary gehen
  hoechstens zwoelf Kandidaten plus `UNGEPLANT` ein; die Trackreihenfolge wird
  dabei nicht erneut durchsucht oder veraendert.
- Rekordbox-Beatgrid, Downbeat und Phrasen werden je Analyselauf aus demselben
  ANLZ-Snapshot gelesen.

### Hoerproben und Bewertung

- `tools/rate_transitions.py` baut und qualifiziert zuerst dieselben lokalen
  PairCandidates wie die App. Erst danach erfolgt Maximin-Auswahl auf lokalen
  Teilwerten. Kein fest erzwungener Uebergangstyp; der aktive Kandidat/App-
  Vertrag bestimmt den Typ. Maximal fuenf Versionen je Paar.
- `tools/hoertest_server.py`: Einzelclip ohne Siegerknopf/-pflicht; Multi-Clip
  mit explizitem "kein bester"; Note 1 loescht eine bestehende Siegerwahl und
  kann serverseitig nicht als Sieger gesetzt werden.
- Statistik/Schema-Lernen wertet Sieger nur bei mindestens zwei Clips und
  genau einer echten Siegerwahl aus. Einzelclips und "kein bester" bleiben
  reine Notenbeobachtungen.

## Hoerproben-Iststand

Der erste, inzwischen fachlich verworfene Satz liegt unter:

`C:\Users\david\Music\HPG-Psytrance-Kandidaten-30Paare-2026-08-25`

Er enthaelt 30 Paare und 47 WAVs. Diese Clips wurden vor dem vollstaendigen
lokalen Vertrag aus nur 231 Cache-Tracks erzeugt und duerfen nicht als Beleg
fuer die neue Auswahl gelten. Mehrere Paare hatten nachweislich schwachen
lokalen Groove oder Struktur. Nicht ueberschreiben; fuer den neuen Lauf einen
neuen Ausgabeordner verwenden.

Naechster Produkt-Schritt: die komplette erreichbare Psytrance-Library (der
Nutzer erwartet mehr als 2000 Tracks) mit dem bestehenden Benutzer-Cache nur
read-only einlesen, lokal qualifizieren, 30 neue Paare mit je maximal fuenf
Versionen rendern und die Audio-Synchronitaet ueber den gesamten Uebergang
pruefen. Keine Rekordbox-Datei, Musikdatei oder Benutzer-Cache-Datei aendern.

## Verifikation

- Interpreter: `venv312\Scripts\python.exe`, Python 3.12.10.
- Syntaxpruefung der geaenderten Produktionsmodule: bestanden.
- `git diff --check` fuer den getrackten Diff: bestanden (nur bekannte
  LF/CRLF-Hinweise). Neue ungetrackte Pflichtartefakte werden vor dem spaeteren
  gezielten Staging separat und danach nochmals im staged Diff geprueft.
- Abschlusslauf:
  `venv312\Scripts\python.exe -m pytest tests\ --tb=short -q`
- Aktueller staerkerer Abschlusslauf vom 2026-08-27 mit allen Markern,
  explizitem isoliertem Windows-Basetemp und sichtbarer Warnungsauswertung:
  3568 bestanden, 0 Warnungen, Coverage 86.00 Prozent, Exitcode 0. Ein erster
  inhaltlich ebenfalls bis 100 Prozent gruener Versuch scheiterte erst beim
  pytest-eigenen Aufraeumen des globalen Temp-Symlinks mit `WinError 5`; der
  technisch geaenderte Wiederholungslauf mit explizitem Basetemp beseitigte
  genau diese Infrastrukturursache.
- Historischer Volltest-Snapshot vom 2026-08-25 vor den nachfolgenden
  GUI-/E2E-/Kandidatensatz-Auditor-Aenderungen: 2035 bestanden, 25 Warnungen,
  Coverage 81.65 Prozent, Exitcode 0. Dieser Wert ist nur Historie und wurde
  durch den aktuellen 3568er Beleg ersetzt.
- Aktueller Code-Iststand vom 2026-08-27: `CACHE_VERSION = 44`. Der historische
  Bump von 36 auf 37 erzwang die korrigierte `None`-Semantik; 37 auf 38
  invalidierte alte Analysezeilen fuer BPM-lose Rekordbox-Metadaten. Version 39
  erzwingt den strikten Vertrag aus 60 Track- und je 28 Kandidatenfeldern,
  tief losgeloeste Snapshots mit feldabhaengiger NaN/Inf-Semantik sowie
  dauerabhaengige PSSI-Memoisierung mit der echten endlichen Dateidauer. Version
  40 macht die framegenaue Audiodauer auch im Rekordbox-Fast-Path autoritativ
  und filtert Cues vor Override, Kandidatenbildung und Persistenz gegen diese
  physische Dateigrenze. Version 41 korrigiert 3/4- und 4/3-BPM-Faktoren nur
  fuer bekannte kanonische ID3-Genres und liest fehlende AIFF-Metadaten aus
  rohen Frames. Version 42 entfernt die letzte manuelle Cue-Ausnahme auf
  Track-, Kandidaten- und Paarebene; alte v41-Zeilen koennen grenzverletzende
  Mixpunkte oder Kandidaten enthalten und werden nicht weiterverwendet.
  Version 43 validiert mehrdeutige Keys, Beatgrids, PSSI-Grenzen und
  KI-Metadaten strikt. Version 44 invalidiert alte Bar-Fallback-Mixpunkte,
  wenn kein gueltiges Phrasenraster existiert.
- Der damalige unabhaengige Waechterdurchgang fand keine funktionalen Blocker
  im damaligen Produktionscode-Stand. Die statische Pruefung bestaetigte insbesondere den
  lokalen Messvertrag, Sparse-Indizes, die begrenzte Kettensuche und den
  gemeinsamen ANLZ-Snapshot.

### Laufzeit- und Crash-Haertung am 2026-08-25

- Finale Playlist-Erzeugung, Kandidatenwahl und Drag-and-Drop-Reorder sind
  gegen fruehe und spaete Exceptions atomar abgesichert. Alter Playlist-,
  Quality-, Empfehlungs- und View-Stand wird restauriert; ein gescheiterter
  Persistenz-Rollback wird ehrlich gemeldet und verlaesst den Qt-Slot nicht.
- `e2e_check.py` besitzt jetzt echtes `--help`, `--audio-dir` und ein positiv
  validiertes `--max-fixtures`. Es sucht begrenzt nach einer vollwertigen
  lokalen gerichteten Kante. Fehlt sie im Fixture-Limit, endet es eindeutig
  mit Exitcode 3 statt den korrekten Paarvertrag als Playlist-Crash zu melden.
- Gezielt nach diesen Aenderungen: 55 GUI-Crash-/Worker-Tests und 6
  E2E-Werkzeugtests bestanden (61 insgesamt). Der aktuelle 3568er Volllauf
  deckt diese Aenderungen inzwischen ab. Bibliotheksanalyse, Render-/Audioaudit
  und subjektiver Hoertest bleiben davon getrennte Laufzeitbelege.

### Vollstaendige Library und Cache-Iststand

- Read-only lokalisiert:
  `E:\david\VARIANTE_2\MUSIK-SAMMLUNG\AIFF-WAV_MASTERS\PSYTRANCE`
  mit 3666 Audio-Mastern. Daneben liegen 907 MP3-Versionen unter
  `MP3_VERSIONS\PSYTRANCE`; diese koennen Duplikate der Master sein.
- Der am 2026-08-25 gepruefte Benutzer-Cache `hpg_cache_v37.db` enthielt 0 Track-Zeilen.
  Er wurde durch einen versehentlichen, sofort abgebrochenen E2E-Start neu
  angelegt; `cache` und `cache_quarantine` wurden danach immutable/read-only
  mit jeweils 0 Zeilen geprueft. Musik und Rekordbox blieben unveraendert.
- Der erste Coverage-Abschlusslauf erzeugte trotz isoliertem TEMP die
  ignorierte Datei `.coverage` im Repository (69632 Bytes). Bis zu einer
  expliziten Nutzerfreigabe werden weder diese Datei noch der leere v37-Cache
  oder dessen Lock geloescht. Weitere Laeufe setzen `COVERAGE_FILE` explizit
  auf einen Pfad ausserhalb des Worktrees.
- Der groesste alte Cache `hpg_cache_v34.db` enthaelt nur 232 Zeilen und ist
  fuer den neuen lokalen v37-Vertrag nicht verwendbar. Die v30-v34-Caches
  wurden nur immutable/read-only vermessen.
- `tools/analyze_library.py` ist der neue abgesicherte, wiederaufnehmbare
  Vollbestand-Treiber. Er validiert vor jedem HPG-Import den exakten Bestand,
  vier Worker als Obergrenze, Symlinks/Junctions, Discovery-Fehler und alle
  Schreibpfade. Der reale Guard fand exakt 3666 Dateien; ein absichtlich
  falsches Soll von 3665 endete mit Exitcode 2, ohne Ordner, Cache oder Log
  anzulegen.
- `tools/rate_transitions.py::sammle_kandidaten` nutzt nun einen gerichteten
  BPM-Bisect-Index fuer direkte sowie Half-/Double-Time-Fenster. Reihenfolge,
  Gates und Scoring bleiben gleich; ein Test mit 1000 Tracks reduziert die
  Ranking-Aufrufe von bis zu 1.000.000 auf 1000 lokale Paare.
- Historisch wurde der isolierte 3666-Track-Lauf am 2026-08-25 um 22:06 Uhr mit
  vier Workern gestartet. Arbeitscache
  `C:\Users\david\AppData\Local\HPG-Work\hpg_cache_v37_psytrance_3666_20260825.db`
  und Fortschrittslog
  `C:\Users\david\AppData\Local\HPG-Work\psytrance_3666_20260825.progress.log`
  liegen ausschliesslich im getrennten Arbeitsbereich. Dieser v37-Lauf wurde
  ohne erfolgreichen Abschlussbeleg abgebrochen und durch den damaligen
  v39-Vertrag ersetzt; seine Dateien bleiben historische Arbeitsartefakte.
- Am 2026-08-26 um 16:27 Uhr wurde ein isolierter v39-Lauf mit
  vier Workern und exakt 3666 erwarteten Masterdateien gestartet. Arbeitscache:
  `C:\Users\david\AppData\Local\HPG-Work\hpg_cache_v39_psytrance_3666_20260826.db`.
  Fortschrittslog:
  `C:\Users\david\AppData\Local\HPG-Work\psytrance_3666_v39_20260826.progress.log`.
  Er wurde nach 112 Analyseergebnissen und 110 persistierten Tracks kontrolliert
  gestoppt: Zwei musikalisch gueltige Rekordbox-Cues lagen nur hinter der auf
  volle Sekunden gekuerzten Rekordbox-Dauer, nicht hinter dem echten Audioende.
  Der daraus abgeleitete v40-Fix wurde mit
  `venv312\Scripts\python.exe -m pytest tests\test_mix_candidates.py tests\test_analyze_track.py tests\test_caching.py --no-cov --tb=short -q`
  belegt: 330 Tests bestanden, Exitcode 0. Zusaetzlich bestanden beide realen
  Problemtracks einen isolierten Analyse-, Validierungs-, Cache-Write- und
  Cache-Read-Roundtrip. Das unabhaengige Waechterurteil lautet
  `DURCHGEWUNKEN`. Der v39-Cache bleibt historisch und wird nicht fortgesetzt
  oder umbenannt.
- **HISTORISCH/BEENDET:** Am 2026-08-26 um 17:07 Uhr wurde der korrigierte
  v40-Lauf mit vier Workern und exakt 3666 erwarteten Masterdateien gestartet.
  Arbeitscache:
  `C:\Users\david\AppData\Local\HPG-Work\hpg_cache_v40_psytrance_3666_20260826.db`.
  Fortschrittslog:
  `C:\Users\david\AppData\Local\HPG-Work\psytrance_3666_v40_20260826.progress.log`.
  Der erste Prozess verwendete unbeabsichtigt den CLI-Standard von 60 Sekunden
  je Track. Nach einem normalen Track-Timeout und dem dadurch seriell
  gewordenen Safe-Mode wurde nur dieser Prozessbaum kontrolliert beendet. Seit
  Ab 17:13 Uhr wurde derselbe v40-Cache mit vier Workern und
  `--task-timeout 900` wiederaufgenommen; Prozessausgaben liegen in
  `psytrance_3666_v40_20260826_resume1.stdout.log` und
  `psytrance_3666_v40_20260826_resume1.stderr.log`. Bereits persistierte Zeilen
  werden ausschliesslich ueber Cache-Key und DB-Validierung wiederverwendet.
  Laufende Meldungen `Analysiert (Persistenz ungeprueft)` belegen nur ein
  erzeugtes Trackobjekt. Weder Fortschrittslog noch Track-Rueckgabe zaehlen als
  Speichererfolg. Operative Wahrheit ist ausschliesslich der abschliessende
  read-only Abgleich von Cache-Version, Cache-Key, Pfad und validiertem JSON mit
  dem finalen Status `Persistiert: x/y Analyseerfolge`.
  Der Lauf wurde spaeter beendet und wird nicht fortgesetzt. Ein nachfolgender
  v41-Lauf wurde nach mindestens 24 analysierten Tracks kontrolliert beendet,
  als die noch vorhandene manuelle Intro-/Outro-Cue-Ausnahme nachgewiesen
  wurde. Seine DB und Logs bleiben unveraenderte historische Artefakte. Erst
  Die historischen v42- und v43-Laeufe werden nicht fortgesetzt. Ein spaeter
  ausdruecklich freigegebener Bibliothekslauf muss mit einem neuen isolierten
  v44-Arbeitscache beginnen. Erfolgsschwelle bleibt 3661, weil fuenf bekannte
  Continuous-Mix-Dateien das 500-MB-Limit ueberschreiten. Ein v44-Endergebnis
  oder Exitcode ist noch nicht belegt.
- Ein realer, isolierter E2E-Lauf analysierte 12 echte Psytrance-Tracks und
  endete korrekt mit Exitcode 3: innerhalb dieses kleinen deterministischen
  Satzes keine vollwertige lokale gerichtete Kante. 998 rohe
  Kandidatenkombinationen wurden read-only diagnostiziert; keine bestand alle
  lokalen Messbarkeits-Gates, vor allem wegen fehlender Vocal-, Struktur- und
  Groove-Messbarkeit. Daraus wurde kein Default und keine Gate-Lockerung
  abgeleitet.

## Worktree und Schutzgrenzen

Der Worktree ist umfangreich geaendert. Die Aenderungen stammen aus der
fortlaufenden Beatgrid-/Rendering-/Hoerprobenarbeit dieser Sitzung und aus dem
lokalen Paarvertrag. Vor Commit den Diff fachlich gruppieren. Niemals die
ungetrackten OpenClaw-Workspace-Dateien, `memory/`, `Claude-Autopilot-*`,
Cache-/DB-/Lock-/Coverage-Dateien stagen. Es wurde in diesem letzten Schritt
weder committed noch gepusht.

## Zusammenfassung des relevanten Chats

1. David fragte, ob alle Playlistparameter wirklich vollwertig wirken. Die
   ehrliche Pruefung ergab reale Implementierung, aber auch bedingte/fehlende
   Einfluesse und Beatgrid-Probleme.
2. Fuer neue Hoerproben stellte David klar: Takt/Kicks von A und B muessen
   zeitgleich uebereinanderliegen. Rekordbox-Beatgrids sollen fuer diesen Lauf
   nicht korrigiert werden; Synchronitaet wird am Audio hergestellt.
3. David verlangte zuerst 30 Psytrance-Paare, maximal fuenf Versionen je Paar.
   Ein erster Lauf erzeugte 47 Clips, nutzte aber nur 231 Cache-Tracks.
4. David bewertete viele Paarungen als rhythmisch/grooveseitig unbrauchbar und
   schlechter als vorher. Die Codeanalyse bestaetigte seine Kritik: Der
   Hoertest hatte vor der lokalen Kandidatenbildung Ganztrackmerkmale und
   Maximin benutzt; ausserdem war ein Uebergangstyp fest erzwungen.
5. David erklaerte verbindlich, dass kein Faktor einen globalen Wert haben
   darf. Jeder Track und jedes Mixfenster besitzt eigene Messwerte; A/B sollen
   zusammen harmonieren, nicht identisch sein.
6. David beanstandete die Bewertungslogik: Bei nur einer Version und Note 1
   darf kein "bester" verlangt werden; bei mehreren schlechten Versionen muss
   "kein bester" moeglich sein. Das ist jetzt umgesetzt.
7. David verlangte die gleiche lokale Logik in der gesamten App, nicht nur im
   Hoertestwerkzeug. Die zentrale App-Auswahl, alle acht Strategien, aktive
   Kandidatenkette, Anzeige und Hoertest wurden deshalb auf denselben Vertrag
   gestellt.
8. Nach Abschluss soll Codex nahtlos uebernehmen und diese Arbeit als seinen
   aktuellen Stand behandeln. Diese Datei ist die verbindliche Uebergabe.

## Noch offen fuer Codex

1. Die auftragsbezogenen Code- und Dokumentaenderungen mit aktuellem
   Volltest- und Waechterbeleg committen und pushen.
2. Die Bibliotheksanalyse bleibt auf ausdrueckliche Nutzeranweisung pausiert.
   Ein spaeterer Lauf muss einen neuen getrennten v44-Arbeitscache verwenden;
   Benutzer-Cache, Rekordbox und Musik bleiben read-only.
3. Neuen Ausgabeordner anlegen und 30 neue Psytrance-Paare aus der vollstaendig
   erreichbaren Library rendern, maximal fuenf lokale Versionen je Paar.
4. Den neuen Satz zwingend mit
   `tools/audit_candidate_set.py --set-dir <Ausgabeordner> --cache <Arbeitscache> --report <separater Report>`
   pruefen. Nur Exitcode 0 belegt die 1:1-Konsistenz von CSV/JSON/WAV, striktes
   deterministisches PCM-Rerendering, drei Kick-Lags je Clip sowie einen
   unveraenderten, WAL-freien Cache.
5. Einen echten lokalen Audio-E2E-Pfad mit vollwertiger gerichteter Kante und
   erfolgreichem Render (Exitcode 0) belegen.
6. Clipzahl, Paarzahl, lokale Teilwert-Minima, Synchronitaetspruefung,
   Auditreport und Ausgabeordner dokumentieren. Alte 47 Clips nicht als neuen
   Lauf melden.

## Codex-Uebernahme bestaetigt

Ein frischer Codex-Agent hat diese Datei und den damaligen Worktree read-only
geprueft und die Arbeit als Ausgangsstand uebernommen. Die historischen v37-,
v39-, v40-, partiellen v41-, v42- und v43-Laeufe werden nicht weiterverwendet.
Die Bibliotheksanalyse ist auf Nutzeranweisung pausiert. Vor einem spaeteren
v44-Lauf bleiben der neue Render-/Audioaudit und ein echter Render-E2E-Beleg
offen; fuer den Code-Abschluss sind aktueller Volllauf und Abschlusswaechter
verbindlich.
