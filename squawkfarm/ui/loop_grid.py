"""Module defining the LoopGrid class for visualizing loop structure."""
from typing import Optional
from kivy.graphics.instructions import InstructionGroup
from kivy.graphics import Line, Color, Rectangle
from kivy.core.window import Window
from kivy.uix.image import Image

from squawkfarm.services.loop_engine import LoopEngine
from squawkfarm.utils import get_ui_asset_path
# TODO: change inports using _init_

class LoopGrid(InstructionGroup):
    """
    Visual grid showing slots, sub-beats, beats, and measures for loop/recording editing/placement.
    """
    def __init__(self, loop_engine: LoopEngine, num_slots: Optional[int] = None, width: Optional[float] = None, height: Optional[float] = None, x: float = 0, y: float = 0):
        super(LoopGrid, self).__init__()
        self.loop_engine = loop_engine
        self.total_slots = loop_engine.get_total_slots() if num_slots is None else num_slots
        print(self.total_slots)
        print(self.loop_engine.get_total_slots())
        
        self.x = x
        self.y = y
        self.width = width or Window.width
        self.height = height or Window.height

        self.bg_texture = Image(source=get_ui_asset_path("woodB2.png")).texture
        
        # TODO: make this loop nicer
        self.marker_styles = {
            "measure": ((0.10, 0.10, 0.10, 1.0), 3.0, 1.00),  # color, width, height_ratio
            "beat":    ((0.30, 0.30, 0.30, 0.9), 2.0, 0.80), 
            "sub":     ((0.50, 0.50, 0.50, 0.7), 1.2, 0.55),
            "pulse":   ((0.70, 0.70, 0.70, 0.4), 0.8, 0.35),
        }
        
        self.on_resize((self.width, self.height))
        
    def _draw_background(self) -> None:
        self.add(Color(1, 1, 1, 1))
        self._bg_rect = Rectangle(pos=(self.x, self.y), size=(self.width, self.height), texture=self.bg_texture)
        self.add(self._bg_rect)
    
    def _draw_grid(self) -> None:
        slots_per_sub   = self.loop_engine.get_slots_per_sub_beat()
        slots_per_beat  = self.loop_engine.get_slots_per_beat()
        slots_per_meas  = self.loop_engine.get_slots_per_measure()
        slot_w = self.width / self.total_slots

        for slot in range(self.total_slots + 1):  # include right edge
            x = self.x + slot * slot_w
            if slot % slots_per_meas == 0:
                tier = "measure"
            elif slot % slots_per_beat == 0:
                tier = "beat"
            elif slot % slots_per_sub == 0:
                tier = "sub"
            else:
                tier = "pulse"

            color, width_px, h_ratio = self.marker_styles[tier]
            h = self.height * h_ratio
            y0 = self.y + (self.height - h) / 2.0
            y1 = y0 + h

            self.add(Color(*color))
            self.add(Line(points=[x, y0, x, y1], width=width_px))

    def on_resize(self, win_size):
        self.width, self.height = win_size
        self.clear()
        self._draw_background()
        self._draw_grid()

    def get_slot_from_x(self, x_coord: float) -> int:
        if x_coord <= self.x: return 0
        if x_coord >= self.x + self.width: return self.total_slots - 1
        slot_w = self.width / float(self.total_slots)
        slot = round((x_coord - self.x) / slot_w)
        return max(0, min(slot, self.total_slots))

    def get_x_from_slot(self, slot: int) -> float:
        slot_w = self.width / float(self.total_slots)
        return self.x + slot * slot_w