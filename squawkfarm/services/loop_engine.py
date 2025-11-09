"""Loop engine managing global tempo/meter and per-animal loops."""

from typing import Callable, Dict, List, Optional, Tuple

from imslib.audio import Audio
from imslib.mixer import Mixer
from imslib.wavegen import WaveGenerator
from imslib.wavesrc import WaveBuffer, WaveFile
from squawkfarm.models.loop import AnimalLoop, AnimalLoopSection, GlobalLoopSettings, LoopSection

from imslib.clock import AudioScheduler, SimpleTempoMap, kTicksPerQuarter, Clock, Scheduler


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
# Runtime section – what the engine actually plays/edits
# sections can overlap other sections but cannot have the same start slot
# ---------------------------------------------------------------------------
class RuntimeLoopSection(object):
    def __init__(self, local_start_frame: int, audio: WaveBuffer):
        """
        Runtime slice of the original audio.

        - local_start_frame: frame index in the ORIGINAL file where this slice begins
        - audio: WaveBuffer that already contains JUST this slice
        """
        super(RuntimeLoopSection, self).__init__()
        self.local_start_frame = local_start_frame
        self.audio = audio
    
    # -------- basic getters --------
    def get_num_frames(self):
        """Return number of frames in this slice (per original file)."""
        return self.audio.get_num_frames()
    
    def get_local_end_frame(self):
        """Return the end frame (per original file)."""
        return self.local_start_frame + self.get_num_frames()
    
    def get_wave_generator(self, frame: int = 0) -> WaveGenerator:
        """
        Returns a WaveGenerator for the section starting at frame
        """
        gen = WaveGenerator(self.audio) 
        gen.frame = frame 
            
        return gen
    
    # -------- editing --------
    def set_audio(self, audio: WaveBuffer, new_start_frame: Optional[int] = None) -> None:
        """Replace the underlying WaveBuffer (used when changing slice).""" 
        self.audio = audio
        if new_start_frame is not None:
            self.local_start_frame = new_start_frame

    def mute_region(self, start_frame: int, end_frame: int, mute: bool) -> None:
        """ Mute/unmute from from start_frame to end_frame (per this section)."""
        start_frame = max(0, start_frame)
        end_frame = min(self.get_num_frames(), end_frame)

        if mute:
            self.audio.mute_frames(start_frame, end_frame)
        else:
            self.audio.unmute_frames(start_frame, end_frame)

