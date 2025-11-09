"""Garden (main) screen for squawk-farm."""
import os
import sounddevice as sd
import soundfile as sf
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


class GardenScreen(Screen):
    """Main farm/garden view where animals are shown and global loop settings can be adjusted."""
    def __init__(self, **kwargs):
        super(GardenScreen, self).__init__(**kwargs)
        self.num_animals = 0  # starting number of animals
        
        base_dir = os.path.dirname(__file__)
        self.farm_path = os.path.join(base_dir, "../UIelems/4x4Farm.png")
        self.sun_path = os.path.join(base_dir, "../UIelems/cutes.png")
        self.barn_path = os.path.join(base_dir, "../UIelems/redbarn2.png")
        self.woodB_path = os.path.join(base_dir, "../UIelems/woodB2.png") 

        # path from this file (squawkfarm/screens) up to project root: ../../assets/...
        self.bg_image = Image(source = self.farm_path).texture
        self.buttons = {}
        Window.clearcolor = (0.5,0.2,1,1)
        #self.sun = Image(source = self.sun_path).texture  # sun png for BPM
        self.sun = Image(source = self.sun_path, keep_data=True).texture
        print(f"Texture size: {self.sun.size}, colorfmt: {self.sun.colorfmt}, mipmap: {self.sun.mipmap}")
        self.sun_const = 9
        self.s_size = Window.height/self.sun_const
        self.barn = Image(source = self.barn_path).texture #barn png for button
        self.wood_board = Image(source = self.woodB_path).texture #wood board overlay
        self.b_size = Window.width/8
        self.bpm = 90
        self.board_visible = False  # Track if the board is showing
        
        # Audio recording settings
        self.is_recording = False
        self.audio_data = []  # Store audio chunks
        self.sample_rate = 44100  # CD quality audio
        self.channels = 1  # Mono recording
        self.recording_callback = None
        
        # Waveform visualization settings
        self.record_duration = 2.0  # Duration in seconds
        self.start_time = None
        self.waveform_points = deque(maxlen=int(self.sample_rate))  # Store up to 1 second of samples
        self.waveform_line = None
        self.update_event = None
        self.viz_scale = Window.height * 0.2  # Scale factor for visualization

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
        self.barn_rect.size = (self.b_size, self.b_size)
        self.barn_rect.pos = (Window.width - self.b_size,0)
    
    def audio_callback(self, indata, frames, time, status):
        """This is called for each audio block from the microphone"""
        if status:
            print(status)
        if self.is_recording:
            self.audio_data.append(indata.copy())
            # Add audio data points to visualization buffer
            # Take every Nth sample to reduce points and normalize the amplitude
            samples = indata[:, 0]  # Get first channel
            max_sample = np.max(np.abs(samples)) if len(samples) > 0 else 1
            # Normalize and decimate the samples
            for sample in samples[::20]:  # Take every 20th sample
                normalized_sample = float(sample) / max_sample if max_sample > 0 else 0
                self.waveform_points.append(normalized_sample)
    
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
        points_per_second = max(1, self.sample_rate // decimation)

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
    
    def start_recording(self):
        """Start recording audio from microphone"""
        self.audio_data = []  # Clear any previous recording
        self.waveform_points.clear()  # Clear visualization points
        self.is_recording = True
        self.start_time = datetime.now()
        self.record_duration = 2.0  # 2 seconds recording duration
        
        try:
            # Start the recording stream
            self.stream = sd.InputStream(
                channels=self.channels,
                samplerate=self.sample_rate,
                callback=self.audio_callback
            )
            self.stream.start()
            
            # Start waveform updates
            if self.update_event is None:
                self.update_event = Clock.schedule_interval(self.update_waveform, 1/30)  # 30 FPS
            
            # Schedule recording stop after duration
            Clock.schedule_once(lambda dt: self.stop_recording(), self.record_duration)
            
            print("Recording started...")
        except Exception as e:
            print(f"Could not start recording: {str(e)}")
    
    def stop_recording(self):
        """Stop recording and save the audio file"""
        if self.is_recording:
            self.is_recording = False
            if hasattr(self, 'stream'):
                self.stream.stop()
                self.stream.close()
            
            # Stop waveform updates
            if self.update_event:
                self.update_event.cancel()
                self.update_event = None
            
            # Clear waveform visualization
            if hasattr(self, 'waveform_line'):
                self.canvas.remove(self.waveform_line)
                self.waveform_line = None
            
            if self.audio_data:
                # Combine all audio chunks
                recorded_audio = np.concatenate(self.audio_data)
                
                # Create recordings directory in project root if it doesn't exist
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                recordings_dir = os.path.join(base_dir, 'recordings')
                os.makedirs(recordings_dir, exist_ok=True)
                
                # Generate filename with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(recordings_dir, f"recording_{timestamp}.wav")
                
                # Save the recording
                try:
                    sf.write(filename, recorded_audio, self.sample_rate)
                    print(f"Recording saved to {filename}")
                except Exception as e:
                    print(f"Error saving recording: {str(e)}")
                    # Print more detailed error information
                    import traceback
                    traceback.print_exc()
            
            self.audio_data = []  # Clear the audio data
            self.waveform_points.clear()  # Clear visualization points
    
    def on_barn_press(self, ins):
        # handler receives the button instance
        print('Barn button pressed!', ins)

        # change the sun_const to make the sun larger/smaller and recompute s_size
        if self.sun_const >= 7:
            self.sun_const -= 1
        else:
            self.sun_const = 9

        # recompute sun size and immediately update the sun rectangle
        self.s_size = Window.height / self.sun_const
        if hasattr(self, 'sun_rect'):
            self.sun_rect.size = (self.s_size, self.s_size)
            self.sun_rect.pos = (0, Window.height - self.s_size)

        # if the barn_texture is drawn in the button canvas, ensure its rect is updated too
        if hasattr(self, 'barn_rect'):
            # barn_rect is positioned relative to absolute Window coords in our setup
            self.barn_rect.size = (self.b_size, self.b_size)
            self.barn_rect.pos = (Window.width - self.b_size, 0)
        
        if self.board_visible:
            # Stop recording and remove wood board
            print("Stopping recording...")
            self.stop_recording()
            # Remove the wood board rectangle from the canvas
            if hasattr(self, 'wood_rect'):
                self.canvas.remove(self.wood_rect)
                self.wood_rect = None
            self.stop_recording()
        else: 
            # Create and add wood board rectangle
            with self.canvas:
                Color(1, 1, 1, 1)  # Set color to white to show texture properly
                self.wood_rect = Rectangle(
                    pos=(0, 0),
                    size=Window.size,
                    texture=self.wood_board
                )
                # Add waveform visualization
                Color(0, 0.8, 0, 1)  # Green color for waveform
                self.waveform_line = Line(points=[0, Window.height/2, Window.width, Window.height/2], width=1.5)
                Color(1, 1, 1, 1)  # Reset color for barn
                self.barn_rect = Rectangle(
                    pos=self.barn_button.pos,
                    size=self.barn_button.size,
                    texture=self.barn
                )
            # Start recording when board appears
            print("Starting recording...")
            self.start_recording()
                
        
        self.board_visible = not self.board_visible
    
