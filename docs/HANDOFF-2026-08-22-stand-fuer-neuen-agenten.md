# Handoff 2026-08-22: Gesamtstand fuer einen neuen Agenten

Ziel dieses Dokuments: Ein Agent, der das Repo frisch klont, soll **denselben
Wissensstand** haben wie der Agent der Sessions vom 20.–22.08.2026 — Code,
Plaene, Entscheidungen des Nutzers, Skills, Subagenten und das
Sitzungsgedaechtnis (Memory) — und an exakt der Stelle weitermachen, an der
dieser Agent aufgehoert hat (Abschnitt 3).

Vorheriger Handoff: `docs/HANDOFF-2026-08-21-kandidaten-design.md`.

## 1. Reihenfolge zum Einlesen (Pflicht)

1. `CLAUDE.md` (Projektregeln, Waechter-Pflicht, Skills, venv312)
2. `docs/agent-memory/MEMORY.md` + alle Dateien darin (Abschnitt 5) —
   besonders `hpg-stand-2026-08-22-teil1-gemerged.md`
3. `.agents/skills/hpg-orientation/SKILL.md`, dann
   `hpg-mixpoint-engineering`, `hpg-playlist-scoring`
4. `docs/superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md`
   (Abschnitte 1–4 vom Nutzer genehmigt, **exakt so umsetzen**)
5. `docs/superpowers/plans/2026-08-21-mixpunkt-kandidaten-teil1-datenmodell.md`
   (gebaut, gemerged — zeigt das Planformat und die Waechter-Auflagen)
6. `docs/superpowers/plans/2026-08-22-faktenblatt-kandidaten-teil2.md`
7. `docs/superpowers/plans/2026-08-22-entwurfsnotizen-kandidaten-teil2.md`
8. dieses Dokument, Abschnitt 2–4

Regel aus CLAUDE.md gilt weiter: Statusdokumente sind Hypothesen, der Code
ist die Wahrheit. Jede Zahl und Zeilenreferenz vor Gebrauch im Code
nachpruefen.

## 2. Branch-Lage (Stand 2026-08-22, nach dem Merge)

| Branch | Stand | Inhalt |
|---|---|---|
| `main` | `f18815b` (Merge) + Doku-Commits danach | **Teil 1 (Datenmodell) gemerged**: `hpg_core/mix_candidates.py`, `hpg_core/rekordbox_phrases.py` (PSSI-Leser), Kandidatenfelder in `models.py`, CACHE_VERSION 34, Kandidaten in beiden Analysepfaden, Cue-Positionsheuristik entfernt, `tools/kandidaten_messen.py`, Skills/CLAUDE.md aktualisiert |
| `kandidaten-teil1` | **geloescht** (lokal + remote), Worktree entfernt | vollstaendig in `main` |
| `feature/groove-scoring`, `audit/2026-08-14-messbasierte-fixes` | alt, in `main` enthalten | nur Historie |

Merge-Verifikation am 2026-08-22: Suite auf `main` nach dem Merge
`1786 passed, 25 warnings, 81 s, Exit-Code 0` (Coverage-Gate 70 bestanden),
Aufruf `venv312\Scripts\python.exe -m pytest tests/ --tb=short -q -p no:cacheprovider`.

`.claude/skills` und `.claude/agents` wurden nach dem Merge aus `.agents/`
gespiegelt (lokal; `.claude/` ist gitignored, siehe Abschnitt 4).

## 3. Wo genau weitergemacht wird

### 3a. Plan Teil 1, Task 12 — Rest

- **Realmessung an den 231 analysierten Tracks** (`tools/kandidaten_messen.py
  --liste <tracks231.txt> --json <out.json>`): am 2026-08-22 gestartet.
  Ergebnis und Pflichtzahlen stehen in
  `docs/HANDOFF-2026-08-22-kandidaten-teil1.md`, sobald vorhanden. **Fehlt
  diese Datei, ist die Messung nicht dokumentiert → neu laufen lassen**
  (Trackliste aus `hpg_cache_v33.db`, Spalte `filepath`, `key <> 'version'`
  ausschliessen; sqlite3-CLI nicht im PATH, Python nutzen; Dauer > 30 min,
  detached starten).
- Danach ist Teil 1 komplett abgeschlossen.

### 3b. Teil 2 — Paarung und Bewertung (NICHT begonnen)

Stand: Vorarbeit liegt vor, Plan NICHT geschrieben, Waechter Tor 1 NICHT
gelaufen, Nutzer hat die Entwurfsnotizen NICHT gesehen.

Reihenfolge:
1. `2026-08-22-entwurfsnotizen-kandidaten-teil2.md` Abschnitt 10: die
   offenen Messwerte aus der Kandidaten-Messung ablesen (Einheit
   `avg_mids_lokal`, Spannen `bass_rms_dbfs`/`lufs_lokal`, Anteil leeres
   `camelot_lokal`).
2. Die offenen Entscheidungen aus den Entwurfsnotizen dem Nutzer vorlegen
   (Benannter-Cue-Ausnahme am Blenden-Guard; eigene
   `kandidaten_*_weight`-Schluessel; Startwerte) — **eine praezise Frage je
   Punkt**, Empfehlung = die praezisere Variante (Nutzer-Regel
   `hpg-praezision-vor-einfachheit`).
