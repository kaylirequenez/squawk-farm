from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

from imslib.audio import Audio
from imslib.mixer import Mixer
from imslib.wavegen import WaveGenerator
from imslib.clock import AudioScheduler
from kivy.clock import Clock

from squawkfarm.services.audio.grid import Grid
from squawkfarm.models.loop_runtime import Loop, Recording, RuntimeLoopInstance
from squawkfarm.models.loop import GlobalLoopSettings
from squawkfarm.utils import tune_to_midi

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

    def play(self, start_time: float = 0.0, repeat: bool = False, animal_id: Optional[str] = None) -> None:
        """
        Play loops. If animal_id is provided, play only that animal's loop.
        Otherwise, play ALL loops currently in `self.loops`.
        """
        self.playing = True
        self.current_cycle = 0
        self._schedule_cycle(start_time, repeat, animal_id)

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

    def _schedule_cycle(self, start_time: float, repeat: bool, filter_animal_id: Optional[str] = None) -> None:
        now = self.scheduler.get_tick()
        loop_ticks = self.grid.slot_to_tick(self.grid.get_total_slots())
        tick_offset = self.grid.time_to_tick(start_time)

        # Filter loops if animal_id is specified
        loops_to_play = {filter_animal_id: self.loops[filter_animal_id]} if filter_animal_id and filter_animal_id in self.loops else self.loops

        for animal_id, loop in loops_to_play.items():
            for start_slot, num_slots, _ in loop.get_instances_info(self.grid.frame_to_slot):
                wave_generator: Optional[WaveGenerator] = None
                tick = self.grid.slot_to_tick(start_slot)
                frame_offset = 0

                if tick >= tick_offset:
                    frame_offset = 0
                else:
                    end_tick = tick + self.grid.slot_to_tick(num_slots)
                    if end_tick > tick_offset:
                        local_tick_offset = tick_offset - tick
                        frame_offset = self.grid.tick_to_frame(
                            self.grid.tick_to_time(local_tick_offset)
                        )
                        tick += local_tick_offset
                    else:
                        continue

                transpose_semitones = self.get_global_transpose_at_slot(start_slot)

                self.scheduler.post_at_tick(
                    self._start_section_playback,
                    tick + now,
                    (animal_id, start_slot, frame_offset, transpose_semitones),
                )

        def callback(_dt):
            if repeat and self.playing:
                self.current_cycle += 1
                self._schedule_cycle(0.0, repeat, filter_animal_id)
            else:
                self.pause()

        self.scheduler.post_at_tick(
            callback,
            loop_ticks - tick_offset + now,
        )

    def _start_section_playback(self, _: int, args: Tuple[str, int, int, int]) -> None:
        animal_id, start_slot, frame_offset, transpose_semitones = args

        loop = self.loops.get(animal_id)
        if not loop or start_slot not in loop.instances:
            return

        instance = loop.instances[start_slot]

        if transpose_semitones != 0:
            current_midi = instance.midi
            target_midi = current_midi + transpose_semitones
            transposed_data = tune_to_midi(instance.clean_data, current_midi, target_midi)
            temp_instance = RuntimeLoopInstance(transposed_data, target_midi, instance.muted_ranges)
            gen = WaveGenerator(temp_instance, False)
        else:
            gen = loop.get_generator(start_slot, frame_offset, False)
            frame_offset = 0

        gen.frame = frame_offset
        gen.set_gain(loop.volume)
        self.mixer.add(gen)

        self._on_sing(animal_id)
        duration = self.grid.frame_to_time(loop.get_num_frames(start_slot))

        close_duration = duration * 0.9

        def close_callback(_dt):
            self._on_close(animal_id)
            if animal_id in self.scheduled_close_events:
                try:
                    self.scheduled_close_events[animal_id].remove(event)
                    if not self.scheduled_close_events[animal_id]:
                        del self.scheduled_close_events[animal_id]
                except (ValueError, KeyError):
                    pass

        event = Clock.schedule_once(close_callback, close_duration)

        if animal_id not in self.scheduled_close_events:
            self.scheduled_close_events[animal_id] = []
        self.scheduled_close_events[animal_id].append(event)
