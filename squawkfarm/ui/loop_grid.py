from kivy.graphics.instructions import InstructionGroup
from kivy.graphics import Line, Color, Rectangle
from kivy.core.window import Window
from kivy.uix.image import Image

from squawkfarm.utils import get_ui_asset_path


class LoopGrid(InstructionGroup):
    def __init__(self, total_slots, slots_per_beat, slots_per_measure, x_margin=0, y_margin=0, draw_rows=False, skip_outer_lines=False):
        super(LoopGrid, self).__init__()
        self.total_slots = total_slots
        self.slots_per_beat = slots_per_beat
        self.slots_per_measure = slots_per_measure

        self.x_margin = x_margin or 0
        self.y_margin = y_margin or 0
        self.width = Window.width - 2 * self.x_margin
        self.height = Window.height - 2 * self.y_margin
        self.x = self.x_margin
        self.y = self.y_margin

        self.bg_texture = Image(source=get_ui_asset_path("board.png")).texture

        self.marker_styles = {
            "measure": ((0.10, 0.10, 0.10, 1.0), 3.0, 1.00),
            "beat":    ((0.30, 0.30, 0.30, 0.9), 2.0, 1.00),
            "pulse":   ((0.70, 0.70, 0.70, 0.4), 0.8, 1.00),
        }

        self.draw_rows = draw_rows
        self.skip_outer_lines = skip_outer_lines

        self.on_resize((Window.width, Window.height))
        
    def _draw_background(self):
        self.add(Color(1, 1, 1, 1))
        self._bg_rect = Rectangle(pos=(self.x, self.y), size=(self.width, self.height), texture=self.bg_texture)
        self.add(self._bg_rect)
    
    def _draw_grid(self):
        slot_w = self.width / self.total_slots

        for slot in range(self.total_slots + 1):
            if self.skip_outer_lines and (slot == 0 or slot == self.total_slots):
                continue

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
        
    def slot_width(self):
        return self.width / float(self.total_slots)

    def slot_index_to_x(self, slot_index):
        return self.x + slot_index * self.slot_width()

    def x_to_slot_index(self, x):
        rel_x = x - self.x
        slot_index = rel_x / self.slot_width()
        half_beat_slots = self.slots_per_beat // 2
        snapped_index = round(slot_index / half_beat_slots) * half_beat_slots
        return int(snapped_index)

    def slots_to_pixels(self, slots):
        return slots * self.slot_width()

    def slot_height(self):
        return self.height / 8.0

    def slot_index_to_y(self, slot_index):
        return self.y + slot_index * self.slot_height()

    def y_to_slot_index(self, y):
        rel_y = y - self.y
        return int(round(rel_y / self.slot_height()))