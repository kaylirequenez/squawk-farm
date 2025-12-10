from kivy.uix.image import Image
from kivy.core.window import Window
from kivy.clock import Clock
from squawkfarm.utils import get_ui_asset_path


class SunWidget(Image):
    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("allow_stretch", True)
        kwargs.setdefault("keep_ratio", True)
        super().__init__(**kwargs)

        self.source = get_ui_asset_path("sun.png")

        self._is_large = False
        self._medium_size = (Window.height * 0.15, Window.height * 0.15)
        self._large_size = (Window.height * 0.17, Window.height * 0.17)

        self._center_target = (
            self._medium_size[0] * 1.3 / 2.0,
            Window.height - self._medium_size[1] * 1.3 / 2.0,
        )

        self._update_size_and_pos()

        Window.bind(size=self._on_window_resize)
        Clock.schedule_interval(self._on_beat, 60.0 / 60.0)

    def _on_window_resize(self, *args):
        self._medium_size = (Window.height * 0.1, Window.height * 0.1)
        self._large_size = (Window.height * 0.15, Window.height * 0.15)

        # update the stored target center Y (X stays same)
        self._center_target = (
            self._center_target[0],
            Window.height - self.height / 2.0,
        )

        self._update_size_and_pos()

    def _on_beat(self, dt):
        self._is_large = not self._is_large
        self._update_size_and_pos()

    def _update_size_and_pos(self):
        if self._is_large:
            self.size = self._large_size
        else:
            self.size = self._medium_size

        cx, cy = self._center_target
        self.pos = (cx - self.width / 2.0, cy - self.height / 2.0)
