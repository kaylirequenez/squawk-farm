"""Loop-related data structures."""

from dataclasses import dataclass, field
from typing import List, Tuple, Dict

@dataclass
class GlobalLoopSettings:
    bpm: int = 100  # tempo
    measures: int = 2  # measures in the global loop
    time_sig: Tuple[int, int] = (4, 4)  # time signature (numerator, denominator)
    
    key_mode: str = "major" # major or minor
    root: int = 60  # MIDI note number for root (C4=60)
    
@dataclass
class LoopInstance:
    """
    Represents a single loop instance with pitch and muting information.
    
    :param midi: MIDI pitch of this loop instance
    :param start_slot: Starting slot position in the global loop
    :param muted_ranges: List of (start_frame, end_frame) tuples indicating muted regions
    """
    midi: int # MIDI pitch
    start_slot: int
    muted_ranges: List[Tuple[int, int]] = field(default_factory=list) # List of (start_frame, end_frame) ranges

@dataclass
class AnimalLoop:
    animal_id: str
    
    start_frame: int # start frame within the recording
    num_frames: int # number of frames in the trimmed recording
    midi: int # default MIDI pitch
    volume: float # 1.0 = max volume
    role: str # "bass", "harmony", or "melody"

    # maps audio_path -> LoopInstance with start_slot and muted_slots
    instances: Dict[str, LoopInstance] = field(default_factory=dict)