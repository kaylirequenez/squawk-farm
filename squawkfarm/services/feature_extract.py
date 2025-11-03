"""Feature extraction utilities: .wav -> features.

These are stubs to be implemented. Keep the function signatures stable
so other modules can import them while you implement internals.
"""

from dataclasses import dataclass


@dataclass
class AudioFeatures:
    pitch: float
    duration: float
    loudness: float


def extract_features(wav_path: str) -> AudioFeatures:
    """Extract features from a WAV file at `wav_path`.

    Returns an AudioFeatures dataclass. Current implementation is a stub.
    """
    pass
