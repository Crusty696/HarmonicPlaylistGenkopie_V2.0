# Gesamtrefaktorierung Implementation Plan

## Fortsetzung 07.11.2026: 26-Track-App-Lauf nach iGPU-Korrektur

Der isolierte App-Lauf `%TEMP%/hpg-full-fresh-app-fixed-20261107` wurde mit
Originaltracks aus `F:/beatport_tracks_2026-04` abgeschlossen. `events.json`
belegt 26 von 26 Tracks mit `analysis_origin=fresh`, den Zustand `success`
und eine in der App veröffentlichte Playlist mit 26 Tracks. Der Snapshot
`result-success-20261107.json` enthält eine Qualität von 60,88 % sowie 19
ausführbare Übergangspläne für 25 Nachbarpaare. `tracks-success-20261107.json`
meldet für alle 26 Tracks `ok` bei Stems, Embedding, nativen Beats und nativen
Phrasen. Die Stem-Ergebnisse fordern DirectML an; `provider_verified=false`
bleibt ausdrücklich bestehen. Die App zeigte eine geladene und laufende
Hörvorschau für Übergang 9 (Involucra zu Sonic Arps). Eine menschliche
musikalische Bewertung dieser Vorschau liegt noch nicht vor.

Die DirectML-Adapterliste ordnet DXGI 0 der iGPU und DXGI 1 der RX 7800 XT zu.
`gpu-engine-sample.json` erfasst während des App-Laufs den HPG-Modellkindprozess
auf der RX-7800-XT-LUID `0x12bd9`; in diesen Stichproben lag keine iGPU-Engine
über der Messschwelle. Die Windows-Zählerwerte selbst waren unplausibel hoch
und werden nicht als Auslastungsprozente gewertet. Eine lückenlose
Ressourcenmessung oder unabhängige musikalische Abnahme ist daraus nicht
ableitbar. Installierte Rekordbox-Bibliotheken, Originalmusik und Produktivcache
wurden nicht verändert.

Ein Cache-Reuse-Nachweis nach der Adapterkorrektur liegt unter
`%TEMP%/hpg-cache-reuse-after-igpu-20261107/report.json`: Der im frischen
App-Lauf analysierte Originaltrack `E-Clip - Umbral` wurde in eine isolierte
SQLite-Datenbank übernommen. `analysis.analyze_track(..., cache_policy='reuse')`
lieferte anschließend `analysis_origin=cache` in 2,34 s; Stem und Embedding
blieben `ok`. Größe, Änderungs- und Erstellungszeit der Originaldatei blieben
gleich. Der erste Prüfversuch verglich auch die Zugriffszeit und endete deshalb
mit einem Fehler im Prüfskript; die korrigierte Prüfung ist der gültige Beleg.
Dies prüft die Wiederverwendung eines Originaltracks im Analysekern, nicht
einen zweiten vollständigen App-Lauf mit allen 26 Tracks.

Die sechs ungeplanten Nachbarpaare wurden mit denselben gespeicherten
Trackdaten und dem eingefrorenen Scoring-Kontext reproduziert (nullbasierte
Grenzindizes): 15, 19
und 24 überschreiten die eingestellte 2-BPM-Grenze; 17 und 18 scheitern an
lokalen Qualitäts- bzw. Beatfolge-Anforderungen. Index 14 hat acht lokale
Kandidaten, aber keinen mit der Nachbarkette vereinbaren Plan. Das sind
erklärte Freigabegrenzen, kein Nachweis für einen Defekt. Keine Grenzwerte
oder Erwartungen wurden deshalb geändert. Die musikalische Bewertung und
ein EXE-Lauf der exakt zugeordneten Fassung bleiben eigene, offene Nachweise.

## Fortsetzung 07.11.2026: DirectML-Geraetewahl

Die lesende DXGI-Abfrage `%TEMP%/hpg-dxgi-adapters-20261107.py` ergab
Adapter 0 `AMD Radeon(TM) Graphics` (iGPU, LUID 0x11324), Adapter 1
`AMD Radeon RX 7800 XT` (16 GiB, LUID 0x12bd9). Laut offizieller
ONNX-Runtime-DirectML-Dokumentation ist `device_id` dieser DXGI-Index.
Der bisherige ONNX-Standard `device_id=0` adressierte auf diesem Rechner
also die iGPU, sofern die DirectML-Session aktiviert war. Ein einzelner
GPU-Engine-Momentwert ohne HPG-Last widerlegt die Geraetewahl nicht.

Der eigene isolierte 26-Track-`fresh`-App-Lauf unter
`%TEMP%/hpg-full-fresh-app-20261107` wurde nach vier analysierten Tracks
ueber das App-Kommando `close` kooperativ beendet; App- und Poolprozesse
sind beendet. Dieser Lauf ist **abgebrochen**, kein voller App-Nachweis.
Originalmusik und Produktivcache blieben unberuehrt.

`directml_device.choose_device_id()` waehlt jetzt die RX 7800 XT, falls
vorhanden, sonst den groessten Hardwareadapter mit mindestens 1 GiB
dediziertem VRAM; ohne passenden Adapter verwendet ONNX CPU. Explizite
Adapter-IDs bleiben moeglich. Der reale SampleCNN-Smoke mit dem lokalen
Originalmodell waehlt ID 1, meldet `DmlExecutionProvider` und liefert
endliche Ausgaben `[1, 50]` und `[1, 512]` in 0,657 s. Die Providerliste
allein beweist nicht, dass jeder Knoten auf der GPU lief; dieser Smoke
beweist keine musikalische Guete. Der gesammelte Gesamttest
`%TEMP%/hpg-directml-full-20261107/directml-full-20261107.*` endete mit
**6704 bestanden**, **81,17 % Coverage**, Exitcode 0 in 1097,98 s.
`source-integrity.json` bestaetigt 355 gebundene Dateien ohne Hashabweichung.
Der erneute isolierte 26-Track-App-Lauf mit frischer Analyse ist unter
`%TEMP%/hpg-full-fresh-app-dgpu-20261107` gestartet. Sein Preflight
`directml-device.json` waehlt RX 7800 XT/Adapter 1 fuer HPG-ONNX.
Eine Windows-GPU-Engine-Messung erfasste jedoch den HPG-Modellkindprozess
PID 33376 mit **56,57 %** auf iGPU-LUID `0x11324` (3D-Engine). Dessen
geladene Module enthielten Rekordbox `tensorflow_cc.dll` und
`onnxruntime.dll` sowie Windows `DirectML.dll`; die genaue native Call-Site
ist damit noch nicht identifiziert. Der eigene App-Lauf wurde vor dem
ersten fertigen Track ueber `close` kooperativ abgebrochen; App- und
Modellkindprozess sind beendet. Der ONNX-Selektor behebt diesen zweiten
nativen GPU-Pfad nicht. Es gibt weiterhin keinen vollstaendigen frischen
Originaltrack-App-/Playlist-Nachweis.

Lesender Bibliotheksabgleich vom 07.11.: Die hashgepinnte
`tensorflow_cc.dll` enthält weder `DML_VISIBLE_DEVICES` noch
`CUDA_VISIBLE_DEVICES` oder `TF_VISIBLE_DEVICE_LIST` als ASCII-/UTF-16-String;
`TF_FORCE_GPU_ALLOW_GROWTH` und generische `device_id`-Strings sind vorhanden.
Ihre statische Importtabelle enthält kein DirectML/ONNX-DLL. Diese Befunde
lokalisieren die GPU-Wahl nicht, weil dynamische Ladepfade und Abhängigkeiten
möglich sind. Zusammen mit dem fehlgeschlagenen `DML_VISIBLE_DEVICES`-Versuch
gibt es weiterhin keinen belegten Adapter- oder CPU-Schalter für die gebündelte
native Rekordbox-Strecke. Keine Binär- oder Systemänderung vorgenommen.

Ein begrenzter Originaltrack-Gegenversuch setzte nur im eigenen Kindprozess
`DML_VISIBLE_DEVICES=1` (Microsofts TensorFlow-DirectML-Variable). Trotzdem
meldete Windows fuer dessen HPG-Modellkind PID 23104 **65,15 %** auf der
iGPU-LUID `0x11324`; die Variable ist fuer diese gebuendelte native
Rekordbox-Strecke kein belegter Fix. Der eigene Probeprozess und sein Kind
wurden nach Quell-/PID-Pruefung beendet; keine Ergebnis- oder Musikdatei
geschrieben. Die REA-Native-Provider Rizin und objdump waren auf diesem
Windows-Host mit `ERR_REA_WINDOWS_NATIVE` nicht nutzbar. Keine unbekannte
native ABI oder System-GPU-Einstellung wurde probeweise geaendert.

## Fortsetzung 07.11.2026: Runtime 2.71.0 und frische KI-App-Probe

Ergänzender Originaltrack-Kernlauf (kein vollständiger App-Ablauf):
`%TEMP%/hpg-fresh-original-20261107-kxptfups/report.json`.
`Umbral` direkt am Quellort mit `analyze_track(..., cache_policy="fresh")`
analysiert; Track zurückgegeben, `analysis_origin=fresh`, 142 BPM,
`native_beat_analysis.status=ok`, keine Track-Cachezeile im isolierten Cache.
Quelldatei nach Größe und mtime unverändert; SHA-256 im Bericht. 245,375 s.
Der frühere gültige 26er-Snapshot hatte ebenfalls 142 BPM und nativen Status
`ok`. Die Übereinstimmung ist keine unabhängige BPM- oder Takt-1-Referenz.
Der Prozess und seine Kinder sind beendet. Es wurden keine neuen Paarpläne,
Playlist, App-Verwendung oder Hörurteile aus diesem Einzeltrack abgeleitet.

Der erste isolierte `fresh`-App-Lauf unter
`%TEMP%/hpg-ai-ui-fresh-20261107-5fu9y41k/report.json` endete PARTIAL:
LM Studio nutzte Vulkan-Runtime 2.71.0, die bisherige HPG-Freigabeliste
enthielt nur 2.51.0 und 2.67.0. Kein Modell wurde geladen, beide
KI-Metadaten blieben leer und beide Track-Cachezeilen fehlten wie beabsichtigt.

Der lokale GPU-Survey meldet RX 7800 XT als Geräte-ID 1, integrierte Grafik
als ID 0 und sichtbare Reihenfolge [1, 0]. Der LM-Studio-App-Code
`main/index.js` hat unverändert SHA-256
`1613092a7807e13f4d386704b02ec1ebbca96faa93f7e85c693bf2e442fd9fd4`;
die Runtime-Manifeste 2.67.0 und 2.71.0 deklarieren beide
`llm_engine_vulkan.node` 0.1.2 und `liblmstudio_bindings_vulkan.node` 0.2.26.
Die Freigabeliste umfasst deshalb zusätzlich genau 2.71.0. Der bestehende
Survey-Mengenvertrag und der Konfigurations-Readback bleiben aktiv; das
beweist keine ausschließliche physische GPU-Ausführung.
Diese LM-Studio/Vulkan-IDs sind keine Zuordnung der ONNX/DirectML-`device_id`.
Eine Windows-GPU-Engine-Momentaufnahme zeigte keinen HPG-Prozess mit
messbarer GPU-Engine-Last; die spaetere DXGI-Abfrage und Korrektur der
ONNX-Geraetewahl stehen im Abschnitt direkt oben.

Gemeinsamer Volltest `%TEMP%/hpg-runtime-271-20261107/full.*`:
**6699 bestanden**, **81,23 % Coverage**, 1159,39 s, Exit 0.
`source-integrity.json`: 353 gebundene Dateien unverändert.
Erneute isolierte App-Probe
`%TEMP%/hpg-ai-ui-fresh-20261107-y5hsdojs/report.json`: SUCCESS,
zwei echte LM-Studio/rnj-1-Metadatenantworten, beide veröffentlicht,
ausschließlich `ai_metadata` der zwei Trackobjekte verändert, keine
Track-Cachezeile geschrieben, sieben gebundene Produktdateien unverändert.
Die App wurde geschlossen. Verwendet wurden vorhandene Originaltrack-
Messwert-Snapshots ab der Audio-Ergebnisgrenze; keine neue Audioinferenz,
kein Rohsignal an das LLM und kein menschliches Hörurteil.

## Fortsetzung 07.11.2026: KI nach frischer Analyse

`analysis_pipeline.finalize_track` schreibt bei `cache_policy="fresh"` bewusst
keinen Track-Cache. Die bisherige KI-Nachverarbeitung verlangte dennoch einen
vorhandenen Cacheeintrag und brach bei gültiger Antwort ab. Der Analyseworker
gibt die Policy nun an den KI-Worker weiter. Bei `fresh` wird die Quelle vor
der Veröffentlichung erneut gegen den Schlüssel vor der Anfrage geprüft;
die KI-Metadaten bleiben nur im aktuellen App-Ergebnis. Bei `reuse` bleibt
der bestätigte, quellengebundene Cache-Merge erhalten.

