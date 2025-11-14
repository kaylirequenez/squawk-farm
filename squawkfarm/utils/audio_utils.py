"""Audio utilities: loading, saving, normalization helpers."""
from typing import Tuple

from imslib.audio import Audio

def frame_to_time(frame: int) -> float:
    """Convert frame index to time in seconds."""
    return frame / Audio.sample_rate

def time_to_frame(time: float) -> int:
    """Convert time in seconds to frame index."""
    return int(time * Audio.sample_rate)

def load_wav(path: str) -> Tuple[int, bytes]:
    """Load a WAV file. Returns (sample_rate, raw_bytes).

    Stubbed: real implementation should return numpy arrays or similar.
    """
    raise NotImplementedError("Implement WAV loading using soundfile or wave+numpy")


def save_wav(path: str, sample_rate: int, data: bytes) -> None:
    """Save bytes as a WAV file. Stub."""
    raise NotImplementedError("Implement WAV saving")


def normalize_audio(data):
    """Normalize audio buffer to -1..1 range (stub)."""
    raise NotImplementedError("Implement normalization")
