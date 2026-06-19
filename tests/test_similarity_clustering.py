"""
Tests fuer MFCC-basiertes Similarity Clustering.
Prueft Distanzberechnung, Track-Suche und k-Means Clustering.
"""
import pytest
import math
from hpg_core.playlist import (
    mfcc_distance,
    find_similar_tracks,
    cluster_tracks_by_similarity,
    get_cluster_summary,
)
from hpg_core.models import Track


# === Hilfsfunktionen ===

def _make_track(
    title: str = "Test",
    bpm: float = 128.0,
    camelot: str = "8A",
    energy: int = 50,
    mfcc: list | None = None,
    genre: str = "Unknown",
) -> Track:
  """Erstellt einen Track mit optionalem MFCC-Fingerprint."""
  return Track(
    filePath="test.mp3",
    fileName="test.mp3",
    title=title,
    bpm=bpm,
    camelotCode=camelot,
    energy=energy,
    mfcc_fingerprint=mfcc if mfcc is not None else [],
    detected_genre=genre,
  )


# === mfcc_distance Tests ===

class TestMfccDistance:
  """Tests fuer die MFCC-Distanzberechnung."""

  def test_identical_vectors_zero(self):
    fp = [1.0, 2.0, 3.0]
    assert mfcc_distance(fp, fp) == 0.0

  def test_known_distance(self):
    """Euklidische Distanz [0,0] -> [3,4] = 5."""
    assert mfcc_distance([0.0, 0.0], [3.0, 4.0]) == pytest.approx(5.0)

  def test_single_dimension(self):
    assert mfcc_distance([10.0], [13.0]) == pytest.approx(3.0)

  def test_empty_first_returns_inf(self):
    assert mfcc_distance([], [1.0, 2.0]) == float('inf')

  def test_empty_second_returns_inf(self):
    assert mfcc_distance([1.0, 2.0], []) == float('inf')

  def test_both_empty_returns_inf(self):
    assert mfcc_distance([], []) == float('inf')

  def test_different_lengths_returns_inf(self):
    assert mfcc_distance([1.0, 2.0], [1.0]) == float('inf')

  def test_symmetric(self):
    fp1 = [1.0, 5.0, -3.0]
    fp2 = [2.0, 1.0, 0.0]
    assert mfcc_distance(fp1, fp2) == pytest.approx(mfcc_distance(fp2, fp1))

  def test_non_negative(self):
    fp1 = [-5.0, 10.0, 3.14]
    fp2 = [7.0, -2.0, 1.0]
    assert mfcc_distance(fp1, fp2) >= 0.0

  def test_13_dim_real_world(self):
    """Typischer 13-dimensionaler MFCC-Vektor."""
    fp1 = [-200.0, 100.0, -50.0, 30.0, 20.0, -10.0, 5.0, 3.0, -2.0, 1.0, 0.5, -0.3, 0.1]
    fp2 = [-180.0, 90.0, -45.0, 28.0, 18.0, -8.0, 4.0, 2.5, -1.5, 0.8, 0.4, -0.2, 0.08]
    dist = mfcc_distance(fp1, fp2)
    assert dist > 0
    assert dist < 100  # Aehnliche Tracks sollten relativ nah sein


# === find_similar_tracks Tests ===