# ---------------------------------------------------------------------------
# Per-animal loop: owns runtime sections, keyed by start_slot
# ---------------------------------------------------------------------------
class Loop(object):
    """
    Runtime per-animal loop.
    Keeps sections in {start_slot: RuntimeLoopSection}.
    """
    def __init__(self, audio_path: str, start_frame: Optional[int], num_frames: Optional[int], volume: Optional[float], pitch_shift: Optional[float], sections: List[AnimalLoopSection] = []):
        super(Loop, self).__init__()
        self.audio_path = audio_path
        self.last_frame = WaveFile(self.audio_path).end # total frames in the original file

        # default “recording region” chosen by user
        self.default_start_frame = start_frame if start_frame is not None else 0
        self.default_num_frames = num_frames if num_frames is not None else self.last_frame

        self.volume = volume if volume is not None else 0.5
        self.pitch_shift = pitch_shift if pitch_shift is not None else 1

        # {start_slot: RuntimeLoopSection}
        self.sections: Dict[int, RuntimeLoopSection] = {}
        for section in sections:
            # model section is already in frames
            start_frame = section.start_frame
            num_frames = section.num_frames
            buf = WaveBuffer(self.audio_path, start_frame, num_frames)
            buf.data = section.audio_data
            self.sections[section.start_slot] = RuntimeLoopSection(
                start_frame,
                buf,
            )

    # ------------- queries -------------
    def get_sections(self, frame_to_slot: Callable[[int], int]) -> Dict[int, int]:
        """
        Returns:
            {start_slot: end_slot} for drawing the grid.
        """
        return {start_slot: frame_to_slot(section.get_num_frames()) + start_slot for start_slot, section in self.sections.items()}

    # ------------- default loop section -------------
    def set_left_margin(self, start_frame: int) -> None:
        """Update the default frame range of the recording."""
        shift = start_frame - self.default_start_frame
        self.default_start_frame += shift
        self.default_num_frames -= shift

    def set_right_margin(self, end_frame: int) -> None:
        """Update the default frame range of the recording."""
        self.default_num_frames = end_frame - self.default_start_frame
        
    def shift(self, num_frames) -> None:
        """ 
        Shift the default frame range by num_frames, clamped to file bounds.
        """
        new_start = self.default_start_frame + num_frames
        new_end = new_start + self.default_num_frames
        
        # clamp to [0, last_frame]
        if new_start < 0:
            new_end -= new_start  # shift right
            new_start = 0
        if new_end > self.last_frame:
            diff = new_end - self.last_frame
            new_start -= diff
            new_end = self.last_frame
            if new_start < 0:
                new_start = 0

        self.default_start_frame = new_start
        self.default_num_frames = new_end - new_start
        
    def set_volume(self, volume: float) -> None:
        """Set per-animal volume."""
        self.volume = max(0.0, min(1.0, volume))
        
    def set_pitch_shift(self, pitch_shift: float) -> None:
        """Set per-animal pitch shift in semitones."""
        self.pitch_shift = pitch_shift
        
    # ------------- individual loop sections -------------
    def add_section(self, start_slot: int) -> bool:
        """
        Adds a new loop section at start_slot using the default frame region.

        Returns:
            True if added, False if a section already exists at that slot.
        """
        if start_slot in self.sections:
            return False

        audio = WaveBuffer(self.audio_path, self.default_start_frame, self.default_num_frames)
        self.sections[start_slot] = RuntimeLoopSection(self.default_start_frame, audio)
        return True

    def toggle_mute(self, start_slot: int, slot_1: int, slot_2: int, slot_to_frame: Callable[[int], int], mute: bool) -> None:
        """
        Mute/unmute the section that starts at start_slot, between slot_1 and slot_2 on global loop grid.
        """
        section: RuntimeLoopSection = self.sections.get(start_slot)
        
        # ensure slot_1 <= slot_2
        if slot_1 > slot_2:
            slot_1, slot_2 = slot_2, slot_1
            
        local_slot_1 = slot_1 - start_slot
        local_slot_2 = slot_2 - start_slot

        start_frame = slot_to_frame(local_slot_1)
        end_frame = slot_to_frame(local_slot_2)

        section.mute_region(start_frame, end_frame, mute)

    def extend_start(self, old_start_slot: int, new_start_slot: int, slot_to_frame: Callable[[int], int]) -> None:
        """Extend a section to the left (earlier in audio)."""
        if not new_start_slot in self.sections:
            section: RuntimeLoopSection = self.sections.get(old_start_slot)

            frame_shift = slot_to_frame(old_start_slot - new_start_slot)
            if frame_shift < section.local_start_frame:
                new_start_frame = section.local_start_frame - frame_shift
                new_num_frames = section.get_num_frames() + frame_shift
                
                section.set_audio(WaveBuffer(self.audio_path, new_start_frame, new_num_frames), new_start_frame)
                
                self.sections[new_start_slot] = self.sections.pop(old_start_slot)

    def extend_end(self, start_slot: int, new_end_slot: int, slot_to_frame: Callable[[int], int]) -> None:
        """Extend a section to the right (later in audio)."""
        section: RuntimeLoopSection = self.sections.get(start_slot)

        local_end_frame = section.get_local_end_frame()
        frame_shift = slot_to_frame(new_end_slot) - local_end_frame
        if local_end_frame + frame_shift <= self.last_frame:
            section.set_audio(WaveBuffer(self.audio_path, section.local_start_frame, section.get_num_frames() + frame_shift))

    def get_min_start_slot(self, start_slot: int, frame_to_slot: Callable[[int], int]) -> int:
        """
        How far left can this section go, in slots (based on how many frames we have BEFORE it).
        """
        section: RuntimeLoopSection = self.sections[start_slot]
        slots_left = frame_to_slot(section.local_start_frame)
        return start_slot - slots_left

    def get_max_end_slot(self, start_slot: int, frame_to_slot: Callable[[int], int]) -> int:
        """
        How far right can this section go, in slots (based on how many frames we have AFTER it).
        """
        section: RuntimeLoopSection = self.sections[start_slot]

        frames_right = self.last_frame - section.get_local_end_frame()
        slots_right = frame_to_slot(frames_right)

        # current length in slots
        curr_len_slots = frame_to_slot(section.get_num_frames())
        return start_slot + curr_len_slots + slots_right

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
        
        # per-animal loops
        self.loops = {id: Loop(loop.audio_path, loop.start_frame, loop.num_frames, loop.volume, loop.pitch_shift, loop.sections) for id, loop in animalLoops.items()}
        
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
    def get_total_slots_info(self) -> dict:
        """
        Returns {
            "measures": list of which slots to mark as measure starts,
            "beats": list of which slots to mark as beat starts,
            "sub_beats": list of which slots to mark as sub-beat starts,
            "total": the total number of slots,
        }

        where one slot is equal to one pulse and there are 
            - 6 pulses per beat for simple meters
            - 4 pulses per beat for compound meters
        """
        return self.slots
    
    def get_sections(self, animal_id: str) -> Dict[int, int]:
        """Returns {start_slot: end_slot} for this animal."""
        return self.loops[animal_id].get_sections()
    
    def get_total_loop_time(self) -> float:
        """Returns total loop time in seconds."""
        total_ticks = self.slot_to_tick(self.slots["total"])
        return self.scheduler.tempo_map.tick_to_time(total_ticks)
    
    # ======================================================================
    # Adding & deleting new loops
    # ======================================================================
    def add_animal_loop(self, animal_id: str, audio_path: str) -> None:
        """
        Adds a new animal loop to the engine.
        Call this as soon as user records audio before animal generation occurs.
        """
        self.loops[animal_id] = Loop(audio_path)
        
    def del_animal_loop(self, animal_id: str) -> None:
        """
        Deletes an animal loop from the engine.
        Call this if user records audio and deletes it or deletes an animal.
        """
        del self.loops[animal_id]
    
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
        
    def shift_recording(self, animal_id: str, fraction_of_slot: float) -> None:
        """
        Shift the *default* recording margins for this animal by a fraction of a slot.
        Call this when user clicks inside margins of recording, drags left or right, and releases.

        EXPECTS:
          - fraction_of_slots in [-1, 1]
          - Positive fraction = later in recording, negative = earlier.
        """
        loop = self.loops[animal_id]
        shift_frames = self.slot_to_frame(fraction_of_slot)
        loop.shift(shift_frames)
        
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
    # Call these when user is editing individual sections of the animal loop
    # that they have added to the global loop grid
    # Each expects slots in terms of number of slots in global loop
    # ======================================================================
    def add_section(self, animal_id: str, start_slot: int) -> bool:
        """
        Add a new section for this animal at start_slot, using that animal's default frame region.
        """
        loop = self.loops[animal_id]
        return loop.add_section(start_slot)
    
    def del_section(self, animal_id: str, section_start: int) -> None:
        """Deletes a loop section."""
        loop = self.loops.get(animal_id)
        del loop.sections[section_start]

    # these are less relevant
    def extend_start_of_section(self, animal_id: str, old_start_slot: int, new_start_slot: int) -> None:
        """
        Change where in the recording this section starts, changing which slot it starts at.
        Call this when user drags left margin of individual section & releases.
        
        EXPECTS
          - new_start_slot >= get_min_start_slot_of_section()
        """
        loop = self.loops[animal_id]
        loop.extend_start(old_start_slot, new_start_slot, self.slot_to_frame)

    def extend_end_of_section(self, animal_id: str, start_slot: int, new_end_slot: int) -> None:
        """
        Change where in the recording this section ends, changing which slot it ends at.
        Call this when user drags right margin of individual section & releases.
        
        EXPECTS
          - new_end_slot <= get_max_end_slot_of_section()
        """
        loop = self.loops[animal_id]
        loop.extend_end(start_slot, new_end_slot, self.slot_to_frame)
        
    def get_min_start_slot_of_section(self, animal_id: str, start_slot: int) -> int:
        """
        How far left (in slots) can this audio section go for this animal?
        Based on distance between start of recording and left margin.
        """
        loop = self.loops.get(animal_id)
        min_start_slot = loop.get_min_start_slot(start_slot, self.frame_to_slot)

        # can't extend beyond slot 0
        return max(0, min_start_slot)

    def get_max_end_slot_of_section(self, animal_id: str, start_slot: int) -> int:
        """
        How far right (in slots) can this audio section go for this animal?
        Based on distance between end of recording and right margin.
        """
        loop = self.loops.get(animal_id)
        max_end_slot = loop.get_max_end_slot(start_slot, self.frame_to_slot)
        
        # can't extend beyond last slot
        return min(self.slots["total"], max_end_slot)
    
    def mute_slots_of_section(self, animal_id: str, start_slot: int, slot_1: int, slot_2: int, mute: bool) -> None:
        """
        Mute/unmute the section of the animal loop that starts at start_slot, between slot_1 and slot_2.
        Call this when mute button has been clicked and user clicks on a slot ot drags over numerous and releases. 
        """
        loop = self.loops[animal_id]
        loop.toggle_mute(start_slot, slot_1, slot_2, self.slot_to_frame, mute)
        
    # ======================================================================
    # audio scheduling
    # ======================================================================
    def _schedule_cycle(self, start_time: float, loop: bool) -> None:
        """Schedule one full pass of the loop (all animals, all sections)."""
        total_slots = self.slots["total"]
        loop_ticks = self.slot_to_tick(total_slots)
        
        tick_offset = self.scheduler.tempo_map.time_to_tick(start_time)

        for animal_id, loop in self.loops.items():
            for start_slot in loop.sections.keys():
                tick = self.slot_to_tick(start_slot)
                # schedule the start of this section
                self.scheduler.post_at_tick(
                    self._start_section_playback,
                    tick,
                    (animal_id, start_slot)
                )
        if loop:
            self.scheduler.post_at_tick(
                self._schedule_cycle,
                loop_ticks,
                (0, loop),
            )
        
    def _start_section_playback(self, tick: int, animal_id: str, start_slot: int) -> None:
        """Starts playback of a section for a given animal at the current time."""
        loop = self.loops.get(animal_id)
        if not loop:
            return
        section = loop.sections.get(start_slot)
        if not section:
            return
        
        # in case we started playback partway through the section
        curr_frame = self.scheduler.tempo_map.cur_frame
        section_start_frame = self.slot_to_frame(start_slot)
        frame_offset = curr_frame - section_start_frame

        gen = section.get_wave_generator(frame_offset)
        # per-animal volume
        gen.set_gain(loop.volume)
        # TODO: pitch shift
        self.mixer.add(gen)
        
    def on_update(self) -> None:
        self.audio.on_update()

    def play(self, start_time: float, loop: bool) -> None:
        """
        Start audio playback of the current loops. 
        If loop=True, will continuously loop.
        start_time specifies the time offset into the loop to begin playback.
        """
        self._schedule_cycle(start_time, loop)

    def pause(self) -> None:
        """Stops audio playback immediately."""
        self.scheduler.commands.clear()
        self.mixer.generators.clear()
            
    # ======================================================================
    # internal helpers
    # ======================================================================
    def _get_beats_per_measure(self) -> int:
        return self.time_sig[0]
    
    def _update_settings(self) -> None:
        self.beats = self.measures * self._get_beats_per_measure()
        self._set_ppb()
        self._set_slots()

    def _set_ppb(self) -> None:
        """Sets pulses-per-beat based on numerator (simple vs compound)."""
        if self._get_beats_per_measure() in (6, 9, 12):
            self.ppb = 6
        else:
            self.ppb = 4

    def _set_slots(self) -> None:
        total_slots = self.beats * self.ppb
        measure_slots = list(range(0, total_slots, self._get_beats_per_measure() * self.ppb))
        beat_slots = list(range(0, total_slots, self.ppb))
        sub_beat_slots = list(range(0, total_slots, 2))
        self.slots = {
            "measures": measure_slots,
            "beats": beat_slots,
            "sub_beats": sub_beat_slots,
            "total": total_slots,
        }
        
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