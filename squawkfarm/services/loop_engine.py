"""Loop engine managing global tempo/meter and per-animal loops."""

from typing import Callable, Dict, List, Optional, Tuple

import librosa
import numpy as np

from imslib.audio import Audio
from imslib.mixer import Mixer
from imslib.wavegen import WaveGenerator
from imslib.wavesrc import WaveBuffer, WaveFile
from squawkfarm.models.loop import AnimalLoop, GlobalLoopSettings, LoopInstance

from imslib.clock import AudioScheduler, SimpleTempoMap, kTicksPerQuarter
from kivy.clock import Clock

from squawkfarm.utils import tune_sample_and_save, tune_to_midi, frame_to_time, time_to_frame, guess_role_from_pitch, get_recording_wav_path


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
# Loop instance on global grid
# ---------------------------------------------------------------------------
class RuntimeLoopInstance(object):
    """
    Runtime per-loop-instance data with audio buffer and muting information.

    :param data: Audio data as numpy array
    :param midi: MIDI pitch of this instance
    :param muted_ranges: List of (start_frame, end_frame) tuples indicating muted regions
    """
    def __init__(self, data: np.ndarray, midi: int, muted_ranges: list[tuple[int, int]] = []):
        super(RuntimeLoopInstance, self).__init__()
        self.muted_ranges = muted_ranges if muted_ranges else []
        self.set_buffer(data, midi)

    def mute_ranges(self) -> None:
        """Apply all stored muted ranges to the current buffer."""
        for start_frame, end_frame in self.muted_ranges:
            start_sample = start_frame
            end_sample = end_frame
            self.data[start_sample:end_sample] = 0

    def set_buffer(self, data: np.ndarray, midi: int) -> None:
        """
        Update the audio buffer for this loop instance.
        """
        self.clean_data = data.copy()
        self.data = data.copy()
        self.midi = midi
        self.num_frames = len(self.data)
        self.num_channels = 1

        self.mute_ranges()

    def toggle_mute(self, start_frame: int, end_frame: int, mute: bool) -> None:
        """
        Mute/unmute between given frames in this loop instance.
        Automatically merges overlapping ranges when muting.

        :param start_frame: Starting frame index
        :param end_frame: Ending frame index
        :param mute: True to mute, False to unmute
        """
        start_frame = max(0, start_frame)
        end_frame = min(self.num_frames, end_frame)

        if mute:
            self.data[start_frame:end_frame] = 0
            # Add and merge overlapping ranges
            self._add_muted_range(start_frame, end_frame)
        else:
            self.data[start_frame:end_frame] = self.clean_data[start_frame:end_frame]
            # Remove the range
            self._remove_muted_range(start_frame, end_frame)
    
    def get_frames(self, start_frame: int, num_frames: int) -> np.ndarray:
        """Get frames from the buffer, compatible with WaveSource interface."""
        return self.data[start_frame:start_frame + num_frames]
    
    def get_num_frames(self) -> int:
        """Get total number of frames."""
        return self.num_frames
    
    def get_num_channels(self) -> int:
        """Get number of channels."""
        return self.num_channels

    def _add_muted_range(self, start_frame: int, end_frame: int) -> None:
        """
        Add a muted range and merge with overlapping ranges.
        """
        i, overlap = 0, False
        while not overlap and i < len(self.muted_ranges):
            existing_start, existing_end = self.muted_ranges[i]
            if existing_start <= start_frame <= existing_end:
                j = i + 1
                while j < len(self.muted_ranges) and end_frame >= self.muted_ranges[j][0]:
                    j += 1
                # Merge all overlapping ranges from i to j-1
                end_frame = max(end_frame, self.muted_ranges[j - 1][1])
                self.muted_ranges[i:j] = [(existing_start, end_frame)]
                overlap = True
            else:
                i += 1

        if not overlap:
            self.muted_ranges.insert(i, (start_frame, end_frame))

    def _remove_muted_range(self, start_frame: int, end_frame: int) -> None:
        """
        Remove a muted range, splitting existing ranges if necessary.
        """
        first_index = None
        last_index = None
        for i, (existing_start, existing_end) in enumerate(self.muted_ranges):
            if first_index is None and existing_start <= start_frame <= existing_end:
                if existing_start == start_frame:
                    first_index = i
                else:
                    # keep left part by shortening this range's end
                    first_index = i + 1
                    left_start, _ = self.muted_ranges[i]
                    self.muted_ranges[i] = (left_start, start_frame)

            if first_index is not None and end_frame <= existing_start:
                last_index = i - 1
                _, right_end = self.muted_ranges[last_index]
                if right_end == end_frame:
                    # entire last range is removed
                    last_index = i
                else:
                    # keep right part by moving its start
                    self.muted_ranges[last_index] = (end_frame, right_end)
                break

        if first_index is not None:
            last_index = last_index if last_index is not None else len(self.muted_ranges)
            self.muted_ranges = self.muted_ranges[:first_index] + self.muted_ranges[last_index:]


