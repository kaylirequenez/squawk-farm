import math
import os
import uuid
import numpy as np

from kivy.uix.button import Button
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.image import Image
from kivy.core.window import Window
from kivy.graphics import Color, Line, Rectangle
from kivy.clock import Clock

from squawkfarm.services.loop_engine import LoopEngine


class ImageButton(ButtonBehavior, Image):
    pass

from imslib.audio import Audio
from imslib.screen import Screen
from imslib.writer import AudioWriter
from imslib.wavesrc import WaveFile
from imslib.wavegen import WaveGenerator

from squawkfarm.ui.loop_grid import LoopGrid
from squawkfarm.services.animal_gen import render_creature_image
from squawkfarm.models.animal import Animal
from squawkfarm.utils import (
    get_recording_wav_path,
    get_animal_data_dir,
    get_animal_recording_dir,
    get_metronome_sound_path,
)
from squawkfarm.utils import get_animal_recording_dir, get_ui_asset_path

class StyledSpinnerOption(SpinnerOption):
    def __init__(self, **kwargs):
        kwargs.setdefault('background_normal', '')
        kwargs.setdefault('background_down', '')
        kwargs.setdefault('background_color', (1, 0.9, 0.95, 1))
        kwargs.setdefault('color', (0.05, 0.05, 0.3, 1))
        kwargs.setdefault('font_size', 22)
        kwargs.setdefault('markup', True)
        super().__init__(**kwargs)


class ShadowSpinner(Spinner):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._shadow_rect = None
        self.bind(pos=self._update_shadow, size=self._update_shadow)
        self._update_shadow()

    def _update_shadow(self, *_):
        if self._shadow_rect:
            self.canvas.before.remove(self._shadow_rect)
            self._shadow_rect = None

        with self.canvas.before:
            Color(0.15, 0.1, 0.05, 0.7)
            self._shadow_rect = Rectangle(
                pos=(self.x + 5, self.y - 5),
                size=self.size
            )


