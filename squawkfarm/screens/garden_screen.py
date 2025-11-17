"""Garden (main) screen for squawk-farm."""
import os
import random
import numpy as np
from datetime import datetime

from imslib.screen import Screen
from kivy.core.window import Window
from kivy.graphics import Rectangle, Color, Line
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
from collections import deque

from squawkfarm.services.loop_engine import LoopEngine
from squawkfarm.services.arpeggio_processor import build_arpeggiated_loop_for_animal
from ..models.animal import Animal
from squawkfarm.widgets.animal_widget import AnimalWidget
from squawkfarm.utils import get_ui_asset_path


class GardenScreen(Screen):
    def __init__(self, **kwargs):
        super(GardenScreen, self).__init__(**kwargs)
        self.loop_engine: LoopEngine = self.globals.loop_engine
        self.loop_engine.set_callbacks(self.on_sing, self.on_close_mouth)

        self.num_animals = 0
        self.animals = {}
        self.animal_widgets = {}
        self.active_animal_id = None

        self.farm_path = get_ui_asset_path("4x4Farm.png")
        self.sun_path = get_ui_asset_path("cutes.png")
        self.barn_path = get_ui_asset_path("redbarn2.png")
        self.woodB_path = get_ui_asset_path("woodB2.png")

        self.bg_image = Image(source=self.farm_path).texture
        self.buttons = {}
        Window.clearcolor = (0.5, 0.2, 1, 1)

        self.sun = Image(source=self.sun_path, keep_data=True).texture
        self.sun_const = 9
        self.s_size = Window.height / self.sun_const
        # Sun resize scale factors for 4-beat cycle (large, small, medium, medium-large)
        self.sun_scale_cycle = [1.3, 0.8, 1.0, 1.15]
        self.sun_scale_index = 0  # Track which size we're on in the cycle
        self.sun_scheduled_callback = None  # Track scheduled sun callback
        
        # Schedule sun updates on every beat
        self._schedule_next_sun_update()

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

        with self.canvas:
            self.sun_rect = Rectangle(
                pos=(0, 0),
                size=(self.s_size, self.s_size),
                texture=self.sun,
            )

        Window.bind(size=self.on_resize)
        Clock.schedule_interval(self._update_animals, 1.0 / 30.0)

    def add_or_update_animal(self, animal: Animal):
        try:
            self.animals[animal.animal_id] = animal
            widget = self.animal_widgets.get(animal.animal_id)

            if widget is None:
                widget = AnimalWidget(animal)

                width, height = Window.size
                margin = 10
                max_x = max(margin, width - widget.width - margin)
                max_y = max(margin, height - widget.height - margin)

                x = random.uniform(margin, max_x)
                y = random.uniform(margin, max_y)
                widget.pos = (x, y)

                self.animal_widgets[animal.animal_id] = widget
                self.add_widget(widget)
            else:
                widget.update_from_animal(animal)

            if getattr(animal, "recording_path", None):
                try:
                    build_arpeggiated_loop_for_animal(
                        self.loop_engine,
                        animal.animal_id,
                        animal.recording_path,
                    )
                except Exception as e:
                    print(f"Warning: Failed to build arpeggio for animal {animal.animal_id}: {e}")
                    # Fallback: just add the original recording
                    try:
                        self.loop_engine.add_or_update_animal_loop(animal.animal_id, animal.recording_path)
                        self.loop_engine.add_loop_to_grid(animal.animal_id, [0])
                    except Exception as e2:
                        print(f"Error: Failed to add original recording: {e2}")
                        
        except Exception as e:
            print(f"Error adding/updating animal {getattr(animal, 'animal_id', 'unknown')}: {e}")
            # Don't re-raise to prevent app crash

    def on_sing(self, animal_id: str):
        widget = self.animal_widgets.get(animal_id)
        if widget is not None:
            widget.open_mouth()

    def on_close_mouth(self, animal_id: str):
        widget = self.animal_widgets.get(animal_id)
        if widget is not None:
            widget.close_mouth()

    def on_key_down(self, keycode, modifiers):
        if keycode[1] != "spacebar":
            return

        animal_ids = list(self.animals.keys())
        if not animal_ids:
            return

        animal_id = animal_ids[-1]
        self.active_animal_id = animal_id

        widget = self.animal_widgets.get(animal_id)
        if widget is None:
            return

        widget.speak_once()
        self.loop_engine.toggle_play(loop=True)

    def on_update(self):
        self.loop_engine.on_update()
        
        # Update sun size based on current position in cycle
        scale = self.sun_scale_cycle[self.sun_scale_index]
        new_sun_size = (self.s_size * scale, self.s_size * scale)
        # Center sun vertically while keeping x position
        center_offset_y = (self.s_size * scale - self.s_size) / 2
        self.sun_rect.size = new_sun_size
        self.sun_rect.pos = (0, Window.height - self.s_size - center_offset_y)

    def on_enter(self, *args):
        """Called when this screen becomes active. Ensure sun beat updates are scheduled.

        The audio scheduler may have been paused (and its pending commands cleared)
        while on other screens (for example, the record screen calls
        `loop_engine.pause()` on exit). Reschedule the sun beat callback so the
        sun animation continues after returning to the garden.
        """
        # Only reschedule if we don't already have a callback scheduled
        if self.sun_scheduled_callback is None:
            self._schedule_next_sun_update()

    def on_exit(self):
        # Clear any pending sun callback when leaving the screen
        self.sun_scheduled_callback = None
        self.loop_engine.pause()

    def _update_animals(self, dt):
        bounds = Window.size
        for widget in self.animal_widgets.values():
            widget.update_wander(dt, bounds)

    def _barn_anchor_pos_size(self):
        return self.barn_button.pos, self.barn_button.size

    def _schedule_next_sun_update(self):
        """Schedule the next sun size update on the next beat."""
        # Don't schedule if we already have a pending callback
        if self.sun_scheduled_callback is not None:
            return
            
        try:
            from imslib.clock import kTicksPerQuarter
            # Get the next beat tick
            current_tick = self.loop_engine.scheduler.get_tick()
            next_beat_tick = ((current_tick // kTicksPerQuarter) + 1) * kTicksPerQuarter
            # Schedule callback and store reference
            self.sun_scheduled_callback = self.loop_engine.scheduler.post_at_tick(
                self._on_beat_tick,
                next_beat_tick
            )
        except Exception as e:
            # If scheduling fails, reset the callback reference
            print(f"Warning: Failed to schedule sun update: {e}")
            self.sun_scheduled_callback = None

    def _on_beat_tick(self, tick):
        """Called on every beat; advance sun size in cycle."""
        # Clear the callback reference since this one has fired
        self.sun_scheduled_callback = None
        
        # Update sun scale
        self.sun_scale_index = (self.sun_scale_index + 1) % len(self.sun_scale_cycle)
        
        # Schedule the next beat update
        self._schedule_next_sun_update()

    def build_scene(self):
        pass

    def on_resize(self, *args):
        self.bg_rect.pos = (0, 0)
        self.bg_rect.size = Window.size
        self.s_size = Window.height / self.sun_const
        self.sun_rect.size = (self.s_size, self.s_size)
        self.sun_rect.pos = (0, Window.height - self.s_size)
        self.b_size = Window.width / 6
        new_size = (self.b_size, self.b_size)
        new_pos = (Window.width - self.b_size, 0)
        self.barn_button.size = new_size
        self.barn_rect.size = new_size
        self.barn_button.pos = new_pos
        self.barn_rect.pos = new_pos

    def on_barn_press(self, instance):
        self.switch_to("record")
