# Handoff 2026-08-22: Gesamtstand fuer einen neuen Agenten

Ziel dieses Dokuments: Ein Agent, der das Repo frisch klont, soll **denselben
Wissensstand** haben wie der Agent der Sessions vom 20.–22.08.2026 — Code,
Plaene, Entscheidungen des Nutzers, Skills, Subagenten und das
Sitzungsgedaechtnis (Memory).

Vorheriger Handoff: `docs/HANDOFF-2026-08-21-kandidaten-design.md`.

## 1. Reihenfolge zum Einlesen (Pflicht)

1. `CLAUDE.md` (Projektregeln, Waechter-Pflicht, Skills, venv312)
2. `docs/agent-memory/MEMORY.md` + alle Dateien darin (siehe Abschnitt 5)
3. `.agents/skills/hpg-orientation/SKILL.md`, danach den fachlich passenden Skill
4. `docs/superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md`
   (Abschnitte 1–4 vom Nutzer genehmigt, **exakt so umsetzen**)
5. `docs/superpowers/plans/2026-08-21-mixpunkt-kandidaten-teil1-datenmodell.md`
6. dieses Dokument, Abschnitt 2–4

Regel aus CLAUDE.md gilt weiter: Statusdokumente sind Hypothesen, der Code
ist die Wahrheit. Jede Zahl vor Gebrauch im Code nachpruefen.

## 2. Branch-Lage (Stand 2026-08-22)

| Branch | Stand | Inhalt |
|---|---|---|
| `main` | `3d9535a` + dieser Handoff-Commit | Spec, Plan Teil 1, Waechter-Auflagen Tor 1 (nur Doku) |
| `kandidaten-teil1` | `4865586`, 21 Commits vor `main` | **Teil 1 (Datenmodell) gebaut**: `hpg_core/mix_candidates.py`, `hpg_core/rekordbox_phrases.py` (PSSI-Leser), `MixCandidate`-Felder in `models.py`, CACHE_VERSION 34, Kandidaten in beiden Analysepfaden, Cue-Positionsheuristik entfernt, `tools/kandidaten_messen.py`, Skills/CLAUDE.md aktualisiert; Waechter Tor 2 durchlaufen (Auflagen eingearbeitet, Commit `4865586`) |
| `feature/groove-scoring`, `audit/2026-08-14-messbasierte-fixes` | alt, bereits in `main` | nur Historie |

Lokal lag `kandidaten-teil1` als Worktree unter
`..\HPG-wt-kandidaten-teil1` (ohne eigenes venv — Tests dort mit dem
`venv312` des Hauptrepos laufen lassen).

**Nicht auf main gemerged.** Der Nutzer sagte "am Ende alles auf main
mergen"; der Merge ist Teil von Task 12 Step 6 des Plans und soll ueber
`superpowers:finishing-a-development-branch` erfolgen. Das ist der naechste
Schritt, sobald die offenen Punkte in Abschnitt 3 erledigt sind.

Testlauf `kandidaten-teil1` am 2026-08-22: siehe Abschnitt 6.

## 3. Offen aus Plan Teil 1 (Task 12) — vor dem Merge

- **Step 1–2: Realmessung an den 231 analysierten Tracks** mit
  `tools/kandidaten_messen.py` (Liste aus `hpg_cache_v33.db`, Spalte
  `filepath`, `key <> 'version'` ausschliessen; sqlite3-CLI nicht im PATH,
  Python nutzen). Pflichtzahlen fuer den Handoff Teil 1:
  `intro_outro_verletzungen` (muss 0), `ohne_in`/`ohne_out`, Median
  Kandidaten je Seite, Schemaverteilung, `mit_pssi` (erwartet nahe 231),
  Analysezeit-Median je `build_track_candidates` aus dem Log.
  **Im Repo ist keine solche Messung dokumentiert** — gilt als nicht gemacht.
- **Step 4: Handoff `docs/HANDOFF-<Datum>-kandidaten-teil1.md`** mit den
  Messzahlen — fehlt noch.
- **Step 6: Push + Merge auf main.** Push des Branches erfolgt mit diesem
  Handoff; Merge offen (Nutzer-Entscheidung, siehe oben).
- Nach dem Merge: `.agents/skills/*` → `.claude/skills/*` und
  `.agents/agents/*` → `.claude/agents/*` kopieren (Abschnitt 4).

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

  Am 2026-08-22 waren beide Spiegel auf `main` inhaltlich identisch (nur
  CRLF/LF-Unterschied). Wer einen Skill aendert, aendert **beide** Kopien;
  die `.agents`-Kopie ist die einzige, die im Repo landet.
- Der `consulting-team`-Skill unter `.agents/skills/` gehoert nicht zu HPG.

## 5. Sitzungsgedaechtnis (Memory) — `docs/agent-memory/`

Kopie der Claude-Code-Memory dieses Projekts vom 2026-08-22 (17 Dateien,
Index `MEMORY.md`). Ein neuer Claude-Code-Agent auf einem anderen Rechner
legt sie unter
`%USERPROFILE%\.claude\projects\<projekt-slug>\memory\` ab, dann werden sie
automatisch geladen; jeder andere Agent liest sie als Markdown.

Die fuer die aktuelle Arbeit wichtigsten Eintraege:

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

Diese Kopie ist ein Schnappschuss. Quelle bleibt die Memory des jeweiligen
Agenten; bei Widerspruch gilt der Code.

## 6. Verifikation am 2026-08-22

- `main`: Working Tree sauber, 2 Doku-Commits vor `origin/main` (vor diesem
  Handoff), danach gepusht.
- `kandidaten-teil1`: Working Tree sauber; Testlauf mit
  `venv312\Scripts\python.exe -m pytest tests/ --tb=short -q -p no:cacheprovider`
  aus dem Worktree — Ergebnis siehe Nachtrag unten.

## 7. Offen (unveraendert aus dem vorigen Handoff)

- App-BPM-Default 3.0 → 2.0 (Teil von Abschnitt 4 der Spec)
- Teil 2 (Paar-Bewertung), Teil 3 (Hoertest-Modus Kandidaten), Teil 4 (App)
  — je eigener Plan nach `docs/superpowers/plans/`, Waechter an beiden
  Toren je Schritt
- #4 Melodic Techno: wartet auf Noten
- `docs/PLAYLIST_ALGORITHMEN_ERKLAERUNG.md` ("10 Strategien") und
  `HANDOFF-2026-08-20-groove-scoring.md:189` veraltet
- Memory `hpg-mixpoint-rundungsfehler.md`: 57/200 Tracks mit Mix-In in einer
  Intro-Sektion (Invariante 5), vorbestehend, ungeprueft

## Nachtrag: Testlauf kandidaten-teil1

Gemessen 2026-08-22 im Worktree `HPG-wt-kandidaten-teil1` (HEAD `4865586`), mit
`venv312` des Hauptrepos, `pytest.ini`-Defaults (`-n auto`, Coverage-Gate 70):
**1786 passed, 25 warnings, 87 s, Exit-Code 0** (Coverage-Gate bestanden).
