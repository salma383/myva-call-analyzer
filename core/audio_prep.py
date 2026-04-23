import os
import tempfile
import shutil
from pydub import AudioSegment
from pydub.utils import which

# Point pydub at ffmpeg if it's not on PATH (winget installs to a non-PATH location)
_FFMPEG_WINGET = os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"
)
if not which("ffmpeg"):
    for root, dirs, files in os.walk(_FFMPEG_WINGET):
        if "ffmpeg.exe" in files:
            AudioSegment.converter = os.path.join(root, "ffmpeg.exe")
            AudioSegment.ffmpeg = os.path.join(root, "ffmpeg.exe")
            break

SUPPORTED = {".mp3", ".wav", ".m4a", ".mp4", ".ogg", ".flac", ".webm"}
MAX_DURATION_MS = 45 * 60 * 1000  # 45 minutes — OpenAI 25MB safety cap

# Whisper internally resamples everything to 16kHz mono, so giving it a
# pre-compressed 16kHz mono mp3 produces IDENTICAL transcription quality
# while shrinking upload size by 10–20x (much faster network round-trip).
TARGET_SAMPLE_RATE = 16000
TARGET_BITRATE = "64k"


def prepare_audio(file_path: str) -> str:
    """
    Down-mix audio to 16kHz mono mp3 for fastest Whisper upload.
    Quality is unchanged because Whisper downsamples to 16kHz mono internally.
    Returns the path to the temp mp3 file (caller must delete it).
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED:
        raise ValueError(f"Unsupported audio format: {ext}")

    audio = AudioSegment.from_file(file_path)

    # Trim overly long files first (before resampling — saves CPU)
    if len(audio) > MAX_DURATION_MS:
        audio = audio[:MAX_DURATION_MS]

    # 16kHz mono is the sweet spot for Whisper
    audio = audio.set_frame_rate(TARGET_SAMPLE_RATE).set_channels(1)

    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    audio.export(tmp.name, format="mp3", bitrate=TARGET_BITRATE)
    return tmp.name
