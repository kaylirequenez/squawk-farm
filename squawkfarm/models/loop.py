"""Loop-related data structures."""

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class GlobalLoopSettings:
    bpm: int = 100  # tempo
    measures: int = 2  # measures in the global loop
    time_sig: Tuple[int, int] = (4, 4)  # time signature (numerator, denominator)

@dataclass
class AnimalLoop:
    animal_id: str

    audio_path: str  # the wav to actually play
    
    start_frame: int       # what frame to start at within the recording
    num_frames: int        # how many frames to play from the recording
    
    volume: float = 0.5 # 1.0 = max volume
    pitch_shift: float = 0.0 # in semitones

    # sections of the audio to play in the global loop
    start_slots: List[int] = field(default_factory=list)
    
    # the last state of the audio data from the wave buffer (with possible muted sections)
    audio_data: List[float] = field(default_factory=list)