class Recording(object):
    """
    Original recording with possible trimmed margins.
    """
    def __init__(self, audio_path: str, start_frame: int = 0, num_frames: Optional[int] = None):
        super(Recording, self).__init__()
        self.audio_path = audio_path
        wf = WaveFile(audio_path)
        self.last_frame = wf.end  # total frames in file

        self.start_frame = start_frame
        num_frames = num_frames if num_frames is not None else self.last_frame - start_frame

        self.trimmed = WaveBuffer(audio_path, self.start_frame, num_frames)

    # ------------- queries -------------
    def get_num_frames(self) -> int:
        """Return number of frames in this slice (per original file)."""
        return self.trimmed.get_num_frames()

    def get_generator(self, frame_offset: int = 0, loop: bool = False) -> WaveGenerator:
        """
        Get WaveGenerator for the trimmed recording, frame_offset into the trimmed region.
        """
        gen = WaveGenerator(self.trimmed, loop)

        gen.frame = frame_offset
        gen.set_gain(0.5)
        return gen

    # ------------- updating margins -------------
    def set_left_margin(self, start_frame: int) -> None:
        """Update the default frame range of the recording."""
        shift = start_frame - self.start_frame
        self.start_frame += shift
        num_frames = self.get_num_frames() - shift

        self.trimmed = WaveBuffer(self.audio_path, self.start_frame, num_frames)

    def set_right_margin(self, end_frame: int) -> None:
        """Update the default frame range of the recording."""
        num_frames = end_frame - self.start_frame
        self.trimmed = WaveBuffer(self.audio_path, self.start_frame, num_frames)

    def shift(self, num_frames: int) -> None:
        """
        Shift the default frame range by num_frames, clamped to file bounds.
        """
        tot = self.get_num_frames()
        new_start = self.start_frame + num_frames
        new_end = new_start + tot

        # clamp to [0, last_frame]
        if new_start < 0:
            new_start = 0
        elif new_end > self.last_frame:
            new_start = self.last_frame - tot

        self.trimmed = WaveBuffer(self.audio_path, new_start, tot)


