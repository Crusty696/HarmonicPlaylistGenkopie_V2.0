# HPG – Entwicklungs-, Status- und Lagebericht

**Stand:** 09.11.2026  
**Produkt:** Harmonic Playlist Generator (HPG), App-Version 3.7.2  
**Zweck:** Bestandsaufnahme des gesamten App-Projekts nach Abgleich mit GitHub. Dieser Bericht ist eine datierte Lageeinschätzung, keine Produktfreigabe.

## Kurzstatus

HPG ist eine weit entwickelte Windows-Desktopanwendung zur Vorbereitung von DJ-Sets. Der aktuelle Code deckt Analyse, Playlist-Erzeugung, Übergangsplanung, Hörvorschau und Export ab. Der jüngste dokumentierte Volltest ist grün. Ein frischer 26-Track-App-Lauf veröffentlichte eine Playlist und 19 Übergänge.

Die technische Entwicklung ist weiter als die Produktabnahme: Für sechs von 25 Nachbargrenzen gab es in diesem Lauf keinen ausführbaren Übergang. Eine vollständige musikalische Bewertung der Playlist fehlt. Die finale EXE wurde gezielt geprüft, aber nicht in einem vollständigen 26-Track-EXE-App-Lauf abgenommen. HPG ist damit **technisch weit fortgeschritten, aber noch nicht als vollständig musikalisch und auslieferungsseitig abgenommen belegt**.

## GitHub-Abgleich

Abgleich durch `git fetch origin` am 09.11.2026; zusätzlich wurden Remote-Referenzen, jüngste Commitstände und offene Pull Requests geprüft.

| Referenz | Stand | Einordnung |
|---|---|---|
| Lokaler Branch `codex/gesamtrefaktorierung` | `d82e9728` – 07.11.2026 | Aktueller Berichtsbasis-Commit |
| GitHub `origin/codex/gesamtrefaktorierung` | `d82e9728` | Identisch mit dem lokalen Commit; der aktive GitHub-Zweig ist nicht weiter als dieser lokale Commit |
| GitHub `main` | `95a7edbe` – 26.10.2026 | Der aktive Entwicklungszweig enthält drei Commits, die nicht in `main` liegen; `main` enthält keinen Commit, der im aktiven Zweig fehlt |
| Offene Pull Requests | keine gefunden | Der aktive Entwicklungsstand ist nicht über einen offenen PR in `main` integriert |
| Übrige Remote-Zweige | letzter beobachteter Stand spätestens 26.10.2026; mehrere Zweige aus August | Kein erkennbarer neuerer App-Stand als `d82e9728` |

GitHub ist also **nicht weiter als der lokale Commitstand des aktiven Zweigs**. GitHub-`main` ist älter. Die GitHub-Historie ersetzt nicht die Prüfung des lokalen Arbeitsbaums: Dort liegen erhebliche uncommittete Dokumentänderungen und Löschungen sowie eine neue Playlist-Längen-Spezifikation. Diese Änderungen sind nicht Bestandteil von `d82e9728` und wurden nicht als GitHub-Code ausgegeben.

Der lokale Zweig `codex/playlist-length-rotation` zeigt auf `baf34a09`. Der zugehörige Worktree ist in der Git-Verwaltung als nicht mehr erreichbar/prunable markiert; seine Dateien und Tests ließen sich daher nicht als aktuelle Umsetzung prüfen. Dieser Commit enthält Paketierungsänderungen, aber keine erkennbare Implementierung der Playlist-Rotation. Die Rotation ist in diesem Bericht deshalb **Design/Arbeitsabsicht, keine bestätigte Produktfunktion**.

## Produktumfang und technischer Aufbau

HPG ist ein Set-Vorbereitungswerkzeug, kein automatischer DJ-Player. Der dokumentierte Funktionsfluss umfasst:

- Musikbibliothek und Rekordbox-Metadaten einlesen; Audioanalyse mit Cache-Wiederverwendung oder frischer Analyse.
- BPM, Tonart, Audioeigenschaften, native Beats und Phrasen ermitteln und trackbezogene Mixpunkt-Kandidaten ableiten.
- Eine von acht Playlist-Strategien anwenden und Übergänge samt gemeinsamem `PlaylistGenerationResult`/`TransitionPlan` bereitstellen.
- Übergänge rendern und als Vorschau abspielen; Playlists als M3U8 oder Rekordbox-XML exportieren.
- Optionale lokale LLM-Metadaten sowie Stem- und Embedding-Analyse anbieten.