Der gemeinsam gestartete Volltest unter `%TEMP%/hpg-fresh-ai-20261107/full.*`
ergab **6695 bestanden, 2 fehlgeschlagen**, 81,21 % Coverage, Exit 1.
Die zwei Fehler betrafen bestehende GUI-Fixtures: ein nackter Mock lieferte
keine String-Policy, ein Ersatzworker akzeptierte den neuen Parameter nicht.
Nur `tests/test_main_workers.py` wurde danach geändert; Hashvergleich gegen
das Volltestmanifest bestätigt das. Der gemeinsame Nachtest der zwei Fälle
unter `correction.*` ergab **2 bestanden**, Exit 0, ohne Coverage. Der
fehlgeschlagene Volltest bleibt fehlgeschlagen; die Projektregel erlaubt den
gezielten Nachtest bei ausschließlicher Fixture-Anpassung und unverändertem
Produktcode. Die zwei neuen Frischanalyse-Regressionen waren im Volltest grün.
Ein nativer Originaltrack-App-Lauf mit `fresh` plus KI ist noch nicht belegt.
Nach zusätzlicher Parametrisierung des GUI-Lebenszyklustests für beide Policies
lief der gesammelte Vertragsblock `hpg-fresh-ai-20261107/fresh-contract.*`:
**8 bestanden**, Exit 0, ohne Coverage. Er prüft `reuse`/`fresh` am App-Worker,
Cachefreiheit im Frischmodus und Ablehnung einer während der KI-Anfrage
geänderten Quelldatei. Die zusätzliche Teständerung erfolgte nach dem
Volltest; dessen ursprüngliches Ergebnis bleibt unverändert.

## Fortsetzung 02.11.2026: Lebensdauer des KI-HTTP-Prozesses

Zwei Transportfehler gemeinsam reproduziert und korrigiert: der abbrechbare
HTTP-Aufruf hatte keine Gesamtfrist (requests begrenzt nur einzelne
Verbindungs-/Lesevorgänge); ein geschlossener Antwortkanal lieferte einen
ungefilterten EOFError. Der Elternprozess begrenzt nun die Gesamtdauer auf
Verbindungs- plus Lesebudget mittels monotoner Uhr und meldet EOF als
RequestException. Die vorhandene finally-Freigabe beendet den Kindprozess
auch bei diesen Fehlern. Kein Modell-, Provider-, Schema- oder Cachewechsel.

Gesammelter RED-Block unter `%TEMP%/hpg-http-deadline-20261102/red.*`:
4 fehlgeschlagen, 4 bestanden; beide Timeoutformen, rechtzeitige Antwort,
Abbruch und EOF. Danach ein gemeinsamer Abschluss-Volltest (`full.*`),
kein einzelner GREEN-Vorlauf. Anlass: geänderter produktiver HTTP-Transport.

Echte Windows-Spawn-/HTTP-Probe mit lokalem Testserver: `live.json` im
gleichen Nachweisordner. Normale JSON-Antwort erfolgreich; Server erhielt
auch die stockende Anfrage und sendete kontinuierlich einzelne Bytes.
Gesamtfrist nach 6,031 s ausgelöst, keine eigenen Kindprozesse zurückgeblieben.
Produktdatei über SHA-256 gebunden. Kein Modellaufruf, keine Audioanalyse,
keine neue vollständige Originaltrack-App- oder musikalische Abnahme.
Gemeinsamer Abschlusslauf: **6695 bestanden**, **81,22 % Coverage**,
1197,76 s, Exit 0. Konfigurierte slow-Abwahl unverändert; Coverage isoliert
im Nachweisordner. `source-integrity.json` bestätigt den unveränderten
gebundenen Produkt-/Test-/Werkzeugstand. Kein weiterer Testlauf erforderlich.

## Fortsetzung 02.11.2026: Provider-Erkennung und LLM-Quellenbindung

Vier konkrete Korrekturen gesammelt: explizite Provider-Erkennung bleibt beim
gewählten Dienst, auch wenn nur das Wunschmodell fehlt; abgebrochene
Erkennungsworker werden beim Wiedereinschalten ersetzt; LLM-Mixpunkttexte
sind als unverbindlich und nicht als aktiver Übergangsplan gekennzeichnet;
LLM-Antworten behalten den vor der Anfrage eingefrorenen Quellschlüssel.
Der Cache-Merge prüft diese Bindung nach der Lock-Wartezeit erneut. Bei
Quellwechsel bleiben alte/neue Zeilen erhalten, es wird kein Erfolg
publiziert und die App verlangt eine erneute Analyse. Kein Schemawechsel
und kein Cache-Bump; keine Audio-Neuanalyse.

Gemeinsamer RED-Block `hpg-ai-binding-20261102/red.log`: 6 fehlgeschlagen,
2 bestanden. Die erste Wiedereinschalt-Fixture wählte das Modell nicht
tatsächlich aus und war deshalb kein Fehlernachweis. Nach expliziter
Auswahl: `red-corrected.log`, 7 bestanden, genau Wiedereinschalten rot.
Danach dessen Produktkorrektur und Positivkontrolle ergänzt. Keine
Erwartung zur Datenerhaltung oder zum Providerwechsel abgeschwächt.

Native App-Probe `hpg-ai-ui-live-20261102-e_nd043o`: `discovery.json`
belegt LM Studio mit zwei Modellen, ohne automatische Ersatzwahl und mit
gesperrtem Testknopf vor Auswahl; `selection.json` belegt rnj-1 und danach
freigegebenen Testknopf. `report.json` belegt echten AIAnalysisWorker,
zwei gültige Antworten, bestätigte SQLite-Persistenz und SUCCESS-Publikation
nach 36,72 Sekunden. Nur ai_metadata verändert, sieben Produktdateien
während des Laufs unverändert; sichtbares Ergebnis geprüft. Kein Audio an
das Textmodell übertragen. App anschließend geschlossen.

Abschlusslauf `hpg-ai-binding-full-20261102/full.*` beendet, Session 56972:
**6686 bestanden, 1 fehlgeschlagen**, **81,22 % Coverage**, 1124,25 s,
Exit 1. Alle 352 gebundenen Dateien während des Laufs unverändert.
Einziger Fehler: bestehender Wiederbefüllungstest erwartete noch den reinen
Beschreibungstext ohne die neue Advisory-Kennzeichnung. Nur diese genaue
Texterwartung korrigiert; Produktcode unverändert. Gemeinsamer gezielter
Nachtest beider Tooltip-Verträge: **2 bestanden**, 0,70 s, Exit 0, ohne
Coverage (`tooltip-correction.*`). Der fehlgeschlagene Volltest wird nicht
nachträglich als bestanden bezeichnet; kein weiterer Volltest für die
ausschließliche Erwartungskorrektur nötig.

Dateisystem und SQLite bilden keine
gemeinsame atomare Transaktion: eine externe Änderung exakt nach der letzten
Statprüfung ist ohne zusätzliche Quelldateisperre nicht ausgeschlossen.

## Fortsetzung: LLM-Anbindung, erneuter Nutzerauftrag

Der Nutzer hat die Arbeit nach der Nachfrage zu Audio-/LLM-Nachweisen erneut
beauftragt. Die vorherige Aussage „keine weitere belegte Lücke“ bezog sich
auf den damaligen Abgleich; die folgende gezielte Prüfung ergänzt ihn.

Drei Vertragsfehler korrigiert, Prüfungen zunächst gesammelt: impliziter
Ollama-Download bei bloßer Erkennung; verspätete Cancel-Prüfung bei Provider-
und GPU-Vorbereitung; fehlende negative Instanzqualifikation bei ungültigem
äußerem Antwort-JSON. Analyse- und Testworker verwenden denselben Decoder.
Transportfehler und Abbruch sind weiterhin keine negative Modellbewertung.

Echte lokale App-Probe mit vorhandenen Originaltrack-Messwerten:
`hpg-llm-live-20261101-1ri96qpy/report.json`. LM Studio, installiertes
`essentialai/rnj-1`, isolierter Cache, zwei Tracks, kein Audio erneut
analysiert/übertragen. Ergebnis PARTIAL: Runtime 2.67.0 wird vom bisherigen
2.51.0-Gate abgewiesen, kein Modell geladen, keine Metadaten erzeugt.
Playlist mit zwei Tracks veröffentlicht, Quellpayloads unverändert.
Die tatsächliche GPU-ID-Abbildung wird vor einer Kompatibilitätsänderung
an lokalen Artefakten geprüft. Kein Download oder Providerwechsel.

Lokaler Mapping-Beleg `hpg-lmstudio-267-contract-20261101/summary.json`:
App 0.4.27+2 / Runtime 2.67.0 / SDK 1.5.0 übersetzen Survey-IDs intern;
HPG übergibt mainGpu=1, disabledGpus=[0] unverändert. Genau 2.51.0 und
2.67.0 unterstützt; unbekannte Versionen bleiben abgewiesen. Tatsächliche
Runtime wird nun im Qualifikationsschlüssel gebunden. Geräte-Mengenprüfung
und Konfigurations-Readback bleiben erhalten, keine exklusive GPU-Behauptung.
Erneute Probe in `hpg-llm-live-20261101-buqacpev` scheiterte am externen
Prüfstarter: fehlender Windows-Spawn-Guard verursachte eine zweite App im
HTTP-Kindprozess. Beide eigenen Apps geschlossen, kein Erfolg behauptet.
Guarded Starter vorbereitet; Produktcode dafür nicht verändert.
Alle Regressionen gesammelt, gemeinsamer Volltest ohne einzelne Vorläufe:
`hpg-llm-final-full-20261101/full.*`. Produkt-/Testdateien eingefroren.
Guarded Liveprobe erfolgreich: `hpg-llm-live-20261101-ap4au1o1/report.json`.
Echter AIAnalysisWorker mit LM Studio/rnj-1, zwei gültige Antworten,
21,22 Sekunden einschließlich Vorbereitung. Beide Metadaten identisch im
isolierten SQLite-Cache und im App-Track, ausschließlich `ai_metadata`
geändert; sieben gebundene Produktdateien während der Probe unverändert.
MainWindow veröffentlicht SUCCESS und zwei Tracks. Sichtbares Fenster
geprüft, interner Score 81 % ausdrücklich keine musikalische Bewertung.
Kein Audio an das LLM übermittelt, keine neue Audioanalyse und keine
physische/exklusive GPU-Ausführung aus Config-Readback abgeleitet.
Gemeinsamer Abschlusslauf beendet: **6677 bestanden**, **81,20 % Coverage**,
1159,50 s, Exit 0; `hpg-llm-final-full-20261101/source-integrity.json`
bestätigt 351 gebundene Dateien ohne Änderung. Konfigurierte slow-Abwahl
bleibt bestehen. Keine einzelnen Vor-/Nachtests. Die Liveprobe ist ein
Nachweis für Text-Metadatenanreicherung und deren App-/Cache-Anbindung,
kein Test eines Audio-LLM mit Rohsignal und keine musikalische Abnahme.

## Zusammengeführter Nachweisstand (07.11.2026)

Die folgenden Abschnitte enthalten auch zeitliche Zwischenstände. Maßgeblich
ist diese Übersicht; frühere Aussagen wie „noch ungetestet“ sind keine
erneuten Arbeitsaufträge.

| Bereich | Aktueller Beleg und Grenze |
|---|---|
| Refaktorierung, Refiner, Cache-Reparatur, Statistik, UI, LLM-Anbindung und DirectML-Geraetewahl | Neuester Volltest am 07.11.: 6704 bestanden, Coverage 81,17 %, Exit 0; 355 gebundene Dateien nach dem Lauf unverändert. Vorherige fehlgeschlagene Läufe bleiben historische Zwischenstände. |
| Lokales LLM | LM Studio/rnj-1: zwei echte gültige Metadatenantworten im `fresh`-App-Lauf veröffentlicht, ohne Track-Cachezeilen; `reuse` zuvor mit isolierter Persistenz belegt. Kein Rohsignal-Audiotest. |
| Originaltrack-App und Cache | 26 Tracks in der App; Parallel Worlds mit 135 BPM repariert, andere Payloads erhalten; anschließender Reuse 26 Cachetreffer, keine Erstanalysen. |
| Audioabdeckung und Zeilen-Drop | Korrigiert; native Mausprobe zeigt vollständige Zeilen und veröffentlichtes Reorder; Abdeckung korrekt. Gemeinsamer Volltest Session 72342 bestanden. |
| W / Deep Sky | Beide Richtungen geprüft, unter Mindestscore; kein zulässiger Plan, keine Vorschau. Kein Paarungsfehler nachgewiesen. |
| Musikalische Bewertung | Menschliches Hörurteil und unabhängige musikalische Referenzen fehlen weiterhin; technische Ergebnisse ersetzen diese nicht. |
| Auslieferung | Kein neuer EXE-Build beauftragt oder als geprüft behauptet. |

## Weitere projektweite Runde, Auftrag vom 01.11.2026