3. Plan nach `superpowers:writing-plans` als
   `docs/superpowers/plans/2026-08-22-mixpunkt-kandidaten-teil2-paarung.md`
   im Format von Teil 1 (Task 0 = Waechter Tor 1, TDD je Task, Commit je
   Task, letzter Task = Messung + Doku + Waechter Tor 2).
4. Umsetzung im eigenen Branch/Worktree (`superpowers:using-git-worktrees`;
   Worktree hat kein venv — `venv312` des Hauptrepos nutzen), Merge ueber
   `superpowers:finishing-a-development-branch`, Nutzer-Vorgabe: am Ende
   alles auf `main`.
5. Danach Teil 3 (Hoertest-Modus Kandidaten) und Teil 4 (App) nach
   demselben Muster — Spec Abschnitte 3 und 4.

Nutzer-Auflagen (Memory `hpg-kandidaten-design-vollstaendig-bauen`,
`hpg-praezision-vor-einfachheit`): alles komplett, nichts "spaeter", keine
Annahmen, jede Zahl gemessen oder als Startwert markiert, nie den
einfacheren Weg empfehlen, Waechter an beiden Toren.

## 4. Skills und Subagenten — wo sie liegen

- Versioniert: `.agents/skills/hpg-*/SKILL.md` (14 Skills) und
  `.agents/agents/hpg-*.md` (10 Subagenten, darunter `hpg-waechter`).
- `.claude/` ist per `.gitignore:69` **unversioniert** (bewusste
  Entscheidung, Waechter Tor 1, Commit `8732d5d`). Auf einem frischen Klon
  fuer Claude Code daher einmalig spiegeln:

  ```powershell
  New-Item -ItemType Directory -Force .claude\skills, .claude\agents | Out-Null
  Copy-Item -Recurse -Force .agents\skills\hpg-* .claude\skills\
  Copy-Item -Force .agents\agents\hpg-*.md .claude\agents\
  ```

  Wer einen Skill aendert, aendert **beide** Kopien; die `.agents`-Kopie ist
  die einzige, die im Repo landet.
- Der `consulting-team`-Skill unter `.agents/skills/` gehoert nicht zu HPG.

## 5. Sitzungsgedaechtnis (Memory) — `docs/agent-memory/`

Kopie der Claude-Code-Memory dieses Projekts (18 Dateien inkl. Index
`MEMORY.md`, Stand 2026-08-22 nach dem Merge). Ein neuer Claude-Code-Agent
auf einem anderen Rechner legt sie unter
`%USERPROFILE%\.claude\projects\<projekt-slug>\memory\` ab, dann werden sie
automatisch geladen; jeder andere Agent liest sie als Markdown und behandelt
sie wie eigene Notizen.

Die fuer die aktuelle Arbeit wichtigsten Eintraege:

- `hpg-stand-2026-08-22-teil1-gemerged.md` — dieser Stand, Einstiegspunkt.
- `hpg-kandidaten-design-vollstaendig-bauen.md` — Auflage des Nutzers:
  Spec genau so, komplett, keine Annahmen, 100 % ehrlich.
- `hpg-praezision-vor-einfachheit.md` — nie den einfacheren Weg
  empfehlen; alle Faktoren gewichtet (Groove, Rhythmus, Harmonie, Lautheit,
  BPM max 2); Design-Entscheidungen C/B/A+B/C/C/Weg 2.
- `hpg-mixpunkte-individuell-cues-phrasen.md` — keine Einheitsregel fuer
  Mixpunkte; Kandidaten anbieten; PSSI-Phrasen unter
  `D:\PIONEER\Master\share\PIONEER\USBANLZ\...\ANLZ0000.EXT`.
- `hpg-waechter-und-agententeam.md` — Waechter VOR der Umsetzung.
- `hpg-scoring-an-2026-08-21.md`, `hpg-mixpoint-rundungsfehler.md`,
  `hpg-groove-scoring-2026-08-20.md` — Scoring-/Mixpoint-Vorgeschichte.
- `hpg-venv312-environment.md`, `hpg-rekordbox-doppelte-pfade.md` —
  Umgebung und Realdaten.
- `user-smiley-am-ende.md` — jede Antwort an David endet mit `:-)`.

Diese Kopie ist ein Schnappschuss. Bei Widerspruch gilt der Code.

## 6. Offen (unveraendert aus dem vorigen Handoff)

- App-BPM-Default 3.0 → 2.0 (Teil von Abschnitt 4 der Spec)
- #4 Melodic Techno: wartet auf Noten
- `docs/PLAYLIST_ALGORITHMEN_ERKLAERUNG.md` ("10 Strategien") und
  `HANDOFF-2026-08-20-groove-scoring.md:189` veraltet
- Memory `hpg-mixpoint-rundungsfehler.md`: 57/200 Tracks mit Mix-In in einer
  Intro-Sektion (Invariante 5), vorbestehend, ungeprueft
- `docs/AGENT_HANDOFF.md` beschreibt den Stand 2026-07-20 und verweist oben
  auf dieses Dokument.