Die Codebasis ist in `hpg_core/` stärker modularisiert; `main.py` bindet weiterhin die zentrale PyQt6-Oberfläche und Dienste zusammen. Die App-Version in `hpg_core/app_metadata.py` ist 3.7.2. Das Vorhandensein eines Moduls oder einer unterstützten Codec-Factory belegt für sich allein noch keinen erfolgreichen Lauf mit jeder Datei und Konfiguration.

## Fortschritt und Nachweisstand

### Automatisierte Prüfungen

Der jüngste im Umsetzungsprotokoll dokumentierte Volltest nach der EXE-Worker-Laufzeitkorrektur bestand am 07.11.2026 mit **6.706 Tests**, **80,99 % Coverage** und Exitcode 0. Der SHA-gebundene Quellstand blieb während dieses Laufs unverändert. Ein vorheriger Volltest auf einem etwas früheren Stand hatte 6.704 Tests und 81,17 % Coverage bestanden. Die Zahlen gehören zu verschiedenen Läufen und werden nicht vermischt.

Das ist ein starker automatisierter Regressionsnachweis für den damaligen Quellstand. Er beweist weder fehlerfreie Bedienung in jeder Windows-Umgebung noch musikalische Qualität oder eine vollständige EXE-Abnahme.

### Analyse und echte Tracks

Der dokumentierte 26-Track-App-Lauf vom 07.11. analysierte 26 Originaltracks frisch und veröffentlichte eine Playlist mit 26 Tracks. Für 19 von 25 Nachbarpaaren lagen ausführbare Übergangspläne vor. Die sechs übrigen Grenzen wurden diagnostiziert: Drei überschritten die gesetzte 2-BPM-Grenze, zwei scheiterten an lokalen Qualitäts-/Beatfolgenbedingungen, und eine Kandidatenmenge ergab keinen mit der Nachbarkette vereinbaren Plan. Das belegt sichtbare Grenzen bei dieser Sammlung; es belegt nicht automatisch einen Softwarefehler.

Ein gesonderter Cache-Nachweis belegt Wiederverwendung für einen Track. Ein anderer dokumentierter Reparaturablauf endete mit 26 Cachetreffern. Ein einzelner gemeinsamer Lauf, der alle 26 Tracks frisch analysiert, die Playlist erzeugt und danach für alle 26 denselben Cache-Reuse belegt, ist nicht dokumentiert.

### Übergangsvorschau und Hörbewertung

Für einen gerenderten Übergang liegt ein positives Nutzerurteil vor. Eine weitere technisch valide Vorschau ist dokumentiert, aber ihr menschliches Hörurteil stand im letzten Protokoll noch aus. Eine unabhängige musikalische Referenz und eine Hörabnahme der gesamten Playlist fehlen. Der positive Einzelclip ist keine Freigabe des gesamten Sets.

Für W und Deep Sky wurde in beiden Richtungen kein Paarplan oberhalb des bestehenden Mindest-Scores gefunden; daher gab es dafür keine zulässige Vorschau. Die 2-BPM-Grenze und bestehende Qualitätsgates bleiben bestehen. Es gibt keine belegte Grundlage, sie zu lockern.

### Oberfläche und Arbeitsablauf

Automatische Prüfungen decken Ergebnisverträge, Reorder, UI-Texte und Layoutregressionen ab. Eine isolierte Qt-Ansicht zeigte sieben Tracks und vier von sechs Übergängen. Ein sichtbarer aktueller Nutzerablauf mit frischer Analyse, Playlist-Veröffentlichung, Übergangsvorschau, manueller Bedienung und Export in der finalen Kombination ist nicht vollständig belegt. Die UI-Arbeit ist daher automatisiert gut abgesichert, aber nicht als komplette sichtbare Produktabnahme abgeschlossen.

### KI- und Hardwarepfade

Für optionale LLM-Metadaten und lokale Persistenz bestehen dokumentierte Teilnachweise. Der ONNX/DirectML-Pfad wählte auf dem Prüfgerät die RX 7800 XT; ein lokaler Modell-Smoke lieferte gültige Ausgaben. Provider-Auswahl und Stichproben belegen nicht, dass sämtliche Modelloperationen ausschließlich auf der GPU liefen.

Die separate native Rekordbox-Beatpipeline besitzt keinen belegten Adaptervertrag zur dGPU. Der Nutzer hatte am 07.11. festgelegt, die iGPU frei zu halten; ein weiterer nativer 26-Track-Lauf wurde deshalb nicht gestartet. Dieser Pfad ist nicht mit dem ONNX/DirectML-Gerätefix gleichzusetzen.

### Windows-Auslieferung

