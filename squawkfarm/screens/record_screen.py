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
    get_ui_asset_path,
    get_recording_wav_path,
    get_animal_data_dir,
    get_animal_recording_dir,
    get_metronome_sound_path,
    get_available_default_sounds,
    get_default_sound_path,
)
from squawkfarm.models.loop_runtime import Recording

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
        self.loop_engine = Screen.globals.loop_engine

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

        # Default sounds dropdown
        self.default_sounds = get_available_default_sounds()
        self.default_sound_names = [name for name, _ in self.default_sounds]
        
        self.default_sounds_spinner = ShadowSpinner(
            text="[b]default menu[/b]",
            markup=True,
            values=self.default_sound_names if self.default_sound_names else ["(no sounds)"],
            size_hint=(None, None),
            size=(160, 60),
            pos=(20 + 160 + 20, Window.height - 80),
            disabled=False,
            opacity=1,
            background_normal='',
            background_down='',
            background_color=(1, 0.9, 0.95, 1),
            color=(0.05, 0.05, 0.3, 1),
            font_size=24,
            option_cls=self._create_spinner_option_cls(),
        )
        self.default_sounds_spinner.bind(text=self._on_default_sound_selected)

        self.max_display_points = 2000
        self.samples = []

        total_raw_samples = int(self.record_duration * Audio.sample_rate)
        self.decimate = max(1, total_raw_samples // self.max_display_points)

        self.is_recording = False
        self.animal_id = ""

        self.count_in_generator = None
        self.count_in_audio = Audio(num_channels=1)

        self.left_marker_line = None
        self.right_marker_line = None
        self.left_marker_x = 0
        self.right_marker_x = Window.width
        self.dragging_marker = None
        self.skip_margin_update = False  # Flag to skip _update_recording_margins if we just set margins directly
        self.is_default_sound = False  # Flag to indicate if current recording is a default sound

    def _set_editing_buttons_visible(self, visible):
        self.add_loop_btn.disabled = not visible
        self.add_loop_btn.opacity = 1 if visible else 0
        self.play_btn.disabled = not visible
        self.play_btn.opacity = 1 if visible else 0
        self.sample_size_spinner.disabled = not visible
        self.sample_size_spinner.opacity = 1 if visible else 0
        # default_sounds_spinner is always visible, so don't change its visibility

    def _add_button_widgets(self):
        self.add_widget(self.record_btn)
        self.add_widget(self.play_btn)
        self.add_widget(self.add_loop_btn)
        self.add_widget(self.sample_size_spinner)
        self.add_widget(self.default_sounds_spinner)
        self.add_widget(self.barn_btn)

    def _remove_button_widgets(self):
        self.remove_widget(self.record_btn)
        self.remove_widget(self.play_btn)
        self.remove_widget(self.add_loop_btn)
        self.remove_widget(self.sample_size_spinner)
        self.remove_widget(self.default_sounds_spinner)
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

        self.canvas.before.clear()
        self.canvas.clear()

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
        self._update_sample_pixels()

    def on_update(self):
        if self.is_recording:
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
        if hasattr(self, '_record_scheduled_event') and self._record_scheduled_event:
            self._record_scheduled_event.cancel()
            self._record_scheduled_event = None

        self.is_recording = False
        self._recording_started = False
        self._clear_marker_lines()
        self._set_editing_buttons_visible(False)
        self.record_btn.source = self.record_icon_path
        self.record_btn.disabled = False
        self._remove_button_widgets()
        self.loop_engine.pause()

    def _on_barn_press(self, *_):
        self.switch_to("garden")

    def _on_record_press(self, *_):
        if not self.is_recording:
            if not hasattr(self, '_recording_started') or not self._recording_started:
                self._start_recording()
            else:
                self._resume_recording()
        else:
            self._pause_recording()

    def _on_play_press(self, *_):
        self.loop_engine.toggle_play_recording_preview()
        
    def _update_sample_pixels(self):
        num_beats = self.sample_sizes[self.current_sample_size]
        sample_slots = self.loop_engine.beat_to_slot(num_beats)
        self.sample_pixels = self.grid.slots_to_pixels(sample_slots)
        
    def _on_sample_size_change(self, spinner, text):
        self.current_sample_size = text
        self._update_sample_pixels()

        if self.loop_engine.recording is None:
            return

        self.right_marker_x = self.left_marker_x + self.sample_pixels
        overflow = self.right_marker_x - Window.width
        if overflow > 0:
            self.left_marker_x -= overflow
            self.right_marker_x -= overflow

        self._update_marker_lines()
        self._update_recording_margins()

    def _on_default_sound_selected(self, spinner, sound_name):
        """Load a default sound into the recording"""
        # Reset the spinner text first to avoid triggering again
        self.default_sounds_spinner.text = "[b]default menu[/b]"
        
        # Find the sound file path
        sound_path = None
        for display_name, filename in self.default_sounds:
            if display_name == sound_name:
                sound_path = get_default_sound_path(display_name)
                break
        
        if not sound_path or not os.path.exists(sound_path):
            print(f"Error: Could not find default sound: {sound_name}")
            return
        
        try:
            # Create a Recording object from the default sound file
            recording = Recording(sound_path)
            self.loop_engine.recording = recording
            self.loop_engine.recording_frame_count = recording.get_num_frames()
            
            # Load audio data for visualization
            wav_file = WaveFile(sound_path)
            audio_data = wav_file.get_frames(0, wav_file.end)
            
            # Process audio for visualization
            self.samples.clear()
            mono = audio_data  # Already mono from WaveFile
            clipped = np.tanh(mono[::self.decimate] * 5.0)
            
            remaining = self.max_display_points
            if clipped.size > remaining:
                clipped = clipped[:remaining]
            
            self.samples.extend(float(s) for s in clipped)
            
            # Mark that we have a recording loaded (but not currently recording)
            self.is_recording = False
            self._recording_started = True
            self._recorded_frames = recording.get_num_frames()
            
            # Show the editing buttons and record button
            self._set_editing_buttons_visible(True)
            self.record_btn.disabled = False
            self.record_btn.source = self.pause_icon_path  # Show pause icon since we're "paused"
            
            # Initialize marker positions
            self._clear_marker_lines()
            self._update_sample_pixels()
            
            # For default sounds, directly calculate the frame range based on selected sample size
            # But also ensure it fits within the grid's time span
            num_beats = self.sample_sizes[self.current_sample_size]
            num_frames_for_size = int(num_beats * Audio.sample_rate)
            
            # Get file duration first
            file_num_frames = recording.get_num_frames()
            
            # Get the grid's total duration
            grid_total_slots = self.loop_engine.grid.get_total_slots()
            grid_total_frames = self.loop_engine.grid.slot_to_frame(grid_total_slots)
            
            print(f"[_on_default_sound_selected] Default sound margins:")
            print(f"  Selected size: {self.current_sample_size} ({num_beats} beats = {num_frames_for_size} frames)")
            print(f"  File duration: {file_num_frames} frames")
            print(f"  Grid duration: {grid_total_frames} frames")
            
            # If the selected sample size would extend beyond the grid, clamp it
            actual_num_frames = min(num_frames_for_size, grid_total_frames)
            if actual_num_frames < num_frames_for_size:
                print(f"  Sample size too large for grid! Clamping to {actual_num_frames} frames")
            
            # If file is smaller than what we want to use, use the whole file
            if file_num_frames < actual_num_frames:
                print(f"  File smaller than requested. Using full file: {file_num_frames} frames")
                actual_num_frames = file_num_frames
            
            # Trim from the center of the file
            start_frame = max(0, (file_num_frames - actual_num_frames) // 2)
            end_frame = min(file_num_frames, start_frame + actual_num_frames)
            
            print(f"  Trimming from frame {start_frame} to {end_frame} ({end_frame - start_frame} frames)")
            
            # Set the margins directly using frame numbers
            self.loop_engine.recording.set_left_margin(start_frame)
            self.loop_engine.recording.set_right_margin(end_frame)
            
            # Verify the trim worked
            actual_trimmed = self.loop_engine.recording.get_num_frames()
            print(f"  After trim: {actual_trimmed} frames (expected {num_frames_for_size})")
            
            # Calculate visual marker positions from the trimmed frame region
            # Convert frames to grid positions based on the grid's total duration
            grid_total_slots = self.loop_engine.grid.get_total_slots()
            grid_total_frames = self.loop_engine.grid.slot_to_frame(grid_total_slots)
            print(f"  Grid total frames: {grid_total_frames}, Grid total slots: {grid_total_slots}")
            
            # Calculate what fraction of the grid each frame position represents
            if grid_total_frames > 0:
                left_fraction = start_frame / grid_total_frames
                right_fraction = end_frame / grid_total_frames
                self.left_marker_x = self.grid.x + left_fraction * self.grid.width
                self.right_marker_x = self.grid.x + right_fraction * self.grid.width
                print(f"  Frame {start_frame} -> fraction {left_fraction:.4f} -> pixel {self.left_marker_x:.1f}")
                print(f"  Frame {end_frame} -> fraction {right_fraction:.4f} -> pixel {self.right_marker_x:.1f}")
            else:
                # If grid duration is 0 or unknown, use the file fractions as fallback
                total_frames = recording.last_frame
                if total_frames > 0:
                    left_fraction = start_frame / total_frames
                    right_fraction = end_frame / total_frames
                    self.left_marker_x = self.grid.x + left_fraction * self.grid.width
                    self.right_marker_x = self.grid.x + right_fraction * self.grid.width
                    print(f"  (fallback) Using file fractions: {left_fraction:.4f} to {right_fraction:.4f}")
            
            # Draw the markers (using the calculated positions, not grid-centered)
            grid_bottom = self.grid.y
            grid_top = self.grid.y + self.grid.height
            
            self._clear_marker_lines()
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
            
            # Set flag so that _update_recording_margins doesn't override our carefully set margins
            self.skip_margin_update = True
            self.is_default_sound = True
            
            # Update the waveform visualization
            self._update_wave()
            
            print(f"Loaded default sound: {sound_name} ({self._recorded_frames} frames)")
        except AssertionError as e:
            print(f"Error loading default sound {sound_name}: Sample rate mismatch or format issue")
            print(f"Default sounds must be 16-bit WAV files with 44100 Hz sample rate")
        except Exception as e:
            print(f"Error loading default sound {sound_name}: {e}")
            import traceback
            traceback.print_exc()

    def _start_recording(self):
        self.samples.clear()
        self._recording_started = False
        self._recorded_frames = 0
        self._record_scheduled_event = None
        self.is_default_sound = False  # Reset flag for recorded audio

        self._clear_marker_lines()
        self._set_editing_buttons_visible(False)
        self.record_btn.disabled = True
        count_in_duration = self._play_count_in()

        Clock.schedule_once(lambda dt: self._begin_actual_recording(), count_in_duration)

    def _begin_actual_recording(self):
        self._recording_started = True
        self.is_recording = True
        self.record_btn.disabled = False
        self.record_btn.source = self.pause_icon_path
        self.writer.start()

        remaining_time = self.record_duration - (self._recorded_frames / Audio.sample_rate)
        self._record_scheduled_event = Clock.schedule_once(
            lambda dt: self._finish_recording(), remaining_time
        )

    def _pause_recording(self):
        self.is_recording = False
        self.record_btn.source = self.record_icon_path

        if self._record_scheduled_event:
            self._record_scheduled_event.cancel()
            self._record_scheduled_event = None

        self._recorded_frames = len(self.samples) * self.decimate

    def _resume_recording(self):
        self.is_recording = True
        self.record_btn.source = self.pause_icon_path

        remaining_frames = int(self.record_duration * Audio.sample_rate) - self._recorded_frames
        remaining_time = remaining_frames / Audio.sample_rate

        if remaining_time > 0:
            self._record_scheduled_event = Clock.schedule_once(
                lambda dt: self._finish_recording(), remaining_time
            )
        else:
            self._finish_recording()

    def _finish_recording(self):
        self.is_recording = False
        self._recording_started = False
        self.record_btn.source = self.record_icon_path

        self.writer.stop("raw")

        self.loop_engine.set_recording(self.animal_id)
        self._draw_margin_markers()
        self._update_recording_margins()
        self._set_editing_buttons_visible(True)

    def _update_recording_margins(self):
        # Skip if we just loaded a default sound and set margins directly
        if self.skip_margin_update:
            print(f"[_update_recording_margins] Skipping - default sound margins already set")
            self.skip_margin_update = False
            return
        
        # For default sounds, convert visual marker positions to frame numbers based on grid duration
        if self.is_default_sound:
            print(f"[_update_recording_margins] Updating default sound margins from visual markers")
            
            # Calculate grid duration in frames
            grid_total_slots = self.loop_engine.grid.get_total_slots()
            grid_total_frames = self.loop_engine.grid.slot_to_frame(grid_total_slots)
            
            # Convert marker pixel positions to frame positions
            left_fraction = (self.left_marker_x - self.grid.x) / self.grid.width if self.grid.width > 0 else 0
            right_fraction = (self.right_marker_x - self.grid.x) / self.grid.width if self.grid.width > 0 else 0
            
            left_frame = int(left_fraction * grid_total_frames)
            right_frame = int(right_fraction * grid_total_frames)
            
            print(f"[_update_recording_margins] Markers: {self.left_marker_x:.1f} to {self.right_marker_x:.1f}")
            print(f"[_update_recording_margins] Fractions: {left_fraction:.4f} to {right_fraction:.4f}")
            print(f"[_update_recording_margins] Frames: {left_frame} to {right_frame}")
            
            # Set the recording margins
            self.loop_engine.recording.set_left_margin(left_frame)
            self.loop_engine.recording.set_right_margin(right_frame)
            return
        
        left_fraction = (self.left_marker_x - self.grid.x) / self.grid.width
        right_fraction = (self.right_marker_x - self.grid.x) / self.grid.width
        print(f"[_update_recording_margins] left_marker_x={self.left_marker_x}, right_marker_x={self.right_marker_x}, grid.x={self.grid.x}, grid.width={self.grid.width}")
        print(f"[_update_recording_margins] left_fraction={left_fraction:.4f}, right_fraction={right_fraction:.4f}")
        print(f"[_update_recording_margins] sample_size={self.current_sample_size}, sample_pixels={self.sample_pixels}")
        
        # Check if the selected sample size is larger than the available audio
        if self.loop_engine.recording:
            file_frames = self.loop_engine.recording.last_frame
            num_beats = self.sample_sizes[self.current_sample_size]
            requested_frames = int(num_beats * Audio.sample_rate)
            available_beats = file_frames / Audio.sample_rate
            
            print(f"[_update_recording_margins] Audio available: {file_frames} frames ({available_beats:.2f} sec), Requested: {requested_frames} frames ({num_beats:.1f} beats)")
            
            # If file is shorter than requested, snap to the largest size that fits
            if file_frames < requested_frames:
                print(f"[_update_recording_margins] File too short for {self.current_sample_size}!")
                
                # Find the largest sample size that fits in the available audio
                best_size = "Super Small"  # Default to smallest
                best_beats = 0.5
                
                print(f"[_update_recording_margins] Available audio: {available_beats:.2f} seconds. Checking which sizes fit:")
                for size_name, size_beats in self.sample_sizes.items():
                    fits = size_beats <= available_beats
                    print(f"[_update_recording_margins]   {size_name}: {size_beats} beats - {fits}")
                    if fits and size_beats > best_beats:
                        best_size = size_name
                        best_beats = size_beats
                
                print(f"[_update_recording_margins] Snapping to: {best_size} ({best_beats} beats = {int(best_beats * Audio.sample_rate)} frames)")
                
                # Update the spinner to show the correct size
                self.sample_size_spinner.text = best_size
                self.current_sample_size = best_size
                
                # Use the full file
                self.loop_engine.set_left_margin_of_recording(0.0)
                self.loop_engine.set_right_margin_of_recording(1.0)
                return
        
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
    


    def _draw_margin_markers(self):
        grid_center_x = self.grid.x + self.grid.width / 2
        self.left_marker_x = grid_center_x - self.sample_pixels / 2
        self.right_marker_x = grid_center_x + self.sample_pixels / 2

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

        self._update_wave()

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
            grid_right = self.grid.x + self.grid.width
            if self.dragging_marker == "left":
                max_left_x = grid_right - self.sample_pixels
                new_left_x = max(grid_left, min(touch.x, max_left_x))

                self.left_marker_x = new_left_x
                self.right_marker_x = new_left_x + marker_distance

            elif self.dragging_marker == "right":
                new_right_x = max(grid_left + self.sample_pixels, min(touch.x, grid_right))

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
        if not self.is_recording or len(self.samples) >= self.max_display_points:
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

        if total_n < 2:
            self.wave_line.points = [grid_x, cy, grid_x + grid_w, cy]
            self.wave_shadow.points = [grid_x + 2, cy - 2, grid_x + grid_w + 2, cy - 2]
            self.wave_line_trim.points = []
            return

        progress = max(0.0, min(1.0, total_n / float(self.max_display_points)))
        max_x = grid_x + grid_w * progress
        if max_x <= grid_x:
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
        xs = np.linspace(grid_x, max_x, n, dtype=float)

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