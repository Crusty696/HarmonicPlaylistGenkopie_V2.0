---
name: hpg-veritas
description: Fuehrt evidenzbasierte, read-only Forensik-Audits des HPG-Repositories mit drei unabhaengigen Paessen, getrenntem Verifikator, reproduzierbarem Findings-Merge und kontrollierter Wissenssynchronisation aus. Nur fuer ausdrueckliche Voll-, Delta- oder Release-Audits; nicht fuer normale Bugfixes.
---

# HPG VERITAS

Ein Aufruf orchestriert acht Rollen. Projektcode bleibt read-only. Schreibbar
sind nur ein explizites Laufverzeichnis, `tools/audit/` sowie die in
`tools/audit/sync_targets.json` erlaubten Wissensziele.

## Pflicht-Reads

1. `hpg-orientation`
2. `hpg-audit-optimize`
3. `hpg-testing-verification`
4. [protocol.md](references/protocol.md)
5. [finding-format.md](references/finding-format.md)

Lade danach nur die HPG-Fach-Skills, die der Audit-Scope beruehrt.

## Start

1. Lies `git status --short`, `git log --oneline -10` und den aktuellen Code.
2. Schreibe einen pruefbaren Auftrags-Kontrakt. Keine stillen Scope-Annahmen.
3. Initialisiere einen frischen Lauf:

```bat
.\venv312\Scripts\python.exe tools\audit\veritas.py init-run ^
  --run-dir <absoluter-laufordner> --scope "<scope>"
```

`init-run` uebernimmt aktive Regeln aus `tools/audit/learnings.json`. Jeder
Pass muss jede aktive Regel fuer jede Fachrolle als `treffer`, `sauber` oder
`nicht_anwendbar` quittieren; sonst verweigert der Merge.

4. Pruefe den erzeugten `environment.json`. Fehlende oder versionsfalsche
   Werkzeuge sind ein offener Punkt; nie automatisch installieren oder durch
   ein anderes Werkzeug ersetzen.
5. Nutze die Rollen unter `.agents/agents/veritas-*.md`. Pass 1 und Pass 2
   muessen frische, voneinander unabhaengige Kontexte und verschiedene
   `file_order_seed`-Werte haben. Wenn das nicht moeglich ist, ist der Lauf
   unvollstaendig und darf nicht als Drei-Pass-Audit bezeichnet werden.

## Drei Paesse

- Pass 1: Vollscan im vereinbarten Scope.
- Pass 2: unabhaengige Wiederholung mit anderer Dateireihenfolge.
- Pass 3: kennt A und B; sucht Blindstellen, Randbereiche und wiederkehrende
  Fehlerklassen.

Jede Rolle quittiert jedes anwendbare aktive Learning. Pass-Dateien liegen als
`pass-1/findings.json`, `pass-2/findings.json`, `pass-3/findings.json` vor.
Validiere jede Datei vor dem Merge:

```bat
.\venv312\Scripts\python.exe tools\audit\veritas.py validate-pass ^
  --input <pass-findings.json>
```

## Merge und Verifikation

```bat
.\venv312\Scripts\python.exe tools\audit\veritas.py merge ^
  --run-dir <laufordner>
```

Nur derselbe Fingerprint in mindestens zwei Paessen wird `BESTAETIGT`, und nur
wenn `severity` und `confidence` uebereinstimmen. Ein-Pass-Befunde bleiben
`UNBESTAETIGT`. Abweichende `severity` oder `confidence` ergeben `WIDERSPRUCH`
und werden nie still gemittelt.

Abweichend formulierte `claim`, `impact` und `category` sind KEIN Widerspruch --
zwei unabhaengige Paesse schreiben praktisch nie dieselben Saetze. Sie werden als
`varianten` gefuehrt und im Bericht nebeneinander gezeigt. Umgekehrt gilt: gleiche
Prosa in Pass 1 und Pass 2 -- verglichen nach Normalisierung von Whitespace und
Gross-/Kleinschreibung -- ist kein Reproduktionsbeleg, sondern ein Hinweis auf
nicht unabhaengiges Arbeiten. Der Merge vermerkt das als `hinweise` und zaehlt
es im Berichtskopf. Im zurueckgezogenen Lauf `veritas-mixanalysis-2026-09-03`
traf das 22 von 22 gemeinsamen Befunden, im unabhaengigen `veritas-playlist-20260903`
keinen einzigen. Der frische Verifikator prueft danach
jeden Befund gegen Roh-Evidenz; ungepruefte Befunde bleiben unbestaetigt.

## Wissen synchronisieren

Der Wissens-Synchronisator arbeitet nur ueber das deterministische Skript.
Zuerst immer Dry-Run:

```bat
.\venv312\Scripts\python.exe tools\audit\sync_knowledge.py ^
  --run-dir <laufordner>
```

Erst wenn Plan, Zielpfade und Waisenliste korrekt sind:

```bat
.\venv312\Scripts\python.exe tools\audit\sync_knowledge.py ^
  --run-dir <laufordner> --apply
```