class TestFindSimilarTracks:
  """Tests fuer die Track-Aehnlichkeitssuche."""

  def test_finds_closest_track(self):
    ref = _make_track(title="Ref", mfcc=[0.0, 0.0, 0.0])
    close = _make_track(title="Close", mfcc=[1.0, 0.0, 0.0])
    far = _make_track(title="Far", mfcc=[10.0, 10.0, 10.0])
    result = find_similar_tracks(ref, [close, far])
    assert len(result) == 2
    assert result[0][0].title == "Close"
    assert result[0][1] < result[1][1]

  def test_max_results_limit(self):
    ref = _make_track(title="Ref", mfcc=[0.0, 0.0])
    candidates = [
      _make_track(title=f"T{i}", mfcc=[float(i), 0.0]) for i in range(20)
    ]
    result = find_similar_tracks(ref, candidates, max_results=5)
    assert len(result) == 5

  def test_max_distance_filter(self):
    ref = _make_track(title="Ref", mfcc=[0.0, 0.0])
    close = _make_track(title="Close", mfcc=[1.0, 0.0])
    far = _make_track(title="Far", mfcc=[100.0, 0.0])
    result = find_similar_tracks(ref, [close, far], max_distance=5.0)
    assert len(result) == 1
    assert result[0][0].title == "Close"

  def test_excludes_reference_track(self):
    ref = _make_track(title="Ref", mfcc=[0.0, 0.0])
    result = find_similar_tracks(ref, [ref])
    assert len(result) == 0

  def test_empty_candidates(self):
    ref = _make_track(title="Ref", mfcc=[0.0, 0.0])
    result = find_similar_tracks(ref, [])
    assert result == []

  def test_reference_without_mfcc(self):
    ref = _make_track(title="Ref", mfcc=[])
    other = _make_track(title="Other", mfcc=[1.0, 2.0])
    result = find_similar_tracks(ref, [other])
    assert result == []

  def test_candidates_without_mfcc_skipped(self):
    ref = _make_track(title="Ref", mfcc=[0.0, 0.0])
    no_mfcc = _make_track(title="NoMFCC", mfcc=[])
    with_mfcc = _make_track(title="WithMFCC", mfcc=[1.0, 1.0])
    result = find_similar_tracks(ref, [no_mfcc, with_mfcc])
    assert len(result) == 1
    assert result[0][0].title == "WithMFCC"

  def test_sorted_by_distance(self):
    ref = _make_track(title="Ref", mfcc=[0.0, 0.0])
    t1 = _make_track(title="Near", mfcc=[1.0, 0.0])
    t2 = _make_track(title="Mid", mfcc=[5.0, 0.0])
    t3 = _make_track(title="Far", mfcc=[10.0, 0.0])
    result = find_similar_tracks(ref, [t3, t1, t2])
    titles = [r[0].title for r in result]
    assert titles == ["Near", "Mid", "Far"]

  def test_returns_tuples(self):
    ref = _make_track(title="Ref", mfcc=[0.0])
    other = _make_track(title="Other", mfcc=[3.0])
    result = find_similar_tracks(ref, [other])
    assert len(result) == 1
    assert isinstance(result[0], tuple)
    assert isinstance(result[0][0], Track)
    assert isinstance(result[0][1], float)


# === cluster_tracks_by_similarity Tests ===

class TestClusterTracks:
  """Tests fuer das k-Means Clustering."""

  def _make_cluster_tracks(self):
    """Erstellt 9 Tracks in 3 Gruppen mit klaren MFCC-Unterschieden."""
    # Cluster A: MFCC ~[0, 0]
    a1 = _make_track(title="A1", mfcc=[0.0, 0.0])
    a2 = _make_track(title="A2", mfcc=[0.5, 0.3])
    a3 = _make_track(title="A3", mfcc=[0.2, -0.1])
    # Cluster B: MFCC ~[50, 50]
    b1 = _make_track(title="B1", mfcc=[50.0, 50.0])
    b2 = _make_track(title="B2", mfcc=[51.0, 49.0])
    b3 = _make_track(title="B3", mfcc=[49.5, 50.5])
    # Cluster C: MFCC ~[-100, 100]
    c1 = _make_track(title="C1", mfcc=[-100.0, 100.0])
    c2 = _make_track(title="C2", mfcc=[-99.0, 101.0])
    c3 = _make_track(title="C3", mfcc=[-101.0, 99.0])
    return [a1, a2, a3, b1, b2, b3, c1, c2, c3]

  def test_creates_requested_clusters(self):
    tracks = self._make_cluster_tracks()
    clusters = cluster_tracks_by_similarity(tracks, n_clusters=3)
    # Sollte 3 Cluster ergeben (keine leeren)
    assert len(clusters) == 3

  def test_all_tracks_assigned(self):
    tracks = self._make_cluster_tracks()
    clusters = cluster_tracks_by_similarity(tracks, n_clusters=3)
    total = sum(len(c) for c in clusters)
    assert total == 9

  def test_cluster_groups_similar_tracks(self):
    """A/B/C Tracks sollten in separaten Clustern landen."""
    tracks = self._make_cluster_tracks()
    clusters = cluster_tracks_by_similarity(tracks, n_clusters=3)

    # Finde Cluster fuer jeden Track
    track_clusters = {}
    for ci, cluster in enumerate(clusters):
      for t in cluster:
        track_clusters[t.title] = ci

    # A-Tracks sollten im gleichen Cluster sein
    assert track_clusters["A1"] == track_clusters["A2"] == track_clusters["A3"]
    # B-Tracks sollten im gleichen Cluster sein
    assert track_clusters["B1"] == track_clusters["B2"] == track_clusters["B3"]
    # C-Tracks sollten im gleichen Cluster sein
    assert track_clusters["C1"] == track_clusters["C2"] == track_clusters["C3"]

  def test_empty_list(self):
    clusters = cluster_tracks_by_similarity([], n_clusters=3)
    assert clusters == []

  def test_fewer_tracks_than_clusters(self):
    t1 = _make_track(title="T1", mfcc=[1.0, 2.0])
    t2 = _make_track(title="T2", mfcc=[3.0, 4.0])
    clusters = cluster_tracks_by_similarity([t1, t2], n_clusters=5)
    # Jeder Track ist ein eigenes Cluster
    assert len(clusters) == 2
    total = sum(len(c) for c in clusters)
    assert total == 2

  def test_tracks_without_mfcc_separate_cluster(self):
    t_mfcc = _make_track(title="HasMFCC", mfcc=[1.0, 2.0])
    t_no = _make_track(title="NoMFCC", mfcc=[])
    clusters = cluster_tracks_by_similarity([t_mfcc, t_no], n_clusters=2)
    # t_no sollte in einem eigenen Cluster landen
    has_no_mfcc_cluster = any(
      any(t.title == "NoMFCC" for t in cluster) for cluster in clusters
    )
    assert has_no_mfcc_cluster

  def test_single_cluster(self):
    tracks = [
      _make_track(title=f"T{i}", mfcc=[float(i), 0.0]) for i in range(5)
    ]
    clusters = cluster_tracks_by_similarity(tracks, n_clusters=1)
    assert len(clusters) == 1
    assert len(clusters[0]) == 5

  def test_returns_list_of_lists(self):
    tracks = [
      _make_track(title=f"T{i}", mfcc=[float(i)]) for i in range(6)
    ]
    clusters = cluster_tracks_by_similarity(tracks, n_clusters=2)
    assert isinstance(clusters, list)
    for c in clusters:
      assert isinstance(c, list)
      for t in c:
        assert isinstance(t, Track)


