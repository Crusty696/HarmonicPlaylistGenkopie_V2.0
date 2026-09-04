"""Deterministische Wissenssynchronisation fuer HPG-VERITAS.

Ohne ``--apply`` wird ausschliesslich ein Plan ausgegeben. Das Skript loescht
nie Dateien und schreibt nie in ``_raw`` oder ``00_Claude_Memory``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from tools.audit.veritas import (
        AUDIT_ROOT,
        REPO_ROOT,
        READABLE_SCHEMA_VERSIONS,
        SCHEMA_VERSION,
        VeritasError,
        evidence_markdown,
        read_json,
    )
except ModuleNotFoundError:  # direkter Aufruf aus tools/audit
    from veritas import (  # type: ignore[no-redef]
        AUDIT_ROOT,
        REPO_ROOT,
        READABLE_SCHEMA_VERSIONS,
        SCHEMA_VERSION,
        VeritasError,
        evidence_markdown,
        read_json,
    )


FINDING_ID = re.compile(r"V-\d{3,}")
LEARNING_ID = re.compile(r"L-\d{3,}")
USER_STATUSES = {
    "offen",
    "behoben",
    "falsch-positiv",
    "akzeptiert",
    "unbestaetigt",
    "widerspruch",
}
PROTECTED_VAULT_PARTS = {
    "_raw",
    "00_claude_memory",
    "claude-autopilot-v5",
    "claude-autopilot-v6",
    "claude-autopilot-v6.zip",
}
GENERATED_START = "<!-- VERITAS:GENERATED:START -->"
GENERATED_END = "<!-- VERITAS:GENERATED:END -->"


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = content.rstrip() + "\n"
    handle, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(normalized)
        os.replace(temp_name, path)
    except BaseException:
        try:
            Path(temp_name).unlink(missing_ok=True)
        finally:
            raise


def _windows_name(part: str) -> str:
    """Windows ignoriert Punkte und Leerzeichen am Namensende.

    Ohne das Abstreifen passiert '_raw.' die Schutzliste und landet beim
    Aufloesen doch in '_raw'.
    """
    return part.rstrip(". ").casefold()


def frontmatter_value(text: str, key: str) -> str | None:
    # Notepad und PowerShell 5.1 schreiben UTF-8 mit BOM; ohne das Abstreifen
    # galt das Frontmatter als nicht vorhanden und der Nutzerstatus fiel
    # stillschweigend auf den Vorgabewert zurueck. Genau EIN BOM abstreifen,
    # wie in `_frontmatter_teile`: zwei Leser mit zwei Regeln
    # liessen eine doppelt praefixierte Notiz hier durchgehen und erst achtzig
    # Zeilen spaeter mit "ohne lesbares Frontmatter" durchfallen.
    if text.startswith("﻿"):
        text = text[1:]
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    pattern = re.compile(rf"^{re.escape(key)}:\s*[\"']?([^\n\"']+)[\"']?\s*$", re.MULTILINE)
    match = pattern.search(text[4:end])
    return match.group(1).strip() if match else None


def safe_vault_dir(config: dict[str, Any]) -> Path:
    root = Path(str(config.get("vault_root", "")))
    relative = Path(str(config.get("vault_audit_dir", "")))
    if not root.is_absolute():
        raise VeritasError("vault_root muss absolut sein")
    if relative.is_absolute() or ".." in relative.parts:
        raise VeritasError("vault_audit_dir muss sicher relativ sein")
    resolved = (root / relative).resolve()
    # Roh UND aufgeloest pruefen: '_raw.' passiert sonst die Liste und landet
    # beim Aufloesen doch in '_raw'.
    lowered = {
        _windows_name(part)
        for part in (*root.parts, *relative.parts, *resolved.parts)
    }
    if lowered & PROTECTED_VAULT_PARTS:
        raise VeritasError("Geschuetztes Vault-Ziel ist verboten")
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise VeritasError("Vault-Ziel verlaesst vault_root") from exc
    return resolved


def safe_project_target(repo: Path, raw: str) -> Path:
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise VeritasError(f"Unsicheres Projektziel: {raw}")
    resolved = (repo / relative).resolve()
    try:
        rel = resolved.relative_to(repo.resolve())
    except ValueError as exc:
        raise VeritasError(f"Projektziel verlaesst Repository: {raw}") from exc
    allowed = (
        Path("tools/audit"),
        Path(".agents/skills/hpg-veritas"),
        Path(".claude/skills/hpg-veritas"),
    )
    if not any(rel == prefix or prefix in rel.parents for prefix in allowed):
        raise VeritasError(f"Projektziel nicht freigegeben: {raw}")
    return resolved


def _frontmatter_teile(text: str) -> tuple[list[str], str] | None:
    """Frontmatter-Zeilen und Rest, oder None wenn kein Frontmatter da ist."""
    # Genau EIN BOM abstreifen. `lstrip` entfernte beliebig viele, zurueck
    # geschrieben wird aber nur eines -- eine doppelt praefixierte Datei
    # verloere sonst still ein Zeichen.
    if text.startswith("﻿"):
        text = text[1:]
    if not text.startswith("---\n"):
        return None
    ende = text.find("\n---\n", 4)
    if ende < 0:
        return None
    return text[4:ende].splitlines(), text[ende + len("\n---\n"):]


def _tags_vereinigen(alt: str, neu: str) -> str:
    """Eigene Tags erhalten, generierte ergaenzen.

    `tags` ist das einzige Frontmatter-Feld, das beiden gehoert.
    """
    def zerlegen(wert: str) -> list[str]:
        return [t.strip() for t in wert.strip().strip("[]").split(",") if t.strip()]

    zusammen = zerlegen(alt)
    for tag in zerlegen(neu):
        if tag not in zusammen:
            zusammen.append(tag)
    return "[" + ", ".join(zusammen) + "]"


def _frontmatter_mischen(vorhanden: list[str], generiert: dict[str, str]) -> list[str]:
    """Generierte Schluessel aktualisieren, fremde unveraendert erhalten.

    Vorher wurde die ganze Datei neu geschrieben; eigene Felder wie `aliases`
    oder `prioritaet` verschwanden dabei restlos.
    """
    ergebnis: list[str] = []
    gesehen: set[str] = set()
    for zeile in vorhanden:
        # Nur Zeilen ohne fuehrenden Leerraum sind Schluessel der obersten
        # Ebene. Eine eingerueckte Zeile gehoert zum Wert darueber; wuerde sie
        # als Schluessel behandelt, verloere ein eigenes verschachteltes Feld
        # seinen Wert und seine Einrueckung.
        ist_schluessel = bool(zeile[:1].strip()) and not zeile.startswith("#") and ":" in zeile
        schluessel = zeile.split(":", 1)[0].strip() if ist_schluessel else ""
        if schluessel == "tags":
            alt = zeile.split(":", 1)[1]
            wert = alt.strip()
            mehrzeilig = wert.startswith("[") and not wert.endswith("]")
            if not wert or wert.startswith("#") or mehrzeilig:
                # Blockstil (`tags:` und darunter `  - x`), Kommentar statt
                # Wert, oder eine Inline-Liste, die erst in einer Folgezeile
                # schliesst. In allen drei Faellen gehoeren die Folgezeilen zum
                # Wert, sind hier aber nicht sichtbar. Eine Inline-Liste
                # darueberzuschreiben zerstoert das Frontmatter, also bleibt
                # der Wert unangetastet.
                ergebnis.append(zeile)
            else:
                ergebnis.append(f"tags: {_tags_vereinigen(alt, generiert['tags'])}")
            gesehen.add("tags")
        elif schluessel in generiert:
            ergebnis.append(f"{schluessel}: {generiert[schluessel]}")
            gesehen.add(schluessel)
        else:
            ergebnis.append(zeile)
    for schluessel, wert in generiert.items():
        if schluessel not in gesehen:
            ergebnis.append(f"{schluessel}: {wert}")
    return ergebnis


def _marker_positionen(rumpf: str) -> tuple[list[int], list[int]]:
    """Zeichenpositionen der Marker: Zeilen, die exakt der Markerzeile gleichen.

    Bewusst OHNE Codeblock-Erkennung. Ein Zustandsautomat ueber ```-Zeilen
    haengt an fremdem Text: ein einzelner nicht geschlossener Codeblock im
    Nutzerabschnitt -- in Obsidian ein haeufiger Tippfehler -- liesse die
    echten Marker als "im Codeblock" gelten, und der Sync meldete "Notiz ohne
    VERITAS-Marker" an einer Notiz, die er selbst geschrieben hat.

    Dass ein Evidenz-Zitat eine Markerzeile enthaelt, ist stattdessen an der
    Quelle geloest: `_marker_entschaerfen` sorgt dafuer, dass im
    erzeugten Block keine Zeile exakt einem Marker gleicht.
    """
    starts: list[int] = []
    enden: list[int] = []
    position = 0
    for zeile in rumpf.split("\n"):
        if zeile == GENERATED_START:
            starts.append(position)
        elif zeile == GENERATED_END:
            enden.append(position)
        position += len(zeile) + 1
    return starts, enden


def _titel_aktualisieren(davor: str, finding_id: str, claim: str) -> str:
    """Die vom Generator gesetzte Ueberschrift nachziehen.

    Der Titel `# V-001 - {claim}` steht ausserhalb der Marker, stammt aber vom
    Generator. Ohne dieses Nachziehen zeigte eine Bestandsnotiz dauerhaft den
    alten Claim. Eine vom Nutzer umbenannte Ueberschrift wird nicht angefasst:
    erkannt wird nur die erzeugte Form mit dem Praefix `# {id} - `.

    Betrachtet wird ausschliesslich die ERSTE nicht leere Zeile: genau dort
    schreibt der Neuanlage-Pfad die Ueberschrift hin. Bewusst OHNE
    Codeblock-Erkennung -- ein Zustandsautomat ueber ```-Zeilen haengt an
    fremdem Text, und ein einzelner nicht geschlossener Codeblock oberhalb
    liesse die Schleife nie zum Ende kommen und den Titel stillschweigend fuer
    immer einfrieren. Steht in der ersten Zeile etwas anderes, gehoert der
    Kopf dem Nutzer und bleibt unangetastet.
    """
    praefix = f"# {finding_id} - "
    zeilen = davor.split("\n")
    for index, zeile in enumerate(zeilen):
        if not zeile.strip():
            continue
        if zeile.startswith(praefix):
            zeilen[index] = f"{praefix}{claim}"
        break
    return "\n".join(zeilen)


def _einzeilig(wert: str) -> str:
    """Einen Wert auf eine Zeile ziehen und Markerzeichenfolgen entschaerfen.

    Fuer alles, was AUSSERHALB der Marker landet: Frontmatter-Werte und die
    Ueberschrift. Dort ist Mehrzeiligkeit schon fuer sich schaedlich -- der
    Rueckbau ersetzt zeilenweise und liesse die Notiz bei jedem Lauf wachsen --
    und eine Markerzeile waere unsichtbar, weil `_marker_positionen` nur den
    Rumpf liest.
    """
    zusammengezogen = " ".join(str(wert).split())
    for marker in (GENERATED_START, GENERATED_END):
        zusammengezogen = zusammengezogen.replace(
            marker, marker.replace("-->", "-- >")
        )
    return zusammengezogen


def _marker_entschaerfen(text: str) -> tuple[str, bool]:
    """Markerzeilen im erzeugten Text unschaedlich machen.

    `evidence_markdown` setzt Quellzitate unveraendert in einen ```text-Block,
    und `impact`, `claim`, `rule` und `path` werden roh interpoliert -- keines
    davon ist auf eine Zeile beschraenkt. Ein Audit ueber dieses Modul oder
    ueber die Skill-Doku kann die Markerzeile also an JEDER dieser Stellen
    einschleusen, nicht nur im Zitat. Der naechste Lauf faende dann in seiner
    eigenen Notiz mehrere Marker und meldete einen Konflikt, den niemand
    aufloesen kann.

    Betroffen ist nur eine Zeile, die dem Marker EXAKT gleicht; aus `-->` wird
    `-- >`. Der Text im Vault ist dann an dieser einen Stelle nicht mehr
    byteweise exakt -- die Laufdatei unter `tools/audit/runs/` bleibt es.
    """
    ersetzt: list[str] = []
    getroffen = False
    for zeile in text.split("\n"):
        if zeile == GENERATED_START or zeile == GENERATED_END:
            ersetzt.append(zeile.replace("-->", "-- >"))
            getroffen = True
        else:
            ersetzt.append(zeile)
    return "\n".join(ersetzt), getroffen


HINWEIS_ENTSCHAERFT = (
    "Hinweis: Mindestens eine Markerzeile in diesem Block wurde zu `-- >` "
    "entschaerft, damit der naechste Lauf seine eigenen Marker wiederfindet. "
    "Der Originaltext steht unveraendert in `tools/audit/runs/`."
)


def _generierter_block(finding: dict[str, Any]) -> str:
    roh = f"""## Befund