Das CLI akzeptiert absichtlich keine alternative Sync-Konfiguration. Das
einzige produktive Zielprofil ist `tools/audit/sync_targets.json`; Aenderungen
daran sind normaler, pruefbarer Repository-Diff.

Nie `_raw/`, `00_Claude_Memory/`, Cache/DB/Locks oder
`Claude-Autopilot-*` schreiben.

In einer Befund-Notiz schreibt der Sync ausschliesslich den Block zwischen
`VERITAS:GENERATED:START` und `:END`, die generierten Frontmatter-Felder und
die Ueberschrift, solange sie noch die erzeugte Form `# V-001 - ...` hat.
Betrachtet wird dafuer nur die ERSTE nicht leere Zeile; steht dort nicht die
erzeugte Form, bleibt der Kopf unangetastet und der Titel eingefroren. Der
Titel ist immer einzeilig -- ein mehrzeiliger Claim wird zusammengezogen.
Alles andere bleibt erhalten: eigene Felder, eigene Ueberschriften, eigene
Abschnitte und der `Nutzerkommentar`. Der Status gehoert dem Nutzer. Bei
`tags` wird eine einzeilige Inline-Liste vereinigt. Steht sie im Blockstil
(`tags:` und darunter `  - x`), traegt sie nur einen Kommentar, oder schliesst
die Klammer erst in einer Folgezeile, bleibt sie unangetastet und die
generierten Tags fehlen -- eine Inline-Liste darueber zu schreiben zerstoerte
das ganze Frontmatter, also auch Status und eigene Felder.

Enthaelt IRGENDEINE Stelle des generierten Blocks eine Zeile, die einer
Markerzeile exakt gleicht -- Zitat, `impact`, `rule`, `path` --, schreibt der
Sync dort `-- >` statt `-->` und weist das mit einer Hinweiszeile unter dem
Beweis aus. Ueberschrift und generierte Frontmatter-Werte werden zusaetzlich
auf eine Zeile zusammengezogen: dort ist Mehrzeiligkeit schon fuer sich
schaedlich, weil der Rueckbau zeilenweise ersetzt und die Notiz sonst bei
jedem Lauf waechst. Der Text im Vault ist an diesen Stellen nicht mehr
byteweise exakt; die Laufdatei unter `tools/audit/runs/` bleibt es, und der
volle Claim steht unverkuerzt im generierten Block.
Fehlen die Marker, wird die Datei nicht angefasst.

Learning-Notizen unter `Learnings/` sind KEINE Bestandsnotizen: sie werden
bei jedem `--apply` vollstaendig neu geschrieben, ohne Markerbereich, ohne
Fingerprint-Pruefung, ohne Statusuebernahme und ohne Konfliktpfad. Eigene
Ergaenzungen darin gehen verloren. Seit die Vereinigung greift, gilt das auch
fuer Learnings, die nur im Bestand stehen -- sie sind keine Waisen mehr,
sondern Ziele. Wer dort eigenen Text braucht, legt ihn ausserhalb von
`Learnings/` ab.

`tools/audit/learnings.json` wird ueber die `id` vereinigt, nicht ersetzt --
Wissen aus frueheren Laeufen bleibt erhalten. Ein Learning behaelt genau die
Quellen, die im Bestand schon an ihm hingen; jede andere Quelle muss ein
Befund dieses Laufs sein. Der vereinigte Stand wird vor dem Rendern genauso
geprueft wie der Lauf. GitHub-Issues brauchen eine neue,
ausdrueckliche Freigabe.

## Abschluss-Gate

Ein Lauf ist nur abgeschlossen, wenn:

- alle drei Pass-Dateien valide sind;
- der unabhaengige Verifikator jeden bestaetigten Befund akzeptiert hat;
- `sync_knowledge.py --apply` mit `sync_difference_count = 0` endet und keine
  `konflikte` meldet. `orphan_count` zaehlt getrennt: Waisen entstehen, wenn
  eine Befund-ID wegfaellt, und `--apply` entfernt sie nie. Sie blockieren das
  Gate nicht, sind aber Handarbeit und muessen bewertet werden;
- gemeldete `konflikte` geklaert sind. Eine Notiz mit fremdem `fingerprint`,
  unbekanntem Statuswert, ohne lesbares Frontmatter, ohne VERITAS-Marker oder
  mit mehr als einem generierten Block gehoert dem Nutzer und wird nicht
  ueberschrieben. CRLF-Notizen fallen NICHT darunter: `Path.read_text`
  normalisiert die Zeilenenden beim Lesen, und der Sync schreibt sie mit LF
  zurueck. `mehrfache VERITAS-Marker` meldet nur ein zweiter Startmarker
  INNERHALB des Blocks -- hinter dem Endmarker liegt Nutzerterritorium, dort
  wird nichts geprueft und nichts angefasst;
- angewendete Learnings und Ergebnisse im Bericht stehen;
- offene Fragen, fehlende Werkzeuge und nicht gepruefte Bereiche genannt sind;
- der Bericht auf Deutsch ist und jede User-Nachricht mit `:-)` endet.
