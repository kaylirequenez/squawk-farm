import librosa
from imslib.audio import Audio
from imslib.wavesrc import WaveFile
from squawkfarm.models.progression import ChordProgression
from squawkfarm.models.loop_runtime import Loop, Recording
from squawkfarm.services.audio.grid import Grid
from squawkfarm.services.audio.audio_manager import AudioManager
from squawkfarm.services.composition.composer import Composer
from squawkfarm.services.composition.pitch import generate_constrained_pentatonic_pitch_map
from squawkfarm.services.composition.rhythm import generate_slots
from squawkfarm.utils import tune_sample_and_save, get_recording_wav_path
from squawkfarm.utils.audio_utils import frame_to_time, time_to_frame

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
                    
        self.rhythm_candidates: list[list[int]] = []
        self.rhythm_candidate_index: int = 0

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
        
    def set_recording_to_preset(self, audio_path):
        wf = WaveFile(audio_path)
        num_frames = wf.end
        global_frames = self.grid.slot_to_frame(self.get_total_slots())
        if num_frames > global_frames:
            num_frames = global_frames
        self.recording = Recording(audio_path, 0, num_frames)
        
        return list(wf.get_frames(0, num_frames))

    def get_recording_duration(self):
        if not self.recording:
            return 0.0
        return frame_to_time(self.recording.get_num_frames())

    def set_left_margin_of_recording(self, fraction):
        if not self.recording:
            return
        left_frame = round(fraction * self.recording.last_frame)
        self.recording.set_left_margin(left_frame)

    def set_right_margin_of_recording(self, fraction):
        if not self.recording:
            return
        right_frame = round(fraction * self.recording.last_frame)
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
        volume = self.recording.get_volume()  # Get the volume from the recording
        audio_data, base_midi = tune_sample_and_save(animal_id, trimmed_data)
        self.composer.handle_first_animal_if_needed(base_midi)

        if not role:
            slots = self.grid.frame_to_slot(num_frames)
            beats = self.slot_to_beat(slots)
            role = self.composer.guess_initial_role(base_midi, beats)

        self.loops[animal_id] = Loop(audio_data, start_frame, num_frames, base_midi, role, volume)
        self.composer.register_animal_role(animal_id, role)
        
    def delete_animal_loop(self, animal_id):
        loop = self.loops.pop(animal_id)
        self.composer.unregister_animal_role(animal_id, loop.role)

    def slot_to_time(self, slot):
        tick = self.grid.slot_to_tick(slot)
        return self.grid.tick_to_time(tick)

    def time_to_slot(self, time_sec):
        frame = time_to_frame(time_sec)
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

    def get_instances_info(self, animal_id):
        loop = self.loops[animal_id]
        return loop.instances, self.grid.frame_to_slot(loop.num_frames)

    def add_loop_instance(self, animal_id, start_slot, overlap=False, midi=None):
        loop = self.loops[animal_id]

        return loop.add_to_grid(start_slot, self.grid.frame_to_slot, overlap, midi)

    def remove_loop_instance(self, animal_id, start_slot):
        self.loops[animal_id].instances.pop(start_slot, None)

    def clear_loop_instances(self, animal_id):
        self.loops[animal_id].instances.clear()

    def set_pitch_of_instance(self, animal_id, start_slot, midi):
        loop = self.loops[animal_id]
        loop.set_pitch(start_slot, midi)

    def shift_animal_octave(self, animal_id, direction: int):
        """
        Shift an animal's notes up or down by whole octaves.

        direction:
            +1 -> up one octave ( +12 semitones )
            -1 -> down one octave ( -12 semitones )
        """
        loop = self.loops.get(animal_id)

        semitones = 12 * direction

        loop.midi += semitones
        for slot in loop.instances:
            loop.instances[slot] += semitones
            
        loop.role = self.composer.guess_initial_role(loop.midi, self.slot_to_beat(len(loop.instances))) 
        self.rhythm_candidates = self._compute_rhythm_candidates_for_animal(animal_id)
        self.rhythm_candidate_index = 0

    def slide_instance(self, animal_id, old_start_slot, new_start_slot, overlap=False):
        self.pause()
        return self.loops[animal_id].slide(old_start_slot, new_start_slot, self.grid.frame_to_slot, overlap)

    def set_loop_volume(self, animal_id, volume):
        self.loops[animal_id].set_volume(volume)

    def set_callbacks(self, on_sing, on_close):
        self.audio_manager.set_callbacks(on_sing, on_close)

    def on_update(self):
        self.audio_manager.on_update()
    
    def is_playing(self):
        return self.audio_manager.is_playing()

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
        if self.recording is None:
            return
        self.audio_manager.play_recording(self.recording, offset, repeat)

    def toggle_play_recording_preview(self, offset=0.0, repeat=False):
        if self.audio_manager.is_playing():
            self.audio_manager.pause()
        else:
            print("playing")
            print(self.audio_manager.mixer.gain)
            self.play_recording_preview(offset, repeat)

    def set_recording_volume(self, volume):
        if self.recording is not None:
            self.recording.set_volume(volume)

    def get_recording_volume(self):
        if self.recording is not None:
            return self.recording.get_volume()
        return 0.5  # Default volume

    def adjust_recording_volume(self, delta):
        """Adjust recording volume by delta (e.g., +0.1 or -0.1)"""
        if self.recording is not None:
            new_volume = self.recording.get_volume() + delta
            self.recording.set_volume(new_volume)
            return self.recording.get_volume()
        return 0.5
    
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
        """
        Called when an animal is first added or user makes edits.
        Picks the best rhythm candidate and applies it (with fresh pitches).
        """
        self.rhythm_candidates = self._compute_rhythm_candidates_for_animal(animal_id)
        self.rhythm_candidate_index = 0
        
        self._apply_rhythm_candidate(animal_id)
        
    def toggle_rhythm_option(self, animal_id, direction: int = 1):
        """
        Cycle through precomputed rhythm candidates for this animal.

        direction:
          +1 -> next candidate
          -1 -> previous candidate
        """
        candidates = self.rhythm_candidates

        self.rhythm_candidate_index = (self.rhythm_candidate_index + direction) % len(candidates)
        
        self._apply_rhythm_candidate(animal_id)
    
    def _apply_rhythm_candidate(self, animal_id):
        """
        Clear this animal's instances and rebuild them
        """
        start_slots = self.rhythm_candidates[self.rhythm_candidate_index]["pattern"]
        loop = self.loops[animal_id]

        # Clear existing rhythm for this animal
        loop.instances.clear()

        # Generate pitches for these slots
        pitch_map = self._generate_pitch_map_for_animal(
            animal_id=animal_id,
            start_slots=start_slots,
        )

        # Lay them down in the grid
        for s in start_slots:
            midi = pitch_map.get(s, loop.midi)
            loop.add_to_grid(
                start_slot=int(s),
                frame_to_slot=self.grid.frame_to_slot,
                midi=midi,
            )

    def _generate_pitch_map_for_animal(self, animal_id, start_slots):
        loop = self.loops[animal_id]

        pitch_map, ui_base_midi = generate_constrained_pentatonic_pitch_map(
            base_midi=loop.midi,
            root_midi=self.composer.root,
            start_slots=start_slots,
        )

        loop.midi = ui_base_midi
        return pitch_map
    
    def _get_same_role_globals(self, role: str, exclude_animal_id=None) -> list[list[int]]:
        """
        Get global slot patterns for animals of the same role, excluding one.
        """
        patterns: list[list[int]] = []
        for aid in self.composer.animals_by_role[role]:
            if aid == exclude_animal_id:
                continue
            slots = sorted(self.loops[aid].instances.keys())
            patterns.append(slots)
        return patterns

    def _get_all_role_globals(self, exclude_animal_id=None) -> list[list[int]]:
        """
        Get global slot patterns for all animals (all roles), excluding one.
        """
        patterns: list[list[int]] = []
        for aid, loop in self.loops.items():
            if aid == exclude_animal_id:
                continue
            slots = sorted(loop.instances.keys())
            patterns.append(slots)
        return patterns

    def _compute_rhythm_candidates_for_animal(self, animal_id) -> list[list[int]]:
        """
        Compute rhythm candidates for this animal and cache them.

        Returns the list of candidate global slot patterns.
        """
        loop = self.loops[animal_id]
        role = loop.role

        slots_per_measure = self.get_slots_per_measure()
        total_measures = self.grid.get_total_measures()

        loop_slots = self.grid.frame_to_slot(loop.num_frames)

        same_role_globals = self._get_same_role_globals(role, exclude_animal_id=animal_id)
        all_role_globals = self._get_all_role_globals(exclude_animal_id=animal_id)

        candidates = generate_slots(
            role=role,
            loop_slots=loop_slots,
            slots_per_measure=slots_per_measure,
            total_measures=total_measures,
            same_role_globals=same_role_globals,
            all_role_globals=all_role_globals,
            min_score=None,  # you can tweak this later
        )
        
        self.rhythm_candidates = candidates
        self.rhythm_candidate_index = 0

        return candidates

    def _retune_all_instances(self):
        pass

    def _retune_animal_instances(self, animal_id):
        pass
