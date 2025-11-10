"""Loop editor screen — shows final waveform of last recording on a wood board.

This screen mirrors the visual style of `record_screen.RecordScreen` but instead
of recording it displays the final waveform of the most recent recording file.
A barn button in the lower-right navigates back to the garden screen.
"""
import os
import soundfile as sf
import numpy as np
from imslib.screen import Screen
from imslib.audio import Audio
from imslib.wavesrc import WaveBuffer
from imslib.wavegen import WaveGenerator
from kivy.core.window import Window
from kivy.graphics import Rectangle, Color, Line
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.clock import Clock


class LoopEditorScreen(Screen):
    def __init__(self, **kwargs):
        super(LoopEditorScreen, self).__init__(**kwargs)
        self.wood_rect = None
        self.waveform_line = None
        self.barn_button = None
        self.barn_rect = None
        # Trash control (bottom-left) and its texture rect
        self.trash_button = None
        self.trash_rect = None
        self.waveform_points = []
        self.viz_scale = Window.height * 0.2
        
        # Draggable markers for loop start and end
        self.left_marker_x = 0  # Will be set to margin in draw function
        self.right_marker_x = 0  # Will be set to margin + draw_width in draw function
        self.left_marker_line = None
        self.right_marker_line = None
        
        # Drag state
        self.dragging_marker = None  # None, 'left', or 'right'
        self.drag_start_x = 0
        
        # Audio playback
        self.raw_audio_data = None
        self.sample_rate = Audio.sample_rate
        self.audio = Audio(num_channels=1)
        self.playback_thread = None
        self._play_event = None
        
        # Sample button
        self.sample_button = Button(
            text='Sample',
            size_hint=(None, None),
            size=(100, 50),
            pos=(Window.width / 2 - 50, Window.height - 60)
        )
        self.sample_button.bind(on_press=self._on_sample_press)
        self.add_widget(self.sample_button)

        # Bind resize
        Window.bind(size=self.on_resize)

    def on_enter(self, *args):
        # Draw UI each time we enter to reflect any new recordings
        self._draw_board_and_waveform()

    def on_leave(self, *args):
        # cleanup if needed
        pass

    def _get_recordings_dir(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        recordings_dir = os.path.join(base_dir, "data", "recordings")
        return recordings_dir

    def _find_latest_recording(self):
        recordings_dir = self._get_recordings_dir()
        if not os.path.isdir(recordings_dir):
            return None
        files = [os.path.join(recordings_dir, f) for f in os.listdir(recordings_dir) if os.path.isfile(os.path.join(recordings_dir, f))]
        if not files:
            return None
        latest = max(files, key=os.path.getmtime)
        return latest

    def _load_waveform_points_from_file(self, path, decimation=20):
        try:
            data, sr = sf.read(path)
            self.sample_rate = sr
            # Store raw audio data for playback
            if data is not None and len(data) > 0:
                if data.ndim > 1:
                    self.raw_audio_data = data[:, 0]  # Take first channel
                else:
                    self.raw_audio_data = data
        except Exception:
            self.raw_audio_data = None
            return []
        if data is None or len(data) == 0:
            return []
        # If multi-channel, take first channel
        if data.ndim > 1:
            samples = data[:, 0]
        else:
            samples = data
        max_sample = np.max(np.abs(samples)) if samples.size else 1.0
        if max_sample == 0:
            max_sample = 1.0
        pts = [float(s) / max_sample for s in samples[::decimation]]
        return pts

    def _draw_board_and_waveform(self):
        # remove previous widgets/canvas items if any
        if self.wood_rect:
            try:
                self.canvas.before.remove(self.wood_rect)
            except Exception:
                pass
        if self.waveform_line:
            try:
                self.canvas.remove(self.waveform_line)
            except Exception:
                pass
        if self.left_marker_line:
            try:
                self.canvas.remove(self.left_marker_line)
            except Exception:
                pass
        if self.right_marker_line:
            try:
                self.canvas.remove(self.right_marker_line)
            except Exception:
                pass
        # remove barn and trash visuals/widgets if present
        if self.barn_rect:
            try:
                self.canvas.remove(self.barn_rect)
            except Exception:
                pass
        if self.trash_rect:
            try:
                self.canvas.remove(self.trash_rect)
            except Exception:
                pass
        if self.barn_button and self.barn_button.parent:
            try:
                self.remove_widget(self.barn_button)
            except Exception:
                pass
        if self.trash_button and self.trash_button.parent:
            try:
                self.remove_widget(self.trash_button)
            except Exception:
                pass
        
        # Reset marker references
        self.left_marker_line = None
        self.right_marker_line = None

        # draw wood board in canvas.before so it's behind widgets
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        woodB_path = os.path.join(base_dir, "assets", "ui_images", "woodB2.png")
        if not os.path.isfile(woodB_path):
            # fallback to relative path used elsewhere
            woodB_path = os.path.join(os.path.dirname(__file__), "../../assets/ui_images/woodB2.png")
        wood_tex = Image(source=woodB_path).texture if os.path.exists(woodB_path) else None
        with self.canvas.before:
            Color(1, 1, 1, 1)
            if wood_tex:
                self.wood_rect = Rectangle(pos=(0, 0), size=Window.size, texture=wood_tex)
            else:
                # plain background if texture missing
                self.wood_rect = Rectangle(pos=(0, 0), size=Window.size)

        # Trash button in bottom-left (discard)
        b_size = Window.width / 8
        self.trash_button = Button(
            size_hint=(None, None),
            size=(b_size, b_size),
            pos=(0, 0),
            background_normal='',
            background_color=(1, 1, 1, 0),
        )
        self.trash_button.bind(on_press=self.on_trash_press)
        self.add_widget(self.trash_button)

        # Barn button in bottom-right (save & return)
        self.barn_button = Button(
            size_hint=(None, None),
            size=(b_size, b_size),
            pos=(Window.width - b_size, 0),
            background_normal='',
            background_color=(1, 1, 1, 0),
        )
        self.barn_button.bind(on_press=self.on_barn_press)
        self.add_widget(self.barn_button)

        # Draw waveform in canvas so it's visible centered on screen
        # Load latest recording
        latest = self._find_latest_recording()
        if latest:
            self.waveform_points = self._load_waveform_points_from_file(latest)
        else:
            self.waveform_points = []

        # compute points across central 13/15ths of screen
        width = Window.width
        margin = width / 15
        draw_width = width - 2 * margin
        center_y = Window.height / 2

        # build line points
        points = []
        if len(self.waveform_points) < 2:
            # flat center line
            points = [margin, center_y, margin + draw_width, center_y]
        else:
            denom = max(1, len(self.waveform_points) - 1)
            for i, s in enumerate(self.waveform_points):
                x = margin + (i / denom) * draw_width
                y = center_y + float(s) * self.viz_scale
                points.extend([x, y])

        with self.canvas:
            Color(0, 0.8, 0, 1)
            self.waveform_line = Line(points=points, width=1.5)
            
            # Draw 9 vertical marker lines dividing the waveform into 8 equal parts
            Color(0, 0, 0, 0.5)  # Semi-transparent black
            for i in range(9):
                x = margin + (i / 8) * draw_width
                marker = Line(points=[x, center_y - Window.height * 0.25, x, center_y + Window.height * 0.25], width=1)
            
            # Draw left and right loop markers (red lines)
            Color(1, 0, 0, 1)  # Red for loop markers
            self.left_marker_x = margin
            self.left_marker_line = Line(
                points=[self.left_marker_x, center_y - Window.height * 0.35, self.left_marker_x, center_y + Window.height * 0.35],
                width=2.5
            )
            self.right_marker_x = margin + draw_width
            self.right_marker_line = Line(
                points=[self.right_marker_x, center_y - Window.height * 0.35, self.right_marker_x, center_y + Window.height * 0.35],
                width=2.5
            )
            
            Color(1, 1, 1, 1)
            # barn texture on canvas (for visual only)
            try:
                trash_path = os.path.join(base_dir, "assets", "ui_images", "trash.png")
                trash_tex = Image(source=trash_path).texture if os.path.exists(trash_path) else None
                if trash_tex and self.trash_button:
                    self.trash_rect = Rectangle(pos=self.trash_button.pos, size=self.trash_button.size, texture=trash_tex)
            except Exception:
                pass
            try:
                barn_path = os.path.join(base_dir, "assets", "ui_images", "redbarn2.png")
                barn_tex = Image(source=barn_path).texture if os.path.exists(barn_path) else None
                if barn_tex and self.barn_button:
                    self.barn_rect = Rectangle(pos=self.barn_button.pos, size=self.barn_button.size, texture=barn_tex)
            except Exception:
                pass

    def on_barn_press(self, instance=None):
        """Save trimmed audio based on markers and navigate back to garden"""
        # Save the trimmed audio first
        if self.raw_audio_data is not None and len(self.raw_audio_data) > 0:
            try:
                # Calculate which samples correspond to the marker positions
                width = Window.width
                margin = width / 15
                draw_width = width - 2 * margin
                
                total_samples = len(self.raw_audio_data)
                
                # Map marker positions to sample indices
                left_progress = (self.left_marker_x - margin) / draw_width
                right_progress = (self.right_marker_x - margin) / draw_width
                
                # Clamp to valid range
                left_progress = max(0, min(1, left_progress))
                right_progress = max(0, min(1, right_progress))
                
                # Convert to sample indices
                left_sample = int(left_progress * total_samples)
                right_sample = int(right_progress * total_samples)
                
                # Ensure valid range
                left_sample = max(0, min(left_sample, total_samples - 1))
                right_sample = max(left_sample + 1, min(right_sample, total_samples))
                
                # Extract the segment
                audio_segment = self.raw_audio_data[left_sample:right_sample]
                
                # Find the original recording file name and create a "final" version
                latest = self._find_latest_recording()
                if latest:
                    # Get the base filename without extension
                    base_name = os.path.splitext(os.path.basename(latest))[0]
                    
                    # Create the final filename (e.g., recording25.wav -> recording25final.wav)
                    recordings_dir = self._get_recordings_dir()
                    final_filename = os.path.join(recordings_dir, f"{base_name}final.wav")
                    
                    # Save the trimmed audio
                    sf.write(final_filename, audio_segment, self.sample_rate)
                    print(f"Saved trimmed audio to {final_filename}")
            except Exception as e:
                print(f"Error saving trimmed audio: {e}")
        
        # Navigate back to garden
        if self.manager:
            self.switch_to('garden')

    def on_trash_press(self, instance=None):
        """Discard and return to garden/main screen without saving."""
        # Do not save trimmed audio; just return to garden/main
        if self._play_event:
            try:
                self._play_event.cancel()
            except Exception:
                pass
            self._play_event = None

        # stop any audio generator
        try:
            self.audio.set_generator(None)
        except Exception:
            pass

        if self.manager:
            self.switch_to('garden')

    def _on_sample_press(self, instance):
        """Play back the audio between the markers"""
        if self.raw_audio_data is None or len(self.raw_audio_data) == 0:
            print("No audio data loaded")
            return
        
        # Calculate which samples correspond to the marker positions
        width = Window.width
        margin = width / 15
        draw_width = width - 2 * margin
        
        # Map marker positions to sample indices
        total_samples = len(self.raw_audio_data)
        
        # Calculate progress from 0 to 1 for each marker
        left_progress = (self.left_marker_x - margin) / draw_width
        right_progress = (self.right_marker_x - margin) / draw_width
        
        # Clamp to valid range
        left_progress = max(0, min(1, left_progress))
        right_progress = max(0, min(1, right_progress))
        
        # Convert to sample indices
        left_sample = int(left_progress * total_samples)
        right_sample = int(right_progress * total_samples)
        
        # Ensure valid range
        left_sample = max(0, min(left_sample, total_samples - 1))
        right_sample = max(left_sample + 1, min(right_sample, total_samples))
        
        # Play the selected segment via the project's audio generator model
        latest = self._find_latest_recording()
        if not latest:
            print("No recording file found to create WaveBuffer")
            return

        # number of frames to play
        num_frames = right_sample - left_sample
        if num_frames <= 0:
            print("Invalid segment length")
            return

        try:
            # Create an in-memory WaveBuffer pointing at the portion of the wave file
            wb = WaveBuffer(latest, left_sample, num_frames)
            gen = WaveGenerator(wb, loop=False)
            gen.set_gain(1.0)

            # Stop any existing playback generator
            self.audio.set_generator(None)

            # Set our generator on the audio object and schedule on_update ticks
            self.audio.set_generator(gen)

            # schedule audio.on_update() to be called frequently until generator finishes
            if self._play_event:
                try:
                    self._play_event.cancel()
                except Exception:
                    pass
            # schedule at ~60Hz to match the typical audio/update loop
            self._play_event = Clock.schedule_interval(self._audio_playback_tick, 1.0 / 60.0)

        except Exception as e:
            print(f"Error starting engine playback: {e}")

    def _audio_playback_tick(self, dt):
        """Clock callback that pumps the Audio object until the generator finishes."""
        try:
            # call on_update which will pull data from our generator and write to stream
            self.audio.on_update()
            # when generator finishes, Audio.on_update() clears self.audio.generator
            if self.audio.generator is None:
                if self._play_event:
                    try:
                        self._play_event.cancel()
                    except Exception:
                        pass
                    self._play_event = None
        except Exception as e:
            print(f"Error during audio playback tick: {e}")
            if self._play_event:
                try:
                    self._play_event.cancel()
                except Exception:
                    pass
                self._play_event = None

    def on_touch_down(self, touch):
        """Handle touch down on markers"""
        # Check if touching near left or right marker (within 30 pixels)
        margin = Window.width / 15
        draw_width = Window.width - 2 * margin
        center_y = Window.height / 2
        marker_touch_tolerance = 30
        
        if abs(touch.x - self.left_marker_x) < marker_touch_tolerance:
            self.dragging_marker = 'left'
            self.drag_start_x = touch.x
            touch.grab(self)
            return True
        elif abs(touch.x - self.right_marker_x) < marker_touch_tolerance:
            self.dragging_marker = 'right'
            self.drag_start_x = touch.x
            touch.grab(self)
            return True
        
        return super(LoopEditorScreen, self).on_touch_down(touch)

    def on_touch_move(self, touch):
        """Handle marker dragging"""
        if self.dragging_marker and touch.grab_current == self:
            margin = Window.width / 15
            draw_width = Window.width - 2 * margin
            
            # Update marker position
            if self.dragging_marker == 'left':
                # Keep left marker within bounds
                self.left_marker_x = max(margin, min(touch.x, self.right_marker_x - 10))
            elif self.dragging_marker == 'right':
                # Keep right marker within bounds
                self.right_marker_x = max(self.left_marker_x + 10, min(touch.x, margin + draw_width))
            
            # Redraw markers
            self._update_marker_lines()
            return True
        
        return super(LoopEditorScreen, self).on_touch_move(touch)

    def on_touch_up(self, touch):
        """Handle touch release"""
        if self.dragging_marker and touch.grab_current == self:
            touch.ungrab(self)
            self.dragging_marker = None
            return True
        
        return super(LoopEditorScreen, self).on_touch_up(touch)

    def _update_marker_lines(self):
        """Redraw the marker lines at their current positions"""
        center_y = Window.height / 2
        if self.left_marker_line:
            self.left_marker_line.points = [
                self.left_marker_x, center_y - Window.height * 0.35,
                self.left_marker_x, center_y + Window.height * 0.35
            ]
        if self.right_marker_line:
            self.right_marker_line.points = [
                self.right_marker_x, center_y - Window.height * 0.35,
                self.right_marker_x, center_y + Window.height * 0.35
            ]

    def on_resize(self, *args):
        # Update sample button position
        if self.sample_button:
            self.sample_button.pos = (Window.width / 2 - 50, Window.height - 60)
        
        # Update sizes/positions of canvas elements when window resizes
        if self.wood_rect:
            self.wood_rect.pos = (0, 0)
            self.wood_rect.size = Window.size
        if self.barn_button:
            b_size = Window.width / 8
            self.barn_button.size = (b_size, b_size)
            self.barn_button.pos = (Window.width - b_size, 0)
        if self.trash_button:
            b_size = Window.width / 8
            self.trash_button.size = (b_size, b_size)
            self.trash_button.pos = (0, 0)
        if self.barn_rect:
            self.barn_rect.pos = self.barn_button.pos
            self.barn_rect.size = self.barn_button.size
        if self.trash_rect:
            self.trash_rect.pos = self.trash_button.pos
            self.trash_rect.size = self.trash_button.size
        
        # Redraw waveform and markers on resize
        if self.waveform_points:
            width = Window.width
            margin = width / 15
            draw_width = width - 2 * margin
            center_y = Window.height / 2
            
            # Redraw waveform line
            points = []
            denom = max(1, len(self.waveform_points) - 1)
            for i, s in enumerate(self.waveform_points):
                x = margin + (i / denom) * draw_width
                y = center_y + float(s) * self.viz_scale
                points.extend([x, y])
            
            # Clear canvas and redraw everything
            self.canvas.clear()
            with self.canvas:
                Color(0, 0.8, 0, 1)
                self.waveform_line = Line(points=points, width=1.5)
                
                # Redraw 9 vertical marker lines
                Color(0, 0, 0, 0.5)  # Semi-transparent black
                for i in range(9):
                    x = margin + (i / 8) * draw_width
                    Line(points=[x, center_y - Window.height * 0.25, x, center_y + Window.height * 0.25], width=1)
                
                # Redraw left and right loop markers
                Color(1, 0, 0, 1)  # Red for loop markers
                self.left_marker_x = margin
                self.left_marker_line = Line(
                    points=[self.left_marker_x, center_y - Window.height * 0.35, self.left_marker_x, center_y + Window.height * 0.35],
                    width=2.5
                )
                self.right_marker_x = margin + draw_width
                self.right_marker_line = Line(
                    points=[self.right_marker_x, center_y - Window.height * 0.35, self.right_marker_x, center_y + Window.height * 0.35],
                    width=2.5
                )
                
                Color(1, 1, 1, 1)
                # Redraw barn texture
                try:
                    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                    # trash texture
                    trash_path = os.path.join(base_dir, "assets", "ui_images", "trash.png")
                    trash_tex = Image(source=trash_path).texture if os.path.exists(trash_path) else None
                    if trash_tex and self.trash_button:
                        self.trash_rect = Rectangle(pos=self.trash_button.pos, size=self.trash_button.size, texture=trash_tex)
                    # barn texture
                    barn_path = os.path.join(base_dir, "assets", "ui_images", "redbarn2.png")
                    barn_tex = Image(source=barn_path).texture if os.path.exists(barn_path) else None
                    if barn_tex and self.barn_button:
                        self.barn_rect = Rectangle(pos=self.barn_button.pos, size=self.barn_button.size, texture=barn_tex)
                except Exception:
                    pass
