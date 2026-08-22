# Handoff 2026-08-22: Gesamtstand fuer einen neuen Agenten

Ziel dieses Dokuments: Ein Agent, der das Repo frisch klont, soll **denselben
Wissensstand** haben wie der Agent der Sessions vom 20.–22.08.2026 — Code,
Plaene, Entscheidungen des Nutzers, Skills, Subagenten und das
Sitzungsgedaechtnis (Memory) — und an exakt der Stelle weitermachen, an der
dieser Agent aufgehoert hat (Abschnitt 3).

Vorheriger Handoff: `docs/HANDOFF-2026-08-21-kandidaten-design.md`.
Stand dieses Dokuments: Abend 2026-08-22, nach Merge von Teil 3.

## 0. Arbeitsmodus (Nutzer-Anweisung 2026-08-22, `/goal`)

„Dein finales Ziel ist es, die App in diesem Repository komplett fehlerfrei und
produktionsreif fertigzustellen. Ab sofort arbeitest du zu 100% autonom. […] Du
fragst mich nicht nach Erlaubnis fuer Zwischenschritte. […] Start-Analyse: Scanne
als allererstes das gesamte Projektverzeichnis nach den neuesten Plaenen,
Statusberichten oder Notizen. […] Audio-Tests: Alle Aufgaben, die eine
menschliche Hoerprobe erfordern, ueberspringst du. Dokumentiere sie fuer mich
auf einer finalen Checkliste und arbeite sofort am naechsten Punkt weiter.
Melde dich erst mit einer Erfolgsmeldung zurueck, wenn alles rundherum komplett
fertiggebaut, getestet und gegengeprueft ist." — Caveman-Modus, Subagenten und
Skills aus `.agents/` nutzen, keine Platzhalter, alles messen.

## 1. Reihenfolge zum Einlesen (Pflicht)

1. `CLAUDE.md` (Projektregeln, Waechter-Pflicht, Skills, venv312)
2. `docs/agent-memory/MEMORY.md` + alle Dateien darin (Abschnitt 5) —
   besonders `hpg-stand-2026-08-22-teil1-gemerged.md` (Einstieg)
3. `.agents/skills/hpg-orientation/SKILL.md`, dann `hpg-mixpoint-engineering`,
   `hpg-playlist-scoring`, `hpg-testing-verification`, `hpg-qt-gui`
4. `docs/superpowers/specs/2026-08-21-mixpunkt-kandidaten-design.md`
   (Abschnitte 1–4 vom Nutzer genehmigt, **exakt so umsetzen**)
5. Handoffs der gebauten Teile: `docs/HANDOFF-2026-08-22-kandidaten-teil1.md`,
   `-teil2.md`, `-teil3.md` (Messzahlen, Entscheidungen, Waechter-Urteile,
   Checkliste Hoerproben)
6. `docs/superpowers/plans/2026-08-22-mixpunkt-kandidaten-teil4-app.md` (+
   `2026-08-22-faktenblatt-kandidaten-teil4.md`)
7. dieses Dokument, Abschnitt 2–4

Regel aus CLAUDE.md gilt weiter: Statusdokumente sind Hypothesen, der Code
ist die Wahrheit. Jede Zahl und Zeilenreferenz vor Gebrauch im Code
nachpruefen.

## 2. Branch-Lage

| Branch | Stand | Inhalt |
|---|---|---|
| `main` | `2d1684b` (Merge Teil 4) ueber `5ce9ddb` (Merge Teil 3), `ca15013` (Merge Teil 2), `f18815b` (Merge Teil 1) | Teil 1–4 komplett: Teil 4 = App-Anbindung (`candidate_choices.py`, Kandidatenpfad in `playlist.py` mit Kettenwahl, GUI-Kandidatentabelle, Regler Lautheit, BPM 2.0, Export `HPG K<n>`, `tools/playlist_kandidaten_messen.py`); Teil 1–3: `mix_candidates.py`, `rekordbox_phrases.py`, `pair_candidates.py`, `candidate_preferences.py`, `models.camelot_relation_score`, `kandidaten_*_weight`, Hoertest-Kandidatenmodus (`tools/rate_transitions.py`, `tools/hoertest_server.py`), Werkzeuge `tools/kandidaten_messen.py`, `tools/paar_kandidaten_messen.py` |
| `kandidaten-teil1/2/3/4` | geloescht (lokal), Worktrees entfernt | vollstaendig in `main` |

Suite auf `main` nach Merge Teil 4 (HEAD `2d1684b`): **1871 passed, 25 warnings, Exit 0, 85 s** (Coverage-Gate
70 bestanden); `compileall` und Import-Rauchtest (`main`, `hpg_core.playlist`,
Exporter) sauber; `ruff` zeigt nur vorbestehende Stil-Treffer in `main.py` (E402).

## 3. Wo genau weitergemacht wird

