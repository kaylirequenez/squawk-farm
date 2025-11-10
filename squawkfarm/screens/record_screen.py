"""Screen for recording a new animal sound."""
import os
from kivy.uix.button import Button
import numpy as np
from datetime import datetime
from imslib.audio import Audio
from imslib.screen import Screen
from kivy.core.window import Window
from kivy.graphics import Rectangle, Color, Line
from kivy.clock import Clock
from collections import deque
from kivy.uix.image import Image

from imslib.writer import AudioWriter


class RecordScreen(Screen):
    """
    UI for recording with a dedicated Audio input stream,
    while showing a wood-board overlay and a simple waveform.
    """
    def __init__(self, **kwargs):
        super(RecordScreen, self).__init__(**kwargs)
        # recording state
        self.record_duration = 2.0  # seconds
        self.is_recording = False
        self.audio_writer = None
        self.record_audio = None  # separate Audio object for recording
        # Waveform visualization settings
        self.viz_scale = Window.height * 0.2  # Scale factor for visualization
        self.waveform_points = deque(maxlen=Audio.sample_rate)  # about 1 second
        self.waveform_line = None
        self.update_event = None
        
        self.wood_rect = None  # will hold the wood board rectangle
        
        # UI button
        self.record_btn = Button(
            text="Record",
            size_hint=(None, None),
            size=(140, 60),
            pos=(20, 20),
        )
        self.record_btn.bind(on_press=self._on_record_btn)
        self.add_widget(self.record_btn)
        
    def _get_ui_asset_path(self, filename):
        # Path calculation assumes the script is in squawkfarm/screens/
        base_dir = os.path.dirname(__file__)
        return os.path.join(base_dir, "../../assets/ui_images", filename)
        
    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def on_enter(self, *args):
        """
        Called when we switch to this screen.
        Creates a dedicated Audio object for recording input.
        """
        # create writer if we haven't
        if self.audio_writer is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            recordings_base = os.path.join(base_dir, "data", "recordings", "recording")
            os.makedirs(os.path.dirname(recordings_base), exist_ok=True)
            self.audio_writer = AudioWriter(recordings_base, num_channels=1)

        # Create a separate Audio object just for recording input
        if self.record_audio is None:
            def listen_func(data, num_channels):
                # write (only if writer.active)
                self.audio_writer.add_audio(data, num_channels)
                # feed viz if currently recording
                self._ingest_samples_for_viz(data, num_channels)

            self.record_audio = Audio(num_channels=1, input_func=listen_func, num_input_channels=1)

        # draw board + empty waveform if needed
        if self.wood_rect is None or self.waveform_line is None:
            self._draw_board_and_line()

        # start periodic UI updates (need to call record_audio.on_update())
        if self.update_event is None:
            self.update_event = Clock.schedule_interval(self._poll_audio, 1 / 60.0)

    def on_leave(self, *args):
        # if user backs out in the middle, stop and save
        if self.is_recording:
            self._finish_recording_and_return()

        if self.update_event is not None:
            self.update_event.cancel()
            self.update_event = None

    # ------------------------------------------------------------------
    # drawing
    # ------------------------------------------------------------------
    def on_barn_press(self, instance=None):
        # Button on_press passes the instance; accept it optionally
        self.switch_to('garden')
    
    def _draw_board_and_line(self):
        """
        Draw a full-screen wood board and an empty waveform line.
        """
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        woodB_path = self._get_ui_asset_path("woodB2.png")
        wood_tex = Image(source=woodB_path).texture 
        barn_path = self._get_ui_asset_path("redbarn2.png")
        barn = Image(source=barn_path).texture 
        b_size = Window.width/8
        

        with self.canvas.before:
            Color(1, 1, 1, 1)
            self.wood_rect = Rectangle(pos=(0, 0), size=Window.size, texture=wood_tex)
            
        self.barn_button = Button(
            size_hint=(None, None),
            size=(b_size, b_size),
            pos=(Window.width - b_size, 0),
            background_normal='',  # Remove default button background
            background_color=(1, 1, 1, 0)  # White color to show texture properly
        )
        # Bind the button press event
        self.barn_button.bind(on_press=self.on_barn_press)
        # Add the button to the widget tree so it receives touch events
        self.add_widget(self.barn_button)

        # waveform can go above board but still under widgets if you want;
        # we can also put it in canvas.after to make sure it's visible.
        with self.canvas:
            Color(0, 0.8, 0, 1)
            self.waveform_line = Line(
                points=[0, Window.height / 2, Window.width, Window.height / 2],
                width=1.5,
            )
            Color(1, 1, 1, 1)  # Reset color for barn
            self.barn_rect = Rectangle(
                    pos=self.barn_button.pos,
                    size=self.barn_button.size,
                    texture=barn
                )

    # ------------------------------------------------------------------
    # UI handlers
    # ------------------------------------------------------------------
    def _on_record_btn(self, *args):
        """
        Button toggles recording (for now we only do a 2s capture).
        """
        if not self.is_recording:
            self.start_recording()

    # ------------------------------------------------------------------
    # recording control
    # ------------------------------------------------------------------
    def start_recording(self):
        """
        Start capturing from AudioWriter for a fixed 2 seconds.
        """
        if self.is_recording:
            return

        self.is_recording = True
        self.waveform_points.clear()
        self.start_time = datetime.now()

        # start writer
        self.audio_writer.start()

        # update button text while recording
        self.record_btn.text = "Recording..."

        # auto-stop after record_duration
        Clock.schedule_once(lambda dt: self._finish_recording_and_return(), self.record_duration)

    def _finish_recording_and_return(self):
        """
        Stop writer, reset UI, and go back to the garden screen.
        """
        if self.is_recording:
            self.is_recording = False
            self.audio_writer.stop()

        # reset button
        self.record_btn.text = "Record"

        # optional: reset waveform to flat line
        if self.waveform_line is not None:
            self.waveform_line.points = [0, Window.height / 2, Window.width, Window.height / 2]

        # go back to garden
        if self.manager:
            self.switch_to('loop')

    # ------------------------------------------------------------------
    # audio → waveform
    # ------------------------------------------------------------------
    def _poll_audio(self, dt):
        """
        Called every frame to:
        1. Poll the recording Audio object for input
        2. Update the waveform visualization
        """
        # Poll the recording audio for microphone input
        if self.record_audio:
            self.record_audio.on_update()
        
        # Update waveform display
        self.update_waveform(dt)
    
    def _ingest_samples_for_viz(self, data, num_channels: int):
        """
        Take incoming interleaved audio from global Audio, decimate, and store
        for drawing. Only do this while recording.
        """
        if not self.is_recording:
            return

        # take left channel
        if num_channels > 1:
            samples = data[0::num_channels]
        else:
            samples = data

        stride = 20
        max_sample = np.max(np.abs(samples)) if samples.size else 1.0
        if max_sample == 0:
            max_sample = 1.0

        for sample in samples[::stride]:
            self.waveform_points.append(float(sample) / max_sample)
        
    def update_waveform(self, dt):
        """Update the waveform visualization.

        Draws the most recent captured samples left-to-right over the configured
        record_duration. The audio callback decimates samples (every 20th), so
        we compute points-per-second accordingly when mapping time -> samples.
        """
        if not self.is_recording or not hasattr(self, 'waveform_line'):
            return

        # Need at least two points to draw a line
        if len(self.waveform_points) < 2:
            return
        
        # elapsed time since recording started
        elapsed = (datetime.now() - self.start_time).total_seconds()
        progress = min(1.0, elapsed / self.record_duration)

        width = Window.width
        center_y = Window.height / 2
        max_width = width * progress  # grows from 0 -> width over record_duration

        # audio_callback appends every 20th sample. Compute points collected per second.
        decimation = 20
        points_per_second = max(1, Audio.sample_rate // decimation)

        # How many points should be visible at this elapsed time
        samples_to_show = min(len(self.waveform_points), int(points_per_second * elapsed))
        if samples_to_show < 2:
            return

        samples = list(self.waveform_points)[-samples_to_show:]

        points = []
        # Map samples to x positions within current max_width so the waveform grows
        # left-to-right as elapsed increases.
        denom = max(1, samples_to_show - 1)
        for i, sample in enumerate(samples):
            x = (i / denom) * max_width
            y = center_y + (float(sample) * self.viz_scale)
            points.extend([x, y])

        # If we're at full progress (2s) and we have more samples than fit the width,
        # show the most recent samples across the full width (scrolling window could be
        # implemented later).
        if progress >= 1.0 and len(points) == 0:
            return

        self.waveform_line.points = points
    

    
   
