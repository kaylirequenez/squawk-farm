import random
from imslib.screen import Screen
from kivy.core.window import Window
from kivy.graphics import Rectangle
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.graphics.opengl import (
    glEnable,
    glBlendFunc,
    GL_BLEND,
    GL_SRC_ALPHA,
    GL_ONE_MINUS_SRC_ALPHA,
)
from kivy.clock import Clock

from squawkfarm.services.loop_engine import LoopEngine
from ..models.animal import Animal
from squawkfarm.widgets.animal_widget import AnimalWidget
from squawkfarm.widgets.egg_widget import EggWidget
from squawkfarm.widgets.sun_widget import SunWidget
from squawkfarm.utils import get_ui_asset_path

TERRAIN_BOUNDARY_RATIO = 0.363


class GardenScreen(Screen):
    def __init__(self, **kwargs):
        super(GardenScreen, self).__init__(**kwargs)
        self.loop_engine: LoopEngine = self.globals.loop_engine
        self.loop_engine.set_callbacks(self.on_sing, self.on_close_mouth)

        self.num_animals = 0
        self.animals = {}
        self.animal_widgets = {}
        self.egg_widgets = {}
        self.active_animal_id = None

        self.farm_path = get_ui_asset_path("lawn.png")
        self.barn_path = get_ui_asset_path("barn.png")
        self.woodB_path = get_ui_asset_path("board.png")

        self.bg_image = Image(source=self.farm_path).texture
        self.buttons = {}
        Window.clearcolor = (0.5, 0.2, 1, 1)

        self.barn = Image(source=self.barn_path).texture
        self.b_size = Window.width / 8
        self.bpm = 90

        with self.canvas.before:
            self.bg_rect = Rectangle(pos=(0, 0), size=Window.size, texture=self.bg_image)

        self.barn_button = Button(
            size_hint=(None, None),
            size=(self.b_size, self.b_size),
            pos=(Window.width - self.b_size, 0),
            background_normal="",
            background_color=(1, 1, 1, 0),
        )
        with self.barn_button.canvas.before:
            self.barn_rect = Rectangle(
                pos=self.barn_button.pos,
                size=self.barn_button.size,
                texture=self.barn,
            )
        self.barn_button.bind(on_press=self.on_barn_press)
        self.add_widget(self.barn_button)

        self.chords_path = get_ui_asset_path("chords.png")
        self.chords_texture = Image(source=self.chords_path).texture
        self.chord_btn_size = Window.width / 10
        self.chord_btn = Button(
            size_hint=(None, None),
            size=(self.chord_btn_size, self.chord_btn_size),
            pos=(Window.width - self.chord_btn_size - 10, Window.height - self.chord_btn_size - 10),
            background_normal="",
            background_color=(1, 1, 1, 0),
        )
        with self.chord_btn.canvas.before:
            self.chord_rect = Rectangle(
                pos=self.chord_btn.pos,
                size=self.chord_btn.size,
                texture=self.chords_texture,
            )
        self.chord_btn.bind(on_press=self._on_chord_press)
        self.add_widget(self.chord_btn)

        self.sun_widget = SunWidget()
        self.add_widget(self.sun_widget)

        self._prev_window_size = Window.size

        Window.bind(size=self.on_resize)
        Clock.schedule_interval(self._update_animals, 1.0 / 30.0)

    def add_or_update_animal(self, animal: Animal):
        self.animals[animal.animal_id] = animal
        widget = self.animal_widgets.get(animal.animal_id)

        if widget is None:
            if animal.animal_id in self.egg_widgets:
                return

            width, height = Window.size
            spawn_x = width / 2
            spawn_y = height * 0.125

            animal.pos = (spawn_x, spawn_y)

            egg = EggWidget(animal.animal_id, on_hatch_callback=self._on_egg_hatch)
            egg.set_pos((spawn_x, spawn_y))
            self.egg_widgets[animal.animal_id] = egg
            self.add_widget(egg)

            # Mute the animal while it's still an egg
            if animal.animal_id in self.loop_engine.loops:
                loop = self.loop_engine.loops[animal.animal_id]
                egg.pre_hatch_volume = loop.volume  # Store original volume
                loop.set_volume(0.0)
        else:
            widget.update_from_animal(animal)

    def _on_egg_hatch(self, animal_id):
        egg = self.egg_widgets.pop(animal_id, None)
        if egg is None:
            return

        egg_x, egg_y = egg.pos
        egg_w, egg_h = egg.size
        egg.remove_from_parent()

        animal = self.animals.get(animal_id)
        if animal is None:
            return

        widget = AnimalWidget(animal, on_click_callback=self._on_animal_click)

        egg_center_x = egg_x + egg_w / 2
        egg_center_y = egg_y + egg_h / 2

        ground_x = egg_center_x - widget._base_width / 2
        ground_y = egg_center_y - widget._base_height / 2

        animal.pos = (ground_x, ground_y)
        widget.move_to((ground_x, ground_y))
        self.animal_widgets[animal_id] = widget
        self.add_widget(widget)

        if animal_id in self.loop_engine.loops:
            # Restore the volume that was set in the record screen
            if hasattr(egg, 'pre_hatch_volume'):
                self.loop_engine.loops[animal_id].set_volume(egg.pre_hatch_volume)
            self.loop_engine.auto_generate_for_animal(animal_id)
            self.loop_engine.pause()
            self.loop_engine.play(start_time=0.0, loop=True)

    def on_sing(self, animal_id):
        widget = self.animal_widgets.get(animal_id)
        if widget is not None:
            widget.open_mouth()

    def on_close_mouth(self, animal_id):
        widget = self.animal_widgets.get(animal_id)
        if widget is not None:
            widget.close_mouth()

    def on_key_down(self, keycode, modifiers):
        if keycode[1] == "spacebar":
            self.loop_engine.toggle_play(loop=True)

    def on_enter(self):
        if self.loop_engine.loops:
            self.loop_engine.play(start_time=0.0, loop=True)

    def on_update(self):
        self.loop_engine.on_update()

    def on_exit(self):
        self.loop_engine.pause()

    def _find_non_colliding_spawn(self, min_x, max_x, max_y, size, min_y, max_attempts=50):
        for _ in range(max_attempts):
            x = random.uniform(min_x, max_x)
            y = random.uniform(min_y, max_y)
            collides = False
            for egg in self.egg_widgets.values():
                ex, ey = egg.pos
                ew, eh = egg.size
                min_dist_x = (size + ew) / 2 * 1.2
                min_dist_y = (size + eh) / 2 * 1.2
                if abs(x - ex) < min_dist_x and abs(y - ey) < min_dist_y:
                    collides = True
                    break
            if not collides:
                for aw in self.animal_widgets.values():
                    ax, ay = aw.pos
                    min_dist_x = (size + aw.width) / 2 * 1.2
                    min_dist_y = (size + aw.height) / 2 * 1.2
                    if abs(x - ax) < min_dist_x and abs(y - ay) < min_dist_y:
                        collides = True
                        break
            if not collides:
                return x, y
        return random.uniform(min_x, max_x), random.uniform(min_y, max_y)

    def _get_other_animal_positions(self, exclude_id):
        positions = []
        for aid, aw in self.animal_widgets.items():
            if aid != exclude_id:
                positions.append((aw.pos[0], aw.pos[1], aw.width, aw.height))
        for egg in self.egg_widgets.values():
            positions.append((egg.pos[0], egg.pos[1], egg.size[0], egg.size[1]))
        return positions

    def _update_animals(self, dt):
        bounds = Window.size
        for aid, widget in self.animal_widgets.items():
            others = self._get_other_animal_positions(aid)
            widget.update_wander(dt, bounds, others)

    def _barn_anchor_pos_size(self):
        return self.barn_button.pos, self.barn_button.size

    def build_scene(self):
        pass

    def on_resize(self, *args):
        prev_w, prev_h = self._prev_window_size
        new_w, new_h = Window.size

        scale_x = new_w / prev_w if prev_w > 0 else 1.0
        scale_y = new_h / prev_h if prev_h > 0 else 1.0

        self.bg_rect.pos = (0, 0)
        self.bg_rect.size = Window.size
        self.b_size = Window.width / 8
        new_size = (self.b_size, self.b_size)
        new_pos = (Window.width - self.b_size, 0)
        self.barn_button.size = new_size
        self.barn_rect.size = new_size
        self.barn_button.pos = new_pos
        self.barn_rect.pos = new_pos
        self.chord_btn_size = Window.width / 10
        self.chord_btn.size = (self.chord_btn_size, self.chord_btn_size)
        self.chord_btn.pos = (Window.width - self.chord_btn_size - 10, Window.height - self.chord_btn_size - 10)
        self.chord_rect.size = self.chord_btn.size
        self.chord_rect.pos = self.chord_btn.pos

        for animal_id, widget in self.animal_widgets.items():
            old_x, old_y = widget.pos
            new_x = old_x * scale_x
            new_y = old_y * scale_y

            widget.move_to((new_x, new_y))
            animal = self.animals.get(animal_id)
            if animal:
                animal.pos = (new_x, new_y)

        for egg in self.egg_widgets.values():
            old_x, old_y = egg.pos
            new_x = old_x * scale_x
            new_y = old_y * scale_y

            egg.set_pos((new_x, new_y))

        self._prev_window_size = Window.size

    def on_barn_press(self, instance):
        self.switch_to("record")

    def _on_chord_press(self, *_):
        self.switch_to("chord")

    def _on_animal_click(self, animal_id):
        animal = self.animals.get(animal_id)
        if animal:
            self.switch_to("loop_placement", animal_id)
