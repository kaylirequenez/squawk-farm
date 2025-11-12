"""Garden (main) screen for squawk-farm."""
import os
import numpy as np
from datetime import datetime
from imslib.screen import Screen
from kivy.core.window import Window
from kivy.graphics import Rectangle, Color, Line
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.graphics.opengl import glEnable, glBlendFunc, GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA
from kivy.clock import Clock
from collections import deque

from squawkfarm.services.loop_engine import LoopEngine
from ..models.animal import Animal
from squawkfarm.utils import get_ui_asset_path


class GardenScreen(Screen):
    """Main farm/garden view where animals are shown and global loop settings can be adjusted."""
    def __init__(self, **kwargs):
        super(GardenScreen, self).__init__(**kwargs)
        self.loop_engine: LoopEngine = self.globals.loop_engine
        self.num_animals = 0  # starting number of animals

        self.animals = {}
        self.animal_widgets = {}
        
        self.farm_path = get_ui_asset_path("4x4Farm.png")
        self.sun_path = get_ui_asset_path("cutes.png")
        self.barn_path = get_ui_asset_path("redbarn2.png")
        self.woodB_path = get_ui_asset_path("woodB2.png") 

        # path from this file (squawkfarm/screens) up to project root: ../../assets/...
        self.bg_image = Image(source = self.farm_path).texture
        self.buttons = {}
        Window.clearcolor = (0.5,0.2,1,1)
        #self.sun = Image(source = self.sun_path).texture  # sun png for BPM
        self.sun = Image(source = self.sun_path, keep_data=True).texture
        self.sun_const = 9
        self.s_size = Window.height/self.sun_const
        self.barn = Image(source = self.barn_path).texture #barn png for button
        self.b_size = Window.width/8
        self.bpm = 90

        # create the background rectangle immediately so the canvas has it
        with self.canvas.before:
            self.bg_rect = Rectangle(pos=(0, 0), size=Window.size, texture=self.bg_image)
        
        self.barn_button = Button(
            size_hint=(None, None),
            size=(self.b_size, self.b_size),
            pos=(Window.width - self.b_size, 0),
            background_normal='',  # Remove default button background
            background_color=(1, 1, 1, 0)  # White color to show texture properly
        )
        # Add the barn texture to the button's canvas
        with self.barn_button.canvas.before:
            self.barn_rect = Rectangle(
                pos=self.barn_button.pos,
                size=self.barn_button.size,
                texture=self.barn
            )
        # Bind the button press event
        self.barn_button.bind(on_press=self.on_barn_press)
        self.add_widget(self.barn_button)

        with self.canvas:
            self.sun_rect = Rectangle(pos=(0, 0), size=(self.s_size, self.s_size), texture=self.sun)
        # update background size when Window changes
        Window.bind(size=self.on_resize)


    def _barn_anchor_pos_size(self):
        return self.barn_button.pos, self.barn_button.size
    
    def add_or_update_animal(self, animal: Animal):

        self.animals[animal.animal_id] = animal
        w = self.animal_widgets.get(animal.animal_id)

        pos = animal.pos
        size = animal.size

        if w is None:

            print(animal.image_path)
            w = Image(source=animal.image_path, size_hint=(None, None))
            print(animal.image_path)

            print(w)
            w.size = size
            w.pos = pos

            #temporary override:
            w.pos = (0, 0) 
            
            print("POSITION")
            print(w.pos)
            w.size = (1000, 1000)
            self.animal_widgets[animal.animal_id] = w
            self.add_widget(w)
        else:

            if w.source != animal.image_path:
                w.source = animal.image_path
                w.reload()

            w.size = size
            w.pos = pos

    def build_scene(self):
        # kept for compatibility if other code calls it; background is built in __init__
        pass

    def on_resize(self, *args):
        # Window.bind will pass (window, size) so accept *args and read Window.size
        self.bg_rect.pos = (0,0)
        self.bg_rect.size = Window.size
        self.s_size = Window.height/self.sun_const
        self.sun_rect.size = (self.s_size,self.s_size)
        self.sun_rect.pos = (0, Window.height - self.s_size)
        self.b_size = Window.width/6
        new_size = (self.b_size, self.b_size) 
        new_pos = (Window.width - self.b_size,0) 
        self.barn_button.size = new_size
        self.barn_rect.size = new_size
        self.barn_button.pos = new_pos 
        self.barn_rect.pos = new_pos
        
    def sing(self):
        print("animal is opening mouth")
        
    def close_mouth(self):
        print("animal is closing mouth")
    
    def on_barn_press(self, instance):
        self.switch_to('record')
    
    def on_key_down(self, keycode, modifiers):
        if keycode[1] == "spacebar":
            animal_ids = list(self.animals.keys())
            if len(animal_ids) > 0:
                animal_id = animal_ids[-1]
                print(animal_id)
                self.loop_engine.play_loop(animal_id, self.sing, self.close_mouth)
                
    def on_update(self):
        self.loop_engine.on_update()