Ein konkreter EXE-Worker-Absturz mit einer veralteten PyQt6-VC-Laufzeitkopie wurde eingegrenzt und durch Entfernen dieser gebündelten Kopien aus `HPG.spec` behoben. Die finale EXE wurde gebaut; synthetischer Smoke und gezielter Originaltrack-Worker liefen mit Exit 0. Die EXE wurde **nicht** in einem vollständigen 26-Track-App-Lauf bis zu Playlist, sichtbaren Übergängen, Vorschau und Export abgenommen. Außerdem belegt der Test auf diesem PC mit installierter aktueller VC-Laufzeit nicht die Startfähigkeit auf einem System ohne diese Laufzeit.

## Neue Playlist-Längen- und Rotationsidee

Die lokale Spezifikation vom 07.11. beschreibt eine wählbare Playlist-Länge und variierende Track-Teilmengen nach letztem erfolgreichem Export. Der gewünschte Vertrag lässt die Strategie, Übergangspläne, Vorschau und Export weiterhin dasselbe Playlist-Ergebnis verwenden. Die Spezifikation ist uncommittet und der beschriebene Implementierungs-Worktree aktuell nicht erreichbar. Die Funktion ist daher **noch nicht als integriert, getestet oder abgenommen einzustufen**.

## Lageeinschätzung

| Dimension | Status | Begründung |
|---|---|---|
| Codebasis / Architektur | weit fortgeschritten | Analyse, Scoring, UI-Worker und Renderer sind modularisiert; gemeinsamer Ergebnisvertrag ist vorhanden |
| Automatisierte Regression | gut belegt | jüngster dokumentierter Volltest grün; Ergebnis gilt genau für den protokollierten Stand |
| Frische Originaltrack-Analyse | teilweise belegt | 26/26 frisch in der App; Paar-/Übergangsdeckung bei 19/25 |
| Musikalische Qualität | offen | keine unabhängigen Referenzen und keine vollständige Playlist-Hörabnahme |
| UI-Endabnahme | teilweise belegt | automatische und isolierte UI-Nachweise, kein vollständiger manueller End-to-End-Ablauf |
| Cache | teilweise belegt | einzelne Reuse- und 26-Treffer-Nachweise aus getrennten Abläufen |
| KI/GPU | teilweise belegt | lokale Teilpfade funktionieren; keine vollständige GPU-Ausführungsgarantie |
| EXE / Release | teilweise belegt | finaler Build und gezielter Worker-Nachweis; vollständiger 26-Track-EXE-Ablauf und Fremdsystemtest offen |
| Playlist-Rotation | Entwurf | lokale Spezifikation; Implementierung im nicht erreichbaren Worktree nicht bestätigt |

## Sinnvolle nächste Schritte

1. Playlist-Rotations-Worktree wieder auffinden oder aus einer gültigen Referenz rekonstruieren; Änderungen, Tests und GitHub-Status prüfen, bevor die Funktion als umgesetzt geführt wird.
2. Einen vollständigen sichtbaren Ablauf mit der finalen EXE durchführen: Analyse, veröffentlichte Playlist, nachvollziehbare Übergangspläne, Vorschau und Export. Dabei die iGPU-Vorgabe beachten.
3. Die verbleibenden Grenzen der 26er-Sammlung mit Hörurteil bzw. unabhängigen Referenzen bewerten, ohne bestehende Tempo- und Qualitätsgates aufzuweichen.
4. Cache-Reuse, UI-Endablauf und EXE-Lauf jeweils als getrennte Nachweise führen; ihren Erfolg nicht aus Teilbelegen ableiten.

## Quellen und Grenzen dieses Berichts

- GitHub-Remote: `https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0`; aktiver Branch und `main` wurden am 09.11.2026 abgeglichen.
- [Umsetzungs- und Nachweisprotokoll](superpowers/plans/2026-10-30-gesamtrefaktorierung.md), insbesondere der zusammengeführte Stand vom 07.11.2026.
- [Projektwissen und Nutzerverträge](PROJECT_KNOWLEDGE.md).
- [Playlist-Längen-Spezifikation](superpowers/specs/2026-11-07-varied-playlist-length-design.md), lokal und uncommittet.
- [Architektur und Datenfluss](ARCHITEKTUR.md) sowie [README](../README.md).

Für diesen Bericht wurden keine Tests, Audioanalysen oder Builds erneut ausgeführt. Testzahlen, App-Läufe und Hörergebnisse sind datierte Nachweise aus dem Umsetzungsprotokoll; sie wurden hier nicht neu reproduziert. Der lokale Arbeitsbaum enthält weitere nicht committete Änderungen und Löschungen, die nicht als GitHub-Änderungen interpretiert wurden.
