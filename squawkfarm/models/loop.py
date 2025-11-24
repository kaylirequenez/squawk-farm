"""Loop-related data structures."""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from squawkfarm.models.progression import ChordProgression

@dataclass
class GlobalLoopSettings:
    bpm: int = 100  # tempo
    measures: int = 2  # measures in the global loop
    time_sig: Tuple[int, int] = (4, 4)  # time signature (numerator, denominator)
    
    key_mode: str = "major" # major or minor
    root: int = 60  # MIDI note number for root (C4=60)
    
    chord_progression: Optional[ChordProgression] = None
    
@dataclass
class LoopInstance:
    """
    Represents a single loop instance with pitch and muting information.
    """
    midi: int 
    start_slot: int
    muted_ranges: List[Tuple[int, int]] = field(default_factory=list) 

@dataclass
class AnimalLoop:
    """
    Represents an animal's loop with its properties and instances.
    """
    animal_id: str
    
    start_frame: int # start frame within the recording
    num_frames: int # number of frames in the trimmed recording
    midi: int 
    volume: float # 1.0 = max volume
    role: str # "bass", "harmony", "melody", or "percussion"

    # list of instances for this animal on the grid
    instances: List[LoopInstance] = field(default_factory=list)