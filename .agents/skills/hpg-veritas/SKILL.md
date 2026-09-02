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

Nur derselbe Fingerprint in mindestens zwei Paessen wird `BESTAETIGT`.
Ein-Pass-Befunde bleiben `UNBESTAETIGT`. Widerspruechliche Claims werden
`WIDERSPRUCH` und nie still gemittelt. Der frische Verifikator prueft danach
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
`Claude-Autopilot-*` schreiben. Vault-Status und `Nutzerkommentar` gehoeren
dem Nutzer und werden nicht ueberschrieben. GitHub-Issues brauchen eine neue,
ausdrueckliche Freigabe.

## Abschluss-Gate

Ein Lauf ist nur abgeschlossen, wenn:

- alle drei Pass-Dateien valide sind;
- der unabhaengige Verifikator jeden bestaetigten Befund akzeptiert hat;
- `sync_knowledge.py --apply` mit `sync_difference_count = 0` endet;
- angewendete Learnings und Ergebnisse im Bericht stehen;
- offene Fragen, fehlende Werkzeuge und nicht gepruefte Bereiche genannt sind;
- der Bericht auf Deutsch ist und jede User-Nachricht mit `:-)` endet.
