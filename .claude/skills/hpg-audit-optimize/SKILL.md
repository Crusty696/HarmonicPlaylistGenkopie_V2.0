---
name: hpg-audit-optimize
description: Use when auditing, reviewing, cleaning up or optimizing the HPG codebase — Code-Review, toter oder doppelter Code, Doku-Widersprueche, Produktionsreife-Check, oder wenn ein Audit-Bericht aus docs/ gegen den aktuellen Stand abgeglichen werden soll.
---

# HPG Audit & Optimize

## Quellen und Scope

Vor Facharbeit hpg-orientation laden. Aktuellen Auftrag, git status und den
betroffenen Code lesen. docs/PROJECT_KNOWLEDGE.md enthaelt erhaltene Regeln
und offene Fragen. Historische Audits sind keine aktuelle Fehlerliste.

## Vorgehen

1. Behauptung und Akzeptanzkriterium festlegen; konkrete Quelle lesen.
2. Vorhandene Nachweise auf relevante Hashes, Eingaben und Umgebung pruefen.
   Wiederholung nur mit dokumentiertem Grund und kleinstem passenden Umfang.
3. Verbraucher und Referenzen vor Entfernen pruefen. Fehlende lokale
   Referenzen allein beweisen nicht, dass ein Werkzeug unbenutzt ist.
4. Vor Umsetzung unabhaengigen hpg-waechter mit genauem Dateivertrag einsetzen.
5. Reproduzierbaren Fehler vor Korrektur nachweisen und denselben Test danach
   bestehen lassen. Nicht reproduzierbare Diagnose klar begrenzen.
6. Bei Produktaenderungen Fachinvarianten und Testvertrag anwenden. Fuer reine
   Dokumentation kein neuer Volltest, Build oder Audioanalyselauf (AGENTS.md).
7. Vor Commit Diff und genaue Stagingliste unabhaengig pruefen lassen.

## Bereinigung

Erst haltbare Erkenntnisse und offene Fragen extrahieren, dann sichern und
entfernen. Historische Fehler nicht automatisch als behoben markieren.
Originalmusik, Datenbanken, Lock-/Coverage-Dateien und geschuetzte
Benutzerartefakte bleiben unangetastet. Keine Wiederherstellung veralteter
Statuskopien als aktuelle Wahrheit. Beide Skill-Spiegel konsistent halten.

## Beweisgrenzen

Implementierung, automatische Tests, Originaltrack-App-Ablauf und musikalische
Bewertung getrennt berichten. Interne Scores sind keine Ground Truth.
Cache-Erfolg beweist keinen frischen Erstlauf. Eine Quellenbereinigung ist
keine Produktabnahme.
