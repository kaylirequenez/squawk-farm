import random

from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.graphics import Rectangle

from squawkfarm.utils import get_ui_asset_path


class EggWidget(Image):
    def __init__(self, animal_id, on_hatch_callback=None, **kwargs):
        self.animal_id = animal_id
        self.on_hatch_callback = on_hatch_callback
        self._last_parent = None
        self.shadow_image = None

        egg_num = random.choice([1, 2, 3])
        self.egg_path = get_ui_asset_path(f"egg{egg_num}.png")
        self.shadow_path = get_ui_asset_path(f"egg{egg_num}_shadow.png")

        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("source", self.egg_path)
        super().__init__(**kwargs)

        self.size = (240, 240)

        self.click_button = Button(
            size_hint=(None, None),
            size=self.size,
            background_color=(0, 0, 0, 0),
            background_normal="",
        )
        self.click_button.bind(on_press=self._on_click)

    def on_parent(self, instance, parent):
        if parent is not None:
            parent.add_widget(self.click_button)
            if self.shadow_image is None:
                self.shadow_image = Image(
                    source=self.shadow_path, size_hint=(None, None), size=self.size
                )
                parent.add_widget(self.shadow_image, index=0)
                self._update_shadow_pos()
        else:
            if self._last_parent is not None:
                if self.click_button in self._last_parent.children:
                    try:
                        self._last_parent.remove_widget(self.click_button)
                    except Exception:
                        pass
                if self.shadow_image is not None:
                    try:
                        self._last_parent.remove_widget(self.shadow_image)
                    except Exception:
                        pass
                    self.shadow_image = None
        self._last_parent = parent

    def _update_shadow_pos(self):
        if self.shadow_image is not None:
            self.shadow_image.pos = self.pos
            self.shadow_image.size = self.size

    def set_pos(self, pos):
        self.pos = pos
        self.click_button.pos = pos
        self._update_shadow_pos()

    def _on_click(self, instance):
        if self.on_hatch_callback:
            self.on_hatch_callback(self.animal_id)

    def remove_from_parent(self):
        if self.parent:
            parent = self.parent
            parent.remove_widget(self)
            if self.click_button in parent.children:
                parent.remove_widget(self.click_button)
            if self.shadow_image is not None and self.shadow_image in parent.children:
                parent.remove_widget(self.shadow_image)
                self.shadow_image = None
