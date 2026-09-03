# VERITAS-Protokoll

## Verfassung

- Befund = nachpruefbarer Claim plus Roh-Evidenz. Annahmen sind keine Befunde.
- Projektcode, Musik, Rekordbox, Cache, DB, Locks und private Artefakte bleiben
  unveraendert.
- Der Laufvertrag definiert Scope, Ausschluesse, erlaubte Ausgaben,
  Invarianten und Abschlussbedingungen.
- Tool- und Python-Versionen werden aus `toolchain.lock.json` geprueft und in
  `environment.json` festgehalten. Seed und Dateireihenfolge stehen pro Pass.
- Status `BESTAETIGT` erfordert denselben Fingerprint in mindestens zwei
  Paessen bei gleicher `severity` und `confidence` und
  Akzeptanz durch einen frischen Verifikator.
- Ein Lauf mit fehlendem Pass, fehlender Evidenz oder Sync-Differenzen bleibt
  offen.

## Rollen

| Rolle | Vertrag |
|---|---|
| Orchestrator | `.agents/agents/veritas-orchestrator.md` |
| Statiker | `.agents/agents/veritas-static.md` |
| Dynamiker | `.agents/agents/veritas-dynamic.md` |
| Audio/DSP | `.agents/agents/veritas-audio.md` |
| Integration | `.agents/agents/veritas-integration.md` |
| GUI/Threading | `.agents/agents/veritas-gui.md` |
| Verifikator | `.agents/agents/veritas-verifier.md` |
| Wissen | `.agents/agents/veritas-knowledge.md` |

Rollen duerfen weitere read-only Fachpruefungen vorbereiten. Nur Orchestrator
merged. Nur Wissens-Synchronisator darf das Sync-Skript mit `--apply` starten.

## Pass-Unabhaengigkeit

Pass 2 erhaelt nur Laufvertrag, Scope, aktive Learnings, Umgebung und Code.
Keine Pass-1-Befunde oder -Zusammenfassung. `agent_context_id` und
`file_order_seed` muessen verschieden sein -- das prueft der Merge, es ist aber
nur eine Beschriftung. Der echte Beleg ist die Sprache: sind `claim` und
`impact` zwischen Pass 1 und Pass 2 zeichengleich, war der Text uebernommen und
nicht zweimal erarbeitet. Der Merge zaehlt solche Befunde, weist sie am Befund aus
und nennt die Summe im Berichtskopf. Er blockiert nicht -- die Bewertung
trifft der Verifikator. Ein Lauf mit solchen Hinweisen darf erst dann als
Drei-Pass-Audit gelten, wenn sie geklaert sind. Pass 3 erhaelt A und B.

## Learning-Loop

`learnings.json` ist strukturiert. Quellen sind Befund-IDs. Jede Anwendung
enthaelt Pass, Rolle, Ort und Ergebnis `treffer`, `sauber` oder
`nicht_anwendbar`. Ein Learning darf nur dann `applied` hochzaehlen, wenn eine
solche Quittung existiert. Nach zwei manuellen Anwendungen prueft der
Orchestrator, ob ein deterministischer Check moeglich ist. Regel-Aenderungen
werden als Diff vorgelegt und brauchen Nutzerfreigabe.

Der persistente Speicher ist `tools/audit/learnings.json`. `init-run` kopiert
ihn in den neuen Lauf; erst der kontrollierte Sync schreibt den validierten
Laufstand zurueck. `LESSONS.md`, Vault-Notes und `active-learnings.md` werden
daraus generiert.

## Ehrlichkeitsgrenze

Gruene Tests beweisen technische Regressionen im geprueften Bereich, nicht
musikalische Qualitaet. Audio-Claims brauchen Ground Truth oder menschlichen
Hoertest. Nicht installierte Tools, fehlende Testdaten und nicht reproduzierte
Fehler werden explizit genannt.
