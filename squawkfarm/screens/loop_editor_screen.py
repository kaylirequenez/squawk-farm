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
from squawkfarm.services.loop_engine import Loop
from kivy.core.window import Window
from kivy.graphics import Rectangle, Color, Line
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.clock import Clock
from squawkfarm.utils import get_ui_asset_path, get_recording_wav_path, get_animal_data_dir, get_recordings_dir


class LoopEditorScreen(Screen):
    def __init__(self, **kwargs):
        super(LoopEditorScreen, self).__init__(**kwargs)
        self.wood_rect = None
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

    def on_enter(self, animal_id: str, num_slots: int):
        # Store animal information but don't load waveform
        self.animal_id = animal_id
        self.num_slots = num_slots
        self._draw_board_and_horizontal_lines()

    def on_leave(self, *args):
        # cleanup if needed
        pass

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

    def _draw_board_and_horizontal_lines(self):
        # remove previous widgets/canvas items if any
        if self.wood_rect:
            try:
                self.canvas.before.remove(self.wood_rect)
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
        woodB_path = get_ui_asset_path("woodB2.png")
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

        # compute central area for drawing lines
        width = Window.width
        margin = width / 15
        draw_width = width - 2 * margin
        center_y = Window.height / 2
        line_spacing = Window.height * 0.05  # Spacing between horizontal lines

        with self.canvas:
            Color(0, 0.8, 0, 1)  # Green color for horizontal lines
            # Draw 8 horizontal lines centered in the middle of the screen
            for i in range(8):
                # Calculate y position for each line, centered around middle of screen
                y_offset = (i - 3.5) * line_spacing  # Center around line 3.5 for 8 lines
                y = center_y + y_offset
                Line(points=[margin, y, margin + draw_width, y], width=2)
            
            # Draw 9 vertical marker lines dividing the area into 8 equal parts
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
                trash_path = get_ui_asset_path("trashcan2.png")
                trash_tex = Image(source=trash_path).texture if os.path.exists(trash_path) else None
                if trash_tex and self.trash_button:
                    self.trash_rect = Rectangle(pos=self.trash_button.pos, size=self.trash_button.size, texture=trash_tex)
            except Exception:
                pass
            try:
                barn_path = get_ui_asset_path("redbarn2.png")
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
            # Use the global LoopEngine to play this sample once via play_loop.
            engine = None
            # prefer instance-level globals if present
            if hasattr(self, 'globals') and getattr(self, 'globals'):
                engine = getattr(self, 'globals').loop_engine
            # fallback to class-level Screen.globals
            if engine is None:
                engine = type(self).globals.loop_engine

            if engine is None:
                raise Exception("LoopEngine not available in globals")

            # create a unique temporary loop id for preview
            import time
            temp_id = f"__preview__{int(time.time() * 1000)}"

            # create Loop entry for this slice
            try:
                engine.loops[temp_id] = Loop(latest, left_sample, num_frames, 1.0, 1.0)
            except Exception as e:
                print(f"Error creating temporary Loop entry: {e}")
                raise

            print(f"LoopEditor: starting preview via LoopEngine.play_loop id={temp_id} frames={num_frames} start={left_sample}")

            # Play it once using the engine
            try:
                engine.play_loop(temp_id)
            except Exception as e:
                print(f"Error during engine.play_loop: {e}")
                # cleanup temp entry on error
                try:
                    del engine.loops[temp_id]
                except Exception:
                    pass
                raise

            # Start pumping the engine audio (if not already) while preview plays
            try:
                # store the scheduled event so we can cancel it later
                if hasattr(self, '_engine_preview_event') and self._engine_preview_event:
                    try:
                        self._engine_preview_event.cancel()
                    except Exception:
                        pass
                self._engine_preview_event = Clock.schedule_interval(lambda dt: engine.on_update(), 1.0 / 60.0)
            except Exception as e:
                print(f"Error scheduling engine.on_update pump: {e}")

            # schedule cleanup of the temporary loop entry after a safe delay (duration + 1s)
            try:
                duration_sec = float(num_frames) / float(self.sample_rate) if self.sample_rate else 2.0
                def _cleanup(dt):
                    try:
                        if temp_id in engine.loops:
                            del engine.loops[temp_id]
                            print(f"LoopEditor: cleaned up preview id={temp_id}")
                    except Exception as e:
                        print(f"Error cleaning temporary preview: {e}")
                    # stop pumping engine audio
                    try:
                        if hasattr(self, '_engine_preview_event') and self._engine_preview_event:
                            self._engine_preview_event.cancel()
                            self._engine_preview_event = None
                    except Exception:
                        pass
                Clock.schedule_once(_cleanup, duration_sec + 1.0)
            except Exception as e:
                print(f"Error scheduling preview cleanup: {e}")

        except Exception as e:
            print(f"Error starting engine playback via LoopEngine.play_loop: {e}")

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
        
        # Redraw horizontal lines and markers on resize
        # Simply redraw everything using the new method
        self._draw_board_and_horizontal_lines()
