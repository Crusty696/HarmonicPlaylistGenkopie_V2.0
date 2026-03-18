
import math
from typing import List, Optional
from dataclasses import dataclass, field

@dataclass
class Track:
    filePath: str
    fileName: str
    title: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    bpm: float = 0.0
    keyNote: str = ""
    keyMode: str = ""
    camelotCode: str = ""
    energy: int = 0
    duration: float = 0.0
    mix_in_point: float = 0.0
    mix_out_point: float = 0.0
    mfcc_fingerprint: List[float] = field(default_factory=list)
    detected_genre: str = "Unknown"

def mfcc_distance(fp1: list, fp2: list) -> float:
    if not fp1 or not fp2:
        return float("inf")
    if len(fp1) != len(fp2):
        return float("inf")
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(fp1, fp2)))

def cluster_tracks_by_similarity_ORIGINAL(
    tracks: list[Track],
    n_clusters: int = 3,
    max_iterations: int = 50,
) -> list[list[Track]]:
    with_mfcc = [
        t for t in tracks if t.mfcc_fingerprint and len(t.mfcc_fingerprint) > 0
    ]
    without_mfcc = [
        t for t in tracks if not t.mfcc_fingerprint or len(t.mfcc_fingerprint) == 0
    ]

    if len(with_mfcc) <= n_clusters:
        clusters = [[t] for t in with_mfcc]
        if without_mfcc:
            clusters.append(without_mfcc)
        return clusters

    step = len(with_mfcc) // n_clusters
    centroids = [list(with_mfcc[i * step].mfcc_fingerprint) for i in range(n_clusters)]

    assignments = [0] * len(with_mfcc)

    total_assign_time = 0
    total_update_time = 0
    for _ in range(max_iterations):
        t0 = time.time()
        new_assignments = []
        for track in with_mfcc:
            dists = [mfcc_distance(track.mfcc_fingerprint, c) for c in centroids]
            new_assignments.append(dists.index(min(dists)))

        if new_assignments == assignments:
            break
        assignments = new_assignments
        t1 = time.time()
        total_assign_time += (t1 - t0)

        t2 = time.time()
        dim = len(centroids[0])
        for k in range(n_clusters):
            members = [with_mfcc[i] for i, a in enumerate(assignments) if a == k]
            if not members:
                continue
            new_centroid = [0.0] * dim
            for m in members:
                for d in range(dim):
                    new_centroid[d] += m.mfcc_fingerprint[d]
            centroids[k] = [v / len(members) for v in new_centroid]
        t3 = time.time()
        total_update_time += (t3 - t2)

    print(f"  Assign time: {total_assign_time:.4f}s")
    print(f"  Update time: {total_update_time:.4f}s")

    clusters = [[] for _ in range(n_clusters)]
    for i, a in enumerate(assignments):
        clusters[a].append(with_mfcc[i])
    clusters = [c for c in clusters if c]
    if without_mfcc:
        clusters.append(without_mfcc)
    return clusters

def cluster_tracks_by_similarity_OPTIMIZED(
    tracks: list[Track],
    n_clusters: int = 3,
    max_iterations: int = 50,
) -> list[list[Track]]:
    with_mfcc = [
        t for t in tracks if t.mfcc_fingerprint and len(t.mfcc_fingerprint) > 0
    ]
    without_mfcc = [
        t for t in tracks if not t.mfcc_fingerprint or len(t.mfcc_fingerprint) == 0
    ]

    if len(with_mfcc) <= n_clusters:
        clusters = [[t] for t in with_mfcc]
        if without_mfcc:
            clusters.append(without_mfcc)
        return clusters

    step = len(with_mfcc) // n_clusters
    centroids = [list(with_mfcc[i * step].mfcc_fingerprint) for i in range(n_clusters)]

    assignments = [0] * len(with_mfcc)

    total_assign_time = 0
    total_update_time = 0
    for _ in range(max_iterations):
        t0 = time.time()
        new_assignments = []
        for track in with_mfcc:
            dists = [mfcc_distance(track.mfcc_fingerprint, c) for c in centroids]
            new_assignments.append(dists.index(min(dists)))

        if new_assignments == assignments:
            break
        assignments = new_assignments
        t1 = time.time()
        total_assign_time += (t1 - t0)

        t2 = time.time()
        dim = len(centroids[0])

        # OPTIMIZATION: Build mapping from cluster ID to member indices
        cluster_to_member_indices = [[] for _ in range(n_clusters)]
        for i, a in enumerate(assignments):
            cluster_to_member_indices[a].append(i)

        for k in range(n_clusters):
            member_indices = cluster_to_member_indices[k]
            if not member_indices:
                continue

            new_centroid = [0.0] * dim
            for idx in member_indices:
                m = with_mfcc[idx]
                for d in range(dim):
                    new_centroid[d] += m.mfcc_fingerprint[d]
            centroids[k] = [v / len(member_indices) for v in new_centroid]
        t3 = time.time()
        total_update_time += (t3 - t2)

    print(f"  Assign time: {total_assign_time:.4f}s")
    print(f"  Update time: {total_update_time:.4f}s")

    clusters = [[] for _ in range(n_clusters)]
    for i, a in enumerate(assignments):
        clusters[a].append(with_mfcc[i])
    clusters = [c for c in clusters if c]
    if without_mfcc:
        clusters.append(without_mfcc)
    return clusters

import time
import random

def generate_mock_tracks(n, dim=13):
    tracks = []
    for i in range(n):
        mfcc = [random.uniform(-100, 100) for _ in range(dim)]
        tracks.append(Track(
            filePath=f"path/to/track_{i}.mp3",
            fileName=f"track_{i}.mp3",
            title=f"Track {i}",
            mfcc_fingerprint=mfcc
        ))
    return tracks

def benchmark():
    n_tracks = 2000
    n_clusters = 200
    max_iterations = 20

    print(f"Generating {n_tracks} tracks...")
    tracks = generate_mock_tracks(n_tracks)

    print(f"Benchmarking ORIGINAL...")
    start_time = time.time()
    cluster_tracks_by_similarity_ORIGINAL(tracks, n_clusters=n_clusters, max_iterations=max_iterations)
    original_duration = time.time() - start_time
    print(f"ORIGINAL took {original_duration:.4f} seconds.")

    print(f"Benchmarking OPTIMIZED...")
    start_time = time.time()
    cluster_tracks_by_similarity_OPTIMIZED(tracks, n_clusters=n_clusters, max_iterations=max_iterations)
    optimized_duration = time.time() - start_time
    print(f"OPTIMIZED took {optimized_duration:.4f} seconds.")

    improvement = (original_duration - optimized_duration) / original_duration * 100
    print(f"Improvement: {improvement:.2f}%")

if __name__ == "__main__":
    benchmark()
