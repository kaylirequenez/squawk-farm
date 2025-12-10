"""Loop-related data structures."""

from dataclasses import dataclass, field

from squawkfarm.models.progression import ChordProgression


@dataclass
class GlobalLoopSettings:
    bpm: int = 100
    measures: int = 2
    time_sig: tuple = (4, 4)

    key_mode: str = "major"
    root: int = 60

    chord_progression: ChordProgression = None

    key_change_offsets: list = field(default_factory=lambda: [0, -3, -5, -2])
    key_change_interval: int = 4


@dataclass
class LoopInstance:
    """
    Represents a single loop instance with pitch and muting information.
    """

    midi: int
    start_slot: int
    muted_ranges: list = field(default_factory=list)


@dataclass
class AnimalLoop:
    """
    Represents an animal's loop with its properties and instances.
    """

    animal_id: str

    start_frame: int  # start frame within the recording
    num_frames: int  # number of frames in the trimmed recording
    midi: int
    volume: float  # 1.0 = max volume
    role: str  # "bass", "harmony", "melody"

    # list of instances for this animal on the grid
    instances: dict[int, int] = field(default_factory=dict)  # start_slot -> midi
