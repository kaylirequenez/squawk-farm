"""Full garden composition data structure."""

from dataclasses import dataclass, field

from squawkfarm.models.animal import Animal
from squawkfarm.models.loop import AnimalLoop, GlobalLoopSettings


@dataclass
class Project:
    name: str = "Untitled Project"
    global_settings: GlobalLoopSettings = None
    animals: dict = field(default_factory=dict)
    loops: dict = field(default_factory=dict)