- Claim: {finding['claim']}
- Status im Merge: {finding['merge_status']}
- Status nach Verifikator: {finding['verifier_status']}
- Datei: `{finding['path']}:{finding['line_start']}`
- Regel: `{finding['rule']}`
- Auswirkung: {finding['impact']}
- Reproduziert: {finding['pass_quote']}

## Beweis

{evidence_markdown(finding)}"""
    block, getroffen = _marker_entschaerfen(roh)
    # Der Hinweis erscheint nur, wenn wirklich ersetzt wurde -- sonst wuechse
    # jede Notiz um eine Zeile ohne Anlass. Ohne ihn stuende im Vault ein als
    # woertlich ausgewiesenes Zitat, das an einer Stelle nicht woertlich ist.
    return f"{block}\n\n{HINWEIS_ENTSCHAERFT}" if getroffen else block


def canonical_user_status(finding: dict[str, Any]) -> str:
    status = finding.get("status")
    if status == "BESTAETIGT":
        return "offen"
    if status == "WIDERSPRUCH":
        return "widerspruch"
    return "unbestaetigt"


def render_finding_note(
    finding: dict[str, Any], existing: str, generated_at: str
) -> tuple[str | None, str | dict[str, Any] | None]:
    """Notizinhalt und Drift, ODER (None, Konflikt).

    Ein Konflikt bedeutet: die vorhandene Notiz gehoert dem Nutzer und wird
    nicht angefasst -- fremder Fingerprint oder unbekannter Statuswert.
    """
    default_status = canonical_user_status(finding)
    saved_status = frontmatter_value(existing, "status") if existing else None
    alter_fp = frontmatter_value(existing, "fingerprint") if existing else None
    fingerprint = str(finding.get("fingerprint", ""))
    # Fremde Notiz unter derselben ID: nichts uebernehmen, sonst erbt ein
    # offener Befund den Status "behoben" eines ganz anderen.
    fremde_notiz = bool(existing) and alter_fp is not None and alter_fp != fingerprint
    if fremde_notiz:
        return None, {
            "id": finding["id"],
            "grund": "fremder Fingerprint",
            "notiz_fingerprint": alter_fp,
            "befund_fingerprint": fingerprint,
        }
    normalisiert = saved_status.casefold() if isinstance(saved_status, str) else None
    schreibweise_geaendert = (
        isinstance(saved_status, str)
        and normalisiert in USER_STATUSES
        and saved_status != normalisiert
    )
    if normalisiert in USER_STATUSES:
        status = normalisiert
    elif saved_status is not None and existing:
        # C6: ein unbekannter Wert wurde bisher kommentarlos ersetzt.
        return None, {
            "id": finding["id"],
            "grund": "unbekannter Statuswert",
            "vorgefunden": saved_status,
        }
    else:
        status = default_status
    drift = status if status != default_status else None
    if schreibweise_geaendert:
        # Nutzertext wird kleingeschrieben zurueckgeschrieben -- das ist eine
        # Aenderung an seiner Datei und gehoert gemeldet.
        drift = drift or status
    if existing and alter_fp is None:
        # Erstmigration: die Notiz stammt aus der Zeit ohne Fingerprint.
        drift = drift or status
    # Ueber `_tags_vereinigen` normalisiert: bei leerem `category` entstuende
    # sonst `[veritas, audit, ]`, das der Aktualisierungspfad im naechsten Lauf
    # zu `[veritas, audit]` aufraeumt -- eine Differenz an einer Datei, die
    # niemand angefasst hat.
    tags = _tags_vereinigen(
        "",
        f"[veritas, audit, {str(finding.get('category', '')).casefold().replace(' ', '-')}]",
    )
    generiert = {
        "type": "audit-finding",
        "project": "HarmonicPlaylistGenerator",
        "id": str(finding["id"]),
        "fingerprint": fingerprint,
        "status": status,
        "severity": str(finding["severity"]),
        "kategorie": str(finding["category"]),
        "datei": str(finding["path"]),
        "pass_quote": str(finding["pass_quote"]),
        "konfidenz": str(finding["confidence"]),
        "updated": generated_at,
        "tags": tags,
    }
    # JEDER generierte Frontmatter-Wert muss einzeilig und markerfrei sein.
    # `category`, `path` und `pass_quote` werden roh interpoliert und sind
    # nicht auf eine Zeile beschraenkt. Eine Markerzeile dort ist schlimmer
    # als im Rumpf: `_marker_positionen` liest nur den Rumpf, meldet also
    # keinen Konflikt -- die Notiz wuchs bei JEDEM Lauf um einen Marker, und
    # `--apply` endete fuer immer mit einer Differenz, ohne dass irgendwo
    # stand warum. Eine `---`-Zeile schnitt zusaetzlich das Frontmatter ab.
    generiert = {
        schluessel: _einzeilig(wert) for schluessel, wert in generiert.items()
    }
    block = _generierter_block(finding)
    # Die Ueberschrift steht ausserhalb der Marker und muss EINZEILIG sein.
    # `claim` ist auf eine Zeile nicht beschraenkt: ein mehrzeiliger Claim
    # erzeugte eine mehrzeilige Ueberschrift, die `_titel_aktualisieren`
    # zeilenweise nicht stabil ersetzen kann -- die Notiz wuchs bei jedem Lauf.
    # Enthielt er zudem eine Markerzeile, blockierte sie ab dem dritten Lauf
    # dauerhaft. Zusammenziehen loest beides an der Wurzel.
    titel_text = _einzeilig(str(finding["claim"]))
    titel = f"{finding['id']} - {titel_text}"

    if not existing:
        kopf = "\n".join(f"{k}: {v}" for k, v in generiert.items())
        return (
            f"---\n{kopf}\n---\n\n"
            f"# {titel}\n\n"
            f"{GENERATED_START}\n\n{block}\n\n{GENERATED_END}\n\n"
            f"## Nutzerkommentar\n\n"
        ), drift

    # Bestandsnotiz: nur der Bereich zwischen den Markern wird neu geschrieben.
    # Alles davor und dahinter bleibt byteweise erhalten -- eigene Abschnitte,
    # eigene Ueberschriften, eigene Frontmatter-Felder.
    teile = _frontmatter_teile(existing)
    if teile is None:
        return None, {
            "id": finding["id"],
            "grund": "Notiz ohne lesbares Frontmatter",
        }
    fm_zeilen, rumpf = teile
    starts, enden = _marker_positionen(rumpf)
    # Der erste Startmarker, und dazu das ERSTE Ende DAHINTER. Ein woertlich
    # zitierter Endmarker oberhalb des Blocks gehoert dem Nutzer und darf die
    # Notiz nicht als "ohne Marker" erscheinen lassen -- dieselbe Regel wie
    # hinter dem Block, nur nach vorn.
    start = starts[0] if starts else None
    ende = next((wert for wert in enden if wert > start), None) if starts else None
    if start is None or ende is None:
        # Von Hand angelegte Notiz ohne Marker: nicht ueberschreiben.
        return None, {
            "id": finding["id"],
            "grund": "Notiz ohne VERITAS-Marker",
        }
    if any(start < weiterer < ende for weiterer in starts[1:]):
        # Ein zweiter Startmarker INNERHALB des Blocks: es wuerde nur bis zum
        # ersten Ende aktualisiert, der Rest bliebe mit veralteten Werten
        # stehen. Marker HINTER dem Ende zaehlen bewusst nicht -- dort liegt
        # der Nutzerkommentar, und ein woertlich zitierter Marker darin
        # blockierte die Notiz sonst dauerhaft, ohne dass der Nutzer den
        # Zusammenhang erkennen kann.
        return None, {
            "id": finding["id"],
            "grund": "mehrfache VERITAS-Marker",
        }
    kopf = "\n".join(_frontmatter_mischen(fm_zeilen, generiert))
    # Denselben einzeiligen Titel wie im Neuanlage-Pfad verwenden: der rohe
    # Claim schriebe zusaetzliche Zeilen VOR den Startmarker, die Notiz wuechse
    # bei jedem Lauf und blockierte ab dem dritten dauerhaft.
    davor = _titel_aktualisieren(rumpf[:start], str(finding["id"]), titel_text)
    dahinter = rumpf[ende + len(GENERATED_END):]
    # Notepad und PowerShell 5.1 schreiben UTF-8 mit BOM. `_frontmatter_teile`
    # streift es zum Lesen ab; ohne dieses Merken verloere die Notiz es bei
    # jedem Sync -- eine stille Formataenderung an einer Nutzerdatei.
    bom = "﻿" if existing.startswith("﻿") else ""
    return (
        f"{bom}---\n{kopf}\n---\n"
        f"{davor}{GENERATED_START}\n\n{block}\n\n{GENERATED_END}{dahinter}"
    ), drift


def vereinige_learnings(ziel: Path, lauf_daten: dict[str, Any]) -> dict[str, Any]:
    """Lauf-Stand in den persistenten Speicher mischen, nicht ersetzen.

    Vorher schrieb der Sync die Laufdatei ueber die persistente. Gemischt wird
    ueber die `id`: was der Lauf kennt, gewinnt; was er nicht kennt, bleibt
    unangetastet.

    ACHTUNG, Grenze: `veritas.command_init` seedet die Laufdatei aus dem
    persistenten Speicher. Im Regelfall traegt der Lauf den Bestand also
    bereits, und das alte Ueberschreiben verlor nichts. Verlust entstand nur,
    wenn der Lauf aus einer anderen Quelle initialisiert wurde oder sich der
    Bestand zwischen `init-run` und `sync` geaendert hat.

    Und: was der Lauf kennt, gewinnt VOLLSTAENDIG. Emittiert er ein bekanntes
    Learning mit `applied: 0` neu, sind die akkumulierten Zaehler des Bestands
    weg. Erhalten bleibt die Existenz des Learnings, nicht sein Zaehlerstand.
    """
    bestand: list[dict[str, Any]] = []
    vorhandene_version: Any = None
    if ziel.is_file():
        vorhanden = read_json(ziel)
        vorhandene_version = vorhanden.get("schema_version")
        if vorhanden.get("schema_version") not in READABLE_SCHEMA_VERSIONS:
            raise VeritasError(f"{ziel}: falsche schema_version")
        roh = vorhanden.get("learnings")
        if not isinstance(roh, list):
            raise VeritasError(f"{ziel}: learnings muss Liste sein")
        bestand = []
        gesehene_ids: set[str] = set()
        for index, eintrag in enumerate(roh):
            if not isinstance(eintrag, dict):
                raise VeritasError(f"{ziel}: learnings[{index}] muss Objekt sein")
            kennung = eintrag.get("id")
            if not isinstance(kennung, str) or not kennung:
                # Ohne id liesse sich der Eintrag nie wieder aktualisieren.
                raise VeritasError(f"{ziel}: learnings[{index}] ohne id")
            if kennung in gesehene_ids:
                raise VeritasError(f"{ziel}: doppelte Learning-ID {kennung}")
            gesehene_ids.add(kennung)
            bestand.append(eintrag)
    aus_lauf = {
        eintrag["id"]: eintrag
        for eintrag in lauf_daten.get("learnings", [])
        if isinstance(eintrag, dict) and isinstance(eintrag.get("id"), str)
    }
    ergebnis: list[dict[str, Any]] = []
    gesehen: set[str] = set()
    for alt in bestand:
        kennung = str(alt["id"])
        ergebnis.append(aus_lauf.get(kennung, alt))
        gesehen.add(kennung)
    for kennung, neu in aus_lauf.items():
        if kennung not in gesehen:
            ergebnis.append(neu)
    # Nie herabgestuft, angehoben nur wenn der Lauf neuer ist. Blind
    # `SCHEMA_VERSION` zu schreiben hob eine Bestandsdatei auch dann an, wenn
    # der Lauf selbst noch die aeltere Fassung lieferte.
    # ACHTUNG, Grenze dieser Regel: `veritas.command_init` stempelt der
    # Laufdatei immer `SCHEMA_VERSION` auf. Im produktiven Pfad ist der Lauf
    # also stets die neueste Fassung, und eine Bestandsdatei mit einer
    # aelteren Version wird dadurch weiterhin angehoben. Wirksam ist die Regel
    # nur fuer Aufrufer, die den Lauf-Stand selbst bilden.
    versionen = [
        wert
        for wert in (vorhandene_version, lauf_daten.get("schema_version"))
        if isinstance(wert, int) and wert in READABLE_SCHEMA_VERSIONS
    ]
    return {
        "schema_version": max(versionen) if versionen else SCHEMA_VERSION,
        "learnings": ergebnis,
    }


def validate_learnings(
    data: dict[str, Any],
    finding_ids: set[str],
    bekannte_quellen: dict[str, set[str]] | None = None,
) -> list[dict[str, Any]]:
    if data.get("schema_version") not in READABLE_SCHEMA_VERSIONS:
        raise VeritasError("learnings.json: falsche schema_version")
    raw = data.get("learnings")
    if not isinstance(raw, list):
        raise VeritasError("learnings.json: learnings muss Liste sein")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, learning in enumerate(raw):
        if not isinstance(learning, dict):
            raise VeritasError(f"learnings[{index}] muss Objekt sein")
        learning_id = learning.get("id")
        if not isinstance(learning_id, str) or not LEARNING_ID.fullmatch(learning_id):
            raise VeritasError(f"learnings[{index}].id ungueltig")
        if learning_id in seen:
            raise VeritasError(f"Doppelte Learning-ID: {learning_id}")
        seen.add(learning_id)
        sources = learning.get("sources")
        if not isinstance(sources, list) or not sources:
            raise VeritasError(f"{learning_id}: sources fehlen")
        invalid_sources = [
            source
            for source in sources
            if not isinstance(source, str) or not FINDING_ID.fullmatch(source)
        ]
        if invalid_sources:
            raise VeritasError(f"{learning_id}: ungueltige Quellen {invalid_sources}")
        # Ein Learning behaelt genau die Quellen, die im persistenten Speicher
        # schon an ihm hingen -- sonst koennte akkumuliertes Wissen strukturell
        # nie mitgefuehrt werden. JEDE andere Quelle muss ein Befund dieses
        # Laufs sein, sonst faellt ein Tippfehler wie V-999 nicht auf. Die
        # Pruefung haengt an der einzelnen Quelle, nicht an der Learning-ID:
        # sonst waere ein bekanntes Learning dauerhaft ungeschuetzt.
        erlaubt = finding_ids | (bekannte_quellen or {}).get(learning_id, set())
        unknown_sources = [source for source in sources if source not in erlaubt]
        if unknown_sources:
            raise VeritasError(
                f"{learning_id}: Quellen ohne Befund im Lauf {sorted(unknown_sources)}"
            )
        for key in ("situation", "rule", "counterexample"):
            if not isinstance(learning.get(key), str) or not learning[key].strip():
                raise VeritasError(f"{learning_id}: {key} fehlt")
        tags = learning.get("tags")
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise VeritasError(f"{learning_id}: tags muss String-Liste sein")
        if learning.get("status") not in {"aktiv", "review", "archiviert"}:
            raise VeritasError(f"{learning_id}: status ungueltig")
        for key in ("applied", "hits"):
            if not isinstance(learning.get(key), int) or learning[key] < 0:
                raise VeritasError(f"{learning_id}: {key} muss nichtnegativer Integer sein")
        if learning["hits"] > learning["applied"]:
            raise VeritasError(f"{learning_id}: hits darf applied nicht uebersteigen")
        applications = learning.get("applications", [])
        if not isinstance(applications, list):
            raise VeritasError(f"{learning_id}: applications muss Liste sein")
        application_ids = [
            application.get("application_id")
            for application in applications
            if isinstance(application, dict)
        ]
        if len(application_ids) != len(applications) or len(set(application_ids)) != len(
            application_ids
        ):
            raise VeritasError(f"{learning_id}: applications ungueltig oder doppelt")
        if learning["applied"] != len(applications):
            raise VeritasError(f"{learning_id}: applied stimmt nicht mit applications ueberein")
        counted_hits = sum(
            1
            for application in applications
            if application.get("result") == "treffer"
        )
        if learning["hits"] != counted_hits:
            raise VeritasError(f"{learning_id}: hits stimmt nicht mit applications ueberein")
        result.append(learning)
    return result


def render_learning_note(learning: dict[str, Any], generated_at: str) -> str:
    sources = ", ".join(f"[[../Befunde/{source}|{source}]]" for source in learning["sources"])
    tags = ", ".join(learning["tags"])
    return f"""---
