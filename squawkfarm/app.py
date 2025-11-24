"""Application bootstrap for squawk-farm.

Defines a minimal Kivy App subclass and attaches a ScreenManager.
"""

from imslib.screen import ScreenManager
from squawkfarm.models.loop import GlobalLoopSettings
from squawkfarm.screens.garden_screen import GardenScreen
from squawkfarm.screens.loop_placement_screen import LoopPlacementScreen
from squawkfarm.screens.record_screen import RecordScreen
from squawkfarm.services.loop_engine import LoopEngine


# Insert information to be globally accessible to screens here.
class Globals:
    def __init__(self):
        self.loop_engine = LoopEngine(GlobalLoopSettings())


def build_app():
    sm = ScreenManager(globals=Globals())
    sm.add_screen(GardenScreen(name="garden"))
    sm.add_screen(RecordScreen(name="record"))
    sm.add_screen(LoopPlacementScreen(name="loop_placement"))
    return sm