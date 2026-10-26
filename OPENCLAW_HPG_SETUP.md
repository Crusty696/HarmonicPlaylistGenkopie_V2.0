# OpenClaw für Harmonic Playlist Generator

Projektlokale Hinweise, abgeglichen am 26.10.2026. Der frühere Agentenname
`hpg` ist eine dokumentierte Konfiguration; laufendes Modell, Provider,
Gateway, Berechtigungen und Agentenzahl müssen in der jeweiligen Installation
geprüft werden. Dieses Dokument behauptet keinen aktiven Runtimezustand.

## Projektvertrag

[AGENTS.md](AGENTS.md) und der aktuelle Auftrag bestimmen die Arbeit.
Die verfügbaren Fachskills liegen unter `.agents/skills/`, Fachrollen unter
`.agents/agents/`; keine feste historische Anzahl als Iststand übernehmen.
Die Claude-Spiegel und Codex-Rollenbeschreibungen sollen denselben Inhalt tragen.
Wächterprüfungen erfolgen auf Anforderung, ohne obligatorische Freigabetore.

`SOUL.md`, `TOOLS.md`, `USER.md`, `IDENTITY.md` und `MEMORY.md` ergänzen
Produktleitlinie und Arbeitsumgebung. Schutzregeln und Testausnahmen aus
AGENTS.md gelten auch für OpenClaw. Installationen, Modell-/Providerwechsel
oder Berechtigungsänderungen werden durch dieses Dokument nicht beauftragt.

## Auftrag formulieren

> Prüfe den betroffenen Codepfad und gültige vorhandene Nachweise. Bearbeite
> den beauftragten Umfang, bewahre fremde Änderungen und prüfe die Änderung
> mit dem kleinsten geeigneten Umfang. Berichte Implementierung, Tests,
> nativen Originaltrack-Ablauf und musikalische Bewertung getrennt.

Historischer CLI-Einstieg: `openclaw agent --agent hpg --message "<Auftrag>"`.
Syntax und Verfügbarkeit vor Nutzung anhand der installierten CLI-Hilfe prüfen.
HPG startet mit `venv312\Scripts\python.exe main.py`; die Prüfregeln stehen
im [Testskill](.agents/skills/hpg-testing-verification/SKILL.md).
