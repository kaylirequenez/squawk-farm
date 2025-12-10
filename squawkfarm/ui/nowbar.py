from kivy.graphics import Color, Line, InstructionGroup

from imslib.gfxutil import KFAnim


class NowBar(InstructionGroup):
    def __init__(
        self,
        start_x,
        end_x,
        bottom_y,
        top_y,
        duration,
        color=Color(0.05, 0.05, 0.3, 1),
        width=3.0,
        loop=False,
    ):
        super(NowBar, self).__init__()

        self.start_x = start_x
        self.end_x = end_x
        self.bottom_y = bottom_y
        self.top_y = top_y
        self.duration = duration
        self.loop = loop

        # Anim state
        self.current_time = 0.0

        self.color = color
        self.line = Line(
            points=[self.start_x, self.bottom_y, self.start_x, self.top_y], width=width
        )

        self.add(self.color)
        self.add(self.line)

    def on_update(self, dt):
        self.current_time = min(self.duration, self.current_time + dt)
        self._update_line()

    def set_duration(self, duration, end_x):
        self.duration = duration
        self.current_time = min(self.current_time, self.duration)
        self.end_x = end_x
        self._update_line()

    def reset(self):
        self.current_time = 0
        self._update_line()

    def on_resize(self, start_x, end_x, bottom_y, top_y):
        self.start_x = start_x
        self.end_x = end_x
        self.bottom_y = bottom_y
        self.top_y = top_y
        self._update_line()

    def _update_line(self):
        x = self.start_x + (self.end_x - self.start_x) * (
            self.current_time / self.duration
        )
        self.line.points = [x, self.bottom_y, x, self.top_y]
