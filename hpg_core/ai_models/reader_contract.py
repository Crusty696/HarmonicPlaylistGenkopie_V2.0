"""Gemeinsame Provenienzlabels der Analyse-Reader."""

NATIVE_BEAT_INPUT_CONVENTIONS = {
    'rekordbox-builtin': 'rekordbox-builtin-planar-float32',
    'rekordbox-mpg123': 'rekordbox-mpg123-planar-float32',
    'rekordbox-mpg123-soxr-hq': 'rekordbox-mpg123-soxr-hq-planar-float32',
    'rekordbox-mpg123-stream': 'rekordbox-mpg123-stream-planar-float32',
    'rekordbox-mpg123-soxr-hq-stream': 'rekordbox-mpg123-soxr-hq-stream-planar-float32',
    'hpg-libsndfile': 'hpg-libsndfile-planar-float32',
    'hpg-librosa': 'hpg-librosa-planar-float32',
    'hpg-libsndfile-soxr-hq-44100': 'hpg-libsndfile-soxr-hq-44100-planar-float32',
    'hpg-libsndfile-pcm16-44100': 'hpg-libsndfile-pcm16-44100-planar-float32',
    'hpg-libsndfile-mono-downmix-44100': 'hpg-libsndfile-mono-downmix-planar-float32',
    'hpg-librosa-mono-downmix-44100': 'hpg-librosa-mono-downmix-planar-float32',
    'hpg-audioread-pcm16-44100': 'hpg-audioread-pcm16-44100-planar-float32',
    'hpg-audioread-soxr-hq-44100': 'hpg-audioread-soxr-hq-44100-planar-float32',
    'hpg-audioread-mono-downmix-44100': 'hpg-audioread-mono-downmix-planar-float32',
}

# Der gemeinsame Validator und der Beat-Adapter teilen dieselbe Backendliste;
# ein neu zugelassener Reader kann so nicht still ohne Modellkonvention bleiben.
READER_BACKENDS = frozenset(NATIVE_BEAT_INPUT_CONVENTIONS)
