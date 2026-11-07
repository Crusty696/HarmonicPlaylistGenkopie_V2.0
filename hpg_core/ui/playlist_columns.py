"""Eine Definition für Identität, Beschriftung und Darstellung der Spalten."""
from dataclasses import dataclass
from enum import IntEnum


class PlaylistColumn(IntEnum):
    POSITION = 0
    TITLE = 1
    ARTIST = 2
    DURATION = 3
    BPM = 4
    KEY = 5
    CAMELOT = 6
    ENERGY = 7
    GENRE = 8
    GENRE_CONFIDENCE = 9
    MIX_IN = 10
    MIX_OUT = 11
    BASS = 12
    TIMBRE = 13
    TRANSITION = 14
    AI_INSIGHTS = 15


@dataclass(frozen=True)
class ColumnDefinition:
    column: PlaylistColumn
    title: str
    tooltip: str
    width: int
    core: bool


PLAYLIST_COLUMNS = (
    ColumnDefinition(PlaylistColumn.POSITION, '#', 'Position in der Playlist.\nDrag & Drop zum Umsortieren.', 40, True),
    ColumnDefinition(PlaylistColumn.TITLE, 'Titel', 'Dateiname des Audio-Tracks.', 180, True),
    ColumnDefinition(PlaylistColumn.ARTIST, 'Interpret', 'Interpret (aus ID3-Tag oder Dateiname).', 120, True),
    ColumnDefinition(PlaylistColumn.DURATION, 'Dauer', 'Gesamtlaenge des Tracks (Minuten:Sekunden).', 60, False),
    ColumnDefinition(PlaylistColumn.BPM, 'BPM', 'Beats Per Minute – das Tempo des Tracks.', 60, True),
    ColumnDefinition(PlaylistColumn.KEY, 'Tonart', 'Musikalische Tonart (z.B. C Major, A Minor).', 80, False),
    ColumnDefinition(PlaylistColumn.CAMELOT, 'Camelot', 'Camelot-Code fuer harmonisches Mixing.', 70, True),
    ColumnDefinition(PlaylistColumn.ENERGY, 'Energie', 'Energie-Level des Tracks (0-100).', 60, True),
    ColumnDefinition(PlaylistColumn.GENRE, 'Genre', 'Automatisch erkanntes Genre.', 100, False),
    ColumnDefinition(PlaylistColumn.GENRE_CONFIDENCE, 'Genre %', 'Konfidenz der Genre-Erkennung (0-100%).', 60, False),
    ColumnDefinition(PlaylistColumn.MIX_IN, 'Mix-In', 'Mix-In-Punkt: Dynamisch berechneter Startpunkt für den Mix (nach Intro).', 70, False),
    ColumnDefinition(PlaylistColumn.MIX_OUT, 'Mix-Out', 'Mix-Out-Punkt: Dynamisch berechneter Endpunkt für den Mix (vor Outro).', 70, False),
    ColumnDefinition(PlaylistColumn.BASS, 'Bass %', 'Bass %: Trackweiter Mittelwert des Bassanteils aus der Audioanalyse. Für Übergangs- und EQ-Hinweise werden bevorzugt die Werte der Mix-Out-/Mix-In-Sektionen betrachtet.', 65, False),
    ColumnDefinition(PlaylistColumn.TIMBRE, 'Klangfarbe', 'Klangfarbe zum vorherigen Track: Vergleich der trackweiten MFCC-Messwerte. Keine Aussage über Tonart oder Synchronität.', 205, False),
    ColumnDefinition(PlaylistColumn.TRANSITION, 'Übergang', 'Freigegebener Übergang zum vorherigen Track: Passung (0-100%). Ohne Freigabe erscheint der Ablehnungsgrund.', 310, True),
    ColumnDefinition(PlaylistColumn.AI_INSIGHTS, 'KI-Beschreibung', 'Optionale KI-Beschreibung zu Stimmung und Charakter.', 180, False),
)
