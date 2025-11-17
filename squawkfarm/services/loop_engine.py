"""Loop engine managing global tempo/meter and per-animal loops."""

from typing import Callable, Dict, List, Optional, Tuple

from imslib.audio import Audio
from imslib.mixer import Mixer
from imslib.wavegen import WaveGenerator
from imslib.wavesrc import WaveBuffer, WaveFile
from squawkfarm.models.loop import AnimalLoop, GlobalLoopSettings

from imslib.clock import AudioScheduler, SimpleTempoMap, kTicksPerQuarter
from kivy.clock import Clock

from squawkfarm.utils import frame_to_time, time_to_frame


MAX_MEASURES = 4
MIN_BPM = 60
MAX_BPM = 120

COMMON_TIME_SIGNATURES = [
    # simple duple
    (2, 4), (2, 2),
    # simple triple
    (3, 8), (3, 4), (3, 2),
    # simple quadruple
    (4, 8), (4, 4), (4, 2),
    # compound duple
    (6, 8), (6, 4),
    # compound triple
    (9, 8), (9, 4),
    # compound quadruple
    (12, 8), (12, 4),
]

# ---------------------------------------------------------------------------
# Per-animal loop
# ---------------------------------------------------------------------------
class Loop(object):
    """
    Runtime per-animal loop.
    """
    def __init__(self, audio_path: str, start_frame: Optional[int] = None, num_frames: Optional[int] = None, audio_data: Optional[list[float]] = None, volume: Optional[float] = None, pitch_shift: Optional[float] = None, start_slots: List[int] = []):
        super(Loop, self).__init__()
        self.update_recording(audio_path, start_frame, num_frames, audio_data)

        self.start_slots = set(start_slots)

        self.volume = volume if volume is not None else 0.5
        self.pitch_shift = pitch_shift if pitch_shift is not None else 1

    # ------------- queries -------------
    def get_start_slots(self) -> List[int]:
        """Return list of start slots for drawing the grid."""
        return list(self.start_slots)
    
    def get_frame_offset(self) -> int:
        """Return the local start frame of this slice (per original file)."""
        return self.local_start_frame

    def get_num_frames(self) -> int:
        """Return number of frames in this slice (per original file)."""
        return self.buffer.get_num_frames()

    # ------------- loop slice -------------
    def update_recording(self, audio_path: str, start_frame: Optional[int] = None, num_frames: Optional[int] = None, audio_data: Optional[list[float]] = None) -> None:
        """
        Change the audio file path of the recording.
        """
        self.audio_path = audio_path
        self.wf = WaveFile(audio_path)
        self.last_frame = self.wf.end  # total frames in the new file
        
        self.local_start_frame = start_frame if start_frame is not None else 0
        self.buffer = WaveBuffer(audio_path, self.local_start_frame, num_frames or self.last_frame - self.local_start_frame)
        
        if audio_data:
            self.buffer.data = audio_data

    def get_slice(self, frame_offset: Optional[int] = None, loop: bool = False) -> WaveGenerator:
        """Get WaveGenerator for this loop."""
        if frame_offset is not None:
            self.buffer.frame = frame_offset
        return WaveGenerator(self.buffer, loop)
    
    def set_left_margin(self, start_frame: int) -> None:
        """Update the default frame range of the recording."""
        shift = start_frame - self.local_start_frame
        self.local_start_frame += shift
        num_frames = self.get_num_frames() - shift

        self.buffer = WaveBuffer(self.audio_path, self.local_start_frame, num_frames)

    def set_right_margin(self, end_frame: int) -> None:
        """Update the default frame range of the recording."""
        num_frames = end_frame - self.local_start_frame
        self.buffer = WaveBuffer(self.audio_path, self.local_start_frame, num_frames)

    def shift(self, num_frames) -> None:
        """ 
        Shift the default frame range by num_frames, clamped to file bounds.
        """
        tot = self.get_num_frames()
        new_start = self.local_start_frame + num_frames
        new_end = new_start + tot
        
        # clamp to [0, last_frame]
        if new_start < 0:
            new_start = 0
        elif new_end > self.last_frame:
            new_start = self.last_frame - tot

        self.buffer = WaveBuffer(self.audio_path, new_start, tot)
        
    def set_volume(self, volume: float) -> None:
        """Set per-animal volume."""
        self.volume = max(0.0, min(1.0, volume))
        
    def set_pitch_shift(self, pitch_shift: float) -> None:
        """Set per-animal pitch shift in semitones."""
        self.pitch_shift = pitch_shift
        
    # ------------- individual loop instances -------------
    def add_to_grid(self, start_slot: int) -> None:
        """
        Adds a new loop instance at start_slot.
        """
        self.start_slots.add(start_slot)

    def del_from_grid(self, start_slot: int) -> None:
        """
        Removes the loop instance at start_slot.
        """
        if start_slot in self.start_slots:
            self.start_slots.remove(start_slot)

    def toggle_mute(self, frame_1: int, frame_2: int, mute: bool) -> None:
        """
        Mute/unmute between frame_1 and frame_2 recording/trimming grid.
        """
        # ensure frame_1 <= frame_2
        if frame_1 > frame_2:
            frame_1, frame_2 = frame_2, frame_1
            
        start_frame = max(0, start_frame)
        end_frame = min(self.get_num_frames(), end_frame)

        if mute:
            self.buffer.mute_frames(start_frame, end_frame)
        else:
            self.buffer.unmute_frames(start_frame, end_frame)

