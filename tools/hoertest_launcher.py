"""Interaktiver Launcher fuer HPG-Hoertests.

Ermoeglicht das Auswaehlen, Neuladen und Fortsetzen verschiedener
Hoertest-Saetze (z.B. Techno/Progressive/Melodic vs. Psytrance) ueber ein
einfaches Menue.
"""
from __future__ import annotations

import csv
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

DEFAULT_PORT = 8767
# Muss den drei von hoertest_server.py akzeptierten CSV-Schemas entsprechen.
BEWERTUNG_SCHEMAS = {
    ("pair_id", "clip", "bewertung"),
    ("pair_id", "clip_id", "note", "gewaehlt", "zeit"),
    ("pair_id", "clip_id", "track_note", "technik_note", "gesamt_note", "gewaehlt", "zeit"),
}
DRAMATURGIE_SCHEMA = (
    "variant_id", "dramaturgie_gesamt", "energieverlauf", "peak_platzierung", "kohaerenz", "zeit",
)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def finde_hoertest_ordner() -> list[Path]:
    """Findet Hoertest-Ordner auf dem Desktop und im Projekt."""
    suchpfade = [
        Path(os.environ.get("USERPROFILE", "")) / "Desktop",
        Path(__file__).parent.parent,
    ]
    kandidaten: list[Path] = []
    gesehen: set[str] = set()

    for basis in suchpfade:
        if not basis.exists():
            continue
        # Suche direkte Unterordner, die wie ein Hoertest-Satz aussehen
        for eintrag in sorted(basis.iterdir()):
            if eintrag.is_dir() and (eintrag / "bewertung.csv").is_file():
                norm = str(eintrag.resolve()).lower()
                if norm not in gesehen:
                    gesehen.add(norm)
                    kandidaten.append(eintrag)

    # Sortiere: HPG-Techno-Prog-Melodic-50 zuerst, dann Psytrance, dann Rest
    def sortierschluessel(p: Path) -> tuple[int, str]:
        name = p.name.lower()
        if "techno-prog-melodic" in name:
            return (0, name)
        if "psytrance-90-v3" in name:
            return (1, name)
        if "psytrance" in name:
            return (2, name)
        return (3, name)

    return sorted(kandidaten, key=sortierschluessel)