class Loop(object):
    """
    Runtime per-animal loop.
    """
    def __init__(self, audio_data: np.ndarray, start_frame: int, num_frames: int, midi: int, volume: float, role: str, loop_instances: list[LoopInstance] = []):
        super(Loop, self).__init__()
        self.current = audio_data

        self.start_frame = start_frame # start frame within the recording
        self.num_frames = num_frames # number of frames in the trimmed recording
        self.midi = midi
        self.volume = volume
        self.role = role # "bass", "harmony", or "melody"

        self.instances: Dict[int, RuntimeLoopInstance] = {}
        for loop in loop_instances:
            shifted_data = tune_to_midi(self.current, self.midi, loop.midi)
            self.instances[loop.start_slot] = RuntimeLoopInstance(shifted_data, loop.midi, loop.muted_ranges)

    def has_instance_at_start_slot(self, slot: int) -> bool:
        """Return True if a loop instance exists at the given start slot."""
        return slot in self.instances

    def get_num_frames(self, slot: int) -> int:
        """Return number of frames in the loop instance at the given slot."""
        return self.instances[slot].num_frames

    def get_slot_ranges(self, frame_to_slot: Callable[[int], int]) -> List[Tuple[int, int]]:
        """
        Get list of (start_slot, num_slots) for all loop instances.
        """
        return [(start_slot, frame_to_slot(instance.num_frames)) for start_slot, instance in self.instances.items()]

    def get_generator(self, start_slot: int, frame_offset: int = 0, loop: bool = False) -> WaveGenerator:
        """
        Get WaveGenerator for this loop instance at start_slot.
        """
        instance = self.instances[start_slot]
        gen = WaveGenerator(instance, loop)

        gen.frame = frame_offset
        gen.set_gain(self.volume)

        return gen

    def set_volume(self, volume: float) -> None:
        """Set per-animal volume."""
        self.volume = max(0.0, min(1.0, volume))

    def set_pitch(self, start_slot: int, midi: int) -> None:
        """
        Set the pitch of the loop instance at start_slot.
        """
        shifted_data = tune_to_midi(self.current, self.midi, midi)
        self.instances[start_slot].set_buffer(shifted_data, midi)

    def toggle_mute(self, start_slot: int, frame_1: int, frame_2: int, mute: bool) -> None:
        """
        Mute/unmute between frame_1 and frame_2 of loop instance at start_slot.
        """
        if frame_1 > frame_2:
            frame_1, frame_2 = frame_2, frame_1
        self.instances[start_slot].toggle_mute(frame_1, frame_2, mute)

    def slide(
        self,
        old_start_slot: int,
        new_start_slot: int,
        frame_to_slot: Callable[[int], int],
        overlap: bool = False,
    ) -> int:
        """
        Attempt to move loop instance from old_start_slot to new_start_slot.
        If overlap is False, do not allow moving if it would overlap with another instance.
        Return the final start_slot of the instance.
        """
        if new_start_slot in self.instances:
            return old_start_slot
        elif not overlap and any(
            left_slot <= new_start_slot <= right_slot and old_start_slot != left_slot
            for left_slot, right_slot in self.get_slot_ranges(frame_to_slot)
        ):
            return old_start_slot
        else:
            self.instances[new_start_slot] = self.instances.pop(old_start_slot)
            return new_start_slot

    def add_to_grid(self, start_slot: int, midi: Optional[int] = None) -> None:
        """
        Adds loop instance at start_slot if none exists there.
        """
        if not start_slot in self.instances:
            midi = midi if midi is not None else self.midi
            shifted_data = tune_to_midi(self.current, self.midi, midi)
            self.instances[start_slot] = RuntimeLoopInstance(shifted_data, midi)

    def del_from_grid(self, start_slot: int) -> None:
        """
        Removes the loop instance at start_slot.
        """
        if start_slot in self.instances:
            del self.instances[start_slot]


