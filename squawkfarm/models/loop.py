"""Loop-related data structures."""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class GlobalLoopSettings:
    bpm: int = 100  # tempo
    measures: int = 2  # measures in the global loop
    time_sig: Tuple[int, int] = (4, 4)  # time signature (numerator, denominator)
    
@dataclass
class AnimalLoopSection:
    # 1) where in the GLOBAL loop
    start_slot: int             # slot in the global loop to start playing

    # 2) where in the AUDIO file
    start_frame: int   # what frame to start at within the recording
    num_frames: int    # how many frames to play from the recording

    # 3) the last state of the audio data from this section of the file (with possible muted sections)
    audio_data: Optional[List[float]] = field(default_factory=list)

@dataclass
class AnimalLoop:
    animal_id: str

    audio_path: str  # the wav to actually play
    
    # Defaultt frame range of recording, corresponding to left and right margins user chose
    start_frame: int       # what frame to start at within the recording
    num_frames: int        # how many frames to play from the recording
    
    volume: float = 0.5 # 1.0 = max volume
    pitch_shift: float = 0.0 # in semitones

    # sections of the audio to play in the global loop
    sections: List[AnimalLoopSection] = field(default_factory=list)