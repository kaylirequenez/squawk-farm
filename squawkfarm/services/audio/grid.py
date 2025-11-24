from typing import List, Tuple

from imslib.clock import SimpleTempoMap, kTicksPerQuarter
from imslib.audio import Audio
from squawkfarm.models.loop import GlobalLoopSettings


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


class Grid:
    """
    Global timing + grid abstraction for the loop.
    """

    def __init__(self, settings: GlobalLoopSettings):
        self.measures: int = settings.measures
        self.time_sig: Tuple[int, int] = settings.time_sig   # (numerator, denominator)
        self.tempo_map = SimpleTempoMap(settings.bpm)

    # ------------------------------------------------------------------ #
    # high-level queries
    # ------------------------------------------------------------------ #

    def get_bpm(self) -> int:
        return self.tempo_map.get_tempo()

    def get_total_measures(self) -> int:
        return self.measures

    def get_time_signature(self) -> Tuple[int, int]:
        return self.time_sig

    def get_beats(self) -> int:
        return self.measures * self.get_beats_per_measure()

    def get_beats_per_measure(self) -> int:
        return self.time_sig[0]
    
    def get_slots_per_beat(self) -> int:
        """
        pulses-per-beat: 4 for simple meters, 6 for compound (6/8, 9/8, 12/8).
        """
        beats = self.get_beats_per_measure()
        if beats in (6, 9, 12):
            return 6
        return 4

    def get_total_slots(self) -> int:
        return self.get_beats() * self.get_slots_per_beat()

    def get_total_measures_options(self) -> List[int]:
        return list(range(1, MAX_MEASURES + 1))

    def get_time_signature_options(self) -> List[Tuple[int, int]]:
        beats = self.get_beats()
        return [ts for ts in COMMON_TIME_SIGNATURES if beats % ts[0] == 0]

    # ------------------------------------------------------------------ #
    # mutators
    # ------------------------------------------------------------------ #

    def set_total_measures(self, total_measures: int) -> None:
        self.measures = total_measures

    def set_time_signature(self, time_sig: Tuple[int, int]) -> None:
        self.time_sig = time_sig

    def set_bpm(self, bpm: int, current_time: float) -> None:
        bpm = max(MIN_BPM, min(MAX_BPM, bpm))
        self.tempo_map.set_tempo(bpm, current_time)

    # ------------------------------------------------------------------ #
    # conversions: slots <-> ticks <-> time <-> frames
    # ------------------------------------------------------------------ #

    def slot_to_tick(self, slot: int) -> int:
        ppb = self.get_slots_per_beat()
        ticks_per_slot = kTicksPerQuarter // ppb
        return slot * ticks_per_slot

    def tick_to_time(self, tick: int) -> float:
        return self.tempo_map.tick_to_time(tick)

    def time_to_tick(self, time_sec: float) -> int:
        return self.tempo_map.time_to_tick(time_sec)

    def time_to_frame(self, time_sec: float) -> int:
        return int(time_sec * Audio.sample_rate)

    def frame_to_time(self, frame: int) -> float:
        return frame / float(Audio.sample_rate)

    def slot_to_frame(self, slot: float) -> int:
        bpm = self.get_bpm()
        ppb = self.get_slots_per_beat()
        seconds_per_slot = (60.0 / bpm) / ppb
        seconds = slot * seconds_per_slot
        return int(seconds * Audio.sample_rate)

    def frame_to_slot(self, frame: int) -> int:
        bpm = self.get_bpm()
        ppb = self.get_slots_per_beat()
        seconds_per_slot = (60.0 / bpm) / ppb
        seconds = frame / Audio.sample_rate
        slot = seconds / seconds_per_slot
        return int(slot)
