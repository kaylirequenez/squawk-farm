"""Loop engine managing global tempo/meter and per-animal loops."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from squawkfarm.models.loop import AnimalLoop, GlobalLoopSettings

from imslib.clock import SimpleTempoMap, kTicksPerQuarter, Clock, Scheduler


MAX_MEASURES = 4
MIN_BPM = 40
MAX_BPM = 240

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

class LoopEngine:
    """
    Manages global tempo and a set of per-animal loops.
    """
    def __init__(self, clock: Clock, globalLoopSettings: GlobalLoopSettings = GlobalLoopSettings(), animalLoops: Dict[str, AnimalLoop] = {}):
        # synchronization
        self.clock = clock
        self.scheduler = Scheduler(self.clock, self.tempo_map)
        
        # loop settings
        self.measures = globalLoopSettings.measures
        self.time_sig = globalLoopSettings.time_sig
        self.beats = self.measures * self.get_beats_per_measure()
        self.tempo_map = SimpleTempoMap(globalLoopSettings.bpm)
        self.update_settings()
        
        # per-animal loops
        self.loops = animalLoops
        
        # TO DO
        # Review chosen slots to show & max number of measures w/ different time signatures.
        
    # Small internal helpers
    def get_beats_per_measure(self) -> int:
        """Returns number of beats per measure based on time signature."""
        return self.time_sig[0]
    
    # Global Setters
    def set_bpm(self, bpm: int) -> bool | int:
        """Sets the global BPM defaulting to valid range if it can be changed.
            Returns the BPM, whether or not changed.
        """
        if not self.loops:
            bpm = max(MIN_BPM, min(MAX_BPM, bpm))
            self.tempo_map.set_tempo(bpm, self.clock.get_time())
        return bpm

    def set_total_measures(self, total_measures: int) -> bool | int:
        """Sets the global total beats if it can be changed.
            Returns the total beats, whether or not changed.
        """
        if not self.loops:
            self.measures = total_measures
            self.beats = self.measures * self.get_beats_per_measure()
        return self.measures

    def set_time_signature(self, time_sig: Tuple[int, int]) -> bool | Tuple[int, int]:
        """Sets the global time signature if it can be changed.
            Returns the time signature, whether or not changed.
        """
        if not self.loops:
            self.time_sig = time_sig
            self.update_settings()
        return self.time_sig

    # Internal setters
    def update_settings(self) -> None:
        """Update loop settings based on current time signature and BPM.
        """
        self.set_ppb()
        self.set_slots()

    def set_ppb(self):
        """Sets the pulses per beat based on time signature denominator."""
        num, _ = self.time_sig

        if num in (6, 9, 12):
            self.ppb = 6   # enough for 3s and 6s
        else:
            self.ppb = 4   # simple: 2s and 4s
            
    def set_slots(self) -> dict:
        """
        Return structured slots that mirror the chart:
        - measure_starts: slot index of each measure start
        - beat_starts: slot index of each beat start
        - sub_beats: one finer level (8ths for simple, triplets for compound)
        
        Use this to draw the grid in the loop editor & recording screen.
        """
        beats_per_measure = self.get_beats_per_measure()
        total_slots = self.beats * self.ppb

        # 1) measure starts: every measure * beats_per_measure * ppb
        measure_starts = list(range(0, total_slots, beats_per_measure * self.ppb))

        # 2) beat starts: every beat * ppb
        beat_starts = list(range(0, total_slots, self.ppb))

        # 3) one more level smaller
        # simple (ppb=4): we want 8ths -> every 2 slots
        # compound (ppb=6): we want the "3-per-beat" layer -> every 2 slots (because 6/3 = 2)
        sub_step = 2
        sub_beats = list(range(0, total_slots, sub_step))

        self.slots = {
            "measure_starts": measure_starts,
            "beat_starts": beat_starts,
            "sub_beats": sub_beats,
            "total_slots": total_slots,
        }
            
    # Loop Grid + Recording Management 
    def get_total_measures_options(self) -> List[int]:
        """Returns list of possible total beats compatible with time signature."""
        return [measure for measure in range(MAX_MEASURES)]
    
    def get_time_signature_options(self) -> List[Tuple[int, int]]:
        """Returns list of common time signatures compatible with total beats."""
        return [ts for ts in COMMON_TIME_SIGNATURES if self.beats % ts[0] == 0]
    
    def get_loop_duration(self) -> float:
        """
        Returns the total length of the loop in seconds based on
        the current BPM and total number of beats.
        """
        bpm = self.tempo_map.get_tempo()
        seconds_per_beat = 60.0 / bpm
        total_seconds = self.beats * seconds_per_beat
        return total_seconds
        
    # def _closest_slot(self, target: int) -> int:
    #     """Return the slot from slot_list that is closest to target."""
    #     return min(self.slots, key=lambda s: abs(s - target))

    # def snap_to_slots(self, n1: int, n2: int) -> tuple[int, int]:
    #     """
    #     Given two numbers (slot-ish indexes), return the closest
    #     slots from the loop's defined grid (we use sub_beats).
    #     """
    #     slots_info = self.get_slots()
    #     sub_beats = slots_info["sub_beats"]

    #     snapped_1 = self._closest_slot(n1, sub_beats)
    #     snapped_2 = self._closest_slot(n2, sub_beats)

    #     return (snapped_1, snapped_2)

    # Individual Loop Management
    def add_loop(self, loop: AnimalLoop) -> None:
        """Adds new loop/animal"""
        self._ensure_valid_length(loop)
        self._ensure_step_mutes(loop)
        self._loops[loop.animal_id] = loop