"""Screen for recording a new animal sound."""
import os
import uuid
from kivy.uix.button import Button
import numpy as np
from datetime import datetime
from imslib.audio import Audio
from imslib.screen import Screen
from kivy.core.window import Window
from kivy.graphics import Color, Line
from kivy.clock import Clock

from imslib.writer import AudioWriter
from squawkfarm.services.loop_engine import LoopEngine
from squawkfarm.ui.loop_grid import LoopGrid
from ..services.animal_gen import render_creature_image
from ..models.animal import Animal
from squawkfarm.utils import get_recording_wav_path, get_animal_data_dir, get_recordings_dir


class RecordScreen(Screen):
    """
    UI for recording with a dedicated Audio input stream, visualizing the waveform,
    and editing the recording to a new animal.
    """
    TARGET_PTS_PER_SEC = 2200  # plotted waveform density
    
    def __init__(self, **kwargs):
        super(RecordScreen, self).__init__(**kwargs)
        self.loop_engine: LoopEngine = Screen.globals.loop_engine
        
        # duration
        # TODO: add button to select option (see get_recording_duration spec)
        self.record_slots = self.loop_engine.get_recording_slots("measure")
        self.record_duration = self.loop_engine.get_time_from_slots(self.record_slots)
        
        # audio capture
        self.writer = AudioWriter(get_recordings_dir(), num_channels=1)  
        def listen_func(data, num_channels):
            # write (only if writer.active)
            self.writer.add_audio(data, num_channels)
            # feed viz if currently recording
            self._ingest_for_waveform(data, num_channels)

        self.mic = Audio(num_channels=1, input_func=listen_func, num_input_channels=1)
        
        # canvas elements
        self.viz_scale = Window.height * 0.22
        
        # button (widget)
        self.record_btn = Button(
            text="Record",
            size_hint=(None, None),
            size=(160, 64),
            pos=(20, 20),
        )
        self.record_btn.bind(on_release=self._on_record_press)
        
        self.add_loop_btn = Button(
            text="Add to Loop",
            size_hint=(None, None),
            size=(160, 64),
            pos=(Window.width - 180, 20),  # Top right
            disabled=True,
            opacity=0  # Hide initially
        )
        self.add_loop_btn.bind(on_release=self._add_animal)
        
        # Sample button
        self.sample_button = Button(
            text='Sample',
            size_hint=(None, None),
            size=(100, 50),
            pos=(Window.width / 2 - 50, Window.height - 60),
            disabled=True,
            opacity=0
        )
        self.sample_button.bind(on_press=self._on_sample_press)
        
        # waveform buffer (ring)
        self.max_samples = int(self.record_duration * self.TARGET_PTS_PER_SEC)
        self.samples = []  # not a deque
        self.decimate = max(1, round(Audio.sample_rate / self.TARGET_PTS_PER_SEC))
        
        # state
        self.is_recording = False
        self.animal_id = ""
        
        # margin markers (draggable)
        self.left_marker_line = None
        self.right_marker_line = None
        self.left_marker_x = 0
        self.right_marker_x = Window.width
        self.dragging_marker = None  # None, 'left', or 'right'
        
    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def on_enter(self, *_):
        self.animal_id = str(uuid.uuid4())
        
        # clear canvas layers you own
        self.canvas.before.clear()
        self.canvas.clear()

        # grid (full width)
        self.grid = LoopGrid(
            loop_engine=self.loop_engine,
            num_slots=self.record_slots
        )
        
        self.canvas.before.clear()
        self.canvas.before.add(self.grid)

        # waveform line
        with self.canvas:
            Color(0, 0.8, 0, 1)
            self.wave_line = Line(points=[0, Window.height/2, Window.width, Window.height/2], width=1.5)
        
        # Re-add to bring to front
        self.add_widget(self.record_btn)  
        self.add_widget(self.add_loop_btn)
        self.add_widget(self.sample_button)  

    def on_update(self):
        # poll mic input and redraw waveform every frame when this screen is active
        if self.is_recording:
            self.mic.on_update()
            self._update_wave()
        
        self.loop_engine.on_update()
        
    def on_resize(self, winsize):
        if hasattr(self, 'grid'):
            self.grid.on_resize(winsize)
        self.viz_scale = Window.height * 0.22
        
        self.add_loop_btn.pos = (Window.width - 180, 20)
        self.sample_button.pos = (Window.width / 2 - 50, Window.height - 60)
        
    def on_leave(self):
        # reset markers
        self.left_marker_line = None
        self.right_marker_line = None
        
        # hide add loop & sample buttons
        self.add_loop_btn.disabled = True
        self.add_loop_btn.opacity = 0
        
        self.sample_button.disabled = True
        self.sample_button.opacity = 0
        
        self.remove_widget(self.record_btn)
        self.remove_widget(self.add_loop_btn)
        self.remove_widget(self.sample_button)

    # ------------------------------------------------------------------
    # UI Handlers
    # ------------------------------------------------------------------
    # TODO: actually add button & if they press this before clicking add animal
    # call loop_engine.del_animal_loop
    def _on_barn_press(self, *_):
        # Button on_press passes the instance; accept it optionally
        self.switch_to('garden')
        
    def _on_record_press(self, *_):
        if not self.is_recording:
            self._start_recording()
            
    def _on_sample_press(self, *_):
        self.loop_engine.play_loop(self.animal_id)

    # ------------------------------------------------------------------
    # recording control
    # ------------------------------------------------------------------
    # TODO: figure out why you can't drag lines when re-recording
    def _start_recording(self):
        self.samples.clear()
        self.samples = []

        self.is_recording = True
        self.samples.clear()
        self.writer.start()
        self.record_btn.text = "Recording..."
        
        if self.left_marker_line:
            self.canvas.after.remove(self.left_marker_line)
            self.left_marker_line = None
        if self.right_marker_line:
            self.canvas.after.remove(self.right_marker_line)
            self.right_marker_line = None
        
        # Hide add loop button & sample button
        self.add_loop_btn.disabled = True
        self.add_loop_btn.opacity = 0
        
        self.sample_button.disabled = True
        self.sample_button.opacity = 0

        # auto-finish after configured duration
        Clock.schedule_once(lambda dt: self._finish_recording(), self.record_duration)
        
        # margin markers (draggable)
        self.left_marker_line = None
        self.right_marker_line = None
        self.left_marker_x = 0
        self.right_marker_x = Window.width
        self.dragging_marker = None  # None, 'left', or 'right'

    def _finish_recording(self):
        """
        Stop writer, reset UI, and go back to the garden screen.
        """
        self.is_recording = False
        self.record_btn.text = "Re-record"
        
        self.writer.stop(self.animal_id)
        
        self._add_loop()
        self._draw_margin_markers()
        self.add_loop_btn.disabled = False
        self.add_loop_btn.opacity = 1
        self.sample_button.disabled = False
        self.sample_button.opacity = 1
        
    # ------------------------------------------------------------------
    # post recording
    # ------------------------------------------------------------------ 
    def _add_loop(self):
        """Add the recorded loop to the LoopEngine."""
        wav = get_recording_wav_path(self.animal_id)
        if self.loop_engine.animal_has_loop(self.animal_id):
            self.loop_engine.change_audio_of_recording(self.animal_id, wav)
        else:   
            self.loop_engine.add_animal_loop(self.animal_id, wav)
           
    def _draw_margin_markers(self):
        """Draw draggable left/right margin markers at the edges."""
        self.left_marker_slot = 0
        self.right_marker_slot = self.record_slots
        
        left_x = self.grid.get_x_from_slot(self.left_marker_slot)
        right_x = self.grid.get_x_from_slot(self.right_marker_slot)
        
        # Don't use 'with', add directly
        self.canvas.after.add(Color(1, 0, 0, 1))  # Red
        self.left_marker_line = Line(
            points=[left_x, 0, left_x, Window.height],
            width=3
        )
        self.canvas.after.add(self.left_marker_line)
        
        self.right_marker_line = Line(
            points=[right_x, 0, right_x, Window.height],
            width=3
        )
        self.canvas.after.add(self.right_marker_line)

    def _update_marker_lines(self):
        """Update marker line positions based on current slot values."""
        if not self.left_marker_line or not self.right_marker_line:
            return
        
        self.left_marker_line.points = [self.left_marker_x, 0, self.left_marker_x, Window.height]
        self.right_marker_line.points = [self.right_marker_x, 0, self.right_marker_x, Window.height]

    def on_touch_down(self, touch):
        """Handle touch down on markers."""
        if not self.left_marker_line or not self.right_marker_line:
            return super(RecordScreen, self).on_touch_down(touch)
        
        marker_tolerance = 30
        if abs(touch.x - self.left_marker_x) < marker_tolerance:
            self.dragging_marker = 'left'
            touch.grab(self)
            return True
        elif abs(touch.x - self.right_marker_x) < marker_tolerance:
            self.dragging_marker = 'right'
            touch.grab(self)
            return True
        
        return super(RecordScreen, self).on_touch_down(touch)

    # TODO: don't left left & right cross
    def on_touch_move(self, touch):
        """Handle marker dragging."""
        if self.dragging_marker and touch.grab_current == self:
            if self.dragging_marker == 'left':
                self.left_marker_x = touch.x
            elif self.dragging_marker == 'right':
                self.right_marker_x = touch.x
            
            self._update_marker_lines()
            return True
        
        return super(RecordScreen, self).on_touch_move(touch)

    def on_touch_up(self, touch):
        """Handle touch release."""
        if self.dragging_marker and touch.grab_current == self:
            touch.ungrab(self)
                   
            if self.dragging_marker == 'left':
                slot = self.grid.get_slot_from_x(self.left_marker_x)
                self.left_marker_x = self.grid.get_x_from_slot(slot)
                self.loop_engine.set_left_margin_of_recording(
                    self.animal_id, slot)
            elif self.dragging_marker == 'right':
                slot = self.grid.get_slot_from_x(self.right_marker_x)
                self.right_marker_x = self.grid.get_x_from_slot(slot)
                self.loop_engine.set_right_margin_of_recording(
                    self.animal_id, slot)
                
            self._update_marker_lines()
            self.dragging_marker = None
            return True
        
        return super(RecordScreen, self).on_touch_up(touch)
    
    def _add_animal(self, *_):
        # write final clipped version to recordings
        wav_path = get_recording_wav_path(self.animal_id)
        
        out_dir = get_animal_data_dir(self.animal_id)
        out_path = os.path.join(out_dir, "open.png")
        
        offset, duration = self.loop_engine.get_loop_time_range(self.animal_id)

        render_creature_image(wav_path, out_dir, size=(640, 480), offset=offset, duration=duration)

        animal = Animal(
            animal_id=self.animal_id,
            image_path=out_path,
            recording_path=wav_path,
            pos=(50, 50),          
            size=(100,100)
        )

        garden = next((s for s in self.manager.screens if s.name == 'garden'), None)
        garden.add_or_update_animal(animal)
        
        self.switch_to('garden')

    # ------------------------------------------------------------------
    # audio → waveform
    # ------------------------------------------------------------------
    def _ingest_for_waveform(self, data, num_channels: int):
        if not self.is_recording or len(self.samples) >= self.max_samples:
            return

        mono = data[0::num_channels] if num_channels > 1 else data
        if mono.size == 0:
            return

        clipped = np.tanh(mono[::self.decimate] * 2.5)

        # don't exceed max length
        remaining = self.max_samples - len(self.samples)
        if remaining <= 0:
            return
        if clipped.size > remaining:
            clipped = clipped[:remaining]

        self.samples.extend(float(s) for s in clipped)

    # TODO: figure out why wave glitches after recording ends
    def _update_wave(self):
        cy = Window.height / 2

        n = len(self.samples)
        if n < 2:
            self.wave_line.points = [0, cy, Window.width, cy]
            return

        # progress based on how many samples we actually have
        progress = n / float(self.max_samples)
        progress = max(0.0, min(1.0, progress))
        max_x = Window.width * progress 
        if max_x <= 0:
            self.wave_line.points = [0, cy, Window.width, cy]
            return

        arr = np.asarray(self.samples, dtype=float)
        peak = float(np.max(np.abs(arr))) if arr.size else 0.0
        yscale = self.viz_scale if peak == 0.0 else min(self.viz_scale, (self.viz_scale * 0.9) / peak)
        ys = cy + arr * yscale

        xs = np.linspace(0.0, max_x, n, dtype=float)
        pts = np.empty(n * 2, dtype=float)
        pts[0::2], pts[1::2] = xs, ys
        self.wave_line.points = pts.tolist()

    

    
   
