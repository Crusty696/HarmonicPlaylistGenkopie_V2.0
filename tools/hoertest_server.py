"""Lokaler Hoertest-Server: Clips anhoeren und mit 1 bis 5 bewerten.

Warum: `rate_transitions.py prepare` legt <dir>/bewertung.csv mit leerer
Spalte `bewertung` an, die der Nutzer bisher von Hand in einem
Tabellenprogramm fuellt. Beim Hoeren von hundertsechzig Clips ist das die
fehleranfaelligste Stelle des Verfahrens: Zeile und Clip koennen
auseinanderlaufen. Diese Seite spielt den Clip und schreibt die Note zur
selben pair_id zurueck, sofort nach dem Klick.

Aufruf:
    .\\venv312\\Scripts\\python.exe tools/hoertest_server.py --dir C:\\...\\HPG-Hoertest

Bindet ausschliesslich an 127.0.0.1. Kein Fremdzugriff, keine Abhaengigkeit
ausserhalb der Standardbibliothek.

Trennung von reiner Logik und Aussenwelt (Testbarkeit):
- REIN: `sichere_clip_datei`, `merge_bewertungen`, `lade_uebersicht`
  (bekommt bereits gelesene Zeilen).
- AUSSENWELT: `lies_csv`, `schreibe_csv`, `HoertestHandler`, `main`.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Spalten von bewertung.csv — muessen zu rate_transitions.befehl_prepare und
# verbinde_bewertungen passen, sonst findet `fit` die Noten nicht wieder.
BEWERTUNG_SPALTEN = ("pair_id", "clip", "bewertung")

# Erlaubte Clip-Dateinamen: die von prepare vergebenen laufenden Nummern.
CLIP_NAME = re.compile(r"^[0-9A-Za-z_-]{1,32}\.wav$")

NOTEN = (1, 2, 3, 4, 5)

# Blockgroesse beim Ausliefern der Clips. 25-MB-WAVs am Stueck in den Socket
# zu schreiben blockiert den Thread bis zum Ende und bricht ab, sobald der
# Player weiterspringt.
BLOCK = 256 * 1024

# Nachlauf von Track B hinter der Blende, aus tools/rate_transitions.py. Der
# Clip ist [pre_roll | crossfade | post_roll] (transition_renderer.py:10). Der
# Vorlauf wird NICHT als Konstante uebernommen: liegt der Mix-Out weniger als
# pre_roll Sekunden hinter dem Trackanfang, klemmt der Renderer ihn
# (transition_renderer.py:159). Die Seite rechnet ihn deshalb aus der echten
# Cliplaenge zurueck: vorlauf = dauer - blende - nachlauf.
NACHLAUF_SEK = 8.0


# ===========================================================================
# Reine Logik
# ===========================================================================

def sichere_clip_datei(clips_dir: Path, name: str) -> Path:
    """Loest einen angefragten Clip-Namen auf oder wirft ValueError.

    Der Server liefert Dateien aus, deshalb wird der Name nicht nur auf ".."
    geprueft, sondern gegen ein enges Muster gehalten und der aufgeloeste
    Pfad danach als Kind von clips_dir verifiziert.
    """
    if not CLIP_NAME.match(name):
        raise ValueError(f"Unerlaubter Clip-Name: {name!r}")
    ziel = (clips_dir / name).resolve()
    wurzel = clips_dir.resolve()
    if wurzel not in ziel.parents:
        raise ValueError(f"Clip liegt ausserhalb von {wurzel}: {name!r}")
    return ziel


def lies_range(kopfzeile, groesse: int) -> tuple[int, int]:
    """Wertet einen Range-Kopf aus und gibt (start, ende) einschliesslich zurueck.

    Fehlt der Kopf oder ist er unbrauchbar, wird die ganze Datei geliefert.
    Unterstuetzt wird die einzige Form, die <audio> schickt: "bytes=a-" oder
    "bytes=a-b". Ein Bereich hinter dem Dateiende wird auf das Ende gekappt,
    damit der Server nie mehr ankuendigt als er schreiben kann.
    """
    if not kopfzeile or not str(kopfzeile).startswith("bytes="):
        return 0, max(0, groesse - 1)
    roh = str(kopfzeile)[len("bytes="):].split(",")[0].strip()
    teile = roh.split("-")
    if len(teile) != 2:
        return 0, max(0, groesse - 1)
    try:
        start = int(teile[0]) if teile[0] else 0
        ende = int(teile[1]) if teile[1] else groesse - 1
    except ValueError:
        return 0, max(0, groesse - 1)
    start = max(0, min(start, max(0, groesse - 1)))
    ende = max(start, min(ende, max(0, groesse - 1)))
    return start, ende


def merge_bewertungen(zeilen: list[dict], noten: dict) -> list[dict]:
    """Traegt Noten in die vorhandenen bewertung.csv-Zeilen ein.

    Bestehende Zeilen bleiben in Reihenfolge und Spaltenbelegung erhalten;
    nur `bewertung` wird ersetzt. Unbekannte pair_ids werden ignoriert statt
    angehaengt — sie koennten nur aus einem Tippfehler stammen, und eine
    zusaetzliche Zeile wuerde `fit` still verfaelschen.
    """
    neu = []
    for zeile in zeilen:
        kopie = dict(zeile)
        pair_id = str(zeile.get("pair_id", "")).strip()
        if pair_id in noten:
            wert = noten[pair_id]
            kopie["bewertung"] = "" if wert in (None, "") else str(int(wert))
        neu.append(kopie)
    return neu


def lade_uebersicht(
    merkmale_zeilen: list[dict],
    bewertung_zeilen: list[dict],
    infos: dict | None = None,
) -> list[dict]:
    """Baut die Anzeigeliste aus merkmale.csv und bewertung.csv.

    Fuehrend ist bewertung.csv: nur was dort steht, kann auch bewertet
    werden. merkmale.csv liefert Zusatzangaben fuer die Anzeige, `infos`
    (Pfad -> BPM/Genre/Key aus dem Cache) den Kontext zum Uebergang.

    Bewusst NICHT angezeigt werden die Faktor-Spalten aus merkmale.csv
    (groove, bass, timbre, mood, ...): das sind die Groessen, deren Gewicht
    der Hoertest schaetzen soll. Wer sie beim Bewerten sieht, bewertet sie
    mit — die Messung wuerde ihre eigene Vorannahme bestaetigen.
    """
    extra = {str(z.get("pair_id", "")).strip(): z for z in merkmale_zeilen}
    infos = infos or {}
    liste = []
    for zeile in bewertung_zeilen:
        pair_id = str(zeile.get("pair_id", "")).strip()
        m = extra.get(pair_id, {})
        pfad_a = str(m.get("track_a", ""))
        pfad_b = str(m.get("track_b", ""))
        info_a = infos.get(pfad_a.lower(), {})
        info_b = infos.get(pfad_b.lower(), {})
        liste.append(
            {
                "pair_id": pair_id,
                "clip": str(zeile.get("clip", "")).strip(),
                "bewertung": str(zeile.get("bewertung", "")).strip(),
                "crossfade_sek": str(m.get("crossfade_sek", "")).strip(),
                "track_a": Path(pfad_a).name,
                "track_b": Path(pfad_b).name,
                "bpm_a": info_a.get("bpm", ""),
                "bpm_b": info_b.get("bpm", ""),
                "genre_a": info_a.get("genre", ""),
                "genre_b": info_b.get("genre", ""),
                "key_a": info_a.get("key", ""),
                "key_b": info_b.get("key", ""),
            }
        )
    return liste


# ===========================================================================
# Kandidatenmodus (Spec 2026-08-21 Abschnitt 3): bewertung.csv traegt clip_id.
# Der Server erkennt den Modus selbst — kein Schalter, kein Eingriff in die
# Start-Skripte des Mobil-Ordners.
# ===========================================================================

BEWERTUNG_KANDIDATEN_SPALTEN = ("pair_id", "clip_id", "note", "gewaehlt", "zeit")
# Felder, die /daten je Clip liefert — absichtlich ohne score, schema, Teilwerte
# (verdeckte Bewertung; Waechter Tor 2 prueft diese Liste).
KANDIDAT_ANZEIGE_FELDER = ("clip_id", "clip", "note", "gewaehlt", "crossfade_sek")


def ist_kandidatensatz(bewertung_zeilen: list[dict]) -> bool:
    """Moduserkennung: ein Kandidatensatz hat die Spalte clip_id."""
    return bool(bewertung_zeilen) and "clip_id" in bewertung_zeilen[0]


def merge_kandidaten_bewertung(zeilen: list[dict], *, pair_id: str, clip_id: str,
                               note=None, bester: bool = False, zeit: str = "") -> list[dict]:
    """Traegt Note (None = loeschen) bzw. die exklusive Wahl 'bester' eines
    Clips ein; `zeit` wird nur auf dem beruehrten Clip gesetzt."""
    neu = []
    for z in zeilen:
        k = dict(z)
        if k.get("pair_id") == pair_id:
            if bester:
                k["gewaehlt"] = "1" if k.get("clip_id") == clip_id else ""
            if k.get("clip_id") == clip_id:
                if not bester:
                    k["note"] = "" if note in (None, "") else str(int(note))
                k["zeit"] = zeit
        neu.append(k)
    return neu


def lade_uebersicht_kandidaten(merkmale_zeilen, bewertung_zeilen, reihenfolge: dict,
                               infos: dict | None = None) -> list[dict]:
    """Gruppen je Paar, Clips in gespeicherter Reihenfolge, verdeckt: kein
    score, kein Schema, keine Teilwerte — nur Tempo/Genre/Camelot/Blende.
    Kontext kommt aus dem Cache (`infos`), sonst aus merkmale.csv (Mobil)."""
    infos = infos or {}
    merk = {z.get("clip_id"): z for z in merkmale_zeilen}
    gruppen: dict[str, dict] = {}
    for z in bewertung_zeilen:
        pid = str(z.get("pair_id", "")).strip()
        m = merk.get(z.get("clip_id"), {})
        if pid not in gruppen:
            pfad_a, pfad_b = str(m.get("track_a", "")), str(m.get("track_b", ""))
            ia, ib = infos.get(pfad_a.lower(), {}), infos.get(pfad_b.lower(), {})
            gruppen[pid] = {
                "pair_id": pid, "track_a": Path(pfad_a).name, "track_b": Path(pfad_b).name,
                "bpm_a": ia.get("bpm") or m.get("bpm_a", ""), "bpm_b": ib.get("bpm") or m.get("bpm_b", ""),
                "genre_a": ia.get("genre") or m.get("genre_a", ""),
                "genre_b": ib.get("genre") or m.get("genre_b", ""),
                "key_a": ia.get("key") or m.get("key_a", ""), "key_b": ib.get("key") or m.get("key_b", ""),
                "clips": [],
            }
        gruppen[pid]["clips"].append({
            "clip_id": z.get("clip_id", ""), "clip": str(m.get("clip", "")),
            "note": str(z.get("note", "")).strip(), "gewaehlt": str(z.get("gewaehlt", "")).strip(),
            "crossfade_sek": str(m.get("crossfade_sek", "")).strip(),
        })
    for pid, g in gruppen.items():
        folge = reihenfolge.get(pid, {}).get("clips")
        if folge:
            rang = {cid: i for i, cid in enumerate(folge)}
            g["clips"].sort(key=lambda c: rang.get(c["clip_id"], len(rang)))
    return list(gruppen.values())


# ===========================================================================
# Dateizugriff
# ===========================================================================

def lade_track_infos() -> dict:
    """Liest BPM, Genre und Key der analysierten Tracks aus dem Cache.

    Diese Angaben stehen nicht in merkmale.csv — dort sind `bpm` und `genre`
    die Faktor-Punktzahlen des Scorings, nicht die Werte selbst. Faellt der
    Cache aus, bleibt die Anzeige leer statt den Hoertest zu blockieren.
    """
    try:
        from tools.rate_transitions import lade_tracks_aus_cache, loese_genre_auf
    except Exception as exc:  # noqa: BLE001 - Anzeige ist Beiwerk
        print(f"Hinweis: BPM/Genre nicht verfuegbar ({exc})")
        return {}
    try:
        tracks = lade_tracks_aus_cache()
    except Exception as exc:  # noqa: BLE001 - Anzeige ist Beiwerk
        print(f"Hinweis: BPM/Genre nicht verfuegbar ({exc})")
        return {}
    infos = {}
    for track in tracks:
        infos[str(track.filePath).lower()] = {
            "bpm": round(float(track.bpm), 1) if track.bpm else "",
            "genre": loese_genre_auf(track),
            # Camelot-Code, weil danach gemischt wird — nicht keyNote/keyMode.
            "key": str(getattr(track, "camelotCode", "") or ""),
        }
    return infos


def lies_csv(pfad: Path) -> list[dict]:
    if not pfad.exists():
        return []
    with pfad.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def schreibe_csv(pfad: Path, spalten, zeilen) -> None:
    with pfad.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(spalten))
        writer.writeheader()
        writer.writerows(zeilen)


# ===========================================================================
# Seite
# ===========================================================================

SEITE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>HPG Hoertest</title>
<style>
  :root { color-scheme: dark; }
  body { background:#0f1420; color:#e6e9f0; font:15px/1.5 system-ui,sans-serif;
         margin:0; padding:24px 16px 96px; }
  h1 { font-size:20px; margin:0 0 4px; }
  .hinweis { color:#8b93a7; margin:0 0 24px; }
  .clip { background:#161d2e; border:1px solid #232c42; border-radius:10px;
          padding:14px 16px; margin:0 auto 14px; max-width:820px; }
  .clip.fertig { border-color:#3b6b4a; }
  .clip.aktiv { box-shadow:0 0 0 2px #c8a02e; }
  .kopf { display:flex; justify-content:space-between; gap:12px;
          align-items:baseline; margin-bottom:8px; }
  .id { font-weight:600; }
  .meta { color:#8b93a7; font-size:13px; }
  .filter { position:sticky; top:0; z-index:5; display:flex; flex-wrap:wrap;
            gap:8px; max-width:820px; margin:0 auto 16px; padding:10px 0;
            background:#0f1420; }
  .reiter { padding:7px 12px; font-size:14px; cursor:pointer; color:#c8cede;
            background:#161d2e; border:1px solid #2c3855; border-radius:20px; }
  .reiter:hover { background:#27334f; }
  .reiter.aktiv { background:#c8a02e; color:#101010; font-weight:700;
                  border-color:#c8a02e; }
  .reiter.durch { border-color:#3b6b4a; }
  .reiter .zahl { opacity:0.65; font-size:12px; }
  .spur { position:relative; height:26px; margin:2px 0 4px; border-radius:5px;
          background:#10182a; border:1px solid #2c3855; cursor:pointer;
          overflow:hidden; }
  .mix { position:absolute; top:0; bottom:0;
         background:linear-gradient(90deg,#c8a02e33,#c8a02e66,#c8a02e33);
         border-left:2px solid #c8a02e; border-right:2px solid #c8a02e; }
  .marke-a, .marke-b { position:absolute; top:0; bottom:0; display:flex;
                       align-items:center; padding:0 7px; font-size:11px;
                       font-weight:700; color:#8b93a7; }
  .marke-a { left:0; justify-content:flex-end; }
  .marke-b { right:0; }
  .nadel { position:absolute; top:0; bottom:0; width:2px; background:#e6e9f0;
           display:none; }
  .spurtext { color:#8b93a7; font-size:12px; margin-bottom:10px; }
  .fakten { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:8px; }
  .marke { background:#1d2740; border:1px solid #2c3855; border-radius:5px;
           padding:2px 8px; font-size:12px; color:#c8cede; }
  .titel { color:#a8b0c4; font-size:13px; margin-bottom:8px;
           overflow-wrap:anywhere; }
  audio { width:100%; margin-bottom:10px; }
  .noten { display:flex; gap:8px; }
  .noten button { flex:1; padding:9px 0; font-size:15px; cursor:pointer;
                  background:#1d2740; color:#e6e9f0; border:1px solid #2c3855;
                  border-radius:7px; }
  .noten button:hover { background:#27334f; }
  .noten button.aktiv { background:#c8a02e; color:#101010; font-weight:700;
                        border-color:#c8a02e; }
  .fuss { position:fixed; left:0; right:0; bottom:0; padding:10px 16px;
          background:#0b0f19; border-top:1px solid #232c42; color:#8b93a7; }
</style>
</head>
<body>
<h1>HPG Hoertest</h1>
<p class="hinweis">1 = geht gar nicht, 5 = sehr gut. Jede Note wird sofort in
bewertung.csv geschrieben. Tasten: <b>1</b>&ndash;<b>5</b> bewerten,
<b>Pfeil hoch/runter</b> wechselt den Clip, <b>Leertaste</b> spielt ihn ab.</p>
<div id="filter" class="filter"></div>
<div id="liste"></div>
<div class="fuss" id="fuss">lade ...</div>
<script>
const NACHLAUF = __NACHLAUF__;  // Sekunden Track B hinter der Blende
let daten = [];        // alle Clips, wie vom Server geliefert
let sichtbar = [];     // die aktuell gefilterte Teilmenge
let filter = 'alle';   // Genre-Filter, 'alle' = ohne Einschraenkung
let aktuell = 0;       // Index in sichtbar, nicht in daten

// Ein Uebergang hat zwei Genres. Er zaehlt zu beiden, sonst faellt jeder
// Genrewechsel (Progressive -> Techno) aus beiden Gruppen heraus.
function passt(z) {
  return filter === 'alle' || z.genre_a === filter || z.genre_b === filter;
}

function genreListe() {
  const zaehler = new Map();
  for (const z of daten) {
    for (const g of new Set([z.genre_a, z.genre_b])) {
      if (g) zaehler.set(g, (zaehler.get(g) || 0) + 1);
    }
  }
  return [...zaehler.entries()].sort((a, b) => b[1] - a[1]);
}

function zeichneFilter() {
  const leiste = document.getElementById('filter');
  leiste.innerHTML = '';
  const eintraege = [['alle', daten.length], ...genreListe()];
  for (const [name, anzahl] of eintraege) {
    const menge = name === 'alle' ? daten : daten.filter(
      z => z.genre_a === name || z.genre_b === name);
    const fertig = menge.filter(z => z.bewertung).length;
    const b = document.createElement('button');
    b.className = 'reiter' + (filter === name ? ' aktiv' : '')
                           + (fertig === anzahl ? ' durch' : '');
    b.innerHTML = (name === 'alle' ? 'Alle' : name)
      + ' <span class="zahl">' + fertig + '/' + anzahl + '</span>';
    b.onclick = () => { filter = name; aktuell = 0; zeichne(); window.scrollTo(0, 0); };
    leiste.appendChild(b);
  }
}

function zeichne() {
  zeichneFilter();
  sichtbar = daten.filter(passt);
  const liste = document.getElementById('liste');
  liste.innerHTML = '';
  sichtbar.forEach((z, i) => {
    const box = document.createElement('div');
    box.className = 'clip' + (z.bewertung ? ' fertig' : '')
                           + (i === aktuell ? ' aktiv' : '');
    const dauer = z.crossfade_sek ? z.crossfade_sek + ' s Blende' : '';
    const tempo = (z.bpm_a && z.bpm_b)
      ? z.bpm_a + ' &rarr; ' + z.bpm_b + ' BPM'
      : '';
    const stil = (z.genre_a || z.genre_b)
      ? (z.genre_a === z.genre_b ? z.genre_a : z.genre_a + ' &rarr; ' + z.genre_b)
      : '';
    const tonart = (z.key_a && z.key_b) ? z.key_a + ' &rarr; ' + z.key_b : '';
    box.innerHTML =
      '<div class="kopf"><span class="id">' + z.pair_id + '</span>' +
      '<span class="meta">' + dauer + '</span></div>' +
      '<div class="fakten">' +
        (tempo ? '<span class="marke">' + tempo + '</span>' : '') +
        (stil ? '<span class="marke">' + stil + '</span>' : '') +
        (tonart ? '<span class="marke">' + tonart + '</span>' : '') +
      '</div>' +
      '<div class="titel">' + z.track_a + '<br>&rarr; ' + z.track_b + '</div>' +
      '<audio controls preload="metadata" src="/' + z.clip + '"></audio>' +
      '<div class="spur" title="Klicken springt an die Stelle">' +
        '<div class="mix"></div>' +
        '<div class="marke-a">A</div><div class="marke-b">B</div>' +
        '<div class="nadel"></div>' +
      '</div>' +
      '<div class="spurtext"></div>';
    const audio = box.querySelector('audio');
    const spur = box.querySelector('.spur');
    audio.addEventListener('loadedmetadata', () => zeichneSpur(box, z, audio));
    audio.addEventListener('timeupdate', () => {
      const nadel = box.querySelector('.nadel');
      nadel.style.left = (100 * audio.currentTime / audio.duration) + '%';
      nadel.style.display = 'block';
    });
    spur.addEventListener('click', ev => {
      if (!audio.duration) return;
      const kasten = spur.getBoundingClientRect();
      audio.currentTime = audio.duration * (ev.clientX - kasten.left) / kasten.width;
    });

    const noten = document.createElement('div');
    noten.className = 'noten';
    for (const n of [1,2,3,4,5]) {
      const b = document.createElement('button');
      b.textContent = n;
      if (String(z.bewertung) === String(n)) b.className = 'aktiv';
      b.onclick = () => setze(z.pair_id, n);
      noten.appendChild(b);
    }
    box.appendChild(noten);
    box.onclick = () => { aktuell = i; markiere(); };
    liste.appendChild(box);
  });
  zaehleFuss();
}

function zaehleFuss() {
  const fertigAlle = daten.filter(z => z.bewertung).length;
  const fertigHier = sichtbar.filter(z => z.bewertung).length;
  const teil = filter === 'alle' ? ''
    : filter + ': ' + fertigHier + ' von ' + sichtbar.length + '   |   ';
  document.getElementById('fuss').textContent =
    teil + 'gesamt ' + fertigAlle + ' von ' + daten.length + ' bewertet';
}

// Der Clip ist [Vorlauf A | Blende | Nachlauf B]. Die Blendenlaenge kommt aus
// merkmale.csv, der Nachlauf ist fest; der Vorlauf ergibt sich als Rest, weil
// der Renderer ihn kuerzt, wenn der Mix-Out nah am Trackanfang liegt.
function zeichneSpur(box, z, audio) {
  const dauer = audio.duration;
  const blende = parseFloat(z.crossfade_sek);
  if (!dauer || !isFinite(dauer) || !blende) return;
  const vorlauf = Math.max(0, dauer - blende - NACHLAUF);
  const start = 100 * vorlauf / dauer;
  const breite = 100 * blende / dauer;
  const mix = box.querySelector('.mix');
  mix.style.left = start + '%';
  mix.style.width = breite + '%';
  box.querySelector('.marke-a').style.right = (100 - start) + '%';
  box.querySelector('.marke-b').style.left = (start + breite) + '%';
  box.querySelector('.spurtext').textContent =
    'nur A bis ' + zeit(vorlauf) + '   |   Mix ' + zeit(vorlauf) + '–'
    + zeit(vorlauf + blende) + ' (' + blende.toFixed(1) + ' s)   |   nur B ab '
    + zeit(vorlauf + blende);
}

function zeit(s) {
  const m = Math.floor(s / 60);
  const r = Math.round(s % 60);
  return m + ':' + String(r).padStart(2, '0');
}

function markiere() {
  document.querySelectorAll('.clip').forEach((el, i) =>
    el.classList.toggle('aktiv', i === aktuell));
  const box = document.querySelectorAll('.clip')[aktuell];
  if (box) box.scrollIntoView({block: 'nearest'});
}

document.addEventListener('keydown', e => {
  if (e.key >= '1' && e.key <= '5' && sichtbar[aktuell]) {
    setze(sichtbar[aktuell].pair_id, Number(e.key));
    e.preventDefault();
  } else if (e.key === 'ArrowDown') {
    aktuell = Math.min(sichtbar.length - 1, aktuell + 1); markiere(); e.preventDefault();
  } else if (e.key === 'ArrowUp') {
    aktuell = Math.max(0, aktuell - 1); markiere(); e.preventDefault();
  } else if (e.key === ' ') {
    const audio = document.querySelectorAll('.clip audio')[aktuell];
    if (audio) { audio.paused ? audio.play() : audio.pause(); }
    e.preventDefault();
  }
});

async function setze(pairId, note) {
  const antwort = await fetch('/note', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({pair_id: pairId, note: note})
  });
  if (!antwort.ok) {
    document.getElementById('fuss').textContent =
      'Speichern fehlgeschlagen: ' + antwort.status;
    return;
  }
  // Nicht neu zeichnen: ein Neuaufbau wuerde das <audio>-Element ersetzen und
  // damit die laufende Wiedergabe abbrechen. Nur die betroffene Karte anfassen.
  const z = daten.find(x => x.pair_id === pairId);
  if (z) z.bewertung = String(note);
  const i = sichtbar.findIndex(x => x.pair_id === pairId);
  if (i < 0) return;
  const box = document.querySelectorAll('.clip')[i];
  box.classList.add('fertig');
  box.querySelectorAll('.noten button').forEach((b, k) =>
    b.classList.toggle('aktiv', k + 1 === note));
  zeichneFilter();
  zaehleFuss();
}

async function laden() {
  daten = await (await fetch('/daten')).json();
  zeichne();
}
laden();
</script>
</body>
</html>
"""


