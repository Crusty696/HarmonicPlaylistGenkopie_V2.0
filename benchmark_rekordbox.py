import time
from hpg_core.rekordbox_importer import RekordboxImporter

# Mock db logic manually
importer = RekordboxImporter()
# populate track cache with dummy data
importer.track_cache = {f'/path/to/folder{i}/track{i}.wav': 'data' for i in range(10000)}
# also manually mock basename cache if it exists (for later comparison)
if hasattr(importer, 'basename_cache'):
    importer.basename_cache = {f'track{i}.wav': 'data' for i in range(10000)}
importer.db = 'mock_db'

start = time.time()
for i in range(1000):
    importer.get_track_data(f'/different/path/track{i}.wav')
end = time.time()
print(f'Fallback search took {end - start:.4f} seconds')