Fortsetzung nach technischer Refaktorabnahme: Der Gesamtauftrag bleibt offen.
Konkrete native Lücke: Parallel Worlds wird heute mit 81 BPM/mismatch
zurückgegeben; der historische Erfolg betraf einen anderen Replaypfad.
Der frische Worker verwendet bei Neufensterung denselben nativen Refiner
erneut. Zustandseinfluss ist eine Hypothese, noch kein belegter Fix.
Ein einzelner isolierter Diagnoselauf wird vorbereitet; Modell7-Rohdaten und
Modell8-Ausgaben vor/nach Refinement sollen für Vergleiche erhalten bleiben.
Probe nach Quellreview gestartet, Session 57699, maximal 420 s:
`hpg-native-acceptance-20261101-h2z8piod/native-refiner-probe/launch_probe.py`.
Ein Originaltrack, bestehender OwnedModelProcess, kein Produktivcachezugriff.
Diagnose beendet, Exit 0, Quelle unverändert: Ersatzfenster exakt 348 s,
Modell8-Rohwert 136,36 BPM, beide Aufrufe derselben Instanz liefern 81 BPM.
Frischer Refiner auf identischem Ersatzoutput liefert 135 BPM und keinen
Widerspruch zur Gesamtfolge. Ursache damit eingegrenzt; Worker nutzt nun
für alternatives Modell8-Fenster und Modell7-Fallback jeweils frischen Zustand.
Keine zweite Modellinferenz dafür; vier Regressionen zunächst gesammelt,
anschließend im unten dokumentierten 6630-Test-Lauf bestanden.
Gezielte Cache-Reparatur durch Root implementiert: optionale streng validierte
Fehlerproducerrevision ausschließlich für exakt diese alte Ablehnung. Alte
Fehler werden einmal durch die reguläre Kernpipeline erneuert; erneute
Ablehnung mit aktueller Revision bleibt wiederverwendbar. Quellgebundene
gültige Stems/Embeddings werden an den regulären Attachment-Validator übergeben.
Kein globaler CACHE_VERSION-/Core-Fingerprint-Bump: Erfolgsschema und gültige
Messwerte bleiben gleich; die präzise Fehlerrevision verhindert das Maskieren
des Fixes. Dies ersetzt hier bewusst den pauschalen Bump aus dem Cache-Skill,
der unnötig alle erfolgreichen Analysen verwerfen würde. Alte Fehlerpayloads
bleiben lesbar und werden nicht quarantänisiert. Die gesammelten Tests
sind im unten dokumentierten 6630-Test-Lauf bestanden.

Deep-Sky-Quelle vorhanden, aktuelles vollständiges Payload fehlt. Read-only-
Beleg `hpg-deepsky-contract-20261101-odi8491p/report.json`: v46-Altpayload
verletzt zehn aktuelle Pflichtfelder, ctime-Quellbindung abweichend;
Größe/mtime allein reichen nicht zur Freigabe. Rekordbox aktuell 125 BPM,
Em/9A, W aktuell 127 BPM. Alte Rohdaten extern erhalten; keine erfundenen
Pflichtfelder oder ungeprüfte Übernahme alter Analysewerte.
Einmalige frische Deep-Sky-Analyse gestartet (Session 98841), ausschließlich
dieser Originaltrack, Ausgabe `hpg-deepsky-fresh-20261101-8ceqex1v`.
Stems/Embedding für diesen Paarplannachweis ausdrücklich deaktiviert;
W bleibt unverändert aus aktuellem Snapshot. Produktdateien währenddessen
eingefroren; Tests werden nur vorbereitet, nicht parallel ausgeführt.
Deep-Sky-Lauf abgeschlossen, Exit 0, Payload validiert; aktuelle Quelle und
W-Snapshot unverändert. Modell-/Phrasenstatus und genaue Laufzeit stehen in
`hpg-deepsky-fresh-20261101-8ceqex1v/report.json`. Kein Hörurteil daraus abgeleitet.

Nächster gemeinsamer Volltest begründet durch neue Refinerzustandskorrektur,
gezielte Cache-Reparatur und Missing-Data-/Bootstrap-Korrekturen. Keine
vorgeschalteten Einzeltests. Belege `hpg-refiner-statistics-full-20261101/full.*`,
Projektinterpreter, pytest.ini-Coverage, vier xdist-Worker. Produkt-/Testdateien
währenddessen eingefroren. Prüfmanifest bindet jetzt auch importierte tools-
Pythonmodule und den Launcher selbst; frühere Manifeste bleiben unverändert.
Gesamtlauf abgeschlossen: **6630 bestanden**, **81,14 % Coverage**, 1161,04 s,
Exit 0. 349 gebundene Dateien nach Laufende unverändert (`source-integrity.json`).
Konfigurierte slow-Abwahl bleibt bestehen. Keine weiteren Einzeltests nötig.
Gezielte native App-Reparatur gestartet, Session 48126, neuer Belegordner
`hpg-native-acceptance-20261101-h2z8piod/native-app-refiner-repaired`.
Gleiche isolierte Datenbank, keine Kopie/Neuseedung, normale Wiederverwendung.
Erwartung: 25 unveränderte Kerncachetreffer, einmal Parallel-Worlds-Reparatur;
dessen erfolgreiche Stem-/Embedding-Payloads müssen unverändert bleiben.
App-Reparatur abgeschlossen: 25 Cachetreffer, Parallel Worlds frisch mit
135 BPM, Beatgrid verified, native Beat-/Phrasenstatus ok. Beide Zusatz-
Payloads exakt erhalten, sämtliche anderen 25 Trackpayloads unverändert;
alle 33 bisherigen DB-Zeilen erhalten. Playlist 19/25 geplante Grenzen,
interner Score 60,88 % (keine musikalische Qualitätsmessung).
Beleg `native-app-refiner-repaired/refiner-verification-refiner-final.json` sowie
`tracks-refiner-final.json`/`result-refiner-final.json`. Anschließender
App-Reuse liefert 26 Cachetreffer, null Erstanalysen, alle Trackpayloads
exakt gleich (`post-repair-cache-proof.json`). App geschlossen, Exit 0.

W/Deep-Sky-Paarprobe gestartet, Session 4210, echte App mit vorhandenen
aktuellen Payloads, 2 BPM, Harmonic Flow; keine weitere Analyse. Belege:
`hpg-w-deepsky-app-20261101-mf6p32sd`. W -> Deep Sky ist zunächst ungeplant
(lokale Mindestpassung, unregelmäßige/unvollständige native Beatfolge im
Mixfenster). Keine Vorschau gestartet, kein Gate umgangen. Beide Richtungen
werden anhand der vorhandenen Metadaten diagnostiziert.
Neue sichtbare UI-Befunde: gültige Abdeckung wird als ungültig gespeichert
angezeigt; Ziehen unter das Ende der Zweierliste ließ erste Zeile leer.
Screenshot `window-pair-blocked-drag.png`. Read-only-Diagnose bestätigt:
Abdeckungsanzeige erwartet Intervallpaare, obwohl der gültige Vertrag
`start`/`end`-Dictionaries liefert. Beim Tabellen-Drag deckt die bisherige
Absicherung nur Modell-Zeilensignale ab; der genaue native Drop-Pfad bleibt
noch einzugrenzen. Beide Korrekturen samt Regressionen werden gesammelt.
Paar-App vor diesen Änderungen geschlossen, Exit 0.

Beide Paarrichtungen anhand validierter Snapshots geprüft (`pair-diagnosis.json`):
W -> Deep Sky hat acht bewertete Kandidaten, bester Score 0,51315;
Deep Sky -> W sechs, bester Score 0,66202. Alle scheitern am Mindestscore
0,70, obwohl Tempoabstand 2 BPM und Groove-Mindestwert erfüllt sind.
Zusätzliche Fenster scheitern am Beatgate; dieses sperrt nicht alle Fenster.
Kein falsches Beatgate nachgewiesen, keine Vorschau oder Grenzlockerung.

GUI-Korrekturen gesammelt: kanonische Abdeckungs-Dictionaries lesen;
PlaylistTable bewegt ganze Zeilen über Modell-Signale und vermeidet den
Qt-Item-Cleanup. 14 neue Regressionen für Abdeckung, Drop und Rollback.
Ein gemeinsamer Abschlusslauf ohne vorgeschaltete Einzeltests gestartet:
`hpg-ui-final-full-20261101/full.*`, Session 72342. Quellstand eingefroren.
Abgeschlossen: **6644 bestanden**, **81,17 % Coverage**, 1334,16 s, Exit 0.
`source-integrity.json` bestätigt 351 gebundene Dateien ohne Änderung.
Konfigurierte slow-Abwahl bleibt bestehen. Keine zusätzlichen Einzeltests.
Native Mausprüfung mit denselben vorhandenen Originaltrack-Payloads:
`hpg-w-deepsky-app-20261101-z_r04kez`. Drop in Leerfläche veröffentlicht
Deep Sky -> W, beide Zeilen vollständig; Status bestätigt gemeinsames
Result für Mixpoints, Preview, Timeline und Export. Abdeckungsanzeige zeigt
für W korrekt 540,0/657,1 Sekunden (82 %) und abgedecktes Trackende.
Keine Audio-Neuanalyse, keine Vorschau und kein musikalisches Urteil.

Sechs ungeplante Grenzen des reparierten 26er-Ergebnisses lesend erklärt:
`native-app-refiner-repaired/unplanned-boundary-audit.json` sowie
`three-boundaries-diagnosis.json`. Drei überschreiten 2 BPM (3/5/8 BPM).
W mit 127 BPM hat unter den übrigen Tracks keinen Tempo-Nachbarn (Minimum
135 BPM); mindestens eine Unterbrechung ist daher unvermeidbar.
Dream Voyager -> Source of Reality hat acht qualifizierte Paar-Kandidaten,
aber deren Ausstiege 324,507/365,070 s sind mit dem gewählten vorherigen
Eingang 365,070 s nicht verkettbar (frühester zulässiger Ausstieg 419,105 s).
Terra -> The Ritual: sieben bewertete Kandidaten, bester Score 0,49914,
Groove 0,26054; The Ritual -> Hallucination Generation: neun, bester
Score 0,66706, Groove 0,66445. Mindestwerte 0,70 und 0,50 unverändert.
Kein zusätzlicher Implementierungsfehler daraus nachgewiesen. Die drei
Paarbewertungen nutzten gespeicherten Kontext und explizit leere Präferenzen,
weil der historische Wahl-Snapshot fehlt. Historische Wahlpriorität und
globale Optimalität sind damit nicht bewiesen. Keine neue Audioanalyse.

Abschlussabgleich: keine weitere belegte Implementierungslücke in Auftrag,
Design und aktuellen Nachweisen gefunden. Dies ist keine Zusage völliger
Fehlerfreiheit. Menschliches Hörurteil am 01.11. per Rückfrage angefordert;
am 07.11. antwortete der Nutzer „Noch nicht angehört“. Musikalische Abnahme
daher weiterhin offen, Gesamtziel
nicht als vollständig erreicht markiert. Kein weiterer Test-/Audio-/Buildlauf
allein wegen dieser ausstehenden Bewertung gerechtfertigt.

Neuer tatsächlicher Fehler in der Mixreferenzauswertung: sieben der 15
Fensterpaare haben keine verwertbaren Rhythmusmuster, wurden aber mit
`groove_sim=0` als schlechte Passung ausgegeben. `mix_analysis.deltas_between`
lässt fehlende Groove-/Timbrefaktoren nun weg; faktorweise Mining-AUC und
Toleranzen verwenden nur Messwerte. Der gelernte Gesamtscore verlangt alle
positiv gewichteten Faktoren, sonst None; Holdout zählt Ausfälle getrennt.
Bootstrap zieht beide Klassen desselben informativen Mixes gemeinsam;
unter zwei beidseitig informativen Mixen bleibt das Intervall unbestimmt.
Ausgabe zeigt Messanzahlen je Faktor. Die gesammelten Regressionen sind
im oben dokumentierten 6630-Test-Lauf bestanden.
Gespeicherte Fenster ohne neuen Audiozugriff erneut ausgewertet:
`hpg-reference-20261101-mb2ayj_i/transition-windows-corrected.json` ersetzt
die davon betroffenen Deltas; der ursprüngliche Rohbeleg bleibt erhalten.
Ältere Voll-/Nachtests vor diesem 6630-Test-Lauf belegen den neuen Fix nicht.

Aktueller Abschlussstand des ersten App-Laufs (01.11., ca. 15:17):
26 Tracks veröffentlicht, davon 19 frisch und sieben aus migriertem Cache;
18 von 25 Übergängen geplant, Qualität initial 57,92 %. Native Umsortierung
und anschließender Wechsel auf Kandidat 2 des ersten Paars ausgeführt.
Zeitlinie folgt dem Resultat. M3U8 und Rekordbox-XML aus der App exportiert;
26 Pfade in beiden Exporten exakt in Resultatreihenfolge. XML MIX OUT
271,3041950113 s / MIX IN 83,4779818594 s entsprechen der aktiven Wahl.
Beleg: `native-app-final/export-verification.json`, dazu `chosen-export.*`
und `result-chosen-export.json`. XML enthält 25 Beatgrids und 549 Cues;
für Parallel Worlds wurden Grid/Cues mit sichtbarer Warnung ausgelassen.
Kein Rekordbox-Import und kein menschliches Hörurteil nachgewiesen.
App geordnet geschlossen, Session 48223 Exit 0.

