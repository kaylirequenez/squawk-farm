"""Full garden composition data structure."""

from dataclasses import dataclass
from typing import Dict

from squawkfarm.models.animal import Animal
from squawkfarm.models.loop import AnimalLoop, GlobalLoopSettings


@dataclass
class Project:
    name: str = "Untitled Project"
    global_settings: GlobalLoopSettings = GlobalLoopSettings()
    animals: Dict[str, Animal] = {}
    loops: Dict[str, AnimalLoop] = {}
