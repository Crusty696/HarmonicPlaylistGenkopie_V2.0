# consulting-team — Installation

Ein Multi-Persona Consulting-Skill für Claude. Funktioniert in **Claude Code**, **Claude Desktop** und **Cowork** mit identischer Auslieferung.

## Was der Skill macht

7 Consulting-Rollen analysieren deine Ideen, Pläne oder Konversationen — strikt anti-sycophantisch, mit Pyramid-Principle-Struktur und Caveman-komprimierter Persona-Interna für Token-Effizienz.

Details siehe `SKILL.md`.

---

## Installation

### Option A: Claude Code (Linux/macOS/WSL)

```bash
# Skills-Verzeichnis (falls noch nicht da)
mkdir -p ~/.claude/skills

# Skill kopieren
cp -r consulting-team ~/.claude/skills/

# Verifizieren
ls ~/.claude/skills/consulting-team/
# Erwartete Ausgabe: SKILL.md  personas/  frameworks/  references/  INSTALL.md
```

Bei nächster Claude-Code-Session wird der Skill automatisch erkannt.

### Option B: Claude Code (Windows nativ)

PowerShell:

```powershell
# Skills-Verzeichnis
$skillsDir = "$env:USERPROFILE\.claude\skills"
New-Item -ItemType Directory -Force -Path $skillsDir

# Skill kopieren (Pfad anpassen an dein Download-Verzeichnis)
Copy-Item -Recurse -Force ".\consulting-team" "$skillsDir\"

# Verifizieren
Get-ChildItem "$skillsDir\consulting-team\"
```

### Option C: Claude Desktop

Claude Desktop liest Skills aus demselben Verzeichnis wie Claude Code:

- **macOS/Linux:** `~/.claude/skills/`
- **Windows:** `%USERPROFILE%\.claude\skills\`

Gleiche Installation wie A/B. Claude Desktop neu starten nach Installation.

### Option D: Cowork

Cowork liest User-Skills automatisch aus dem Skills-Verzeichnis. Installation analog zu A/B/C. Falls Cowork ein eigenes Skills-Verzeichnis nutzt (kann sich ändern): in den Cowork-Settings unter "Skills" das Verzeichnis prüfen.

Nach Installation ist der Skill in allen Cowork-Sessions verfügbar.

### Option E: claude.ai (Web)

Skills können via "Skills" Sektion in den Settings hochgeladen werden. Den Ordner `consulting-team` als `.skill`-Archiv hochladen (Anleitung in der claude.ai-UI).

---

## Verifikation der Installation

In einer neuen Claude-Session:

```
User: Liste mir alle verfügbaren Skills auf.
```

`consulting-team` sollte in der Liste erscheinen.

Oder direkt testen:

```
User: /consulting-team Soll ich für meine Audio-Pipeline asyncio statt QThread nutzen?
```

Wenn der Skill triggert: du bekommst einen vollständigen Report mit Executive Summary, Findings nach Severity, Steel-Man-Gegenposition, Open Questions und Recommendation.

---

## Trigger-Phrasen

Der Skill triggert auf:

**Explizite Trigger:**
- `/consulting-team`, `/ct`
- "consulting team review"
- "challenge meinen Plan"
- "team-meinung zu X"
- "macht das Sinn"
- "pre-mortem für X"

**Soft-Trigger (proaktiv):**
- User präsentiert substantielle Idee/Plan/Architektur
- One-way-door-Entscheidung steht an (Stack, Architektur, Tool-Wahl)
- User äußert Selbstzweifel an einem Plan

**NICHT triggert:**
- Reine Code-Implementierungs-Tasks (dafür `code-auditor`, `full-stack-auditor`)
- Faktische Fragen ("was ist X")
- Trivial-Tasks

---

## Caveman-Integration

Der Skill nutzt Caveman-Stil **intern** für die 6 Spezialisten-Personas, um Tokens zu sparen (~50-70% Reduktion). Der finale Synthesizer-Report bleibt lesbares Deutsch.

Wenn der separate Caveman-Skill (Julius Brussee) bereits installiert ist: kein Konflikt, beide arbeiten unabhängig.

---

## Anpassung

### Domain-Expert auf eigenen Stack erweitern

Editiere `personas/domain-expert.md`, Abschnitt "Domains, die der Domain Expert kennt". Liste hier deine Stacks und Frameworks auf, damit der Expert sie als bekannt behandelt.

### Trigger-Schwelle anpassen

Standardmäßig ist der Skill *eher pushy* (er triggert auch ohne explizite Aufforderung bei substantiellen Plänen). Wenn du das nicht willst:

In `SKILL.md`, Frontmatter `description:` — den Satz "IMMER nutzen wenn der User eine Idee, einen Plan, eine Architektur..." entfernen oder durch "Nur bei expliziter Aufforderung nutzen" ersetzen.

### Verbotene Phrasen erweitern

Editiere `references/anti-sycophancy.md`, Sektion "Verbotene Phrasen". Eigene Lieblings-Floskeln, die dich nerven, hier eintragen.

---

## Deinstallation

```bash
# Linux/macOS/WSL
rm -rf ~/.claude/skills/consulting-team
```

```powershell
# Windows
Remove-Item -Recurse -Force "$env:USERPROFILE\.claude\skills\consulting-team"
```

---

## Troubleshooting

### Skill triggert nicht

1. Prüfe Pfad: `~/.claude/skills/consulting-team/SKILL.md` muss existieren
2. Frontmatter im `SKILL.md` muss intakt sein (zwischen `---` Zeilen)
3. Claude-Session neu starten
4. Explizit aufrufen mit `/consulting-team`

### Skill triggert zu oft

Trigger-Schwelle anpassen (siehe oben).

### Output ist nicht kritisch genug

1. `references/anti-sycophancy.md` lesen — werden die Regeln befolgt?
2. Im Prompt explizit nachhaken: "Sei kritischer. Steel-Man die Gegenposition."
3. Wenn Synthesizer zustimmend wirkt: er bricht den Selbst-Test in `personas/synthesizer.md`

### Synthesizer-Output zu lang

Im Prompt: "Verkürze den Report auf das Essential." Synthesizer ist instruiert, knapp zu bleiben, aber Pyramid Principle erlaubt Granularitäts-Anpassung.

---

## Weiterentwicklung

PRs, Issues, Erweiterungen willkommen.

Insbesondere:
- Weitere Domain-Expert-Stacks
- Zusätzliche Frameworks (z.B. Cynefin, OODA-Loop, Wardley Maps)
- Persona-Varianten (z.B. Compliance Officer für regulatorische Themen)

---

## Lizenz

MIT. Use as you like.
