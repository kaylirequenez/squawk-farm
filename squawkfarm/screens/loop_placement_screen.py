
from imslib.screen import Screen

class LoopPlacementScreen(Screen):
    def __init__(self, **kwargs):
        super(LoopPlacementScreen, self).__init__(**kwargs)
        
    def on_enter(self):
        pass

    def on_update(self, animal_id: str):
        pass
    
    def on_resize(self, win_size):
        pass