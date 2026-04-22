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
MAX_DURATION_MS = 45 * 60 * 1000  # 45 minutes — Groq/OpenAI 25MB limit safety cap


def prepare_audio(file_path: str) -> str:
    """
    Convert audio to a clean wav temp file for the Whisper API.
    No noise reduction, no resampling — just format normalization.
    Returns the path to the temp wav file (caller must delete it).
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED:
        raise ValueError(f"Unsupported audio format: {ext}")

    audio = AudioSegment.from_file(file_path)

    if len(audio) > MAX_DURATION_MS:
        audio = audio[:MAX_DURATION_MS]

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    audio.export(tmp.name, format="wav")
    return tmp.name
