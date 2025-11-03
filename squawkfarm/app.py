"""Application bootstrap for squawk-farm.

Defines a minimal Kivy App subclass and attaches a ScreenManager.
"""

from imslib.screen import ScreenManager
from squawkfarm.models.loop import GlobalLoopSettings
from squawkfarm.screens.garden_screen import GardenScreen
from squawkfarm.screens.loop_editor_screen import LoopEditorScreen
from squawkfarm.screens.record_screen import RecordScreen


# Insert information to be globally accessible to screens here.
class Globals:
    def __init__(self):
        self.global_loop = GlobalLoopSettings()
        self.animals = []
        self.animal_loops = []


def build_app():
    sm = ScreenManager(globals=Globals())
    sm.add_screen(GardenScreen(name="garden"))
    sm.add_screen(RecordScreen(name="record"))
    sm.add_screen(LoopEditorScreen(name="loop"))
    return sm