Nach Laufende gebündelte Korrekturen: lokale Tonarthinweise an aktive
Mixpunkte binden; die exakt belegte permanente native Rasterablehnung von
transienten Fehlern trennen; verbleibende Zeitlinienbeschriftungen übersetzen.
Runtime-Integration des längenabhängigen Stem-Budgets in Arbeit.
Runtime inzwischen integriert: automatische Stems erhalten quellgebunden
240 bis 900 Sekunden; Embedding, explizite kurze Fristen, gemeinsame
Fallback-Restzeit und Trackdeadline bleiben begrenzt. Produzenten unverändert.
Konfigurationssicherung extern unter `hpg-runtime-config-c4dbc4dbbd574ef9ae52fd090d5fa6a5`.
Gemeinsamer Abschluss-Volltest wird gestartet, weil Runtime/Broker, Cache-
Fehlerklassifikation und beide Playlist-Einstiege seit dem letzten Beleg
geändert wurden. Keine vorgeschalteten Einzeltests. Belegverzeichnis:
`C:/Users/david/AppData/Local/Temp/hpg-runtime-full-20261101`, Label `full`.
Projektinterpreter, pytest.ini-Coverage und vier xdist-Worker; Produkt-/Test-
Dateien während des Laufs eingefroren. Danach Cache-Wiederverwendung in der App.
Der Gesamtlauf endete mit **6578 bestanden, 6 fehlgeschlagen**, 80,92 %
Coverage, 1302,45 s, Exit 1. Er wird nicht als bestanden dargestellt.
Zwei Fehler waren veraltete Erwartungen an „Timeline ungültig“ nach der
Übersetzung zu „Zeitlinie ungültig“. Vier neue Resultpfadtests hatten eine
inkonsistente Fixture: Camelot gesetzt, Quelltonart leer; der echte Einstieg
berechnet Camelot aus keyNote/keyMode neu. Fixturequellen korrigiert,
Assertions unverändert. Kein Produktcode nach dem Gesamtlauf geändert.
Gebündelter notwendiger Nachtest: `test_main_workers.py` und
`test_transition_key_notes.py`, Label `corrections`, dasselbe Belegverzeichnis.
Kein weiterer Volltest für diese reinen Testkorrekturen.
Nachtest beendet: **206 bestanden, 1 abgewählt**, 16,12 s, Exit 0,
ohne Coverage. Gegen Volltestmanifest sind nur die zwei korrigierten
Testdateien geändert; kein Produktcode. Native Cache-Wiederverwendung
gestartet (Session 15034): `native_app_reuse_probe.py`, Zustand unter
`native-app-reuse-after-runtime/`, unveränderter isolierter Erstlaufcache.
Zweiter App-Lauf abgeschlossen: 26 Tracks, 25 Kerncachetreffer und eine
frische Analyse (Parallel Worlds). Beleg `reuse-verification.json`: alle
32 vorherigen Cachezeilen erhalten, eine neue hinzugefügt; in bestehenden
Zeilen ausschließlich W `stem_analysis` verändert. W-Stems jetzt `ok`.
Trackvergleich: nur W-Stems und die Diagnose zur dauerhaften Ablehnung bei
Parallel Worlds unterscheiden sich. Dessen natives Grid bleibt gesperrt;
keine erfundenen Beats/Cues. Alle vorher erfolgreichen Zusatzmerkmale und
übrigen Kernwerte bleiben unverändert. App veröffentlicht 26 Tracks, Qualität
58 %. Kein exklusiver GPU-Nachweis (`provider_verified` bleibt false).
Lokale Tonarterklärung für Dream & Desire -> Neural Pathways sichtbar:
6A -> 6A lokal, trackweit 6A -> 10B getrennt, Messkonfidenz 0,6/0,6;
kein widersprüchlicher globaler Tonart-Clash. Zeitlinie deutsch sichtbar.
Screenshots `window-local-key-visible.png` und `window-translated-timeline.png`.
Abschließender Hashabgleich `hpg-runtime-full-20261101/source-integrity-final.json`:
312 Dateien gebunden, gegenüber Nachtest keine Änderung; gegenüber Volltest
nur die zwei dokumentierten Testkorrekturen. App geordnet geschlossen,
Session 15034 Exit 0. Unabhängiger schreibgeschützter Belegabgleich bestätigt
die technische Abdeckung der Etappen 1–8; keine pauschale Fehlerfreiheit.
Musikalisches Hörurteil bleibt gesondert offen. Kein EXE-Lauf/Zielimport behauptet.
Die bereitgestellte Mixreferenz wurde anschließend begrenzt ausgewertet:
15 von 17 deklarierten Übergangsstellen, 30 Fenster à 60 s, 20 s Schutzabstand.
27:30 und 28:30 ausgelassen, weil die Nachbarmarken keine ausreichend
abgetrennten 60-s-Fenster zulassen. Bestehende HPG-Funktionen `miss_fenster`,
`window_bounds`, `deltas_between`; nur RAM-Audio und neue JSON-Metadaten.
Beleg `C:/Users/david/AppData/Local/Temp/hpg-reference-20261101-mb2ayj_i/transition-windows.json`,
12,09 s Messlauf, Exit 0. Vorhandener Voll-Dekodierbeleg wiederverwendet;
Originalgröße/Änderungszeit und Tracklistenhash vor/nach gebunden.
Dies sind Groove-/Bass-/Klangfarbenmessungen an Nutzermarken, keine bestätigten
Blendzentren oder Titelidentitäten. Keine Gewichte/Toleranzen geändert,
kein Holdout und keine musikalische Güteaussage aus diesem Einzelmix.
Die folgenden Zwischenbeobachtungen dokumentieren die Diagnosechronologie.

Gebündelter Originaltrack-App-Lauf am 01.11.2026 gestartet, Exec-Session 48223:
`C:/Users/david/AppData/Local/Temp/hpg-native-acceptance-20261101-h2z8piod/native_app_probe.py`.
Zustand/Logs unter dessen `native-app-final/`. Echte MainWindow-/Worker-Pipeline,
26 Originaldateien aus `F:/beatport_tracks_2026-04`, vier Analyseprozesse,
2-BPM-Standard, optionale KI-Metadaten aus, sieben alte validierte Metadatensätze
im neuen Prüfcache. Kein Produktivcache geändert. Grund: Nachweis tatsächlicher
Migration/Cache-Nutzung und der fehlenden Erstanalysen in einem App-Ablauf.
Zwischenbeobachtung (14:39:39): 21/26 verarbeitet, Batch 3 lief;
inzwischen abgeschlossen, siehe aktuellen Stand oben.
Neuer realer Fehlerfall: „W (Klipsun 2025 remix)“, 657,084943 s, Stems
`unavailable / service_error:TimeoutError`; native Beats, Phrasen und Embedding
`ok`, Kernresultat gecacht. Broker meldet `ModelProcessTimeout`.
Metadatensnapshot: `native-app-final/w-stem-timeout-track.json`.
Stem-Ausführung ist derzeit sowohl in `deep_features._feature_timeout_seconds`
als auch im Broker auf 240 s begrenzt. Dauerabhängiges begrenztes Budget prüfen;
erfolgreiche Zusatzmerkmale dürfen durch reine Laufzeitpolitik nicht unnötig
neu invalidiert werden. Fix und Regressionen nach Laufende bündeln.
Lesend geprüfter Umsetzungsentwurf: automatische Attachment-Hülle außerhalb
der Deep-Feature-Produzenten, verwendet an beiden `analysis.py`-Aufrufstellen
(Erstanalyse und Cache-Refresh). Quellgebundener, verschachtelbarer Laufzeit-
kontext; `cue_service.session()` liefert darin einen kurzlebigen Proxy, der
nur das Stem-Budget anpasst. Direkte Clientfristen und Embedding unverändert.
Proxy nie im Pool-/Trackclient speichern; Kontext in `finally` wiederherstellen.
Bestehender Client behält einen gemeinsamen Versuch-/Fallback-Zeitrahmen;
Trackdeadline und Cleanupreserve bleiben harte Grenzen. Brokerobergrenze
anpassen, `deep_features.py`/Worker unverändert lassen: erfolgreiche
Producer-Fingerprints bleiben erhalten. Budgetwerte noch nicht laufzeitbelegt.
Regressionen gesammelt zu direkter Frist, automatischem Budget, Quellenbindung,
beiden Sessionpfaden, Kontext-Cleanup, Fallback-Restzeit und Fingerprint-Erhalt.
Vorbereitet, noch nicht eingebunden oder getestet: neue Dateien
`hpg_core/ai_models/deep_feature_runtime.py` und `tests/test_deep_feature_runtime.py`.
API: `attach`, `client_for_context`, `stem_timeout_seconds`; Startbudget
`min(900, max(240, 60 + duration))`. ContextVar, Quellidentitätsprüfung und
Delegations-/Cleanupregressionen vorhanden. Die bisherigen produktiven Module
sind während des App-Laufs unverändert. Nach Laufende beide Attach-Stellen und
beide Session-Zweige integrieren sowie Client-/Brokergrenzen und Fallbackbudget
abstimmen. Testfälle gemeinsam ausführen; noch kein Erfolg des Fixes behaupten.
In der neuen Testdatei zusätzlich gesammelt: echte `cue_service.session()`-
Zweige mit isolierten Clients/Ownern sowie echtes `deep_features.attach()`
mit kontrollierten externen Diensten. Erwartet werden kurzlebige Proxies,
unveränderte gespeicherte Clients, Embedding-Budget/Fingerprints/BPM und
geordneter Cleanup. Noch nicht ausgeführt; Sessiontests benötigen Integration.
Zusätzlich gesammelt: echter `CueClient.deep_features` mit kontrollierter
Transportgrenze/Uhr. Stem717 erhält nach100 Sekunden nur617 Sekunden Fallback;
direkte30/240- sowie Embedding240-Fristen bleiben erhalten, erschöpftes Budget
startet keinen zweiten Versuch. Kein Testlauf, keine Modellinferenz.
„Neural Pathways“ besitzt nach der Erstverarbeitung einen neuen Cacheeintrag:
Analysepfad `rekordbox_fast_tail`, native Beats, native Phrasen, Stems und
Embedding jeweils `ok` (lesend aus isolierter DB bestätigt). Das ist der erste
vollständige Cache-Miss-Nachweis dieses Laufs; App-Veröffentlichung steht aus.
Offener Laufzeitbefund: „Parallel Worlds“ meldet `Degradierte Kernanalyse NICHT
gecacht`. `analysis_pipeline.finalize_track` erzeugt diesen Hinweis bei
degradierter Audioanalyse, transientem Neuralfehler, nicht verfügbarer nativer
Phrasenanalyse oder transientem Anker. Die konkrete Ursache ist erst anhand
des zurückgegebenen Tracks zu bestimmen; noch kein belegter Produktfehler
und kein vollständiger Erstanalysen-Erfolg. Nach Abschluss Snapshot auswerten.
Gesammelter Codebefund aus lesender Diagnose: `analysis.py` behandelt nur
exakt `unsupported_source_format` als dauerhaften nativen Fehler;
`native_track_beats.analyze` verpackt Worker-Fehler dagegen als
`ValueError: <reason>`. Nachprüfung: kein aktueller Producer oder Test erzeugt
`unsupported_source_format`; belegt ist somit ein veralteter Sonderfall,
kein aktuell reproduzierter Fehler. Keine hypothetische Regression oder
Änderung der Cachepolitik allein daraus ableiten. Weiterhin nicht als
Ursache von „Parallel Worlds“ belegt. Für dessen Diagnose insbesondere
`native_phrase_analysis`, `native_beat_analysis`, `neural_analysis` und
`measurement_diagnostics.anchor.neural` auswerten. Zusatzmerkmale selbst
lösen den Kerncache-Verzicht nicht direkt aus.
Sichtbare App per Computer Use geprüft: Analyseschritt und Abbruchknopf
sichtbar, Generieren gesperrt, kein blockierender Dialog. „Floating Kingdom“
besitzt nun ebenfalls erfolgreiche Stems und Embeddings. `provider_request`
meldet DirectML, `provider_verified` bleibt false; keine GPU-Ausführung behaupten.
Lesender Zwischenabgleich der laufenden isolierten DB: sechs historische
Zeilen besitzen bereits einen Eintrag mit neuer Kernidentität. Bei drei
abgeschlossenen Tracks unterscheiden sich nur `embedding_analysis`,
`neural_analysis` und `rekordbox_signature`; die anderen drei übernommenen
Zeilen unterscheiden sich bisher nur in den beiden Herkunftsfeldern.
Das ist ein Zwischenstand der Migration, kein abgeschlossener App-Nachweis.
Bei „Voices“ sind inzwischen sowohl Stems als auch Embedding `ok`; die alte
Zeile bleibt erhalten. Der Prozess ist über Session 48223 weiterhin erreichbar.
Lesender Abgleich um 13:36: alle sieben Kernergebnisse übernommen; im
Neural-Snapshot ändert sich jeweils ausschließlich `fingerprint`. Die fünf
abgeschlossenen Tracks einschließlich „Dream Voyager“ besitzen erfolgreiche
Stems und Embeddings. Noch wartende Payloads sind kein Fehler des aktuellen
Laufs. Beleg: `native-app-final/migration-interim-1336.json`.
`native-app-final/source-integrity.json` bestätigt 308 unveränderte gebundene
Quell-/Testdateien gegenüber dem Korrekturprüfblock. Kein neuer Testlauf.
Nach Verarbeitung aller sieben vorhandenen Tracks bestätigt
`native-app-final/migration-seven-completed.json`: sieben übernommene
Kernergebnisse, sieben erfolgreiche Stem-/Embedding-Paare, neuronale Werte
bis auf `fingerprint` erhalten. Der weitere Lauf verarbeitet die Cache-Misses.
Analyseherkunft pro Track wird nach dem Worker-Ergebnis protokolliert.
Den laufenden Prozess weiterverfolgen; keine zweite App/Analyse starten.

