# squawkfarm/services/animal.py
from dataclasses import dataclass
from typing import Tuple, Optional

@dataclass
class Animal:
    animal_id: str
    image_path: str           # e.g. data/<animal_id>/creature.png
    recording_path: str       # e.g. data/recordings/recording12.wav
    pos: Tuple[float, float] = (0, 0)           # pixel position on Garden
    size: Optional[Tuple[float, float]] = None  # optional explicit size