def lese_fortschritt(ordner: Path) -> tuple[int, int, str]:
    """Liest die Bewertungsdateien und ermittelt (bewertet, gesamt, schema)."""
    bew_datei = ordner / "bewertung.csv"
    if not bew_datei.exists():
        return 0, 0, "unbekannt"

    try:
        with open(bew_datei, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if tuple(reader.fieldnames or ()) not in BEWERTUNG_SCHEMAS:
                return 0, 0, "fehler"
            zeilen = list(reader)
            if any(set(zeile) != set(reader.fieldnames) or any(
                wert is None for wert in zeile.values()
            ) for zeile in zeilen):
                return 0, 0, "fehler"
    except Exception:
        return 0, 0, "fehler"

    gesamt = len(zeilen)
    if gesamt == 0:
        if (ordner / "dramaturgie_manifest.json").is_file():
            return 0, 0, "fehler"
        return 0, 0, "leer"

    # Schema erkennen
    erste = zeilen[0]
    ist_dreinoten = "track_note" in erste or "gesamt_note" in erste
    ist_kandidaten = "clip_id" in erste

    zeilen_fertig: list[bool] = []
    for z in zeilen:
        if ist_dreinoten:
            # Dreinoten gelten erst mit allen drei Noten als abgeschlossen.
            noten = [(z.get(name) or "").strip() for name in
                     ("track_note", "technik_note", "gesamt_note")]
            if any(note and note not in {"1", "2", "3", "4", "5"} for note in noten):
                return 0, 0, "fehler"
            zeilen_fertig.append(all(noten))
        else:
            note = (z.get("note") or "").strip() or (z.get("bewertung") or "").strip()
            if note and note not in {"1", "2", "3", "4", "5"}:
                return 0, 0, "fehler"
            zeilen_fertig.append(bool(note))

    bewertet = sum(zeilen_fertig)
    schema_name = "Dreinoten" if ist_dreinoten else "Standard"
    if (ordner / "dramaturgie_manifest.json").is_file():
        try:
            # Dieselben Manifest-/CSV-Vertraege wie beim Serverstart verwenden.
            if __package__:
                from .hoertest_server import validiere_dramaturgie_satz
            else:
                from hoertest_server import validiere_dramaturgie_satz
            manifest = validiere_dramaturgie_satz(ordner, pruefe_dateien=False)
            varianten = manifest["variants"]
            with open(ordner / "dramaturgie_bewertung.csv", "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                if tuple(reader.fieldnames or ()) != DRAMATURGIE_SCHEMA:
                    return 0, 0, "fehler"
                zusatz = list(reader)
                if any(set(zeile) != set(reader.fieldnames) or any(
                    wert is None for wert in zeile.values()
                ) for zeile in zusatz):
                    return 0, 0, "fehler"
            if [z.get("variant_id") for z in zusatz] != [v["variant_id"] for v in varianten]:
                return 0, 0, "fehler"
            for z in zusatz:
                noten = [(z.get(name) or "").strip() for name in
                         ("dramaturgie_gesamt", "energieverlauf", "peak_platzierung", "kohaerenz")]
                if any(note and note not in {"1", "2", "3", "4", "5"} for note in noten):
                    return 0, 0, "fehler"
                if all(noten):
                    bewertet += 1
            gesamt += len(zusatz)
            schema_name = "Dramaturgie"
        except (OSError, ValueError, KeyError, TypeError, UnicodeError):
            return 0, 0, "fehler"
    if ist_kandidaten and schema_name != "Dramaturgie":
        gruppen: dict[str, list[tuple[dict, bool]]] = {}
        clip_ids: set[str] = set()
        for z, fertig in zip(zeilen, zeilen_fertig):
            paar_id = (z.get("pair_id") or "").strip()
            clip_id = (z.get("clip_id") or "").strip()
            if (
                not paar_id or not clip_id or clip_id in clip_ids
                or (z.get("gewaehlt") or "").strip() not in {"", "0", "1"}
            ):
                return 0, 0, "fehler"
            clip_ids.add(clip_id)
            gruppen.setdefault(paar_id, []).append((z, fertig))
        gesamt = len(gruppen)
        bewertet = 0
        for gruppe in gruppen.values():
            if not ist_dreinoten:
                for z, _ in gruppe:
                    if (z.get("gewaehlt") or "").strip() == "1":
                        if int((z.get("note") or "0").strip() or "0") < 2:
                            return 0, 0, "fehler"
            if not ist_dreinoten and len(gruppe) > 1:
                wahl = [(z.get("gewaehlt") or "").strip() for z, _ in gruppe]
                kein_bester = all(wert == "0" for wert in wahl)
                ein_sieger = wahl.count("1") == 1
                if any(wahl) and not (kein_bester or ein_sieger):
                    return 0, 0, "fehler"
                entschieden = kein_bester or ein_sieger
            else:
                entschieden = True
            if all(fertig for _, fertig in gruppe) and entschieden:
                bewertet += 1
        schema_name += "-Kandidaten"
    return bewertet, gesamt, schema_name


def _fortschritt_einheit(schema: str) -> str:
    if schema in {"Dramaturgie", "Standard", "Dreinoten"}:
        return "Bewertungen"
    return "Paare"


def _port_frei(port: int) -> bool:
    """Prueft einen Loopback-Port, ohne einen fremden Prozess anzufassen."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def finde_freien_port(start: int = DEFAULT_PORT, versuche: int = 32) -> int | None:
    """Liefert den ersten freien Loopback-Port ab ``start``."""
    ende = min(65536, max(1, start) + max(0, versuche))
    for port in range(max(1, start), ende):
        if _port_frei(port):
            return port
    return None


def _server_bereit(port: int, startkennung: str) -> bool:
    """Prueft Startkennung und HTML-Route des eigenen Hoertest-Servers."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/", timeout=0.5
        ) as antwort:
            return (
                antwort.status == 200
                and antwort.headers.get("Server", "").startswith("HPG-Hoertest")
                and antwort.headers.get_content_type() == "text/html"
                and antwort.headers.get("X-HPG-Launch-Token") == startkennung
            )
    except (OSError, urllib.error.URLError):
        return False


def _warte_auf_enter_oder_serverende(prozess: subprocess.Popen) -> bool:
    """Wartet auf Enter und erkennt ein unerwartetes Serverende zeitnah."""
    if prozess.poll() is not None:
        return False
    eingabe_fertig = threading.Event()
    eingabe_fehler: list[Exception] = []

    def lies_eingabe() -> None:
        try:
            input("Drücke [Enter] zum Beenden des Servers...")
        except EOFError:
            pass
        except Exception as exc:
            eingabe_fehler.append(exc)
        finally:
            eingabe_fertig.set()

    threading.Thread(target=lies_eingabe, daemon=True).start()
    while not eingabe_fertig.wait(0.25):
        if prozess.poll() is not None:
            return False
    return not eingabe_fehler and prozess.poll() is None


def zeige_menue(ordner_liste: list[Path]) -> Path | None:
    """Zeigt das interaktive Auswahlmenue."""
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 72)
    print("           HPG - HÖRTEST MANAGER & AUSWAHL (v3.7.2)")
    print("=" * 72)
    print("\nGefundene Hörtest-Sätze auf deinem System:\n")

    for i, ordner in enumerate(ordner_liste, start=1):
        bewertet, gesamt, schema = lese_fortschritt(ordner)
        einheit = _fortschritt_einheit(schema)
        status = ""
        if schema == "fehler":
            status = " [BEWERTUNGSDATEN FEHLERHAFT]"
        elif gesamt > 0:
            if bewertet == gesamt:
                status = " [VOLLSTÄNDIG BEWERTET]"
            elif bewertet == 0:
                status = " [NOCH UNBEWERTET / NEU]"
            else:
                status = f" [{bewertet}/{gesamt} BEWERTET - {gesamt - bewertet} OFFEN]"

        print(f"  [{i}] {ordner.name}{status}")
        print(f"      Pfad:    {ordner}")
        if gesamt > 0:
            print(f"      Status:  {bewertet} von {gesamt} {einheit} ({schema}-Schema)")
        print()

    print("  [E] Eigenen Pfad eingeben")
    print("  [Q] Beenden")
    print("-" * 72)

    while True:
        try:
            eingabe = input("Bitte Nummer wählen [1]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAbbruch.")
            return None

        if not eingabe:
            eingabe = "1"

        if eingabe.lower() in ("q", "quit", "exit"):
            return None

        if eingabe.lower() == "e":
            pfad_str = input("Pfad zum Hörtest-Ordner: ").strip().strip('"')
            p = Path(pfad_str)
            if p.exists() and p.is_dir():
                return p
            print(f"Fehler: Ordner '{pfad_str}' existiert nicht!\n")
            continue

        if eingabe.isdigit():
            idx = int(eingabe) - 1
            if 0 <= idx < len(ordner_liste):
                return ordner_liste[idx]

        print("Ungültige Auswahl, bitte erneut eingeben.")


