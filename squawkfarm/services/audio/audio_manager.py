from imslib.audio import Audio
from imslib.mixer import Mixer
from imslib.wavegen import WaveGenerator
from imslib.clock import AudioScheduler
from kivy.clock import Clock

from squawkfarm.services.audio.grid import Grid
from squawkfarm.models.loop_runtime import Loop, Recording, RuntimeLoopInstance
from squawkfarm.models.loop import GlobalLoopSettings
from squawkfarm.utils import tune_to_midi


class AudioManager:
    def __init__(self, grid, loops, settings):
        self.grid = grid
        self.loops = loops
        self.settings = settings

        self.scheduler = AudioScheduler(self.grid.tempo_map)
        self.mixer = Mixer()
        self.scheduler.set_generator(self.mixer)

        self.audio = Audio(2)
        self.audio.set_generator(self.scheduler)

        self.playing = False
        self._on_sing = lambda aid: None
        self._on_close = lambda aid: None
        self.scheduled_close_events = {}

        self.current_cycle = 0

    def get_chord_info_at_slot(self, slot):
        progression = self.settings.chord_progression
        if not progression:
            return 0, "maj"

        measure = self.grid.slot_to_measure(slot)
        total_measures = self.grid.get_total_measures()
        absolute_measure = measure + (self.current_cycle * total_measures)

        measures_per_chord = 4
        chord_index = absolute_measure // measures_per_chord
        chord = progression.get_chord_at_measure(chord_index)

        transpose = chord.degree - 1

        return transpose, chord.quality

    def set_callbacks(self, on_sing, on_close):
        self._on_sing = on_sing
        self._on_close = on_close

    def on_update(self):
        self.audio.on_update()

    def is_playing(self):
        return self.playing

    def get_scheduler_time(self):
        return self.scheduler.get_time()

    def set_volume(self, volume):
        self.mixer.set_gain(volume)

    def play(self, start_time=0.0, repeat=False, animal_id=None):
        self.playing = True
        self.current_cycle = 0
        self._schedule_cycle(start_time, repeat, animal_id)

    def pause(self, _tick=None):
        self.scheduler.commands.clear()
        self.mixer.generators.clear()
        self.playing = False

        for animal_id, events in self.scheduled_close_events.items():
            for event in events:
                Clock.unschedule(event)
            self._on_close(animal_id)
        self.scheduled_close_events.clear()

    def play_recording(self, recording, offset=0.0, repeat=False):
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

    def _schedule_cycle(self, start_time, repeat, filter_animal_id=None):
        now = self.scheduler.get_tick()
        loop_ticks = self.grid.slot_to_tick(self.grid.get_total_slots())
        tick_offset = self.grid.time_to_tick(start_time)

        # Filter loops if animal_id is specified
        loops_to_play = {filter_animal_id: self.loops[filter_animal_id]} if filter_animal_id and filter_animal_id in self.loops else self.loops

        for animal_id, loop in loops_to_play.items():
            for start_slot, _ in loop.instances.items():
                num_slots = self.grid.frame_to_slot(loop.num_frames)
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

                transpose_semitones, chord_quality = self.get_chord_info_at_slot(start_slot)

                self.scheduler.post_at_tick(
                    self._start_section_playback,
                    tick + now,
                    (animal_id, start_slot, frame_offset, transpose_semitones, chord_quality),
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

    def _start_section_playback(self, _, args):
        animal_id, start_slot, frame_offset, transpose_semitones, chord_quality = args

        loop = self.loops.get(animal_id)
        if not loop or start_slot not in loop.instances:
            return

        midi = loop.instances[start_slot]

        current_midi = midi
        target_midi = current_midi + transpose_semitones

        scale_degree_in_c = current_midi % 12
        quality_adjustment = 0

        if chord_quality in ("min", "min7"):
            if scale_degree_in_c == 4:
                quality_adjustment = -1

        if chord_quality in ("dom7", "min7"):
            if scale_degree_in_c == 11:
                quality_adjustment = -1

        target_midi += quality_adjustment

        if transpose_semitones != 0 or quality_adjustment != 0:
            transposed_data = tune_to_midi(loop.current, loop.original_midi, target_midi)
            temp_instance = RuntimeLoopInstance(transposed_data)
            gen = WaveGenerator(temp_instance, False)
        else:
            gen = loop.get_generator(start_slot, frame_offset, False)
            frame_offset = 0

        gen.frame = frame_offset
        gen.set_gain(loop.volume)
        self.mixer.add(gen)

        self._on_sing(animal_id)
        duration = self.grid.frame_to_time(loop.num_frames)

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