- **Teil 4 (App) ist gebaut, gemessen, vom Waechter an beiden Toren geprueft
  (Tor 2: MIT AUFLAGEN, eingearbeitet) und gemerged** — Handoff
  `docs/HANDOFF-2026-08-22-kandidaten-teil4.md` (20 Entscheidungen, Messung:
  220/230 Paare mit Kandidat, Intro/Outro-Verletzungen 0, Overlap-Abweichungen 0,
  Cue-Gate 2 = Ketten-Neustarts, Score-Median 79 vs. 83, Generierung 51 s vs. 2 s).
- Die Spec 2026-08-21 (Abschnitte 1–4) ist damit vollstaendig umgesetzt. Was
  bleibt, sind ausschliesslich Hoerproben (Mensch) — Checkliste unten in
  Abschnitt 6 bzw. in den Handoffs Teil 3/4 — und die Uebernahme der
  Hoertest-Gewichte (`fit --modus kandidaten`), die den Startwerten folgt.
- Naechste Arbeit ohne Hoerprobe: keine offen. Wer weiterbaut, beginnt mit
  Abschnitt 6 und den Handoffs.
- Nutzer-Auflagen (Memory): alles komplett, nichts "spaeter", keine Annahmen,
  jede Zahl gemessen oder als Startwert markiert, nie den einfacheren Weg
  empfehlen, Waechter an beiden Toren.

## 4. Skills und Subagenten — wo sie liegen

- Versioniert: `.agents/skills/hpg-*/SKILL.md` (14 Skills) und
  `.agents/agents/hpg-*.md` (10 Subagenten, darunter `hpg-waechter`).
- `.claude/` ist per `.gitignore:69` **unversioniert**. Auf einem frischen Klon
  fuer Claude Code einmalig spiegeln:

  ```powershell
  New-Item -ItemType Directory -Force .claude\skills, .claude\agents | Out-Null
  Copy-Item -Recurse -Force .agents\skills\hpg-* .claude\skills\
  Copy-Item -Force .agents\agents\hpg-*.md .claude\agents\
  ```

  Wer einen Skill aendert, aendert **beide** Kopien; die `.agents`-Kopie ist
  die einzige, die im Repo landet.

## 5. Sitzungsgedaechtnis (Memory) — `docs/agent-memory/`

Kopie der Claude-Code-Memory dieses Projekts (18 Dateien inkl. Index
`MEMORY.md`). Ein neuer Claude-Code-Agent auf einem anderen Rechner legt sie
unter `%USERPROFILE%\.claude\projects\<projekt-slug>\memory\` ab; jeder andere
Agent liest sie als Markdown und behandelt sie wie eigene Notizen.

Wichtigste Eintraege: `hpg-stand-2026-08-22-teil1-gemerged.md` (Einstieg),
`hpg-kandidaten-design-vollstaendig-bauen.md`, `hpg-praezision-vor-einfachheit.md`,
`hpg-mixpunkte-individuell-cues-phrasen.md`, `hpg-waechter-und-agententeam.md`,
`hpg-scoring-an-2026-08-21.md`, `hpg-mixpoint-rundungsfehler.md`,
`hpg-venv312-environment.md`, `hpg-rekordbox-doppelte-pfade.md`,
`user-smiley-am-ende.md` (jede Antwort an David endet mit `:-)`).

## 6. Offen (gesammelt)

- Hoerproben (Mensch): Checklisten in `docs/HANDOFF-2026-08-22-kandidaten-teil3.md`
  (Kandidaten-Satz vorbereiten, bewerten, `fit --modus kandidaten`) und
  `docs/HANDOFF-2026-08-22-kandidaten-teil4.md` (App-Preview der Kandidaten,
  Wahl-Klick, Ketten-Neustarts, Regler, Rekordbox-Import der `HPG K`-Cues).
- Generierung mit Kandidaten ~52 s fuer 231 Tracks (2 s ohne) — gemessen, keine
  Kappung; bei groesseren Sammlungen waechst es mit den Paaren im 2-BPM-Gate.
- #4 Melodic Techno: wartet auf Noten
- `docs/PLAYLIST_ALGORITHMEN_ERKLAERUNG.md` ("10 Strategien") und
  `HANDOFF-2026-08-20-groove-scoring.md:189` veraltet
- Memory `hpg-mixpoint-rundungsfehler.md`: 57/200 Tracks mit Mix-In in einer
  Intro-Sektion (Invariante 5), vorbestehend, ungeprueft
- Teil-1-Startwerte `KICK_AKTIV_*` markieren fast nie einen Kick (82/3664);
  `percussive_ratio_lokal` zur Haelfte < 0.3 (Handoff Teil 1/2)
- `HPG.spec` buendelt `hpg_core/data/*.json` nicht (Waechter-Hinweis Teil 3,
  Release-Build pruefen: `hpg-release-build`)
- `docs/AGENT_HANDOFF.md` beschreibt den Stand 2026-07-20 und verweist oben
  auf dieses Dokument.
