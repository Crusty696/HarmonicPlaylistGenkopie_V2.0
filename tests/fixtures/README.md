# HPG Test Fixtures and Infrastructure

Complete test infrastructure for the Harmonic Playlist Generator with deterministic audio generators, track factories, and Camelot test data.

## Directory Structure

```
tests/
├── fixtures/
│   ├── __init__.py              # Exports all fixtures
│   ├── audio_generators.py      # Deterministic audio signal generators
│   ├── track_factories.py       # Track object factories with DJ defaults
│   └── camelot_test_data.py     # Camelot wheel mappings and compatibility rules
├── conftest.py                  # Pytest fixtures and configuration
└── test_infrastructure_demo.py  # Usage examples
```

## Audio Generators (`audio_generators.py`)

### Click Track Generation
```python
from tests.fixtures import generate_click_track

# Create deterministic BPM test signal
audio, sr = generate_click_track(bpm=128.0, duration=10.0, sr=44100)
# Perfect for BPM detection validation
```

### Pure Tone Generation
```python
from tests.fixtures import generate_tone

# Create pure sine tone for key detection
audio, sr = generate_tone(frequency=440.0, duration=5.0, sr=44100)
# A440 reference tone
```

### Structured Track Generation
```python
from tests.fixtures import generate_track_with_structure

# Create track with intro/body/outro sections
audio, sr = generate_track_with_structure(
    bpm=128.0,
    duration=180.0,
    intro_ratio=0.15,  # 15% intro
    outro_ratio=0.85,  # 85% outro start
    sr=44100
)
# Perfect for mix point detection tests
```

### Chord Generation
```python
from tests.fixtures import generate_major_chord, generate_minor_chord

# Create chords for key detection
a_minor = generate_minor_chord('A', duration=3.0, sr=44100)
c_major = generate_major_chord('C', duration=3.0, sr=44100)
```

## Track Factories (`track_factories.py`)

### Basic Track Creation
```python
from tests.fixtures import make_track

# Create track with DJ defaults
track = make_track()
# BPM: 128.0, Key: "8A", Energy: 0.75, Duration: 180s

# Override defaults
track = make_track(bpm=140.0, key="5A", energy=0.95)
```

### Genre-Specific Factories
```python
from tests.fixtures import make_house_track, make_techno_track, make_dnb_track

house = make_house_track()    # 124-128 BPM
techno = make_techno_track()  # 130-140 BPM
dnb = make_dnb_track()        # 170-180 BPM
```

### Compatible Track Pairs
```python
from tests.fixtures import make_compatible_pair

# Create harmonically compatible tracks
track_a, track_b = make_compatible_pair(
    base_key="8A",
    relation="energy_up",  # Options: "same", "energy_up", "energy_down", "relative"
    bpm_diff=0.0
)
# track_a: "8A", track_b: "9A" (energy boost)
```

### Playlist Sets
```python
from tests.fixtures import make_playlist_set

# Create 8-track DJ set with progression
tracks = make_playlist_set(
    num_tracks=8,
    base_bpm=128.0,
    progression="energy_boost"  # Options: "energy_boost", "wave", "plateau", "random"
)
# Creates cohesive DJ set with harmonic flow
```

## Camelot Test Data (`camelot_test_data.py`)

### Camelot Wheel Mappings
```python
from tests.fixtures import CAMELOT_WHEEL

# Complete 24-key wheel
wheel = CAMELOT_WHEEL
# {
#   "1A": {"key": "A♭m", "compatible": ["1A", "12A", "2A", "1B"], "pitch": 0},
#   ...
# }
```

### Compatibility Rules
```python
from tests.fixtures import COMPATIBILITY_RULES

# All 9 harmonic mixing rules with scores
for rule in COMPATIBILITY_RULES:
    name, description, score, type_, semitone_distance, mode_change = rule
    # "Perfect Match", "Same key (1A -> 1A)", 100, "same", 0, False
```

### Expected Compatibility Scores
```python
from tests.fixtures import COMPATIBILITY_SCORES

# Expected scores for key pairs
score = COMPATIBILITY_SCORES[("8A", "9A")]  # 90 (energy boost)
score = COMPATIBILITY_SCORES[("8A", "8B")]  # 95 (relative major/minor)
```

### Helper Functions
```python
from tests.fixtures import get_related_key, get_semitone_distance, is_compatible

# Get harmonically related key
next_key = get_related_key("8A", "energy_up")  # "9A"
relative = get_related_key("8A", "relative")    # "8B"

# Calculate semitone distance
distance = get_semitone_distance("8A", "9A")  # 1

# Check compatibility
compatible = is_compatible("8A", "9A", threshold=60)  # True
```

## Pytest Fixtures (`conftest.py`)