Minimale verbleibende native Abnahme nach lesendem Belegabgleich:
Ergebnis samt tatsächlicher Analyseherkunft sichern; einmal echtes Reorder
ausführen und Reihenfolge in Tabelle/Übergängen/Zeitlinie abgleichen; eine
aktive Alternativwahl bis zum XML-/M3U8-Export über die App verfolgen;
anschließend einmal Cache-Reuse. Wegen des inzwischen belegten Stem-Timeouts
wird dieser Reuse erst nach Integration der Korrektur in einem neuen App-Prozess
mit demselben isolierten Prüfcache durchgeführt. Kein zusätzlicher Reuse im
alten Prozess, der das bekannte Zeitlimit erneut erreichen würde. Erfolgreiche
Kern-/Zusatzanalysen erhalten; fehlende Schritte gezielt erneuern. Exporte enthalten nur
Metadaten/Quellverweise. Vorhandene native Vorschau- und Kandidatenbedienbelege
aus `hpg-app-goal-20261101-lov21pgx` bzw. `hpg-app-goal-20261101-bmwg02w0`
weiterverwenden; keine Wiederholung ohne geänderten Vertrag oder neuen Fehler.
Der aktuelle Lauf mit Standardpolitik beweist bei Cache-Misses Erstanalysen,
nicht einen expliziten `fresh`-Lauf aller 26 Dateien.
Reuse-Starter vorbereitet, noch nicht gestartet:
`C:/Users/david/AppData/Local/Temp/hpg-native-acceptance-20261101-h2z8piod/native_app_reuse_probe.py`.
Er öffnet denselben isolierten `native-app-final/cache.db`, erzeugt getrennte
Belege unter `native-app-reuse-after-runtime` und erfasst vorher Feldprüfsummen
aller Cachezeilen. Kein Seeding, keine Musik-/Datenbankdateikopie. Bereits
gefüllter Belegordner verhindert einen erneuten Start. Erst nach Ende des
aktuellen Prozesses, Integration und gemeinsamem Prüflauf verwenden.

Gesammelte Restkorrektur aus unabhängigem lesendem Anforderungsabgleich:
`main.py` enthält in `_export_m3u8` und `_export_rekordbox_xml` noch englische
Exportfehlertexte. Nach Ende des App-Laufs in den nächsten Änderungsblock
aufnehmen; während des Laufs Produktcode unverändert lassen. Die strukturellen
Aufgaben 1–6 sind vorhanden; dies ersetzt nicht die native und musikalische Abnahme.

Gebündelte notwendige Nachprüfung der Korrekturen: **434 bestanden**, 11,36 s,
Exitcode 0, ohne Coverage. Umfang: caching, core_cache_migration, cue_service,
cue_pipeline_integration und probe_launcher. Rohbelege:
`C:/Users/david/AppData/Local/Temp/hpg-core-cache-corrections-20261101/`.
Ruling gemäß aktueller Nutzeranweisung zur Testminimierung: kein erneuter
Volltest allein für diese beiden begrenzten Korrekturen; gültige Belege der
unveränderten Bereiche weiterverwenden. Der vorherige Gesamtlauf bleibt mit
vier Fehlern dokumentiert; die Nachprüfung ist kein neuer Coverage-Volltest.
Nächster Beleg: tatsächliche Cache-Migration im gebündelten Originaltrack-App-Lauf.

`core-cache-bundle-20261101` beendet, Exitcode 1: **6491 bestanden, 4 fehlgeschlagen**,
80,78 % Coverage, 1149,43 s. Alle 308 gebundenen Quell-/Testdateien anschließend
unverändert; `integrity.json` im Belegordner. Vier Fehler in
`test_cue_pipeline_integration::test_both_producers_cache_policy`: Fixture
patchte noch `fingerprint` statt des nun verwendeten `core_fingerprint`.
Dienstgrenze korrigiert, erwartete Werte unverändert. Außerdem gesammelte
Pfadkorrektur umgesetzt: Migration sucht über den normalisierten Dateiquell-
Präfix des bestehenden Cache-Keys, nicht über textuelle filepath-Varianten.
Variantenregression ergänzt. Die damals ausstehende gebündelte Nachprüfung
ist oben mit 434 bestandenen Tests dokumentiert. Der fehlgeschlagene Gesamtlauf
bleibt als solcher erhalten.

Historische App-Prüfvorbereitung vor dem oben dokumentierten Start:
Harness `hpg-native-acceptance-20261101-h2z8piod/native_app_probe.py`
übernimmt nur validierte, quellidentische Metadatenzeilen aus der früheren
isolierten Prüf-DB in einen neu erzeugten Prüfcache. Quelle ausschließlich
SQLite `mode=ro`; keine Musik- oder Datenbankdateikopie. Herkunft je Zeile mit
Payload-SHA-256 im neuen Prüfverzeichnis. Bestehender Zielcache führt zum
Abbruch statt Überschreiben. Damit kann ein gemeinsamer App-Lauf echte
Migration/Wiederverwendung und fehlende Erstanalysen unterscheiden; die Events
halten `analysis_origin` pro Track fest. Zweiter Reuse-Durchlauf bleibt im selben
App-Prozess möglich. Diese Vorbereitung beweist noch keinen erfolgreichen Lauf.

Lesender Review während `core-cache-bundle-20261101`: Migration und Routing-
Regressionen im laufenden Gesamtlauf bestanden, Gesamtergebnis noch offen.
Mögliche zusätzliche Lücke: historische Zeilensuche vergleicht `filepath`
textuell gegen wenige Varianten. Der bestehende Cache-Key normalisiert dagegen
Groß-/Kleinschreibung und Pfadseparatoren. Nach Laufende Suche auf denselben
Dateiquellvertrag ausrichten und Variantenregression sammeln; Produktcode
während des laufenden Tests unverändert lassen. Kein zweiter Lauf gestartet.

Gemeinsamer Prüflauf für den gesammelten Cache-/Starter-Block gestartet:
`core-cache-bundle-20261101`, Exec-Session 94639, Rohbelegordner
`C:/Users/david/AppData/Local/Temp/hpg-core-cache-bundle-20261101/`.
Grund: neue Kernidentität, historische Migration, Analyse-Routing und geänderter
Prüfstarter. Gesammelte Regressionen enthalten zusätzlich `fresh` ohne beide
Cache-Lookups/Schreiben und tatsächlichen zweimaligen Windows-Starter-Aufruf
mit getrennten Logs und einem Skriptpfad mit Leerzeichen/Klammern.
Keine Einzeltests vorher ausgeführt; ein Gesamtlauf mit vier xdist-Workern,
isolierter Coverage und unveränderter pytest.ini. Produkt/Testdateien eingefroren.
Noch kein Gesamtergebnis; bestehenden Prozess weiterverfolgen, nicht neu starten.

Cache-Migration inzwischen im Analysepfad eingebunden, noch ungeprüft:
`get_legacy_cached_core` liest begrenzt historische Zeilen, validiert Schema,
Dateiquellschlüssel und rekonstruierte Kern-/Rekordbox-Herkunft vor der
Entwertung veralteter Zusatzmerkmale. Alte Zeilen bleiben erhalten; nur ein
validierter Treffer wird als neuer Kernschlüssel gespeichert. `fresh` umgeht
weiterhin beide Cache-Lookups. Fünf SQLite-Regressionen zu Erfolg, geänderter
Quelle, Rekordbox, Kernlaufzeit und ungültigem Schema gesammelt. Kein Testlauf
ausgeführt. Offene Prüfung: Analyse-Integration/Migration und Starter gemeinsam;
danach tatsächliche Wiederverwendung vorhandener Originaltrack-Ergebnisse.

Migration fortgeführt: `legacy_fingerprint()` rekonstruiert den bisherigen
Gesamtschlüssel aus aktuellen Kernabhängigkeiten und genau zwei gespeicherten
Zusatzidentitäten. `legacy_core_matches()` verlangt außerdem passende Rekordbox-
Signatur und identische Herkunft im Neural-Snapshot. Ungültige/fehlende
Zusatzidentitäten werden abgewiesen. Regressionen für veränderte Kernmodelle,
Rekordbox-Herkunft und unvollständige Payloads gesammelt, noch nicht ausgeführt.
Einbindung in den Cache-Leser bleibt offen; keine produktiven Cacheänderungen.

### Aktuelle Testvorgabe des Nutzers

Tests auf das notwendige Minimum begrenzen. Änderungen und Prüffälle zuerst
sammeln, danach gemeinsam prüfen. Einzeltests nur bei konkreter Notwendigkeit.
Der bestandene Lauf `cleanup-full-20261101` bleibt Beleg seines gebundenen
Quellstands; kein neuer Lauf allein wegen einer Fortsetzung oder Dokumentation.
Der 26-Track-App-Lauf unter
`C:/Users/david/AppData/Local/Temp/hpg-native-acceptance-20261101-h2z8piod/`
wurde nach Abgleich mit vorhandenen Analysebelegen und den offenen
Abnahmepunkten gestartet; aktueller Prozessstand am Anfang dieses Dokuments.

Gesammelte Änderung nach dem letzten Gesamtlauf: Der Prüfstarter
`tools/launch_refactor_probe.ps1` referenzierte einen historischen TEMP-Pfad
und feste Lognamen. Er verlangt jetzt `-ProbeScript`, validiert die Datei und
schreibt pro Start in einen neuen Logordner. Diagnose aus dem Quellcode;
kein überschreibender Vorherlauf ausgeführt. Laufzeitprüfung noch offen,
mit dem nächsten erforderlichen Prüfblock bündeln. Der Starter isoliert
Startlogs; den internen App-Zustand isoliert weiterhin die angegebene Probe.

Neuer Befund aus dem Quellenabgleich, 01.11.2026:
Die sieben vorhandenen Analyse-Payloads bestehen zwar die Datenvalidierung,
aber keine ihrer gespeicherten neuronalen Identitäten entspricht dem aktuellen
`cue_service.fingerprint()`. Dieser bindet auch `deep_features.config_fingerprint()`
in den Kern-Cache-Key ein. Damit ist die frühere Aussage, der Embedding-Fix
erhalte automatisch den Kern-Cachetreffer, nicht belegt und durch den aktuellen
Identitätsvergleich widersprochen. Die gezielte Zusatzmerkmal-Erneuerung liegt
erst hinter diesem Lookup. Vor einer teuren Neuanalyse diesen Vertrag prüfen:
Zusatzmerkmale dürfen keine unnötige Wiederholung gültiger Kernanalyse erzwingen;
eine Migration darf alte Kernidentitäten nicht ungeprüft legitimieren.
Gesammelte nächste Scheibe: Cache-Identität/Abhängigkeiten samt Regression,
danach gemeinsamer Prüfblock mit dem Starter. Kein neuer Testlauf gestartet.
Rohbeleg: `C:/Users/david/AppData/Local/Temp/hpg-reuse-inventory-20261101-qe6jlpu8/report.json`.

Implementierung begonnen: `cue_service` bildet die Identitätsbestandteile
jetzt in einer gemeinsamen Funktion. `fingerprint()` behält den bisherigen
Gesamtvertrag; `core_fingerprint()` lässt ausschließlich Zusatzmerkmale aus
und liest deren Modellartefakte nicht. Zwei Regressionen gesammelt:
Zusatzänderung lässt Kernidentität stabil, Kernmodelländerung invalidiert;
Kernidentität verlangt keinen Zugriff auf Zusatzmodellartefakte.
Noch nicht ausgeführt. Die Analyse verwendet bis zur sicheren Migration
weiterhin die Gesamtidentität. Offen: validierte Wiedererkennung alter
Gesamtidentitäten, Einbindung in Cache-Lookup/Neural-Snapshot und gemeinsamer
Prüflauf. Keine alten Cache-Zeilen umgeschrieben und keinen Treffer behauptet.

Der Nutzer beauftragt eine weitere Refaktorierung und Bereinigung im gesamten
Projekt einschließlich Unterordnern. Bestehende Änderungen bleiben erhalten.
Ausführung weiterhin im bestehenden Checkout mit `superpowers:executing-plans`.

- [x] Verzeichnisinventar und Python-Syntax schreibgeschützt prüfen: 150
  Verzeichnisse, 360 Python-Dateien, keine Syntaxfehler oder doppelten Definitionen
  innerhalb desselben Modul-/Klassenbereichs. Rohbeleg:
  `C:/Users/david/AppData/Local/Temp/hpg-cleanup-20261101-inventory.json`.
  Git-Interna, Interpreter, generierte Python-/Pytest-Caches und geschützte
  Autopilot-Artefakte sind ausdrücklich keine Refaktorierungsziele.
- [x] Übergangshinweise zentral formatieren und an den aktiven Kandidatenplan
  binden: Regression für abweichende Taktzahl, Technik und Struktur vor dem Fix;
  beide Playlist-Einstiege prüfen. Zeitpunkte, Grenzen und Scores erhalten.
