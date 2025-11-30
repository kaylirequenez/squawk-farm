import librosa
from imslib.audio import Audio
import random

from squawkfarm.models.progression import ChordProgression
from squawkfarm.models.loop_runtime import Loop, Recording
from squawkfarm.services.audio.grid import Grid
from squawkfarm.services.audio.audio_manager import AudioManager
from squawkfarm.services.composition.composer import Composer
from squawkfarm.utils import tune_sample_and_save, get_recording_wav_path

class LoopEngine:
    def __init__(self, settings, animal_loops=None):
        self.settings = settings
        self.grid = Grid(settings)
        self.loops = {}
        self.recording = None
        animal_loops = animal_loops if animal_loops else {}
        if not settings.chord_progression:
            settings.chord_progression = ChordProgression.generate_random_progression(settings.key_mode, settings.measures)
        self.composer = Composer(
            key_mode=settings.key_mode,
            root=settings.root,
            chord_progression=settings.chord_progression,
        )
        self.audio_manager = AudioManager(self.grid, self.loops, self.settings)

        for animal_id, loop in animal_loops.items():
            audio_data, _ = librosa.load(
                get_recording_wav_path(animal_id, "tuned"),
                sr=Audio.sample_rate,
            )
            self.loops[animal_id] = Loop(
                audio_data,
                loop.start_frame,
                loop.num_frames,
                loop.midi,
                loop.role,
                loop.volume,
                loop.instances,
            )

    def get_bpm(self):
        return self.grid.get_bpm()

    def set_bpm(self, bpm):
        if self.loops:
            return False
        current_time = self.audio_manager.get_scheduler_time()
        self.grid.set_bpm(bpm, current_time)
        return True
    
    def get_time_signature_options(self):
        return self.grid.get_time_signature_options()

    def get_time_signature(self):
        return self.grid.get_time_signature()

    def set_time_signature(self, time_sig):
        if self.loops:
            return False
        self.grid.set_time_signature(time_sig)
        return True
    
    def get_total_measures_options(self):
        return self.grid.get_total_measures_options()

    def get_total_measures(self):
        return self.grid.get_total_measures()

    def set_total_measures(self, measures):
        self.grid.set_total_measures(measures)

    def get_key_mode(self):
        return self.composer.key_mode

    def set_key_mode(self, key_mode):
        self.composer.set_key_mode(key_mode)
        self._retune_all_instances()

    def get_root(self):
        return self.composer.root

    def set_root(self, root):
        self.composer.set_root(root)
        self._retune_all_instances()

    def get_chord_progression(self):
        return self.composer.chord_progression

    def set_chord_progression(self, progression):
        self.composer.set_chord_progression(progression)
        self.settings.chord_progression = progression
        self._retune_all_instances()
        
    def generate_random_chord_progression(self):
        progression = ChordProgression.generate_random_progression(
            self.composer.key_mode,
            self.grid.get_total_measures()
        )
        self.set_chord_progression(progression)
        self._retune_all_instances()
        return progression

    def get_animal_role(self, animal_id):
        return self.loops[animal_id].role

    def set_animal_role(self, animal_id, new_role):
        loop = self.loops[animal_id]
        
        self.composer.change_animal_role(animal_id, loop.role, new_role)
        loop.role = new_role
        
        self._retune_animal_instances(animal_id)

    def set_recording(self, animal_id):
        audio_path = get_recording_wav_path(animal_id, "raw")
        if animal_id in self.loops:
            start_frame = self.loops[animal_id].start_frame
            num_frames = self.loops[animal_id].num_frames
        else:
            start_frame = 0
            num_frames = None
        self.recording = Recording(audio_path, start_frame, num_frames)

    def get_recording_duration(self):
        if not self.recording:
            return 0.0
        return self.grid.frame_to_time(self.recording.get_num_frames())

    def set_left_margin_of_recording(self, fraction):
        if not self.recording:
            return
        left_frame = round(fraction * self.recording.last_frame)
        print("fraction", fraction)
        self.recording.set_left_margin(left_frame)

    def set_right_margin_of_recording(self, fraction):
        if not self.recording:
            return
        right_frame = round(fraction * self.recording.last_frame)
        print("fraction", fraction)
        self.recording.set_right_margin(right_frame)

    def shift_recording(self, num_slots):
        if not self.recording:
            return
        self.recording.shift(self.grid.slot_to_frame(num_slots))

    def finalize_animal_loop(self, animal_id, role=None):
        if not self.recording:
            return

        start_frame = self.recording.start_frame
        num_frames = self.recording.get_num_frames()
        trimmed_data = self.recording.trimmed.data
        audio_data, base_midi = tune_sample_and_save(animal_id, trimmed_data)
        self.composer.handle_first_animal_if_needed(base_midi)

        if not role:
            slots = self.grid.frame_to_slot(num_frames)
            beats = self.slot_to_beat(slots)
            role = self.composer.guess_initial_role(base_midi, beats)

        self.loops[animal_id] = Loop(audio_data, start_frame, num_frames, base_midi, role)
        self.composer.register_animal_role(animal_id, role)
        
    def delete_animal_loop(self, animal_id):
        self.loops.pop(animal_id)
        self.composer.unregister_animal_role(animal_id, self.loops[animal_id].role)

    def slot_to_time(self, slot):
        tick = self.grid.slot_to_tick(slot)
        return self.grid.tick_to_time(tick)

    def time_to_slot(self, time_sec):
        frame = self.grid.time_to_frame(time_sec)
        return self.grid.frame_to_slot(frame)

    def get_slots_per_beat(self):
        return self.grid.get_slots_per_beat()

    def get_slots_per_measure(self):
        return self.grid.get_slots_per_beat() * self.grid.get_beats_per_measure()

    def beat_to_slot(self, beat):
        ppb = self.grid.get_slots_per_beat()
        return beat * ppb

    def slot_to_beat(self, slot):
        ppb = self.grid.get_slots_per_beat()
        return slot / ppb

    def get_total_slots(self):
        return self.grid.get_total_slots()

    def get_base_midi(self, animal_id):
        return self.loops[animal_id].midi

    def get_instance_info(self, animal_id, start_slot):
        return self.loops[animal_id].get_instance_info(start_slot, self.grid.frame_to_slot)

    def get_instances_info(self, animal_id):
        return self.loops[animal_id].get_instances_info(self.grid.frame_to_slot)

    def add_loop_instance(self, animal_id, start_slot, overlap=False, midi=None):
        loop = self.loops[animal_id]

        return loop.add_to_grid(start_slot, self.grid.frame_to_slot, overlap, midi)

    def remove_loop_instance(self, animal_id, start_slot):
        self.loops[animal_id].instances.pop(start_slot, None)

    def clear_loop_instances(self, animal_id):
        for start_slot in self.loops[animal_id].instances:
            self.remove_loop_instance(animal_id, start_slot)

    def set_pitch_of_instance(self, animal_id, start_slot, midi):
        loop = self.loops[animal_id]
        loop.set_pitch(start_slot, midi)

    def shift_animal_octave(self, animal_id, semitones):
        loop = self.loops.get(animal_id)
        if not loop:
            return

        # Check if the shift is possible without clamping any instances
        min_instance_midi = min((instance.midi for instance in loop.instances.values()), default=loop.midi)
        max_instance_midi = max((instance.midi for instance in loop.instances.values()), default=loop.midi)
        
        # Also include base MIDI in the range check
        min_midi = min(min_instance_midi, loop.midi)
        max_midi = max(max_instance_midi, loop.midi)
        
        # Calculate what the new min/max would be
        new_min = min_midi + semitones
        new_max = max_midi + semitones
        
        print(f"[shift_animal_octave] {animal_id}: current range [{min_midi}, {max_midi}], base={loop.midi}, semitones={semitones}, would result in [{new_min}, {new_max}]")
        
        # If the shift would push any MIDI value out of bounds, don't do it
        if new_min < 0 or new_max > 127:
            print(f"[shift_animal_octave] BLOCKED: Cannot shift {animal_id} by {semitones}: would result in MIDI range [{new_min}, {new_max}]")
            return

        print(f"[shift_animal_octave] ALLOWED: Shifting {animal_id} by {semitones}")
        
        # IMPORTANT: Keep the old base_midi before updating
        old_base_midi = loop.midi
        
        # Update all instances FIRST using the old base_midi
        for start_slot in list(loop.instances.keys()):
            instance = loop.instances[start_slot]
            old_midi = instance.midi
            new_midi = instance.midi + semitones
            # set_pitch uses loop.midi internally, so it must be the OLD base_midi
            loop.set_pitch(start_slot, new_midi)
            print(f"[shift_animal_octave] slot {start_slot}: {old_midi} → {new_midi}")
        
        # THEN update base MIDI after all instances are updated
        loop.midi = old_base_midi + semitones
        print(f"[shift_animal_octave] base_midi updated: {old_base_midi} → {loop.midi}")

    def mute_instance_slots(self, animal_id, start_slot, slot_1, slot_2, mute):
        loop = self.loops[animal_id]
        frame_1 = self.grid.slot_to_frame(slot_1)
        frame_2 = self.grid.slot_to_frame(slot_2)
        loop.toggle_mute(start_slot, frame_1, frame_2, mute)

    def slide_instance(self, animal_id, old_start_slot, new_start_slot, overlap=False):
        self.pause()
        return self.loops[animal_id].slide(old_start_slot, new_start_slot, self.grid.frame_to_slot, overlap)

    def set_loop_volume(self, animal_id, volume):
        self.loops[animal_id].set_volume(volume)

    def set_callbacks(self, on_sing, on_close):
        self.audio_manager.set_callbacks(on_sing, on_close)

    def on_update(self):
        self.audio_manager.on_update()

    def play(self, start_time=0.0, loop=False, animal_id=None):
        self.audio_manager.play(start_time, loop, animal_id)

    def pause(self):
        self.audio_manager.pause()

    def toggle_play(self, start_time=0.0, loop=False):
        if self.audio_manager.is_playing():
            self.audio_manager.pause()
        else:
            self.audio_manager.play(start_time, loop)

    def play_recording_preview(self, offset=0.0, repeat=False):
        if not self.recording:
            return
        self.audio_manager.play_recording(self.recording, offset, repeat)

    def toggle_play_recording_preview(self, offset=0.0, repeat=False):
        if self.audio_manager.is_playing():
            self.audio_manager.pause()
        else:
            self.play_recording_preview(offset, repeat)
    
    def set_volume(self, volume):
        self.audio_manager.set_volume(volume)

    def play_note_preview(self, animal_id, start_slot):
        if animal_id not in self.loops:
            return
        loop = self.loops[animal_id]
        if start_slot not in loop.instances:
            return

        gen = loop.get_generator(start_slot, frame_offset=0, loop=False)
        self.audio_manager.mixer.add(gen)

    def auto_generate_for_animal(self, animal_id):
        loop = self.loops[animal_id]

        beat_starts = self._generate_rhythm_beats_for_animal(animal_id)
        start_slots = [int(round(self.beat_to_slot(b))) for b in beat_starts]
        pitch_by_slot = self._generate_pitch_map_for_animal(
            animal_id=animal_id,
            start_slots=start_slots,
        )

        loop = self.loops[animal_id]
        for s in start_slots:
            midi = pitch_by_slot.get(s)
            if midi is not None:
                loop.add_to_grid(s, self.grid.frame_to_slot, overlap=False, midi=midi)
            

    def _generate_pitch_map_for_animal(self, animal_id, start_slots):
        loop = self.loops[animal_id]
        base_midi = loop.midi

        pentatonic_intervals = [0, 2, 4, 7, 9]
        root_c = self.settings.root

        pentatonic_notes = []
        for octave_offset in range(-1, 3):
            for interval in pentatonic_intervals:
                note = root_c + (octave_offset * 12) + interval
                if 0 <= note <= 127:
                    pentatonic_notes.append(note)

        closest_note = min(pentatonic_notes, key=lambda n: abs(n - base_midi))
        closest_index = pentatonic_notes.index(closest_note)

        pitch_map = {}
        current_note_index = closest_index
        is_first_animal = len(self.loops) == 1
        
        # Track the range of notes we generate
        min_note_index = closest_index
        max_note_index = closest_index
        generated_notes = []

        for s in start_slots:
            if is_first_animal and s == 0:
                pitch_map[s] = pentatonic_notes[current_note_index]
                generated_notes.append(pentatonic_notes[current_note_index])
                min_note_index = min(min_note_index, current_note_index)
                max_note_index = max(max_note_index, current_note_index)
                step = random.choice([-1, 0, 1, 1])
                current_note_index = max(0, min(len(pentatonic_notes) - 1, current_note_index + step))
            elif random.random() < 0.7:
                pitch_map[s] = pentatonic_notes[current_note_index]
                generated_notes.append(pentatonic_notes[current_note_index])
                min_note_index = min(min_note_index, current_note_index)
                max_note_index = max(max_note_index, current_note_index)
                step = random.choice([-1, 0, 1, 1])
                current_note_index = max(0, min(len(pentatonic_notes) - 1, current_note_index + step))
            else:
                pitch_map[s] = None

        # Adjust base_midi to center the generated notes on the visible range
        # The display shows 8 rows (0-7), where row 0 is the lowest and row 7 is the highest
        # We want the minimum generated note to appear around row 0-1 and max around row 6-7
        min_generated_note = min(generated_notes) if generated_notes else base_midi
        max_generated_note = max(generated_notes) if generated_notes else base_midi
        note_range = max_generated_note - min_generated_note
        
        print(f"[_generate_pitch_map_for_animal] Generated notes: min={min_generated_note}, max={max_generated_note}, range={note_range}")
        print(f"[_generate_pitch_map_for_animal] Original base_midi={base_midi}, pitch_map={pitch_map}")
        
        # Set base_midi to the minimum generated note (or slightly below it)
        # This ensures the lowest note appears near the bottom of the display
        new_base_midi = min_generated_note
        if new_base_midi != base_midi:
            print(f"[_generate_pitch_map_for_animal] Adjusting base_midi from {base_midi} to {new_base_midi}")
            loop.midi = new_base_midi
            loop.original_midi = new_base_midi

        return pitch_map


    def _get_existing_bass_templates(self, exclude_animal_id):
        templates = []

        for aid in self.composer.animals_by_role.get("bass"):
            if aid == exclude_animal_id:
                continue

            tpl = [self.slot_to_beat(start_slot) % self.grid.get_beats_per_measure()
                   for start_slot in self.loops[aid].instances]
            tpl.sort()
            templates.append(tpl)

        return templates

    def _generate_rhythm_beats_for_animal(self, animal_id):
        loop = self.loops[animal_id]
        role = loop.role

        beats_per_measure = self.grid.get_beats_per_measure()
        total_measures = self.grid.get_total_measures()
        total_beats = beats_per_measure * total_measures

        loop_slots = self.grid.frame_to_slot(loop.num_frames)
        loop_beats = self.slot_to_beat(loop_slots)

        if loop_beats < 1.5:
            interval = 1
        elif loop_beats < 3:
            interval = 2
        else:
            interval = 4

        beat_starts = []
        current_beat = 0

        while current_beat < total_beats:
            if current_beat + loop_beats <= total_beats:
                beat_starts.append(float(current_beat))
            current_beat += interval

        return beat_starts

    def _retune_all_instances(self):
        pass

    def _retune_animal_instances(self, animal_id):
        pass
