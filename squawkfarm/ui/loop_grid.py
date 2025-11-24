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
    def __init__(self, total_slots: int, slots_per_beat: int, slots_per_measure: int, x_margin: Optional[float] = 0, y_margin: Optional[float] = 0, draw_rows: bool = False):
        super(LoopGrid, self).__init__()
        self.total_slots = total_slots
        self.slots_per_beat = slots_per_beat
        self.slots_per_measure = slots_per_measure

        # Center grid with margins
        self.x_margin = x_margin or 0
        self.y_margin = y_margin or 0
        self.width = Window.width - 2 * self.x_margin
        self.height = Window.height - 2 * self.y_margin
        self.x = self.x_margin
        self.y = self.y_margin

        self.bg_texture = Image(source=get_ui_asset_path("woodB2.png")).texture

        # TODO: make this loop nicer
        self.marker_styles = {
            "measure": ((0.10, 0.10, 0.10, 1.0), 3.0, 1.00),  # color, width, height_ratio
            "beat":    ((0.30, 0.30, 0.30, 0.9), 2.0, 1.00), 
            "pulse":   ((0.70, 0.70, 0.70, 0.4), 0.8, 1.00),
        }

        self.draw_rows = draw_rows

        self.on_resize((Window.width, Window.height))
        
    def _draw_background(self) -> None:
        self.add(Color(1, 1, 1, 1))
        self._bg_rect = Rectangle(pos=(self.x, self.y), size=(self.width, self.height), texture=self.bg_texture)
        self.add(self._bg_rect)
    
    def _draw_grid(self) -> None:
        slot_w = self.width / self.total_slots

        # Draw vertical grid lines
        for slot in range(self.total_slots + 1):  # include right edge
            x = self.x + slot * slot_w
            if slot % self.slots_per_measure == 0:
                tier = "measure"
            elif slot % self.slots_per_beat == 0:
                tier = "beat"
            else:
                tier = "pulse"

            color, width_px, h_ratio = self.marker_styles[tier]
            h = self.height * h_ratio
            y0 = self.y + (self.height - h) / 2.0
            y1 = y0 + h

            self.add(Color(*color))
            self.add(Line(points=[x, y0, x, y1], width=width_px))

        # Optionally draw horizontal row lines
        if self.draw_rows:
            pulse_color, pulse_width, _ = self.marker_styles["pulse"]
            num_rows = 8
            for row in range(num_rows + 1):
                y = self.y + row * self.slot_height()
                self.add(Color(*pulse_color))
                self.add(Line(points=[self.x, y, self.x + self.width, y], width=pulse_width))

    def on_resize(self, win_size):
        win_w, win_h = win_size
        self.width = win_w - 2 * self.x_margin
        self.height = win_h - 2 * self.y_margin
        self.x = self.x_margin
        self.y = self.y_margin
        self.clear()
        self._draw_background()
        self._draw_grid()
        
    def slot_width(self) -> float:
        """Width of a single slot in pixels."""
        return self.width / float(self.total_slots)

    def slot_index_to_x(self, slot_index: int) -> float:
        """Left edge X pixel for a given slot."""
        return self.x + slot_index * self.slot_width()

    def x_to_slot_index(self, x: float) -> int:
        """Convert an x pixel coordinate to nearest slot index."""
        rel_x = x - self.x
        return int(round(rel_x / self.slot_width()))

    def slots_to_pixels(self, slots: int) -> float:
        return slots * self.slot_width()
    
    def slot_height(self) -> float:
        """Height of a single slot in pixels."""
        return self.height / 8.0  # assuming 8 horizontal lines
    
    def slot_index_to_y(self, slot_index: int) -> float:
        """Bottom edge Y pixel for a given slot index (0-based from bottom)."""
        return self.y + slot_index * self.slot_height()
    
    def y_to_slot_index(self, y: float) -> int:
        """Convert a y pixel coordinate to nearest slot index (0-based from bottom)."""
        rel_y = y - self.y
        return int(round(rel_y / self.slot_height()))