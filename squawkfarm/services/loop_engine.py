from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import librosa
from imslib.audio import Audio

from squawkfarm.models.progression import ChordProgression
from squawkfarm.models.loop import GlobalLoopSettings, AnimalLoop
from squawkfarm.models.loop_runtime import Loop, Recording
from squawkfarm.services.audio.grid import Grid
from squawkfarm.services.audio.audio_manager import AudioManager
from squawkfarm.services.composition.composer import Composer
from squawkfarm.services.composition.rhythm import generate_beats
from squawkfarm.utils import tune_sample_and_save, get_recording_wav_path

class LoopEngine:
    """
    Public API for the loop system.

    UI talks ONLY to this class.

    Internally coordinates:
      - Grid (timing / slots / bpm / meter)
      - loops dict (per-animal Loop)
      - Recording (while editing)
      - Composer (roles, key, chords, degrees → MIDI)
      - AudioManager (scheduling + audio device)
    """

    def __init__(self, settings: GlobalLoopSettings, animal_loops: Dict[str, AnimalLoop] = {}):
        # Store settings for access by other components
        self.settings = settings

        # timing
        self.grid = Grid(settings)

        # runtime loops (per animal)
        self.loops: Dict[str, Loop] = {}

        # current recording (if editing)
        self.recording: Optional[Recording] = None

        # composition logic
        if not settings.chord_progression:
            settings.chord_progression = ChordProgression.generate_random_progression(settings.key_mode, settings.measures)
        self.composer = Composer(
            key_mode=settings.key_mode,
            root=settings.root,
            chord_progression=settings.chord_progression,
        )

        # audio manager shares this loops dict and settings
        self.audio_manager = AudioManager(self.grid, self.loops, self.settings)

        # hydrate from existing saved animals
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

    # ======================================================================
    # Global loop settings (UI-facing getters/setters)
    # ======================================================================

    def get_bpm(self) -> int:
        return self.grid.get_bpm()

    def set_bpm(self, bpm: int) -> bool:
        if self.loops:
            return False
        current_time = self.audio_manager.get_scheduler_time()
        self.grid.set_bpm(bpm, current_time)
        return True
    
    def get_time_signature_options(self) -> List[Tuple[int, int]]:
        return self.grid.get_time_signature_options()

    def get_time_signature(self):
        return self.grid.get_time_signature()

    def set_time_signature(self, time_sig) -> bool:
        if self.loops:
            return False
        self.grid.set_time_signature(time_sig)
        return True
    
    def get_total_measures_options(self) -> List[int]:
        return self.grid.get_total_measures_options()

    def get_total_measures(self) -> int:
        return self.grid.get_total_measures()

    def set_total_measures(self, measures: int) -> None:
        self.grid.set_total_measures(measures)

    def get_key_mode(self) -> str:
        return self.composer.key_mode

    def set_key_mode(self, key_mode: str) -> None:
        self.composer.set_key_mode(key_mode)
        self._retune_all_instances()

    def get_root(self) -> int:
        return self.composer.root

    def set_root(self, root: int) -> None:
        self.composer.set_root(root)
        self._retune_all_instances()

    def get_chord_progression(self):
        return self.composer.chord_progression

    def set_chord_progression(self, progression) -> None:
        self.composer.set_chord_progression(progression)
        self._retune_all_instances()
        
    def generate_random_chord_progression(self) -> ChordProgression:
        progression = ChordProgression.generate_random_progression(
            self.composer.key_mode,
            self.grid.get_total_measures()
        )
        self.set_chord_progression(progression)
        self._retune_all_instances()
        return progression

    # ======================================================================
    # Roles / pitch range
    # ======================================================================
    
    def get_animal_role(self, animal_id: str) -> str:
        return self.loops[animal_id].role

    def set_animal_role(self, animal_id: str, new_role: str) -> None:
        loop = self.loops[animal_id]
        
        self.composer.change_animal_role(animal_id, loop.role, new_role)
        loop.role = new_role
        
        self._retune_animal_instances(animal_id)

    # ======================================================================
    # Recording → create/update loops
    # ======================================================================

    def set_recording(self, animal_id: str) -> None:
        """
        Call after user records audio and wants to edit.
        """
        audio_path = get_recording_wav_path(animal_id, "raw")
        if animal_id in self.loops:
            start_frame = self.loops[animal_id].start_frame
            num_frames = self.loops[animal_id].num_frames
        else:
            start_frame = 0
            num_frames = None
        self.recording = Recording(audio_path, start_frame, num_frames)

    def get_recording_duration(self) -> float:
        if not self.recording:
            return 0.0
        return self.grid.frame_to_time(self.recording.get_num_frames())

    def set_left_margin_of_recording(self, fraction: float) -> None:
        if not self.recording:
            return
        left_frame = int(round(fraction * self.recording.last_frame))
        self.recording.set_left_margin(left_frame)

    def set_right_margin_of_recording(self, fraction: float) -> None:
        if not self.recording:
            return
        right_frame = int(round(fraction * self.recording.last_frame))
        self.recording.set_right_margin(right_frame)

    def shift_recording(self, num_slots: float) -> None:
        if not self.recording:
            return
        self.recording.shift(self.grid.slot_to_frame(num_slots))

    def finalize_animal_loop(self, animal_id: str, role: Optional[str] = None) -> None:
        """
        Turn the current `Recording` into a Loop for this animal.
        """
        if not self.recording:
            return

        start_frame = self.recording.start_frame
        num_frames = self.recording.get_num_frames()
        trimmed_data = self.recording.trimmed.data
        audio_data, base_midi = tune_sample_and_save(animal_id, trimmed_data)

        #  If this is the first animal, Composer sets the global root to nearest C
        self.composer.handle_first_animal_if_needed(base_midi)

        if not role:
            slots = self.grid.frame_to_slot(num_frames)
            beats = self.slot_to_beat(slots)
            role = self.composer.guess_initial_role(base_midi, beats)

        self.loops[animal_id] = Loop(audio_data, start_frame, num_frames, base_midi, role)
        self.composer.register_animal_role(animal_id, role)
        
    def delete_animal_loop(self, animal_id: str) -> None:
        self.loops.pop(animal_id)
        self.composer.unregister_animal_role(animal_id, self.loops[animal_id].role)


    # ======================================================================
    # Grid / loop instances (UI-facing)
    # ======================================================================
    
    def slot_to_time(self, slot: float) -> float:
        tick = self.grid.slot_to_tick(int(slot))
        return self.grid.tick_to_time(tick)
    
    def time_to_slot(self, time_sec: float) -> float:
        frame = self.grid.time_to_frame(time_sec)
        return self.grid.frame_to_slot(frame)
    
    def get_slots_per_beat(self) -> int:
        return self.grid.get_slots_per_beat()
    
    def get_slots_per_measure(self) -> int: 
        return self.grid.get_slots_per_beat() * self.grid.get_beats_per_measure()
    
    def beat_to_slot(self, beat: float) -> float:
        ppb = self.grid.get_slots_per_beat()
        return beat * ppb
    
    def slot_to_beat(self, slot: float) -> float:
        ppb = self.grid.get_slots_per_beat()
        return slot / ppb
    
    def get_total_slots(self) -> int:
        return self.grid.get_total_slots()
    
    def get_base_midi(self, animal_id: str) -> int:
        return self.loops[animal_id].midi
    
    def get_instance_info(self, animal_id: str, start_slot: int) -> Tuple[int, int]:
        """
        For UI drawing: returns (num_slots, midi)
        """
        return self.loops[animal_id].get_instance_info(start_slot, self.grid.frame_to_slot)

    def get_instances_info(self, animal_id: str):
        """
        For UI drawing: returns (start_slot, num_slots, midi)
        """
        return self.loops[animal_id].get_instances_info(self.grid.frame_to_slot)

    def add_loop_instance(self, animal_id: str, start_slot: int, overlap: bool = False, midi: Optional[int] = None) -> bool:
        """ 
        Attempt to add a loop instance for the given animal at the given slot. 
        Returns True if successful, False if failed due to overlap.
        """
        loop = self.loops[animal_id]

        return loop.add_to_grid(start_slot, self.grid.frame_to_slot, overlap, midi)

    def remove_loop_instance(self, animal_id: str, start_slot: int) -> None:
        self.loops[animal_id].instances.pop(start_slot, None)
        
    def clear_loop_instances(self, animal_id: str) -> None:
        for start_slot in self.loops[animal_id].instances:
            self.remove_loop_instance(animal_id, start_slot)
            
    def set_pitch_of_instance(self, animal_id: str, start_slot: int, midi: int) -> None:
        loop = self.loops[animal_id]
        loop.set_pitch(start_slot, midi)

    def shift_animal_octave(self, animal_id: str, semitones: int) -> None:
        """Shift all instances of an animal by the given number of semitones (12 = octave)."""
        loop = self.loops.get(animal_id)
        if not loop:
            return

        # Shift the base MIDI so visual positions stay the same (mod 8)
        loop.midi = max(0, min(127, loop.midi + semitones))

        # Shift all instance pitches
        for start_slot in list(loop.instances.keys()):
            instance = loop.instances[start_slot]
            new_midi = instance.midi + semitones
            new_midi = max(0, min(127, new_midi))
            loop.set_pitch(start_slot, new_midi)

    def mute_instance_slots(self, animal_id: str, start_slot: int, slot_1: int, slot_2: int, mute: bool) -> None:
        loop = self.loops[animal_id]
        frame_1 = self.grid.slot_to_frame(slot_1)
        frame_2 = self.grid.slot_to_frame(slot_2)
        loop.toggle_mute(start_slot, frame_1, frame_2, mute)

    def slide_instance(self, animal_id: str, old_start_slot: int, new_start_slot: int, overlap: bool = False) -> int:
        """
        Attempt to move loop instance from old_start_slot to new_start_slot.
        Returns slot of final position (may be unchanged if failed due to overlap).
        """
        self.pause()
        return self.loops[animal_id].slide(old_start_slot, new_start_slot, self.grid.frame_to_slot, overlap)

    def set_loop_volume(self, animal_id: str, volume: float) -> None:
        self.loops[animal_id].set_volume(volume)

    # ======================================================================
    # Playback (UI-facing, delegate to AudioManager)
    # ======================================================================

    def set_callbacks(self, on_sing, on_close) -> None:
        self.audio_manager.set_callbacks(on_sing, on_close)

    def on_update(self) -> None:
        self.audio_manager.on_update()

    def play(self, start_time: float = 0.0, loop: bool = False, animal_id: Optional[str] = None) -> None:
        """Play all loops or a specific animal's loop if animal_id is provided."""
        self.audio_manager.play(start_time, loop, animal_id)

    def pause(self) -> None:
        self.audio_manager.pause()

    def toggle_play(self, start_time: float = 0.0, loop: bool = False) -> None:
        if self.audio_manager.is_playing():
            self.audio_manager.pause()
        else:
            self.audio_manager.play(start_time, loop)

    def play_recording_preview(self, offset: float = 0.0, repeat: bool = False) -> None:
        if not self.recording:
            return
        self.audio_manager.play_recording(self.recording, offset, repeat)

    def toggle_play_recording_preview(self, offset: float = 0.0, repeat: bool = False) -> None:
        if self.audio_manager.is_playing():
            self.audio_manager.pause()
        else:
            self.play_recording_preview(offset, repeat)
    
    def set_volume(self, volume: float) -> None:
        self.audio_manager.set_volume(volume)

    def play_note_preview(self, animal_id: str, start_slot: int) -> None:
        if animal_id not in self.loops:
            return
        loop = self.loops[animal_id]
        if start_slot not in loop.instances:
            return

        gen = loop.get_generator(start_slot, frame_offset=0, loop=False)
        self.audio_manager.mixer.add(gen)

    # ======================================================================
    # Composition helpers
    # ======================================================================

    def auto_generate_for_animal(self, animal_id: str) -> None:
        """
        High-level helper:
        1) generate rhythm for this animal (in beats),
        2) convert to slots,
        3) ask pitch generator for MIDI per event,
        4) add instances to the grid with those MIDI notes.
        """
        loop = self.loops[animal_id]

        # 1) rhythm (beats)
        beat_starts = self._generate_rhythm_beats_for_animal(animal_id)

        # 2) beats -> slots
        start_slots = [int(round(self.beat_to_slot(b))) for b in beat_starts]

        # 3) pitch
        pitch_by_slot = self._generate_pitch_map_for_animal(
            animal_id=animal_id,
            start_slots=start_slots,
        )

        # 4) actually add loop instances
        loop = self.loops[animal_id]
        for s in start_slots:
            midi = pitch_by_slot.get(s)
            if midi is not None:
                loop.add_to_grid(s, self.grid.frame_to_slot, overlap=False, midi=midi)
            

    def _generate_pitch_map_for_animal(
        self,
        animal_id: str,
        start_slots: list[int],
    ) -> dict[int, int | None]:
        """
        Decide which MIDI note each generated loop instance should use.

        Uses C pentatonic scale (C, D, E, G, A) starting from the note closest to the animal's base pitch.
        Adds notes probabilistically based on sample size.

        Returns:
            dict mapping start_slot -> midi
        """
        import random

        loop = self.loops[animal_id]
        base_midi = loop.midi  # the "natural" pitch of this animal's recording

        # C pentatonic scale intervals (semitones from C)
        # C=0, D=2, E=4, G=7, A=9
        pentatonic_intervals = [0, 2, 4, 7, 9]

        # Find the C below the base_midi
        root_c = self.settings.root

        # Build pentatonic scale notes across multiple octaves (to have range)
        pentatonic_notes = []
        for octave_offset in range(-1, 3):  # Cover a good range of octaves
            for interval in pentatonic_intervals:
                note = root_c + (octave_offset * 12) + interval
                if 0 <= note <= 127:  # Valid MIDI range
                    pentatonic_notes.append(note)

        # Find the closest pentatonic note to base_midi
        closest_note = min(pentatonic_notes, key=lambda n: abs(n - base_midi))
        closest_index = pentatonic_notes.index(closest_note)

        # Generate melody with 70% probability per note
        # The start_slots already represent the rhythm (placed by _generate_rhythm_beats_for_animal)
        pitch_map: dict[int, int | None] = {}
        current_note_index = closest_index

        # Check if this is the first animal
        is_first_animal = len(self.loops) == 1

        for s in start_slots:
            # Force first animal to have a note on beat 1 (slot 0)
            if is_first_animal and s == 0:
                pitch_map[s] = pentatonic_notes[current_note_index]
                step = random.choice([-1, 0, 1, 1])
                current_note_index = max(0, min(len(pentatonic_notes) - 1, current_note_index + step))
            # 70% chance to add a note at other rhythm points
            elif random.random() < 0.7:
                # Add a note from the pentatonic scale
                pitch_map[s] = pentatonic_notes[current_note_index]

                # Move to next note in scale (with some randomness)
                step = random.choice([-1, 0, 1, 1])  # Slight bias toward going up
                current_note_index = max(0, min(len(pentatonic_notes) - 1, current_note_index + step))
            else:
                # No note at this rhythm point (30% chance)
                pitch_map[s] = None

        return pitch_map
    
    # Rhythm Generation
    def _get_existing_bass_templates(self, exclude_animal_id: str) -> list[list[float]]:
        templates: list[list[float]] = []

        for aid in self.composer.animals_by_role.get("bass"):
            if aid == exclude_animal_id:
                continue

            tpl = [self.slot_to_beat(start_slot) % self.grid.get_beats_per_measure()
                   for start_slot in self.loops[aid].instances]
            tpl.sort()
            templates.append(tpl)

        return templates

    def _generate_rhythm_beats_for_animal(self, animal_id: str) -> None:
        loop = self.loops[animal_id]
        role = loop.role

        beats_per_measure = self.grid.get_beats_per_measure()
        total_measures = self.grid.get_total_measures()
        total_beats = beats_per_measure * total_measures

        loop_slots = self.grid.frame_to_slot(loop.num_frames)
        loop_beats = self.slot_to_beat(loop_slots)

        # Simple placement logic based on note length:
        # - Short note (< 1.5 beats): place every beat
        # - Medium note (1.5-3 beats): place every 2 beats
        # - Long note (>= 3 beats): place every 4 beats

        if loop_beats < 1.5:
            # Short note: every beat
            interval = 1
        elif loop_beats < 3:
            # Medium note: every 2 beats
            interval = 2
        else:
            # Long note: every 4 beats
            interval = 4

        # Generate beat positions without overlap
        beat_starts = []
        current_beat = 0

        while current_beat < total_beats:
            # Check if this placement would fit completely
            if current_beat + loop_beats <= total_beats:
                beat_starts.append(float(current_beat))
            current_beat += interval

        return beat_starts

    
    # ======================================================================
    # TODO: LATER IF WE CAN
    # ======================================================================
            
    def _retune_all_instances(self) -> None:
        pass
    
    def _retune_animal_instances(self, animal_id: str) -> None:
        pass