class LoopEngine(object):
    """
    Manages global tempo and a set of per-animal loops.
    """
    def __init__(self, globalLoopSettings: GlobalLoopSettings, animalLoops: Dict[str, AnimalLoop] = {}):
        super(LoopEngine, self).__init__()
        # loop settings
        self.measures = globalLoopSettings.measures
        self.time_sig = globalLoopSettings.time_sig
        self.tempo_map = SimpleTempoMap(globalLoopSettings.bpm)
        self._update_settings()
        
        # synchronization
        self.scheduler = AudioScheduler(self.tempo_map)
        self.mixer = Mixer()
        self.scheduler.set_generator(self.mixer)
        
        self.audio = Audio(2)
        self.audio.set_generator(self.scheduler)
        
        self.playing = False
        
        # per-animal loops
        self.loops = {id: Loop(loop.audio_path, loop.start_frame, loop.num_frames, loop.audio_data, loop.volume, loop.pitch_shift, loop.start_slots) for id, loop in animalLoops.items()}
        
        # TO DO
        # Review chosen slots to show & max number of measures w/ different time signatures.
            
    # ======================================================================
    # global loop settings
    # ======================================================================
    def get_total_measures_options(self) -> List[int]:
        """
        Call this to display drop down menu of total measures options.
        """
        return list(range(1, MAX_MEASURES + 1))
    
    def get_total_measures(self) -> int:
        return self.measures
    
    def set_total_measures(self, total_measures: int) -> None:
        self.measures = total_measures
        self.beats = self.measures * self._get_beats_per_measure()
        self._update_settings()
    
    def get_time_signature_options(self) -> List[Tuple[int, int]]:
        """
        Call this to display drop down menu of total time signature options.
        """
        return [ts for ts in COMMON_TIME_SIGNATURES if self.beats % ts[0] == 0]

    def get_time_signature(self) -> Tuple[int, int]:
        return self.time_sig

    def set_time_signature(self, time_sig: Tuple[int, int]) -> bool:
        """
        Returns True if set, False if there are existing loops and it cannot be changed.
        """
        if not self.loops:
            self.time_sig = time_sig
            self._update_settings()
            return True
        return False
    
    def get_bpm(self) -> int:
        return self.tempo_map.get_tempo()
    
    def set_bpm(self, bpm: int) -> bool:
        """
        Returns True if set, False if there are existing loops and it cannot be changed.
        """
        if not self.loops:
            bpm = max(MIN_BPM, min(MAX_BPM, bpm))
            self.tempo_map.set_tempo(bpm, self.scheduler.get_time())
            return True
        return False
    
    # ======================================================================
    # Call these when initializing grid in ui
    # ======================================================================
    def get_slots_per_measure(self) -> int:
        return self._get_beats_per_measure() * self.ppb
    
    def get_slots_per_beat(self) -> int:
        return self.ppb
    
    def get_slots_per_sub_beat(self) -> int:
        return 2
    
    def get_total_slots(self) -> int:
        return self.total_slots

    def get_start_slots(self, animal_id: str) -> List[int]:
        """Return list of start slots for drawing the grid."""
        return self.loops[animal_id].get_start_slots()

    def get_time_from_slots(self, slots: float) -> float:
        """Returns total loop time in seconds."""
        total_ticks = self.slot_to_tick(slots)
        return self.scheduler.tempo_map.tick_to_time(total_ticks)
    
    # ======================================================================
    # Adding & deleting new loops
    # ======================================================================
    def add_or_update_animal_loop(self, animal_id: str, audio_path: str) -> None:
        """
        Adds or updates an animal loop.
        Call this as soon as user records audio.
        """
        try:
            if animal_id in self.loops:
                self.loops[animal_id].update_recording(audio_path)
            else:
                self.loops[animal_id] = Loop(audio_path)
        except Exception as e:
            print(f"Error adding/updating animal loop for {animal_id}: {e}")

    def del_animal_loop(self, animal_id: str) -> None:
        """
        Deletes an animal loop from the engine.
        Call this if user records audio and deletes it or deletes an animal.
        """
        del self.loops[animal_id]
        
    # ======================================================================
    # Call these when user is about to record audio
    # ======================================================================
    def get_recording_slots(self, unit: str) -> float:
        """
        Get the number of slots for recording based on the unit.
        """
        if unit == "measure":
            return self.get_slots_per_measure()
        elif unit == "beat":
            return self.get_slots_per_beat()
        elif unit == "sub_beat":
            return self.get_slots_per_sub_beat()
    
    # ======================================================================
    # Call these after user records audio and wants to make edits
    # Each expects slots in terms of number of slots in original recording
    # ======================================================================
    def set_left_margin_of_recording(self, animal_id: str, slot: int) -> None:
        """
        Set the left margin of the recorded audio. 
        Call this when user clicks on left margin, drags it, and releases.
        """
        loop = self.loops[animal_id]
        loop.set_left_margin(self.slot_to_frame(slot))
        
    def set_right_margin_of_recording(self, animal_id: str, slot: int) -> None:
        """
        Set the right margin of the recorded audio. 
        Call this when user clicks on right margin, drags it, and releases.
        """
        loop = self.loops[animal_id]
        loop.set_right_margin(self.slot_to_frame(slot))
        
    def shift_recording(self, animal_id: str, num_slots: float) -> None:
        """
        Shift the *default* recording margins for this animal by num_slots.
        Call this when user clicks inside margins of recording, drags left or right, and releases.

        EXPECTS:
          - Positive num_slots = later in recording, negative = earlier.
        """
        loop = self.loops[animal_id]
        shift_frames = self.slot_to_frame(num_slots)
        loop.shift(shift_frames)
        
    def mute_slots(self, animal_id: str, slot_1: int, slot_2: int, mute: bool) -> None:
        """
        Mute/unmute between slot_1 and slot_2 of loop.
        Call this when mute button has been clicked and user clicks on a slot ot drags over numerous and releases. 
        """
        loop = self.loops[animal_id]
        frame_1, frame_2 = self.slot_to_frame(slot_1), self.slot_to_frame(slot_2)
        loop.toggle_mute(frame_1, frame_2, mute)

    def set_volume_of_recording(self, animal_id: str, volume: float) -> None:
        """
        Set per-animal volume.
        Call this when user adjusts per-animal volume slider and releases.
        """
        loop = self.loops[animal_id]
        loop.set_volume(volume)
        
    def set_pitch_shift_of_recording(self, animal_id: str, pitch_shift: float) -> None:
        """
        Set per-animal pitch shift in semitones.
        Call this when user adjusts per-animal pitch shift slider and releases.
        """
        loop = self.loops[animal_id]
        loop.set_pitch_shift(pitch_shift)
    
    # ======================================================================
    # Call these when user editing global loop grid
    # ======================================================================
    def add_loop_to_grid(self, animal_id: str, slots: list[int]) -> None:
        """Adds loop instances at the specified slots."""
        try:
            loop = self.loops[animal_id]
            for start_slot in slots:
                loop.add_to_grid(start_slot)
        except KeyError:
            print(f"Warning: Animal {animal_id} not found in loops when adding to grid")
        except Exception as e:
            print(f"Error adding loop to grid for animal {animal_id}: {e}")
    
    def del_loop_from_grid(self, animal_id: str, slots: list[int]) -> None:
        """Deletes loop instances from the global grid at the specified slots."""
        loop = self.loops.get(animal_id)
        for start_slot in slots:
            loop.del_from_grid(start_slot)

    # ======================================================================
    # audio scheduling
    # ======================================================================  
    def get_loop_offset(self, animal_id: str) -> float:
        """Return the default loop offset time in seconds for this animal."""
        try:
            return frame_to_time(self.loops.get(animal_id).get_frame_offset())
        except (KeyError, AttributeError):
            print(f"Warning: Could not get loop offset for animal {animal_id}, returning 0")
            return 0.0
    
    def get_loop_duration(self, animal_id: str) -> float:
        """Return the default loop duration time in seconds for this animal."""
        try:
            return frame_to_time(self.loops.get(animal_id).get_num_frames())
        except (KeyError, AttributeError):
            print(f"Warning: Could not get loop duration for animal {animal_id}, returning 0")
            return 0.0
    
    def set_callbacks(self, on_sing: Callable[[str], None], on_close: Callable[[str], None]) -> None: 
        self._on_sing = on_sing
        self._on_close = on_close
        
    def on_update(self) -> None:
        self.audio.on_update()
        
    def toggle_play_loop(self, animal_id: str, start_time: float = 0, repeat: bool = False) -> None:
        """Toggle playback of only the specified animal's default loop region."""
        if self.playing:
            self.pause()
        else:
            self.play_loop(animal_id, start_time, repeat)
        
    # TODO: Add pausing as well & optional start time
    def play_loop(self, animal_id: str, offset: float = 0, repeat: bool = False) -> None:
        """Play only the specified animal's default loop region once where offset is time in seconds into the loop to start playback."""
        loop = self.loops.get(animal_id)
        
        gen = loop.get_slice(time_to_frame(offset), repeat)
        gen.set_gain(loop.volume)
        # TODO: apply pitch shift if/when implemented in WaveGenerator or a wrapper
        self.mixer.add(gen)
        
        self.playing = True
        if not repeat:
            end_time = self.get_loop_duration(animal_id) - offset + self.scheduler.get_time()
            self.scheduler.post_at_tick(
                        self.pause,
                        self.tempo_map.time_to_tick(end_time)
                    )
        
    def toggle_play(self, start_time: float = 0, loop: bool = False) -> None:
        """Toggle audio playback of the current loops. 
        If loop=True, will continuously loop.
        start_time specifies the time offset into the loop to begin playback.
        """
        if self.playing:
            self.pause()
        else:
            self.play(start_time, loop)

    def play(self, start_time: float = 0, loop: bool = False) -> None:
        """Start audio playback of the current loops."""
        self.playing = True
        self._schedule_cycle(start_time, loop)

    def pause(self, tick: Optional[int] = None) -> None:
        """Stops audio playback immediately."""
        self.scheduler.commands.clear()
        self.mixer.generators.clear()
        self.playing = False
        
    def _schedule_cycle(self, start_time: float = 0, repeat: bool = False) -> None:
        """Schedule one full pass of the loop (all animals, all sections)."""
        now = self.scheduler.get_tick()
        loop_ticks = self.slot_to_tick(self.total_slots)
        
        tick_offset = self.scheduler.tempo_map.time_to_tick(start_time) 

        for animal_id, loop in self.loops.items():
            for start_slot in loop.get_start_slots():
                wave_generator = None
                tick = self.slot_to_tick(start_slot) 
                if tick >= tick_offset:
                    wave_generator = loop.get_slice()
                else:
                    end_tick = tick + self.tempo_map.time_to_tick(loop.get_loop_duration(animal_id))
                    if end_tick > tick_offset:
                        local_tick_offset = tick_offset - tick
                        local_frame_offset = time_to_frame(self.tempo_map.tick_to_time(local_tick_offset))  
                        wave_generator = loop.get_slice(local_frame_offset)
                        tick += local_tick_offset
                    
                if wave_generator is not None:
                    self.scheduler.post_at_tick(
                        self._start_section_playback,
                        tick + now,
                        (animal_id, start_slot, wave_generator)
                    )
        
        def callback(dt):
            if repeat:
                self._schedule_cycle(0, repeat)
            else:
                self.pause()
        
        self.scheduler.post_at_tick(
                        callback,
                        loop_ticks - tick_offset + now
                    )

    def _start_section_playback(self, _, args: Tuple[str, int, WaveGenerator]) -> None:
        """Starts playback of a section for a given animal at the current time."""
        animal_id, start_slot, gen = args
        loop: Loop = self.loops.get(animal_id)
        if not loop:
            return
        if not start_slot in loop.start_slots:
            return

        # per-animal volume
        gen.set_gain(loop.volume)
        # TODO: pitch shift
        self.mixer.add(gen)
        
        self._on_sing(animal_id)
        duration = self.get_loop_duration(animal_id)
        Clock.schedule_once(lambda dt: self._on_close(animal_id), duration)

    # ======================================================================
    # internal helpers
    # ======================================================================
    def _get_beats_per_measure(self) -> int:
        return self.time_sig[0]
    
    def _update_settings(self) -> None:
        self.beats = self.measures * self._get_beats_per_measure()
        self._set_ppb()
        self.total_slots = self.beats * self.ppb

    def _set_ppb(self) -> None:
        """Sets pulses-per-beat based on numerator (simple vs compound)."""
        if self._get_beats_per_measure() in (6, 9, 12):
            self.ppb = 6
        else:
            self.ppb = 4
        
    def slot_to_tick(self, slot: int) -> int:
        # 1 beat = kTicksPerQuarter
        ticks_per_slot = kTicksPerQuarter // self.ppb
        return slot * ticks_per_slot
            
    def slot_to_frame(self, slot: float) -> int:
        bpm = self.tempo_map.get_tempo()
        seconds_per_slot = (60.0 / bpm) / self.ppb
        seconds = slot * seconds_per_slot
        frame = int(seconds * Audio.sample_rate)
        return frame

    def frame_to_slot(self, frame: int) -> int:
        bpm = self.tempo_map.get_tempo()
        seconds_per_slot = (60.0 / bpm) / self.ppb
        seconds = frame / Audio.sample_rate
        slot = seconds / seconds_per_slot
        return int(slot)