import os
import uuid
import numpy as np
import soundfile as sf

from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.core.window import Window
from kivy.graphics import Color, Line
from kivy.clock import Clock

from imslib.audio import Audio
from imslib.screen import Screen
from imslib.writer import AudioWriter

from squawkfarm.services.loop_engine import LoopEngine
from squawkfarm.ui.loop_grid import LoopGrid
from squawkfarm.services.animal_gen import render_creature_image
from squawkfarm.models.animal import Animal
from squawkfarm.utils import (
    get_recording_wav_path,
    get_animal_data_dir,
    get_recordings_dir,
)


class RecordScreen(Screen):
    TARGET_PTS_PER_SEC = 2200

    def __init__(self, **kwargs):
        super(RecordScreen, self).__init__(**kwargs)
        self.loop_engine: LoopEngine = Screen.globals.loop_engine

        self.window_slots = self.loop_engine.get_recording_slots("beat")
        self.record_slots = self.window_slots * 8
        self.record_duration = self.loop_engine.get_time_from_slots(self.record_slots)

        self.writer = AudioWriter(get_recordings_dir(), num_channels=1)

        def listen_func(data, num_channels):
            self.writer.add_audio(data, num_channels)
            self._ingest_for_waveform(data, num_channels)

        self.mic = Audio(num_channels=1, input_func=listen_func, num_input_channels=1)

        self.viz_scale = Window.height * 0.35

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
            pos=(Window.width - 180, 20),
            disabled=True,
            opacity=0,
        )
        self.add_loop_btn.bind(on_release=self._add_animal)

        self.sample_button = Button(
            text="Sample",
            size_hint=(None, None),
            size=(100, 50),
            pos=(Window.width / 2 - 50, Window.height - 60),
            disabled=True,
            opacity=0,
        )
        self.sample_button.bind(on_press=self._on_sample_press)
        
        # Sample size options with corresponding pulse/beat multipliers
        self.sample_sizes = {
            "Small": 1,    # 1 pulse/beat length
            "Medium": 2,   # 2 pulse lengths  
            "Large": 4     # 4 pulse lengths
        }
        self.current_sample_size = "Medium"  # Default selection
        
        # Sample size dropdown (initially hidden)
        self.sample_size_spinner = Spinner(
            text=self.current_sample_size,
            values=list(self.sample_sizes.keys()),
            size_hint=(None, None),
            size=(120, 50),
            pos=(20, Window.height - 70),
            disabled=True,
            opacity=0,
        )
        self.sample_size_spinner.bind(text=self._on_sample_size_change)

        self.max_samples = int(self.record_duration * self.TARGET_PTS_PER_SEC)
        self.samples = []
        self.decimate = max(1, round(Audio.sample_rate / self.TARGET_PTS_PER_SEC))

        self.is_recording = False
        self.animal_id = ""

        self.left_marker_line = None
        self.right_marker_line = None
        self.left_marker_x = 0
        self.right_marker_x = Window.width
        self.left_marker_slot = 0
        self.right_marker_slot = self.record_slots
        self.dragging_marker = None

    def _set_editing_buttons_visible(self, visible: bool):
        self.add_loop_btn.disabled = not visible
        self.add_loop_btn.opacity = 1 if visible else 0
        self.sample_button.disabled = not visible
        self.sample_button.opacity = 1 if visible else 0
        self.sample_size_spinner.disabled = not visible
        self.sample_size_spinner.opacity = 1 if visible else 0

    def _add_button_widgets(self):
        self.add_widget(self.record_btn)
        self.add_widget(self.add_loop_btn)
        self.add_widget(self.sample_button)
        self.add_widget(self.sample_size_spinner)

    def _remove_button_widgets(self):
        self.remove_widget(self.record_btn)
        self.remove_widget(self.add_loop_btn)
        self.remove_widget(self.sample_button)
        self.remove_widget(self.sample_size_spinner)

    def _clear_marker_lines(self):
        if self.left_marker_line is not None:
            try:
                self.canvas.after.remove(self.left_marker_line)
            except ValueError:
                pass
            self.left_marker_line = None

        if self.right_marker_line is not None:
            try:
                self.canvas.after.remove(self.right_marker_line)
            except ValueError:
                pass
            self.right_marker_line = None

        self.left_marker_x = 0
        self.right_marker_x = Window.width
        self.left_marker_slot = 0
        self.right_marker_slot = self.record_slots
        self.dragging_marker = None

    def on_enter(self, *_):
        self.animal_id = str(uuid.uuid4())
        self._clear_marker_lines()

        self.canvas.before.clear()
        self.canvas.clear()

        self.grid = LoopGrid(
            loop_engine=self.loop_engine,
            num_slots=self.record_slots,
        )
        self.canvas.before.add(self.grid)

        with self.canvas:
            Color(0, 0.8, 0, 1)
            self.wave_line = Line(
                points=[0, Window.height / 2, Window.width, Window.height / 2],
                width=1.5,
            )

        self._add_button_widgets()

    def on_update(self):
        if self.is_recording:
            self.mic.on_update()
            self._update_wave()

        self.loop_engine.on_update()

    def on_resize(self, winsize):
        if hasattr(self, "grid"):
            self.grid.on_resize(winsize)

        self.viz_scale = Window.height * 0.35
        self.add_loop_btn.pos = (Window.width - 180, 20)
        self.sample_button.pos = (Window.width / 2 - 50, Window.height - 60)
        self.sample_size_spinner.pos = (20, Window.height - 70)

    def on_exit(self):
        self._clear_marker_lines()
        self._set_editing_buttons_visible(False)
        self.record_btn.text = "Record"
        self._remove_button_widgets()
        self.loop_engine.pause()

    def _on_barn_press(self, *_):
        self.switch_to("garden")

    def _on_record_press(self, *_):
        if not self.is_recording:
            self._start_recording()

    def _on_sample_press(self, *_):
        self.loop_engine.play_loop(self.animal_id)
        
    def _on_sample_size_change(self, spinner, text):
        """Handle sample size dropdown selection change."""
        self.current_sample_size = text
        # Update the markers based on the new sample size
        self._update_markers_for_sample_size()

    def _start_recording(self):
        self.samples.clear()

        self.is_recording = True
        self.writer.start()
        self.record_btn.text = "Recording..."

        self._clear_marker_lines()
        self._set_editing_buttons_visible(False)

        Clock.schedule_once(lambda dt: self._finish_recording(), self.record_duration)

    def _finish_recording(self):
        self.is_recording = False
        self.record_btn.text = "Re-record"

        self.writer.stop(self.animal_id)

        self._add_loop()
        self._draw_margin_markers()
        self._set_editing_buttons_visible(True)

    def _add_loop(self):
        wav_path = get_recording_wav_path(self.animal_id)
        self.loop_engine.add_or_update_animal_loop(self.animal_id, wav_path)

    def _draw_margin_markers(self):
        self.left_marker_slot = 0
        # Set right marker based on current sample size
        sample_multiplier = self.sample_sizes[self.current_sample_size]
        sample_slots = self.window_slots * sample_multiplier
        self.right_marker_slot = min(sample_slots, self.record_slots)

        self.left_marker_x = self.grid.get_x_from_slot(self.left_marker_slot)
        self.right_marker_x = self.grid.get_x_from_slot(self.right_marker_slot)

        self.canvas.after.add(Color(1, 0, 0, 1))
        self.left_marker_line = Line(
            points=[self.left_marker_x, 0, self.left_marker_x, Window.height],
            width=3,
        )
        self.canvas.after.add(self.left_marker_line)

        self.right_marker_line = Line(
            points=[self.right_marker_x, 0, self.right_marker_x, Window.height],
            width=3,
        )
        self.canvas.after.add(self.right_marker_line)

        self.loop_engine.set_left_margin_of_recording(self.animal_id, self.left_marker_slot)
        self.loop_engine.set_right_margin_of_recording(self.animal_id, self.right_marker_slot)
        
    def _update_markers_for_sample_size(self):
        """Update marker positions based on current sample size selection."""
        if not hasattr(self, 'grid') or self.grid is None:
            return
            
        sample_multiplier = self.sample_sizes[self.current_sample_size]
        # Calculate the number of slots for this sample size
        sample_slots = self.window_slots * sample_multiplier
        
        # Keep left marker at current position, adjust right marker
        self.right_marker_slot = min(
            self.left_marker_slot + sample_slots,
            self.record_slots
        )
        
        # Update visual positions
        self.left_marker_x = self.grid.get_x_from_slot(self.left_marker_slot)
        self.right_marker_x = self.grid.get_x_from_slot(self.right_marker_slot)
        self._update_marker_lines()
        
        # Update loop engine
        self.loop_engine.set_left_margin_of_recording(self.animal_id, self.left_marker_slot)
        self.loop_engine.set_right_margin_of_recording(self.animal_id, self.right_marker_slot)

    def _update_marker_lines(self):
        if not self.left_marker_line or not self.right_marker_line:
            return

        self.left_marker_line.points = [
            self.left_marker_x,
            0,
            self.left_marker_x,
            Window.height,
        ]
        self.right_marker_line.points = [
            self.right_marker_x,
            0,
            self.right_marker_x,
            Window.height,
        ]

    def on_touch_down(self, touch):
        if not self.left_marker_line or not self.right_marker_line:
            return super(RecordScreen, self).on_touch_down(touch)

        MARKER_TOLERANCE = 30

        if abs(touch.x - self.left_marker_x) < MARKER_TOLERANCE:
            self.dragging_marker = "left"
            touch.grab(self)
            return True
        elif abs(touch.x - self.right_marker_x) < MARKER_TOLERANCE:
            self.dragging_marker = "right"
            touch.grab(self)
            return True

        return super(RecordScreen, self).on_touch_down(touch)

    def on_touch_move(self, touch):
        if self.dragging_marker and touch.grab_current == self:
            if self.dragging_marker == "left":
                # Calculate the current distance between markers
                marker_distance = self.right_marker_x - self.left_marker_x
                
                # Move left marker to touch position with boundary constraints
                sample_multiplier = self.sample_sizes[self.current_sample_size]
                sample_slots = self.window_slots * sample_multiplier
                max_left_x = self.grid.get_x_from_slot(self.record_slots - sample_slots)
                
                new_left_x = max(0, min(touch.x, max_left_x))
                
                # Move right marker by the same amount to maintain exact distance
                self.left_marker_x = new_left_x
                self.right_marker_x = new_left_x + marker_distance
                
            elif self.dragging_marker == "right":
                # Calculate the current distance between markers
                marker_distance = self.right_marker_x - self.left_marker_x
                
                # Move right marker to touch position with boundary constraints
                min_right_x = marker_distance  # Minimum distance from left edge
                max_right_x = self.grid.get_x_from_slot(self.record_slots)
                
                new_right_x = max(min_right_x, min(touch.x, max_right_x))
                
                # Move left marker by the same amount to maintain exact distance
                self.right_marker_x = new_right_x
                self.left_marker_x = new_right_x - marker_distance

            self._update_marker_lines()
            return True

        return super(RecordScreen, self).on_touch_move(touch)

    def on_touch_up(self, touch):
        if self.dragging_marker and touch.grab_current == self:
            touch.ungrab(self)

            # Convert current marker positions back to slots (without snapping)
            self.left_marker_slot = self.grid.get_slot_from_x(self.left_marker_x)
            self.right_marker_slot = self.grid.get_slot_from_x(self.right_marker_x)
            
            # Update loop engine with the current positions
            self.loop_engine.set_left_margin_of_recording(self.animal_id, self.left_marker_slot)
            self.loop_engine.set_right_margin_of_recording(self.animal_id, self.right_marker_slot)

            self.dragging_marker = None
            return True

        return super(RecordScreen, self).on_touch_up(touch)

    def _trim_recording_to_loop_window(self) -> str:
        wav_path = get_recording_wav_path(self.animal_id)
        if not os.path.exists(wav_path):
            return wav_path

        offset = self.loop_engine.get_loop_offset(self.animal_id)
        duration = self.loop_engine.get_loop_duration(self.animal_id)
        if duration <= 0:
            return wav_path

        data, sr = sf.read(wav_path, always_2d=False)
        if data.size == 0:
            return wav_path

        start = int(offset * sr)
        end = start + int(duration * sr)
        start = max(0, min(start, len(data)))
        end = max(start, min(end, len(data)))
        trimmed = data[start:end]
        if trimmed.size == 0:
            return wav_path

        sf.write(wav_path, trimmed, sr)
        self.loop_engine.add_or_update_animal_loop(self.animal_id, wav_path)

        return wav_path

    def _add_animal(self, *_):
        wav_path = self._trim_recording_to_loop_window()
        out_dir = get_animal_data_dir(self.animal_id)
        out_path = os.path.join(out_dir, "open.png")

        offset = 0.0
        duration = self.loop_engine.get_loop_duration(self.animal_id)

        render_creature_image(
            wav_path,
            out_dir,
            size=(640, 480),
            offset=offset,
            duration=duration,
        )

        animal = Animal(
            animal_id=self.animal_id,
            image_path=out_path,
            recording_path=wav_path,
            pos=(50, 50),
            size=(100, 100),
        )

        garden = next((s for s in self.manager.screens if s.name == "garden"), None)
        if garden:
            garden.add_or_update_animal(animal)

        self.switch_to("garden")

    def _ingest_for_waveform(self, data, num_channels: int):
        if not self.is_recording or len(self.samples) >= self.max_samples:
            return

        mono = data[0::num_channels] if num_channels > 1 else data
        if mono.size == 0:
            return

        clipped = np.tanh(mono[::self.decimate] * 5.0)

        remaining = self.max_samples - len(self.samples)
        if remaining <= 0:
            return
        if clipped.size > remaining:
            clipped = clipped[:remaining]

        self.samples.extend(float(s) for s in clipped)

    def _update_wave(self):
        cy = Window.height / 2
        total_n = len(self.samples)

        if total_n < 2:
            self.wave_line.points = [0, cy, Window.width, cy]
            return

        arr = np.asarray(self.samples, dtype=float)

        max_points = 2000
        if total_n > max_points:
            stride = int(np.ceil(total_n / max_points))
            arr = arr[::stride]
        n = len(arr)

        peak = float(np.max(np.abs(arr))) if arr.size else 0.0
        if peak == 0.0:
            yscale = self.viz_scale
        else:
            yscale = min(self.viz_scale, (self.viz_scale * 0.9) / peak)

        ys = cy + arr * yscale
        ys = np.clip(ys, 0.0, float(Window.height))

        progress = max(0.0, min(1.0, total_n / float(self.max_samples)))
        max_x = Window.width * progress
        if max_x <= 0:
            self.wave_line.points = [0, cy, Window.width, cy]
            return

        xs = np.linspace(0.0, max_x, n, dtype=float)

        pts = np.empty(n * 2, dtype=float)
        pts[0::2], pts[1::2] = xs, ys
        self.wave_line.points = pts.tolist()