# === get_cluster_summary Tests ===

class TestClusterSummary:
  """Tests fuer die Cluster-Zusammenfassung."""

  def test_basic_summary(self):
    t1 = _make_track(title="T1", bpm=128.0, energy=70, genre="Tech House")
    t2 = _make_track(title="T2", bpm=130.0, energy=75, genre="Tech House")
    clusters = [[t1, t2]]
    summaries = get_cluster_summary(clusters)
    assert len(summaries) == 1
    s = summaries[0]
    assert s["size"] == 2
    assert s["avg_bpm"] == pytest.approx(129.0)
    assert s["avg_energy"] == pytest.approx(72.5)
    assert s["cluster_id"] == 0

  def test_bpm_range(self):
    t1 = _make_track(bpm=120.0)
    t2 = _make_track(bpm=140.0)
    summaries = get_cluster_summary([[t1, t2]])
    assert summaries[0]["bpm_range"] == (120.0, 140.0)

  def test_top_genres(self):
    t1 = _make_track(genre="Psytrance")
    t2 = _make_track(genre="Psytrance")
    t3 = _make_track(genre="Techno")
    summaries = get_cluster_summary([[t1, t2, t3]])
    top = summaries[0]["top_genres"]
    assert top[0][0] == "Psytrance"
    assert top[0][1] == 2

  def test_empty_clusters_skipped(self):
    summaries = get_cluster_summary([[], [_make_track()]])
    assert len(summaries) == 1

  def test_tracks_preview(self):
    tracks = [_make_track(title=f"Track{i}") for i in range(10)]
    summaries = get_cluster_summary([tracks])
    assert len(summaries[0]["tracks"]) == 5  # Maximal 5 Titel

  def test_multiple_clusters(self):
    c1 = [_make_track(title="A", bpm=128.0)]
    c2 = [_make_track(title="B", bpm=174.0)]
    summaries = get_cluster_summary([c1, c2])
    assert len(summaries) == 2
    assert summaries[0]["cluster_id"] == 0
    assert summaries[1]["cluster_id"] == 1

  def test_zero_bpm_tracks(self):
    t = _make_track(bpm=0.0, energy=0)
    summaries = get_cluster_summary([[t]])
    assert summaries[0]["avg_bpm"] == 0.0
    assert summaries[0]["avg_energy"] == 0.0