class RecordScreen(Screen):
    TARGET_PTS_PER_SEC = 2200

    def _create_spinner_option_cls(self):
        return StyledSpinnerOption

    def __init__(self, **kwargs):
        super(RecordScreen, self).__init__(**kwargs)
        self.loop_engine: LoopEngine = Screen.globals.loop_engine

        self.window_slots = self.loop_engine.beat_to_slot(1)
        self.record_slots = self.window_slots * 8
        self.record_duration = self.loop_engine.slot_to_time(self.record_slots)

        self.grid_x_margin = Window.width * 0.1
        self.grid_y_margin = Window.height * 0.15

        def listen_func(data, num_channels):
            self.writer.add_audio(data, num_channels)
            self._ingest_for_waveform(data, num_channels)

        self.mic = Audio(num_channels=1, input_func=listen_func, num_input_channels=1)

        self.viz_scale = Window.height * 0.25

        self.barn_path = get_ui_asset_path("barn.png")
        self.barn = Image(source=self.barn_path).texture
        self.barn_btn_size = Window.width / 8
        self.barn_btn = Button(
            size_hint=(None, None),
            size=(self.barn_btn_size, self.barn_btn_size),
            pos=(Window.width - self.barn_btn_size, 0),
            background_normal="",
            background_color=(1, 1, 1, 0),
        )
        with self.barn_btn.canvas.before:
            self.barn_rect = Rectangle(
                pos=self.barn_btn.pos,
                size=self.barn_btn.size,
                texture=self.barn,
            )
        self.barn_btn.bind(on_press=self._on_barn_press)

        # Record/Pause button (image-based)
        self.btn_size = 100
        self.record_icon_path = get_ui_asset_path("record.png")
        self.pause_icon_path = get_ui_asset_path("pause.png")

        self.record_btn = ImageButton(
            source=self.record_icon_path,
            size_hint=(None, None),
            size=(self.btn_size, self.btn_size),
            pos=(20, 20),
        )
        self.record_btn.bind(on_release=self._on_record_press)

        self.play_icon_path = get_ui_asset_path("play.png")
        self.play_btn = ImageButton(
            source=self.play_icon_path,
            size_hint=(None, None),
            size=(self.btn_size, self.btn_size),
            pos=(20 + self.btn_size + 20, 20),
            opacity=0,
            disabled=True,
        )
        self.play_btn.bind(on_release=self._on_play_press)

        self.hatch_icon_path = get_ui_asset_path("hatch.png")
        self.hatch_btn_size = 300
        self.add_loop_btn = ImageButton(
            source=self.hatch_icon_path,
            size_hint=(None, None),
            size=(self.hatch_btn_size, self.hatch_btn_size),
            pos=(Window.width - self.hatch_btn_size - 20, Window.height - self.hatch_btn_size - 20),
            disabled=True,
            opacity=0,
        )
        self.add_loop_btn.bind(on_release=self._add_animal)

        self.sample_sizes = {
            "Super Small": 0.5,
            "Small": 1,
            "Medium": 2,
            "Large": 4
        }
        self.current_sample_size = "Medium"
        
        self.sample_size_spinner = ShadowSpinner(
            text=f"[b]{self.current_sample_size}[/b]",
            markup=True,
            values=list(self.sample_sizes.keys()),
            size_hint=(None, None),
            size=(160, 60),
            pos=(20, Window.height - 80),
            disabled=True,
            opacity=0,
            background_normal='',
            background_down='',
            background_color=(1, 0.9, 0.95, 1),
            color=(0.05, 0.05, 0.3, 1),
            font_size=24,
            option_cls=self._create_spinner_option_cls(),
        )
        self.sample_size_spinner.bind(text=self._on_sample_size_change)

        self.max_display_points = 2000
        self.samples = []

        total_raw_samples = int(self.record_duration * Audio.sample_rate)
        self.decimate = max(1, total_raw_samples // self.max_display_points)

        self.animal_id = ""

        self.count_in_generator = None
        self.count_in_audio = Audio(num_channels=1)

        self.left_marker_line = None
        self.right_marker_line = None
        self.left_marker_x = None
        self.right_marker_x = None
        self.dragging_marker = None

    def _set_editing_buttons_visible(self, visible):
        self.add_loop_btn.disabled = not visible
        self.add_loop_btn.opacity = 1 if visible else 0
        self.play_btn.disabled = not visible
        self.play_btn.opacity = 1 if visible else 0
        self.sample_size_spinner.disabled = not visible
        self.sample_size_spinner.opacity = 1 if visible else 0

    def _add_button_widgets(self):
        self.add_widget(self.record_btn)
        self.add_widget(self.play_btn)
        self.add_widget(self.add_loop_btn)
        self.add_widget(self.sample_size_spinner)
        self.add_widget(self.barn_btn)

    def _remove_button_widgets(self):
        self.remove_widget(self.record_btn)
        self.remove_widget(self.play_btn)
        self.remove_widget(self.add_loop_btn)
        self.remove_widget(self.sample_size_spinner)
        self.remove_widget(self.barn_btn)

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

        self.dragging_marker = None

    def on_enter(self, *_):
        self.animal_id = str(uuid.uuid4())
        self.writer = AudioWriter(get_animal_recording_dir(self.animal_id), num_channels=1)
        self.max_possible_sample_size = None

        self._clear_editing_buttons()
        self.canvas.before.clear()
        self.canvas.clear()
        
        self._recording_started = False

        # Add layered backgrounds: lawn.png then board.png on top
        with self.canvas.before:
            Color(1, 1, 1, 1)
            lawn_path = get_ui_asset_path("lawn.png")
            lawn_tex = Image(source=lawn_path).texture if os.path.exists(lawn_path) else None
            if lawn_tex:
                Rectangle(pos=(0, 0), size=Window.size, texture=lawn_tex)

          
        self.grid = LoopGrid(
            total_slots=self.record_slots,
            slots_per_beat=self.loop_engine.get_slots_per_beat(),
            slots_per_measure=self.loop_engine.get_slots_per_measure(),
            x_margin=self.grid_x_margin,
            y_margin=self.grid_y_margin,
            skip_outer_lines=True,
        )
        self.canvas.before.add(self.grid)

        grid_cy = self.grid.y + self.grid.height / 2

        with self.canvas:
            Color(0.4, 0.4, 0.6, 0.5)
            self.wave_shadow = Line(
                points=[self.grid.x + 2, grid_cy - 2, self.grid.x + self.grid.width + 2, grid_cy - 2],
                width=2.5,
            )
            Color(0.6, 0.6, 0.85, 1)
            self.wave_line = Line(
                points=[self.grid.x, grid_cy, self.grid.x + self.grid.width, grid_cy],
                width=2.0,
            )
            Color(0.45, 0.6, 0.35, 1)
            self.wave_line_trim = Line(
                points=[self.grid.x, grid_cy, self.grid.x, grid_cy],
                width=2.0,
            )

        self._add_button_widgets()

    def on_update(self):
        if self.writer.active:
            self.mic.on_update()
            self._update_wave()
        
        if self.count_in_audio.generator is not None:
            self.count_in_audio.on_update()

        self.loop_engine.on_update()

    def on_resize(self, winsize):
        if hasattr(self, "grid"):
            self.grid.x_margin = Window.width * 0.1
            self.grid.y_margin = Window.height * 0.15
            self.grid.on_resize(winsize)
            self.viz_scale = self.grid.height * 0.4
        self.add_loop_btn.pos = (Window.width - self.hatch_btn_size - 20, Window.height - self.hatch_btn_size - 20)
        self.sample_size_spinner.pos = (20, Window.height - 80)
        self.barn_btn.size = (Window.width / 8, Window.width / 8)
        self.barn_btn.pos = (Window.width - self.barn_btn.width, 0)
        self.barn_rect.size = self.barn_btn.size
        self.barn_rect.pos = self.barn_btn.pos

    def on_exit(self):
        if self._record_scheduled_event:
            self._record_scheduled_event.cancel()
            self._record_scheduled_event = None

        self._set_editing_buttons_visible(False)
        self.record_btn.source = self.record_icon_path
        self._remove_button_widgets()
        self.loop_engine.pause()

    def _on_barn_press(self, *_):
        self.switch_to("garden")

    def _on_record_press(self, *_):
        if not self.writer.active:
            if not self._recording_started:
                self._start_recording()
            else:
                self._clear_editing_buttons()
                self._begin_actual_recording(reset=False)
        else:
            self._pause_recording()

    def _on_play_press(self, *_):
        self.loop_engine.toggle_play_recording_preview()
        
    def _adjust_markers_for_sample_size_change(self):
        self.right_marker_x = self.left_marker_x + self.sample_pixels
        overflow = self.right_marker_x - self.max_x
        if overflow > 0:
            self.left_marker_x -= overflow
            self.right_marker_x -= overflow
        
        self._update_marker_lines()
        
    def _on_sample_size_change(self, _, text):
        self.current_sample_size = text
        
        if not self.writer.active:
            sample_size = self.sample_sizes[self.current_sample_size]
            self.sample_pixels = self._get_sample_pixels(sample_size)
            self._adjust_markers_for_sample_size_change()
            self._update_recording_margins()
            
    def _clear_editing_buttons(self):
        self._set_editing_buttons_visible(False)
        self._clear_marker_lines()
        self._set_editing_buttons_visible(False)

    def _start_recording(self):
        self.samples.clear()
        self._recording_started = False
        self._recorded_frames = 0
        self._record_scheduled_event = None
        self.left_marker_x = None
        self.right_marker_x = None

        self._clear_editing_buttons()
        count_in_duration = self._play_count_in()

        Clock.schedule_once(lambda dt: self._begin_actual_recording(), count_in_duration)

    def _begin_actual_recording(self, reset=True):
        self._recording_started = True
        self.record_btn.source = self.pause_icon_path
        self.writer.start(reset)

        remaining_time = self.record_duration - (self._recorded_frames / Audio.sample_rate)
        self._record_scheduled_event = Clock.schedule_once(
            lambda dt: self._finish_recording(), remaining_time
        )

    def _pause_recording(self, finished=False):
        self.writer.stop("raw")
        self.record_btn.source = self.record_icon_path

        if self._record_scheduled_event:
            self._record_scheduled_event.cancel()
            self._record_scheduled_event = None

        # Find the largest sample size that fits within max_x
        best_size = None
        if not finished:
            for key, sample_size in self.sample_sizes.items():
                if self._get_sample_pixels(sample_size) < (self.max_x - self.grid.x):
                    self.max_possible_sample_size = key
                    if self._get_sample_pixels(self.sample_sizes[self.current_sample_size]) >= self._get_sample_pixels(sample_size):
                        best_size = key
                    else:
                        break
                        
        if best_size is not None:
            self.current_sample_size = best_size
        
        large_enough = finished or best_size is not None
        self._setup_editing_after_recording(large_enough)
        
        self._recorded_frames = len(self.samples) * self.decimate

    def _finish_recording(self):
        self._recording_started = False
        self.max_possible_sample_size = "Large"

        self._pause_recording(True)
            
    def _get_sample_pixels(self, num_beats):
        sample_slots = self.loop_engine.beat_to_slot(num_beats)
        return self.grid.slots_to_pixels(sample_slots)
        
    def _setup_editing_after_recording(self, large_enough):
        self.loop_engine.set_recording(self.animal_id)
        
        if large_enough:
            sample_size = self.sample_sizes[self.current_sample_size]
            self.sample_pixels = self._get_sample_pixels(sample_size)
            
            self._initialize_markers()
            self.sample_size_spinner.text = self.current_sample_size
            self._set_editing_buttons_visible(True)
            
            # Set spinner values to all keys up to and including max_possible_sample_size
            all_keys = list(self.sample_sizes.keys())
            max_idx = all_keys.index(self.max_possible_sample_size)
            self.sample_size_spinner.values = all_keys[:max_idx+1]
        else:
            self.sample_pixels = self.max_x - self.grid.x

    def _update_recording_margins(self):
        recorded_pixels = self.max_x - self.grid.x
        left_fraction = (self.left_marker_x - self.grid.x) / recorded_pixels
        right_fraction = (self.right_marker_x - self.grid.x) / recorded_pixels
        self.loop_engine.set_left_margin_of_recording(left_fraction)
        self.loop_engine.set_right_margin_of_recording(right_fraction)

    def _play_count_in(self):
        try:
            wf = WaveFile(get_metronome_sound_path())
            metronome_data = wf.get_frames(0, wf.end)

            beat_duration = self.loop_engine.slot_to_time(self.loop_engine.beat_to_slot(1))

            metronome_duration = len(metronome_data) / Audio.sample_rate
            speed_factor = metronome_duration / beat_duration
            num_output_samples = int(len(metronome_data) / speed_factor)

            resampled_data = np.interp(
                np.linspace(0, len(metronome_data) - 1, num_output_samples),
                np.arange(len(metronome_data)),
                metronome_data
            )

            count_in_data = np.tile(resampled_data, 4)

            class ArrayBuffer:
                def __init__(self, data):
                    self.data = data
                    self.num_channels = 1
                
                def get_frames(self, start_frame, num_frames):
                    end_frame = min(start_frame + num_frames, len(self.data))
                    result = self.data[start_frame:end_frame]
                    if len(result) < num_frames:
                        result = np.append(result, np.zeros(num_frames - len(result)))
                    return result
                
                def get_num_channels(self):
                    return self.num_channels

            buffer = ArrayBuffer(count_in_data)
            self.count_in_generator = WaveGenerator(buffer, loop=False)
            self.count_in_generator.set_gain(0.7)
            self.count_in_audio.set_generator(self.count_in_generator)
            
            return beat_duration * 4
            
        except Exception as e:
            print(f"Error playing count-in: {e}")
            return 0.1

    def _initialize_markers(self):
        if not self.left_marker_x:
            center_x = self.grid.x + (self.max_x  - self.grid.x) / 2
            self.left_marker_x = center_x - self.sample_pixels / 2
            self.right_marker_x = center_x + self.sample_pixels / 2

        grid_bottom = self.grid.y
        grid_top = self.grid.y + self.grid.height

        self.canvas.after.add(Color(0.05, 0.05, 0.3, 1))
        self.left_marker_line = Line(
            points=[self.left_marker_x, grid_bottom, self.left_marker_x, grid_top],
            width=5,
        )
        self.canvas.after.add(self.left_marker_line)

        self.right_marker_line = Line(
            points=[self.right_marker_x, grid_bottom, self.right_marker_x, grid_top],
            width=5,
        )
        self.canvas.after.add(self.right_marker_line)

    def _update_marker_lines(self):
        if not self.left_marker_line or not self.right_marker_line:
            return

        grid_bottom = self.grid.y
        grid_top = self.grid.y + self.grid.height

        self.left_marker_line.points = [
            self.left_marker_x,
            grid_bottom,
            self.left_marker_x,
            grid_top,
        ]
        self.right_marker_line.points = [
            self.right_marker_x,
            grid_bottom,
            self.right_marker_x,
            grid_top,
        ]

        self._update_wave()

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
            marker_distance = self.right_marker_x - self.left_marker_x
            grid_left = self.grid.x
            if self.dragging_marker == "left":
                max_left_x = self.max_x - self.sample_pixels
                new_left_x = max(grid_left, min(touch.x, max_left_x))

                self.left_marker_x = new_left_x
                self.right_marker_x = new_left_x + marker_distance

            elif self.dragging_marker == "right":
                new_right_x = max(grid_left + self.sample_pixels, min(touch.x, self.max_x))

                self.right_marker_x = new_right_x
                self.left_marker_x = new_right_x - marker_distance

            self._update_marker_lines()
            return True

        return super(RecordScreen, self).on_touch_move(touch)

    def on_touch_up(self, touch):
        if self.dragging_marker and touch.grab_current == self:
            touch.ungrab(self)
            
            self._update_recording_margins()

            self.dragging_marker = None
            return True

        return super(RecordScreen, self).on_touch_up(touch)

    def _add_animal(self, *_):
        self.loop_engine.finalize_animal_loop(self.animal_id)
        
        self.loop_engine.auto_generate_for_animal(self.animal_id)
        
        wav_path = get_recording_wav_path(self.animal_id, "tuned")
        out_dir = get_animal_data_dir(self.animal_id)
        out_path = os.path.join(out_dir, "open.png")

        render_creature_image(
            wav_path,
            out_dir,
            size=(640, 480),
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
        if not self.writer.active or len(self.samples) >= self.max_display_points:
            return

        mono = data[0::num_channels] if num_channels > 1 else data
        if mono.size == 0:
            return

        clipped = np.tanh(mono[::self.decimate] * 5.0)

        remaining = self.max_display_points - len(self.samples)
        if remaining <= 0:
            return
        if clipped.size > remaining:
            clipped = clipped[:remaining]

        self.samples.extend(float(s) for s in clipped)

    def _update_wave(self):
        grid_x = self.grid.x
        grid_w = self.grid.width
        cy = self.grid.y + self.grid.height / 2
        total_n = len(self.samples)
        progress = max(0.0, min(1.0, total_n / float(self.max_display_points)))
        self.max_x = self.grid.x + self.grid.width * progress

        if total_n < 2:
            self.wave_line.points = [grid_x, cy, grid_x + grid_w, cy]
            self.wave_shadow.points = [grid_x + 2, cy - 2, grid_x + grid_w + 2, cy - 2]
            self.wave_line_trim.points = []
            return

        if self.max_x <= grid_x:
            self.wave_line.points = [grid_x, cy, grid_x + grid_w, cy]
            self.wave_shadow.points = [grid_x + 2, cy - 2, grid_x + grid_w + 2, cy - 2]
            self.wave_line_trim.points = []
            return

        arr = np.asarray(self.samples, dtype=float)
        n = len(arr)

        peak = float(np.max(np.abs(arr))) if arr.size else 0.0
        if peak == 0.0:
            yscale = self.viz_scale
        else:
            yscale = min(self.viz_scale, (self.viz_scale * 0.9) / peak)

        ys = cy + arr * yscale
        ys = np.clip(ys, float(self.grid.y), float(self.grid.y + self.grid.height))
        xs = np.linspace(grid_x, self.max_x, n, dtype=float)

        pts = np.empty(n * 2, dtype=float)
        pts[0::2], pts[1::2] = xs, ys
        self.wave_line.points = pts.tolist()

        shadow_ys = ys - 2
        shadow_xs = xs + 2
        shadow_pts = np.empty(n * 2, dtype=float)
        shadow_pts[0::2], shadow_pts[1::2] = shadow_xs, shadow_ys
        self.wave_shadow.points = shadow_pts.tolist()

        if hasattr(self, 'left_marker_x') and hasattr(self, 'right_marker_x') and self.left_marker_line:
            left_idx = int(np.searchsorted(xs, self.left_marker_x))
            right_idx = int(np.searchsorted(xs, self.right_marker_x))
            if left_idx < right_idx and left_idx < n:
                trim_xs = xs[left_idx:right_idx]
                trim_ys = ys[left_idx:right_idx]
                trim_pts = np.empty(len(trim_xs) * 2, dtype=float)
                trim_pts[0::2], trim_pts[1::2] = trim_xs, trim_ys
                self.wave_line_trim.points = trim_pts.tolist()
            else:
                self.wave_line_trim.points = []
        else:
            self.wave_line_trim.points = []