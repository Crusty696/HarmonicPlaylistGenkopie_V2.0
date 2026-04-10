import librosa
try:
    print(librosa.get_duration(filename="dummy.mp3"))
except Exception as e:
    print(e)
