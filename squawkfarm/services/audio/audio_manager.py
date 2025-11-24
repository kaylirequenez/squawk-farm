from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

from imslib.audio import Audio
from imslib.mixer import Mixer
from imslib.wavegen import WaveGenerator, SpeedModulator
from imslib.clock import AudioScheduler
from kivy.clock import Clock

from squawkfarm.services.audio.grid import Grid
from squawkfarm.models.loop_runtime import Loop, Recording
from squawkfarm.models.loop import GlobalLoopSettings

# TODO: make it so callbacks must be included for initialization
class AudioManager:
    """
    Handles audio scheduling + device:

      - AudioScheduler + Mixer + Audio
      - schedules playback of a shared `loops` dict
      - optionally plays a Recording preview

    NOTES:
      - `loops` is a reference to the dict owned by LoopEngine.
      - AudioManager does NOT modify loops; it only reads them to schedule audio.
    """
    def __init__(self, grid: Grid, loops: Dict[str, Loop], settings: GlobalLoopSettings):
        self.grid = grid
        self.loops = loops  # shared reference from LoopEngine
        self.settings = settings  # global settings for key changes

        self.scheduler = AudioScheduler(self.grid.tempo_map)
        self.mixer = Mixer()
        self.scheduler.set_generator(self.mixer)

        self.audio = Audio(2)
        self.audio.set_generator(self.scheduler)

        self.playing: bool = False

        # callbacks set by LoopEngine (for mouth animations, etc.)
        self._on_sing: Callable[[str], None] = lambda aid: None
        self._on_close: Callable[[str], None] = lambda aid: None

        # scheduled mouth-close events (can have multiple per animal)
        self.scheduled_close_events: Dict[str, list] = {}

        self.current_cycle: int = 0

    def get_global_transpose_at_slot(self, slot: int) -> int:
        if not self.settings.key_change_offsets:
            return 0

        total_measures = self.grid.get_total_measures()
        measure = self.grid.slot_to_measure(slot) + (self.current_cycle * total_measures)
        key_change_index = (measure // self.settings.key_change_interval) % len(self.settings.key_change_offsets)
        return self.settings.key_change_offsets[key_change_index]

    # ------------------------------------------------------------------ #
    # basic control
    # ------------------------------------------------------------------ #

    def set_callbacks(self, on_sing: Callable[[str], None], on_close: Callable[[str], None]) -> None:
        self._on_sing = on_sing
        self._on_close = on_close

    def on_update(self) -> None:
        self.audio.on_update()

    def is_playing(self) -> bool:
        return self.playing

    def get_scheduler_time(self) -> float:
        return self.scheduler.get_time()
    
    def set_volume(self, volume: float) -> None:
        self.mixer.set_gain(volume)

    # ------------------------------------------------------------------ #
    # loop playback
    # ------------------------------------------------------------------ #

    def play(self, start_time: float = 0.0, repeat: bool = False) -> None:
        """
        Play ALL loops currently in `self.loops`.
        """
        self.playing = True
        self.current_cycle = 0
        self._schedule_cycle(start_time, repeat)

    def pause(self, _tick: Optional[int] = None) -> None:
        """
        Stop playback immediately.
        """
        self.scheduler.commands.clear()
        self.mixer.generators.clear()
        self.playing = False

        # cancel scheduled mouth-closes
        for animal_id, events in self.scheduled_close_events.items():
            for event in events:
                Clock.unschedule(event)
            self._on_close(animal_id)
        self.scheduled_close_events.clear()

    # ------------------------------------------------------------------ #
    # recording preview playback
    # ------------------------------------------------------------------ #

    def play_recording(
        self,
        recording: Recording,
        offset: float = 0.0,
        repeat: bool = False,
    ) -> None:
        """
        Play a single Recording object.
        """
        gen = recording.get_generator(self.grid.time_to_frame(offset), repeat)
        self.mixer.add(gen)
        self.playing = True
        
        if not repeat:
            duration = self.grid.frame_to_time(recording.get_num_frames()) - offset
            end_time = self.scheduler.get_time() + duration
            
            self.scheduler.post_at_tick(
                self.pause,
                self.grid.tempo_map.time_to_tick(end_time),
            )

    # ------------------------------------------------------------------ #
    # internal scheduling for loops
    # ------------------------------------------------------------------ #

    def _schedule_cycle(self, start_time: float, repeat: bool) -> None:
        now = self.scheduler.get_tick()
        loop_ticks = self.grid.slot_to_tick(self.grid.get_total_slots())
        tick_offset = self.grid.time_to_tick(start_time)

        for animal_id, loop in self.loops.items():
            for start_slot, num_slots, _ in loop.get_instances_info(self.grid.frame_to_slot):
                wave_generator: Optional[WaveGenerator] = None
                tick = self.grid.slot_to_tick(start_slot)

                if tick >= tick_offset:
                    wave_generator = loop.get_generator(start_slot)
                else:
                    end_tick = tick + self.grid.slot_to_tick(num_slots)
                    if end_tick > tick_offset:
                        local_tick_offset = tick_offset - tick
                        local_frame_offset = self.grid.tick_to_frame(
                            self.grid.tick_to_time(local_tick_offset)
                        )
                        wave_generator = loop.get_generator(start_slot, local_frame_offset)
                        tick += local_tick_offset

                if wave_generator is not None:
                    transpose_semitones = self.get_global_transpose_at_slot(start_slot)
                    if transpose_semitones != 0:
                        speed_multiplier = 2.0 ** (transpose_semitones / 12.0)
                        wave_generator = SpeedModulator(wave_generator, speed_multiplier)

                    self.scheduler.post_at_tick(
                        self._start_section_playback,
                        tick + now,
                        (animal_id, start_slot, wave_generator),
                    )

        def callback(_dt):
            if repeat and self.playing:
                self.current_cycle += 1
                self._schedule_cycle(0.0, repeat)
            else:
                self.pause()

        self.scheduler.post_at_tick(
            callback,
            loop_ticks - tick_offset + now,
        )

    # TODO: make not tuple
    def _start_section_playback(self, _: int, args: Tuple[str, int, WaveGenerator]) -> None:
        animal_id, start_slot, gen = args

        loop = self.loops.get(animal_id)
        if not loop or not start_slot in loop.instances:
            return

        self.mixer.add(gen)

        self._on_sing(animal_id)
        duration = self.grid.frame_to_time(loop.get_num_frames(start_slot))

        # Close mouth slightly before the end (90% of duration) so it can reopen for the next note
        close_duration = duration * 0.9

        def close_callback(_dt):
            self._on_close(animal_id)
            # Remove this specific event from the list
            if animal_id in self.scheduled_close_events:
                try:
                    self.scheduled_close_events[animal_id].remove(event)
                    if not self.scheduled_close_events[animal_id]:
                        del self.scheduled_close_events[animal_id]
                except (ValueError, KeyError):
                    pass

        event = Clock.schedule_once(close_callback, close_duration)

        # Add to list of events for this animal
        if animal_id not in self.scheduled_close_events:
            self.scheduled_close_events[animal_id] = []
        self.scheduled_close_events[animal_id].append(event)
