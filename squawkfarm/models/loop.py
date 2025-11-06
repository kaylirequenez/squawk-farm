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

    audio_path: str = ""  # the wav to actually play

    # when in the global loop do we start? 0 = first beat
    start_beat: int = 0

    # how many beats this loop occupies (must divide global.total_beats)
    length_beats: int = 4

    # per-beat mute within this loop (optional)
    # e.g. for a 4-beat loop: [1, 0, 1, 1] means don't play beat 2
    step_mutes: List[int] = field(default_factory=list)

    # playback controls
    volume: float = 1.0  # 1.0 = normal
    pitch_shift: float = 0.0  # in semitones
