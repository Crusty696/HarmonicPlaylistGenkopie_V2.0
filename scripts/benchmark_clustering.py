
import time
import random
from hpg_core.playlist import cluster_tracks_by_similarity
from hpg_core.models import Track

def generate_mock_tracks(n, dim=13):
    tracks = []
    for i in range(n):
        mfcc = [random.uniform(-100, 100) for _ in range(dim)]
        tracks.append(Track(
            filePath=f"path/to/track_{i}.mp3",
            fileName=f"track_{i}.mp3",
            title=f"Track {i}",
            bpm=random.uniform(60, 180),
            camelotCode="8A",
            energy=random.randint(1, 100),
            mfcc_fingerprint=mfcc
        ))
    return tracks

def benchmark():
    n_tracks = 2000
    n_clusters = 50
    max_iterations = 20

    print(f"Generating {n_tracks} tracks...")
    tracks = generate_mock_tracks(n_tracks)

    print(f"Clustering into {n_clusters} clusters (max_iterations={max_iterations})...")
    start_time = time.time()
    clusters = cluster_tracks_by_similarity(tracks, n_clusters=n_clusters, max_iterations=max_iterations)
    end_time = time.time()

    duration = end_time - start_time
    print(f"Clustering took {duration:.4f} seconds.")
    return duration

if __name__ == "__main__":
    # Run a few times to get a stable average
    durations = []
    for i in range(5):
        print(f"Run {i+1}/5:")
        durations.append(benchmark())

    avg_duration = sum(durations) / len(durations)
    print(f"\nAverage duration: {avg_duration:.4f} seconds.")