- [x] Übergangskarten bei langen Dateinamen innerhalb der verfügbaren Breite
  halten; echte Qt-Geometrie als Regression prüfen.
- [x] Dokumentationsverweise, Skill-Spiegel und Zuständigkeiten in allen
  projektseitigen Unterordnern abgleichen; nur belegte Redundanzen bereinigen.
- [x] Gezielt betroffene Tests, danach ein Abschluss-Volltest mit isolierter
  Coverage. Vorhandene Nachweise für unveränderte Bereiche weiterverwenden.
  Native App-Nachweise und musikalische Bewertung getrennt ausweisen.

Keine pauschale Dateilöschung. Laufzeitdaten, Sicherungen, Modellartefakte,
Konfigurationen, Musik und bestehende Coverage bleiben geschützt.

Nachweise dieser Runde:

- `transition_notes.py` bündelt Qt-freie Techniknamen, Formatierung und Bindung
  der Hinweismetadaten an den aktiven Kandidaten. Beide Playlist-Einstiege
  verwenden dieselbe Funktion. Generische EQ-Hinweise für die vorherige Technik
  werden entfernt; konkrete Ausführung bleibt im Plan/Renderer. Struktur wird
  an den aktiven Punkten gelesen, ohne bei fehlender Sektion eine Randsektion
  zu unterstellen. Zeitpunkte, Dauer, Scores und Grenzen werden nicht geändert.
- Regression vor Fix: `cleanup-notes-red2-20261101`, zwei erwartete Fehler
  wegen veralteter Takt-/Technik-/Strukturhinweise. Vorheriger `red`-Lauf enthielt
  zusätzlich einen Fixturefehler im Legacy-Einstieg; dieser wurde korrigiert,
  nicht als Produktfehler gewertet. Nachher 384 Tests bestanden unter
  `C:/Users/david/AppData/Local/Temp/hpg-refactor-0dac1b1a41724fc6a74d45106bb0c56c/`.
- Echte Qt-Geometrie bei 700/1100 px: vor Fix zwei Fehler mit horizontalem
  Überlauf, danach 19 Tests bestanden. Erster Korrekturlauf scheiterte am
  fehlenden QSizePolicy-Import; nach dessen Ergänzung erfolgreich:
  `C:/Users/david/AppData/Local/Temp/hpg-refactor-e3e034257afe44dd88630bb5059a75fa/`.
  Kartenstil auf die Karte begrenzt, damit Tabellenkopf und Kinder keine
  Kartenrahmen/-abstände erben. Titel umbrechen; Tabelle scrollt intern.
- Gemeinsamer Integrationslauf: 408 bestanden, 7,97 s, ohne Coverage:
  `C:/Users/david/AppData/Local/Temp/hpg-refactor-7993280001c540cfb99b147dc23a737d/`.
  Danach ausschließlich Qualitätsbadge-Titel und Track-Zähler übersetzt;
  diese Änderung wird vom laufenden Abschluss-Volltest mitgeprüft.
- Projektweite statische Importprüfung: 362 Python-Dateien und 1731 lokale
  Importverweise ohne fehlenden Modulpfad. Tools mit HPG-Imports enthalten
  die Parent-Pfad-Einbindung. Keine Aussage über jeden dynamischen Import.
  Rohbeleg: `C:/Users/david/AppData/Local/Temp/hpg-cleanup-20261101-imports.json`.
- Alle drei projektseitigen PowerShell-Skripte mit dem vorgeschriebenen
  Parser geprüft: `tools/run_refactor_checks.ps1`, `tools/launch_refactor_probe.ps1`,
  `.github/scripts/test_installer_runtime.ps1`; jeweils Syntax PASS. Daraus folgt
  keine Installer-/Build-Laufzeitabnahme; kein Build gestartet.
- Markdown-Verweise ohne fehlendes lokales Dateiziel; Skill-Spiegel identisch.
  Die 66 Gruppen identischer Markdown-Dateien bestehen aus gewollten
  Agent-/Skill-Spiegeln und zwei historischen Audit-/Sicherungspaaren. Erhalten,
  da Gleichheit hier kein Löschgrund ist. Rohbeleg:
  `C:/Users/david/AppData/Local/Temp/hpg-cleanup-20261101-docs.json`.
- Sichtbare native App mit sieben vorhandenen Originaltrack-Analysen geprüft:
  Karte bei 1100 px vollständig erreichbar; Kandidatenwechsel von 8 auf
  16 Takte aktualisiert Überlappung 13,5 → 27,0 s und Hinweis gemeinsam.
  Vier von sechs Grenzen geplant; isolierter Zustand, keine Neuanalyse und
  kein Cache-Lookup-Nachweis. App geordnet geschlossen, Prozess Exitcode 0.
  Beleg: `C:/Users/david/AppData/Local/Temp/hpg-app-goal-20261101-bmwg02w0/`.
  Vergleich zum vorherigen isolierten App-Ergebnis `lov21pgx`: gleiche
  Trackreihenfolge, gleiche Qualitätswerte, weiterhin vier geplante Grenzen.
- Abschlusslauf wegen Produktänderungen gestartet: `cleanup-full-20261101`,
  vier xdist-Worker, isolierte Coverage, unveränderte pytest.ini. Quell-/Test-
  Dateien währenddessen eingefroren. Exec-Session 22506; Rohbelege unter
  `C:/Users/david/AppData/Local/Temp/hpg-cleanup-full-20261101/`.
  Beendet mit Exitcode 0: **6478 bestanden**, **80,75 % Coverage**, 1139,99 s
  (18:59). Anschließender SHA-256-Abgleich aller 306 gebundenen Quell-/Testdateien:
  keine Änderung; `integrity.json` im selben Belegordner. Die konfigurierte
  Abwahl des Markers `slow` bleibt Teil des Prüfvertrags.

Diese zusätzliche Bereinigungsrunde ist umgesetzt und automatisch geprüft.
Der sichtbare App-Nachweis umfasst vorhandene Originaltrack-Analysen und den
Kandidatenwechsel. Vollständige frische Originaltrack-Analyse samt tatsächlicher
Cache-Wiederverwendung und musikalische Bewertung bleiben gesondert offen.
Kein neuer EXE-Build, Commit oder Push. Keine pauschale Fehlerfreiheit behauptet.

> Ausführung: superpowers:executing-plans; Umsetzung in diesem Chat.

**Goal:** Den bestätigten Gesamtentwurf in überprüfbaren Etappen umsetzen.
**Architecture:** Qt-freie Fachverträge und kleine zuständige Module; kompatible öffentliche Fassaden; ein Ergebnis für alle Verbraucher.
**Tech Stack:** vorhandenes Python 3.12/venv312, PyQt6, pytest.
**Spec:** ../specs/2026-10-30-gesamtrefaktorierung-design.md

## Globale Grenzen

AGENTS.md gilt. Originalmusik und Produktivzustand bleiben geschützt.
Keine Installationen oder kostenpflichtigen Aufrufe. Keine Änderung der
musikalischen Grenzen ohne nachgewiesenen fachlichen Grund. Keine Pushes oder Builds.

## Prüfschwerpunkte

Doppelte Trackvorkommen, verspätete Worker, fehlende lokale Messungen,
atomare Ergebnisveröffentlichung und Quellidentität bei Cache-Reuse.
Vorhandene Regressionen weiterverwenden; Charakterisierung vor Auslagerungen.

## Aufgaben

- [x] 1. Scoring-Grundlagen: scoring_primitives.py mit combine_weighted und
  VOCAL_CLASH_PENALTY; playlist re-exportiert; pair_candidates verwendet
  genres.resolve_track_genre direkt. Test: fehlende/Nullgewichte und reale Paarregressionen.
- [x] 2. Result-Verträge: playlist_results.py für unveränderliche Snapshots,
  TransitionPlan, Result-Typen und freeze/thaw; kompatible Imports. Test:
  test_playlist_generation_result.py und test_preview_result_contract.py.
- [x] 3. Playlist-Tabelle und Details: ui/playlist_columns.py, zentrale
  Identitäten; main.PlaylistPanel verwendet Definition und zeigt ausblendbare
  konkrete Track-/Übergangsdetails sowie erweiterte Spalten. Test: echte Qt-Tabelle,
  Auswahl, Reorder, leere Liste und doppelte Vorkommen.
- [x] 4. Ablaufsteuerung: UI-Worker/Publikation nach Abhängigkeitsprüfung
  trennen; RunState und atomare Veröffentlichung erhalten. Test:
  test_main_workers.py, test_main_window.py, Result-/Reorder-Regressionen.
- [x] 5. Analyse/Cache: gemeinsame Schritte für Vorprüfung und Finalisierung
  isolieren, Datenverträge erhalten, Messdiagnosen in Details anzeigen. Test:
  test_analyze_track.py, test_analysis_coverage.py, test_caching.py.
- [x] 6. Strategien/Timeline/Übergänge: zuständige Module und konsistente
  Ablehnungsdiagnose; geplante und ungeplante Grenzen sichtbar unterscheiden.
  Test: Scoring-, Timeline-, Kandidaten- und Renderer-Verträge.
- [x] 7. Projektweite Integration: Rekordbox, Export, Inferenz, ParallelAnalyzer,
  Buildimporte und Dokumentation gegen Migration prüfen; konkrete Defekte
  reproduzieren und korrigieren. Keine unbegründete Neuentwicklung.
- [x] 8. Technischer Abschluss: Volltest mit isolierter Coverage; nativer App-Ablauf und
  Cache-Reuse anhand Originaltracks; sichtbare Prüfung, unabhängiger Review.
  Musikalische Bewertung bleibt ohne menschliches Urteil offen.

## Fortschrittsprotokoll

30.10.2026: Entwurf vom Nutzer vollständig zur Umsetzung bestätigt.
Ruling: Arbeit auf codex/gesamtrefaktorierung im bestehenden Checkout;
damit bleiben venv/native Artefakte verfügbar. Keine Installation oder Kopie
von Musik/Cache. Nur der eigene Entwurf war untracked, sonst sauberer Ausgang.
Ruling: Rein strukturelle Änderungen werden durch Vorher-/Nachher-Verträge
belegt; kein erfundener RED-Bug für bereits korrektes Verhalten.
Neue Tests laufen gezielt ohne Coverage; der Abschlusslauf mit isolierter
COVERAGE_FILE und unveränderter pytest.ini. Jeder Lauf erhält einen benannten Grund.

### Laufende Umsetzung

Nachweisordner: `C:/Users/david/AppData/Local/Temp/hpg-refactor-03b4f107ad294ab8a3d32e86ba01ac1b`.
Keine Commits/Pushes/Builds ausgeführt. Branch `codex/gesamtrefaktorierung`.

- Scoring, Result-Typen, Timeline ausgelagert; vorher 253 Tests bestanden,
  nachher 258 einschließlich neuer Modul-/Pickleverträge (module-green.log).
- Playlistspalten zentralisiert; kompakte Ansicht, ausblendbare Details,
  Instanzzuordnung und Reorder-Rollback: ui-green.log 375 bestanden/1 abgewählt.
- Worker in app_workers.py, Zustände in run_state.py, Veröffentlichung in
  ui/result_publication.py. Kompatible Dienstgrenzen in main.py bleiben für
  Verbraucher und Tests erhalten. workers-green.log: 240 bestanden/1 abgewählt.
- Strategien in playlist_strategies.py mit expliziten StrategyServices;
  strategies-green.log: 224 bestanden. Kandidaten-DP in candidate_path.py.
- Zentrale Ablaufhinweise in Toolbar; workflow-green.log: 401 bestanden/1 abgewählt
  einschließlich DP, Strategie- und Qt-Regressionsfällen.
- Detaildiagnose verwendet vorhandene validierte Messansicht. Neuer Fehler
  unvalidierter Detailpayload RED/GREEN belegt; details-diagnostic-green.log:
  26 bestanden.
- Gemeinsamer Analyseabschluss in analysis_pipeline.py eingebunden;
  pipeline-red.log 6 erwartete Fehler,
  pipeline-green.log 6 bestanden.
- Vorherlauf Analyse/Cache: 509 bestanden (analysis-baseline.log). Danach
  Cachevalidierung und FeatureCache ausgelagert sowie Audio-/Rekordbox-Pfade
  in explizite Analysefunktionen getrennt. analysis-cache-green.log: 571 bestanden.
- Renderer-Spezifikation in transition_spec.py ausgelagert. Vorherlauf:
  20 Fehler durch veraltete librosa-Mocks; unveränderter Produktcode verwendete
  bereits preview_stretch.stretch. Tests auf die tatsächliche Dienstgrenze
  umgestellt, Erwartungen erhalten: render-test-contract-green.log 171 bestanden.
- tools/run_refactor_checks.ps1 mit vorgeschriebenem PowerShell-Prüfer validiert.
  Schreibt eindeutige Logs; Full-Schalter aktiviert Projekt-Coverage mit neuer Datei.

