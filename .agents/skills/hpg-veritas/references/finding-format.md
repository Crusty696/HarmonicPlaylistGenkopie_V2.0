# Findings-Format

Jeder Pass schreibt ein JSON-Objekt:

```json
{
  "schema_version": 1,
  "pass_id": 1,
  "agent_context_id": "frischer-kontext-id",
  "file_order_seed": 101,
  "role": "Statiker",
  "role_results": [
    {
      "role": "Statiker",
      "status": "completed",
      "note": "Scope vollstaendig geprueft.",
      "checked_scope": ["hpg_core/**/*.py"]
    }
  ],
  "findings": [
    {
      "rule": "THREAD-001",
      "claim": "Worker schreibt direkt in ein QWidget.",
      "impact": "Qt-Threadvertrag wird verletzt.",
      "severity": "P1",
      "category": "Threading",
      "path": "main.py",
      "line_start": 100,
      "line_end": 102,
      "context": "widget.setText(value)",
      "confidence": "hoch",
      "evidence": [
        {
          "kind": "source",
          "path": "main.py",
          "line_start": 100,
          "line_end": 102,
          "quote": "<exakter Text dieser Zeilen>"
        }
      ],
      "reproduction": {
        "command": "<echter Befehl oder leer>",
        "result": "<beobachtetes Ergebnis>"
      }
    }
  ],
  "learning_applications": [
    {
      "application_id": "lauf-pass1-static-L-007",
      "id": "L-007",
      "pass_id": 1,
      "role": "Statiker",
      "location": "hpg_core/parallel_analyzer.py",
      "result": "sauber",
      "finding_fingerprints": []
    }
  ]
}
```

`role_results` enthaelt genau je einen Eintrag fuer Statiker, Dynamiker,
Audio/DSP, Integration und GUI/Threading. Nicht anwendbare Rollen quittieren
`not_applicable` mit konkreter Begruendung; sie werden nie still ausgelassen.
Bei `result: treffer` enthaelt `finding_fingerprints` mindestens den
SHA-256-Fingerprint eines Befunds aus demselben Pass. Der Merge loest diese
deterministisch zu stabilen `V-NNN`-IDs auf.

`source`-Evidenz wird beim Validieren exakt gegen Datei und Zeilenbereich
geprueft. `command`-Evidenz braucht `command`, `cwd`, `exit_code`, `output`,
`output_sha256` und `timestamp`; der Hash muss zum Output passen. Ein
Befundtext darf keine als Tatsache verkleideten Woerter `vermutlich`,
`wahrscheinlich`, `duerfte` oder `scheint` enthalten.

Fingerprint: normalisierter relativer Pfad + Regel + normalisierter Kontext.
Zeilennummern gehoeren bewusst nicht dazu, damit Verschiebungen zwischen
Paessen denselben Befund ergeben.