def starte_server(ordner: Path, port: int = DEFAULT_PORT) -> bool:
    """Startet hoertest_server.py und oeffnet den Browser."""
    server_script = Path(__file__).parent / "hoertest_server.py"
    if not server_script.exists():
        print(f"Fehler: {server_script} nicht gefunden!")
        return False
    if not (ordner / "bewertung.csv").is_file():
        print(f"Fehler: Keine bewertung.csv in {ordner}.")
        return False

    print("\n" + "=" * 72)
    print(f"Starte Hörtest-Server für: {ordner.name}")
    print(f"Ordner: {ordner}")
    print("=" * 72)

    freier_port = finde_freien_port(port)
    if freier_port is None:
        print(f"Kein freier Loopback-Port ab {port} gefunden.")
        return False

    startkennung = secrets.token_urlsafe(24)
    cmd = [
        sys.executable,
        str(server_script),
        "--dir",
        str(ordner),
        "--port",
        str(freier_port),
        "--launch-token",
        startkennung,
    ]

    try:
        prozess = subprocess.Popen(cmd)
    except OSError as exc:
        print(f"Hörtest-Server konnte nicht gestartet werden: {exc}")
        return False

    bereit = False
    abgebrochen = False
    server_ended_unexpectedly = False
    try:
        for _ in range(20):
            if prozess.poll() is not None:
                break
            if _server_bereit(freier_port, startkennung):
                bereit = True
                break
            time.sleep(0.25)
        if not bereit:
            exit_code = prozess.poll()
            print(
                "Hörtest-Server konnte nicht gestartet werden "
                f"(Prozesscode {exit_code if exit_code is not None else 'keine Bereitschaft'})."
            )
            return False

        url = f"http://127.0.0.1:{freier_port}"
        print(f"\n-> Server läuft auf: {url}")
        print("-> Öffne Browser automatisch...")
        try:
            browser_offen = webbrowser.open(url)
        except (OSError, webbrowser.Error) as exc:
            print(f"Browser konnte nicht geöffnet werden: {exc}")
            return False
        if not browser_offen:
            print("Browser konnte nicht geöffnet werden.")
            return False

        print("\n" + "-" * 72)
        print(" HINWEIS:")
        if (ordner / "dramaturgie_manifest.json").is_file():
            print(" Übergangsnoten: bewertung.csv; Playlistnoten: dramaturgie_bewertung.csv.")
        else:
            print(" Jede abgegebene Note wird SOFORT in der bewertung.csv gespeichert.")
        print(" Du kannst den Server jederzeit beenden und später nahtlos fortsetzen.")
        print(" Drücke [Enter] oder Strg+C in dieser Konsole, um den Server zu stoppen.")
        print("-" * 72 + "\n")
        if not _warte_auf_enter_oder_serverende(prozess):
            print("Hörtest-Server wurde unerwartet beendet (während der Bedienung).")
            return False
    except (KeyboardInterrupt, EOFError):
        abgebrochen = not bereit
    finally:
        print("\nBeende Hörtest-Server...")
        server_ended_unexpectedly = prozess.poll() is not None
        if not server_ended_unexpectedly:
            prozess.terminate()
            try:
                prozess.wait(timeout=3)
            except subprocess.TimeoutExpired:
                prozess.kill()
                prozess.wait(timeout=3)

        # Zeige aktuellen Stand nach Beendigung
        bewertet, gesamt, schema = lese_fortschritt(ordner)
        einheit = _fortschritt_einheit(schema)
        print(f"\nAktueller Stand für {ordner.name}:")
        print(f"-> {bewertet} von {gesamt} {einheit} bewertet ({gesamt - bewertet} verbleibend).")
        print("Fertig. Bis zum nächsten Mal!\n")
    if abgebrochen or server_ended_unexpectedly:
        print("Hörtest-Server wurde unerwartet beendet.")
        return False
    return True


def main() -> int:
    while True:
        ordner_liste = finde_hoertest_ordner()
        if not ordner_liste:
            print("Keine Hörtest-Ordner automatisch gefunden. Eigenen Pfad wählen.")

        gewaehlter_ordner = zeige_menue(ordner_liste)
        if not gewaehlter_ordner:
            return 0

        if not starte_server(gewaehlter_ordner):
            return 1

        try:
            nochmal = input("Anderen Hörtest-Satz laden? [j/N]: ").strip().lower()
            if nochmal not in ("j", "ja", "y", "yes"):
                break
        except (KeyboardInterrupt, EOFError):
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