type: learning
project: HarmonicPlaylistGenerator
id: {learning['id']}
status: {learning['status']}
sources: [{', '.join(learning['sources'])}]
tags: [{tags}]
applied: {learning['applied']}
hits: {learning['hits']}
updated: {generated_at}
---

# {learning['id']}

## Situation

{learning['situation']}

## Regel

{learning['rule']}

## Gegenbeispiel

{learning['counterexample']}

## Quellen

{sources}
"""


def render_moc(
    findings: list[dict[str, Any]], learnings: list[dict[str, Any]], generated_at: str
) -> str:
    lines = [
        "---",
        "type: map-of-content",
        "project: HarmonicPlaylistGenerator",
        "tags: [veritas, audit]",
        f"updated: {generated_at}",
        "---",
        "",
        "# VERITAS Audit MOC",
        "",
        "## Befunde",
        "",
        "| ID | Status | Severity | Kategorie | Datei | Paesse |",
        "|---|---|---|---|---|---:|",
    ]
    for finding in findings:
        lines.append(
            f"| [[Befunde/{finding['id']}|{finding['id']}]] | {finding['status']} | "
            f"{finding['severity']} | {finding['category']} | `{finding['path']}` | {finding['pass_quote']} |"
        )
    lines.extend(["", "## Learnings", ""])
    if learnings:
        lines.extend(f"- [[Learnings/{learning['id']}|{learning['id']}]]" for learning in learnings)
    else:
        lines.append("Keine.")
    return "\n".join(lines)


def render_lessons(learnings: list[dict[str, Any]]) -> str:
    lines = ["# VERITAS Lessons", "", "Generiert aus validiertem `learnings.json`.", ""]
    active = [learning for learning in learnings if learning["status"] in {"aktiv", "review"}]
    if not active:
        lines.append("Noch keine bestaetigten Learnings.")
    for learning in active:
        lines.extend(
            [
                f"## {learning['id']} [{learning['status']}]",
                "",
                f"- Regel: {learning['rule']}",
                f"- Quellen: {', '.join(learning['sources'])}",
                f"- Anwendungen/Treffer: {learning['applied']}/{learning['hits']}",
                "",
            ]
        )
    return "\n".join(lines)


def render_active_learnings(learnings: list[dict[str, Any]], max_lines: int) -> str:
    lines = ["# Aktive VERITAS-Learnings", ""]
    active = [learning for learning in learnings if learning["status"] == "aktiv"]
    if not active:
        lines.append("Noch keine bestaetigten Learnings.")
    else:
        # Die zwei Kopfzeilen zaehlten im Limit mit: von 25 aktiven Regeln
        # landeten 18 in der Datei, ohne jeden Hinweis auf den Rest.
        geschrieben = 0
        for learning in active:
            if len(lines) >= max_lines - 1:
                break
            lines.append(f"- {learning['id']}: {learning['rule']}")
            geschrieben += 1
        if geschrieben < len(active):
            lines.append(
                f"- ... {len(active) - geschrieben} weitere, siehe LESSONS.md"
            )
    return "\n".join(lines)


def report_path(run_dir: Path) -> Path:
    reports = sorted(run_dir.glob("AUDIT_REPORT_*.md"))
    if len(reports) != 1:
        raise VeritasError("Lauf braucht genau einen AUDIT_REPORT_*.md")
    return reports[0]


def active_learning_targets(config: dict[str, Any]) -> list[str]:
    """Ein Ziel oder mehrere Spiegel; jeder Eintrag bekommt denselben Inhalt."""
    raw = config.get("active_learnings")
    targets = [raw] if isinstance(raw, str) else raw
    if not isinstance(targets, list) or not targets:
        raise VeritasError("active_learnings: String oder nichtleere Liste erforderlich")
    if not all(isinstance(target, str) and target.strip() for target in targets):
        raise VeritasError("active_learnings: nur nichtleere Pfad-Strings erlaubt")
    if len(set(targets)) != len(targets):
        raise VeritasError("active_learnings: doppelte Ziele")
    return targets


def build_expected(
    run_dir: Path, repo: Path, config: dict[str, Any]
) -> tuple[
    dict[Path, str], list[dict[str, Any]], list[str], list[dict[str, Any]]
]:
    canonical = read_json(run_dir / "findings.json")
    verifier_context = canonical.get("verifier_context_id")
    if not isinstance(verifier_context, str) or not verifier_context.strip():
        raise VeritasError("Unabhaengiges Verifikatorurteil fehlt")
    generated_at = str(
        canonical.get("verifier_applied_at")
        or canonical.get("generated_at")
        or "UNKNOWN"
    )
    findings = canonical.get("findings")
    if not isinstance(findings, list):
        raise VeritasError("findings.json: findings muss Liste sein")
    pending_verifier = [
        finding.get("id", "UNBEKANNT")
        for finding in findings
        if isinstance(finding, dict)
        and finding.get("merge_status") == "BESTAETIGT"
        and (
            finding.get("verifier_status") != "AKZEPTIERT"
            or finding.get("status") != "BESTAETIGT"
        )
    ]
    if pending_verifier:
        raise VeritasError(
            "Bestaetigte Merge-Kandidaten ohne Verifikator-Akzeptanz: "
            + ", ".join(str(value) for value in pending_verifier)
        )
    ids = {finding.get("id") for finding in findings if isinstance(finding, dict)}
    if len(ids) != len(findings) or not all(isinstance(value, str) and FINDING_ID.fullmatch(value) for value in ids):
        raise VeritasError("findings.json: ungueltige oder doppelte IDs")
    learning_data = read_json(run_dir / "learnings.json")
    learning_ziel_pfad = safe_project_target(repo, str(config["project_learnings"]))
    bekannte: dict[str, set[str]] = {}
    if learning_ziel_pfad.is_file():
        roh_bestand = read_json(learning_ziel_pfad).get("learnings")
        if not isinstance(roh_bestand, list):
            # Ohne diese Pruefung endete eine von Hand editierte Datei mit
            # `"learnings": null` in einem TypeError statt in einer Meldung.
            raise VeritasError(f"{learning_ziel_pfad}: learnings muss Liste sein")
        for eintrag in roh_bestand:
            if isinstance(eintrag, dict) and isinstance(eintrag.get("id"), str):
                quellen = eintrag.get("sources")
                bekannte[eintrag["id"]] = {
                    quelle for quelle in quellen if isinstance(quelle, str)
                } if isinstance(quellen, list) else set()
    # Der Lauf wird SEPARAT geprueft, obwohl unten der vereinigte Stand noch
    # einmal durch dieselbe Pruefung geht: `vereinige_learnings` filtert
    # Lauf-Eintraege ohne gueltige `id` heraus, die faenden sich dort also nie
    # wieder. Das Ergebnis wird bewusst nicht gebunden -- gerendert wird
    # ausschliesslich der vereinigte Stand.
    validate_learnings(learning_data, set(ids), bekannte)
    report = report_path(run_dir)
    report_text = report.read_text(encoding="utf-8")
    missing_report_ids = sorted(value for value in ids if value not in report_text)
    if missing_report_ids:
        raise VeritasError("Bericht enthaelt IDs nicht: " + ", ".join(missing_report_ids))

    vault_dir = safe_vault_dir(config)
    expected: dict[Path, str] = {}
    status_drifts: list[dict[str, Any]] = []
    konflikte: list[dict[str, Any]] = []
    for finding in findings:
        target = vault_dir / "Befunde" / f"{finding['id']}.md"
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
        content, drift = render_finding_note(finding, existing, generated_at)
        if content is None:
            # Fremder Fingerprint oder unbekannter Statuswert: die Notiz
            # gehoert dem Nutzer und wird nicht angefasst.
            konflikte.append({**drift, "pfad": str(target)})
            continue
        expected[target] = content
        if drift:
            status_drifts.append(
                {"id": finding["id"], "vault_status": drift, "audit_status": finding["status"]}
            )
    vereinigt = vereinige_learnings(learning_ziel_pfad, learning_data)
    expected[learning_ziel_pfad] = (
        json.dumps(vereinigt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    # Der Bestand wird genauso geprueft wie der Lauf: die Renderer greifen per
    # Index auf `sources`, `applied` und `hits` zu und wuerden bei einem
    # unvollstaendigen Alteintrag mit KeyError statt mit einer Meldung
    # abbrechen.
    alle = validate_learnings(vereinigt, set(ids), bekannte)
    # ALLE Ziele beschreiben den GESAMTEN Wissensstand, nicht nur diesen Lauf.
    # Solange Notizen, MOC und Waisenerkennung nur den Lauf sahen, stand ein
    # akkumuliertes Learning zwar in LESSONS.md, fehlte aber im MOC und galt
    # als Waise -- seine Notiz wurde nie wieder aktualisiert. Genau in dem
    # Fall, fuer den die Vereinigung ueberhaupt gebaut wurde.
    for learning in alle:
        expected[vault_dir / "Learnings" / f"{learning['id']}.md"] = render_learning_note(
            learning, generated_at
        )
    expected[vault_dir / "AUDIT-MOC.md"] = render_moc(findings, alle, generated_at)
    expected[safe_project_target(repo, str(config["project_lessons"]))] = render_lessons(alle)
    max_lines = int(config.get("max_active_learning_lines", 20))
    active_text = render_active_learnings(alle, max_lines)
    for raw_target in active_learning_targets(config):
        expected[safe_project_target(repo, raw_target)] = active_text

    orphans: list[str] = []
    for directory, pattern, known in (
        (vault_dir / "Befunde", "V-*.md", set(ids)),
        (vault_dir / "Learnings", "L-*.md", {learning["id"] for learning in alle}),
    ):
        if directory.is_dir():
            for path in directory.glob(pattern):
                if path.stem not in known:
                    orphans.append(str(path))
    return expected, status_drifts, sorted(orphans), konflikte


def diff_plan(expected: dict[Path, str], orphans: list[str]) -> dict[str, Any]:
    changes: list[dict[str, str]] = []
    for path, content in expected.items():
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        normalized = content.rstrip() + "\n"
        if current != normalized:
            changes.append({"action": "create" if current is None else "update", "path": str(path)})
    return {
        "changes": changes,
        "orphans": orphans,
        # Waisen zaehlen NICHT mit: --apply entfernt sie nie, der Zaehler
        # koennte sonst nie 0 werden und das Abschluss-Gate waere mit einer
        # einzigen Waise dauerhaft unerreichbar. Sie bleiben als eigener
        # Posten sichtbar und sind Handarbeit.
        "sync_difference_count": len(changes),
        "orphan_count": len(orphans),
    }


def command_sync(
    args: argparse.Namespace, config_path: Path | None = None
) -> int:
    run_dir = Path(args.run_dir).resolve()
    repo = Path(args.repo).resolve()
    # Das CLI bietet bewusst keinen Konfigurationsschalter (siehe SKILL.md);
    # ein abweichendes Profil kann nur programmatisch uebergeben werden.
    resolved = config_path if config_path is not None else AUDIT_ROOT / "sync_targets.json"
    config = read_json(Path(resolved).resolve())
    expected, status_drifts, orphans, konflikte = build_expected(run_dir, repo, config)
    before = diff_plan(expected, orphans)
    geschrieben: list[str] = []
    if args.apply:
        # Nicht transaktional ueber mehrere Dateien: bricht ein Schreibvorgang
        # ab, muss der Teilzustand sichtbar sein statt still zu bleiben.
        try:
            for path, content in expected.items():
                atomic_write(path, content)
                geschrieben.append(str(path))
        except OSError as exc:
            print(json.dumps({
                "mode": "apply",
                "abgebrochen_nach": geschrieben,
                "fehler": str(exc),
            }, ensure_ascii=False, indent=2))
            raise VeritasError(
                f"Sync nach {len(geschrieben)} von {len(expected)} Dateien "
                f"abgebrochen: {exc}"
            ) from exc
    after = diff_plan(expected, orphans)
    payload = {
        "mode": "apply" if args.apply else "dry-run",
        "planned": before,
        "after": after,
        "user_status_pending_verification": status_drifts,
        # Notizen, die dem Nutzer gehoeren und deshalb nicht angefasst wurden.
        "konflikte": konflikte,
        "complete": bool(
            args.apply
            and after["sync_difference_count"] == 0
            and not konflikte
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.apply and (after["sync_difference_count"] != 0 or konflikte):
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HPG VERITAS Wissens-Sync")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--repo", default=str(REPO_ROOT))
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return command_sync(args)
    except VeritasError as exc:
        print(f"VERITAS_SYNC_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