# Seite fuer den Kandidatenmodus: EIN Paar je Ansicht, alle Clips des Paars in
# der gespeicherten (zufaelligen) Reihenfolge, je Clip Note 1-5 und die Wahl
# "bester". Kein Score, kein Schema, keine Teilwerte (verdeckt).
SEITE_KANDIDATEN = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>HPG Hoertest — Kandidaten</title>
<style>
  :root { color-scheme: dark; }
  body { background:#0f1420; color:#e6e9f0; font:15px/1.5 system-ui,sans-serif;
         margin:0; padding:24px 16px 96px; }
  h1 { font-size:20px; margin:0 0 4px; }
  .hinweis { color:#8b93a7; margin:0 0 16px; }
  .kopf { position:sticky; top:0; z-index:5; max-width:820px; margin:0 auto 14px;
          padding:10px 0; background:#0f1420; border-bottom:1px solid #232c42; }
  .nav { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  .nav button { padding:7px 12px; font-size:14px; cursor:pointer; color:#c8cede;
                background:#161d2e; border:1px solid #2c3855; border-radius:20px; }
  .nav button:hover { background:#27334f; }
  .nav .stand { color:#8b93a7; font-size:13px; margin-left:auto; }
  .fakten { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0 0; }
  .marke { background:#1d2740; border:1px solid #2c3855; border-radius:5px;
           padding:2px 8px; font-size:12px; color:#c8cede; }
  .titel { color:#a8b0c4; font-size:13px; margin-top:6px; overflow-wrap:anywhere; }
  .clip { background:#161d2e; border:1px solid #232c42; border-radius:10px;
          padding:14px 16px; margin:0 auto 14px; max-width:820px; }
  .clip.fertig { border-color:#3b6b4a; }
  .clip.aktiv { box-shadow:0 0 0 2px #c8a02e; }
  .clip.bester { border-color:#c8a02e; }
  .clipkopf { display:flex; justify-content:space-between; gap:12px;
              align-items:baseline; margin-bottom:8px; }
  .id { font-weight:600; }
  .meta { color:#8b93a7; font-size:13px; }
  .spur { position:relative; height:26px; margin:2px 0 4px; border-radius:5px;
          background:#10182a; border:1px solid #2c3855; cursor:pointer; overflow:hidden; }
  .mix { position:absolute; top:0; bottom:0;
         background:linear-gradient(90deg,#c8a02e33,#c8a02e66,#c8a02e33);
         border-left:2px solid #c8a02e; border-right:2px solid #c8a02e; }
  .marke-a, .marke-b { position:absolute; top:0; bottom:0; display:flex;
                       align-items:center; padding:0 7px; font-size:11px;
                       font-weight:700; color:#8b93a7; }
  .marke-a { left:0; justify-content:flex-end; }
  .marke-b { right:0; }
  .nadel { position:absolute; top:0; bottom:0; width:2px; background:#e6e9f0; display:none; }
  .spurtext { color:#8b93a7; font-size:12px; margin-bottom:10px; }
  audio { width:100%; margin-bottom:10px; }
  .noten { display:flex; gap:8px; align-items:stretch; }
  .noten button { flex:1; padding:9px 0; font-size:15px; cursor:pointer;
                  background:#1d2740; color:#e6e9f0; border:1px solid #2c3855; border-radius:7px; }
  .noten button:hover { background:#27334f; }
  .noten button.aktiv { background:#c8a02e; color:#101010; font-weight:700; border-color:#c8a02e; }
  .noten button.wahl { flex:1.6; }
  .noten button.wahl.aktiv { background:#3b6b4a; color:#e6e9f0; border-color:#3b6b4a; }
  .fuss { position:fixed; left:0; right:0; bottom:0; padding:10px 16px;
          background:#0b0f19; border-top:1px solid #232c42; color:#8b93a7; }
</style>
</head>
<body>
<h1>HPG Hoertest — Kandidaten</h1>
<p class="hinweis">Gleiches Paar, andere Mixpunkte. Jeden Clip mit <b>1</b>&ndash;<b>5</b>
benoten <b>und</b> den besten waehlen (Taste <b>B</b>). <b>Pfeil hoch/runter</b> wechselt den Clip,
<b>Leertaste</b> spielt, <b>Bild auf/ab</b> wechselt das Paar. Alles wird sofort gespeichert.</p>
<div class="kopf" id="kopf"></div>
<div id="liste"></div>
<div class="fuss" id="fuss">lade ...</div>
<script>
const NACHLAUF = __NACHLAUF__;  // Sekunden Track B hinter der Blende
let paare = [];     // Gruppen vom Server, Clips bereits in gespeicherter Reihenfolge
let pi = 0;         // Index des angezeigten Paars
let aktuell = 0;    // Index des aktiven Clips im Paar

function paarAusUrl() {
  const m = new URLSearchParams(location.search).get('pair');
  const i = paare.findIndex(p => p.pair_id === m);
  return i >= 0 ? i : 0;
}

function fertig(p) { return p.clips.every(c => c.note) && p.clips.some(c => c.gewaehlt === '1'); }

function zeichneKopf() {
  const p = paare[pi];
  const kopf = document.getElementById('kopf');
  const tempo = (p.bpm_a && p.bpm_b) ? p.bpm_a + ' &rarr; ' + p.bpm_b + ' BPM' : '';
  const stil = (p.genre_a || p.genre_b)
    ? (p.genre_a === p.genre_b ? p.genre_a : p.genre_a + ' &rarr; ' + p.genre_b) : '';
  const tonart = (p.key_a && p.key_b) ? p.key_a + ' &rarr; ' + p.key_b : '';
  const n_fertig = paare.filter(fertig).length;
  kopf.innerHTML =
    '<div class="nav">' +
      '<button id="zurueck">&larr; Paar</button>' +
      '<button id="weiter">Paar &rarr;</button>' +
      '<span class="stand">Paar ' + (pi + 1) + ' von ' + paare.length +
      '   |   ' + n_fertig + ' vollstaendig</span>' +
    '</div>' +
    '<div class="fakten">' +
      '<span class="marke">' + p.pair_id + '</span>' +
      (tempo ? '<span class="marke">' + tempo + '</span>' : '') +
      (stil ? '<span class="marke">' + stil + '</span>' : '') +
      (tonart ? '<span class="marke">' + tonart + '</span>' : '') +
      '<span class="marke">' + p.clips.length + ' Kandidaten</span>' +
    '</div>' +
    '<div class="titel">' + p.track_a + '<br>&rarr; ' + p.track_b + '</div>';
  document.getElementById('zurueck').onclick = () => wechsle(-1);
  document.getElementById('weiter').onclick = () => wechsle(1);
}

function zeichne() {
  if (!paare.length) { document.getElementById('fuss').textContent = 'keine Paare'; return; }
  zeichneKopf();
  const p = paare[pi];
  const liste = document.getElementById('liste');
  liste.innerHTML = '';
  p.clips.forEach((c, i) => {
    const box = document.createElement('div');
    box.className = 'clip' + (c.note ? ' fertig' : '') + (c.gewaehlt === '1' ? ' bester' : '')
                           + (i === aktuell ? ' aktiv' : '');
    const dauer = c.crossfade_sek ? c.crossfade_sek + ' s Blende' : '';
    box.innerHTML =
      '<div class="clipkopf"><span class="id">Kandidat ' + (i + 1) + '</span>' +
      '<span class="meta">' + dauer + '</span></div>' +
      '<audio controls preload="metadata" src="/' + c.clip + '"></audio>' +
      '<div class="spur" title="Klicken springt an die Stelle">' +
        '<div class="mix"></div><div class="marke-a">A</div><div class="marke-b">B</div>' +
        '<div class="nadel"></div></div>' +
      '<div class="spurtext"></div>';
    const audio = box.querySelector('audio');
    const spur = box.querySelector('.spur');
    audio.addEventListener('loadedmetadata', () => zeichneSpur(box, c, audio));
    audio.addEventListener('timeupdate', () => {
      const nadel = box.querySelector('.nadel');
      nadel.style.left = (100 * audio.currentTime / audio.duration) + '%';
      nadel.style.display = 'block';
    });
    spur.addEventListener('click', ev => {
      if (!audio.duration) return;
      const kasten = spur.getBoundingClientRect();
      audio.currentTime = audio.duration * (ev.clientX - kasten.left) / kasten.width;
    });
    const noten = document.createElement('div');
    noten.className = 'noten';
    for (const n of [1,2,3,4,5]) {
      const b = document.createElement('button');
      b.textContent = n;
      if (String(c.note) === String(n)) b.className = 'aktiv';
      b.onclick = () => setzeNote(p.pair_id, c.clip_id, n);
      noten.appendChild(b);
    }
    const w = document.createElement('button');
    w.textContent = 'bester';
    w.className = 'wahl' + (c.gewaehlt === '1' ? ' aktiv' : '');
    w.onclick = () => setzeBester(p.pair_id, c.clip_id);
    noten.appendChild(w);
    box.appendChild(noten);
    box.onclick = () => { aktuell = i; markiere(); };
    liste.appendChild(box);
  });
  zaehleFuss();
}

function zaehleFuss() {
  const p = paare[pi];
  const noten = p.clips.filter(c => c.note).length;
  const wahl = p.clips.some(c => c.gewaehlt === '1') ? 'bester gewaehlt' : 'bester fehlt';
  document.getElementById('fuss').textContent =
    'Paar ' + p.pair_id + ': ' + noten + ' von ' + p.clips.length + ' benotet, ' + wahl +
    '   |   gesamt ' + paare.filter(fertig).length + ' von ' + paare.length + ' Paaren vollstaendig';
}

function zeichneSpur(box, c, audio) {
  const dauer = audio.duration;
  const blende = parseFloat(c.crossfade_sek);
  if (!dauer || !isFinite(dauer) || !blende) return;
  const vorlauf = Math.max(0, dauer - blende - NACHLAUF);
  const start = 100 * vorlauf / dauer;
  const breite = 100 * blende / dauer;
  const mix = box.querySelector('.mix');
  mix.style.left = start + '%';
  mix.style.width = breite + '%';
  box.querySelector('.marke-a').style.right = (100 - start) + '%';
  box.querySelector('.marke-b').style.left = (start + breite) + '%';
  box.querySelector('.spurtext').textContent =
    'nur A bis ' + zeit(vorlauf) + '   |   Mix ' + zeit(vorlauf) + '–' + zeit(vorlauf + blende) +
    ' (' + blende.toFixed(1) + ' s)   |   nur B ab ' + zeit(vorlauf + blende);
}

function zeit(s) {
  const m = Math.floor(s / 60);
  const r = Math.round(s % 60);
  return m + ':' + String(r).padStart(2, '0');
}

function markiere() {
  document.querySelectorAll('.clip').forEach((el, i) => el.classList.toggle('aktiv', i === aktuell));
  const box = document.querySelectorAll('.clip')[aktuell];
  if (box) box.scrollIntoView({block: 'nearest'});
}

function wechsle(schritt) {
  pi = Math.max(0, Math.min(paare.length - 1, pi + schritt));
  aktuell = 0;
  history.replaceState(null, '', '?pair=' + paare[pi].pair_id);
  zeichne();
  window.scrollTo(0, 0);
}

document.addEventListener('keydown', e => {
  const p = paare[pi];
  if (!p) return;
  if (e.key >= '1' && e.key <= '5' && p.clips[aktuell]) {
    setzeNote(p.pair_id, p.clips[aktuell].clip_id, Number(e.key)); e.preventDefault();
  } else if ((e.key === 'b' || e.key === 'B') && p.clips[aktuell]) {
    setzeBester(p.pair_id, p.clips[aktuell].clip_id); e.preventDefault();
  } else if (e.key === 'ArrowDown') {
    aktuell = Math.min(p.clips.length - 1, aktuell + 1); markiere(); e.preventDefault();
  } else if (e.key === 'ArrowUp') {
    aktuell = Math.max(0, aktuell - 1); markiere(); e.preventDefault();
  } else if (e.key === 'PageDown') { wechsle(1); e.preventDefault();
  } else if (e.key === 'PageUp') { wechsle(-1); e.preventDefault();
  } else if (e.key === ' ') {
    const audio = document.querySelectorAll('.clip audio')[aktuell];
    if (audio) { audio.paused ? audio.play() : audio.pause(); }
    e.preventDefault();
  }
});

async function sende(pfad, koerper) {
  const antwort = await fetch(pfad, {method: 'POST', headers: {'Content-Type': 'application/json'},
                                     body: JSON.stringify(koerper)});
  if (!antwort.ok) {
    document.getElementById('fuss').textContent = 'Speichern fehlgeschlagen: ' + antwort.status;
    return false;
  }
  return true;
}

async function setzeNote(pairId, clipId, note) {
  if (!await sende('/note', {pair_id: pairId, clip_id: clipId, note: note})) return;
  const p = paare[pi];
  const i = p.clips.findIndex(c => c.clip_id === clipId);
  if (i < 0) return;
  p.clips[i].note = String(note);
  // Nur die Karte anfassen — ein Neuaufbau wuerde das <audio> ersetzen.
  const box = document.querySelectorAll('.clip')[i];
  box.classList.add('fertig');
  box.querySelectorAll('.noten button:not(.wahl)').forEach((b, k) => b.classList.toggle('aktiv', k + 1 === note));
  zeichneKopf(); zaehleFuss();
}

async function setzeBester(pairId, clipId) {
  if (!await sende('/bester', {pair_id: pairId, clip_id: clipId})) return;
  const p = paare[pi];
  p.clips.forEach(c => { c.gewaehlt = (c.clip_id === clipId) ? '1' : ''; });
  document.querySelectorAll('.clip').forEach((box, k) => {
    const ist = p.clips[k].clip_id === clipId;
    box.classList.toggle('bester', ist);
    box.querySelector('.noten button.wahl').classList.toggle('aktiv', ist);
  });
  zeichneKopf(); zaehleFuss();
}

async function laden() {
  paare = await (await fetch('/daten')).json();
  pi = paarAusUrl();
  zeichne();
}
laden();
</script>
</body>
</html>
"""


class HoertestHandler(BaseHTTPRequestHandler):
    """Bedient die Routen /, /noten, /daten, /reihenfolge, /clips/<name> (GET) und
    /note, /bester (POST). Alles andere ist 404."""

    ordner: Path = Path(".")
    track_infos: dict = {}
    reihenfolge: dict = {}

    server_version = "HPG-Hoertest"

    def log_message(self, format, *args):  # noqa: A002 - Signatur der Basisklasse
        # Standardausgabe pro Datei-Request waere bei 160 Clips nur Laerm.
        pass

    # --- Hilfen ---------------------------------------------------------
    def _sende(self, status: int, typ: str, koerper: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(koerper)))
        self.end_headers()
        self.wfile.write(koerper)

    def _bewertung_pfad(self) -> Path:
        return self.ordner / "bewertung.csv"

    def _kandidatenmodus(self) -> bool:
        return ist_kandidatensatz(lies_csv(self._bewertung_pfad()))

    # --- Routen ---------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - Name der Basisklasse
        pfad = self.path.split("?", 1)[0]
        if pfad in ("/", "/index.html"):
            vorlage = SEITE_KANDIDATEN if self._kandidatenmodus() else SEITE
            seite = vorlage.replace("__NACHLAUF__", repr(float(NACHLAUF_SEK)))
            self._sende(200, "text/html; charset=utf-8", seite.encode("utf-8"))
            return
        if pfad == "/reihenfolge":
            koerper = json.dumps(self.reihenfolge).encode("utf-8")
            self._sende(200, "application/json; charset=utf-8", koerper)
            return
        if pfad == "/noten":
            # Protokoll des unversionierten Vorlaeufers
            # (Music\HPG-Hoertest-Probe2\hoertest_server.py): pair_id -> Note.
            # Beibehalten, damit die dort liegenden bewerten.html-Seiten nicht
            # gegen ein zweites, abweichendes Protokoll laufen.
            noten = {
                str(z.get("pair_id", "")).strip(): int(z["bewertung"])
                for z in lies_csv(self._bewertung_pfad())
                if str(z.get("bewertung") or "").strip().isdigit()
            }
            koerper = json.dumps(noten).encode("utf-8")
            self._sende(200, "application/json; charset=utf-8", koerper)
            return
        if pfad == "/daten":
            if self._kandidatenmodus():
                uebersicht = lade_uebersicht_kandidaten(
                    lies_csv(self.ordner / "merkmale.csv"),
                    lies_csv(self._bewertung_pfad()),
                    self.reihenfolge,
                    self.track_infos,
                )
            else:
                uebersicht = lade_uebersicht(
                    lies_csv(self.ordner / "merkmale.csv"),
                    lies_csv(self._bewertung_pfad()),
                    self.track_infos,
                )
            koerper = json.dumps(uebersicht, ensure_ascii=False).encode("utf-8")
            self._sende(200, "application/json; charset=utf-8", koerper)
            return
        if pfad.startswith("/clips/"):
            self._sende_clip(pfad[len("/clips/"):])
            return
        self._sende(404, "text/plain; charset=utf-8", b"nicht gefunden")

    def _sende_clip(self, name: str) -> None:
        """Liefert einen Clip aus, mit Bereichsanfragen.

        Ein <audio>-Element fordert Bytebereiche an (Range) und bricht die
        Verbindung ab, sobald es genug hat oder der Nutzer weiterspringt. Ohne
        206-Antwort laedt der Browser jede WAV vollstaendig (bis 25 MB) und
        kann nicht spulen; die abgebrochenen Verbindungen erschienen als
        ConnectionAbortedError. Deshalb: Bereiche beantworten und blockweise
        schreiben.
        """
        try:
            datei = sichere_clip_datei(self.ordner / "clips", name)
        except ValueError:
            self._sende(400, "text/plain; charset=utf-8", b"unerlaubter Name")
            return
        if not datei.is_file():
            self._sende(404, "text/plain; charset=utf-8", b"Clip fehlt")
            return

        groesse = datei.stat().st_size
        start, ende = lies_range(self.headers.get("Range"), groesse)
        laenge = ende - start + 1

        self.send_response(206 if start or ende != groesse - 1 else 200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(laenge))
        if start or ende != groesse - 1:
            self.send_header("Content-Range", f"bytes {start}-{ende}/{groesse}")
        self.end_headers()

        try:
            with datei.open("rb") as handle:
                handle.seek(start)
                rest = laenge
                while rest > 0:
                    block = handle.read(min(BLOCK, rest))
                    if not block:
                        break
                    self.wfile.write(block)
                    rest -= len(block)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # Normalfall beim Spulen oder Clipwechsel — kein Fehler des Servers.
            pass

    def do_POST(self) -> None:  # noqa: N802 - Name der Basisklasse
        pfad = self.path.split("?", 1)[0]
        if self._kandidatenmodus() and pfad in ("/note", "/bester"):
            self._post_kandidaten(pfad)
            return
        # Pfad und Nutzlast wie beim Vorlaeufer: {"pair_id": ..., "note": 1..5},
        # note=null loescht die Note wieder.
        if pfad != "/note":
            self._sende(404, "text/plain; charset=utf-8", b"nicht gefunden")
            return
        laenge = int(self.headers.get("Content-Length") or 0)
        try:
            daten = json.loads(self.rfile.read(laenge) or b"{}")
            pair_id = str(daten.get("pair_id", "")).strip()
            note = daten.get("note")
            if note is not None and int(note) not in NOTEN:
                raise ValueError("Note muss 1 bis 5 sein")
            noten = {pair_id: None if note is None else int(note)}
        except (ValueError, TypeError, AttributeError):
            self._sende(400, "text/plain; charset=utf-8", b"ungueltige Note")
            return
        zeilen = lies_csv(self._bewertung_pfad())
        schreibe_csv(
            self._bewertung_pfad(),
            BEWERTUNG_SPALTEN,
            merge_bewertungen(zeilen, noten),
        )
        self._sende(200, "application/json; charset=utf-8", b'{"ok":true}')


    def _post_kandidaten(self, pfad: str) -> None:
        """Kandidatenmodus: /note {pair_id, clip_id, note|null}, /bester
        {pair_id, clip_id}; beides mit Zeitstempel in bewertung.csv."""
        laenge = int(self.headers.get("Content-Length") or 0)
        try:
            daten = json.loads(self.rfile.read(laenge) or b"{}")
            pair_id = str(daten.get("pair_id", "")).strip()
            clip_id = str(daten.get("clip_id", "")).strip()
            if not pair_id or not clip_id:
                raise ValueError("pair_id und clip_id noetig")
            note = daten.get("note")
            if pfad == "/note" and note is not None and int(note) not in NOTEN:
                raise ValueError("Note muss 1 bis 5 sein")
        except (ValueError, TypeError, AttributeError):
            self._sende(400, "text/plain; charset=utf-8", b"ungueltige Eingabe")
            return
        zeit = datetime.datetime.now().isoformat(timespec="seconds")
        zeilen = lies_csv(self._bewertung_pfad())
        if pfad == "/bester":
            neu = merge_kandidaten_bewertung(zeilen, pair_id=pair_id, clip_id=clip_id, bester=True, zeit=zeit)
        else:
            neu = merge_kandidaten_bewertung(zeilen, pair_id=pair_id, clip_id=clip_id,
                                            note=None if note is None else int(note), zeit=zeit)
        schreibe_csv(self._bewertung_pfad(), BEWERTUNG_KANDIDATEN_SPALTEN, neu)
        self._sende(200, "application/json; charset=utf-8", b'{"ok":true}')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", required=True, help="Hoertest-Ordner von prepare")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    ordner = Path(args.dir)
    if not (ordner / "bewertung.csv").exists():
        print(f"Keine bewertung.csv in {ordner} — erst `prepare` laufen lassen.")
        return 2

    HoertestHandler.ordner = ordner
    HoertestHandler.track_infos = lade_track_infos()
    reihenfolge_pfad = ordner / "reihenfolge.json"
    HoertestHandler.reihenfolge = (
        json.loads(reihenfolge_pfad.read_text(encoding="utf-8")) if reihenfolge_pfad.is_file() else {}
    )
    if ist_kandidatensatz(lies_csv(ordner / "bewertung.csv")):
        print("Kandidatenmodus erkannt (Spalte clip_id): Seite je Paar, Note + bester.")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), HoertestHandler)
    print(f"Hoertest laeuft: http://127.0.0.1:{args.port}   (Strg+C beendet)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbeendet")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
