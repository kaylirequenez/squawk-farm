"""Full garden composition data structure."""

from dataclasses import dataclass
from typing import List

from squawkfarm.models.animal import Animal
from squawkfarm.models.loop import AnimalLoop, GlobalLoopSettings


@dataclass
class Project:
    name: str
    global_settings: GlobalLoopSettings
    animals: List[Animal]
    loops: List[AnimalLoop]