class LoopEngine(object):
    """
    Manages global tempo and a set of per-animal loops.
    """
    def __init__(self, global_loop_settings: GlobalLoopSettings, animal_loops: Dict[str, AnimalLoop] = {}):
        super(LoopEngine, self).__init__()
        # rhythm
        self.measures = global_loop_settings.measures
        self.time_sig = global_loop_settings.time_sig
        self.tempo_map = SimpleTempoMap(global_loop_settings.bpm)
        self._update_settings()
        
        # melody
        self.key_mode = global_loop_settings.key_mode
        self.root = global_loop_settings.root

        # synchronization
        self.scheduler = AudioScheduler(self.tempo_map)
        self.mixer = Mixer()
        self.scheduler.set_generator(self.mixer)

        self.audio = Audio(2)
        self.audio.set_generator(self.scheduler)

        self.playing = False

        # per-animal loops
        self.loops: Dict[str, Loop] = {}
        self.bass_animals: set[str] = set()
        self.melody_animals: set[str] = set()
        self.harmony_animals: set[str] = set()
        
        for id, loop in animal_loops.items():
            audio_data, _ = librosa.load(get_recording_wav_path(id, "tuned"), sr=Audio.sample_rate)
            self.loops[id] = Loop(audio_data, loop.start_frame, loop.num_frames, loop.midi, loop.volume, loop.role, loop.instances)
            self._add_to_role_set(id, loop.role)

        self.recording: Optional[Recording] = None  # if the user is currently recording audio
        
        # Track scheduled mouth close events for each animal
        self.scheduled_close_events: Dict[str, object] = {}

    # ======================================================================
    # global loop settings
    # ======================================================================
    def get_total_measures_options(self) -> List[int]:
        """
        Call this to display drop down menu of total measures options.
        """
        return list(range(1, MAX_MEASURES + 1))

    def get_total_measures(self) -> int:
        """Return the current number of measures in the global loop."""
        return self.measures

    def set_total_measures(self, total_measures: int) -> None:
        """Set the total number of measures and update internal timing settings."""
        self.measures = total_measures
        self.beats = self.measures * self._get_beats_per_measure()
        self._update_settings()

    def get_time_signature_options(self) -> List[Tuple[int, int]]:
        """
        Call this to display drop down menu of total time signature options.
        """
        return [ts for ts in COMMON_TIME_SIGNATURES if self.beats % ts[0] == 0]

    def get_time_signature(self) -> Tuple[int, int]:
        """Return the current time signature (numerator, denominator)."""
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
        """Return the current tempo in beats per minute."""
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
    
    def get_key_mode(self) -> str:
        """Return the current key mode ('major' or 'minor')."""
        return self.key_mode
    
    def set_key_mode(self, key_mode: str) -> bool:
        """
        Returns True if set, False if there are existing loops and it cannot be changed.
        """
        if not self.loops:
            self.key_mode = key_mode
            return True
        return False
    
    def get_root(self) -> int:
        """Return the current root note (MIDI number)."""
        return self.root

    def set_root(self, root: int) -> bool:
        """
        Returns True if set, False if there are existing loops and it cannot be changed.
        """
        if not self.loops:
            self.root = root
            return True
        return False

    # ======================================================================
    # Call these when initializing grid in ui
    # ======================================================================
    def get_slots_per_measure(self) -> int:
        """Return the number of slots per measure."""
        return self._get_beats_per_measure() * self.ppb

    def get_slots_per_beat(self) -> int:
        """Return the number of slots per beat."""
        return self.ppb

    def get_total_slots(self) -> int:
        """Return the total number of slots in the full loop."""
        return self.total_slots

    def get_slot_ranges(self, animal_id: str) -> List[Tuple[int, int]]:
        """Return list of slot ranges for drawing the grid for a given animal."""
        return self.loops[animal_id].get_slot_ranges(self.frame_to_slot)

    def get_time_from_slots(self, slots: float) -> float:
        """Returns total loop time in seconds for a given number of slots."""
        total_ticks = self.slot_to_tick(slots)
        return self.scheduler.tempo_map.tick_to_time(total_ticks)

    # ======================================================================
    # Adding & deleting new loops
    # ======================================================================
    def add_animal_loop(self, animal_id: str) -> None:
        """
        Adds or updates an animal loop.
        Call this when user is finished making edits to their recording and saves it.
        """
        start_frame, num_frames = self.recording.start_frame, self.recording.get_num_frames()
        trimmed_data = self.recording.trimmed.data
        audio_data, midi = tune_sample_and_save(animal_id, trimmed_data)
        role = guess_role_from_pitch(midi, self.root)
        self.loops[animal_id] = Loop(audio_data, start_frame, num_frames, midi, 0.5, role)
        self._add_to_role_set(animal_id, role)
        self.recording = None

    def del_animal_loop(self, animal_id: str) -> None:
        """
        Deletes an animal loop from the engine.
        Call this if user deletes an animal.
        """
        if animal_id in self.loops:
            self._remove_from_role_set(animal_id, self.loops[animal_id].role)
            del self.loops[animal_id]

    # ======================================================================
    # Call these when user is about to record audio
    # ======================================================================
    def get_recording_slots(self, num_beats: int) -> float:
        """
        Get the number of slots for recording based on the number of beats.
        """
        return num_beats * self.get_slots_per_beat()

    def get_recording_slots_for_animal(self) -> int:
        """
        Get the number of slots for recording based on the original recording length of the animal.
        """
        return self.frame_to_slot(self.recording.get_num_frames())

    # ======================================================================
    # Call these after user records audio and wants to make edits
    # Each expects slots in terms of number of slots in original recording
    # ======================================================================
    def set_recording(self, animal_id: str) -> None:
        """
        Add a new recording to be edited.
        Call this after user finishes recording audio.
        """
        audio_path = get_recording_wav_path(animal_id, "raw")
        start_frame = self.loops[animal_id].start_frame if animal_id in self.loops else 0
        num_frames = self.loops[animal_id].num_frames if animal_id in self.loops else None

        self.recording = Recording(audio_path, start_frame, num_frames)

    def set_left_margin_of_recording(self, slot: int) -> None:
        """
        Set the left margin of the recorded audio.
        Call this when user clicks on left margin, drags it, and releases.
        """
        self.recording.set_left_margin(self.slot_to_frame(slot))

    def set_right_margin_of_recording(self, slot: int) -> None:
        """
        Set the right margin of the recorded audio.
        Call this when user clicks on right margin, drags it, and releases.
        """
        self.recording.set_right_margin(self.slot_to_frame(slot))

    def shift_recording(self, num_slots: float) -> None:
        """
        Shift the *default* recording margins for this animal by num_slots.
        Call this when user clicks inside margins of recording, drags left or right, and releases.

        EXPECTS:
          - Positive num_slots = later in recording, negative = earlier.
        """
        self.recording.shift(self.slot_to_frame(num_slots))

    # ======================================================================
    # Call these when user editing global loop grid
    # ======================================================================
    def add_loop_to_grid(self, animal_id: str, slot: int, midi: Optional[int] = None) -> None:
        """Adds loop instances at the specified slots."""
        self.loops[animal_id].add_to_grid(slot, midi)

    def del_loop_from_grid(self, animal_id: str, slot: int) -> None:
        """Deletes loop instances from the global grid at the specified slots."""
        self.loops.get(animal_id).del_from_grid(slot)
        
    def set_role_of_loop(self, animal_id: str, role: str) -> None:
        """
        Set the role of an animal loop.
        Call this when user changes an animal's role.
        """
        old_role = self.loops[animal_id].role
        self._remove_from_role_set(animal_id, old_role)
        self.loops[animal_id].role = role
        self._add_to_role_set(animal_id, role)
        
    def clear_loops_from_grid(self, animal_id: str) -> None:
        """Deletes all loop instances from the global grid for the specified animal."""
        loop = self.loops.get(animal_id)
        for start_slot in list(loop.instances.keys()):
            loop.del_from_grid(start_slot)

    def set_pitch_of_loop_instance(self, animal_id: str, start_slot: int, midi: int) -> None:
        """Sets/updates audio file path of loop instance at start_slot."""
        self.loops.get(animal_id).set_pitch(start_slot, midi)

    def mute_slots_of_loop_instance(
        self,
        animal_id: str,
        start_slot: int,
        slot_1: int,
        slot_2: int,
        mute: bool,
    ) -> None:
        """
        Mute/unmute between slot_1 and slot_2 of loop.
        Call this when mute button has been clicked and user clicks on a slot ot drags over numerous and releases.
        """
        frame_1, frame_2 = self.slot_to_frame(slot_1), self.slot_to_frame(slot_2)
        self.loops.get(animal_id).toggle_mute(start_slot, frame_1, frame_2, mute)
        
    def set_volume_of_loop(self, animal_id: str, volume: float) -> None:
        """
        Set per-animal volume.
        Call this when user adjusts per-animal volume slider and releases.
        """
        self.loops[animal_id].set_volume(volume)
        
    def slide_loop_instance(self, animal_id: str, old_start_slot: int, new_start_slot: int, overlap: bool = False) -> int:
        """
        Slide the loop instance from old_start_slot to new_start_slot.
        If overlap is True, will allow the loop to overlap with other loops.
        Return the final start_slot of the instance.
        """
        self.pause()
        return self.loops[animal_id].slide(old_start_slot, new_start_slot, overlap)

    # ======================================================================
    # audio scheduling
    # ======================================================================
    def get_recording_duration(self) -> float:
        """Return the default loop duration time in seconds for this animal."""
        return frame_to_time(self.recording.get_num_frames())

    def get_duration(self, loop: Loop, start_slot: int) -> float:
        """Return the loop duration time in seconds for a given loop instance."""
        return frame_to_time(loop.get_num_frames(start_slot))
    
    def get_num_slots(self, loop: Loop) -> int:
        """Return the default number of slots for a loop."""
        return self.frame_to_slot(loop.num_frames)

    def set_callbacks(self, on_sing: Callable[[str], None], on_close: Callable[[str], None]) -> None:
        """Set callback functions for when an animal starts and stops singing."""
        self._on_sing = on_sing
        self._on_close = on_close

    def on_update(self) -> None:
        """Forward update tick to the underlying audio system."""
        self.audio.on_update()

    def toggle_play_recording(self, offset: float = 0, repeat: bool = False) -> None:
        """Toggle playback of only the specified animal's default loop region."""
        if self.playing:
            self.pause()
        else:
            self.play_recording(offset, repeat)

    def play_recording(self, offset: float = 0, repeat: bool = False) -> None:
        """Play the current recording where offset is time in seconds into the loop to start playback."""
        gen = self.recording.get_generator(time_to_frame(offset), repeat)
        self.mixer.add(gen)

        self.playing = True
        if not repeat:
            end_time = self.get_recording_duration() - offset + self.scheduler.get_time()
            self.scheduler.post_at_tick(
                self.pause,
                self.tempo_map.time_to_tick(end_time),
            )

    def toggle_play(self, start_time: float = 0, loop: bool = False) -> None:
        """
        Toggle audio playback of the current loops.
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
        
        # Cancel all scheduled close events and immediately close all mouths
        for animal_id, event in self.scheduled_close_events.items():
            Clock.unschedule(event)
            self._on_close(animal_id)
        self.scheduled_close_events.clear()

    def _schedule_cycle(self, start_time: float = 0, repeat: bool = False) -> None:
        """Schedule one full pass of the loop (all animals, all sections)."""
        now = self.scheduler.get_tick()
        loop_ticks = self.slot_to_tick(self.total_slots)

        tick_offset = self.scheduler.tempo_map.time_to_tick(start_time)

        for animal_id, loop in self.loops.items():
            for start_slot, num_slots in loop.get_slot_ranges(self.frame_to_slot):
                wave_generator = None
                tick = self.slot_to_tick(start_slot)
                if tick >= tick_offset:
                    wave_generator = loop.get_generator(start_slot)
                else:
                    end_tick = tick + self.slot_to_tick(num_slots)
                    if end_tick > tick_offset:
                        local_tick_offset = tick_offset - tick
                        local_frame_offset = time_to_frame(self.tempo_map.tick_to_time(local_tick_offset))
                        wave_generator = loop.get_generator(start_slot, local_frame_offset)
                        tick += local_tick_offset

                if wave_generator is not None:
                    self.scheduler.post_at_tick(
                        self._start_section_playback,
                        tick + now,
                        (animal_id, start_slot, wave_generator),
                    )

        def callback(dt):
            if repeat:
                self._schedule_cycle(0, repeat)
            else:
                self.pause()

        self.scheduler.post_at_tick(
            callback,
            loop_ticks - tick_offset + now,
        )

    def _start_section_playback(self, _, args: Tuple[str, int, WaveGenerator]) -> None:
        """Starts playback of a section for a given animal at the current time."""
        animal_id, start_slot, gen = args
        loop: Loop = self.loops.get(animal_id)
        if not loop:
            return
        if not loop.has_instance_at_start_slot(start_slot):
            return

        self.mixer.add(gen)

        self._on_sing(animal_id)
        duration = self.get_duration(loop, start_slot)
        
        # Schedule close callback and track the event so we can cancel it on pause
        def close_callback(dt):
            self._on_close(animal_id)
            # Remove from tracking when it fires naturally
            self.scheduled_close_events.pop(animal_id, None)
        
        event = Clock.schedule_once(close_callback, duration)
        self.scheduled_close_events[animal_id] = event

    # ======================================================================
    # internal helpers
    # ======================================================================
    def _add_to_role_set(self, animal_id: str, role: str) -> None:
        """Add animal to the appropriate role set."""
        if role == "bass":
            self.bass_animals.add(animal_id)
        elif role == "melody":
            self.melody_animals.add(animal_id)
        elif role == "harmony":
            self.harmony_animals.add(animal_id)
    
    def _remove_from_role_set(self, animal_id: str, role: str) -> None:
        """Remove animal from the appropriate role set."""
        if role == "bass":
            self.bass_animals.discard(animal_id)
        elif role == "melody":
            self.melody_animals.discard(animal_id)
        elif role == "harmony":
            self.harmony_animals.discard(animal_id)
    
    def _get_beats_per_measure(self) -> int:
        """Return the number of beats per measure (time signature numerator)."""
        return self.time_sig[0]

    def _update_settings(self) -> None:
        """Recompute beat and slot settings from measures and time signature."""
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
        """Convert a grid slot index to clock ticks."""
        # 1 beat = kTicksPerQuarter
        ticks_per_slot = kTicksPerQuarter // self.ppb
        return slot * ticks_per_slot

    def slot_to_frame(self, slot: float) -> int:
        """Convert a grid slot position to an audio frame index."""
        bpm = self.tempo_map.get_tempo()
        seconds_per_slot = (60.0 / bpm) / self.ppb
        seconds = slot * seconds_per_slot
        frame = int(seconds * Audio.sample_rate)
        return frame

    def frame_to_slot(self, frame: int) -> int:
        """Convert an audio frame index to a grid slot index."""
        bpm = self.tempo_map.get_tempo()
        seconds_per_slot = (60.0 / bpm) / self.ppb
        seconds = frame / Audio.sample_rate
        slot = seconds / seconds_per_slot
        return int(slot)
