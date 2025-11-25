# squawkfarm/models/animal.py  (or wherever it currently lives)

from dataclasses import dataclass

@dataclass
class Animal:
    animal_id: str
    image_path: str           # e.g. data/<animal_id>/creature.png
    recording_path: str       # e.g. data/recordings/recording12.wav
    pos: tuple = (0, 0)       # pixel position on Garden
    size: tuple = None        # optional explicit size