### Audio Fixtures
```python
def test_bpm_detection(click_128bpm):
    """Uses pre-generated 128 BPM click track."""
    assert detect_bpm(click_128bpm) == 128.0

def test_key_detection(a_minor_chord):
    """Uses pre-generated A minor chord."""
    assert detect_key(a_minor_chord) == "8A"
```

### Track Fixtures
```python
def test_compatibility(default_track):
    """Uses standard house track."""
    assert default_track.bpm == 128.0

def test_playlist(dj_set_8tracks):
    """Uses 8-track DJ set."""
    assert len(dj_set_8tracks) == 8
```

### Available Fixtures

**Audio Fixtures:**
- `click_128bpm` - 128 BPM click track (10s)
- `click_120bpm` - 120 BPM click track (10s)
- `silence_10s` - 10 seconds of silence
- `noise_10s` - 10 seconds white noise
- `structured_audio_128bpm` - Structured 5-minute track
- `a_minor_chord` - A minor chord (3s)
- `c_major_chord` - C major chord (3s)

**Track Fixtures:**
- `default_track` - Standard house track
- `house_track` - House genre defaults
- `techno_track` - Techno genre defaults
- `dnb_track` - Drum & Bass defaults
- `minimal_track` - Only required fields
- `dj_set_8tracks` - 8-track cohesive set
- `dj_set_3tracks` - Minimal 3-track set
- `all_camelot_tracks` - One track per Camelot code

**Test Data Fixtures:**
- `compatibility_rules` - All harmonic rules
- `incompatible_pairs` - Known incompatible keys
- `bpm_tolerance_cases` - BPM tolerance test cases

## Usage Examples

### BPM Detection Test
```python
def test_bpm_detection_accuracy():
    """Test BPM detection with known signal."""
    # Generate precise 128 BPM signal
    audio, sr = generate_click_track(bpm=128.0, duration=10.0, sr=44100)

    # Detect BPM
    detected_bpm = detect_bpm(audio, sr)

    # Validate within tolerance
    assert abs(detected_bpm - 128.0) <= 1.0
```

### Key Detection Test
```python
def test_key_detection_a_minor():
    """Test key detection with A minor chord."""
    # Generate pure A minor chord
    audio = generate_minor_chord('A', duration=3.0)

    # Detect key
    detected_key = detect_key(audio)

    # Should detect as "8A" (A minor)
    assert detected_key == "8A"
```

### Mix Point Detection Test
```python
def test_mix_point_detection():
    """Test mix point detection with structured track."""
    # Generate track with known structure
    audio, sr = generate_track_with_structure(
        bpm=128.0,
        duration=180.0,
        intro_ratio=0.15,
        outro_ratio=0.85
    )

    # Detect mix points
    mix_in, mix_out = detect_mix_points(audio, sr, bpm=128.0)

    # Validate against known structure
    expected_mix_in = 180.0 * 0.15  # 27s
    expected_mix_out = 180.0 * 0.85  # 153s

    assert abs(mix_in - expected_mix_in) < 5.0
    assert abs(mix_out - expected_mix_out) < 5.0
```

### Compatibility Test
```python
def test_harmonic_compatibility(compatibility_rules):
    """Test compatibility scoring with known rules."""
    for key1, key2, expected_score, rule_name in compatibility_rules:
        calculated_score = calculate_compatibility(key1, key2)
        assert calculated_score == expected_score, \
            f"Rule '{rule_name}' failed: {key1} -> {key2}"
```

### Playlist Generation Test
```python
def test_playlist_generation():
    """Test playlist generation with cohesive set."""
    # Create 8-track source pool
    tracks = make_playlist_set(8, progression="energy_boost")

    # Generate playlist
    playlist = generate_playlist(tracks, length=8)

    # Verify progression
    assert len(playlist) == 8
    assert playlist[0].energy < playlist[-1].energy

    # Verify harmonic flow
    for i in range(len(playlist) - 1):
        score = calculate_compatibility(
            playlist[i].key,
            playlist[i+1].key
        )
        assert score >= 60, "Adjacent tracks should be compatible"
```

## Pytest Markers

Tests are automatically marked based on content:

- `@pytest.mark.audio` - Audio processing tests
- `@pytest.mark.slow` - Tests taking >1 second
- `@pytest.mark.integration` - Multi-component tests

Run specific test types:
```bash
pytest -m audio          # Only audio tests
pytest -m "not slow"     # Skip slow tests
pytest -m integration    # Only integration tests
```

## Best Practices

1. **Use Deterministic Generators**: All audio generators use fixed seeds for reproducibility
2. **Batch Fixtures**: Use pytest fixtures for expensive operations
3. **Clear Test Names**: Name tests by what they validate, not how
4. **Known Values**: Test against mathematically known values, not estimated
5. **Edge Cases**: Use minimal_track and empty_track_list for boundary tests

## See Also

- `test_infrastructure_demo.py` - Complete usage examples
- Individual test files for real-world usage patterns