Offen: Reviewkorrekturen (Ansichtszustand, Coverage-Schutz), sichtbare deutsche
Oberfläche und Höhenbegrenzung, projektweiter Abschlusslauf,
native Originaltrack-App-Prüfung. Erster Volltest full-01 läuft; bisher ein Fehler
im nativen Hörtest. Unabhängiger schreibgeschützter Review durchgeführt.
26 Originaltracks unter F:/beatport_tracks_2026-04 sind vorhanden; bisher nicht
neu analysiert. Der historische Nachweisordner ist leer; der produktive Cache
enthält alte, nicht zum aktuellen Vertrag passende Daten und bleibt unberührt.
Eine isolierte native App wurde ohne Analyse gestartet; die sichtbare Prüfung
zeigte eine zu hohe erweiterte Einstellungsansicht, die noch korrigiert wird.

### Fortsetzung und Nachweisabgleich vom 01.11.2026

Der aktuelle Nutzerauftrag verlangt die vollständige, nachweisliche Erledigung
der offenen Implementierungen und Fehler. Die Checkboxen oben bleiben bis zum
Abgleich der jeweiligen Akzeptanzkriterien offen. Der frühere Zwischenstand
„full-01 läuft“ beschreibt keinen aktuellen Prozess.

- `full-02.json` und `full-02.log` im oben genannten Nachweisordner belegen
  6470 bestandene Tests, einen Fehler und 80,39 % Coverage. Die gespeicherten
  Quellhashes stimmten vor den Änderungen dieser Fortsetzung mit dem Checkout
  überein. Der Volltest ist fehlgeschlagen, nicht nachträglich grün.
- Einziger Fehler: echter Hörtest-Smoke, Timeout im Produktions-Initializer.
  Der isolierte Nachtest bestand unverändert (34,24 s Gesamtlauf):
  `C:/Users/david/AppData/Local/Temp/hpg-refactor-bac605bcd4bb42a1aab0526aad1902b3/hearing-smoke-repro-20261101.log`.
  Der Timeout unter Volltestlast ist damit nicht als behoben bewiesen.
- Konkreter Isolationsfehler: Der synthetische Diagnosemodus öffnete die echte
  Rekordbox-Bibliothek. Neuer Regressionstest reproduzierte diesen Zugriff;
  der normale Start wurde als Gegenprobe erhalten. Diagnose-Bootstrap setzt
  jetzt vor Produktimports `HPG_DISABLE_REKORDBOX=1`, auch für Spawn-Kinder.
  RED: `hpg-refactor-5ec4737f2957410d9ee8bb9cbd948d3c/smoke-isolation-red-20261101.log`
  unter TEMP (1 fehlgeschlagen, 1 bestanden). GREEN:
  `hpg-refactor-3f8b0b3cd83b4c139e60f6bfe3adee66/smoke-isolation-green-20261101.log`
  (32 bestanden, 38,43 s). Kein musikalischer oder vollständiger App-Nachweis.
- `native-app-final/events.json` endet mit `cancelled`, nicht Erfolg.
  Vier Fortschrittsmeldungen für 26 Dateien beweisen keine fertige Playlist.
  Der alte Prozess läuft nicht mehr. Historische Deep-Sky-/Playlist-Payloads
  fehlen; der 26er-Snapshotordner ist leer. Wiederverwendung darf nicht
  behauptet werden, solange kein gültiger Ersatzbeleg gefunden ist.
- Englische normale Analyse-Fortschrittsmeldungen waren in diesen Events
  sichtbar. Start-, Erfolgs- und Wiederherstellungstext sind nun deutsch;
  Statusmarker für Fehler bleiben kompatibel. Gezielte Regression läuft.

Historische Arbeitsmatrix vor den oben dokumentierten App-Läufen (keine aktuelle Abnahme):

| Anforderung | Zuständigkeit / nächster Beleg | Status |
|---|---|---|
| Finale Regression und Coverage | Nach den deutschen UI-Textkorrekturen: `%TEMP%/hpg-ui-language-full-20261107/ui-language-full-20261107.*`: 6704 bestanden, 81,17 % Coverage, Exit 0; `source-integrity.json`: 355 gebundene Dateien unverändert | für diesen Quell-/Teststand belegt |
| Sichtbare deutsche, in Bildschirmhöhe nutzbare App | MainWindow und vorhandene UI-Reviewbelege; sichtbarer Ablauf | teilweise belegt, sichtbare Abnahme offen |
| Einheitliches Ergebnis und Instanzidentität | Result-Verträge, Publikation, Reorder, Kandidatenwechsel, Export | vorhandene automatische Belege; echter Ablauf offen |
| Frische native Analyse und Cache-Reuse | 26-Track-App-Beleg `native-app-refiner-repaired` und `post-repair-cache-proof.json`: einmal Parallel Worlds frisch repariert, danach 26 Cachetreffer. Zusätzlich `hpg-fresh-original-20261107-kxptfups/report.json`: Umbral direkt am Quellort frisch analysiert, native Beats ok, isolierter Cache leer. | Teilabläufe belegt; vollständige frische Analyse, Paarbewertung und Playlist im selben App-Lauf nicht belegt |
| W/Deep Sky und ungeplante Grenzen | Spätere Paarprüfung in beiden Richtungen unter Mindestscore; sechs ungeplante Grenzen im reparierten 26er-Lauf diagnostiziert | keine zulässige W/Deep-Sky-Vorschau und kein menschliches Hörurteil; musikalische Optimierung offen |
| Übergangsvorschau aus vorhandenem App-Ergebnis | Plan 0 aus `native-app-refiner-repaired/result-refiner-final.json` und die zugehörigen Trackpayloads wurden über `TransitionClipSpec.from_plan` mit dem aktuellen Renderer gerendert: `%TEMP%/hpg-hearing-preview-20261107/01-Solarians-to-Dream-Desire.wav`, SHA-256 `e91358668154bab84d463fe987e56a074b19c0634fec82d9d58bacf3c50a791d` (am 07.11. erneut geprüft). 87,826 s, Stereo/44100 Hz, endliche Samples, Peak 0,94998. | Nutzerurteil am 07.11.: „ja der hört sich gut an“ für genau diesen Clip. Technischer Renderbeleg und positives subjektives Hörurteil für dieses Paar; frischer vollständiger App-Lauf und Qualität der ganzen Playlist offen. |
| Modell-/Codec-/Stem-/Embedding-Vertrag | `tests/test_native_reader_selection.py` prüft MP4/M4A-Codec-Routing und ALAC-Dimensionsablehnung mit Mutagen-Mocks; der Originaltrack-Kernlauf vom 07.11. belegt AIFF mit nativen Beats und aktivierter Stem-Verarbeitung. Die 26er-Sammlung enthält ausschließlich AIFF. In der bereits genannten Psy-Set-Quelle liegen zusätzlich ein MP3 (3745,6 s) sowie AAC in MP4 (5531,0 s) und M4A (11258,7 s). Die gebündelten Originaldatei-Reader-Proben `hpg-codec-reader-20261107-1i3mevbt/report.json` und `hpg-codec-reader-extra-20261107-74rxepo4/report.json` lasen aus MP3, AAC/MP4 und der Nutzer-WAV je 44100 endliche Stereo-Frames bei 44100 Hz; Quellgröße und Änderungszeit blieben gleich. Die M4A wurde mit `NativeContractError: Native reader duration exceeded` vor dem Dekodieren abgewiesen; Quelle unverändert. Ältere Embedding-Rohbelege bleiben separat. | MP3-/AAC/MP4-/WAV-Decoding für je eine Sekunde belegt, keine vollständige Analyse oder Modellbewertung dieser Dateien. M4A überschreitet das HPG-Dauerlimit von 7200 s. FLAC/ALAC in diesen zwei Quellen nicht gefunden. Unabhängige musikalische Genauigkeit offen. |
| Musikalische Qualität | unabhängige Referenzen und tatsächliches Hörurteil | offen |

Neue vom Nutzer bereitgestellte Referenz:
`E:/02_Musik_Audio/Audio_Clips/Psy-Set/02 Mai Podcast 19 - Kopie.wav`
und `E:/03_Video_Medien/Film_4/Tracklist_youtube (1).txt`.
WAV-Header lesbar: Stereo, 44100 Hz, PCM16. Trackliste: 18 Zeitmarken,
zwei ausdrücklich unklare Zuordnungen. Sie ist keine unabhängig verifizierte
Beat-/Takt-/Phrasenannotation und keine Freigabe zur automatischen Kalibrierung.
Originaldateien bleiben am Quellort. Dateinamensuche fand DNA Activation und
zwei Liquid-Hook-Versionen in der Psytrance-Sammlung; akustische Identität und
Eignung als Paar sind dadurch noch nicht bewiesen.

Weitere aktuelle Rohbelege:

- Vollständiger Mix dekodiert: 243917336 Frames, 44100 Hz Stereo,
  5531,005351 s (92:11,005), 93 zusammenhängende Pegelfenster. Kein vorzeitiges
  Dateiende oder nicht endliche Samples; Größe und Änderungszeit unverändert.
  `C:/Users/david/AppData/Local/Temp/hpg-reference-20261101-mb2ayj_i/reference-input.json`.
  Dieser technische Eingangsbeleg identifiziert keine Tracks und bewertet keine Übergänge.
- Sieben Datensätze aus der isolierten `native-app-final/cache.db` bestehen
  den aktuellen Trackvalidator; Quellidentitäten und Cachekeys zur gespeicherten
  Signatur stimmen überein. Die heutige Rekordbox-Signatur wurde dabei noch
  nicht neu ermittelt. Metadatenbeleg:
  `C:/Users/david/AppData/Local/Temp/hpg-goal-evidence-20261101-kkqijooj/inspection.json`.
  Drei Stem-Ergebnisse sind vorhanden; vier weitere melden `service_error:EOFError`.
- Vier Embedding-Ergebnisse enthalten den konkreten Produktfehler
  `NameError: name 'EMBEDDING_WINDOW_SECONDS' is not defined`.
  Ursache im aktuellen `deep_feature_worker.py`: lokaler Import in `generate`,
  Verwendung in der anderen Funktion `_generate_embedding`. Regression für
  Dispatcher, echte 29-s-Fensterbildung, Restfenster und gewichtete Aggregation
  wird vor dem Fix ausgeführt. Kein erneuter Stem-Lauf dafür erforderlich.

Erledigte Korrekturen und laufende Prüfung:

- ParallelAnalyzer-Nachtest: 63 bestanden, 335,33 s.
  `C:/Users/david/AppData/Local/Temp/hpg-refactor-39004fd26179480d993827488fe5d4ee/parallel-status-20261101.log`.
- Embedding-Regression reproduzierte exakt den `NameError` aus den Originaltrack-
  Ergebnissen: `hpg-refactor-c47f8f23d04d4e4bb1f7860b61611d57/embedding-window-red-20261101.log`
  unter TEMP. Der Import steht jetzt zusätzlich im verwendenden Funktionsbereich.
  37 Tests für Worker, Merkmale, Wiederverwendung und Predictor bestanden:
  `hpg-refactor-d94e86518b024a03956dbfdf0fe16e21/embedding-window-green-20261101.log`.
  Die Inferenzgrenze im neuen Regressionstest ist kontrolliert ersetzt;
  tatsächliche Modellinferenz mit Originalaudio bleibt gesondert nachzuweisen.
- Cacheentscheidung: kein globaler Cache-Bump für diesen isolierten Modellfix.
  `config_fingerprint` bindet den funktionsbezogenen `producer_digest`, und
  `dict_to_track`/Deep-Feature-Refresh prüfen diesen Vertrag. Embedding-Digest:
  vorher `812be5c8bc256e84cd1f182e59ad7fe92fb6c164288243e7c5234c9c346037b2`,
  danach `fc6ee6d6f0332a81c99ed1163086bddad5cbd32e3b82c3f6c60f1a4c40f45e8f`.
  Stem-Digest unverändert:
  `8af0d48ac09293f2bb0c90288679b00f41fbfb9d64b0c36f58eb2331d71f2460`.
  Der bestehende lokale Import in `generate` wird bewusst erhalten, damit
  dessen im Stem-Produzenthash enthaltener Code keine fertigen Stems entwertet.
- Neuer Volltest ist durch Änderungen an Diagnose-Bootstrap, Fortschrittsmeldungen
  und Embedding-Worker begründet. Befehl über `tools/run_refactor_checks.ps1 -Full`
  entspricht `venv312/Scripts/python.exe -m pytest tests/ --tb=short -q`;
  eigene Coverage, vier xdist-Worker wie im vorhandenen Vergleichslauf.
  Während des Laufs keine Änderungen an Produkt- und Testdateien.
  Laufender Rohbeleg:
  `C:/Users/david/AppData/Local/Temp/hpg-refactor-38653b8149dc41579a3b3869b329d2b6/full-goal-20261101-01.log`.
  Zugehöriges Manifest im selben Ordner; Exec-Session 69679. Letzte Beobachtung:
  Prozess noch aktiv, 15 % im Log. Das ist kein Testergebnis. Fortsetzung am
  selben Handle; keinen zweiten Volltest starten. Danach tatsächliche
  Originalaudio-Embedding-Inferenz und App-Abnahme weiterführen.
  Spätere Beobachtung in derselben Session: 97 %, weiterhin aktiv. Der zuvor
  fehlgeschlagene `test_source_smoke_actual_qt_spawn_ram_dsp_from_unrelated_directory`
  ist in diesem Volltest bestanden. Ein Gesamtergebnis steht noch aus.
  Vorbereiteter, noch nicht ausgeführter Originalaudio-Prüflauf:
  `C:/Users/david/AppData/Local/Temp/hpg-embedding-original-20261101.py`.
  Er verwendet den Produktbroker, erneuert ausschließlich das fehlgeschlagene
  Umbral-Embedding, prüft unveränderte Stems und Quell-SHA-256, schreibt nur
  neue Metadatenbelege. Erst nach Ende des laufenden Volltests starten.

