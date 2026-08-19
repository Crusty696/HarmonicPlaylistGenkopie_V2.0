"""CLI-Werkzeug: schaetzt Toleranzen fuer das Transition-Scoring aus echten DJ-Mixen.

Findet Uebergangsstellen in einem Mix ueber `find_transitions`, misst je ein
stabiles Fenster vor und hinter der Blend-Zone und vergleicht diese echten
Uebergaenge gegen zufaellige Fensterpaare aus demselben Mix. Ein Faktor, der
echte Uebergaenge von Zufallspaaren trennt, beschreibt eine echte
DJ-Entscheidung und bekommt Gewicht (siehe hpg_core/mix_analysis.py).

Aufruf:
    python tools/mix_mining.py --genre Psytrance --mix <pfad-oder-url> \
        [--mix ...] [--holdout <pfad-oder-url>] --out kennzahlen.json

Reine Logik (testbar ohne Audio) und Ein-/Ausgabe-Code sind getrennt:
- Beschaffung (`beschaffe_audio`) und Fenstermessung (`miss_fenster`,
  `mine_mix`) fassen Dateien/Netzwerk/librosa an.
- `baue_zufallspaare`, `berechne_auc_richtung` und `baue_ergebnis` sind rein
  und werden in tests/test_mix_mining.py getestet.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import librosa
import numpy as np

from hpg_core.groove import extract_groove
from hpg_core.mix_analysis import (
    TransitionSample,
    deltas_between,
    discrimination_auc,
    find_transitions,
    holdout_passed,
    learn_weights,
    tolerance_percentile,
    window_bounds,
)

logger = logging.getLogger("mix_mining")

# Analyse-Samplerate — reicht fuer Rhythmus/Bass/Timbre und haelt lange Mixe
# bezahlbar.
SR = 22050

# Faktoren, bei denen ein HOHER Wert fuer einen echten Uebergang spricht
# ("higher is better"). Alle anderen wirken umgekehrt (niedriger ist besser).
HOEHER_IST_BESSER = {"groove_sim": True, "timbre_sim": True}
NIEDRIGER_IST_BESSER = {"sub_delta": False, "punch_delta": False, "brightness_delta": False}
AUC_RICHTUNG = {**HOEHER_IST_BESSER, **NIEDRIGER_IST_BESSER}

# Umrechnung Spektralschwerpunkt (Hz) auf eine 0-100-Helligkeitsskala.
BRIGHTNESS_HZ_TEILER = 80.0

# Anzahl der Zufallspaare je Mix — deutlich mehr als echte Uebergaenge,
# damit die AUC-Schaetzung nicht auf wenigen Stichproben zittert.
ZUFALLSPAARE_JE_MIX = 30
ZUFALLS_SEED = 42


# ---------------------------------------------------------------------------
# Beschaffung (Netzwerk/Dateisystem)
# ---------------------------------------------------------------------------

def ist_lokale_datei(mix: str) -> bool:
    """True, wenn `mix` ein existierender lokaler Pfad ist."""
    return Path(mix).is_file()


def beschaffe_audio(mix: str, ziel_verzeichnis: Path) -> Path | None:
    """Liefert einen lokalen Audiopfad fuer `mix`.

    Lokale Dateien werden unveraendert verwendet. Alles andere wird per
    yt-dlp als Opus in `ziel_verzeichnis` geladen. Bei Fehlschlag None und
    eine Warnung im Log — ein einzelner defekter Mix darf den restlichen
    Lauf nicht abbrechen.
    """
    if ist_lokale_datei(mix):
        return Path(mix)

    ziel = ziel_verzeichnis / "download.%(ext)s"
    try:
        subprocess.run(
            [
                "yt-dlp", "-f", "bestaudio", "-x", "--audio-format", "opus",
                "-o", str(ziel), mix,
            ],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as exc:
        # Die eigentliche Ursache steht in stderr, nicht im Exception-Text.
        # Ohne diese Zeile meldet das Log nur "exit status 1" und den
        # Aufrufbefehl — der Grund (403, fehlende JS-Laufzeit, geoblockt,
        # Video privat) bleibt unsichtbar und muss von Hand nachgestellt
        # werden.
        grund = (exc.stderr or "").strip().splitlines()
        logger.warning(
            "Download fehlgeschlagen fuer %s (exit %s): %s",
            mix, exc.returncode, grund[-1] if grund else "keine Fehlerausgabe",
        )
        for zeile in grund[-4:-1]:
            logger.warning("  %s", zeile)
        return None
    except FileNotFoundError:
        logger.warning(
            "yt-dlp nicht gefunden — fuer URLs noetig, lokale Dateien "
            "funktionieren ohne. Uebersprungen: %s", mix,
        )
        return None

    treffer = list(ziel_verzeichnis.glob("download.*"))
    if not treffer:
        logger.warning("Download lieferte keine Datei fuer %s", mix)
        return None
    return treffer[0]


# ---------------------------------------------------------------------------
# Fenstermessung (librosa)
# ---------------------------------------------------------------------------

def miss_fenster(y: np.ndarray, sr: int) -> TransitionSample:
    """Misst ein Fenster-Ausschnitt und baut daraus ein TransitionSample."""
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(tempo) if np.ndim(tempo) == 0 else float(tempo[0])
    groove = extract_groove(y=y, sr=sr, bpm=bpm, first_downbeat=0.0)

    centroid = librosa.feature.spectral_centroid(y=y, sr=sr).mean()
    brightness = min(100.0, float(centroid) / BRIGHTNESS_HZ_TEILER)

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13).mean(axis=1)

    return TransitionSample(
        groove_pattern=list(groove.groove_pattern),
        bass_pattern=list(groove.bass_pattern),
        sub_energy=groove.sub_energy,
        bass_punch=groove.bass_punch,
        brightness=brightness,
        timbre=[float(v) for v in mfcc],
    )


def mine_mix(pfad: Path) -> tuple[list[dict], list[TransitionSample]]:
    """Findet Uebergaenge in einem Mix und misst die Fenster daneben.

    Rueckgabe: (Deltas je echtem Uebergang, alle gemessenen Fenster fuer
    den anschliessenden Zufallspaar-Schritt).
    """
    y, sr = librosa.load(str(pfad), sr=SR, mono=True)
    dauer = len(y) / float(sr)
    logger.info("%s geladen, Dauer %.1f s", pfad.name, dauer)

    stellen = find_transitions(y, sr)
    logger.info("%d Uebergangsstellen gefunden", len(stellen))

    echte_deltas: list[dict] = []
    alle_fenster: list[TransitionSample] = []
    for stelle in stellen:
        grenzen = window_bounds(stelle, dauer)
        if grenzen is None:
            continue
        (vor_start, vor_ende), (nach_start, nach_ende) = grenzen
        vor = miss_fenster(y[int(vor_start * sr):int(vor_ende * sr)], sr)
        nach = miss_fenster(y[int(nach_start * sr):int(nach_ende * sr)], sr)
        delta = deltas_between(vor, nach)
        # Zeitstempel mitschreiben: ohne ihn laesst sich nicht pruefen, ob
        # eine gefundene Stelle ein echter DJ-Uebergang ist oder nur eine
        # Moderationsgrenze. Bei Sendungen mit Sprechanteilen ballen sich
        # Fehltreffer typischerweise am Anfang und um die Talkbloecke.
        delta["stelle_s"] = float(stelle)
        echte_deltas.append(delta)
        alle_fenster.append(vor)
        alle_fenster.append(nach)

    logger.info("%d Fenster gemessen", len(alle_fenster))
    if echte_deltas:
        zeiten = [d["stelle_s"] for d in echte_deltas]
        abstaende = [b - a for a, b in zip(zeiten, zeiten[1:])]
        logger.info(
            "Stellen von %.0f s bis %.0f s, Abstand Median %.0f s",
            zeiten[0], zeiten[-1],
            sorted(abstaende)[len(abstaende) // 2] if abstaende else 0.0,
        )
    return echte_deltas, alle_fenster


# ---------------------------------------------------------------------------
# Reine Logik (kein Audio, kein Dateizugriff) — hier testbar
# ---------------------------------------------------------------------------

def _skalen_aus(deltas: list[dict]) -> dict[str, float]:
    """Groesster beobachteter Betrag je Faktor — Bezugsgroesse fuers Normieren."""
    skalen: dict[str, float] = {}
    for faktor in AUC_RICHTUNG:
        werte = [abs(float(d[faktor])) for d in deltas if faktor in d]
        skalen[faktor] = max(werte) if werte else 1.0
    return skalen


def kombinierter_score(
    delta: dict, gewichte: dict[str, float], skalen: dict[str, float]
) -> float:
    """Gewichteter Gesamtscore eines Paares; hoeher = eher echter Uebergang.

    Faktoren, bei denen ein NIEDRIGER Wert fuer einen Uebergang spricht
    (Abstaende), werden umgedreht, damit alle in dieselbe Richtung zeigen.
    """
    summe = 0.0
    gewicht_summe = 0.0
    for faktor, hoeher_ist_besser in AUC_RICHTUNG.items():
        if faktor not in delta:
            continue
        w = gewichte.get(faktor, 0.0)
        if w <= 0.0:
            continue
        skala = skalen.get(faktor) or 1.0
        wert = min(1.0, abs(float(delta[faktor])) / skala)
        summe += w * (wert if hoeher_ist_besser else 1.0 - wert)
        gewicht_summe += w
    return summe / gewicht_summe if gewicht_summe > 0 else 0.0


def baue_zufallspaare(
    fenster: list[TransitionSample], anzahl: int = ZUFALLSPAARE_JE_MIX,
    seed: int = ZUFALLS_SEED,
) -> list[tuple[int, int]]:
    """Zieht `anzahl` zufaellige, unterschiedliche Fensterpaare (Indizes).

    Fester Seed macht das Ergebnis reproduzierbar. Bei weniger als zwei
    Fenstern gibt es keine gueltigen Paare.
    """
    if len(fenster) < 2:
        return []
    rng = random.Random(seed)
    paare: list[tuple[int, int]] = []
    for _ in range(anzahl):
        i, j = rng.sample(range(len(fenster)), 2)
        paare.append((i, j))
    return paare


def zufallsdeltas_aus_fenstern(
    fenster: list[TransitionSample], anzahl: int = ZUFALLSPAARE_JE_MIX,
    seed: int = ZUFALLS_SEED,
) -> list[dict]:
    """Berechnet die Deltas fuer zufaellige Fensterpaare (die Negativklasse)."""
    paare = baue_zufallspaare(fenster, anzahl=anzahl, seed=seed)
    return [deltas_between(fenster[i], fenster[j]) for i, j in paare]


def berechne_auc_richtung(echte: list[dict], zufall: list[dict]) -> dict[str, float]:
    """AUC je Faktor, unter Beachtung der Richtung (hoeher/niedriger ist besser)."""
    auc: dict[str, float] = {}
    for faktor, hoeher_ist_besser in AUC_RICHTUNG.items():
        echte_werte = [d[faktor] for d in echte]
        zufalls_werte = [d[faktor] for d in zufall]
        auc[faktor] = discrimination_auc(echte_werte, zufalls_werte, hoeher_ist_besser)
    return auc


def berechne_toleranzen(echte: list[dict]) -> dict[str, float | None]:
    """Toleranzgrenzen aus den echten Uebergaengen.

    groove_sim ist eine Untergrenze (10. Perzentil): darunter gilt eine
    Groove-Aehnlichkeit als untypisch fuer einen echten Mix. sub_delta und
    brightness_delta sind Obergrenzen (90. Perzentil).
    """
    return {
        "groove_sim_min": tolerance_percentile(
            [d["groove_sim"] for d in echte], 10.0
        ),
        "sub_delta_max": tolerance_percentile(
            [d["sub_delta"] for d in echte], 90.0
        ),
        "brightness_delta_max": tolerance_percentile(
            [d["brightness_delta"] for d in echte], 90.0
        ),
    }


def baue_ergebnis(
    genre: str,
    echte_deltas: list[dict],
    zufalls_deltas: list[dict],
    holdout: bool | None,
) -> dict:
    """Fasst AUC, gelernte Gewichte, Toleranzen und Holdout zum Ausgabe-JSON zusammen."""
    auc = berechne_auc_richtung(echte_deltas, zufalls_deltas)
    roh_gewichte = learn_weights(auc)
    gewichte = {
        "groove_weight": roh_gewichte.get("groove_sim", 0.0),
        "bass_weight": roh_gewichte.get("sub_delta", 0.0) + roh_gewichte.get("punch_delta", 0.0),
        "timbre_weight": roh_gewichte.get("timbre_sim", 0.0),
        "mood_weight": roh_gewichte.get("brightness_delta", 0.0),
    }
    return {
        "genre": genre,
        "anzahl_uebergaenge": len(echte_deltas),
        "anzahl_zufallspaare": len(zufalls_deltas),
        "auc": auc,
        "gewichte": gewichte,
        "toleranzen": berechne_toleranzen(echte_deltas),
        "holdout": holdout,
        # Fundstellen in Sekunden — die Pruefspur fuer die Frage, ob die
        # Erkennung echte Uebergaenge getroffen hat oder Sprechgrenzen.
        "stellen_s": [round(d["stelle_s"], 1) for d in echte_deltas
                      if "stelle_s" in d],
    }


# ---------------------------------------------------------------------------
# Orchestrierung (CLI)
# ---------------------------------------------------------------------------

def verarbeite_mix(mix: str) -> tuple[list[dict], list[TransitionSample]] | None:
    """Beschafft und mint einen einzelnen Mix; None bei Fehlschlag."""
    with tempfile.TemporaryDirectory() as tmp:
        pfad = beschaffe_audio(mix, Path(tmp))
        if pfad is None:
            return None
        try:
            return mine_mix(pfad)
        except Exception as exc:  # noqa: BLE001 — ein defekter Mix darf den Lauf nicht abbrechen
            logger.warning("Analyse fehlgeschlagen fuer %s: %s", mix, exc)
            return None


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--genre", required=True)
    parser.add_argument("--mix", action="append", required=True, dest="mixe")
    parser.add_argument("--holdout", default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    alle_echten_deltas: list[dict] = []
    alle_fenster: list[TransitionSample] = []
    for mix in args.mixe:
        ergebnis = verarbeite_mix(mix)
        if ergebnis is None:
            continue
        echte_deltas, fenster = ergebnis
        alle_echten_deltas.extend(echte_deltas)
        alle_fenster.extend(fenster)

    if not alle_echten_deltas:
        logger.error("Keine Uebergangsstellen in einem der Mixe gefunden — Abbruch.")
        return 1

    # Die Genauigkeit der AUC haengt an der KLEINEREN der beiden Klassen.
    # Ein fester Deckel von 30 Negativbeispielen macht 167 gesammelte
    # Uebergaenge wertlos: das Konfidenzintervall bleibt so breit wie bei
    # 30 gegen 30. Deshalb mindestens so viele Zufallspaare wie echte
    # Uebergaenge ziehen.
    zufalls_deltas = zufallsdeltas_aus_fenstern(
        alle_fenster, anzahl=max(ZUFALLSPAARE_JE_MIX, len(echte_deltas))
    )

    # Gewichte schon hier lernen: der Holdout braucht sie, um den
    # GESAMTSCORE zu pruefen statt eines einzelnen Faktors.
    gewichte_roh = learn_weights(berechne_auc_richtung(echte_deltas, zufalls_deltas))

    holdout_ergebnis: bool | None = None
    if args.holdout:
        holdout_daten = verarbeite_mix(args.holdout)
        if holdout_daten is None:
            logger.warning("Holdout-Mix konnte nicht verarbeitet werden.")
        else:
            holdout_echte, holdout_fenster = holdout_daten
            holdout_zufall = zufallsdeltas_aus_fenstern(
                holdout_fenster,
                anzahl=max(ZUFALLSPAARE_JE_MIX, len(holdout_echte)),
            )
            # Geprueft wird der GELERNTE GESAMTSCORE, nicht ein einzelner
            # Faktor. Frueher stand hier groove_sim allein — ausgerechnet der
            # schwaechste der fuenf. Der Test verwarf damit Kalibrierungen,
            # die von timbre_sim und sub_delta klar gestuetzt wurden.
            skalen = _skalen_aus(echte_deltas + zufalls_deltas)
            holdout_ergebnis = holdout_passed(
                [kombinierter_score(d, gewichte_roh, skalen) for d in holdout_echte],
                [kombinierter_score(d, gewichte_roh, skalen) for d in holdout_zufall],
            )
            if not holdout_ergebnis:
                logger.warning(
                    "Holdout-Test nicht bestanden — gelernte Werte fuer %s "
                    "nicht belastbar genug fuer den Einbau.", args.genre
                )

    ergebnis = baue_ergebnis(args.genre, alle_echten_deltas, zufalls_deltas, holdout_ergebnis)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(ergebnis, f, indent=2, ensure_ascii=False)
    logger.info("Ergebnis geschrieben nach %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