### Volltest und tatsächlicher Originalaudio-/App-Nachweis, 01.11.2026

- Volltest `full-goal-20261101-01` beendet, Exitcode 0: **6474 bestanden**,
  **80,72 % Coverage**, 1158,19 s. Alle 304 im Manifest gebundenen Quell-/Test-
  Dateien anschließend erneut gehasht: keine Abweichung. Konfigurierte
  `slow`-Abwahl gemäß pytest.ini bleibt Teil der Beweisgrenze.
- Originalaudio-Embedding mit unverändertem Produktbroker ausgeführt:
  `C:/Users/david/AppData/Local/Temp/hpg-embedding-original-20261101-gn8o6l1_/report.json`.
  Umbral, 370,140861678 s, 13 Fenster, 6,83 s; Ausgabevalidator und Track-
  Roundtrip bestanden, vorhandene Stems unverändert, Original-SHA-256 vor/nach
  identisch. Gemeldete Sessionprovider: DmlExecutionProvider und CPUExecutionProvider.
  Das beweist keine ausschließliche GPU-Ausführung und keinen musikalischen Nutzen.
- Echte sichtbare Qt-App ohne Mocks, sieben vorhandene validierte Analysen,
  2-BPM-Grenze, Harmonic Flow: sieben Tracks veröffentlicht, vier von sechs
  Übergängen geplant. Zwei Grenzen sichtbar wegen Tempoabstand ungeplant.
  Isolierter Zustand und Result-Pickle:
  `C:/Users/david/AppData/Local/Temp/hpg-app-goal-20261101-lov21pgx/`.
  Harness: `C:/Users/david/AppData/Local/Temp/hpg-app-goal-20261101.py`.
  Kein frischer Analyse- oder tatsächlicher Cache-Lookup-Nachweis: vorhandene
  Track-Payloads wurden in die echte App-Pipeline gegeben.
- Erste Vorschau per sichtbarem App-Button gerendert, von Qt aus RAM geladen,
  Wiedergabe gestartet und pausiert. Umbral 142 → Source of Reality 143 BPM;
  pro_eq_swap, Mix-Out 220,985442 s, Mix-In 60,419841 s, Überlappung 13,521127 s;
  30 s Vor-/Nachlauf, PCM16/Stereo/44100 Hz, Gesamtlänge 73,52 s. App meldete
  Vorschau bereit; strikte Synchronprüfung nicht deaktiviert. Kein menschliches
  Klangurteil. App danach geordnet geschlossen, Exec-Session 67424 Exitcode 0.

Neue sichtbare Befunde für die nächste Korrektur (nicht als erledigt markieren):

Nachprüfung der Reihenfolge am 01.11.2026 nach der Bereinigungsrunde:
24 Permutationen der letzten vier Originaltracks mit unverändertem Kontext,
2-BPM-Grenze und tatsächlicher Kandidaten-DP geprüft, 18 Paar-Rankings.
Keine Variante erreicht mehr als vier geplante Grenzen. Die tempoverträgliche
Grenze Voices 137 → Eternal 135 liefert null qualifizierte Kandidaten:
Passung unter Mindestwert sowie unregelmäßige/unvollständige native Beatfolge
im Übergangsfenster. Eine bessere Sortierung allein behebt diese Lücke in
diesem Suchraum nicht. Die beste geprüfte Variante verbessert lediglich die
Scoresumme von 3,0349527921 auf 3,0871418428; kein musikalischer Qualitätsbeleg
und keine globale Optimalitätsaussage. Produktcode unverändert, keine Analyse
oder Cache-Erneuerung. Rohbeleg:
`C:/Users/david/AppData/Local/Temp/hpg-chain-audit-20261101-qdqlyrfq/report.json`.
Damit ist der Verdacht einer allein durch BPM-Sortierung vermeidbaren Lücke
eingegrenzt; frische Analyse-/Cache-Abnahme bleibt der nächste offene Nachweis.

1. **Widersprüchliche DJ-Hinweise:** derselbe aktive Übergang zeigt 8 Takte und
   13,5 s, im DJ-Text jedoch `Transition: 24 bars`. Ursache eingegrenzt:
   `playlist.py::_recommendation_snapshot` übernimmt bereits formatierte
   `dj_notes` aus `_process_dj_brain_recommendations`, setzt danach nur Zeiten
   und `overlap_seconds`, nicht den bereits erzeugten Text bzw. `transition_bars`.
   Auch Mixtechnik-/Strukturtexte müssen gegen den aktiven Plan geprüft werden.
   Regression vor Fix; unveränderter Plan bis Anzeige/Preview/Export ist der Vertrag.
2. **Übergangsansicht überbreit:** lange Titel/Kandidatentabelle erzwingen horizontales
   Scrollen der gesamten Karte; rechte Inhalte sind bei 1100 px Fensterbreite
   abgeschnitten. Tabellen dürfen intern scrollen, die Bedienung muss erreichbar bleiben.
3. **Noch englische sichtbare Texte:** `OVERALL`, `HARMONY`, `ENERGY`, `7 tracks`,
   diverse Übergangshinweise. Deutsche Oberfläche bleibt unvollständig.
4. **Reihenfolge prüfen:** 135/137/138/138-BPM-Untergruppe wird aktuell so angeordnet,
   dass eine 138→135-Grenze ungeplant bleibt. Eine bessere vollständige lokale
   Kandidatenkette ist noch nicht nachgewiesen. Nicht allein aus BPM auf einen
   Suchfehler schließen; mit eingefrorenen Originaltrack-Kandidaten vergleichen.

Neue Referenzdateikandidaten wurden unter `E:/02_Musik_Audio/Sammlung_Final`
gefunden: Let There Be Light, DNA Activation, Liquid Hook (Original/Fabio Fusco/
Zentura-Datei), Museum of Dreams, Swimming in Acid, We Are Not Toys und The Journey
Begins. Dateinamen sind weiterhin kein akustischer Identitätsbeleg.

### Abgleich der vier historischen UI-/Reihenfolge-Befunde vom 01.11. am 07.11.

1. Der veraltete `24 bars`-Text wird im aktuellen Code aus dem aktiven Kandidaten
   neu gebildet (`hpg_core/transition_notes.py`); die Regression in
   `tests/test_playlist_generation_result.py` prüft 8 statt 24 Takte und
   verwirft veraltete Technik-/Strukturtexte. Im gemeinsamen Gesamtlauf vom
   07.11. enthalten. Keine neue Hörabnahme daraus ableiten.
2. `tests/test_mix_tips_layout.py` prüft bei 700 und 1100 px, dass lange Titel
   die Karte nicht horizontal verschieben; die Kandidatentabelle scrollt intern.
   Im selben Gesamtlauf enthalten. Sichtbare Nutzerabnahme bleibt offen.
3. Die zuvor genannten `OVERALL`/`HARMONY`/`ENERGY` stehen im aktuellen
   `main.py` als `GESAMT`/`HARMONIE`/`ENERGIE`; Status- und Tabellentexte sind
   ebenfalls deutsch. Das beweist keine vollständige Sprachprüfung jeder Ansicht.
4. Die 24-Permutationen-Diagnose unmittelbar oben widerlegt für den geprüften
   eingefrorenen 4-Track-Suchraum eine alleinige Sortierkorrektur: höchstens
   vier geplante Grenzen. Die sechs ungeplanten 26er-Grenzen und musikalische
   Eignung bleiben offen; ohne neue Referenz keine Gates aufweichen.

Die native Rekordbox-Beatpipeline bindet hashgepinntes `tensorflow_cc.dll`
und ruft die Modell-RVAs in einem Einmalprozess auf
(`native_beat_pipeline_worker.py`, `native_beat_boundaries.py`). Ihr aktueller
Aufrufvertrag enthält keinen belegten GPU-Adapterparameter. Die gemessene
iGPU-Last dieses Prozesses ist deshalb noch nicht sicher auf die RX 7800 XT
umgestellt. Das HPG-ONNX-Device-Fix betrifft diesen separaten Pfad nicht.
Der Nutzer entschied am 07.11. ausdrücklich: **iGPU frei halten; nativen
26-Track-Lauf vorerst aussetzen.** Deshalb keinen weiteren nativen
Rekordbox-Modelllauf zur App-Abnahme starten, solange diese Vorgabe gilt.
Der gemeinsame pytest-Lauf ist davon getrennt und wurde beendet:
`%TEMP%/hpg-ui-language-full-20261107/`, 6704 bestanden, 81,17 % Coverage,
Exit 0, 1112,70 s. Das SHA-256-Manifest bindet 355 Quell-/Test-/Tooldateien;
nach Testende keine Änderung (`source-integrity.json`). Dies bestätigt weder
einen frischen vollständigen Originaltrack-App-Lauf noch musikalische Qualität.

Ein separater, isolierter Qt-App-Lauf mit **sieben vorhandenen** Track-Snapshots
und deaktivierter KI veröffentlichte nach diesen Textkorrekturen sieben Tracks,
vier von sechs geplanten Übergängen und den Status `success`; Prozess-Exit 0.
Beleg `%TEMP%/hpg-app-ui-current-20261107-b9fju3rk/` (`events.json`,
`result.json`, `window.png`). Der Lauf nutzte Qt `offscreen`, keinen frischen
Audio-/Cache-Lookup und keinen nativen Modellaufruf. Die Offscreen-Aufnahme
zeigt Schrift als Ersatzkästchen; sie ist daher **kein** Beleg für lesbare
sichtbare Beschriftungen oder Nutzerabnahme. Die frühere sichtbare App-Probe
vom 01.11. betrifft einen anderen Quellstand.
Die Ursache der Ersatzkästchen ist die leere Qt-Schriftdatenbank im
`offscreen`-Plugin (`QFontDatabase.families() == []`). Ein erneuter isolierter
App-Lauf lud die vorhandene Windows-Consolas-Schrift ausschließlich im
Prüfharness (`QFontDatabase.addApplicationFont`); derselbe Snapshot-Ablauf
endete mit Exit 0, sieben veröffentlichten Tracks und vier von sechs geplanten
Übergängen. In `%TEMP%/hpg-app-ui-font-current-20261107-irhk462f/window.png`
sind Kennzahlen, Tabelle und Bedienelemente lesbar. Die beiden roten Grenzen
bleiben als „Kein Übergang“ sichtbar. Es ist weiterhin eine virtuelle
Offscreen-Ansicht mit bestehenden Analysen, kein frischer Audio-/Cache-Lauf,
keine physische Nutzerbedienung und kein musikalisches Urteil.

## EXE-Laufzeitkorrektur vom 07.11.2026

Der erste gebaute EXE-Stand `ce2e978f` startete die GUI, aber seine
Analyse-Worker stürzten in der 26-Track-Analyse mit `0xc0000005` ab.
Windows-Fehlerereignis 1000 nannte bei einem gezielten Ein-Track-Lauf
`MSVCP140.dll` aus dem gebündelten PyQt6-Verzeichnis (Version 14.26).
Dieser Ein-Track-Lauf scheiterte auch mit `HPG_STEMS=0` und
`HPG_NATIVE_BEAT=0` (Exit 1). Der synthetische EXE-Smoke-Test bestand;
damit war nur der einfache Spawn- und DSP-Transport belegt.

`HPG.spec` filtert nun die fünf alten VC-Laufzeitkopien aus
`PyQt6/Qt6/bin`. Auf diesem Windows-Rechner steht die neuere installierte
VC-Laufzeit 14.51 zur Verfügung. Der zweite Build enthält laut
`EXE-00.toc` keine dieser PyQt6-Kopien. Derselbe Originaltrack-Workerlauf
bestand sowohl mit deaktivierten als auch mit den normalen nativen
Analysefunktionen (je Exit 0); in den letzten drei Minuten des zweiten
Laufs wurde kein zugehöriges Windows-Absturzereignis gefunden.
Der gemeinsame Abschlusslauf bestand 6706 Tests bei 80,99 % Coverage:
`%TEMP%/hpg-vc-runtime-full-20261107/vc_runtime_full_20261107.log`.
Die abschließend neu gebaute und separat geprüfte EXE liegt unter
`%TEMP%/hpg-exe-dist-vcfix-final-20261107/HarmonicPlaylistGenerator.exe`,
SHA-256 `FB46812453B4A62B771E2283FAFDF30E23630DD7ED8AABF6E5D8D92BADEA225A`.
Ihr synthetischer EXE-Smoke-Test und der Originaltrack-Workerlauf mit normaler
Analyse endeten je mit Exit 0. Windows meldete im Zeitfenster des letzten
Laufs keinen zugehörigen Absturz. Das finale `EXE-00.toc` enthält keine
PyQt6-VC-Laufzeitkopien.
Dies ist ein gezielter Worker-Nachweis, kein erneuter 26-Track-EXE-App-Lauf
und keine Prüfung auf Windows-Systemen ohne installierte VC-Laufzeit.
